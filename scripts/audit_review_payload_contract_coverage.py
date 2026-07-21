#!/usr/bin/env python3
"""Audit generated review-payload contract validation coverage.

This is a lightweight coverage check. It does not prove semantic quality of a
customer run. It proves that every generated non-plotting workbench plugin has
at least one test file that references the plugin and calls
``validate_contract(...)`` against generated review-session artifacts.
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
    "CoverageIssue",
    "PluginCoverageReport",
    "audit_contract_coverage",
    "discover_workbench_plugins",
    "main",
]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_ROOTS = (
    ROOT / "tests" / "plugins",
    ROOT / "plugins" / "client-file-preparation" / "tests",
)
SEVERITY_RANK = {
    "info": 1,
    "medium": 2,
    "high": 3,
    "blocker": 4,
}


@dataclass(frozen=True)
class CoverageIssue:
    """One coverage finding."""

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
class PluginCoverageReport:
    """Generated review-payload contract coverage for one plugin."""

    plugin: str
    test_files: tuple[str, ...] = ()
    scenario_files: tuple[str, ...] = ()
    issues: list[CoverageIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Return a compact status."""

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
            "test_files": list(self.test_files),
            "scenario_files": list(self.scenario_files),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _issue(severity: str, code: str, message: str) -> CoverageIssue:
    return CoverageIssue(severity=severity, code=code, message=message)


def discover_workbench_plugins(root: Path = ROOT) -> tuple[str, ...]:
    """Return plugins that ship a generated non-plotting workbench adapter."""

    plugin_root = root / "plugins"
    if not plugin_root.exists():
        return ()
    return tuple(
        sorted(
            path.parents[1].name
            for path in plugin_root.glob("*/assets/review-workbench-adapter.json")
        )
    )


def _test_files(test_roots: tuple[Path, ...]) -> tuple[Path, ...]:
    files: list[Path] = []
    for root in test_roots:
        if root.exists():
            files.extend(sorted(root.rglob("test_*.py")))
    return tuple(dict.fromkeys(files))


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _plugin_owner_signal(plugin: str, *, text: str, test_file: Path) -> bool:
    """Return true when a test file clearly owns assertions for one plugin."""

    underscored = plugin.replace("-", "_")
    if underscored in test_file.stem:
        return True
    patterns = (
        rf'["\']plugin["\']\s*:\s*["\']{re.escape(plugin)}["\']',
        rf'\[["\']plugin["\']\]\s*==\s*["\']{re.escape(plugin)}["\']',
        rf'ROOT\s*/\s*["\']plugins["\']\s*/\s*["\']{re.escape(plugin)}["\']',
        rf'["\']plugins/{re.escape(plugin)}/',
    )
    return any(re.search(pattern, text) for pattern in patterns)


REVIEW_SESSION_ARTIFACTS = (
    "run_intake.json",
    "review_payload.json",
    "ui_decisions.json",
    "final_artifacts.json",
)
WORKFLOW_GENERATION_SIGNALS = (
    "core.inspect_",
    "core.run_",
    "core.build_",
    "core.normalize_",
    "build_file_preparation_outputs(",
    "write_review_session_artifacts(",
    "write_validation_package(",
    "write_validation(",
)


def _workflow_scenario_signal(text: str) -> bool:
    """Return true when a contract test appears to validate generated outputs."""

    return all(name in text for name in REVIEW_SESSION_ARTIFACTS) and any(
        signal in text for signal in WORKFLOW_GENERATION_SIGNALS
    )


def _coverage_files_for_plugin(
    plugin: str,
    *,
    root: Path,
    test_files: tuple[Path, ...],
) -> tuple[tuple[str, bool], ...]:
    matches: list[str] = []
    scenario_matches: list[str] = []
    for test_file in test_files:
        text = test_file.read_text(encoding="utf-8")
        if "validate_contract(" not in text:
            continue
        if not _plugin_owner_signal(plugin, text=text, test_file=test_file):
            continue
        relative_path = _relative(test_file, root)
        matches.append(relative_path)
        if _workflow_scenario_signal(text):
            scenario_matches.append(relative_path)
    return tuple((path, path in scenario_matches) for path in matches)


