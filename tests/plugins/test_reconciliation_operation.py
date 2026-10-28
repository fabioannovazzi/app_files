"""Ordinary import-to-delivery behavior, using the actual public producer."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.open_item_reconciliation.test_reviewed_tabular_adapter import spec
from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
)

__all__: list[str] = []


@pytest.fixture
def operation(archive_core, monkeypatch):
    path = Path(archive_core.__file__).with_name("reconcile_open_items.py")
    module_spec = importlib.util.spec_from_file_location(
        "test_reconcile_operation", path
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    monkeypatch.setattr(module, "archive", archive_core)
    return module


def request_for(case, tmp_path):
    invoice = tmp_path / "invoices.csv"
    bank = tmp_path / "bank.csv"
    invoice.write_text("InvoiceX;DateX;ValueX\nFT-2026-0102;01/07/2026;1220.00\n")
    bank.write_text(
        "IdX;DescriptionX;PostedX;ValueX\nTX-010;Saldo FT-2026-0102;11/07/2026;1220.00\n"
    )
    invoices, payments = spec(invoice), spec(bank, "bank_statement")
    payments["tabular"]["columns"] = {
        "source_record_id": "IdX",
        "description": "DescriptionX",
        "posting_date": "PostedX",
        "amount": "ValueX",
    }
    for mapping in (invoices, payments):
        mapping["tabular"]["last_data_row"] = 2
        mapping.pop("reviewer_ref")
        mapping.pop("reviewed_on")
    return {
        "client_id": case.client_id,
        "engagement_id": case.engagement_id,
        "request_id": "ordinary-exact-payment",
        "sources": [
            {"path": str(invoice), "mapping": invoices},
            {"path": str(bank), "mapping": payments},
        ],
        "assumptions": {
            "cutoff_date": "2026-07-01",
            "post_cutoff_events_excluded": False,
        },
    }


@pytest.mark.parametrize("unmapped_send", [False, True])
def test_one_call_delivers_exact_match_and_reopening_does_not_recalculate(
    operation, client_case, tmp_path, monkeypatch, reporting_runtime, unmapped_send
):
    request = request_for(client_case, tmp_path)
    if unmapped_send:
        original_start = operation.archive.start_studio_client_workflow

        def start_with_unmapped_send(client_id, engagement_id, run_id, **kwargs):
            result = original_start(client_id, engagement_id, run_id, **kwargs)
            from archive_reporting import record_send

            loaded = operation.archive.ledger.load_run(
                client_case.client_root, engagement_id, run_id
            )
            record_send(
                Path(loaded["run_root"]),
                "Unmapped case-derived content",
                channel="worker",
            )
            return result

        monkeypatch.setattr(
            operation.archive, "start_studio_client_workflow", start_with_unmapped_send
        )
    result = operation.reconcile(request, state_dir=client_case.state_dir)

    assert result["status"] == "completed"
    assert result["accounting_status"] == "verified"
    assert result["report_ready"] is True
    assert result["review_handoff"]["required_before_final_delivery"] is False
    assert result["artifacts"] and all(Path(p).is_file() for p in result["artifacts"])
    output = Path(result["output_dir"])
    rows = json.loads((output / "reconciliation_results.json").read_text())[
        "reconciliation_rows"
    ]
    assert rows[0]["rule_applied"] == "external_bank_match"
    assert rows[0]["supporting_bank_date"] == "2026-07-11"
    assert rows[0]["reconciliation_status"] == "closed"
    if unmapped_send:
        assert result["warnings"][0]["kind"] == "data_usage_reporting_incomplete"
        report = json.loads((output.parent / "model_data_report.json").read_text())
        assert "sent_data_has_no_source_coordinates" in report["errors"]
        assert result["reporting"]["collection_status"] == "incomplete"

    def forbidden(*args, **kwargs):
        raise AssertionError("Reopening must not repeat producer, workers or assurance")

    monkeypatch.setattr(operation, "_command", forbidden)
    reopened = operation.reconcile(request, state_dir=client_case.state_dir)
    assert reopened["run_id"] == result["run_id"]
    assert reopened["status"] == "completed"
    changed = copy.deepcopy(request)
    changed["sources"][0]["mapping"]["perimeter"]["party_ref"] = "another-party"
    with pytest.raises(operation.archive.ArchiveError, match="different mappings"):
        operation.reconcile(changed, state_dir=client_case.state_dir)


def test_failed_producer_retains_run_and_repeated_request_does_not_retry(
    operation, client_case, tmp_path, monkeypatch, reporting_runtime
):
    calls = []

    def failed(*args, **kwargs):
        calls.append(args)
        raise operation.archive.ArchiveError("Synthetic producer failure")

    monkeypatch.setattr(operation, "_command", failed)
    request = request_for(client_case, tmp_path)
    with pytest.raises(
        operation.archive.ArchiveError, match="Synthetic producer failure"
    ):
        operation.reconcile(request, state_dir=client_case.state_dir)
    with pytest.raises(operation.archive.ArchiveError, match="Existing run is failed"):
        operation.reconcile(request, state_dir=client_case.state_dir)
    assert len(calls) == 1


def test_unresolved_payment_delivers_resumable_draft_without_claiming_approval(
    operation, client_case, tmp_path, reporting_runtime
):
    request = request_for(client_case, tmp_path)
    request["sources"][1]["mapping"]["perimeter"]["party_ref"] = "different-payer"

    result = operation.reconcile(request, state_dir=client_case.state_dir)

    assert result["status"] == "review_required"
    assert result["report_ready"] is False
    assert result["artifacts"] and all(Path(p).is_file() for p in result["artifacts"])
    loaded = operation.archive.ledger.load_run(
        client_case.client_root, client_case.engagement_id, result["run_id"]
    )
    assert loaded["run"]["status"] == "running"
    assert result["reporting"]["display_markdown"]


def test_packaged_operation_retains_its_release_for_later_review(client_case, tmp_path):
    root = Path(__file__).resolve().parents[2]
    with ZipFile(root / "plugin_packages/vera/vera-plugin.zip") as package:
        package.extractall(tmp_path / "installed")
    installed = tmp_path / "installed/vera-codex-plugin/plugins/vera"
    request = request_for(client_case, tmp_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request))
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(installed / "modules/studio-archive/scripts/reconcile_open_items.py"),
            "--request",
            str(request_path),
            "--state-dir",
            str(client_case.state_dir),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "MPARANZA_RUNTIME_ROOT": str(tmp_path / "runtime")},
    )
    assert result.returncode == 0, result.stderr
    delivery = json.loads(result.stdout)
    assert delivery["status"] == "completed"
    assert delivery["report_ready"] is True
    run = Path(delivery["output_dir"]).parent.parent
    binding = json.loads((run / "execution-runtime.json").read_text())
    assert len(binding["package_sha256"]) == 64
    assert delivery["artifacts"]


@pytest.mark.parametrize("legacy_checkpoint", [False, True])
def test_reviewed_draft_finishes_with_retained_checkpoint_without_recalculation(
    operation, client_case, tmp_path, monkeypatch, reporting_runtime, legacy_checkpoint
):
    request = request_for(client_case, tmp_path)
    request["sources"] = request["sources"][:1]
    draft = operation.reconcile(request, state_dir=client_case.state_dir)
    output = Path(draft["output_dir"])
    checkpoint = json.loads(
        (output.parent / "reconciliation-review-checkpoint.json").read_text()
    )["content_sha256"]
    payload = json.loads((output / "review_payload.json").read_text())
    scripts = (
        Path(__file__).resolve().parents[2] / "plugins/open-item-reconciliation/scripts"
    )
    monkeypatch.syspath_prepend(str(scripts))
    import review_server

    applied = review_server.apply_decisions(
        output,
        {
            "reviewer": "agent.codex",
            "expected_predecessor_checkpoint": checkpoint,
            "decisions": [
                {"item_id": item["id"], "action": "accept"} for item in payload["items"]
            ],
        },
    )
    assert applied["application_status"] == "awaiting_regeneration"
    context = output.parent.parent / "context.json"
    operation._command(
        "raw_input_runner.py",
        [
            "--client-engagement",
            str(context),
            "--output-subdirectory",
            "reconciliation",
            "--expected-predecessor-checkpoint",
            checkpoint,
        ],
        output.parent / "regeneration.log",
    )
    original = operation._command

    def replay_only(script, arguments, log):
        assert script == "audit_assurance.py"
        assert arguments[-2:] == ["--expected-predecessor-checkpoint", checkpoint]
        return original(script, arguments, log)

    monkeypatch.setattr(operation, "_command", replay_only)
    if legacy_checkpoint:
        (output.parent / "reconciliation-review-checkpoint.json").unlink()
    finished = operation.finish_reconciliation(
        client_case.client_id,
        client_case.engagement_id,
        draft["run_id"],
        state_dir=client_case.state_dir,
        expected_predecessor_checkpoint=checkpoint if legacy_checkpoint else None,
    )
    assert finished["status"] == "completed"
    assert finished["report_ready"] is True
    assert finished["run_id"] == draft["run_id"]


def test_unsupported_source_is_rejected_before_any_archive_write(
    operation, tmp_path, monkeypatch
):
    source = tmp_path / "payments.csv"
    source.write_text("InvoiceX;DateX;ValueX\nF1;01/09/2026;100\n")
    mapping = spec(source)
    mapping["role"] = "payment_order"

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid source must not create Archive records")

    monkeypatch.setattr(operation.archive, "import_studio_client_document", forbidden)
    request = {
        "client_id": "unused",
        "engagement_id": "unused",
        "request_id": "invalid",
        "sources": [{"path": str(source), "mapping": mapping}],
    }
    with pytest.raises(
        operation.archive.ArchiveError, match="does not support this source role"
    ):
        operation.reconcile(request)


def test_declared_lists_normal_operation_delivers_draft_and_reports_separately(
    operation, client_case, tmp_path, reporting_runtime
):
    from tests.open_item_reconciliation.test_declared_payment_lists import case

    source, assumptions = case(tmp_path)
    mappings = assumptions.pop("reviewed_source_decisions")
    request = {
        "client_id": client_case.client_id,
        "engagement_id": client_case.engagement_id,
        "request_id": "declared-list-draft",
        "assumptions": assumptions,
        "sources": [
            {"path": str(source / name), "mapping": mapping}
            for name, mapping in mappings.items()
        ],
    }
    result = operation.reconcile(request, state_dir=client_case.state_dir)

    assert result["accounting_status"] == "review_required"
    assert result["report_ready"] is False
    assert result["artifacts"] and all(Path(p).is_file() for p in result["artifacts"])
    output = Path(result["output_dir"])
    rows = json.loads((output / "reconciliation_results.json").read_text())[
        "reconciliation_rows"
    ]
    assert [row["residual_amount"] for row in rows] == ["0.00", "150.00"]
    assert (output.parent / "model_data_report.json").is_file()
    assert result["reporting"]["status"] != "not_applicable"
