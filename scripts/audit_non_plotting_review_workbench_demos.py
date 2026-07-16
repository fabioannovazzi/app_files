#!/usr/bin/env python3
"""Audit shared non-plotting review workbench demo payloads.

The interaction-pattern audit checks plugin contracts. This audit checks the
sample review payload embedded in each generated workbench adapter, because the
demo is the cheapest repeatable proxy for whether a reviewer can see the real
workflow shape: queue, evidence, actions, edit impact, and localized labels.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "DemoIssue",
    "DemoWorkbenchReport",
    "audit_adapter",
    "audit_adapters",
    "main",
]

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_LOCALES = ("it", "fr", "de")
MIN_DEMO_ITEMS = 2
MIN_WORKFLOW_PANELS = 3
MATERIAL_REVIEW_ACTIONS = {
    "edit",
    "mark_unclear",
    "reject",
    "request_more_documents",
}
SEVERITY_RANK = {
    "info": 1,
    "medium": 2,
    "high": 3,
    "blocker": 4,
}
MCP_SET_PATTERN_TEMPLATE = (
    r"const\s+{name}\s*=\s*new\s+Set\s*\(\s*\[(?P<body>.*?)\]\s*\)"
)


@dataclass(frozen=True)
class DemoIssue:
    """One workbench demo-payload finding."""

    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable representation."""

        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class DemoWorkbenchReport:
    """Audit result for one shared workbench adapter demo."""

    plugin: str
    adapter_path: str
    detail_mode: str = ""
    review_title: str = ""
    queue_title: str = ""
    detail_title: str = ""
    item_count: int = 0
    item_types: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()
    detail_groups: tuple[str, ...] = ()
    issues: list[DemoIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Return a compact status for CI and scorecards."""

        severities = {issue.severity for issue in self.issues}
        if "blocker" in severities:
            return "blocker"
        if "high" in severities:
            return "needs_attention"
        if "medium" in severities:
            return "partial"
        return "ok"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "plugin": self.plugin,
            "status": self.status,
            "adapter_path": self.adapter_path,
            "detail_mode": self.detail_mode,
            "review_title": self.review_title,
            "queue_title": self.queue_title,
            "detail_title": self.detail_title,
            "item_count": self.item_count,
            "item_types": list(self.item_types),
            "recommended_actions": list(self.recommended_actions),
            "detail_groups": list(self.detail_groups),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _discover_adapters(root: Path) -> list[Path]:
    plugin_root = root / "plugins"
    if not plugin_root.exists():
        return []
    return sorted(plugin_root.glob("*/assets/review-workbench-adapter.json"))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _plugin_from_adapter_path(path: Path) -> str:
    try:
        return path.parents[1].name
    except IndexError:
        return path.stem


def _issue(severity: str, code: str, message: str) -> DemoIssue:
    return DemoIssue(severity=severity, code=code, message=message)


def _plugin_dir_for_adapter(adapter_path: Path) -> Path | None:
    try:
        return adapter_path.parents[1]
    except IndexError:
        return None


def _read_mcp_string_set(plugin_dir: Path | None, const_name: str) -> set[str] | None:
    """Return a simple string set declared by the plugin MCP server."""

    if plugin_dir is None:
        return None
    server_path = plugin_dir / "mcp" / "server.cjs"
    if not server_path.exists():
        return None
    pattern = MCP_SET_PATTERN_TEMPLATE.format(name=re.escape(const_name))
    match = re.search(pattern, server_path.read_text(encoding="utf-8"), re.DOTALL)
    if match is None:
        return None
    return set(re.findall(r'"([^"]+)"', match.group("body")))


def _item_dicts(adapter: dict[str, Any]) -> list[dict[str, Any]]:
    demo = adapter.get("demo")
    if not isinstance(demo, dict):
        return []
    items = demo.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _field_is_present(field: str, item: dict[str, Any]) -> bool:
    if _has_meaningful_value(item.get(field)):
        return True
    data = item.get("data")
    if isinstance(data, dict) and _has_meaningful_value(data.get(field)):
        return True
    evidence = item.get("evidence")
    if isinstance(evidence, list):
        for evidence_row in evidence:
            if isinstance(evidence_row, dict) and _has_meaningful_value(
                evidence_row.get(field)
            ):
                return True
    return False


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _string_value(adapter: dict[str, Any], key: str) -> str:
    value = adapter.get(key)
    return value.strip() if isinstance(value, str) else ""


def _has_explicit_edit_target(item: dict[str, Any]) -> bool:
    if "edit" not in _allowed_actions(item):
        return False
    data = item.get("data")
    if not isinstance(data, dict):
        return False
    return (
        _has_meaningful_value(data.get("target_artifact"))
        and _has_meaningful_value(data.get("target_field"))
        and (
            _has_meaningful_value(data.get("target_record_id"))
            or _has_meaningful_value(data.get("target_records_key"))
        )
        and _has_meaningful_value(data.get("edit_hint"))
    )


def _allowed_actions(item: dict[str, Any]) -> set[str]:
    actions = item.get("allowed_actions")
    if not isinstance(actions, list):
        return set()
    return {action for action in actions if isinstance(action, str) and action}


def _recommended_action(item: dict[str, Any]) -> str:
    action = item.get("recommended_action")
    return action if isinstance(action, str) else ""


def _detail_group_coverage(
    groups: list[dict[str, Any]], items: list[dict[str, Any]]
) -> list[str]:
    missing: list[str] = []
    for group in groups:
        title = group.get("title")
        fields = group.get("fields")
        if not isinstance(title, str) or not isinstance(fields, list):
            missing.append(str(title or "untitled"))
            continue
        group_fields = [field for field in fields if isinstance(field, str)]
        if not any(
            _field_is_present(field, item) for field in group_fields for item in items
        ):
            missing.append(title)
    return missing


def audit_adapter(adapter_path: Path, root: Path = ROOT) -> DemoWorkbenchReport:
    """Audit one generated workbench adapter demo payload."""

    adapter = _read_json(adapter_path)
    plugin = adapter.get("plugin")
    if not isinstance(plugin, str) or not plugin:
        plugin = _plugin_from_adapter_path(adapter_path)
    try:
        relative_path = str(adapter_path.relative_to(root)).replace("\\", "/")
    except ValueError:
        relative_path = str(adapter_path)
    items = _item_dicts(adapter)
    item_types = tuple(
        sorted(
            {
                item_type
                for item in items
                if isinstance(item_type := item.get("item_type"), str) and item_type
            }
        )
    )
    recommended_actions = tuple(
        sorted(
            {_recommended_action(item) for item in items if _recommended_action(item)}
        )
    )
    detail_groups = adapter.get("detailGroups")
    if not isinstance(detail_groups, list):
        detail_groups = []
    detail_group_titles = tuple(
        group["title"]
        for group in detail_groups
        if isinstance(group, dict) and isinstance(group.get("title"), str)
    )
    panels = adapter.get("panels")
    if not isinstance(panels, list):
        panels = []
    panel_titles = [panel for panel in panels if isinstance(panel, str) and panel]
    report = DemoWorkbenchReport(
        plugin=plugin,
        adapter_path=relative_path,
        detail_mode=_string_value(adapter, "detailMode"),
        review_title=_string_value(adapter, "reviewTitle"),
        queue_title=_string_value(adapter, "queueTitle"),
        detail_title=_string_value(adapter, "detailTitle"),
        item_count=len(items),
        item_types=item_types,
        recommended_actions=recommended_actions,
        detail_groups=detail_group_titles,
    )
    plugin_dir = _plugin_dir_for_adapter(adapter_path)
    supported_item_types = _read_mcp_string_set(plugin_dir, "ITEM_TYPES")
    supported_actions = _read_mcp_string_set(plugin_dir, "ALLOWED_ACTIONS")

    required_workflow_identity_fields = {
        "detailMode": report.detail_mode,
        "reviewTitle": report.review_title,
        "queueTitle": report.queue_title,
        "detailTitle": report.detail_title,
        "detailHelp": _string_value(adapter, "detailHelp"),
    }
    for field, value in required_workflow_identity_fields.items():
        if not value:
            report.issues.append(
                _issue(
                    "high" if field == "detailMode" else "medium",
                    "workflow_identity_field_missing",
                    f"Adapter is missing workflow-specific {field}.",
                )
            )

    if len(panel_titles) < MIN_WORKFLOW_PANELS:
        report.issues.append(
            _issue(
                "medium",
                "workflow_panels_too_shallow",
                "Adapter should define at least three workflow-specific panels so the shared shell does not read as a generic page.",
            )
        )

    if len(items) < MIN_DEMO_ITEMS:
        report.issues.append(
            _issue(
                "high",
                "demo_queue_too_shallow",
                "Demo must include at least two review items so queue and selection behavior are exercised.",
            )
        )

    if len(item_types) < 2:
        report.issues.append(
            _issue(
                "medium",
                "demo_item_types_too_shallow",
                "Demo should include at least two item types so workflow-specific review states are visible.",
            )
        )

    if len(recommended_actions) < 2:
        report.issues.append(
            _issue(
                "medium",
                "demo_action_variety_missing",
                "Demo should include at least two recommended actions so state filters and decision impact are exercised.",
            )
        )

    if not any(action in MATERIAL_REVIEW_ACTIONS for action in recommended_actions):
        report.issues.append(
            _issue(
                "medium",
                "demo_material_review_path_missing",
                "Demo should include an edit, rejection, unclear, or document-request path, not only clean accept rows.",
            )
        )

    for item in items:
        item_id = item.get("id") or "<missing id>"
        item_type = item.get("item_type")
        allowed = _allowed_actions(item)
        recommended = _recommended_action(item)
        if not _has_meaningful_value(item.get("id")):
            report.issues.append(
                _issue("high", "demo_item_id_missing", "Demo item is missing id.")
            )
        if supported_item_types is not None and (
            not isinstance(item_type, str) or item_type not in supported_item_types
        ):
            report.issues.append(
                _issue(
                    "high",
                    "demo_item_type_unsupported",
                    f"Demo item {item_id} has item_type {item_type!r}, which is not accepted by the MCP validator.",
                )
            )
        if not _has_meaningful_value(item.get("title")):
            report.issues.append(
                _issue(
                    "medium",
                    "demo_item_title_missing",
                    f"Demo item {item_id} is missing title.",
                )
            )
        if not allowed:
            report.issues.append(
                _issue(
                    "high",
                    "demo_allowed_actions_missing",
                    f"Demo item {item_id} is missing allowed_actions.",
                )
            )
        if supported_actions is not None:
            unsupported_actions = sorted(allowed - supported_actions)
            if unsupported_actions:
                report.issues.append(
                    _issue(
                        "high",
                        "demo_allowed_action_unsupported",
                        f"Demo item {item_id} allows unsupported action(s): "
                        + ", ".join(unsupported_actions),
                    )
                )
        if recommended and recommended not in allowed:
            report.issues.append(
                _issue(
                    "high",
                    "demo_recommended_action_invalid",
                    f"Demo item {item_id} recommends {recommended!r}, which is not allowed.",
                )
            )
        if (
            supported_actions is not None
            and recommended
            and recommended not in supported_actions
        ):
            report.issues.append(
                _issue(
                    "high",
                    "demo_recommended_action_unsupported",
                    f"Demo item {item_id} recommends unsupported action {recommended!r}.",
                )
            )
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            report.issues.append(
                _issue(
                    "high",
                    "demo_evidence_missing",
                    f"Demo item {item_id} has no evidence rows.",
                )
            )

    if not any(_has_explicit_edit_target(item) for item in items):
        report.issues.append(
            _issue(
                "medium",
                "demo_edit_target_missing",
                "At least one editable demo item should show target artifact, record, field, and edit hint.",
            )
        )

    missing_groups = _detail_group_coverage(detail_groups, items)
    for group_title in missing_groups:
        report.issues.append(
            _issue(
                "medium",
                "demo_detail_group_uncovered",
                f"Demo does not populate any configured field for detail group {group_title!r}.",
            )
        )

    localized = adapter.get("localized")
    if not isinstance(localized, dict):
        localized = {}
    missing_locales = [locale for locale in REQUIRED_LOCALES if locale not in localized]
    if missing_locales:
        report.issues.append(
            _issue(
                "high",
                "demo_locales_missing",
                "Adapter is missing localized workflow labels for "
                + ", ".join(missing_locales)
                + ".",
            )
        )

    return report


def audit_adapters(root: Path = ROOT) -> list[DemoWorkbenchReport]:
    """Audit every generated non-plotting workbench adapter in the repo."""

    reports = [audit_adapter(path, root=root) for path in _discover_adapters(root)]
    by_detail_mode: dict[str, list[DemoWorkbenchReport]] = {}
    for report in reports:
        if report.detail_mode:
            by_detail_mode.setdefault(report.detail_mode, []).append(report)
    for detail_mode, duplicate_reports in by_detail_mode.items():
        if len(duplicate_reports) < 2:
            continue
        plugins = ", ".join(report.plugin for report in duplicate_reports)
        for report in duplicate_reports:
            report.issues.append(
                _issue(
                    "high",
                    "workflow_detail_mode_duplicate",
                    f"detailMode {detail_mode!r} is shared by multiple adapters: {plugins}.",
                )
            )
    return reports


def _summary(reports: list[DemoWorkbenchReport]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    issue_counts: dict[str, int] = {}
    for report in reports:
        counts[report.status] = counts.get(report.status, 0) + 1
        for issue in report.issues:
            issue_counts[issue.severity] = issue_counts.get(issue.severity, 0) + 1
    return {
        "adapter_count": len(reports),
        "status_counts": dict(sorted(counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
    }


def _markdown_report(reports: list[DemoWorkbenchReport]) -> str:
    summary = _summary(reports)
    lines = [
        "# Non-Plotting Workbench Demo Audit",
        "",
        f"Adapters audited: {summary['adapter_count']}",
        f"Status counts: `{json.dumps(summary['status_counts'], sort_keys=True)}`",
        f"Issue counts: `{json.dumps(summary['issue_counts'], sort_keys=True)}`",
        "",
        "| Plugin | Status | Mode | Items | Types | Actions | Detail Groups | Issues |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for report in reports:
        issues = ", ".join(f"{issue.severity}:{issue.code}" for issue in report.issues)
        lines.append(
            "| "
            + " | ".join(
                [
                    report.plugin,
                    report.status,
                    report.detail_mode or "missing",
                    str(report.item_count),
                    ", ".join(report.item_types) or "none",
                    ", ".join(report.recommended_actions) or "none",
                    ", ".join(report.detail_groups) or "none",
                    issues or "none",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _json_report(reports: list[DemoWorkbenchReport]) -> str:
    return (
        json.dumps(
            {
                "summary": _summary(reports),
                "reports": [report.to_dict() for report in reports],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _has_failure(reports: list[DemoWorkbenchReport], fail_on: str) -> bool:
    threshold = SEVERITY_RANK[fail_on]
    return any(
        SEVERITY_RANK[issue.severity] >= threshold
        for report in reports
        for issue in report.issues
    )


def main(argv: list[str] | None = None) -> int:
    """Run the demo audit CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--fail-on",
        choices=("blocker", "high", "medium", "info"),
        default="high",
        help="Exit nonzero when findings at or above this severity exist.",
    )
    args = parser.parse_args(argv)

    reports = audit_adapters(args.root)
    if args.format == "json":
        sys.stdout.write(_json_report(reports))
    else:
        sys.stdout.write(_markdown_report(reports))
    return 1 if _has_failure(reports, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
