"""Archive outages must not become prerequisites for otherwise usable work."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    monkeypatch.syspath_prepend(str(ROOT / "plugins/studio-archive/scripts"))
    api = importlib.import_module("work_folder")
    # These tests exercise execution storage, not an external receipt service.
    runtime = SimpleNamespace(
        begin_report=lambda loaded: {"status": "not_applicable"},
        finish_report=lambda loaded: {"status": "not_applicable"},
        report_declarations=lambda output: [],
        retain_artifact_manifest=lambda *args: None,
    )
    monkeypatch.setattr(api.ledger, "_reporting_runtime", lambda: runtime)
    broken_state = tmp_path / "unavailable-archive"
    broken_state.write_text("not a directory")
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_STATE_DIR", str(broken_state))
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(broken_state))
    return api


def prepare(work, tmp_path, workflow="financial-analysis", **options):
    source = tmp_path / "selected.txt"
    source.write_text("Selected evidence; preserve these bytes")
    return work.prepare_work(
        tmp_path / "Working result",
        workflow_id=workflow,
        sources=[(source, "source")],
        label="Requested professional work",
        purpose="Review the supplied evidence",
        **options,
    )


@pytest.mark.parametrize(
    "workflow",
    [
        "financial-analysis",
        "business-planning",
        "treasury-forecast",
        "journal-bank-reconciliation",
        "journal-sampling",
        "posizioni-negoziali",
        "contenzioso-tributario",
        "archive-organization",
        "aml-review",
        "esg-reporting-assurance",
        "bilancio-xbrl-it",
        "lipe",
    ],
)
def test_work_starts_without_archive_and_passes_ordinary_engine_contract(
    work, tmp_path, workflow
):
    from vera_assurance import load_client_engagement_context_file

    prepared = prepare(work, tmp_path, workflow)

    context = load_client_engagement_context_file(
        prepared["client_engagement_path"],
        expected_workflow_id=workflow,
        output_dir=prepared["client_engagement"]["output_dir"],
    )

    assert context["run_id"] == prepared["run"]["run_id"]
    assert prepared["run"]["status"] == "running"
    assert prepared["archive"]["status"] == "pending"
    assert prepared["workspace_kind"] == "general"
    assert prepared["client_identity_asserted"] is False
    assert (
        Path(context["input_bindings"][0]["path"]).read_text()
        == "Selected evidence; preserve these bytes"
    )


def test_repeated_request_retains_job_and_progress_after_original_is_removed(
    work, tmp_path
):
    first = prepare(work, tmp_path)
    output = Path(first["client_engagement"]["output_dir"]) / "draft.md"
    output.write_text("Completed analysis; continue from this point")
    source = tmp_path / "selected.txt"
    source.unlink()

    repeated = work.prepare_work(
        Path(first["work_folder"]),
        workflow_id="financial-analysis",
        sources=[(source, "source")],
        label="Requested professional work",
        purpose="Review the supplied evidence",
    )

    assert repeated["run"]["run_id"] == first["run"]["run_id"]
    assert output.read_text() == "Completed analysis; continue from this point"
    assert len(list(Path(first["work_folder"]).rglob("run.json"))) == 1


def test_existing_known_client_id_is_preserved_without_registration(work, tmp_path):
    client_id = "client_" + "a" * 24

    prepared = prepare(work, tmp_path, client_id=client_id)

    assert prepared["client_engagement"]["client_id"] == client_id
    assert prepared["client_identity_asserted"] is True
    assert prepared["archive"]["status"] == "pending"


@pytest.mark.parametrize("failure_at", ["finalize", "complete", "status_record"])
def test_saved_result_is_delivered_when_optional_closure_fails(
    work, tmp_path, monkeypatch, failure_at
):
    prepared = prepare(work, tmp_path)
    output = Path(prepared["client_engagement"]["output_dir"]) / "result.md"
    output.write_bytes(b"Completed professional result")

    def unavailable(*args, **kwargs):
        raise OSError("Synthetic unavailable Archive bookkeeping")

    if failure_at == "status_record":
        monkeypatch.setattr(work, "_save", unavailable)
    else:
        monkeypatch.setattr(work.ledger, failure_at + "_run", unavailable)

    delivered = work.finish_work(Path(prepared["work_folder"]))

    assert delivered["processing"]["status"] == "result_ready"
    assert delivered["archive"]["status"] == "pending"
    assert delivered["outputs"][0]["path"] == str(output)
    assert output.read_bytes() == b"Completed professional result"


def completed(work, tmp_path):
    prepared = prepare(work, tmp_path)
    (Path(prepared["client_engagement"]["output_dir"]) / "result.md").write_text(
        "Useful result"
    )
    work.finish_work(Path(prepared["work_folder"]))
    return prepared


def test_archive_failure_then_exact_retry_preserves_result_and_copies_one_job(
    work, tmp_path, monkeypatch
):
    prepared = completed(work, tmp_path)
    root = Path(prepared["work_folder"])
    target = tmp_path / "Archive destination"

    def unavailable(*args, **kwargs):
        raise OSError("Archive disconnected")

    with monkeypatch.context() as scoped:
        scoped.setattr(work.ledger, "_stable_copy", unavailable)
        failed = work.archive_work(root, target)
    archived = work.archive_work(root, target)
    replayed = work.archive_work(root, target)

    assert failed["processing"]["status"] == "result_ready"
    assert failed["archive"]["status"] == "pending"
    assert archived["archive"]["status"] == replayed["archive"]["status"] == "saved"
    assert (
        archived["run"]["run_id"]
        == replayed["run"]["run_id"]
        == prepared["run"]["run_id"]
    )
    assert len(list(target.rglob("run.json"))) == 1
    assert next(target.rglob("result.md")).read_text() == "Useful result"


def test_archive_retry_after_lost_status_write_reuses_committed_copy(
    work, tmp_path, monkeypatch
):
    prepared = completed(work, tmp_path)
    root = Path(prepared["work_folder"])
    target = tmp_path / "Archive destination"

    def unavailable(*args, **kwargs):
        raise OSError("Response bookkeeping failed after the archive copy")

    with monkeypatch.context() as scoped:
        scoped.setattr(work, "_save", unavailable)
        first = work.archive_work(root, target)
    retried = work.archive_work(root, target)

    assert first["status_record"]["status"] == "pending"
    assert retried["archive"]["status"] == "saved"
    assert len(list(target.rglob("run.json"))) == 1


def test_archive_destination_conflict_keeps_work_deliverable_and_other_client_unchanged(
    work, tmp_path
):
    prepared = completed(work, tmp_path)
    target = tmp_path / "Other client"
    target.mkdir()
    work.ledger.create_client_manifest(target, "client_" + "b" * 24)
    original = (target / "Vera/client.json").read_bytes()

    result = work.archive_work(Path(prepared["work_folder"]), target)

    assert result["archive"]["status"] == "pending"
    assert result["processing"]["status"] == "result_ready"
    assert (target / "Vera/client.json").read_bytes() == original
    assert not list(target.rglob("result.md"))


def test_changed_execution_input_is_not_accepted_as_an_archive_outage(work, tmp_path):
    prepared = prepare(work, tmp_path)
    source = Path(prepared["client_engagement"]["input_bindings"][0]["path"])
    source.write_text("Changed evidence")

    with pytest.raises(work.ledger.LedgerError):
        work.inspect_work(Path(prepared["work_folder"]))


def test_an_empty_run_cannot_claim_a_delivered_result(work, tmp_path):
    prepared = prepare(work, tmp_path)

    with pytest.raises(ValueError, match="No saved result"):
        work.finish_work(Path(prepared["work_folder"]))


def test_treasury_engine_calculates_and_delivers_while_archive_is_unavailable(
    work, tmp_path, monkeypatch
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/treasury-forecast/scripts"))
    from run_treasury import validate_context
    from treasury_session import create_session

    from tests.plugins.test_treasury_forecast import first

    source = tmp_path / "treasury-inputs.json"
    source.write_text(json.dumps(first()))
    prepared = work.prepare_work(
        tmp_path / "Forecast work",
        workflow_id="treasury-forecast",
        sources=[(source, "source")],
        label="Forecast",
        purpose="Prepare the requested cash forecast",
    )
    context = validate_context(Path(prepared["client_engagement_path"]))
    bound_source = Path(context["input_bindings"][0]["path"])
    inputs = json.loads(bound_source.read_text())
    inputs.update(
        client_id=context["client_id"], engagement_id=context["engagement_id"]
    )

    forecast = create_session(
        Path(context["output_dir"]),
        inputs,
        None,
        source_paths=[bound_source],
        context_path=Path(prepared["client_engagement_path"]),
    )
    delivered = work.finish_work(Path(prepared["work_folder"]))

    assert forecast["daily"][-1]["closing_cash"] == "15000.00"
    assert forecast["status"] == "draft_for_review"
    assert delivered["processing"]["status"] == "result_ready"
    assert delivered["archive"]["status"] == "pending"
    assert (Path(context["output_dir"]) / "treasury_session.json").is_file()
