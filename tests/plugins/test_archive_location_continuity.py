"""Saved preparation must continue into calculation without rediscovering storage."""

from __future__ import annotations

import importlib
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import reporting_runtime
from tests.plugins.test_vera_customer_folder_ledger import archive_script_imports
from tests.plugins.test_vera_studio_archive_component import isolated_mcp_launcher


def prepared_case(tmp_path, monkeypatch, *, blocked=False):
    core = importlib.import_module("archive_core")
    work = importlib.import_module("work_folder")
    state = tmp_path / "state"
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_STATE_DIR", str(state))
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(tmp_path / "profile"))
    if blocked:
        (tmp_path / ".vera-work-continuity").write_text("unwritable secondary pointer")
    source = tmp_path / "source.txt"
    source.write_text("Original source evidence")
    result = work.prepare_work(
        tmp_path / "Vari",
        workflow_id="financial-analysis",
        sources=[(source, "source")],
        label="Synthetic work",
        purpose="Continue the same saved job",
    )
    return core, work, result


@pytest.mark.parametrize("blocked", [False, True])
def test_saved_work_native_read_and_stage_handoff_without_archive(
    tmp_path, monkeypatch, blocked
):
    core, work, saved = prepared_case(tmp_path, monkeypatch, blocked=blocked)
    context = Path(saved["client_engagement_path"])
    run = saved["run"]
    output = Path(saved["client_engagement"]["output_dir"])
    (output / "prepared.txt").write_text("Prepared evidence for calculation")
    assert saved["work_binding"]["status"] == ("unavailable" if blocked else "retained")
    with core.use_studio_run_context(context) if blocked else nullcontext():
        read = core.read_studio_run_artifact(
            run["client_id"],
            run["engagement_id"],
            run["run_id"],
            "outputs/prepared.txt",
        )
        final = core.finalize_studio_client_workflow(
            run["client_id"],
            run["engagement_id"],
            run["run_id"],
            [
                {
                    "artifact_id": "prepared",
                    "path": "prepared.txt",
                    "purpose": "Calculation input",
                    "audience": "internal",
                    "media_type": "text/plain",
                }
            ],
        )
        next_stage = core.prepare_studio_client_workflow(
            run["engagement_id"],
            "financial-analysis",
            upstream_artifacts=[
                {"run_id": run["run_id"], "artifact_id": "prepared", "role": "source"}
            ],
            idempotency_key="same-job-calculation",
            new_run=True,
        )
    assert read
    assert final["status"] == "ready_for_review"
    assert next_stage["client_id"] == run["client_id"]
    assert next_stage["engagement_id"] == run["engagement_id"]
    assert Path(next_stage["client_engagement_path"]).is_relative_to(
        Path(saved["work_folder"])
    )
    with core.use_studio_run_context(Path(next_stage["client_engagement_path"])):
        started = core.start_studio_client_workflow(
            run["client_id"], run["engagement_id"], next_stage["run"]["run_id"]
        )
    assert started["status"] == "running"
    resumed = work.resume_work(context, "financial-analysis")
    assert resumed["run"]["run_id"] == run["run_id"]


def test_explicit_context_rejects_cross_run_selection_and_does_not_leak(
    tmp_path, monkeypatch
):
    core, _, saved = prepared_case(tmp_path, monkeypatch, blocked=True)
    run = saved["run"]
    with core.use_studio_run_context(Path(saved["client_engagement_path"])):
        with pytest.raises(core.ArchiveError, match="different selected run"):
            core.read_studio_run_artifact(
                run["client_id"],
                run["engagement_id"],
                "run_" + "f" * 24,
                "outputs/result.txt",
            )
    with pytest.raises((core.ArchiveError, OSError)):
        core.read_studio_run_artifact(
            run["client_id"], run["engagement_id"], run["run_id"], "outputs/result.txt"
        )


def test_explicit_context_rejects_changed_input_for_execution_but_delivers_saved_result(
    tmp_path, monkeypatch
):
    core, _, saved = prepared_case(tmp_path, monkeypatch, blocked=True)
    run = saved["run"]
    Path(saved["client_engagement"]["input_bindings"][0]["path"]).write_text(
        "Changed evidence"
    )
    (Path(saved["client_engagement"]["output_dir"]) / "result.txt").write_text(
        "Already saved useful result"
    )
    with core.use_studio_run_context(Path(saved["client_engagement_path"])):
        delivered = core.read_studio_run_artifact(
            run["client_id"], run["engagement_id"], run["run_id"], "outputs/result.txt"
        )
        with pytest.raises(
            core.ArchiveError, match="execution input no longer matches"
        ):
            core.start_studio_client_workflow(
                run["client_id"], run["engagement_id"], run["run_id"]
            )
    assert delivered


