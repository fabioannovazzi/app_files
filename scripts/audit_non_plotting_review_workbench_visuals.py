#!/usr/bin/env python3
"""Run a headless-browser smoke audit for non-plotting review workbenches.

This is intentionally not a package gate because it depends on a local browser.
It gives repeatable evidence that the generated HTML widgets load, render their
demo payloads, expose the review task, and avoid obvious viewport overflow at
desktop and mobile sizes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "VisualIssue",
    "VisualPluginReport",
    "VisualViewportReport",
    "audit_workbench_visuals",
    "discover_targets",
    "main",
]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIEWPORTS = {
    "desktop": (1440, 1000),
    "mobile": (390, 844),
}
DEFAULT_LANGUAGES = ("en",)
LANGUAGE_LABELS = {
    "en": ("Save decisions", "Final outputs", "Data posture"),
    "it": ("Salva decisioni", "Output finali", "Postura dati"),
    "fr": ("Enregistrer decisions", "Sorties finales", "Posture donnees"),
    "de": ("Entscheidungen speichern", "Finale Ausgaben", "Datenhaltung"),
}
SEVERITY_RANK = {
    "info": 1,
    "medium": 2,
    "high": 3,
    "blocker": 4,
}
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


@dataclass(frozen=True)
class WorkbenchTarget:
    """One generated workbench HTML file and its adapter config."""

    plugin: str
    adapter_path: Path
    html_path: Path
    item_count: int
    adapter: dict[str, Any]


@dataclass(frozen=True)
class VisualIssue:
    """One runtime or viewport issue."""

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
class VisualViewportReport:
    """Runtime smoke result for one plugin at one viewport."""

    viewport: str
    language: str
    width: int
    height: int
    row_count: int = 0
    decision_count: int = 0
    body_text_length: int = 0
    document_scroll_width: int = 0
    viewport_width: int = 0
    screenshot_path: str | None = None
    issues: list[VisualIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Return a compact status for markdown output."""

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
            "viewport": self.viewport,
            "language": self.language,
            "status": self.status,
            "width": self.width,
            "height": self.height,
            "row_count": self.row_count,
            "decision_count": self.decision_count,
            "body_text_length": self.body_text_length,
            "document_scroll_width": self.document_scroll_width,
            "viewport_width": self.viewport_width,
            "screenshot_path": self.screenshot_path,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class VisualPluginReport:
    """Runtime smoke result for one generated workbench."""

    plugin: str
    html_path: str
    item_count: int
    viewports: list[VisualViewportReport] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Return a compact status for markdown output."""

        statuses = {viewport.status for viewport in self.viewports}
        if "blocker" in statuses:
            return "blocker"
        if "needs_attention" in statuses:
            return "needs_attention"
        if "partial" in statuses:
            return "partial"
        return "ok"

    @property
    def issues(self) -> list[VisualIssue]:
        """Return issues from every viewport."""

        return [issue for viewport in self.viewports for issue in viewport.issues]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "plugin": self.plugin,
            "status": self.status,
            "html_path": self.html_path,
            "item_count": self.item_count,
            "viewports": [viewport.to_dict() for viewport in self.viewports],
        }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _item_count(adapter: dict[str, Any]) -> int:
    demo = adapter.get("demo")
    if not isinstance(demo, dict):
        return 0
    items = demo.get("items")
    if not isinstance(items, list):
        return 0
    return len([item for item in items if isinstance(item, dict)])


def _html_asset_for_adapter(adapter_path: Path) -> Path | None:
    asset_dir = adapter_path.parent
    candidates = sorted(
        path
        for path in asset_dir.glob("*.html")
        if "review" in path.name.lower() or "workbench" in path.name.lower()
    )
    return candidates[0] if candidates else None


def discover_targets(root: Path = ROOT) -> list[WorkbenchTarget]:
    """Return generated non-plotting workbench targets under ``root``."""

    targets: list[WorkbenchTarget] = []
    for adapter_path in sorted(
        (root / "plugins").glob("*/assets/review-workbench-adapter.json")
    ):
        adapter = _read_json(adapter_path)
        plugin = adapter.get("plugin")
        html_path = _html_asset_for_adapter(adapter_path)
        if isinstance(plugin, str) and plugin and html_path is not None:
            targets.append(
                WorkbenchTarget(
                    plugin=plugin,
                    adapter_path=adapter_path,
                    html_path=html_path,
                    item_count=_item_count(adapter),
                    adapter=adapter,
                )
            )
    return targets


def _browser_executable(explicit_path: str | None) -> str | None:
    candidates = [
        explicit_path,
        os.environ.get("WORKBENCH_VISUAL_BROWSER"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("chrome"),
        *CHROME_CANDIDATES,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return None


def _issue(severity: str, code: str, message: str) -> VisualIssue:
    return VisualIssue(severity=severity, code=code, message=message)


def _screenshot_path(
    screenshots_dir: Path | None,
    plugin: str,
    language: str,
    viewport_name: str,
) -> Path | None:
    if screenshots_dir is None:
        return None
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    return screenshots_dir / f"{plugin}-{language}-{viewport_name}.png"


def _localized_payload(target: WorkbenchTarget, language: str) -> dict[str, Any]:
    """Return an MCP-style sample payload for one language."""

    adapter = target.adapter
    demo = adapter.get("demo")
    demo_items = demo.get("items", []) if isinstance(demo, dict) else []
    items = demo_items if isinstance(demo_items, list) else []
    review_type = (
        demo.get("review_type", f"{target.plugin.replace('-', '_')}_review")
        if isinstance(demo, dict)
        else f"{target.plugin.replace('-', '_')}_review"
    )
    widget_type = str(
        adapter.get("widgetType", f"{target.plugin.replace('-', '_')}_review")
    )
    run_id = f"sample-review-{language}"
    return {
        "widget_type": widget_type,
        "run_intake": {
            "schema_version": "1.0",
            "plugin": target.plugin,
            "workflow": target.plugin,
            "run_id": run_id,
            "output_dir": f"/tmp/{target.plugin}/sample",
            "input_paths": ["input.xlsx", "evidence/"],
            "language": language,
            "data_posture": {
                "local_files_read": ["input.xlsx", "evidence/"],
                "model_excerpts_sent": [],
                "external_connectors_used": [],
                "upload_paths_used": [],
                "remote_sql_execution_used": False,
                "hosted_notebook_execution_used": False,
            },
            "execution_trace": [
                {
                    "step_id": f"{target.plugin}_sample_run",
                    "kind": "deterministic_review_session",
                    "status": "passed",
                    "execution_location": "local_codex_workspace",
                    "command": [
                        "python",
                        f"plugins/{target.plugin}/scripts/review_session.py",
                    ],
                    "inputs": ["input.xlsx", "evidence/"],
                    "outputs": [
                        "review_payload.json",
                        "review_summary.md",
                        "evidence_workbook.xlsx",
                        "final_artifacts.json",
                    ],
                }
            ],
            "status": "ready_for_review",
        },
        "review_payload": {
            "schema_version": "1.0",
            "plugin": target.plugin,
            "workflow": target.plugin,
            "run_id": run_id,
            "review_type": review_type,
            "status": "ready_for_review",
            "items": items,
            "item_count": len(items),
            "summary": {
                "language": language,
                "result_row_count": len(items),
                "issue_count": len(
                    [
                        item
                        for item in items
                        if isinstance(item, dict)
                        and item.get("recommended_action") != "accept"
                    ]
                ),
                "artifact_count": 2,
            },
        },
        "ui_decisions": {
            "schema_version": "1.0",
            "plugin": target.plugin,
            "workflow": target.plugin,
            "run_id": run_id,
            "review_payload_path": "review_payload.json",
            "decisions": [],
            "decision_count": 0,
            "status": "pending_review",
        },
        "final_artifacts": {
            "schema_version": "1.0",
            "plugin": target.plugin,
            "workflow": target.plugin,
            "run_id": run_id,
            "outputs": [
                {
                    "path": "review_payload.json",
                    "kind": "json",
                    "status": "written",
                    "row_count": len(items),
                    "records_key": "items",
                    "required_columns": ["id", "item_type", "title"],
                    "qa_checks": ["json_parse", "row_count", "required_columns"],
                },
                {
                    "path": "review_summary.md",
                    "kind": "md",
                    "status": "written",
                    "required_text": [
                        str(adapter.get("reviewTitle", "Review")),
                        "local_codex_workspace",
                        "Sample payload is bounded for review.",
                    ],
                    "qa_checks": ["nonempty_text", "required_text"],
                },
                {
                    "path": "evidence_workbook.xlsx",
                    "kind": "xlsx",
                    "status": "written",
                    "required_sheets": ["summary"],
                    "required_sheet_headers": {
                        "summary": ["item_id", "recommended_action", "status"]
                    },
                    "qa_checks": [
                        "office_zip",
                        "workbook_xml",
                        "required_sheets",
                        "required_sheet_headers",
                    ],
                },
                {
                    "path": "ui_decisions.json",
                    "kind": "json",
                    "status": "pending_review",
                    "records_key": "decisions",
                    "min_rows": 1,
                },
            ],
            "caveats": ["Sample payload is bounded for review."],
            "next_actions": [
                "Save or apply decisions from the widget before treating outputs as final."
            ],
            "status": "written_pending_review",
        },
        "decision_policy": {
            "save_tool": adapter.get("saveTool"),
            "apply_tool": adapter.get("applyTool"),
            "can_persist": False,
            "fallback": "copy_json",
        },
    }


def _evaluate_page(page: Any, language: str) -> dict[str, Any]:
    expected_labels = list(LANGUAGE_LABELS.get(language, LANGUAGE_LABELS["en"]))
    return page.evaluate(
        """(expectedLabels) => {
  const text = document.body.innerText || "";
  const rows = Array.from(document.querySelectorAll("#rows button.row[data-id]"));
  const decisionChoices = Array.from(document.querySelectorAll("#details .decision-choice"));
  const selectors = {
    appTitle: !!document.querySelector("#app-title"),
    details: !!document.querySelector("#details"),
    finalOutputs: !!document.querySelector("#artifact-strip .artifact-header"),
    dataPosture: (document.querySelector("#data-posture")?.innerText || "").trim().length > 40,
    executionProvenance: document.querySelector("#execution-provenance")?.classList.contains("is-visible"),
    safeguards: (document.querySelector("#review-safeguards")?.innerText || "").trim().length > 40,
    emptyPayload: text.includes("No review payload loaded"),
  };
  const missingExpectedLabels = expectedLabels.filter((label) => !text.includes(label));
  const overflowNodes = Array.from(document.querySelectorAll("body *")).flatMap((node) => {
    const rect = node.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) return [];
    if (rect.right <= window.innerWidth + 2 && rect.left >= -2) return [];
    const label = node.id || node.className || node.tagName;
    return [`${node.tagName.toLowerCase()}:${String(label).slice(0, 80)}:${Math.round(rect.left)}:${Math.round(rect.right)}`];
  }).slice(0, 12);
  return {
    textLength: text.trim().length,
    rowCount: rows.length,
    decisionCount: decisionChoices.length,
    selectedRowText: rows[0]?.innerText || "",
    detailTextLength: (document.querySelector("#details")?.innerText || "").trim().length,
    selectors,
    documentScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    viewportWidth: window.innerWidth,
    htmlLang: document.documentElement.lang,
    missingExpectedLabels,
    overflowNodes,
  };
}""",
        expected_labels,
    )


def _run_viewport(
    browser: Any,
    target: WorkbenchTarget,
    viewport_name: str,
    language: str,
    width: int,
    height: int,
    screenshots_dir: Path | None,
    root: Path,
) -> VisualViewportReport:
    report = VisualViewportReport(
        viewport=viewport_name,
        language=language,
        width=width,
        height=height,
    )
    console_errors: list[str] = []
    page_errors: list[str] = []
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.add_init_script(
        "window.openai = { toolOutput: %s };"
        % json.dumps(_localized_payload(target, language), ensure_ascii=True)
    )
    page.on(
        "console",
        lambda message: (
            console_errors.append(message.text) if message.type == "error" else None
        ),
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    try:
        page.goto(target.html_path.resolve().as_uri(), wait_until="load")
        page.locator("#rows button.row[data-id]").first.wait_for(timeout=10_000)
        page.locator("#details .decision-choice").first.wait_for(timeout=10_000)
        result = _evaluate_page(page, language)
        report.row_count = int(result["rowCount"])
        report.decision_count = int(result["decisionCount"])
        report.body_text_length = int(result["textLength"])
        report.document_scroll_width = int(result["documentScrollWidth"])
        report.viewport_width = int(result["viewportWidth"])

        if report.body_text_length < 500:
            report.issues.append(
                _issue(
                    "high",
                    "body_text_too_short",
                    "Rendered workbench body text is unexpectedly short.",
                )
            )
        if report.row_count < target.item_count:
            report.issues.append(
                _issue(
                    "high",
                    "missing_demo_rows",
                    f"Rendered {report.row_count} queue rows for {target.item_count} demo items.",
                )
            )
        if report.decision_count == 0:
            report.issues.append(
                _issue(
                    "high",
                    "missing_decision_controls",
                    "Selected detail panel has no decision controls.",
                )
            )
        if result["htmlLang"] != language:
            report.issues.append(
                _issue(
                    "high",
                    "wrong_document_language",
                    f"Document language is {result['htmlLang']!r}, expected {language!r}.",
                )
            )
        missing_labels = result["missingExpectedLabels"]
        if missing_labels:
            report.issues.append(
                _issue(
                    "high",
                    "localized_labels_missing",
                    "Missing expected localized labels: " + ", ".join(missing_labels),
                )
            )
        selectors = result["selectors"]
        for key, present in selectors.items():
            if key == "emptyPayload":
                if present:
                    report.issues.append(
                        _issue(
                            "high",
                            "demo_payload_not_loaded",
                            "The empty-payload message is still visible after loading the demo.",
                        )
                    )
                continue
            if not present:
                report.issues.append(
                    _issue(
                        "medium",
                        f"missing_{key}",
                        f"Expected visible workbench section {key} is missing.",
                    )
                )
        if int(result["detailTextLength"]) < 80:
            report.issues.append(
                _issue(
                    "medium",
                    "detail_panel_too_thin",
                    "Selected detail panel did not render enough evidence/decision text.",
                )
            )
        overflow_nodes = result["overflowNodes"]
        scroll_width = max(
            int(result["documentScrollWidth"]),
            int(result["bodyScrollWidth"]),
        )
        if scroll_width > width + 2:
            report.issues.append(
                _issue(
                    "high",
                    "horizontal_overflow",
                    "Page has horizontal overflow: "
                    + ", ".join(str(item) for item in overflow_nodes[:5]),
                )
            )
        if console_errors:
            report.issues.append(
                _issue(
                    "high",
                    "console_errors",
                    "; ".join(console_errors[:3]),
                )
            )
        if page_errors:
            report.issues.append(
                _issue(
                    "high",
                    "page_errors",
                    "; ".join(page_errors[:3]),
                )
            )

        screenshot_file = _screenshot_path(
            screenshots_dir,
            target.plugin,
            language,
            viewport_name,
        )
        if screenshot_file is not None:
            page.screenshot(path=str(screenshot_file), full_page=True)
            try:
                report.screenshot_path = str(screenshot_file.relative_to(root))
            except ValueError:
                report.screenshot_path = str(screenshot_file)
    except Exception as exc:  # noqa: BLE001 - surface browser/runtime failures.
        report.issues.append(
            _issue(
                "blocker",
                "browser_runtime_failed",
                str(exc),
            )
        )
    finally:
        context.close()
    return report


def audit_workbench_visuals(
    *,
    root: Path = ROOT,
    screenshots_dir: Path | None = None,
    browser_executable: str | None = None,
    viewports: dict[str, tuple[int, int]] | None = None,
    languages: tuple[str, ...] = DEFAULT_LANGUAGES,
) -> list[VisualPluginReport]:
    """Run the headless browser audit for every generated workbench."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Python Playwright is not installed.") from exc

    executable = _browser_executable(browser_executable)
    viewport_map = viewports or DEFAULT_VIEWPORTS
    language_list = languages or DEFAULT_LANGUAGES
    reports: list[VisualPluginReport] = []
    with sync_playwright() as playwright:
        launch_args = {"headless": True, "args": ["--disable-gpu"]}
        if executable:
            launch_args["executable_path"] = executable
        browser = playwright.chromium.launch(**launch_args)
        try:
            for target in discover_targets(root):
                try:
                    html_path = str(target.html_path.relative_to(root)).replace(
                        "\\", "/"
                    )
                except ValueError:
                    html_path = str(target.html_path)
                plugin_report = VisualPluginReport(
                    plugin=target.plugin,
                    html_path=html_path,
                    item_count=target.item_count,
                )
                for language in language_list:
                    for viewport_name, (width, height) in viewport_map.items():
                        plugin_report.viewports.append(
                            _run_viewport(
                                browser,
                                target,
                                viewport_name,
                                language,
                                width,
                                height,
                                screenshots_dir,
                                root,
                            )
                        )
                reports.append(plugin_report)
        finally:
            browser.close()
    return reports


