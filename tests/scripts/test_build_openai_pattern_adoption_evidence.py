from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "build_openai_pattern_adoption_evidence.py"


def load_bundle_module():
    spec = importlib.util.spec_from_file_location(
        "build_openai_pattern_adoption_evidence",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_browser_writeback_report(
    path: Path,
    *,
    screenshot_path: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "summary": {
                    "plugin_count": 1,
                    "status_counts": {"ok": 1},
                    "issue_counts": {},
                },
                "reports": [
                    {
                        "plugin": "client-intake",
                        "status": "ok",
                        "row_count": 1,
                        "decision_control_count": 4,
                        "target_artifact": "document_inventory.json",
                        "csv_contains_edit": True,
                        "final_status": "final_ready",
                        "screenshot_path": (
                            screenshot_path.as_posix()
                            if screenshot_path is not None
                            else None
                        ),
                        "issues": [],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_customer_validation_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact_dir = path.parent / "out"
    screenshot_dir = path.parent / "screenshots"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "run_intake.json").write_text(
        json.dumps({"workflow": "client-intake"}),
        encoding="utf-8",
    )
    (artifact_dir / "review_payload.json").write_text(
        json.dumps({"items": [{"id": "item-1"}]}),
        encoding="utf-8",
    )
    (artifact_dir / "ui_decisions.json").write_text(
        json.dumps({"decisions": [{"item_id": "item-1", "action": "accept"}]}),
        encoding="utf-8",
    )
    (artifact_dir / "applied_decisions.json").write_text(
        json.dumps({"applied": True}),
        encoding="utf-8",
    )
    (artifact_dir / "final_artifacts.json").write_text(
        json.dumps({"status": "final-ready"}),
        encoding="utf-8",
    )
    (artifact_dir / "native_readback.md").write_text("readback", encoding="utf-8")
    (screenshot_dir / "client-intake.png").write_text("screenshot", encoding="utf-8")
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "cases": [
                    {
                        "case_id": "case-client-intake-001",
                        "plugin": "client-intake",
                        "scenario_name": "Representative customer case",
                        "input_path_or_case_id": "anonymized/client-intake/001",
                        "language": "it",
                        "reviewer": "Reviewer Name",
                        "validated_at": "2026-06-08T10:00:00Z",
                        "commands": ["ran workflow", "opened review UI"],
                        "artifact_paths": {
                            "run_intake": "out/run_intake.json",
                            "review_payload": "out/review_payload.json",
                            "ui_decisions": "out/ui_decisions.json",
                            "applied_decisions": "out/applied_decisions.json",
                            "final_artifacts": "out/final_artifacts.json",
                            "screenshot_paths": ["screenshots/client-intake.png"],
                            "native_output_readback": "out/native_readback.md",
                        },
                        "decision_summary": {"accepted": 1},
                        "ux_verdict": "usable",
                        "ux_checks": {
                            "queue_clear": True,
                            "evidence_comparison_clear": True,
                            "decision_controls_complete": True,
                            "edit_flow_usable": True,
                            "artifact_handoff_clear": True,
                            "no_blocking_issues": True,
                        },
                        "reviewer_notes": "Queue, evidence, decisions, edit flow, and artifact handoff were usable.",
                        "status": "pass",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_build_evidence_bundle_writes_core_artifacts(tmp_path: Path) -> None:
    bundle = load_bundle_module()
    output_dir = tmp_path / "evidence"

    manifest = bundle.build_evidence_bundle(root=ROOT, output_dir=output_dir)

    manifest_path = output_dir / "bundle_manifest.json"
    readiness_path = output_dir / "readiness.json"
    readme_path = output_dir / "README.md"
    template_path = output_dir / "customer_validation_template.json"
    gallery_path = output_dir / "browser_writeback_gallery.html"
    gallery_json_path = output_dir / "browser_writeback_gallery.json"
    plan_path = output_dir / "customer_validation_plan.md"
    plan_json_path = output_dir / "customer_validation_plan.json"
    checklist_path = output_dir / "customer_validation_checklist.html"
    completion_path = output_dir / "completion_assessment.json"
    dashboard_path = output_dir / "adoption_review_dashboard.html"
    readiness_payload = json.loads(readiness_path.read_text(encoding="utf-8"))
    template_payload = json.loads(template_path.read_text(encoding="utf-8"))
    plan_payload = json.loads(plan_json_path.read_text(encoding="utf-8"))
    completion_payload = json.loads(completion_path.read_text(encoding="utf-8"))

    assert manifest_path.exists()
    assert readme_path.exists()
    assert gallery_path.exists()
    assert gallery_json_path.exists()
    assert plan_path.exists()
    assert plan_json_path.exists()
    assert checklist_path.exists()
    assert completion_path.exists()
    assert dashboard_path.exists()
    assert readiness_payload["status"] == "ok"
    assert manifest["validation_tiers"]["interaction_contracts"] == "covered"
    assert (
        manifest["validation_tiers"]["real_customer_folder_validation"]
        == "not_assessed"
    )
    assert manifest["commands"]["generate_browser_writeback_report"][:3] == [
        ".venv/bin/python",
        "scripts/audit_local_review_workbench_writeback.py",
        "--plugin",
    ]
    assert manifest["commands"]["build_evidence_bundle"][:3] == [
        ".venv/bin/python",
        "scripts/build_openai_pattern_adoption_evidence.py",
        "--output-dir",
    ]
    assert [case["plugin"] for case in template_payload["cases"]] == [
        "audit-reconciliation",
        "check-entries",
        "client-intake",
        "concordato-plan-review",
        "deep-research-validator",
        "journal-bank-reconciliation",
        "journal-sampling",
        "prompt-optimizer",
        "report-builder",
    ]
    assert "Browser write-back evidence is fixture/mechanism evidence" in (
        readme_path.read_text(encoding="utf-8")
    )
    assert "## Commands" in readme_path.read_text(encoding="utf-8")
    plan_text = plan_path.read_text(encoding="utf-8")
    assert "case-audit-reconciliation-001" in plan_text
    assert "--preflight-customer-validation-case" in plan_text
    assert "--record-customer-validation-case" in plan_text
    assert "--infer-case-metadata-from-run" in plan_text
    assert "--require-customer-validation" in plan_text
    checklist_text = checklist_path.read_text(encoding="utf-8")
    assert "Real Customer Validation Checklist" in checklist_text
    assert "case-audit-reconciliation-001" in checklist_text
    assert "--preflight-customer-validation-case" in checklist_text
    assert "--record-customer-validation-case" in checklist_text
    assert "--infer-case-metadata-from-run" in checklist_text
    assert "needs_real_customer_case" in checklist_text
    dashboard_text = dashboard_path.read_text(encoding="utf-8")
    assert "OpenAI-Pattern Adoption Dashboard" in dashboard_text
    assert "Browser Write-Back Gallery" in dashboard_text
    assert "Customer Validation Checklist" in dashboard_text
    assert "Plugin Adoption Matrix" in dashboard_text
    assert "audit-reconciliation" in dashboard_text
    assert "tests/plugins/test_audit_reconciliation_plugin.py" in dashboard_text
    assert "Adopted OpenAI Lessons" in dashboard_text
    assert "ask_material_questions_only" in dashboard_text
    assert "Do not ask the user to type continue" in dashboard_text
    assert "Rejected OpenAI Patterns" in dashboard_text
    assert "Remote warehouse execution as the default" in dashboard_text
    assert "Local deterministic execution by default" in dashboard_text
    assert "validate_real_customer_user_experience" in dashboard_text
    assert "Record passing real customer-validation cases" in dashboard_text
    assert plan_payload["schema_version"] == "1.0"
    assert plan_payload["status"] == "not_assessed"
    assert plan_payload["metadata_inference"]["inferable_fields"] == [
        "plugin",
        "scenario_name",
        "language",
    ]
    assert "reviewer_notes" in plan_payload["metadata_inference"]["still_required"]
    assert plan_payload["cases"][0]["status"] == "needs_real_customer_case"
    assert plan_payload["cases"][0]["preflight_command"][:3] == [
        ".venv/bin/python",
        "scripts/audit_openai_pattern_adoption_readiness.py",
        "--preflight-customer-validation-case",
    ]
    assert plan_payload["cases"][0]["record_command"][:3] == [
        ".venv/bin/python",
        "scripts/audit_openai_pattern_adoption_readiness.py",
        "--record-customer-validation-case",
    ]
    assert completion_payload["overall_status"] == "incomplete"
    requirements = {
        item["requirement_id"]: item["status"]
        for item in completion_payload["requirements"]
    }
    assert requirements["extract_openai_best_practices"] == "covered"
    assert requirements["preserve_local_deterministic_model"] == "covered"
    assert requirements["validate_real_customer_user_experience"] == "not_assessed"


def test_build_evidence_bundle_uses_existing_browser_report(tmp_path: Path) -> None:
    bundle = load_bundle_module()
    browser_report = tmp_path / "browser.json"
    screenshot = tmp_path / "shots" / "client-intake.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    _write_browser_writeback_report(browser_report, screenshot_path=screenshot)
    output_dir = tmp_path / "evidence"

    manifest = bundle.build_evidence_bundle(
        root=ROOT,
        output_dir=output_dir,
        browser_writeback_report_path=browser_report,
        expected_customer_plugins=("client-intake",),
        require_browser_writeback=True,
    )
    readiness_payload = json.loads(
        Path(manifest["artifacts"]["readiness_json"]).read_text(encoding="utf-8")
    )
    tiers = {
        item["tier"]: item["status"] for item in readiness_payload["validation_tiers"]
    }

    assert tiers["browser_writeback_mechanism"] == "covered"
    assert readiness_payload["browser_writeback"]["covered_plugins"] == [
        "client-intake"
    ]
    assert "browser_writeback_gallery" in manifest["artifacts"]
    dashboard_html = Path(manifest["artifacts"]["adoption_review_dashboard"])
    gallery_html = Path(manifest["artifacts"]["browser_writeback_gallery"])
    gallery_payload = json.loads(
        Path(manifest["artifacts"]["browser_writeback_gallery_json"]).read_text(
            encoding="utf-8"
        )
    )
    copied_screenshot = (
        output_dir / "browser_writeback_gallery_assets" / "client-intake.png"
    )

    assert gallery_html.exists()
    assert dashboard_html.exists()
    assert copied_screenshot.exists()
    assert "client-intake" in gallery_html.read_text(encoding="utf-8")
    assert "browser_writeback_mechanism</span>" in dashboard_html.read_text(
        encoding="utf-8"
    )
    assert "client-intake" in dashboard_html.read_text(encoding="utf-8")
    assert gallery_payload["reports"][0]["screenshot_asset"] == (
        "browser_writeback_gallery_assets/client-intake.png"
    )


def test_build_evidence_bundle_accepts_real_customer_manifest(
    tmp_path: Path,
) -> None:
    bundle = load_bundle_module()
    manifest_path = tmp_path / "customer_validation.json"
    _write_customer_validation_manifest(manifest_path)

    manifest = bundle.build_evidence_bundle(
        root=ROOT,
        output_dir=tmp_path / "evidence",
        customer_manifest_path=manifest_path,
        expected_customer_plugins=("client-intake",),
        require_customer_validation=True,
        verify_customer_artifact_paths=True,
    )
    readiness_payload = json.loads(
        Path(manifest["artifacts"]["readiness_json"]).read_text(encoding="utf-8")
    )
    plan_payload = json.loads(
        Path(manifest["artifacts"]["customer_validation_plan_json"]).read_text(
            encoding="utf-8"
        )
    )
    completion_payload = json.loads(
        Path(manifest["artifacts"]["completion_assessment_json"]).read_text(
            encoding="utf-8"
        )
    )
    tiers = {
        item["tier"]: item["status"] for item in readiness_payload["validation_tiers"]
    }

    assert manifest["artifacts"]["customer_validation_manifest"] == str(manifest_path)
    assert str(manifest_path) in manifest["commands"]["strict_customer_validation_gate"]
    checklist_text = Path(
        manifest["artifacts"]["customer_validation_checklist"]
    ).read_text(encoding="utf-8")
    dashboard_text = Path(manifest["artifacts"]["adoption_review_dashboard"]).read_text(
        encoding="utf-8"
    )
    assert "case-client-intake-001" in checklist_text
    assert "covered" in checklist_text
    assert "complete_candidate" in dashboard_text
    assert tiers["real_customer_folder_validation"] == "covered"
    assert readiness_payload["customer_validation"]["covered_plugins"] == [
        "client-intake"
    ]
    assert plan_payload["cases"][0]["status"] == "covered"
    requirements = {
        item["requirement_id"]: item["status"]
        for item in completion_payload["requirements"]
    }
    assert requirements["validate_real_customer_user_experience"] == "covered"


def test_main_writes_manifest_path(tmp_path: Path, capsys) -> None:
    bundle = load_bundle_module()
    output_dir = tmp_path / "evidence"

    exit_code = bundle.main(
        [
            "--output-dir",
            str(output_dir),
            "--fail-on",
            "medium",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Wrote OpenAI-pattern adoption evidence" in output
    assert (output_dir / "bundle_manifest.json").exists()


def test_main_require_complete_objective_fails_for_partial_bundle(
    tmp_path: Path,
    capsys,
) -> None:
    bundle = load_bundle_module()
    output_dir = tmp_path / "evidence"

    exit_code = bundle.main(
        [
            "--output-dir",
            str(output_dir),
            "--require-complete-objective",
            "--fail-on",
            "medium",
        ]
    )
    captured = capsys.readouterr()
    completion_payload = json.loads(
        (output_dir / "completion_assessment.json").read_text(encoding="utf-8")
    )

    assert exit_code == 1
    assert "not complete" in captured.err
    assert completion_payload["overall_status"] == "incomplete"


def test_main_require_complete_objective_passes_with_complete_fixture(
    tmp_path: Path,
    capsys,
) -> None:
    bundle = load_bundle_module()
    output_dir = tmp_path / "evidence"
    browser_report = tmp_path / "browser.json"
    customer_manifest = tmp_path / "customer_validation.json"
    _write_browser_writeback_report(browser_report)
    _write_customer_validation_manifest(customer_manifest)

    exit_code = bundle.main(
        [
            "--output-dir",
            str(output_dir),
            "--browser-writeback-report",
            str(browser_report),
            "--customer-validation-manifest",
            str(customer_manifest),
            "--expected-customer-plugin",
            "client-intake",
            "--require-browser-writeback",
            "--require-customer-validation",
            "--verify-customer-validation-artifacts",
            "--require-complete-objective",
            "--fail-on",
            "medium",
        ]
    )
    captured = capsys.readouterr()
    completion_payload = json.loads(
        (output_dir / "completion_assessment.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert "Wrote OpenAI-pattern adoption evidence" in captured.out
    assert completion_payload["overall_status"] == "complete_candidate"
