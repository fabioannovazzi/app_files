"""Reuse the incident transport without sending client extraction evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

from tests.plugins.test_operational_incident_client import client


def episode(tmp_path):
    output = tmp_path / "run"
    history = output / "pdf_recovery"
    history.mkdir(parents=True)
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps(
            {
                "workflow_id": "journal-bank-reconciliation",
                "output_dir": str(output),
                "run_id": "PRIVATE_CLIENT",
                "input_manifest_sha256": "b" * 64,
            }
        )
    )
    arguments = [
        "run",
        "inspect_inputs.py",
        "--client-engagement",
        str(context),
        "--output-dir",
        str(output),
        "--pdf-recovery",
        "trial",
    ]
    return history, arguments


def event(history, number, passed):
    (history / f"attempt-{number:02}.json").write_text(
        json.dumps(
            {
                "attempt": number,
                "diagnostics": {
                    "accepted": passed,
                    "detail": "PRIVATE_CLIENT VAT SECRET 99999.90",
                    "readable_rows": ["PRIVATE_CUSTOMER"],
                },
                "reason": "PRIVATE_REASON",
                "readable_row_count": 4,
                "rows_sha256": "c" * 64,
                "layout": {
                    "agent_adapter": {
                        "path": "/private/CLIENT.py",
                        "source": "PRIVATE_CODE",
                    }
                },
            }
        )
    )


def freeze_event(history, number):
    path = history / f"attempt-{number:02}.json"
    trial = json.loads(path.read_text())
    trial["layout_sha256"] = hashlib.sha256(
        json.dumps(
            trial["layout"], sort_keys=True, ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()
    path.write_text(json.dumps(trial))
    value = {
        "status": "frozen_requires_mapping_review",
        "qualified": False,
        "previous_sha256": hashlib.sha256(
            json.dumps(
                trial, sort_keys=True, ensure_ascii=False, allow_nan=False
            ).encode()
        ).hexdigest(),
        "rows_sha256": trial["rows_sha256"],
        "layout_sha256": trial["layout_sha256"],
    }
    (history / "freeze_receipt.json").write_text(json.dumps(value))


def test_bank_and_journal_recoveries_keep_separate_linked_incidents(
    tmp_path, monkeypatch
):
    reporter, store, _ = client(tmp_path, monkeypatch)
    history, arguments = episode(tmp_path)
    bank_history = history / "bank" / ("a" * 64)
    bank_history.mkdir(parents=True)
    execution = reporter.execution_identity("journal-bank-reconciliation", arguments)
    event(history, 1, False)
    event(bank_history, 1, False)
    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)
    event(bank_history, 2, True)
    freeze_event(bank_history, 2)

    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)

    state = json.loads(reporter._state_path().read_text())
    journal = state["pdf_recoveries"][execution["operation_id"]]
    bank = state["pdf_recoveries"][execution["operation_id"] + ":bank:" + "a" * 64]
    assert journal["original"]["report_id"] != bank["original"]["report_id"]
    assert len(journal["reported"]) == 1
    assert len(bank["reported"]) == 3
    reports = store.queue()
    assert "PRIVATE_CUSTOMER" not in json.dumps(reports)


def test_initial_bank_failure_links_only_its_own_source_recovery(tmp_path, monkeypatch):
    reporter, store, _ = client(tmp_path, monkeypatch)
    history, arguments = episode(tmp_path)
    execution = reporter.execution_identity("journal-bank-reconciliation", arguments)
    (history.parent / "inspection.json").write_text(
        json.dumps(
            {
                "bank": {
                    "files": [
                        {
                            "source_sha256": "a" * 64,
                            "parser": "pdf_table",
                            "qualification_status": "unsupported_source_layout",
                        },
                        {
                            "source_sha256": "b" * 64,
                            "parser": "pdf_table",
                            "qualification_status": "needs_review",
                        },
                    ]
                }
            }
        )
    )
    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)
    bank_history = history / "bank" / ("a" * 64)
    bank_history.mkdir(parents=True)
    event(bank_history, 1, True)
    freeze_event(bank_history, 1)

    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)

    state = reporter._read()
    assert len(state["pdf_recoveries"]) == 1
    assert len(store.queue()) == 1
    assert len(state["recovery_evidence_receipts"]) == 2
    assert "unsupported_bank_pdf_layout" in json.dumps(store.queue())


@pytest.mark.parametrize("local_only", [False, True])
def test_failure_attempt_and_replay_share_incident_without_closing_original_task(
    tmp_path, monkeypatch, local_only
):
    reporter, store, _ = client(tmp_path, monkeypatch)
    if local_only:
        monkeypatch.setenv("MPARANZA_INCIDENT_DELIVERY", "local-only")
    history, arguments = episode(tmp_path)
    execution = reporter.execution_identity("journal-bank-reconciliation", arguments)
    event(history, 1, False)
    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)
    # A new host process must preserve the original report's exact session binding.
    monkeypatch.setattr(reporter, "_SESSION", str(uuid4()))
    event(history, 2, True)
    freeze_event(history, 2)

    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)
    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)

    state = json.loads(reporter._state_path().read_text())
    original = state["pdf_recoveries"][execution["operation_id"]]["original"]
    assert len(state["pdf_recoveries"][execution["operation_id"]]["reported"]) == 3
    if local_only:
        assert store.queue() == []
        reports = [item["payload"]["report"] for item in state["outbox"]]
        assert len(reports) == 3
        assert reports[1]["evidence_for_report_id"] == original["report_id"]
        assert reports[2]["evidence_for_report_id"] == original["report_id"]
        assert reports[2]["measurements"]["original_task_verified"] is False
        transmitted = json.dumps(reports)
    else:
        incidents = store.queue()
        assert len(incidents) == 1
        assert incidents[0]["status"] == "open"
        assert incidents[0]["outcomes"] == []
        assert len(state["recovery_evidence_receipts"]) == 2
        assert state["outbox"] == []
        transmitted = json.dumps(incidents)
    assert "PRIVATE_" not in transmitted
    assert "99999.90" not in transmitted
    assert "source-reference adapter" in transmitted
    assert "extraction recovered locally" in transmitted


def test_success_without_observed_failure_does_not_create_incident(
    tmp_path, monkeypatch
):
    reporter, store, _ = client(tmp_path, monkeypatch)
    history, arguments = episode(tmp_path)
    execution = reporter.execution_identity("journal-bank-reconciliation", arguments)
    event(history, 1, True)

    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)

    assert store.queue() == []


def test_reporting_refuses_other_case_output(tmp_path, monkeypatch):
    reporter, store, _ = client(tmp_path, monkeypatch)
    history, arguments = episode(tmp_path)
    arguments[arguments.index("--output-dir") + 1] = str(tmp_path / "other_case")
    execution = reporter.execution_identity("journal-bank-reconciliation", arguments)
    event(history, 1, False)

    with pytest.raises(ValueError, match="same bound workflow"):
        reporter.report_pdf_recovery(
            "journal-bank-reconciliation", arguments, execution
        )

    assert store.queue() == []


def test_handled_inspection_failure_is_reported_even_when_first_repair_passes(
    tmp_path, monkeypatch
):
    reporter, store, _ = client(tmp_path, monkeypatch)
    history, arguments = episode(tmp_path)
    arguments = arguments[:-2]
    execution = reporter.execution_identity("journal-bank-reconciliation", arguments)
    (history.parent / "inspection.json").write_text(
        json.dumps(
            {
                "journal": {
                    "files": [
                        {
                            "registration_diagnostics": {
                                "accepted": False,
                                "reason": "registration_pdf_incomplete_or_unbalanced",
                                "readable_row_count": 2,
                                "rejected_rows": [
                                    {
                                        "reason": "unclaimed_source_amount",
                                        "private": "PRIVATE_SOURCE",
                                    }
                                ],
                            }
                        }
                    ]
                }
            }
        )
    )
    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)
    event(history, 1, True)

    reporter.report_pdf_recovery("journal-bank-reconciliation", arguments, execution)

    state = reporter._read()
    assert len(store.queue()) == 1
    assert len(state["recovery_evidence_receipts"]) == 1
    assert "unclaimed_source_amount" in json.dumps(store.queue())
    assert "PRIVATE_SOURCE" not in json.dumps(store.queue())


def test_managed_helper_zero_exit_still_reports_failed_pdf_checks(
    tmp_path, monkeypatch
):
    reporter, store, _ = client(tmp_path, monkeypatch)
    history, arguments = episode(tmp_path)
    event(history, 1, False)
    path = (
        Path(__file__).resolve().parents[2]
        / "plugins/vera/scripts/managed_python_runtime.py"
    )
    spec = importlib.util.spec_from_file_location("pdf_incident_launcher", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setattr(launcher, "_execute_with_diagnostics", lambda *_: (0, None))

    exit_code = launcher.run_verified_helper(
        tmp_path, arguments, "journal-bank-reconciliation"
    )

    assert exit_code == 0
    assert len(store.queue()) == 1
    assert store.queue()[0]["status"] == "open"
    assert reporter._read()["receipts"][0]["report"]["stage"] == "pdf-recovery"


@pytest.mark.parametrize("passed", [False, True])
def test_unbound_freeze_file_cannot_report_extraction_recovery(
    tmp_path, monkeypatch, passed
):
    reporter, store, _ = client(tmp_path, monkeypatch)
    history, arguments = episode(tmp_path)
    execution = reporter.execution_identity("journal-bank-reconciliation", arguments)
    event(history, 1, False)
    event(history, 2, passed)
    freeze_event(history, 2)
    if passed:
        receipt = json.loads((history / "freeze_receipt.json").read_text())
        receipt["rows_sha256"] = "d" * 64
        (history / "freeze_receipt.json").write_text(json.dumps(receipt))

    with pytest.raises(ValueError, match="Freeze evidence"):
        reporter.report_pdf_recovery(
            "journal-bank-reconciliation", arguments, execution
        )

    assert "PDF_REPLAY_MATCHED" not in json.dumps(store.queue())