def audit_contract_coverage(
    root: Path = ROOT,
    *,
    plugins: tuple[str, ...] | None = None,
    test_roots: tuple[Path, ...] = DEFAULT_TEST_ROOTS,
) -> list[PluginCoverageReport]:
    """Return contract-validation coverage for generated workbench plugins."""

    plugin_names = plugins or discover_workbench_plugins(root)
    files = _test_files(test_roots)
    reports: list[PluginCoverageReport] = []
    for plugin in plugin_names:
        coverage_matches = _coverage_files_for_plugin(
            plugin,
            root=root,
            test_files=files,
        )
        coverage_files = tuple(path for path, _scenario in coverage_matches)
        scenario_files = tuple(path for path, scenario in coverage_matches if scenario)
        report = PluginCoverageReport(
            plugin=plugin,
            test_files=coverage_files,
            scenario_files=scenario_files,
        )
        if not coverage_files:
            report.issues.append(
                _issue(
                    "high",
                    "generated_payload_contract_test_missing",
                    (
                        "No test file references this plugin and calls "
                        "validate_contract(...). Add a generated-output test that "
                        "writes run_intake.json, review_payload.json, "
                        "ui_decisions.json, and final_artifacts.json, then validates "
                        "the output directory."
                    ),
                )
            )
        elif not scenario_files:
            report.issues.append(
                _issue(
                    "medium",
                    "generated_payload_workflow_scenario_missing",
                    (
                        "Contract tests reference this plugin, but none appear to "
                        "validate artifacts generated by a workflow-like scenario. "
                        "Add a test that creates representative local inputs, runs "
                        "the plugin workflow, reads run_intake.json, "
                        "review_payload.json, ui_decisions.json, and "
                        "final_artifacts.json, then validates the output directory."
                    ),
                )
            )
        reports.append(report)
    return reports


def _summary(reports: list[PluginCoverageReport]) -> dict[str, Any]:
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


def _markdown_report(reports: list[PluginCoverageReport]) -> str:
    summary = _summary(reports)
    lines = [
        "# Review Payload Contract Coverage Audit",
        "",
        f"Plugins audited: {summary['plugin_count']}",
        f"Status counts: `{json.dumps(summary['status_counts'], sort_keys=True)}`",
        f"Issue counts: `{json.dumps(summary['issue_counts'], sort_keys=True)}`",
        "",
        "| Plugin | Status | Contract Tests | Workflow Scenario Tests | Issues |",
        "| --- | --- | --- | --- | --- |",
    ]
    for report in reports:
        issues = ", ".join(f"{issue.severity}:{issue.code}" for issue in report.issues)
        lines.append(
            "| "
            + " | ".join(
                [
                    report.plugin,
                    report.status,
                    "<br>".join(report.test_files) or "none",
                    "<br>".join(report.scenario_files) or "none",
                    issues or "none",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _json_report(reports: list[PluginCoverageReport]) -> str:
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


def _has_failure(reports: list[PluginCoverageReport], fail_on: str) -> bool:
    threshold = SEVERITY_RANK[fail_on]
    return any(
        SEVERITY_RANK[issue.severity] >= threshold
        for report in reports
        for issue in report.issues
    )


def main(argv: list[str] | None = None) -> int:
    """Run the contract coverage audit CLI."""

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
    test_roots = (
        args.root / "tests" / "plugins",
        args.root / "plugins" / "client-file-preparation" / "tests",
    )
    reports = audit_contract_coverage(args.root, test_roots=test_roots)
    if args.format == "json":
        sys.stdout.write(_json_report(reports))
    else:
        sys.stdout.write(_markdown_report(reports))
    return 1 if _has_failure(reports, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
