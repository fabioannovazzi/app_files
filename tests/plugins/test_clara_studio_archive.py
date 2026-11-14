from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def setup_case(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/clara/scripts"))
    module = importlib.import_module("clara_studio_archive")
    state = tmp_path / "state"
    root = tmp_path / "archive"
    root.mkdir()
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_SESSION_ID", "case-creation-session")
    module.archive.configure_archive(root, state_dir=state, make_studio_default=True)
    client = module.archive.create_studio_client("Synthetic Équipe", state_dir=state)
    cid = client["client"]["client_id"]
    engagement = module.archive.create_studio_client_engagement(
        cid, "Synthetic advisory", state_dir=state
    )
    return module, state, cid, engagement["engagement"]["engagement_id"]


def test_create_and_resume_preserves_case_bytes(setup_case):
    module, state, cid, eid = setup_case
    created = module.open_case(
        cid, eid, objective="Évaluer la croissance", state_dir=state
    )
    path = Path(created["case_dir"])
    before = (path / "case_manifest.json").read_bytes()
    result = module.open_case(cid, eid, state_dir=state)
    assert result["status"] == "resumed"
    assert result["case_dir"] == created["case_dir"]
    assert (path / "case_manifest.json").read_bytes() == before
    assert result["data_handling"]["network_requests"] == 0


def test_existing_case_is_bound_without_moving_or_rewriting(setup_case, tmp_path):
    module, state, cid, eid = setup_case
    path = tmp_path / "existing"
    module.initialize_case(
        path,
        client="Legacy label",
        project="Legacy",
        objective="Saved",
        audience="Partner",
    )
    before = {p.name: p.read_bytes() for p in path.glob("*.json")}
    result = module.open_case(cid, eid, case_dir=str(path), state_dir=state)
    assert result["case_dir"] == str(path)
    assert {name: (path / name).read_bytes() for name in before} == before


def test_same_case_cannot_be_adopted_by_another_engagement(setup_case):
    module, state, cid, eid = setup_case
    first = module.open_case(cid, eid, objective="Original", state_dir=state)
    other = module.archive.create_studio_client_engagement(
        cid, "Other", state_dir=state
    )["engagement"]["engagement_id"]
    with pytest.raises(ValueError, match="already bound"):
        module.open_case(cid, other, case_dir=first["case_dir"], state_dir=state)


def test_client_id_mismatch_cannot_open_engagement(setup_case):
    module, state, cid, eid = setup_case
    other = module.archive.create_studio_client("Another client", state_dir=state)[
        "client"
    ]["client_id"]
    with pytest.raises((ValueError, module.ledger.LedgerError)):
        module.open_case(other, eid, objective="Wrong client", state_dir=state)


def test_missing_bound_case_does_not_initialize_replacement(setup_case):
    module, state, cid, eid = setup_case
    first = module.open_case(cid, eid, objective="Original", state_dir=state)
    path = Path(first["case_dir"])
    path.rename(path.with_name("retained"))
    with pytest.raises(ValueError, match="unavailable"):
        module.open_case(cid, eid, objective="Replacement", state_dir=state)
    assert not path.exists()


def test_mcp_process_restart_resumes_bound_case(setup_case, monkeypatch):
    import os
    import subprocess
    import sys

    module, state, cid, eid = setup_case
    request = {
        "client_id": cid,
        "engagement_id": eid,
        "objective": "Synthetic durable case",
    }
    created = module.open_case(**request, state_dir=state)
    request.pop("objective")
    wire = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "clara_archive_case", "arguments": request},
            }
        )
        + "\n"
    )
    completed = subprocess.run(
        ["node", str(ROOT / "plugins/clara/scripts/studio_archive_mcp.cjs")],
        input=wire,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env={
            **os.environ,
            "VERA_STUDIO_ARCHIVE_STATE_DIR": str(state.parent / "fresh-chat-state"),
            "VERA_STUDIO_ARCHIVE_SESSION_ID": "fresh-resumption-session",
            "VERA_STUDIO_ARCHIVE_PYTHON": sys.executable,
            "MPARANZA_INCIDENT_DELIVERY": "local-only",
        },
        check=True,
    )
    result = json.loads(completed.stdout)["result"]
    assert result["isError"] is False, result
    assert result["structuredContent"]["status"] == "resumed"
    assert result["structuredContent"]["case_dir"] == created["case_dir"]


def test_existing_case_inside_another_client_is_rejected(setup_case):
    module, state, cid, eid = setup_case
    other = module.archive.create_studio_client(
        "Other synthetic client", state_dir=state
    )
    path = Path(other["client_folder"]["client_root"]) / "legacy-case"
    module.initialize_case(
        path, client="Other", project="Saved", objective="Existing", audience="Partner"
    )
    with pytest.raises(ValueError, match="another Archive client"):
        module.open_case(cid, eid, case_dir=str(path), state_dir=state)
    assert not (path / module.BINDING).exists()


def test_symlink_case_cannot_redirect_binding(setup_case, tmp_path):
    module, state, cid, eid = setup_case
    case = tmp_path / "existing-case"
    module.initialize_case(
        case, client="Saved", project="Saved", objective="Existing", audience="Partner"
    )
    link = tmp_path / "alias"
    link.symlink_to(case, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic"):
        module.open_case(cid, eid, case_dir=str(link), state_dir=state)
    assert not (case / module.BINDING).exists()


def test_missing_case_identity_cannot_adopt_replacement(setup_case):
    module, state, cid, eid = setup_case
    first = module.open_case(cid, eid, objective="Original", state_dir=state)
    path = Path(first["case_dir"])
    (path / module.BINDING).unlink()
    with pytest.raises(ValueError, match="identity is missing"):
        module.open_case(cid, eid, state_dir=state)
    assert not (path / module.BINDING).exists()


def test_bound_engagement_cannot_be_redirected_to_another_case(setup_case, tmp_path):
    module, state, cid, eid = setup_case
    module.open_case(cid, eid, objective="Original", state_dir=state)
    with pytest.raises(ValueError, match="already has a case"):
        module.open_case(
            cid, eid, case_dir=str(tmp_path / "replacement"), state_dir=state
        )
    assert not (tmp_path / "replacement").exists()


def test_closed_engagement_does_not_create_new_active_case(setup_case):
    module, state, cid, eid = setup_case
    module.archive.close_studio_client_engagement(cid, eid, state_dir=state)
    with pytest.raises(ValueError, match="open engagement"):
        module.open_case(cid, eid, objective="New work", state_dir=state)
