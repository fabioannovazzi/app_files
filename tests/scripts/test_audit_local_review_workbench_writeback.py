from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "audit_local_review_workbench_writeback.py"
GENERIC_VERA_REVIEW_PLUGINS = (
    "open-item-reconciliation",
    "check-entries",
    "client-file-preparation",
    "concordato-plan-review",
    "deep-research-validator",
    "journal-bank-reconciliation",
    "journal-sampling",
    "prompt-optimizer",
    "report-builder",
)


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
    fixture_root = tmp_path / "run"

    fixture = audit.write_check_entries_fixture(fixture_root)
    output_dir = Path(fixture["output_dir"])

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
    assert item["data"]["target_id_field"] == "prepared_entry_id"
    assert item["data"]["target_field"] == "review_notes"
    assert run_intake["data_posture"]["remote_sql_execution_used"] is False
    assert run_intake["run_id"].startswith("run_")
    assert run_intake["path_reference"] == "run_root_relative"
    assert run_intake["output_dir"] == "outputs"
    assert all(not Path(path).is_absolute() for path in run_intake["input_paths"])
    assert Path(fixture["client_engagement"]) == output_dir.parent / "context.json"
    assert (output_dir / "check_results.csv").exists()


def test_generic_plugin_fixture_uses_adapter_edit_target(tmp_path: Path) -> None:
    audit = load_audit_module()
    output_dir = tmp_path / "deep-research-run"

    fixture = audit.write_plugin_fixture(ROOT, "deep-research-validator", output_dir)
    managed_output_dir = Path(fixture["output_dir"])

    review_payload = json.loads(
        (managed_output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    item = review_payload["items"][0]
    target_artifact = managed_output_dir / fixture["target_artifact"]
    target_payload = json.loads(target_artifact.read_text(encoding="utf-8"))
    assert review_payload["plugin"] == "deep-research-validator"
    assert item["recommended_action"] == "edit"
    assert item["data"]["target_artifact"] == "claims_review.json"
    assert item["data"]["target_records_key"] == "claims"
    assert fixture["item_id"] == item["id"]
    assert target_payload["claims"][0]["claim_index"] == "4"
    assert "proposed_fix" in target_payload["claims"][0]


@pytest.mark.parametrize("plugin", GENERIC_VERA_REVIEW_PLUGINS)
def test_generic_vera_fixture_uses_running_customer_folder_run(
    tmp_path: Path,
    plugin: str,
) -> None:
    audit = load_audit_module()
    fixture_root = tmp_path / plugin

    fixture = audit.write_plugin_fixture(ROOT, plugin, fixture_root)
    output_dir = Path(fixture["output_dir"])
    context_path = Path(fixture["client_engagement"])
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    run_manifest = json.loads(
        (context_path.parent / "run.json").read_text(encoding="utf-8")
    )
    workbench = audit.serve_review_workbench.LocalReviewWorkbench(
        plugin_dir=ROOT / "plugins" / plugin,
        output_dir=output_dir,
    )
    context = audit.serve_review_workbench._validate_vera_customer_run(workbench)

    assert output_dir == context_path.parent / "outputs"
    assert output_dir.is_relative_to(fixture_root)
    assert run_intake["run_id"] == fixture["run_id"] == run_manifest["run_id"]
    assert run_manifest["status"] == "running"
    assert run_intake["path_reference"] == "run_root_relative"
    assert run_intake["output_dir"] == "outputs"
    assert all(not Path(path).is_absolute() for path in run_intake["input_paths"])
    assert context is not None
    assert context["run_id"] == fixture["run_id"]


def test_managed_check_entries_fixture_passes_preflight_and_reaches_mcp(
    tmp_path: Path,
) -> None:
    audit = load_audit_module()
    fixture = audit.write_plugin_fixture(ROOT, "check-entries", tmp_path / "run")
    output_dir = Path(fixture["output_dir"])
    workbench = audit.serve_review_workbench.LocalReviewWorkbench(
        plugin_dir=ROOT / "plugins" / "check-entries",
        output_dir=output_dir,
    )

    context = audit.serve_review_workbench._validate_vera_customer_run(workbench)
    decisions = [
        {
            "item_id": fixture["item_id"],
            "action": "edit",
            "edit_value": "Reviewed from managed fixture",
        }
    ]
    saved = audit.serve_review_workbench.call_review_tool(
        workbench,
        "save_check_entries_decisions",
        {"decisions": decisions, "reviewer": "pytest"},
    )
    applied = audit.serve_review_workbench.call_review_tool(
        workbench,
        "apply_check_entries_decisions",
        {"decisions": decisions, "reviewer": "pytest"},
    )

    assert context is not None
    assert context["run_id"] == fixture["run_id"]
    assert saved["ok"] is True
    assert saved["persisted"] is True
    assert applied["ok"] is True
    assert applied["persisted"] is True
    assert applied["structured_update_count"] == 1
    assert (output_dir / "ui_decisions.json").is_file()
    assert (output_dir / "applied_decisions.json").is_file()


def test_suite_reports_each_managed_fixture_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = load_audit_module()
    suite_root = tmp_path / "suite"

    def fixture_only_audit(**kwargs):
        fixture = audit.write_plugin_fixture(
            kwargs["root"],
            kwargs["plugin"],
            kwargs["output_dir"],
        )
        return audit.BrowserWritebackReport(
            plugin=kwargs["plugin"],
            output_dir=fixture["output_dir"],
            item_id=fixture["item_id"],
            target_artifact=fixture["target_artifact"],
        )

    monkeypatch.setattr(audit, "audit_local_review_writeback", fixture_only_audit)

    reports = audit.audit_local_review_writebacks(
        root=ROOT,
        plugins=["check-entries", "deep-research-validator"],
        output_dir=suite_root,
    )

    assert [report.plugin for report in reports] == [
        "check-entries",
        "deep-research-validator",
    ]
    assert all(Path(report.output_dir).name == "outputs" for report in reports)
    assert all(
        Path(report.output_dir).is_relative_to(suite_root / report.plugin)
        for report in reports
    )


def test_new_client_fixture_uses_real_proposal_only_contract(
    tmp_path: Path,
) -> None:
    audit = load_audit_module()
    output_dir = tmp_path / "new-client-run"

    fixture = audit.write_plugin_fixture(ROOT, "new-client", output_dir)
    managed_output_dir = Path(fixture["output_dir"])

    review_payload = json.loads(
        (managed_output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (managed_output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert review_payload["schema_version"] == "1.1"
    assert review_payload["contract_version"] == "1.1"
    assert review_payload["item_count"] > 1
    assert final_artifacts["export_gate"]["relationship_ready"] is False
    assert fixture["writeback_mode"] == "review_proposal"
    assert fixture["target_artifact"] == "aml_assessment_draft.json"
    assert any(
        item["id"] == fixture["item_id"] and item["item_type"] == "aml_factor_section"
        for item in review_payload["items"]
    )


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