def declare_outputs(output, selected, artifact_id):
    return [
        {
            "artifact_id": artifact_id if path == selected else f"evidence-{index}",
            "path": str(path.relative_to(output)),
            "purpose": "Synthetic workflow evidence",
            "audience": "internal",
            "media_type": "application/octet-stream",
        }
        for index, path in enumerate(sorted(output.rglob("*")))
        if path.is_file()
    ]


@pytest.mark.parametrize(
    "storage",
    [
        "configured",
        "configuration_lost",
        "different_default",
        "retained",
        "context_only",
    ],
)
@pytest.mark.parametrize("path_kind", ["ordinary", "unicode", "deep"])
def test_bank_preparation_calculation_review_delivery_and_reopen(
    tmp_path, monkeypatch, storage, path_kind
):
    """Exercise real stage contracts; only the remote model is a labelled fixture."""
    import sys

    from openpyxl import load_workbook

    from tests.plugins.test_grouped_reconciliation import _environment
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _save_workbook,
        _write_pdf_table,
        load_core,
        load_semantic_review,
    )
    from tests.plugins.test_journal_bank_review_receipts import _decisions

    if path_kind == "unicode":
        tmp_path = tmp_path / "Studio Caffè 東京 ↳"
    elif path_kind == "deep":
        tmp_path = tmp_path / ("documenti-" + "x" * 90) / ("archivio-" + "y" * 90)
    tmp_path.mkdir(parents=True, exist_ok=True)
    archive = importlib.import_module("archive_core")
    work = importlib.import_module("work_folder")
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(tmp_path / "profile"))
    if storage == "context_only":
        (tmp_path / ".vera-work-continuity").write_text("Pointer storage unavailable")
    bank = tmp_path / "bank.xlsx"
    journal = tmp_path / "journal.pdf"
    _save_workbook(
        bank,
        [
            ["Date", "Description", "Amount"],
            ["2026-01-10 00:00:00", "Invoice Alpha", 100],
        ],
    )
    _write_pdf_table(
        journal,
        [
            [
                ["Date", "Description", "Reference", "Amount", "Balance", "Currency"],
                ["2026-01-10", "Invoice Alpha", "INV1001", "100.00", "1100.00", "EUR"],
            ]
        ],
    )
    if storage in {"configured", "configuration_lost", "different_default"}:
        destination = tmp_path / "Studio"
        destination.mkdir()
        archive.configure_archive(destination)
        client = archive.create_studio_client("Vari", general_workspace=True)["client"][
            "client_id"
        ]
        engagement = archive.create_studio_client_engagement(
            client, "Synthetic bank work"
        )["engagement"]["engagement_id"]
        bank_import = archive.import_studio_client_document(
            client, bank, "source", engagement_id=engagement
        )
        journal_import = archive.import_studio_client_document(
            client, journal, "journal", engagement_id=engagement
        )
        prepared = archive.prepare_studio_client_workflow(
            engagement,
            "journal-bank-reconciliation",
            input_ids=[bank_import["input_id"], journal_import["input_id"]],
        )
    else:
        prepared = work.prepare_work(
            tmp_path / "Vari",
            workflow_id="journal-bank-reconciliation",
            sources=[(bank, "source"), (journal, "journal")],
            label="Synthetic bank work",
            purpose="Verify whole workflow",
        )
    with archive.use_studio_run_context(Path(prepared["client_engagement_path"])):
        archive.start_studio_client_workflow(
            prepared["run"]["client_id"],
            prepared["run"]["engagement_id"],
            prepared["run"]["run_id"],
        )
    if storage == "configuration_lost":
        (tmp_path / "state" / "config.json").write_text(
            "corrupt secondary configuration"
        )
    elif storage == "different_default":
        alternate = tmp_path / "Different default"
        alternate.mkdir()
        archive.configure_archive(alternate)
    context = prepared["client_engagement"]
    context_path = Path(prepared["client_engagement_path"])
    run = prepared["run"]
    inputs = {item["role"]: item for item in context["input_bindings"]}
    output = Path(context["output_dir"])
    core = load_core()
    preparation = importlib.import_module("bank_working_copy")
    sealer = importlib.import_module("seal_review_receipts")
    prepared_bank = preparation.prepare_reviewed_bank_copies(
        {
            "reviewer_ref": "agent.synthetic",
            "reviewed_on": "2026-11-12",
            "files": [
                {
                    "source_path": inputs["source"]["path"],
                    "source_sha256": inputs["source"]["sha256"],
                    "sheet": 0,
                    "date_column": 0,
                    "description_column": 1,
                    "amount_column": 2,
                    "date_convention": "day_first",
                    "excluded_rows": [1],
                }
            ],
        },
        output,
        context=context,
    )
    assert prepared_bank["movement_count"] == 1
    csv = next((output / "bank-prepared").glob("*.csv"))
    with (
        archive.use_studio_run_context(context_path)
        if storage == "context_only"
        else nullcontext()
    ):
        archive.finalize_studio_client_workflow(
            run["client_id"],
            run["engagement_id"],
            run["run_id"],
            declare_outputs(output, csv, "prepared-bank"),
        )
        calculation = archive.prepare_studio_client_workflow(
            run["engagement_id"],
            "journal-bank-reconciliation",
            input_ids=[inputs["journal"]["binding_id"]],
            upstream_artifacts=[
                {
                    "run_id": run["run_id"],
                    "artifact_id": "prepared-bank",
                    "role": "source",
                }
            ],
            new_run=True,
            idempotency_key="calculation",
        )
    context = calculation["client_engagement"]
    context_path = Path(calculation["client_engagement_path"])
    run = calculation["run"]
    with archive.use_studio_run_context(context_path):
        archive.start_studio_client_workflow(
            run["client_id"], run["engagement_id"], run["run_id"]
        )
    from vera_assurance import load_client_engagement_context_file

    context = load_client_engagement_context_file(
        context_path, expected_workflow_id="journal-bank-reconciliation"
    )
    inputs = {item["role"]: Path(item["path"]) for item in context["input_bindings"]}
    output = Path(context["output_dir"])
    core.inspect_inputs(
        inputs["source"],
        inputs["journal"],
        output,
        language="it",
        document_language="it",
    )
    recipe_path = output / "suggested_recipe.json"
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    decisions = _decisions(recipe)
    for choice in decisions["bank"]["files"].values():
        choice["mapping"] = {
            "date": "date",
            "description": "description",
            "amount": "amount",
        }
        choice["excluded_monetary_columns"] = []
    recipe = sealer.seal_review_receipts(
        recipe,
        decisions,
        json.loads((output / "input_receipts.json").read_text(encoding="utf-8"))[
            "receipts"
        ],
        context,
    )
    recipe_path.write_text(json.dumps(recipe))
    reconciliation = output / "reconciliation"
    core.run_reconciliation(
        inputs["source"],
        inputs["journal"],
        reconciliation,
        recipe_path,
        language="it",
        document_language="it",
        client_run_id=context["run_id"],
        client_run_root=context_path.parent,
    )

    # Reuse only the synthetic model transport, preserving real source replay,
    # receipt validation, review orchestration and final workbook generation.
    semantic = load_semantic_review()
    fixture_dir = tmp_path / "model-fixture"
    fixture_dir.mkdir()
    _, _, model_calls = _environment(fixture_dir, monkeypatch)
    fixture = sys.modules["semantic_review"]
    monkeypatch.setitem(sys.modules, "semantic_review", semantic)
    monkeypatch.setattr(
        semantic, "run_isolated_native_worker", fixture.run_isolated_native_worker
    )
    monkeypatch.setattr(
        semantic, "discover_worker_selection", fixture.discover_worker_selection
    )
    reviewed = semantic.run_semantic_resolution_pipeline(
        reconciliation, output / "semantic-review", client_engagement=context
    )
    assert model_calls
    assert reviewed["reviewed_bank_count"] == 1
    assert reviewed["exhaustive"] is True
    result = json.loads(reviewed["result"].read_text(encoding="utf-8"))
    assert result["summary"]["bank_net"] == "100"
    assert result["summary"]["journal_net"] == "100"
    assert result["summary"]["bank_minus_journal"] == "0"
    assert result["summary"]["concordant_bank_count"] == 1
    assert result["entries_posted"] is False
    workbook = reviewed["workbook"]
    assert load_workbook(workbook).sheetnames == [
        "Sintesi",
        "Relazioni",
        "Banca",
        "Partitario",
    ]
    with (
        archive.use_studio_run_context(context_path)
        if storage == "context_only"
        else nullcontext()
    ):
        final = archive.finalize_studio_client_workflow(
            run["client_id"],
            run["engagement_id"],
            run["run_id"],
            declare_outputs(output, workbook, "final-workbook"),
        )
        completed = archive.complete_studio_client_workflow(
            run["client_id"], run["engagement_id"], run["run_id"]
        )
        delivered = archive.read_studio_run_artifact(
            run["client_id"],
            run["engagement_id"],
            run["run_id"],
            "outputs/" + str(workbook.relative_to(output)),
        )
    assert final["status"] == "ready_for_review"
    assert completed["status"] == "completed"
    assert (output / "model_data_report.json").is_file()
    assert delivered["reporting"]["status"] == "recorded"
    assert delivered
    resumed = work.resume_work(context_path, "journal-bank-reconciliation")
    assert resumed["run"]["run_id"] == run["run_id"]
    assert resumed["run"]["engagement_id"] == prepared["run"]["engagement_id"]
    assert workbook.is_file()


