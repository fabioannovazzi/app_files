"""A damaged run cannot hide unrelated work or become approved evidence."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def archive(tmp_path, monkeypatch):
    scripts = ROOT / "plugins/studio-archive/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    import archive_core as core

    ledger = core.ledger
    root = tmp_path / "Studio"
    client = root / "Synthetic"
    client.mkdir(parents=True)
    state = tmp_path / "state"
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_STATE_DIR", str(state))
    core.configure_archive(root, state_dir=state)
    core.refresh_archive(state_dir=state)
    scope = core.studio_archive_status(state_dir=state)["scopes"][0]["scope_id"]
    cid = core.set_studio_client_identity(
        scope, legal_names=["Synthetic"], state_dir=state
    )["client"]["client_id"]
    eid = core.create_studio_client_engagement(
        cid, "Synthetic workflows", state_dir=state
    )["engagement"]["engagement_id"]
    source = tmp_path / "source.txt"
    source.write_bytes(b"synthetic input")
    receipt = ledger.import_document(client, cid, eid, source, "source")["receipt"]
    first = ledger.prepare_run(
        client,
        cid,
        eid,
        "sales-plan",
        "1.0.0",
        input_ids=[receipt["input_id"]],
        label="Plan",
        purpose="Synthetic test",
    )
    second = ledger.prepare_run(
        client,
        cid,
        eid,
        "financial-analysis",
        "1.0.0",
        input_ids=[receipt["input_id"]],
        label="Analysis",
        purpose="Synthetic test",
    )
    path = Path(first["output_dir"]).parent / "input_manifest.json"
    value = json.loads(path.read_bytes())
    value.pop("content_sha256")
    value["schema_version"] = "unsupported.synthetic.v0"
    path.write_text(json.dumps(ledger._sealed(value)), encoding="utf-8")
    return core, client, cid, eid, first, second, state, path


def test_activity_listing_keeps_healthy_run_and_marks_bad_record(archive):
    core, client, cid, eid, first, second, state, path = archive
    before = path.read_bytes()
    result = core.list_studio_client_engagements(cid, state_dir=state)["engagements"][0]
    assert result["workflow_run_count"] == 2
    assert [r["run_id"] for r in result["workflow_runs"]] == [second["run"]["run_id"]]
    assert result["blocked_runs"] == [
        {
            "run_id": first["run"]["run_id"],
            "issue_code": "invalid_run_record",
            "reason": "Run integrity validation failed; original records are preserved.",
            "available": False,
        }
    ]
    assert result["ledger_complete"] is False
    assert path.read_bytes() == before


def test_recovery_reports_partial_state_without_rewriting_bad_manifest(archive):
    core, client, cid, eid, first, second, state, path = archive
    before = path.read_bytes()
    result = core.recover_studio_client_ledger(state_dir=state)
    assert result["status"] == "recovered_with_issues"
    assert result["recovery_complete"] is False
    assert result["run_count"] == 1
    assert result["blocked_runs"][0]["run_id"] == first["run"]["run_id"]
    assert path.read_bytes() == before
    page = next((client / "Vera/Pratiche").glob("*/Indice.html")).read_text(
        encoding="utf-8"
    )
    assert first["run"]["run_id"] in page
    assert second["run"]["run_id"] in page
    assert "Attività non disponibile" in page


def test_bad_run_remains_unusable_and_valid_run_can_start(archive):
    core, client, cid, eid, first, second, state, path = archive
    with pytest.raises(core.ledger.LedgerError, match="manifest shape"):
        core.ledger.start_run(client, eid, first["run"]["run_id"])
    result = core.ledger.start_run(client, eid, second["run"]["run_id"])
    assert result["run"]["status"] == "running"


def test_native_navigation_keeps_blocked_record_non_actionable(archive, monkeypatch):
    core, client, cid, eid, first, second, state, path = archive
    scripts = ROOT / "plugins/vera/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    import native_archive_navigation as navigation

    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "REVIEWER")
    result = navigation.catalogue(
        ROOT / "plugins/studio-archive", {"client_id": cid, "engagement_id": eid}
    )
    rows = {row["run_id"]: row for row in result["works"]}
    assert rows[first["run"]["run_id"]]["status"] == "blocked"
    assert rows[first["run"]["run_id"]]["can_start"] is False
    assert rows[first["run"]["run_id"]]["closure_available"] is False
    assert rows[second["run"]["run_id"]]["can_start"] is True


def test_same_request_cannot_replace_invalid_run_but_unrelated_preparation_works(
    archive,
):
    core, client, cid, eid, first, second, state, path = archive
    input_id = core.ledger.list_inputs(client, eid)[0]["input_id"]
    before = path.read_bytes()
    with pytest.raises(core.ledger.LedgerError, match="manifest shape"):
        core.ledger.prepare_run(
            client,
            cid,
            eid,
            "sales-plan",
            "1.0.0",
            input_ids=[input_id],
            label="Plan",
            purpose="Synthetic test",
        )
    replay = core.ledger.prepare_run(
        client,
        cid,
        eid,
        "financial-analysis",
        "1.0.0",
        input_ids=[input_id],
        label="Analysis",
        purpose="Synthetic test",
    )
    assert replay["status"] == "already_prepared"
    assert replay["run"]["run_id"] == second["run"]["run_id"]
    new_run = core.ledger.prepare_run(
        client, cid, eid, "new-workflow", "1.0.0", input_ids=[input_id]
    )
    assert new_run["status"] == "prepared"
    assert new_run["run"]["run_id"] not in {
        first["run"]["run_id"],
        second["run"]["run_id"],
    }
    assert path.read_bytes() == before
    assert len(core.ledger.inspect_runs(client, eid)["runs"]) == 2


def test_unknown_header_still_blocks_new_work_to_preserve_idempotency(archive):
    core, client, cid, eid, first, second, state, path = archive
    (path.parent / "run.json").write_text("{}")
    input_id = core.ledger.list_inputs(client, eid)[0]["input_id"]
    with pytest.raises(core.ledger.LedgerError, match="Run manifest shape"):
        core.ledger.prepare_run(
            client, cid, eid, "new-workflow", "1.0.0", input_ids=[input_id]
        )
