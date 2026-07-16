from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "audit_review_payload_contract_coverage.py"


spec = importlib.util.spec_from_file_location(
    "audit_review_payload_contract_coverage", SCRIPT_PATH
)
assert spec is not None
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


def _write_adapter(root: Path, plugin: str) -> None:
    adapter_dir = root / "plugins" / plugin / "assets"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "review-workbench-adapter.json").write_text(
        json.dumps({"plugin": plugin, "demo": {"items": []}}) + "\n",
        encoding="utf-8",
    )


def test_repo_review_payload_contract_coverage_has_no_gaps() -> None:
    reports = audit.audit_contract_coverage(ROOT)
    by_plugin = {report.plugin: report for report in reports}

    assert set(by_plugin) == {
        "audit-reconciliation",
        "check-entries",
        "client-intake",
        "concordato-plan-review",
        "deep-research-validator",
        "journal-bank-reconciliation",
        "journal-sampling",
        "prompt-optimizer",
        "report-builder",
    }
    assert all(report.status == "ok" for report in reports)
    assert all(report.test_files for report in reports)
    assert all(report.scenario_files for report in reports)
    assert by_plugin["report-builder"].test_files == (
        "tests/plugins/test_report_builder_plugin.py",
    )


def test_audit_detects_missing_generated_payload_contract_test(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "demo-review")
    test_root = tmp_path / "tests" / "plugins"
    test_root.mkdir(parents=True)
    (test_root / "test_demo_review.py").write_text(
        "def test_demo_review_smoke():\n" "    assert 'demo-review'\n",
        encoding="utf-8",
    )

    report = audit.audit_contract_coverage(
        tmp_path,
        test_roots=(test_root,),
    )[0]

    assert report.status == "needs_attention"
    assert report.test_files == ()
    assert report.issues[0].code == "generated_payload_contract_test_missing"


def test_audit_main_emits_json_summary(tmp_path: Path, capsys) -> None:
    _write_adapter(tmp_path, "demo-review")
    test_root = tmp_path / "tests" / "plugins"
    test_root.mkdir(parents=True)
    (test_root / "test_demo_review.py").write_text(
        "from scripts.validate_plugin_review_contract import validate_contract\n\n"
        "def test_demo_review_contract(tmp_path):\n"
        "    core.run_demo_review_workflow()\n"
        "    for name in ('run_intake.json', 'review_payload.json', "
        "'ui_decisions.json', 'final_artifacts.json'):\n"
        "        assert name\n"
        "    assert {'plugin': 'demo-review'}['plugin'] == 'demo-review'\n"
        "    validate_contract(tmp_path)\n",
        encoding="utf-8",
    )

    exit_code = audit.main(
        ["--root", str(tmp_path), "--format", "json", "--fail-on", "high"]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["summary"] == {
        "issue_counts": {},
        "plugin_count": 1,
        "status_counts": {"ok": 1},
    }
    assert payload["reports"][0]["plugin"] == "demo-review"
    assert payload["reports"][0]["scenario_files"] == [
        "tests/plugins/test_demo_review.py"
    ]


def test_audit_ignores_unrelated_plugin_string(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "report-builder")
    test_root = tmp_path / "tests" / "plugins"
    test_root.mkdir(parents=True)
    (test_root / "test_concordato_plan_review.py").write_text(
        "from scripts.validate_plugin_review_contract import validate_contract\n\n"
        "def test_concordato_contract(tmp_path):\n"
        "    assert 'report-builder' not in 'concordato-plan-review'\n"
        "    validate_contract(tmp_path)\n",
        encoding="utf-8",
    )

    report = audit.audit_contract_coverage(
        tmp_path,
        test_roots=(test_root,),
    )[0]

    assert report.status == "needs_attention"
    assert report.test_files == ()
    assert report.issues[0].code == "generated_payload_contract_test_missing"


def test_audit_flags_contract_test_without_workflow_scenario(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "demo-review")
    test_root = tmp_path / "tests" / "plugins"
    test_root.mkdir(parents=True)
    (test_root / "test_demo_review.py").write_text(
        "from scripts.validate_plugin_review_contract import validate_contract\n\n"
        "def test_demo_review_contract(tmp_path):\n"
        "    payload = {'plugin': 'demo-review'}\n"
        "    assert payload['plugin'] == 'demo-review'\n"
        "    validate_contract(tmp_path)\n",
        encoding="utf-8",
    )

    report = audit.audit_contract_coverage(
        tmp_path,
        test_roots=(test_root,),
    )[0]

    assert report.status == "partial"
    assert report.test_files == ("tests/plugins/test_demo_review.py",)
    assert report.scenario_files == ()
    assert report.issues[0].code == "generated_payload_workflow_scenario_missing"
