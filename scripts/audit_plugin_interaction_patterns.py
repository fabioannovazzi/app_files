#!/usr/bin/env python3
"""Audit Codex plugin interaction patterns against the local playbook.

The audit turns OpenAI-pattern lessons into concrete signals that can be
reviewed per plugin without forcing every plugin into the same UI shape.
The command is useful as a repo-level scorecard, and package validation reuses
its blocker/high/medium findings as source-validation failures.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "InteractionIssue",
    "InteractionPattern",
    "InteractionPatternCoverage",
    "InteractionPlaybookSectionCoverage",
    "InteractionRejectedPattern",
    "PluginInteractionReport",
    "audit_plugin",
    "audit_plugins",
    "load_pattern_catalog",
    "load_playbook_section_coverage",
    "load_rejected_patterns",
    "main",
    "pattern_catalog",
    "pattern_coverage",
    "playbook_section_coverage",
    "rejected_patterns",
]

ROOT = Path(__file__).resolve().parents[1]
PATTERN_CATALOG_PATH = ROOT / "docs" / "openai_plugin_interaction_patterns.json"

BANNED_CONTINUE_PROMPTS = (
    "type `continue`",
    "type continue",
    "enter `continue`",
    "enter continue",
    "write `continue`",
    "write continue",
    "say `continue`",
    "say continue",
    "reply `continue`",
    "reply continue",
)
APPROVAL_BOUNDARY_TERMS = (
    "external",
    "destructive",
    "approval-sensitive",
    "material",
)
DECISION_CONTRACT_TERMS = (
    "ui_decisions.json",
    "applied_decisions.json",
    "final_artifacts.json",
)
REVIEW_TOOL_TERMS = ("validate_", "render_", "save_", "apply_")
LOCAL_POSTURE_TERMS = (
    "local",
    "deterministic",
)
KNOWN_PATTERN_SIGNALS = frozenset(
    (
        "mcp_review_widget",
        "stateful_decision_review",
        "generated_workbench_asset",
        "local_html_review_asset",
        "has_local_browser_writeback",
        "has_review_handoff_contract",
        "has_local_data_posture_language",
        "has_approval_boundary_language",
        "has_no_continue_theater",
        "has_decision_contract_language",
        "continue_theater",
        "approval_boundary_missing",
        "local_deterministic_posture_missing",
        "static_review_without_mcp_widget",
        "decision_contract_missing_in_skill",
        "review_tool_names_missing_in_skill",
        "visible_handoff_missing",
        "render_only_review",
        "custom_stateful_review_surface",
    )
)


@dataclass(frozen=True)
class InteractionPattern:
    """One extracted OpenAI interaction pattern adapted for local plugins."""

    pattern_id: str
    source_pattern: str
    local_rule: str
    playbook_section: str
    evidence_signals: tuple[str, ...]
    verifier_paths: tuple[str, ...]
    adoption_scope: str
    applicability_signals: tuple[str, ...] = ()
    evidence_mode: str = "all"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "pattern_id": self.pattern_id,
            "source_pattern": self.source_pattern,
            "local_rule": self.local_rule,
            "playbook_section": self.playbook_section,
            "evidence_signals": list(self.evidence_signals),
            "verifier_paths": list(self.verifier_paths),
            "adoption_scope": self.adoption_scope,
            "applicability_signals": list(self.applicability_signals),
            "evidence_mode": self.evidence_mode,
        }


@dataclass(frozen=True)
class InteractionIssue:
    """One audit finding for a plugin interaction pattern."""

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


@dataclass(frozen=True)
class InteractionPatternCoverage:
    """Per-pattern coverage against the current plugin reports."""

    pattern_id: str
    applicable_plugins: tuple[str, ...]
    satisfied_plugins: tuple[str, ...]
    missing_plugins: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "pattern_id": self.pattern_id,
            "applicable_count": len(self.applicable_plugins),
            "satisfied_count": len(self.satisfied_plugins),
            "missing_count": len(self.missing_plugins),
            "applicable_plugins": list(self.applicable_plugins),
            "satisfied_plugins": list(self.satisfied_plugins),
            "missing_plugins": list(self.missing_plugins),
        }


@dataclass(frozen=True)
class InteractionPlaybookSectionCoverage:
    """Coverage decision for one OpenAI lessons playbook section."""

    section: str
    coverage_mode: str
    pattern_ids: tuple[str, ...]
    verifier_paths: tuple[str, ...]
    note: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "section": self.section,
            "coverage_mode": self.coverage_mode,
            "pattern_ids": list(self.pattern_ids),
            "verifier_paths": list(self.verifier_paths),
            "note": self.note,
        }


@dataclass(frozen=True)
class InteractionRejectedPattern:
    """One OpenAI-style pattern explicitly rejected for local plugins."""

    pattern_id: str
    playbook_text: str
    local_replacement: str
    guardrail_signals: tuple[str, ...]
    verifier_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "pattern_id": self.pattern_id,
            "playbook_text": self.playbook_text,
            "local_replacement": self.local_replacement,
            "guardrail_signals": list(self.guardrail_signals),
            "verifier_paths": list(self.verifier_paths),
        }


def _require_text(value: object, *, field: str, index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Pattern {index} field {field!r} must be a non-empty string.")
    return value


def _require_text_list(value: object, *, field: str, index: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"Pattern {index} field {field!r} must be a non-empty list.")
    items: list[str] = []
    for item_index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"Pattern {index} field {field!r} item {item_index} must be text."
            )
        items.append(item)
    return tuple(items)


def _optional_text_list(value: object, *, field: str, index: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"Pattern {index} field {field!r} must be a list.")
    items: list[str] = []
    for item_index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"Pattern {index} field {field!r} item {item_index} must be text."
            )
        items.append(item)
    return tuple(items)


def _optional_text_list_allow_empty(
    value: object,
    *,
    field: str,
    index: int,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"Pattern {index} field {field!r} must be a list.")
    items: list[str] = []
    for item_index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"Pattern {index} field {field!r} item {item_index} must be text."
            )
        items.append(item)
    return tuple(items)


def _validate_pattern_signals(
    signals: tuple[str, ...],
    *,
    field: str,
    index: int,
) -> None:
    unknown = sorted(set(signals) - KNOWN_PATTERN_SIGNALS)
    if unknown:
        raise ValueError(
            f"Pattern {index} field {field!r} contains unknown signal(s): "
            + ", ".join(unknown)
        )


def _load_catalog_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0":
        raise ValueError("Interaction pattern catalog schema_version must be '1.0'.")
    return payload


def load_pattern_catalog(path: Path = PATTERN_CATALOG_PATH) -> list[InteractionPattern]:
    """Load the structured OpenAI-derived interaction pattern catalog."""

    payload = _load_catalog_payload(path)
    patterns = payload.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        raise ValueError("Interaction pattern catalog must include patterns[].")

    loaded: list[InteractionPattern] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(patterns, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Pattern {index} must be an object.")
        pattern_id = _require_text(
            item.get("pattern_id"), field="pattern_id", index=index
        )
        if pattern_id in seen_ids:
            raise ValueError(f"Duplicate interaction pattern id: {pattern_id}")
        seen_ids.add(pattern_id)
        evidence_mode = item.get("evidence_mode", "all")
        if evidence_mode not in {"all", "any"}:
            raise ValueError(
                f"Pattern {index} evidence_mode must be either 'all' or 'any'."
            )
        evidence_signals = _require_text_list(
            item.get("evidence_signals"),
            field="evidence_signals",
            index=index,
        )
        applicability_signals = _optional_text_list(
            item.get("applicability_signals", []),
            field="applicability_signals",
            index=index,
        )
        _validate_pattern_signals(
            evidence_signals,
            field="evidence_signals",
            index=index,
        )
        _validate_pattern_signals(
            applicability_signals,
            field="applicability_signals",
            index=index,
        )
        loaded.append(
            InteractionPattern(
                pattern_id=pattern_id,
                source_pattern=_require_text(
                    item.get("source_pattern"),
                    field="source_pattern",
                    index=index,
                ),
                local_rule=_require_text(
                    item.get("local_rule"),
                    field="local_rule",
                    index=index,
                ),
                playbook_section=_require_text(
                    item.get("playbook_section"),
                    field="playbook_section",
                    index=index,
                ),
                evidence_signals=evidence_signals,
                verifier_paths=_require_text_list(
                    item.get("verifier_paths"),
                    field="verifier_paths",
                    index=index,
                ),
                adoption_scope=_require_text(
                    item.get("adoption_scope"),
                    field="adoption_scope",
                    index=index,
                ),
                applicability_signals=applicability_signals,
                evidence_mode=evidence_mode,
            )
        )
    return loaded


def load_playbook_section_coverage(
    path: Path = PATTERN_CATALOG_PATH,
) -> list[InteractionPlaybookSectionCoverage]:
    """Load coverage decisions for the source lessons playbook sections."""

    payload = _load_catalog_payload(path)
    known_pattern_ids = {pattern.pattern_id for pattern in load_pattern_catalog(path)}
    coverage = payload.get("playbook_section_coverage")
    if not isinstance(coverage, list) or not coverage:
        raise ValueError(
            "Interaction pattern catalog must include playbook_section_coverage[]."
        )

    loaded: list[InteractionPlaybookSectionCoverage] = []
    seen_sections: set[str] = set()
    for index, item in enumerate(coverage, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Playbook coverage {index} must be an object.")
        section = _require_text(item.get("section"), field="section", index=index)
        if section in seen_sections:
            raise ValueError(f"Duplicate playbook coverage section: {section}")
        seen_sections.add(section)
        coverage_mode = _require_text(
            item.get("coverage_mode"),
            field="coverage_mode",
            index=index,
        )
        if coverage_mode not in {"catalog_pattern", "contract_guidance"}:
            raise ValueError(
                "Playbook coverage mode must be either 'catalog_pattern' or "
                f"'contract_guidance' for section {section!r}."
            )
        pattern_ids = _optional_text_list_allow_empty(
            item.get("pattern_ids", []),
            field="pattern_ids",
            index=index,
        )
        unknown_patterns = sorted(set(pattern_ids) - known_pattern_ids)
        if unknown_patterns:
            raise ValueError(
                f"Playbook coverage {section!r} references unknown pattern id(s): "
                + ", ".join(unknown_patterns)
            )
        if coverage_mode == "catalog_pattern" and not pattern_ids:
            raise ValueError(f"Playbook coverage {section!r} must list pattern_ids.")
        loaded.append(
            InteractionPlaybookSectionCoverage(
                section=section,
                coverage_mode=coverage_mode,
                pattern_ids=pattern_ids,
                verifier_paths=_require_text_list(
                    item.get("verifier_paths"),
                    field="verifier_paths",
                    index=index,
                ),
                note=_require_text(item.get("note"), field="note", index=index),
            )
        )
    return loaded


def load_rejected_patterns(
    path: Path = PATTERN_CATALOG_PATH,
) -> list[InteractionRejectedPattern]:
    """Load OpenAI-style patterns explicitly rejected for local plugins."""

    payload = _load_catalog_payload(path)
    rejected = payload.get("rejected_patterns")
    if not isinstance(rejected, list) or not rejected:
        raise ValueError(
            "Interaction pattern catalog must include rejected_patterns[]."
        )

    loaded: list[InteractionRejectedPattern] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(rejected, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Rejected pattern {index} must be an object.")
        pattern_id = _require_text(
            item.get("pattern_id"),
            field="pattern_id",
            index=index,
        )
        if pattern_id in seen_ids:
            raise ValueError(f"Duplicate rejected interaction pattern id: {pattern_id}")
        seen_ids.add(pattern_id)
        guardrail_signals = _require_text_list(
            item.get("guardrail_signals"),
            field="guardrail_signals",
            index=index,
        )
        _validate_pattern_signals(
            guardrail_signals,
            field="guardrail_signals",
            index=index,
        )
        loaded.append(
            InteractionRejectedPattern(
                pattern_id=pattern_id,
                playbook_text=_require_text(
                    item.get("playbook_text"),
                    field="playbook_text",
                    index=index,
                ),
                local_replacement=_require_text(
                    item.get("local_replacement"),
                    field="local_replacement",
                    index=index,
                ),
                guardrail_signals=guardrail_signals,
                verifier_paths=_require_text_list(
                    item.get("verifier_paths"),
                    field="verifier_paths",
                    index=index,
                ),
            )
        )
    return loaded


PATTERN_CATALOG: tuple[InteractionPattern, ...] = tuple(load_pattern_catalog())
PLAYBOOK_SECTION_COVERAGE: tuple[InteractionPlaybookSectionCoverage, ...] = tuple(
    load_playbook_section_coverage()
)
REJECTED_PATTERNS: tuple[InteractionRejectedPattern, ...] = tuple(
    load_rejected_patterns()
)


def pattern_catalog() -> list[InteractionPattern]:
    """Return the extracted interaction-pattern catalog."""

    return list(PATTERN_CATALOG)


def playbook_section_coverage() -> list[InteractionPlaybookSectionCoverage]:
    """Return coverage decisions for the source playbook sections."""

    return list(PLAYBOOK_SECTION_COVERAGE)


def rejected_patterns() -> list[InteractionRejectedPattern]:
    """Return the OpenAI-style patterns explicitly rejected for local plugins."""

    return list(REJECTED_PATTERNS)


@dataclass
class PluginInteractionReport:
    """Interaction-pattern audit result for one plugin."""

    plugin: str
    skill_files: list[str] = field(default_factory=list)
    mcp_review_widget: bool = False
    stateful_decision_review: bool = False
    generated_workbench_asset: bool = False
    local_html_review_asset: bool = False
    has_local_browser_writeback: bool = False
    has_review_handoff_contract: bool = False
    has_local_data_posture_language: bool = False
    has_approval_boundary_language: bool = False
    has_no_continue_theater: bool = True
    has_decision_contract_language: bool = False
    issues: list[InteractionIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Return a compact status for dashboards and CI logs."""

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
            "skill_files": self.skill_files,
            "mcp_review_widget": self.mcp_review_widget,
            "stateful_decision_review": self.stateful_decision_review,
            "generated_workbench_asset": self.generated_workbench_asset,
            "local_html_review_asset": self.local_html_review_asset,
            "has_local_browser_writeback": self.has_local_browser_writeback,
            "has_review_handoff_contract": self.has_review_handoff_contract,
            "has_local_data_posture_language": self.has_local_data_posture_language,
            "has_approval_boundary_language": self.has_approval_boundary_language,
            "has_no_continue_theater": self.has_no_continue_theater,
            "has_decision_contract_language": self.has_decision_contract_language,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _discover_plugin_dirs(root: Path) -> list[Path]:
    plugin_root = root / "plugins"
    return sorted(
        path
        for path in plugin_root.iterdir()
        if path.is_dir() and (path / ".codex-plugin" / "plugin.json").exists()
    )