def test_native_mcp_reads_same_saved_context_when_pointer_storage_fails(
    tmp_path, monkeypatch
):
    from tests.plugins.test_vera_studio_archive_component import _mcp_tool

    _, _, saved = prepared_case(tmp_path, monkeypatch, blocked=True)
    output = Path(saved["client_engagement"]["output_dir"])
    (output / "result.txt").write_text(
        "Delivered result ↳ from saved context", encoding="utf-8"
    )
    run = saved["run"]
    result = _mcp_tool(
        "read_studio_run_artifact",
        {
            "client_id": run["client_id"],
            "engagement_id": run["engagement_id"],
            "run_id": run["run_id"],
            "path": "outputs/result.txt",
            "context_path": saved["client_engagement_path"],
        },
        state_dir=tmp_path / "state",
    )
    assert result.get("isError") is not True, result
    assert "Delivered result ↳ from saved context" in json.dumps(
        result, ensure_ascii=False
    )


@pytest.mark.parametrize("encoding", ["cp1252", "utf-8"])
def test_work_folder_json_survives_windows_legacy_stdout(
    tmp_path, monkeypatch, encoding
):
    import io
    import sys

    destination = tmp_path / "Studio Caffè 東京 ↳"
    destination.mkdir()
    _, work, saved = prepared_case(destination, monkeypatch)
    output = Path(saved["client_engagement"]["output_dir"])
    (output / "result-↳.txt").write_text("Useful result")
    stream = io.BytesIO()
    stdout = io.TextIOWrapper(stream, encoding=encoding)
    monkeypatch.setattr(sys, "stdout", stdout)
    assert (
        work.main(
            [
                "resume",
                "--context",
                saved["client_engagement_path"],
                "--workflow",
                "financial-analysis",
            ]
        )
        == 0
    )
    stdout.flush()
    assert (
        json.loads(stream.getvalue().decode(encoding))["run"]["run_id"]
        == saved["run"]["run_id"]
    )
    assert json.loads(stream.getvalue().decode(encoding))["work_folder"] == str(
        destination / "Vari"
    )
    assert stream.getvalue().isascii()


