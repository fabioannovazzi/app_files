from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "audit_openai_pattern_adoption_readiness.py"
REQUIRED_UX_CHECKS = (
    "artifact_handoff_clear",
    "decision_controls_complete",
    "edit_flow_usable",
    "evidence_comparison_clear",
    "no_blocking_issues",
    "queue_clear",
)


spec = importlib.util.spec_from_file_location(
    "audit_openai_pattern_adoption_readiness", SCRIPT_PATH
)
assert spec is not None
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


def _write_plugin(root: Path, name: str, skill_text: str) -> None:
    plugin_dir = root / "plugins" / name
    skill_dir = plugin_dir / "skills" / name
    manifest_dir = plugin_dir / ".codex-plugin"
    skill_dir.mkdir(parents=True)
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": name, "version": "0.1.0"}) + "\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(skill_text, encoding="utf-8")


def _write_good_plugin(root: Path) -> None:
    _write_plugin(
        root,
        "client-file-preparation",
        (
            "Use local deterministic scripts. Ask only for external, destructive, "
            "approval-sensitive, or material choices."
        ),
    )


def _write_customer_manifest(
    path: Path,
    *,
    artifact_paths: dict[str, object] | None = None,
    status: str = "pass",
    ux_verdict: str = "usable",
    ux_checks: dict[str, bool] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "cases": [
                    {
                        "case_id": "case-client-file-preparation-001",
                        "plugin": "client-file-preparation",
                        "scenario_name": "Italian customer folder with missing docs",
                        "input_path_or_case_id": "anonymized/client-file-preparation/001",
                        "language": "it",
                        "reviewer": "QA",
                        "validated_at": "2026-06-07T10:00:00Z",
                        "commands": [
                            "run client-file-preparation fixture",
                            "open local review surface",
                        ],
                        "artifact_paths": (
                            artifact_paths
                            if artifact_paths is not None
                            else {
                                "run_intake": "out/run_intake.json",
                                "review_payload": "out/review_payload.json",
                                "ui_decisions": "out/ui_decisions.json",
                                "applied_decisions": "out/applied_decisions.json",
                                "final_artifacts": "out/final_artifacts.json",
                                "screenshot_paths": [
                                    "shots/client-file-preparation.png"
                                ],
                                "native_output_readback": "out/readback.md",
                            }
                        ),
                        "decision_summary": {
                            "accepted": 2,
                            "requested_more_documents": 1,
                        },
                        "ux_verdict": ux_verdict,
                        "ux_checks": (
                            ux_checks
                            if ux_checks is not None
                            else {name: True for name in REQUIRED_UX_CHECKS}
                        ),
                        "reviewer_notes": "Reviewer completed queue, evidence, decisions, and handoff.",
                        "status": status,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_manifest_artifact_files(
    manifest: Path, artifact_paths: dict[str, object]
) -> None:
    for name, value in artifact_paths.items():
        if isinstance(value, str) and value != "not_applicable":
            path = manifest.parent / value
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == ".json":
                payload: dict[str, object] = {"artifact": name}
                if name == "final_artifacts":
                    payload = {"status": "final-ready"}
                if name == "ui_decisions":
                    payload = {"decisions": [{"action": "accept"}]}
                if name == "applied_decisions":
                    payload = {"applied": True}
                path.write_text(json.dumps(payload), encoding="utf-8")
            else:
                path.write_text("artifact", encoding="utf-8")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    path = manifest.parent / item
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("screenshot", encoding="utf-8")


def _write_browser_writeback_report(
    path: Path,
    *,
    plugins: tuple[str, ...] = ("client-file-preparation",),
    screenshot_dir: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    reports = []
    for plugin in plugins:
        screenshot_path = None
        if screenshot_dir is not None:
            screenshot = screenshot_dir / f"{plugin}.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            screenshot.write_text("screenshot", encoding="utf-8")
            screenshot_path = screenshot.as_posix()
        reports.append(
            {
                "plugin": plugin,
                "status": "ok",
                "row_count": 1,
                "decision_control_count": 4,
                "target_artifact": "review.json",
                "csv_contains_edit": True,
                "final_status": "final_ready",
                "screenshot_path": screenshot_path,
                "issues": [],
            }
        )
    path.write_text(
        json.dumps(
            {
                "summary": {
                    "plugin_count": len(reports),
                    "status_counts": {"ok": len(reports)},
                    "issue_counts": {},
                },
                "reports": reports,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_validation_run(run_output_dir: Path) -> None:
    run_output_dir.mkdir(parents=True, exist_ok=True)
    (run_output_dir / "run_intake.json").write_text(
        json.dumps(
            {
                "workflow": "client-file-preparation",
                "language": "it",
                "inferred_task": "first_customer_folder_intake",
            }
        ),
        encoding="utf-8",
    )
    (run_output_dir / "review_payload.json").write_text(
        json.dumps(
            {
                "plugin": "client-file-preparation",
                "workflow": "client-file-preparation",
                "items": [{"id": "item-1"}],
            }
        ),
        encoding="utf-8",
    )
    (run_output_dir / "ui_decisions.json").write_text(
        json.dumps(
            {
                "decisions": [
                    {"item_id": "item-1", "action": "accept"},
                    {"item_id": "item-2", "action": "edit"},
                    {"item_id": "item-3", "action": "request_more_documents"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_output_dir / "applied_decisions.json").write_text(
        json.dumps({"applied": True}),
        encoding="utf-8",
    )
    (run_output_dir / "final_artifacts.json").write_text(
        json.dumps({"status": "final-ready"}),
        encoding="utf-8",
    )
    (run_output_dir / "readback.md").write_text("readback", encoding="utf-8")


def _write_validation_run_with_pending_final_artifacts(run_output_dir: Path) -> None:
    _write_validation_run(run_output_dir)
    (run_output_dir / "final_artifacts.json").write_text(
        json.dumps({"status": "written_pending_review"}),
        encoding="utf-8",
    )


def _ux_check_cli_args() -> list[str]:
    args: list[str] = []
    for check in REQUIRED_UX_CHECKS:
        args.extend(["--ux-check", check])
    return args


def _customer_validation_case_cli_args(
    *,
    manifest: Path,
    run_output_dir: Path,
    screenshot: Path,
    mode_flag: str,
) -> list[str]:
    return [
        "--customer-validation-manifest",
        str(manifest),
        mode_flag,
        "--case-id",
        "case-client-file-preparation-001",
        "--plugin",
        "client-file-preparation",
        "--scenario-name",
        "Italian client file preparation folder",
        "--input-path-or-case-id",
        "anonymized/client-file-preparation/001",
        "--language",
        "it",
        "--reviewer",
        "QA",
        "--run-output-dir",
        str(run_output_dir),
        "--screenshot-path",
        str(screenshot),
        "--native-output-readback",
        str(run_output_dir / "readback.md"),
        "--validation-status",
        "pass",
        "--ux-verdict",
        "usable",
        *_ux_check_cli_args(),
        "--reviewer-notes",
        "Reviewer completed queue, evidence comparison, decisions, and handoff.",
        "--validated-at",
        "2026-06-07T10:00:00Z",
        "--validation-command",
        "run local client-file-preparation fixture",
        "--validation-command",
        "save and apply review decisions",
    ]


def test_repo_openai_pattern_adoption_readiness_is_ok() -> None:
    report = audit.audit_adoption_readiness(ROOT)
    tiers = {item["tier"]: item for item in report.validation_tiers}
    next_action_ids = {item["id"] for item in report.next_actions}

    severe = [
        issue
        for issue in report.issues
        if issue.severity in {"blocker", "high", "medium"}
    ]

    assert report.status == "ok"
    assert severe == []
    assert report.demo_summary["adapter_count"] == 10
    assert report.contract_summary["plugin_count"] == 10
    assert all(item["scenario_files"] for item in report.workbench_evidence)
    assert tiers["interaction_contracts"]["status"] == "covered"
    assert tiers["demo_ui_contracts"]["status"] == "covered"
    assert tiers["workflow_fixture_contracts"]["status"] == "covered"
    assert tiers["browser_writeback_mechanism"]["status"] == "not_assessed"
    assert tiers["real_customer_folder_validation"]["status"] == "not_assessed"
    assert {
        "run_browser_writeback_mechanism_audit",
        "collect_representative_customer_cases",
        "run_local_review_surface",
        "validate_final_artifact_semantics",
        "record_customer_validation_manifest",
    } <= next_action_ids


def test_readiness_markdown_names_patterns_and_scenario_tests(capsys) -> None:
    exit_code = audit.main(["--format", "markdown", "--fail-on", "medium"])

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "# OpenAI Pattern Adoption Readiness" in output
    assert "## Pattern Coverage" in output
    assert "## Playbook Traceability" in output
    assert "## Rejected Patterns" in output
    assert "## Validation Tiers" in output
    assert "## Browser Write-Back" in output
    assert "## Next Actions" in output
    assert "ask_material_questions_only" in output
    assert "Decision Capture Is The Interaction Contract" in output
    assert "Asking the user to type `continue`" in output
    assert "continue_theater" in output
    assert "real_customer_folder_validation" in output
    assert "run_local_review_surface" in output
    assert "ui_decisions.json" in output
    assert "## Workbench Evidence" in output
    assert "Workflow contract plugins audited: 10" in output


def test_readiness_json_includes_machine_readable_limits(capsys) -> None:
    exit_code = audit.main(["--format", "json", "--fail-on", "medium"])

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["summary"]["contract_coverage"]["plugin_count"] == 10
    assert {item["section"] for item in payload["playbook_section_coverage"]} >= {
        "Ask Only When The Answer Changes The Work",
        "Decision Capture Is The Interaction Contract",
        "Visible Handoff Beats Hidden JSON",
    }
    assert any(
        "local_browser_writeback" in item["pattern_ids"]
        for item in payload["playbook_section_coverage"]
    )
    assert any(
        item["pattern_id"] == "continue_theater_checkpoints"
        and "continue_theater" in item["guardrail_signals"]
        for item in payload["rejected_patterns"]
    )
    assert {item["tier"]: item["status"] for item in payload["validation_tiers"]}[
        "browser_writeback_mechanism"
    ] == "not_assessed"
    assert {item["tier"]: item["status"] for item in payload["validation_tiers"]}[
        "real_customer_folder_validation"
    ] == "not_assessed"
    assert {item["id"] for item in payload["next_actions"]} >= {
        "run_browser_writeback_mechanism_audit",
        "record_customer_validation_manifest",
    }
    assert payload["browser_writeback"]["status"] == "not_assessed"
    assert payload["limits"]


def test_readiness_main_writes_report_path(tmp_path: Path, capsys) -> None:
    report_path = tmp_path / "reports" / "openai-readiness.json"

    exit_code = audit.main(
        [
            "--format",
            "json",
            "--report-path",
            str(report_path),
            "--fail-on",
            "medium",
        ]
    )
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert file_payload == stdout_payload
    assert file_payload["status"] == "ok"
    assert file_payload["validation_tiers"]


def test_browser_writeback_report_covers_mechanism_tier(tmp_path: Path) -> None:
    _write_good_plugin(tmp_path)
    report_path = tmp_path / "browser-writeback.json"
    _write_browser_writeback_report(
        report_path,
        plugins=("client-file-preparation",),
        screenshot_dir=tmp_path / "screenshots",
    )

    report = audit.audit_adoption_readiness(
        tmp_path,
        browser_writeback_report_path=report_path,
        expected_customer_plugins=("client-file-preparation",),
        require_browser_writeback=True,
        verify_browser_writeback_screenshots=True,
    )
    tiers = {item["tier"]: item for item in report.validation_tiers}

    assert report.status == "ok"
    assert report.browser_writeback["status"] == "covered"
    assert report.browser_writeback["covered_plugins"] == ["client-file-preparation"]
    assert tiers["browser_writeback_mechanism"]["status"] == "covered"
    assert "run_browser_writeback_mechanism_audit" not in {
        item["id"] for item in report.next_actions
    }


def test_require_browser_writeback_fails_when_report_is_missing(tmp_path: Path) -> None:
    _write_good_plugin(tmp_path)

    report = audit.audit_adoption_readiness(
        tmp_path,
        expected_customer_plugins=("client-file-preparation",),
        require_browser_writeback=True,
    )
    issue_codes = {issue.code for issue in report.issues}
    tiers = {item["tier"]: item for item in report.validation_tiers}

    assert report.status == "partial"
    assert tiers["browser_writeback_mechanism"]["status"] == "not_assessed"
    assert "browser_writeback_required_not_covered" in issue_codes


def test_browser_writeback_report_requires_expected_plugin_coverage(
    tmp_path: Path,
) -> None:
    _write_good_plugin(tmp_path)
    report_path = tmp_path / "browser-writeback.json"
    _write_browser_writeback_report(report_path, plugins=("client-file-preparation",))

    report = audit.audit_adoption_readiness(
        tmp_path,
        browser_writeback_report_path=report_path,
        expected_customer_plugins=("client-file-preparation", "report-builder"),
    )
    issue_codes = {issue.code for issue in report.issues}

    assert report.status == "partial"
    assert report.browser_writeback["status"] == "partial"
    assert report.browser_writeback["covered_plugins"] == ["client-file-preparation"]
    assert report.browser_writeback["missing_expected_plugins"] == ["report-builder"]
    assert "browser_writeback_expected_plugins_missing" in issue_codes


def test_write_customer_validation_template_uses_expected_plugins(
    tmp_path: Path,
    capsys,
) -> None:
    template_path = tmp_path / "templates" / "customer_validation.json"

    exit_code = audit.main(
        [
            "--expected-customer-plugin",
            "report-builder",
            "--expected-customer-plugin",
            "client-file-preparation",
            "--write-customer-validation-template",
            str(template_path),
        ]
    )

    output = capsys.readouterr().out
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "Wrote customer validation template for 2 plugin(s)" in output
    assert [case["plugin"] for case in payload["cases"]] == [
        "client-file-preparation",
        "report-builder",
    ]
    assert payload["cases"][0]["status"] == "partial"
    assert payload["cases"][0]["artifact_paths"]["ui_decisions"].endswith(
        "ui_decisions.json"
    )
    assert payload["cases"][0]["decision_summary"]["edited"] == 0
    assert payload["cases"][0]["ux_verdict"] == "usable_with_issues"
    assert all(value is False for value in payload["cases"][0]["ux_checks"].values())


def test_write_customer_validation_template_defaults_to_workbench_plugins(
    tmp_path: Path,
) -> None:
    template_path = tmp_path / "customer_validation.json"

    exit_code = audit.main(
        [
            "--root",
            str(ROOT),
            "--write-customer-validation-template",
            str(template_path),
        ]
    )

    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert [case["plugin"] for case in payload["cases"]] == [
        "audit-reconciliation",
        "check-entries",
        "client-file-preparation",
        "concordato-plan-review",
        "deep-research-validator",
        "journal-bank-reconciliation",
        "journal-sampling",
        "new-client",
        "prompt-optimizer",
        "report-builder",
    ]


def test_committed_customer_validation_example_covers_default_plugins() -> None:
    example_path = (
        ROOT / "docs" / "openai_pattern_customer_validation_manifest.example.json"
    )
    payload = json.loads(example_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    assert [case["plugin"] for case in payload["cases"]] == [
        "audit-reconciliation",
        "check-entries",
        "client-file-preparation",
        "concordato-plan-review",
        "deep-research-validator",
        "journal-bank-reconciliation",
        "journal-sampling",
        "new-client",
        "prompt-optimizer",
        "report-builder",
    ]
    assert {case["status"] for case in payload["cases"]} == {"partial"}
    assert all(
        case["artifact_paths"]["ui_decisions"].endswith("ui_decisions.json")
        for case in payload["cases"]
    )


def test_customer_validation_runbook_names_required_evidence_and_gate() -> None:
    runbook = (
        ROOT / "docs" / "openai_pattern_customer_validation_runbook.md"
    ).read_text(encoding="utf-8")

    for required_text in (
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
        "native_output_readback",
        "--record-customer-validation-case",
        "--require-customer-validation",
        "--verify-customer-validation-artifacts",
        "--fail-on medium",
        "customer_validation_required_not_covered",
    ):
        assert required_text in runbook

    for plugin in (
        "audit-reconciliation",
        "check-entries",
        "client-file-preparation",
        "concordato-plan-review",
        "deep-research-validator",
        "journal-bank-reconciliation",
        "journal-sampling",
        "new-client",
        "prompt-optimizer",
        "report-builder",
    ):
        assert plugin in runbook


def test_require_customer_validation_fails_when_real_cases_are_not_covered(
    capsys,
) -> None:
    exit_code = audit.main(
        [
            "--format",
            "json",
            "--fail-on",
            "medium",
            "--require-customer-validation",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["customer_validation"]["status"] == "not_assessed"
    assert "customer_validation_required_not_covered" in {
        issue["code"] for issue in payload["issues"]
    }


def test_customer_validation_manifest_can_cover_real_customer_tier(
    tmp_path: Path,
) -> None:
    _write_good_plugin(tmp_path)
    manifest = tmp_path / "customer_validation.json"
    _write_customer_manifest(manifest)

    report = audit.audit_adoption_readiness(
        tmp_path,
        customer_manifest_path=manifest,
        expected_customer_plugins=("client-file-preparation",),
        require_customer_validation=True,
    )
    tiers = {item["tier"]: item for item in report.validation_tiers}

    assert report.status == "ok"
    assert report.customer_validation["status"] == "covered"
    assert report.customer_validation["case_count"] == 1
    assert report.customer_validation["covered_plugins"] == ["client-file-preparation"]
    assert tiers["real_customer_folder_validation"]["status"] == "covered"
    assert report.next_actions == []


def test_customer_validation_manifest_requires_usable_ux_verdict(
    tmp_path: Path,
) -> None:
    _write_good_plugin(tmp_path)
    manifest = tmp_path / "customer_validation.json"
    _write_customer_manifest(manifest, ux_verdict="usable_with_issues")

    report = audit.audit_adoption_readiness(
        tmp_path,
        customer_manifest_path=manifest,
        expected_customer_plugins=("client-file-preparation",),
        require_customer_validation=True,
    )
    issue_codes = {issue.code for issue in report.issues}

    assert report.status == "partial"
    assert report.customer_validation["status"] == "partial"
    assert report.customer_validation["covered_plugins"] == []
    assert "customer_validation_ux_not_usable" in issue_codes
    assert "customer_validation_required_not_covered" in issue_codes


def test_customer_validation_manifest_requires_complete_ux_checks(
    tmp_path: Path,
) -> None:
    _write_good_plugin(tmp_path)
    manifest = tmp_path / "customer_validation.json"
    ux_checks = {name: True for name in REQUIRED_UX_CHECKS}
    ux_checks["edit_flow_usable"] = False
    _write_customer_manifest(manifest, ux_checks=ux_checks)

    report = audit.audit_adoption_readiness(
        tmp_path,
        customer_manifest_path=manifest,
        expected_customer_plugins=("client-file-preparation",),
        require_customer_validation=True,
    )
    issue_codes = {issue.code for issue in report.issues}

    assert report.status == "partial"
    assert report.customer_validation["covered_plugins"] == []
    assert "customer_validation_ux_checks_incomplete" in issue_codes
    assert "customer_validation_required_not_covered" in issue_codes


def test_customer_validation_artifact_verification_flags_missing_files(
    tmp_path: Path,
) -> None:
    _write_good_plugin(tmp_path)
    manifest = tmp_path / "customer_validation.json"
    _write_customer_manifest(manifest)

    report = audit.audit_adoption_readiness(
        tmp_path,
        customer_manifest_path=manifest,
        expected_customer_plugins=("client-file-preparation",),
        require_customer_validation=True,
        verify_customer_artifact_paths=True,
    )
    issue_codes = {issue.code for issue in report.issues}

    assert report.status == "partial"
    assert report.customer_validation["status"] == "partial"
    assert report.customer_validation["artifact_path_verification"] is True
    assert report.customer_validation["covered_plugins"] == []
    assert "customer_validation_artifact_files_missing" in issue_codes
    assert "customer_validation_required_not_covered" in issue_codes


def test_customer_validation_artifact_verification_accepts_existing_files(
    tmp_path: Path,
) -> None:
    _write_good_plugin(tmp_path)
    manifest = tmp_path / "customer_validation.json"
    artifact_paths = {
        "run_intake": "out/run_intake.json",
        "review_payload": "out/review_payload.json",
        "ui_decisions": "out/ui_decisions.json",
        "applied_decisions": "out/applied_decisions.json",
        "final_artifacts": "out/final_artifacts.json",
        "screenshot_paths": ["shots/client-file-preparation.png"],
        "native_output_readback": "out/readback.md",
    }
    _write_customer_manifest(manifest, artifact_paths=artifact_paths)
    _write_manifest_artifact_files(manifest, artifact_paths)

    report = audit.audit_adoption_readiness(
        tmp_path,
        customer_manifest_path=manifest,
        expected_customer_plugins=("client-file-preparation",),
        require_customer_validation=True,
        verify_customer_artifact_paths=True,
    )

    assert report.status == "ok"
    assert report.customer_validation["status"] == "covered"
    assert report.customer_validation["artifact_path_verification"] is True
    assert report.customer_validation["verified_artifact_case_count"] == 1
    assert report.customer_validation["covered_plugins"] == ["client-file-preparation"]


def test_customer_validation_artifact_verification_rejects_pending_final_artifacts(
    tmp_path: Path,
) -> None:
    _write_good_plugin(tmp_path)
    manifest = tmp_path / "customer_validation.json"
    artifact_paths = {
        "run_intake": "out/run_intake.json",
        "review_payload": "out/review_payload.json",
        "ui_decisions": "out/ui_decisions.json",
        "applied_decisions": "out/applied_decisions.json",
        "final_artifacts": "out/final_artifacts.json",
        "screenshot_paths": ["shots/client-file-preparation.png"],
        "native_output_readback": "out/readback.md",
    }
    _write_customer_manifest(manifest, artifact_paths=artifact_paths)
    _write_manifest_artifact_files(manifest, artifact_paths)
    (manifest.parent / "out" / "final_artifacts.json").write_text(
        json.dumps({"status": "written_pending_review"}),
        encoding="utf-8",
    )

    report = audit.audit_adoption_readiness(
        tmp_path,
        customer_manifest_path=manifest,
        expected_customer_plugins=("client-file-preparation",),
        require_customer_validation=True,
        verify_customer_artifact_paths=True,
    )
    issue_codes = {issue.code for issue in report.issues}

    assert report.status == "partial"
    assert report.customer_validation["covered_plugins"] == []
    assert "customer_validation_artifact_contents_invalid" in issue_codes
    assert "customer_validation_required_not_covered" in issue_codes


def test_record_customer_validation_case_from_run_output_passes_strict_gate(
    tmp_path: Path,
    capsys,
) -> None:
    _write_good_plugin(tmp_path)
    manifest = tmp_path / "docs" / "customer_validation.json"
    run_output_dir = manifest.parent / "runs" / "case-001"
    screenshot = manifest.parent / "shots" / "case-001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_text("screenshot", encoding="utf-8")
    _write_validation_run(run_output_dir)

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            "--customer-validation-manifest",
            str(manifest),
            "--record-customer-validation-case",
            "--case-id",
            "case-client-file-preparation-001",
            "--plugin",
            "client-file-preparation",
            "--scenario-name",
            "Italian client file preparation folder",
            "--input-path-or-case-id",
            "anonymized/client-file-preparation/001",
            "--language",
            "it",
            "--reviewer",
            "QA",
            "--run-output-dir",
            str(run_output_dir),
            "--screenshot-path",
            str(screenshot),
            "--native-output-readback",
            str(run_output_dir / "readback.md"),
            "--validation-status",
            "pass",
            "--ux-verdict",
            "usable",
            *_ux_check_cli_args(),
            "--reviewer-notes",
            "Reviewer completed queue, evidence comparison, decisions, and handoff.",
            "--validated-at",
            "2026-06-07T10:00:00Z",
            "--validation-command",
            "run local client-file-preparation fixture",
            "--validation-command",
            "save and apply review decisions",
        ]
    )

    output = capsys.readouterr().out
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    case = payload["cases"][0]
    report = audit.audit_adoption_readiness(
        tmp_path,
        customer_manifest_path=manifest,
        expected_customer_plugins=("client-file-preparation",),
        require_customer_validation=True,
        verify_customer_artifact_paths=True,
    )

    assert exit_code == 0
    assert (
        "Recorded customer validation case case-client-file-preparation-001" in output
    )
    assert case["artifact_paths"]["run_intake"] == "runs/case-001/run_intake.json"
    assert case["artifact_paths"]["screenshot_paths"] == ["shots/case-001.png"]
    assert case["decision_summary"]["accepted"] == 1
    assert case["decision_summary"]["edited"] == 1
    assert case["decision_summary"]["requested_more_documents"] == 1
    assert case["ux_verdict"] == "usable"
    assert "evidence comparison" in case["reviewer_notes"]
    assert report.status == "ok"
    assert report.customer_validation["status"] == "covered"


def test_preflight_customer_validation_case_does_not_write_manifest(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "manifest-store" / "customer_validation.json"
    run_output_dir = tmp_path / "runs" / "case-001"
    screenshot = tmp_path / "shots" / "case-001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_text("screenshot", encoding="utf-8")
    _write_validation_run(run_output_dir)

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            *_customer_validation_case_cli_args(
                manifest=manifest,
                run_output_dir=run_output_dir,
                screenshot=screenshot,
                mode_flag="--preflight-customer-validation-case",
            ),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Customer validation case preflight passed" in output
    assert "manifest not written" in output
    assert not manifest.exists()
    assert not manifest.parent.exists()


def test_preflight_customer_validation_case_refuses_invalid_existing_manifest(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "docs" / "customer_validation.json"
    run_output_dir = tmp_path / "runs" / "case-001"
    screenshot = tmp_path / "shots" / "case-001.png"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('{"schema_version": "0.9", "cases": []}', encoding="utf-8")
    screenshot.write_text("screenshot", encoding="utf-8")
    _write_validation_run(run_output_dir)

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            *_customer_validation_case_cli_args(
                manifest=manifest,
                run_output_dir=run_output_dir,
                screenshot=screenshot,
                mode_flag="--preflight-customer-validation-case",
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "schema_version must be '1.0'" in captured.err
    assert json.loads(manifest.read_text(encoding="utf-8")) == {
        "schema_version": "0.9",
        "cases": [],
    }


def test_preflight_customer_validation_case_can_infer_run_metadata(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "docs" / "customer_validation.json"
    run_output_dir = tmp_path / "runs" / "case-001"
    screenshot = tmp_path / "shots" / "case-001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_text("screenshot", encoding="utf-8")
    _write_validation_run(run_output_dir)

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            "--customer-validation-manifest",
            str(manifest),
            "--preflight-customer-validation-case",
            "--infer-case-metadata-from-run",
            "--case-id",
            "case-client-file-preparation-001",
            "--input-path-or-case-id",
            "anonymized/client-file-preparation/001",
            "--reviewer",
            "QA",
            "--run-output-dir",
            str(run_output_dir),
            "--screenshot-path",
            str(screenshot),
            "--native-output-readback",
            str(run_output_dir / "readback.md"),
            "--validation-status",
            "pass",
            "--ux-verdict",
            "usable",
            *_ux_check_cli_args(),
            "--reviewer-notes",
            "Reviewer completed queue, evidence comparison, decisions, and handoff.",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Customer validation case preflight passed" in output
    assert "case-client-file-preparation-001 (client-file-preparation)" in output
    assert "language=it" in output
    assert "plugin=client-file-preparation" in output
    assert "scenario_name=first_customer_folder_intake" in output
    assert not manifest.exists()


def test_record_customer_validation_case_can_infer_run_metadata(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "docs" / "customer_validation.json"
    run_output_dir = tmp_path / "runs" / "case-001"
    screenshot = tmp_path / "shots" / "case-001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_text("screenshot", encoding="utf-8")
    _write_validation_run(run_output_dir)

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            "--customer-validation-manifest",
            str(manifest),
            "--record-customer-validation-case",
            "--infer-case-metadata-from-run",
            "--case-id",
            "case-client-file-preparation-001",
            "--input-path-or-case-id",
            "anonymized/client-file-preparation/001",
            "--reviewer",
            "QA",
            "--run-output-dir",
            str(run_output_dir),
            "--screenshot-path",
            str(screenshot),
            "--native-output-readback",
            str(run_output_dir / "readback.md"),
            "--validation-status",
            "pass",
            "--ux-verdict",
            "usable",
            *_ux_check_cli_args(),
            "--reviewer-notes",
            "Reviewer completed queue, evidence comparison, decisions, and handoff.",
        ]
    )

    output = capsys.readouterr().out
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    case = payload["cases"][0]

    assert exit_code == 0
    assert (
        "Recorded customer validation case case-client-file-preparation-001" in output
    )
    assert case["plugin"] == "client-file-preparation"
    assert case["scenario_name"] == "first_customer_folder_intake"
    assert case["language"] == "it"


def test_inferred_customer_validation_case_still_requires_reviewer_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "docs" / "customer_validation.json"
    run_output_dir = tmp_path / "runs" / "case-001"
    screenshot = tmp_path / "shots" / "case-001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_text("screenshot", encoding="utf-8")
    _write_validation_run(run_output_dir)

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            "--customer-validation-manifest",
            str(manifest),
            "--preflight-customer-validation-case",
            "--infer-case-metadata-from-run",
            "--case-id",
            "case-client-file-preparation-001",
            "--input-path-or-case-id",
            "anonymized/client-file-preparation/001",
            "--run-output-dir",
            str(run_output_dir),
            "--screenshot-path",
            str(screenshot),
            "--validation-status",
            "pass",
            "--ux-verdict",
            "usable",
            *_ux_check_cli_args(),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "--reviewer" in captured.err
    assert "--reviewer-notes" in captured.err
    assert "--plugin" not in captured.err
    assert "--scenario-name" not in captured.err
    assert "--language" not in captured.err
    assert not manifest.exists()


def test_record_customer_validation_case_refuses_pending_final_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "docs" / "customer_validation.json"
    run_output_dir = manifest.parent / "runs" / "case-001"
    screenshot = manifest.parent / "shots" / "case-001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_text("screenshot", encoding="utf-8")
    _write_validation_run_with_pending_final_artifacts(run_output_dir)

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            "--customer-validation-manifest",
            str(manifest),
            "--record-customer-validation-case",
            "--case-id",
            "case-client-file-preparation-001",
            "--plugin",
            "client-file-preparation",
            "--scenario-name",
            "Italian client file preparation folder",
            "--input-path-or-case-id",
            "anonymized/client-file-preparation/001",
            "--language",
            "it",
            "--reviewer",
            "QA",
            "--run-output-dir",
            str(run_output_dir),
            "--screenshot-path",
            str(screenshot),
            "--validation-status",
            "pass",
            "--ux-verdict",
            "usable",
            *_ux_check_cli_args(),
            "--reviewer-notes",
            "Reviewer completed the UI but final artifacts were pending.",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "invalid artifact content" in captured.err
    assert "pending review" in captured.err
    assert not manifest.exists()


def test_record_customer_validation_case_refuses_synthetic_browser_audit_run(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "docs" / "customer_validation.json"
    run_output_dir = manifest.parent / "runs" / "case-001"
    screenshot = manifest.parent / "shots" / "case-001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_text("screenshot", encoding="utf-8")
    _write_validation_run(run_output_dir)
    (run_output_dir / "run_intake.json").write_text(
        json.dumps(
            {
                "plugin": "client-file-preparation",
                "workflow": "client-file-preparation",
                "inferred_task": "Browser write-back audit for Client File Preparation review.",
                "assumptions": [
                    "Synthetic local fixture generated from the workbench adapter demo; not customer validation."
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            "--customer-validation-manifest",
            str(manifest),
            "--record-customer-validation-case",
            "--case-id",
            "case-client-file-preparation-001",
            "--plugin",
            "client-file-preparation",
            "--scenario-name",
            "Italian client file preparation folder",
            "--input-path-or-case-id",
            "anonymized/client-file-preparation/001",
            "--language",
            "it",
            "--reviewer",
            "QA",
            "--run-output-dir",
            str(run_output_dir),
            "--screenshot-path",
            str(screenshot),
            "--validation-status",
            "pass",
            "--ux-verdict",
            "usable",
            *_ux_check_cli_args(),
            "--reviewer-notes",
            "Reviewer completed queue, evidence comparison, decisions, and handoff.",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "non-customer run metadata" in captured.err
    assert "synthetic" in captured.err
    assert "not customer validation" in captured.err
    assert not manifest.exists()


def test_record_customer_validation_case_refuses_mismatched_plugin_metadata(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "docs" / "customer_validation.json"
    run_output_dir = manifest.parent / "runs" / "case-001"
    screenshot = manifest.parent / "shots" / "case-001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_text("screenshot", encoding="utf-8")
    _write_validation_run(run_output_dir)
    (run_output_dir / "review_payload.json").write_text(
        json.dumps({"plugin": "report-builder", "items": [{"id": "item-1"}]}),
        encoding="utf-8",
    )

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            "--customer-validation-manifest",
            str(manifest),
            "--record-customer-validation-case",
            "--case-id",
            "case-client-file-preparation-001",
            "--plugin",
            "client-file-preparation",
            "--scenario-name",
            "Italian client file preparation folder",
            "--input-path-or-case-id",
            "anonymized/client-file-preparation/001",
            "--language",
            "it",
            "--reviewer",
            "QA",
            "--run-output-dir",
            str(run_output_dir),
            "--screenshot-path",
            str(screenshot),
            "--validation-status",
            "pass",
            "--ux-verdict",
            "usable",
            *_ux_check_cli_args(),
            "--reviewer-notes",
            "Reviewer completed queue, evidence comparison, decisions, and handoff.",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "review_payload.plugin is 'report-builder'" in captured.err
    assert "expected 'client-file-preparation'" in captured.err
    assert not manifest.exists()


def test_record_customer_validation_case_refuses_incomplete_ux_checks(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "docs" / "customer_validation.json"
    run_output_dir = manifest.parent / "runs" / "case-001"
    screenshot = manifest.parent / "shots" / "case-001.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_text("screenshot", encoding="utf-8")
    _write_validation_run(run_output_dir)

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            "--customer-validation-manifest",
            str(manifest),
            "--record-customer-validation-case",
            "--case-id",
            "case-client-file-preparation-001",
            "--plugin",
            "client-file-preparation",
            "--scenario-name",
            "Italian client file preparation folder",
            "--input-path-or-case-id",
            "anonymized/client-file-preparation/001",
            "--language",
            "it",
            "--reviewer",
            "QA",
            "--run-output-dir",
            str(run_output_dir),
            "--screenshot-path",
            str(screenshot),
            "--validation-status",
            "pass",
            "--ux-verdict",
            "usable",
            "--ux-check",
            "queue_clear",
            "--reviewer-notes",
            "Reviewer only confirmed queue clarity.",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "usable/pass cases must include UX checks" in captured.err
    assert "decision_controls_complete" in captured.err
    assert not manifest.exists()


def test_record_customer_validation_case_refuses_missing_run_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "docs" / "customer_validation.json"
    run_output_dir = manifest.parent / "runs" / "case-001"
    screenshot = manifest.parent / "shots" / "case-001.png"
    run_output_dir.mkdir(parents=True, exist_ok=True)
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_text("screenshot", encoding="utf-8")
    (run_output_dir / "run_intake.json").write_text("{}", encoding="utf-8")

    exit_code = audit.main(
        [
            "--root",
            str(tmp_path),
            "--customer-validation-manifest",
            str(manifest),
            "--record-customer-validation-case",
            "--case-id",
            "case-client-file-preparation-001",
            "--plugin",
            "client-file-preparation",
            "--scenario-name",
            "Italian client file preparation folder",
            "--input-path-or-case-id",
            "anonymized/client-file-preparation/001",
            "--language",
            "it",
            "--reviewer",
            "QA",
            "--run-output-dir",
            str(run_output_dir),
            "--screenshot-path",
            str(screenshot),
            "--validation-status",
            "pass",
            "--ux-verdict",
            "usable",
            *_ux_check_cli_args(),
            "--reviewer-notes",
            "Reviewer attempted validation but run artifacts were incomplete.",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "missing artifacts" in captured.err
    assert not manifest.exists()


def test_customer_validation_manifest_flags_incomplete_evidence(
    tmp_path: Path,
) -> None:
    _write_good_plugin(tmp_path)
    manifest = tmp_path / "customer_validation.json"
    _write_customer_manifest(
        manifest,
        artifact_paths={
            "run_intake": "out/run_intake.json",
            "review_payload": "out/review_payload.json",
        },
        status="partial",
    )

    report = audit.audit_adoption_readiness(
        tmp_path,
        customer_manifest_path=manifest,
        expected_customer_plugins=("client-file-preparation",),
    )
    issue_codes = {issue.code for issue in report.issues}

    assert report.status == "partial"
    assert report.customer_validation["status"] == "partial"
    assert "customer_validation_artifact_paths_incomplete" in issue_codes
    assert "customer_validation_screenshots_missing" in issue_codes
    assert {item["id"] for item in report.next_actions} >= {
        "validate_final_artifact_semantics"
    }


def test_customer_validation_manifest_requires_expected_plugin_coverage(
    tmp_path: Path,
) -> None:
    _write_good_plugin(tmp_path)
    manifest = tmp_path / "customer_validation.json"
    _write_customer_manifest(manifest)

    report = audit.audit_adoption_readiness(
        tmp_path,
        customer_manifest_path=manifest,
        expected_customer_plugins=("client-file-preparation", "report-builder"),
    )
    issue_codes = {issue.code for issue in report.issues}

    assert report.status == "partial"
    assert report.customer_validation["status"] == "partial"
    assert report.customer_validation["covered_plugins"] == ["client-file-preparation"]
    assert report.customer_validation["missing_expected_plugins"] == ["report-builder"]
    assert "customer_validation_expected_plugins_missing" in issue_codes


def test_readiness_fails_for_continue_theater(tmp_path: Path) -> None:
    _write_plugin(
        tmp_path,
        "bad-plugin",
        "Ask the user to type continue before every step.",
    )

    report = audit.audit_adoption_readiness(tmp_path)
    issue_codes = {issue.code for issue in report.issues}

    assert report.status == "blocker"
    assert "continue_theater" in issue_codes
    assert (
        audit.main(
            [
                "--root",
                str(tmp_path),
                "--format",
                "json",
                "--fail-on",
                "blocker",
            ]
        )
        == 1
    )
