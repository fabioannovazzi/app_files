"""Missing secondary infrastructure must not hide a committed professional job."""

from __future__ import annotations

import builtins
import importlib
from pathlib import Path

import pytest

from tests.plugins.test_archive_fault_isolation import case


def test_checkpoint_profile_failure_returns_prepared_work(case, monkeypatch):
    core, studio, state, root, cid, eid, input_id = case

    def unavailable(*args):
        raise core.ArchiveError("Synthetic unavailable recovery profile")

    monkeypatch.setattr(core, "_recovery_store", unavailable)

    result = core.prepare_studio_client_workflow(
        eid, "financial-analysis", input_ids=[input_id], state_dir=state
    )

    assert result["status"] == "prepared"
    assert result["recovery"]["status"] == "unavailable"
    assert Path(result["client_engagement_path"]).is_file()


def test_missing_recovery_module_does_not_hide_prepared_work(case, monkeypatch):
    core, studio, state, root, cid, eid, input_id = case
    real_import = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "vera_assurance.recovery":
            raise ImportError("Synthetic unavailable recovery component")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)

    result = core.prepare_studio_client_workflow(
        eid, "financial-analysis", input_ids=[input_id], state_dir=state
    )

    assert result["status"] == "prepared"
    assert result["recovery"]["status"] == "unavailable"
    assert Path(result["client_engagement_path"]).is_file()


def test_missing_reporting_module_does_not_prevent_result_closure(case, monkeypatch):
    core, studio, state, root, cid, eid, input_id = case
    prepared = core.prepare_studio_client_workflow(
        eid, "posizioni-negoziali", input_ids=[input_id], state_dir=state
    )
    rid = prepared["run"]["run_id"]
    core.start_studio_client_workflow(cid, eid, rid, state_dir=state)
    output = Path(prepared["client_engagement"]["output_dir"]) / "result.md"
    output.write_text("Completed professional work")

    def missing():
        raise ImportError("Synthetic unavailable reporting module")

    monkeypatch.setattr(core.ledger, "_reporting_runtime", missing)

    finalized = core.finalize_studio_client_workflow(
        cid,
        eid,
        rid,
        [
            {
                "artifact_id": "result",
                "path": "result.md",
                "purpose": "Review",
                "audience": "review",
                "media_type": "text/markdown",
            }
        ],
        state_dir=state,
    )
    completed = core.complete_studio_client_workflow(cid, eid, rid, state_dir=state)

    assert finalized["status"] == "ready_for_review"
    assert completed["status"] == "completed"
    assert completed["reporting"]["status"] == "unavailable"
    assert output.read_text() == "Completed professional work"


@pytest.mark.parametrize("loader", ["ledger", "engine"])
@pytest.mark.parametrize("changed", [False, True])
def test_recovery_outage_allows_only_unchanged_execution_inputs(
    case, monkeypatch, loader, changed
):
    from vera_assurance import (
        AssuranceContractError,
        load_client_engagement_context_file,
        recovery,
    )

    core, studio, state, root, cid, eid, input_id = case
    prepared = core.prepare_studio_client_workflow(
        eid, "financial-analysis", input_ids=[input_id], state_dir=state
    )
    rid = prepared["run"]["run_id"]
    core.start_studio_client_workflow(cid, eid, rid, state_dir=state)
    if changed:
        Path(prepared["client_engagement"]["input_bindings"][0]["path"]).write_text(
            "Changed bytes"
        )

    def unavailable(*args):
        raise OSError("Synthetic unavailable recovery storage")

    monkeypatch.setattr(recovery, "repair_run_inputs", unavailable)

    def load():
        if loader == "ledger":
            return core.ledger.load_run(root, eid, rid)["context"]
        return load_client_engagement_context_file(
            prepared["client_engagement_path"],
            expected_workflow_id="financial-analysis",
        )

    if changed:
        with pytest.raises((core.ledger.LedgerError, AssuranceContractError)):
            load()
    else:
        assert load()["run_id"] == rid


def test_existing_work_resumes_and_delivers_without_archive_profile(case, monkeypatch):
    core, studio, state, root, cid, eid, input_id = case
    prepared = core.prepare_studio_client_workflow(
        eid, "posizioni-negoziali", input_ids=[input_id], state_dir=state
    )
    api = importlib.import_module("work_folder")
    broken = state / "unavailable-profile"
    broken.write_text("not a directory")
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(broken))
    context = Path(prepared["client_engagement_path"])

    resumed = api.resume_work(context, "posizioni-negoziali")
    output = Path(resumed["client_engagement"]["output_dir"]) / "position.md"
    output.write_text("Retained draft for professional review")
    delivered = api.deliver_work(context, "posizioni-negoziali")

    assert resumed["run"]["run_id"] == prepared["run"]["run_id"]
    assert delivered["processing"]["status"] == "result_ready"
    assert output.read_text() == "Retained draft for professional review"
    assert not (root / "pending-archive-work.json").exists()
