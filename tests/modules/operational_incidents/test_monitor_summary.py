"""Open-item counts retain unknowns and invalidate stale reviewed exclusions."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.summarize_incident_monitor import evidence_hash, payload_hash, summarize


def incident(incident_id="case-a"):
    return {
        "incident_id": incident_id,
        "status": "open",
        "revision": 3,
        "remedy": {"kind": "diagnostic-request"},
        "reports": [{"report_id": "original", "exit_code": 17}],
        "report_records": [{"report_id": "original", "installation_id": "owner"}],
        "evidence": [],
        "outcomes": [],
        "recovery_events": [],
    }


def snapshot(*incidents):
    return {
        "queue_limit": 1000,
        "queue": copy.deepcopy(list(incidents)),
        "incidents": copy.deepcopy(list(incidents)),
    }


def reviewed(row, kind="controlled_fixture"):
    return {
        "monitor_reviews": {
            row["incident_id"]: {
                "kind": kind,
                "reviewed_at": "2026-10-15T20:00:00Z",
                "reason": "Inspected exact controlled evidence, not an error keyword.",
                "evidence_refs": ["private-acceptance-receipt"],
                "report_hashes": {
                    report["report_id"]: payload_hash(report)
                    for report in row["reports"]
                },
                "evidence_sha256": evidence_hash(row),
                "verification": {
                    "original_task_verified": True,
                    "original_inputs_preserved": True,
                    "scope": "Original archive refresh and source imports",
                    "result": "Refresh and both unchanged original imports verified",
                },
            }
        }
    }


def test_count_distinguishes_open_fixture_and_verified_scope_pending_closure():
    fixture = incident("fixture")
    recovered_scope = incident("archive")
    still_open = incident("unknown")
    ledger = reviewed(fixture)
    ledger["monitor_reviews"].update(
        reviewed(recovered_scope, "technical_recovery_pending_closure")[
            "monitor_reviews"
        ]
    )

    result = summarize(snapshot(fixture, recovered_scope, still_open), ledger)

    assert result["raw_open_incidents"] == 3
    assert result["effective_open_incidents"] == 1
    assert result["controlled_fixture_incidents"] == 1
    assert result["technical_recovery_pending_closure_incidents"] == 1
    assert result["summary_en"].startswith("Open technical problems: 1.")
    assert recovered_scope["status"] == "open"


def test_similar_exit_code_and_old_free_text_disposition_do_not_exclude_case():
    row = incident()
    ledger = {"records": [{"incident_id": "case-a", "disposition": "fixture"}]}

    result = summarize(snapshot(row), ledger)

    assert result["effective_open_incidents"] == 1


@pytest.mark.parametrize(
    "change",
    ["new-report", "report-payload", "supplement", "remedy", "owner", "failed-retry"],
)
def test_new_evidence_invalidates_review_and_reopens_effective_item(change):
    row = incident()
    ledger = reviewed(row, "technical_recovery_pending_closure")
    if change == "new-report":
        row["reports"].append({"report_id": "new", "exit_code": 17})
    elif change == "report-payload":
        row["reports"][0]["exit_code"] = 1
    elif change == "supplement":
        row["evidence"].append({"report_id": "reply"})
    elif change == "remedy":
        row["revision"] += 1
    elif change == "owner":
        row["report_records"][0]["installation_id"] = "other-owner"
    else:
        row["recovery_events"].append({"kind": "retry-failed"})

    result = summarize(snapshot(row), ledger)

    assert result["effective_open_incidents"] == 1
    assert result["items"][0]["review_stale"] is True


def test_fixture_review_cannot_hide_new_report_with_identical_error():
    row = incident()
    ledger = reviewed(row)
    row["reports"].append({"report_id": "new", "exit_code": 17})

    result = summarize(snapshot(row), ledger)

    assert result["effective_open_incidents"] == 1
    assert result["controlled_fixture_incidents"] == 0


@pytest.mark.parametrize(
    "missing",
    ["original_task_verified", "original_inputs_preserved", "scope", "result"],
)
def test_retry_success_alone_does_not_prove_original_technical_scope(missing):
    row = incident()
    row["outcomes"].append({"execution_succeeded": True, "status": "action-required"})
    ledger = reviewed(row, "technical_recovery_pending_closure")
    ledger["monitor_reviews"]["case-a"]["verification"].pop(missing)

    result = summarize(snapshot(row), ledger)

    assert result["effective_open_incidents"] == 1


@pytest.mark.parametrize("missing", ["reason", "reviewed_at", "evidence_refs"])
def test_unsubstantiated_exclusion_stays_open(missing):
    row = incident()
    ledger = reviewed(row)
    ledger["monitor_reviews"]["case-a"].pop(missing)

    result = summarize(snapshot(row), ledger)

    assert result["effective_open_incidents"] == 1


def test_derived_clock_capture_changes_do_not_reopen_reviewed_case():
    row = incident()
    ledger = reviewed(row)
    row["report_records"][0]["capture"] = {"capture_overdue": True}
    row["reporting_summary"] = {"overdue_capture": 1}

    result = summarize(snapshot(row), ledger)

    assert result["controlled_fixture_incidents"] == 1


def test_derived_diagnostic_deadlines_do_not_change_reviewed_technical_evidence():
    row = incident()
    ledger = reviewed(row)
    row["remedy_followups"] = [
        {"overdue": True, "reporter_contact": {"last_seen": "now"}}
    ]
    row["diagnostic_requests"] = [
        {"state": "published-awaiting-receipt", "overdue": True}
    ]

    result = summarize(snapshot(row), ledger)

    assert result["controlled_fixture_incidents"] == 1


def test_repeated_reports_count_one_incident_not_two_machines():
    row = incident()
    row["reports"].append({"report_id": "second", "exit_code": 1})

    result = summarize(snapshot(row), {})

    assert result["effective_open_incidents"] == 1
    assert result["raw_open_incidents"] == 1


@pytest.mark.parametrize("broken", ["missing-show", "duplicate", "race", "truncated"])
def test_incomplete_or_inconsistent_snapshot_cannot_emit_lower_count(broken):
    value = snapshot(incident())
    if broken == "missing-show":
        value["incidents"] = []
    elif broken == "duplicate":
        value["queue"].append(incident())
    elif broken == "race":
        value["incidents"][0]["revision"] += 1
    else:
        value["queue_limit"] = 1

    with pytest.raises(ValueError):
        summarize(value, {})


def test_queue_disappearance_requires_show_and_does_not_imply_recovery():
    ledger = {"last_monitor_check": {"queue_ids": ["case-a"]}}

    with pytest.raises(ValueError, match="Missing show evidence"):
        summarize(snapshot(), ledger)


def test_unresolved_disappeared_case_rejects_empty_count():
    value = snapshot()
    value["incidents"].append(incident())
    ledger = {"last_monitor_check": {"queue_ids": ["case-a"]}}

    with pytest.raises(ValueError, match="unresolved incident disappeared"):
        summarize(value, ledger)


def test_closed_case_can_leave_open_count_after_explicit_show():
    closed = incident()
    closed["status"] = "recovered"
    value = snapshot()
    value["incidents"].append(closed)
    ledger = {"last_monitor_check": {"queue_ids": ["case-a"]}}

    result = summarize(value, ledger)

    assert result["raw_open_incidents"] == 0
    assert result["effective_open_incidents"] == 0


@pytest.mark.parametrize("valid", [True, False])
def test_cli_is_read_only_and_fails_without_publishing_partial_count(tmp_path, valid):
    value = snapshot(incident())
    if not valid:
        value["incidents"] = []
    source = tmp_path / "snapshot.json"
    ledger = tmp_path / "ledger.json"
    source.write_text(json.dumps(value))
    ledger.write_text("{}")
    script = (
        Path(__file__).resolve().parents[3] / "scripts/summarize_incident_monitor.py"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--snapshot",
            str(source),
            "--ledger",
            str(ledger),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert ledger.read_text() == "{}"
    assert source.read_text() == json.dumps(value)
    assert result.returncode == (0 if valid else 2)
    if valid:
        assert json.loads(result.stdout)["effective_open_incidents"] == 1
    else:
        assert result.stdout == ""
        assert "Count unavailable" in result.stderr
