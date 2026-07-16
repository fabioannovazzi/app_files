from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "audit_local_review_workbench_writeback.py"


def load_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_local_review_workbench_writeback",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_check_entries_fixture_contains_browser_edit_target(tmp_path: Path) -> None:
    audit = load_audit_module()
    output_dir = tmp_path / "run"

    audit.write_check_entries_fixture(output_dir)

    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    item = review_payload["items"][0]
    assert review_payload["plugin"] == "check-entries"
    assert item["recommended_action"] == "edit"
    assert item["data"]["target_artifact"] == "check_results.csv"
    assert item["data"]["target_id_field"] == "source_row"
    assert item["data"]["target_field"] == "review_notes"
    assert run_intake["data_posture"]["remote_sql_execution_used"] is False
    assert (output_dir / "check_results.csv").exists()


def test_generic_plugin_fixture_uses_adapter_edit_target(tmp_path: Path) -> None:
    audit = load_audit_module()
    output_dir = tmp_path / "deep-research-run"

    fixture = audit.write_plugin_fixture(ROOT, "deep-research-validator", output_dir)

    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    item = review_payload["items"][0]
    target_artifact = output_dir / fixture["target_artifact"]
    target_payload = json.loads(target_artifact.read_text(encoding="utf-8"))
    assert review_payload["plugin"] == "deep-research-validator"
    assert item["recommended_action"] == "edit"
    assert item["data"]["target_artifact"] == "claims_review.json"
    assert item["data"]["target_records_key"] == "claims"
    assert fixture["item_id"] == item["id"]
    assert target_payload["claims"][0]["claim_index"] == "4"
    assert "proposed_fix" in target_payload["claims"][0]


def test_browser_writeback_report_marks_high_issues_as_failure() -> None:
    audit = load_audit_module()
    report = audit.BrowserWritebackReport(
        plugin="check-entries",
        output_dir="/tmp/run",
        issues=[
            audit.BrowserWritebackIssue(
                severity="high",
                code="target_artifact_not_updated",
                message="CSV did not change.",
            )
        ],
    )

    assert report.status == "needs_attention"
    assert audit._has_failure(report, "high") is True
    assert audit._has_failure(report, "blocker") is False


def test_markdown_report_names_fixture_not_customer_validation() -> None:
    audit = load_audit_module()
    report = audit.BrowserWritebackReport(
        plugin="check-entries",
        output_dir="/tmp/run",
        url="http://127.0.0.1:1234/review",
        row_count=1,
        decision_control_count=4,
        final_status="final_ready",
        csv_contains_edit=True,
        files_written=["ui_decisions.json"],
    )

    markdown = audit._markdown_report(report, root=ROOT)

    assert "Local Review Workbench Write-Back Audit" in markdown
    assert "check-entries" in markdown
    assert "not real customer-folder validation" in markdown


def test_suite_markdown_reports_all_plugin_rows() -> None:
    audit = load_audit_module()
    reports = [
        audit.BrowserWritebackReport(
            plugin="check-entries",
            output_dir="/tmp/check",
            target_artifact="check_results.csv",
            row_count=1,
            decision_control_count=4,
            final_status="final_ready",
            csv_contains_edit=True,
        ),
        audit.BrowserWritebackReport(
            plugin="deep-research-validator",
            output_dir="/tmp/deep",
            target_artifact="claims_review.json",
            row_count=1,
            decision_control_count=4,
            final_status="final_ready",
            csv_contains_edit=True,
        ),
    ]

    markdown = audit._markdown_suite_report(reports, root=ROOT)

    assert "Plugins audited: 2" in markdown
    assert "check_results.csv" in markdown
    assert "claims_review.json" in markdown
    assert "not real customer-folder validation" in markdown


def test_main_writes_report_path_for_machine_readable_evidence(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    audit = load_audit_module()
    report_path = tmp_path / "evidence" / "browser-writeback.json"

    def fake_audit_local_review_writebacks(**_kwargs):
        return [
            audit.BrowserWritebackReport(
                plugin="check-entries",
                output_dir="/tmp/check",
                target_artifact="check_results.csv",
                row_count=1,
                decision_control_count=4,
                final_status="final_ready",
                csv_contains_edit=True,
            )
        ]

    monkeypatch.setattr(
        audit,
        "audit_local_review_writebacks",
        fake_audit_local_review_writebacks,
    )

    exit_code = audit.main(
        [
            "--plugin",
            "all",
            "--format",
            "json",
            "--report-path",
            str(report_path),
            "--fail-on",
            "medium",
        ]
    )
    stdout = capsys.readouterr().out
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report_path.exists()
    assert json.loads(stdout) == payload
    assert payload["summary"]["plugin_count"] == 1
    assert payload["reports"][0]["plugin"] == "check-entries"