def _summary(reports: list[VisualPluginReport]) -> dict[str, Any]:
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


def _markdown_report(reports: list[VisualPluginReport]) -> str:
    summary = _summary(reports)
    lines = [
        "# Non-Plotting Workbench Visual Smoke Audit",
        "",
        f"Plugins audited: {summary['plugin_count']}",
        f"Status counts: `{json.dumps(summary['status_counts'], sort_keys=True)}`",
        f"Issue counts: `{json.dumps(summary['issue_counts'], sort_keys=True)}`",
        "",
        "| Plugin | Status | Lang | Viewport | Rows | Decisions | Screenshot | Issues |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for report in reports:
        for viewport in report.viewports:
            issues = ", ".join(
                f"{issue.severity}:{issue.code}" for issue in viewport.issues
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        report.plugin,
                        viewport.status,
                        viewport.language,
                        viewport.viewport,
                        str(viewport.row_count),
                        str(viewport.decision_count),
                        viewport.screenshot_path or "none",
                        issues or "none",
                    ]
                )
                + " |"
            )
    return "\n".join(lines) + "\n"


def _json_report(reports: list[VisualPluginReport]) -> str:
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


def _has_failure(reports: list[VisualPluginReport], fail_on: str) -> bool:
    threshold = SEVERITY_RANK[fail_on]
    return any(
        SEVERITY_RANK[issue.severity] >= threshold
        for report in reports
        for issue in report.issues
    )