def test_native_mcp_context_carries_sealed_preparation_into_next_stage(
    tmp_path, monkeypatch
):
    from tests.plugins.test_vera_studio_archive_component import _mcp_tool

    _, _, saved = prepared_case(tmp_path, monkeypatch, blocked=True)
    run = saved["run"]
    identity = {key: run[key] for key in ("client_id", "engagement_id", "run_id")}
    identity["context_path"] = saved["client_engagement_path"]
    output = Path(saved["client_engagement"]["output_dir"])
    (output / "prepared.txt").write_text("Prepared source for next stage")
    sealed = _mcp_tool(
        "finalize_studio_client_workflow",
        {
            **identity,
            "artifacts": declare_outputs(output, output / "prepared.txt", "prepared"),
        },
        state_dir=tmp_path / "state",
    )
    assert sealed.get("isError") is not True, sealed
    prepared = _mcp_tool(
        "prepare_studio_client_workflow",
        {
            "context_path": identity["context_path"],
            "engagement_id": run["engagement_id"],
            "workflow_id": "financial-analysis",
            "new_run": True,
            "idempotency_key": "native-next-stage",
            "upstream_artifacts": [
                {"run_id": run["run_id"], "artifact_id": "prepared", "role": "source"}
            ],
        },
        state_dir=tmp_path / "state",
    )
    assert prepared.get("isError") is not True, prepared
    next_stage = prepared["structuredContent"]
    assert next_stage["engagement_id"] == run["engagement_id"]
    started = _mcp_tool(
        "start_studio_client_workflow",
        {
            "client_id": run["client_id"],
            "engagement_id": run["engagement_id"],
            "run_id": next_stage["run"]["run_id"],
            "context_path": next_stage["client_engagement_path"],
        },
        state_dir=tmp_path / "state",
    )
    assert started.get("isError") is not True, started
    assert started["structuredContent"]["status"] == "running"


def test_saved_context_rejects_tampered_identity(tmp_path, monkeypatch):
    core, _, saved = prepared_case(tmp_path, monkeypatch, blocked=True)
    context = Path(saved["client_engagement_path"])
    payload = json.loads(context.read_text(encoding="utf-8"))
    payload["client_id"] = "client_" + "f" * 24
    context.write_text(json.dumps(payload))
    with pytest.raises(core.ledger.LedgerError):
        with core.use_studio_run_context(context):
            pytest.fail("Tampered identity was admitted")
