from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "audit_non_plotting_review_workbench_demos.py"


spec = importlib.util.spec_from_file_location(
    "audit_non_plotting_review_workbench_demos", SCRIPT_PATH
)
assert spec is not None
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


def _write_adapter(root: Path, plugin: str, adapter: dict[str, object]) -> Path:
    adapter_dir = root / "plugins" / plugin / "assets"
    adapter_dir.mkdir(parents=True)
    adapter_path = adapter_dir / "review-workbench-adapter.json"
    adapter_path.write_text(json.dumps(adapter, indent=2) + "\n", encoding="utf-8")
    return adapter_path


def _write_mcp_server(root: Path, plugin: str) -> None:
    server_dir = root / "plugins" / plugin / "mcp"
    server_dir.mkdir(parents=True)
    (server_dir / "server.cjs").write_text(
        """
const ALLOWED_ACTIONS = new Set([
  "accept",
  "edit",
  "request_more_documents",
]);
const ITEM_TYPES = new Set([
  "matched_row",
  "exception_row",
]);
""".strip() + "\n",
        encoding="utf-8",
    )


def _valid_adapter(plugin: str = "demo-review") -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "plugin": plugin,
        "title": "Demo Review",
        "reviewTitle": "Demo Review",
        "queueTitle": "Rows",
        "detailTitle": "Evidence",
        "detailMode": "demo-review-desk",
        "detailHelp": "Compare demo rows to support and record reviewer decisions.",
        "detailGroups": [
            {"title": "Row", "fields": ["record_id", "status"]},
            {"title": "Evidence", "fields": ["support", "reason"]},
            {"title": "Decision", "fields": ["review_notes"]},
        ],
        "panels": ["Row", "Evidence", "Decision"],
        "localized": {
            "it": {"title": "Demo"},
            "fr": {"title": "Demo"},
            "de": {"title": "Demo"},
        },
        "demo": {
            "review_type": "demo_review",
            "items": [
                {
                    "id": "row-1",
                    "item_type": "matched_row",
                    "title": "Matched row",
                    "allowed_actions": ["accept", "edit", "mark_unclear"],
                    "recommended_action": "accept",
                    "data": {
                        "record_id": "row-1",
                        "status": "matched",
                        "review_notes": "Ready.",
                        "target_artifact": "review.csv",
                        "target_id_field": "record_id",
                        "target_record_id": "row-1",
                        "target_field": "review_notes",
                        "edit_hint": "Updates review.csv.",
                    },
                    "evidence": [{"kind": "support", "support": "source row 1"}],
                },
                {
                    "id": "row-2",
                    "item_type": "exception_row",
                    "title": "Exception row",
                    "allowed_actions": [
                        "accept",
                        "edit",
                        "request_more_documents",
                    ],
                    "recommended_action": "request_more_documents",
                    "data": {
                        "record_id": "row-2",
                        "status": "needs_evidence",
                        "reason": "Missing support.",
                    },
                    "evidence": [
                        {
                            "kind": "missing_support",
                            "reason": "Missing support.",
                        }
                    ],
                },
            ],
        },
    }


def test_repo_workbench_demo_audit_has_no_findings() -> None:
    reports = audit.audit_adapters(ROOT)

    assert {report.plugin for report in reports} == {
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
    assert all(not report.issues for report in reports)


def test_audit_detects_shallow_demo_payload(tmp_path: Path) -> None:
    adapter = _valid_adapter()
    adapter["localized"] = {"it": {"title": "Demo"}}
    demo = adapter["demo"]
    assert isinstance(demo, dict)
    demo["items"] = [
        {
            "id": "row-1",
            "item_type": "matched_row",
            "title": "Matched row",
            "allowed_actions": ["accept"],
            "recommended_action": "accept",
            "data": {"record_id": "row-1", "status": "matched"},
            "evidence": [],
        }
    ]
    _write_adapter(tmp_path, "demo-review", adapter)

    report = audit.audit_adapters(tmp_path)[0]
    codes = {issue.code for issue in report.issues}

    assert report.status == "needs_attention"
    assert "demo_queue_too_shallow" in codes
    assert "demo_item_types_too_shallow" in codes
    assert "demo_action_variety_missing" in codes
    assert "demo_material_review_path_missing" in codes
    assert "demo_evidence_missing" in codes
    assert "demo_edit_target_missing" in codes
    assert "demo_locales_missing" in codes


def test_audit_detects_missing_workflow_identity_fields(
    tmp_path: Path,
) -> None:
    adapter = _valid_adapter()
    adapter.pop("detailMode")
    adapter.pop("detailHelp")
    adapter["panels"] = ["Evidence"]
    _write_adapter(tmp_path, "demo-review", adapter)

    report = audit.audit_adapters(tmp_path)[0]
    codes = {issue.code for issue in report.issues}

    assert report.status == "needs_attention"
    assert "workflow_identity_field_missing" in codes
    assert "workflow_panels_too_shallow" in codes


def test_audit_detects_duplicate_workflow_detail_modes(tmp_path: Path) -> None:
    first = _valid_adapter(plugin="first-review")
    second = _valid_adapter(plugin="second-review")
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    first["detailMode"] = "generic-desk"
    second["detailMode"] = "generic-desk"
    _write_adapter(tmp_path, "first-review", first)
    _write_adapter(tmp_path, "second-review", second)

    reports = audit.audit_adapters(tmp_path)

    assert {report.plugin for report in reports} == {"first-review", "second-review"}
    assert all(report.status == "needs_attention" for report in reports)
    assert all(
        "workflow_detail_mode_duplicate" in {issue.code for issue in report.issues}
        for report in reports
    )


def test_audit_detects_demo_values_rejected_by_mcp_contract(tmp_path: Path) -> None:
    adapter = _valid_adapter()
    demo = adapter["demo"]
    assert isinstance(demo, dict)
    items = demo["items"]
    assert isinstance(items, list)
    bad_item = items[1]
    assert isinstance(bad_item, dict)
    bad_item["item_type"] = "unsupported_row"
    bad_item["allowed_actions"] = ["accept", "teleport"]
    bad_item["recommended_action"] = "teleport"
    _write_adapter(tmp_path, "demo-review", adapter)
    _write_mcp_server(tmp_path, "demo-review")

    report = audit.audit_adapters(tmp_path)[0]
    codes = {issue.code for issue in report.issues}

    assert report.status == "needs_attention"
    assert "demo_item_type_unsupported" in codes
    assert "demo_allowed_action_unsupported" in codes
    assert "demo_recommended_action_unsupported" in codes


def test_audit_main_emits_json_summary(tmp_path: Path, capsys) -> None:
    _write_adapter(tmp_path, "demo-review", _valid_adapter())

    exit_code = audit.main(
        ["--root", str(tmp_path), "--format", "json", "--fail-on", "medium"]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["summary"] == {
        "adapter_count": 1,
        "issue_counts": {},
        "status_counts": {"ok": 1},
    }
    assert payload["reports"][0]["plugin"] == "demo-review"