def _parse_languages(value: str) -> tuple[str, ...]:
    languages = tuple(
        language.strip().lower() for language in value.split(",") if language.strip()
    )
    if not languages:
        raise argparse.ArgumentTypeError("At least one language is required.")
    unsupported = sorted(set(languages) - set(LANGUAGE_LABELS))
    if unsupported:
        raise argparse.ArgumentTypeError(
            "Unsupported language(s): " + ", ".join(unsupported)
        )
    return languages


def main(argv: list[str] | None = None) -> int:
    """Run the visual smoke audit CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--screenshots-dir", type=Path)
    parser.add_argument("--browser-executable")
    parser.add_argument(
        "--languages",
        type=_parse_languages,
        default=DEFAULT_LANGUAGES,
        help="Comma-separated UI languages to smoke test. Supported: en,it,fr,de.",
    )
    parser.add_argument(
        "--fail-on",
        choices=("blocker", "high", "medium", "info"),
        default="high",
    )
    args = parser.parse_args(argv)

    reports = audit_workbench_visuals(
        root=args.root,
        screenshots_dir=args.screenshots_dir,
        browser_executable=args.browser_executable,
        languages=args.languages,
    )
    if args.format == "json":
        sys.stdout.write(_json_report(reports))
    else:
        sys.stdout.write(_markdown_report(reports))
    return 1 if _has_failure(reports, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