def _combined_skill_text(plugin_dir: Path) -> tuple[list[str], str]:
    skill_files = sorted((plugin_dir / "skills").glob("*/SKILL.md"))
    parts = [_read_text(path) for path in skill_files]
    relative_files = [
        str(path.relative_to(plugin_dir)).replace("\\", "/") for path in skill_files
    ]
    return relative_files, "\n".join(parts)


def _asset_files(plugin_dir: Path) -> list[Path]:
    asset_dir = plugin_dir / "assets"
    if not asset_dir.exists():
        return []
    return sorted(asset_dir.glob("*.html"))


def _asset_texts(plugin_dir: Path) -> list[str]:
    return [_read_text(path) for path in _asset_files(plugin_dir)]


def _mcp_text(plugin_dir: Path) -> str:
    mcp_server = plugin_dir / "mcp" / "server.cjs"
    if not mcp_server.exists():
        return ""
    return _read_text(mcp_server)


def _contains_all(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return all(term.lower() in lowered for term in terms)


def _audit_plugin(plugin_dir: Path) -> PluginInteractionReport:
    skill_files, skill_text = _combined_skill_text(plugin_dir)
    lowered_skill_text = skill_text.lower()
    mcp_text = _mcp_text(plugin_dir)
    lowered_mcp_text = mcp_text.lower()
    asset_files = _asset_files(plugin_dir)
    asset_text = "\n".join(_asset_texts(plugin_dir))
    lowered_asset_text = asset_text.lower()

    report = PluginInteractionReport(plugin=plugin_dir.name, skill_files=skill_files)
    report.mcp_review_widget = (
        "openai/outputtemplate" in lowered_mcp_text
        and "render_" in lowered_mcp_text
        and "review" in lowered_mcp_text
    )
    report.stateful_decision_review = (
        "save_" in lowered_mcp_text
        and "apply_" in lowered_mcp_text
        and "ui_decisions.json" in lowered_mcp_text
    ) or "ui_decisions.json" in lowered_skill_text
    report.generated_workbench_asset = (
        plugin_dir / "assets" / "review-workbench-adapter.json"
    ).exists()
    report.local_html_review_asset = "review-widget" in lowered_asset_text or any(
        "review" in path.name.lower() for path in asset_files
    )
    report.has_local_browser_writeback = (
        report.generated_workbench_asset
        and (plugin_dir / "mcp" / "server.cjs").exists()
        and (
            (plugin_dir / "scripts" / "review_server.py").exists()
            or (ROOT / "scripts" / "serve_review_workbench.py").exists()
        )
    )
    report.has_review_handoff_contract = (
        "review_handoff.md" in lowered_skill_text
        or "artifact_card.md" in lowered_skill_text
        or "review_handoff.md" in lowered_mcp_text
        or "artifact_card.md" in lowered_mcp_text
    )
    report.has_local_data_posture_language = _contains_all(
        skill_text, LOCAL_POSTURE_TERMS
    )
    report.has_approval_boundary_language = _contains_all(
        skill_text, APPROVAL_BOUNDARY_TERMS
    )
    report.has_decision_contract_language = _contains_all(
        skill_text, DECISION_CONTRACT_TERMS
    )

    for phrase in BANNED_CONTINUE_PROMPTS:
        if phrase in lowered_skill_text:
            report.has_no_continue_theater = False
            report.issues.append(
                InteractionIssue(
                    severity="blocker",
                    code="continue_theater",
                    message=(
                        "Skill text asks the user to type continue instead of "
                        "using a material approval boundary."
                    ),
                )
            )
            break

    if not report.has_approval_boundary_language:
        report.issues.append(
            InteractionIssue(
                severity="high",
                code="approval_boundary_missing",
                message=(
                    "Skill text should explain that explicit approval is reserved "
                    "for external, destructive, approval-sensitive, or material steps."
                ),
            )
        )

    if not report.has_local_data_posture_language:
        report.issues.append(
            InteractionIssue(
                severity="medium",
                code="local_deterministic_posture_missing",
                message=(
                    "Skill text should make local data and deterministic-script "
                    "ownership visible when that is part of the workflow."
                ),
            )
        )

    if report.local_html_review_asset and not report.mcp_review_widget:
        report.issues.append(
            InteractionIssue(
                severity="medium",
                code="static_review_without_mcp_widget",
                message=(
                    "A local review HTML asset exists, but no MCP review widget "
                    "template was detected."
                ),
            )
        )

    if report.mcp_review_widget and report.stateful_decision_review:
        if not report.has_decision_contract_language:
            report.issues.append(
                InteractionIssue(
                    severity="high",
                    code="decision_contract_missing_in_skill",
                    message=(
                        "Stateful review plugins should document ui_decisions.json, "
                        "applied_decisions.json, and final_artifacts.json."
                    ),
                )
            )
        if not _contains_all(skill_text, REVIEW_TOOL_TERMS):
            report.issues.append(
                InteractionIssue(
                    severity="medium",
                    code="review_tool_names_missing_in_skill",
                    message=(
                        "Stateful MCP review plugins should name the validate, "
                        "render, save, and apply review tools."
                    ),
                )
            )
        if not report.has_review_handoff_contract:
            report.issues.append(
                InteractionIssue(
                    severity="medium",
                    code="visible_handoff_missing",
                    message=(
                        "Stateful review plugins should document a visible handoff "
                        "card such as review_handoff.md or artifact_card.md."
                    ),
                )
            )

    if report.mcp_review_widget and not report.stateful_decision_review:
        report.issues.append(
            InteractionIssue(
                severity="info",
                code="render_only_review",
                message=(
                    "Review widget appears render-only; that can be fine for charts, "
                    "but row/finding review should persist decisions."
                ),
            )
        )

    if report.stateful_decision_review and not report.generated_workbench_asset:
        report.issues.append(
            InteractionIssue(
                severity="info",
                code="custom_stateful_review_surface",
                message=(
                    "Stateful decision review does not use the shared workbench "
                    "adapter. This is acceptable only when the workflow needs a "
                    "custom local review surface."
                ),
            )
        )

    return report


def audit_plugins(root: Path = ROOT) -> list[PluginInteractionReport]:
    """Audit all repo plugin directories."""

    return [_audit_plugin(plugin_dir) for plugin_dir in _discover_plugin_dirs(root)]


def audit_plugin(plugin_dir: Path) -> PluginInteractionReport:
    """Audit one plugin directory."""

    return _audit_plugin(plugin_dir)


def _report_has_signal(report: PluginInteractionReport, signal: str) -> bool:
    if hasattr(report, signal):
        return bool(getattr(report, signal))
    return any(issue.code == signal for issue in report.issues)


def _pattern_applies(
    pattern: InteractionPattern, report: PluginInteractionReport
) -> bool:
    if not pattern.applicability_signals:
        return True
    return all(
        _report_has_signal(report, signal) for signal in pattern.applicability_signals
    )


def _pattern_is_satisfied(
    pattern: InteractionPattern, report: PluginInteractionReport
) -> bool:
    checks = [_report_has_signal(report, signal) for signal in pattern.evidence_signals]
    if pattern.evidence_mode == "any":
        return any(checks)
    return all(checks)


def pattern_coverage(
    reports: list[PluginInteractionReport],
) -> list[InteractionPatternCoverage]:
    """Return current plugin coverage for every extracted interaction pattern."""

    coverage: list[InteractionPatternCoverage] = []
    for pattern in PATTERN_CATALOG:
        applicable = [
            report.plugin for report in reports if _pattern_applies(pattern, report)
        ]
        satisfied = [
            report.plugin
            for report in reports
            if _pattern_applies(pattern, report)
            and _pattern_is_satisfied(pattern, report)
        ]
        missing = sorted(set(applicable) - set(satisfied))
        coverage.append(
            InteractionPatternCoverage(
                pattern_id=pattern.pattern_id,
                applicable_plugins=tuple(sorted(applicable)),
                satisfied_plugins=tuple(sorted(satisfied)),
                missing_plugins=tuple(missing),
            )
        )
    return coverage


def _summary(reports: list[PluginInteractionReport]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    issue_counts: dict[str, int] = {}
    for report in reports:
        counts[report.status] = counts.get(report.status, 0) + 1
        for issue in report.issues:
            issue_counts[issue.severity] = issue_counts.get(issue.severity, 0) + 1
    return {
        "plugin_count": len(reports),
        "status_counts": dict(sorted(counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
    }


def _markdown_report(reports: list[PluginInteractionReport]) -> str:
    summary = _summary(reports)
    coverage = pattern_coverage(reports)
    lines = [
        "# Plugin Interaction Pattern Audit",
        "",
        f"Plugins audited: {summary['plugin_count']}",
        f"Status counts: `{json.dumps(summary['status_counts'], sort_keys=True)}`",
        f"Issue counts: `{json.dumps(summary['issue_counts'], sort_keys=True)}`",
        "",
        "| Plugin | Status | Review UI | Decision Review | Local Write-Back | Handoff | Issues |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for report in reports:
        issues = ", ".join(f"{issue.severity}:{issue.code}" for issue in report.issues)
        lines.append(
            "| "
            + " | ".join(
                [
                    report.plugin,
                    report.status,
                    "yes" if report.mcp_review_widget else "no",
                    "yes" if report.stateful_decision_review else "no",
                    "yes" if report.has_local_browser_writeback else "no",
                    "yes" if report.has_review_handoff_contract else "no",
                    issues or "none",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Pattern Coverage",
            "",
            "| Pattern | Applicable | Satisfied | Missing Applicable Plugins |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for item in coverage:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.pattern_id,
                    str(len(item.applicable_plugins)),
                    str(len(item.satisfied_plugins)),
                    ", ".join(item.missing_plugins) or "none",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Pattern Catalog",
            "",
            "| Pattern | Playbook Section | Local Rule | Scope | Verifiers |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for pattern in PATTERN_CATALOG:
        lines.append(
            "| "
            + " | ".join(
                [
                    pattern.pattern_id,
                    pattern.playbook_section,
                    pattern.local_rule,
                    pattern.adoption_scope,
                    "<br>".join(pattern.verifier_paths),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Playbook Traceability",
            "",
            "| Playbook Section | Coverage | Patterns | Verifiers | Note |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in PLAYBOOK_SECTION_COVERAGE:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.section,
                    item.coverage_mode,
                    ", ".join(item.pattern_ids) or "none",
                    "<br>".join(item.verifier_paths),
                    item.note,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Rejected Patterns",
            "",
            "| Rejected Pattern | Local Replacement | Guardrail Signals | Verifiers |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in REJECTED_PATTERNS:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.playbook_text,
                    item.local_replacement,
                    ", ".join(item.guardrail_signals),
                    "<br>".join(item.verifier_paths),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _json_report(reports: list[PluginInteractionReport]) -> str:
    payload = {
        "patterns": [pattern.to_dict() for pattern in PATTERN_CATALOG],
        "playbook_section_coverage": [
            item.to_dict() for item in PLAYBOOK_SECTION_COVERAGE
        ],
        "rejected_patterns": [item.to_dict() for item in REJECTED_PATTERNS],
        "pattern_coverage": [item.to_dict() for item in pattern_coverage(reports)],
        "summary": _summary(reports),
        "plugins": [report.to_dict() for report in reports],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit repo plugins for OpenAI-derived interaction patterns."
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "blocker", "high", "medium"),
        default="blocker",
        help="Exit nonzero when any issue at or above this severity is present.",
    )
    return parser.parse_args(argv)


def _should_fail(reports: list[PluginInteractionReport], threshold: str) -> bool:
    if threshold == "none":
        return False
    order = {"info": 0, "medium": 1, "high": 2, "blocker": 3}
    threshold_value = order[threshold]
    return any(
        order.get(issue.severity, 0) >= threshold_value
        for report in reports
        for issue in report.issues
    )


def main(argv: list[str] | None = None) -> int:
    """Run the plugin interaction-pattern audit."""

    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    reports = audit_plugins(ROOT)
    output = (
        _json_report(reports) if args.format == "json" else _markdown_report(reports)
    )
    sys.stdout.write(output)
    return 1 if _should_fail(reports, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
