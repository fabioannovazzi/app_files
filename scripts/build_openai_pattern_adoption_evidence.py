#!/usr/bin/env python3
"""Build a persisted evidence bundle for OpenAI-pattern plugin adoption.

The bundle keeps fixture/mechanism evidence separate from real customer-folder
validation while giving reviewers one folder to inspect.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import shlex
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "build_evidence_bundle",
    "main",
]

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
DEFAULT_OUTPUT_DIR = Path("/private/tmp/openai-pattern-adoption-evidence")


def _load_script(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_asset_name(value: str) -> str:
    chars = [char if char.isalnum() or char in {"-", "_"} else "-" for char in value]
    name = "".join(chars).strip("-")
    return name or "plugin"


def _status_by_tier(readiness_payload: dict[str, Any]) -> dict[str, str]:
    return {
        str(item["tier"]): str(item["status"])
        for item in readiness_payload.get("validation_tiers", [])
        if isinstance(item, dict) and "tier" in item and "status" in item
    }


def _readme_text(bundle_manifest: dict[str, Any]) -> str:
    tiers = bundle_manifest["validation_tiers"]
    artifacts = bundle_manifest["artifacts"]
    commands = bundle_manifest.get("commands", {})
    lines = [
        "# OpenAI-Pattern Adoption Evidence",
        "",
        f"Generated at: `{bundle_manifest['generated_at']}`",
        f"Repo root: `{bundle_manifest['root']}`",
        "",
        "## Validation Tiers",
        "",
        "| Tier | Status |",
        "| --- | --- |",
    ]
    for tier, status in tiers.items():
        lines.append(f"| {tier} | {status} |")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "| Artifact | Path |",
            "| --- | --- |",
        ]
    )
    for name, path in artifacts.items():
        lines.append(f"| {name} | `{path}` |")
    lines.extend(
        [
            "",
            "## Commands",
            "",
        ]
    )
    for name, command in commands.items():
        if isinstance(command, list):
            lines.extend(
                [
                    f"### {name}",
                    "",
                    "```bash",
                    shlex.join(str(part) for part in command),
                    "```",
                    "",
                ]
            )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Browser write-back evidence is fixture/mechanism evidence.",
            "- Real customer-folder validation remains separate and must be recorded with representative local runs.",
            "- The local model stays local-data and deterministic-script first; this bundle tracks selectively adopted interaction patterns.",
            "",
            "## Next Actions",
            "",
        ]
    )
    next_actions = bundle_manifest.get("next_actions", [])
    if not next_actions:
        lines.append("- None.")
    for action in next_actions:
        lines.append(
            "- "
            + str(action.get("id", "unknown"))
            + ": "
            + str(action.get("description", ""))
        )
    return "\n".join(lines) + "\n"


def _load_json_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _copy_browser_screenshot(
    *,
    source_value: object,
    plugin: str,
    output_dir: Path,
) -> str | None:
    if not isinstance(source_value, str) or not source_value.strip():
        return None
    source_path = Path(source_value).expanduser()
    if not source_path.exists() or not source_path.is_file():
        return None
    suffix = source_path.suffix if source_path.suffix else ".png"
    screenshot_dir = output_dir / "browser_writeback_gallery_assets"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    target_path = screenshot_dir / f"{_safe_asset_name(plugin)}{suffix}"
    shutil.copy2(source_path, target_path)
    return target_path.relative_to(output_dir).as_posix()


def _browser_writeback_gallery_payload(
    *,
    browser_report_path: Path | None,
    output_dir: Path,
) -> dict[str, Any]:
    if browser_report_path is None:
        return {
            "schema_version": "1.0",
            "source_report": None,
            "summary": {
                "plugin_count": 0,
                "status_counts": {},
                "issue_counts": {},
            },
            "reports": [],
        }

    payload = _load_json_payload(browser_report_path)
    reports = []
    for report in payload.get("reports", []):
        if not isinstance(report, dict):
            continue
        plugin = str(report.get("plugin") or "unknown-plugin")
        reports.append(
            {
                "plugin": plugin,
                "status": str(report.get("status") or "unknown"),
                "row_count": report.get("row_count"),
                "decision_control_count": report.get("decision_control_count"),
                "final_status": report.get("final_status"),
                "target_artifact": report.get("target_artifact"),
                "csv_contains_edit": report.get("csv_contains_edit"),
                "ui_decision_source": report.get("ui_decision_source"),
                "applied_decision_source": report.get("applied_decision_source"),
                "issues": (
                    report.get("issues")
                    if isinstance(report.get("issues"), list)
                    else []
                ),
                "source_screenshot_path": report.get("screenshot_path"),
                "screenshot_asset": _copy_browser_screenshot(
                    source_value=report.get("screenshot_path"),
                    plugin=plugin,
                    output_dir=output_dir,
                ),
            }
        )

    return {
        "schema_version": "1.0",
        "source_report": browser_report_path.as_posix(),
        "summary": (
            payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        ),
        "reports": sorted(reports, key=lambda item: item["plugin"]),
    }


def _browser_writeback_gallery_html(payload: dict[str, Any]) -> str:
    reports = payload.get("reports") if isinstance(payload.get("reports"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    source_report = payload.get("source_report")
    status_counts = html.escape(
        json.dumps(summary.get("status_counts", {}), sort_keys=True)
    )
    issue_counts = html.escape(
        json.dumps(summary.get("issue_counts", {}), sort_keys=True)
    )
    source_text = (
        html.escape(str(source_report))
        if source_report
        else "No browser write-back report supplied."
    )
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Browser Write-Back UI Gallery</title>",
        "<style>",
        ":root { color-scheme: light; --ink: #1f2a24; --muted: #66736c; --line: #dbe2dd; --soft: #f6f8f6; --ok: #2f7d4f; --warn: #9a5f15; --bad: #a33b36; }",
        "body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #ffffff; color: var(--ink); }",
        "main { max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }",
        "header { border-bottom: 1px solid var(--line); padding-bottom: 18px; margin-bottom: 22px; }",
        "h1 { margin: 0 0 8px; font-size: 1.75rem; line-height: 1.2; font-weight: 720; }",
        "p { margin: 0; color: var(--muted); line-height: 1.5; }",
        ".meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }",
        ".chip { border: 1px solid var(--line); background: var(--soft); border-radius: 999px; padding: 6px 10px; font-size: 0.82rem; color: var(--ink); }",
        ".grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }",
        ".card { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #fff; }",
        ".card-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; padding: 14px 16px; border-bottom: 1px solid var(--line); background: #fbfcfb; }",
        "h2 { margin: 0; font-size: 1rem; line-height: 1.25; }",
        ".status { border-radius: 999px; padding: 4px 8px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0; }",
        ".status-ok { color: var(--ok); background: #eaf5ee; }",
        ".status-partial, .status-unknown { color: var(--warn); background: #fff4df; }",
        ".status-blocker, .status-needs_attention, .status-failed { color: var(--bad); background: #fae9e7; }",
        ".shot-link { display: block; border-bottom: 1px solid var(--line); background: #f4f6f4; }",
        ".shot { display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: cover; object-position: top center; background: #f4f6f4; }",
        ".no-shot { display: grid; place-items: center; min-height: 210px; color: var(--muted); background: #f4f6f4; border-bottom: 1px solid var(--line); padding: 20px; text-align: center; }",
        ".facts { display: grid; grid-template-columns: minmax(110px, max-content) 1fr; gap: 7px 12px; padding: 14px 16px 16px; font-size: 0.9rem; }",
        ".facts dt { color: var(--muted); }",
        ".facts dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }",
        ".empty { border: 1px dashed var(--line); border-radius: 8px; padding: 28px; background: var(--soft); }",
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        "<header>",
        "<h1>Browser Write-Back UI Gallery</h1>",
        "<p>Fixture/mechanism evidence for generated non-plotting review surfaces. This gallery shows whether the local browser bridge can save/apply decisions and update declared target artifacts; it is not real customer-folder validation.</p>",
        '<div class="meta">',
        f'<span class="chip">Source: {source_text}</span>',
        f'<span class="chip">Plugins: {html.escape(str(summary.get("plugin_count", len(reports))))}</span>',
        f'<span class="chip">Status counts: {status_counts}</span>',
        f'<span class="chip">Issue counts: {issue_counts}</span>',
        "</div>",
        "</header>",
    ]
    if not reports:
        lines.extend(
            [
                '<section class="empty">',
                "<p>No browser write-back report was supplied. Generate one with the command in this bundle README, then rebuild the evidence bundle.</p>",
                "</section>",
            ]
        )
    else:
        lines.append('<section class="grid">')
        for report in reports:
            plugin = html.escape(str(report.get("plugin") or "unknown-plugin"))
            status = str(report.get("status") or "unknown")
            status_class = "status-" + _safe_asset_name(status).lower()
            screenshot_asset = report.get("screenshot_asset")
            lines.extend(
                [
                    '<article class="card">',
                    '<div class="card-head">',
                    f"<h2>{plugin}</h2>",
                    f'<span class="status {html.escape(status_class)}">{html.escape(status)}</span>',
                    "</div>",
                ]
            )
            if isinstance(screenshot_asset, str) and screenshot_asset:
                escaped_asset = html.escape(screenshot_asset)
                lines.append(f'<a class="shot-link" href="{escaped_asset}">')
                lines.append(
                    f'<img class="shot" src="{escaped_asset}" alt="{plugin} review UI screenshot">'
                )
                lines.append("</a>")
            else:
                lines.append(
                    '<div class="no-shot">No screenshot copied for this report.</div>'
                )
            facts = [
                ("Rows", report.get("row_count")),
                ("Decision controls", report.get("decision_control_count")),
                ("Final status", report.get("final_status")),
                ("Target artifact", report.get("target_artifact")),
                ("Edit persisted", report.get("csv_contains_edit")),
                ("UI decision source", report.get("ui_decision_source")),
                ("Applied source", report.get("applied_decision_source")),
            ]
            lines.append('<dl class="facts">')
            for label, value in facts:
                lines.append(f"<dt>{html.escape(label)}</dt>")
                lines.append(
                    f"<dd>{html.escape(str(value if value is not None else 'n/a'))}</dd>"
                )
            issues = (
                report.get("issues") if isinstance(report.get("issues"), list) else []
            )
            lines.append("<dt>Issues</dt>")
            lines.append(
                f"<dd>{html.escape(', '.join(str(issue) for issue in issues) if issues else 'none')}</dd>"
            )
            lines.append("</dl>")
            lines.append("</article>")
        lines.append("</section>")
    lines.extend(["</main>", "</body>", "</html>"])
    return "\n".join(lines) + "\n"


def _browser_writeback_command(output_dir: Path) -> list[str]:
    return [
        ".venv/bin/python",
        "scripts/audit_local_review_workbench_writeback.py",
        "--plugin",
        "all",
        "--format",
        "json",
        "--report-path",
        (output_dir / "browser_writeback.json").as_posix(),
        "--output-dir",
        (output_dir / "browser-writeback-runs").as_posix(),
        "--screenshots-dir",
        (output_dir / "browser-writeback-screenshots").as_posix(),
        "--fail-on",
        "medium",
    ]


def _build_bundle_command(
    *,
    output_dir: Path,
    browser_writeback_report_path: Path | None,
    customer_manifest_path: Path | None,
    expected_customer_plugins: tuple[str, ...] | None,
    require_browser_writeback: bool,
    verify_browser_writeback_screenshots: bool,
    require_customer_validation: bool,
    verify_customer_artifact_paths: bool,
    require_complete_objective: bool,
) -> list[str]:
    command = [
        ".venv/bin/python",
        "scripts/build_openai_pattern_adoption_evidence.py",
        "--output-dir",
        output_dir.as_posix(),
    ]
    if browser_writeback_report_path is not None:
        command.extend(
            ["--browser-writeback-report", browser_writeback_report_path.as_posix()]
        )
    if customer_manifest_path is not None:
        command.extend(
            ["--customer-validation-manifest", customer_manifest_path.as_posix()]
        )
    for plugin in expected_customer_plugins or ():
        command.extend(["--expected-customer-plugin", plugin])
    if require_browser_writeback:
        command.append("--require-browser-writeback")
    if verify_browser_writeback_screenshots:
        command.append("--verify-browser-writeback-screenshots")
    if require_customer_validation:
        command.append("--require-customer-validation")
    if verify_customer_artifact_paths:
        command.append("--verify-customer-validation-artifacts")
    if require_complete_objective:
        command.append("--require-complete-objective")
    command.extend(["--fail-on", "medium"])
    return command


def _strict_customer_gate_command(
    customer_manifest_path: Path | None,
    expected_customer_plugins: tuple[str, ...] | None,
) -> list[str]:
    command = [
        ".venv/bin/python",
        "scripts/audit_openai_pattern_adoption_readiness.py",
        "--format",
        "markdown",
        "--require-customer-validation",
        "--verify-customer-validation-artifacts",
    ]
    if customer_manifest_path is not None:
        command.extend(
            ["--customer-validation-manifest", customer_manifest_path.as_posix()]
        )
    for plugin in expected_customer_plugins or ():
        command.extend(["--expected-customer-plugin", plugin])
    command.extend(["--fail-on", "medium"])
    return command


def _customer_validation_case_command(
    *,
    plugin: str,
    case_id: str,
    mode_flag: str,
) -> list[str]:
    return [
        ".venv/bin/python",
        "scripts/audit_openai_pattern_adoption_readiness.py",
        mode_flag,
        "--case-id",
        case_id,
        "--plugin",
        plugin,
        "--scenario-name",
        "Representative customer case",
        "--input-path-or-case-id",
        f"anonymized/{plugin}/001",
        "--language",
        "it",
        "--reviewer",
        "Reviewer Name",
        "--run-output-dir",
        "/path/to/workflow/output",
        "--screenshot-path",
        "/path/to/review-ui.png",
        "--validation-status",
        "pass",
        "--ux-verdict",
        "usable",
        "--ux-check",
        "queue_clear",
        "--ux-check",
        "evidence_comparison_clear",
        "--ux-check",
        "decision_controls_complete",
        "--ux-check",
        "edit_flow_usable",
        "--ux-check",
        "artifact_handoff_clear",
        "--ux-check",
        "no_blocking_issues",
        "--reviewer-notes",
        "Queue, evidence, decisions, edit flow, and artifact handoff were usable.",
        "--validation-command",
        "ran workflow from local customer input",
        "--validation-command",
        "opened review UI and applied decisions",
    ]


def _customer_validation_plan_text(readiness_payload: dict[str, Any]) -> str:
    customer_validation = readiness_payload["customer_validation"]
    missing_plugins = customer_validation.get("missing_expected_plugins", [])
    expected_plugins = customer_validation.get("expected_plugins", [])
    plugins = missing_plugins or expected_plugins
    lines = [
        "# Real Customer Validation Plan",
        "",
        "This is not validation evidence. It is the work plan for collecting real local customer-folder cases.",
        "",
        "## Required Evidence Per Plugin",
        "",
        "- real `run_intake.json`, `review_payload.json`, `ui_decisions.json`, `applied_decisions.json`, and `final_artifacts.json`",
        "- at least one non-empty screenshot showing queue, detail, and decision state",
        "- native output readback, or `not_applicable` only when there is no native output",
        "- `ux_verdict usable` and all required UX checks",
        "- non-empty reviewer notes",
        "",
        "The commands below keep metadata explicit for traceability. When a real run's `run_intake.json` and `review_payload.json` contain workflow metadata, add `--infer-case-metadata-from-run` and omit only `--plugin`, `--scenario-name`, and `--language`. Case id, input case, reviewer, screenshots, UX checks, and reviewer notes remain explicit evidence.",
        "",
        "## Missing Or Expected Cases",
        "",
    ]
    if not plugins:
        lines.append("- No expected customer-validation plugins were reported.")
    for plugin in plugins:
        case_id = f"case-{plugin}-001"
        lines.extend(
            [
                f"### {plugin}",
                "",
                "Preflight without writing the manifest:",
                "",
                "```bash",
                ".venv/bin/python scripts/audit_openai_pattern_adoption_readiness.py \\",
                "  --preflight-customer-validation-case \\",
                f"  --case-id {case_id} \\",
                f"  --plugin {plugin} \\",
                '  --scenario-name "Representative customer case" \\',
                f'  --input-path-or-case-id "anonymized/{plugin}/001" \\',
                "  --language it \\",
                '  --reviewer "Reviewer Name" \\',
                "  --run-output-dir /path/to/workflow/output \\",
                "  --screenshot-path /path/to/review-ui.png \\",
                "  --validation-status pass \\",
                "  --ux-verdict usable \\",
                "  --ux-check queue_clear \\",
                "  --ux-check evidence_comparison_clear \\",
                "  --ux-check decision_controls_complete \\",
                "  --ux-check edit_flow_usable \\",
                "  --ux-check artifact_handoff_clear \\",
                "  --ux-check no_blocking_issues \\",
                '  --reviewer-notes "Queue, evidence, decisions, edit flow, and artifact handoff were usable." \\',
                '  --validation-command "ran workflow from local customer input" \\',
                '  --validation-command "opened review UI and applied decisions"',
                "```",
                "",
                "Record after preflight passes:",
                "",
                "```bash",
                ".venv/bin/python scripts/audit_openai_pattern_adoption_readiness.py \\",
                "  --record-customer-validation-case \\",
                f"  --case-id {case_id} \\",
                f"  --plugin {plugin} \\",
                '  --scenario-name "Representative customer case" \\',
                f'  --input-path-or-case-id "anonymized/{plugin}/001" \\',
                "  --language it \\",
                '  --reviewer "Reviewer Name" \\',
                "  --run-output-dir /path/to/workflow/output \\",
                "  --screenshot-path /path/to/review-ui.png \\",
                "  --validation-status pass \\",
                "  --ux-verdict usable \\",
                "  --ux-check queue_clear \\",
                "  --ux-check evidence_comparison_clear \\",
                "  --ux-check decision_controls_complete \\",
                "  --ux-check edit_flow_usable \\",
                "  --ux-check artifact_handoff_clear \\",
                "  --ux-check no_blocking_issues \\",
                '  --reviewer-notes "Queue, evidence, decisions, edit flow, and artifact handoff were usable." \\',
                '  --validation-command "ran workflow from local customer input" \\',
                '  --validation-command "opened review UI and applied decisions"',
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Strict Gate",
            "",
            "Run after the manifest has real cases:",
            "",
            "```bash",
            ".venv/bin/python scripts/audit_openai_pattern_adoption_readiness.py \\",
            "  --format markdown \\",
            "  --require-customer-validation \\",
            "  --verify-customer-validation-artifacts \\",
            "  --fail-on medium",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def _customer_validation_plan_payload(
    readiness_payload: dict[str, Any],
) -> dict[str, Any]:
    customer_validation = readiness_payload["customer_validation"]
    expected_plugins = list(customer_validation.get("expected_plugins", []))
    covered_plugins = set(customer_validation.get("covered_plugins", []))
    missing_plugins = set(customer_validation.get("missing_expected_plugins", []))
    planned_plugins = expected_plugins or sorted(covered_plugins | missing_plugins)
    cases: list[dict[str, Any]] = []
    for plugin in planned_plugins:
        case_id = f"case-{plugin}-001"
        case_status = (
            "covered" if plugin in covered_plugins else "needs_real_customer_case"
        )
        preflight_command = _customer_validation_case_command(
            plugin=plugin,
            case_id=case_id,
            mode_flag="--preflight-customer-validation-case",
        )
        record_command = _customer_validation_case_command(
            plugin=plugin,
            case_id=case_id,
            mode_flag="--record-customer-validation-case",
        )
        cases.append(
            {
                "plugin": plugin,
                "case_id": case_id,
                "status": case_status,
                "scenario_name": "Representative customer case",
                "input_path_or_case_id": f"anonymized/{plugin}/001",
                "language": "it",
                "required_artifacts": [
                    "run_intake.json",
                    "review_payload.json",
                    "ui_decisions.json",
                    "applied_decisions.json",
                    "final_artifacts.json",
                    "review UI screenshot",
                    "native output readback or not_applicable",
                ],
                "required_ux_checks": [
                    "queue_clear",
                    "evidence_comparison_clear",
                    "decision_controls_complete",
                    "edit_flow_usable",
                    "artifact_handoff_clear",
                    "no_blocking_issues",
                ],
                "preflight_command": preflight_command,
                "record_command": record_command,
            }
        )
    return {
        "schema_version": "1.0",
        "status": customer_validation["status"],
        "expected_plugins": expected_plugins,
        "covered_plugins": list(customer_validation.get("covered_plugins", [])),
        "missing_expected_plugins": list(
            customer_validation.get("missing_expected_plugins", [])
        ),
        "metadata_inference": {
            "flag": "--infer-case-metadata-from-run",
            "inferable_fields": ["plugin", "scenario_name", "language"],
            "still_required": [
                "case_id",
                "input_path_or_case_id",
                "reviewer",
                "screenshot_paths",
                "ux_verdict",
                "ux_checks",
                "reviewer_notes",
            ],
        },
        "cases": cases,
        "strict_gate_command": [
            ".venv/bin/python",
            "scripts/audit_openai_pattern_adoption_readiness.py",
            "--format",
            "markdown",
            "--require-customer-validation",
            "--verify-customer-validation-artifacts",
            "--fail-on",
            "medium",
        ],
    }


def _html_list(items: list[Any]) -> str:
    if not items:
        return "<p>None.</p>"
    lines = ["<ul>"]
    for item in items:
        lines.append(f"<li>{html.escape(str(item))}</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def _customer_validation_checklist_html(plan_payload: dict[str, Any]) -> str:
    cases = (
        plan_payload.get("cases") if isinstance(plan_payload.get("cases"), list) else []
    )
    expected_plugins = plan_payload.get("expected_plugins")
    covered_plugins = plan_payload.get("covered_plugins")
    missing_plugins = plan_payload.get("missing_expected_plugins")
    metadata = (
        plan_payload.get("metadata_inference")
        if isinstance(plan_payload.get("metadata_inference"), dict)
        else {}
    )
    strict_gate = plan_payload.get("strict_gate_command")
    strict_gate_text = (
        shlex.join(str(part) for part in strict_gate)
        if isinstance(strict_gate, list)
        else "not available"
    )
    expected_count = len(expected_plugins) if isinstance(expected_plugins, list) else 0
    covered_count = len(covered_plugins) if isinstance(covered_plugins, list) else 0
    missing_count = len(missing_plugins) if isinstance(missing_plugins, list) else 0
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Real Customer Validation Checklist</title>",
        "<style>",
        ":root { color-scheme: light; --ink: #1f2a24; --muted: #66736c; --line: #dbe2dd; --soft: #f6f8f6; --ok: #2f7d4f; --warn: #9a5f15; --bad: #a33b36; --code: #f3f5f3; }",
        "body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #ffffff; color: var(--ink); }",
        "main { max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }",
        "header { border-bottom: 1px solid var(--line); padding-bottom: 18px; margin-bottom: 22px; }",
        "h1 { margin: 0 0 8px; font-size: 1.75rem; line-height: 1.2; font-weight: 720; }",
        "h2 { margin: 0; font-size: 1rem; line-height: 1.25; }",
        "h3 { margin: 0 0 8px; font-size: 0.95rem; line-height: 1.25; }",
        "p { margin: 0; color: var(--muted); line-height: 1.5; }",
        ".meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }",
        ".chip { border: 1px solid var(--line); background: var(--soft); border-radius: 999px; padding: 6px 10px; font-size: 0.82rem; color: var(--ink); }",
        ".panel { border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #fff; }",
        ".grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; }",
        ".case { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #fff; }",
        ".case-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; padding: 14px 16px; border-bottom: 1px solid var(--line); background: #fbfcfb; }",
        ".case-body { padding: 14px 16px 16px; }",
        ".status { border-radius: 999px; padding: 4px 8px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0; white-space: nowrap; }",
        ".status-covered { color: var(--ok); background: #eaf5ee; }",
        ".status-needs_real_customer_case, .status-not_assessed { color: var(--warn); background: #fff4df; }",
        ".facts { display: grid; grid-template-columns: minmax(120px, max-content) 1fr; gap: 7px 12px; margin: 0 0 14px; font-size: 0.9rem; }",
        ".facts dt { color: var(--muted); }",
        ".facts dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }",
        "ul { margin: 8px 0 14px 18px; padding: 0; color: var(--ink); line-height: 1.45; }",
        "li { margin: 3px 0; }",
        "pre { margin: 8px 0 14px; padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--code); overflow: auto; font-size: 0.78rem; line-height: 1.45; }",
        "code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace; }",
        ".empty { border: 1px dashed var(--line); border-radius: 8px; padding: 28px; background: var(--soft); }",
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        "<header>",
        "<h1>Real Customer Validation Checklist</h1>",
        "<p>This checklist is not validation evidence. It is the reviewer-facing collection surface for proving that generated non-plotting review UIs work on real local customer folders.</p>",
        '<div class="meta">',
        f'<span class="chip">Status: {html.escape(str(plan_payload.get("status", "unknown")))}</span>',
        f'<span class="chip">Expected plugins: {expected_count}</span>',
        f'<span class="chip">Covered: {covered_count}</span>',
        f'<span class="chip">Missing: {missing_count}</span>',
        "</div>",
        "</header>",
        '<section class="panel">',
        "<h2>Metadata Inference</h2>",
        f'<p>Optional flag: <code>{html.escape(str(metadata.get("flag", "--infer-case-metadata-from-run")))}</code>. Infer only the fields listed below from run artifacts; keep reviewer evidence explicit.</p>',
        '<dl class="facts">',
        "<dt>Inferable</dt>",
        f"<dd>{html.escape(', '.join(str(item) for item in metadata.get('inferable_fields', [])) or 'none')}</dd>",
        "<dt>Still required</dt>",
        f"<dd>{html.escape(', '.join(str(item) for item in metadata.get('still_required', [])) or 'none')}</dd>",
        "</dl>",
        "</section>",
    ]
    if not cases:
        lines.extend(
            [
                '<section class="empty">',
                "<p>No expected customer-validation plugins were reported.</p>",
                "</section>",
            ]
        )
    else:
        lines.append('<section class="grid">')
        for case in cases:
            if not isinstance(case, dict):
                continue
            plugin = html.escape(str(case.get("plugin", "unknown-plugin")))
            status = str(case.get("status", "unknown"))
            status_class = "status-" + _safe_asset_name(status).lower()
            preflight_command = case.get("preflight_command")
            record_command = case.get("record_command")
            preflight_text = (
                shlex.join(str(part) for part in preflight_command)
                if isinstance(preflight_command, list)
                else "not available"
            )
            record_text = (
                shlex.join(str(part) for part in record_command)
                if isinstance(record_command, list)
                else "not available"
            )
            lines.extend(
                [
                    '<article class="case">',
                    '<div class="case-head">',
                    f"<h2>{plugin}</h2>",
                    f'<span class="status {html.escape(status_class)}">{html.escape(status)}</span>',
                    "</div>",
                    '<div class="case-body">',
                    '<dl class="facts">',
                    "<dt>Case id</dt>",
                    f"<dd>{html.escape(str(case.get('case_id', 'n/a')))}</dd>",
                    "<dt>Scenario</dt>",
                    f"<dd>{html.escape(str(case.get('scenario_name', 'n/a')))}</dd>",
                    "<dt>Input</dt>",
                    f"<dd>{html.escape(str(case.get('input_path_or_case_id', 'n/a')))}</dd>",
                    "<dt>Language</dt>",
                    f"<dd>{html.escape(str(case.get('language', 'n/a')))}</dd>",
                    "</dl>",
                    "<h3>Required Artifacts</h3>",
                    _html_list(
                        case.get("required_artifacts")
                        if isinstance(case.get("required_artifacts"), list)
                        else []
                    ),
                    "<h3>Required UX Checks</h3>",
                    _html_list(
                        case.get("required_ux_checks")
                        if isinstance(case.get("required_ux_checks"), list)
                        else []
                    ),
                    "<h3>Preflight</h3>",
                    f"<pre><code>{html.escape(preflight_text)}</code></pre>",
                    "<h3>Record</h3>",
                    f"<pre><code>{html.escape(record_text)}</code></pre>",
                    "</div>",
                    "</article>",
                ]
            )
        lines.append("</section>")
    lines.extend(
        [
            '<section class="panel">',
            "<h2>Strict Gate</h2>",
            "<p>Run this only after representative real cases have been recorded.</p>",
            f"<pre><code>{html.escape(strict_gate_text)}</code></pre>",
            "</section>",
            "</main>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(lines) + "\n"


def _pattern_coverage_status(
    readiness_payload: dict[str, Any],
    pattern_id: str,
) -> str:
    for item in readiness_payload.get("pattern_coverage", []):
        if isinstance(item, dict) and item.get("pattern_id") == pattern_id:
            return "covered" if item.get("missing_count") == 0 else "partial"
    return "not_assessed"


def _completion_requirement(
    *,
    requirement_id: str,
    description: str,
    status: str,
    evidence: list[str],
    remaining_gap: str,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement_id,
        "description": description,
        "status": status,
        "evidence": evidence,
        "remaining_gap": remaining_gap,
    }


def _completion_assessment_payload(
    readiness_payload: dict[str, Any],
    artifacts: dict[str, str],
) -> dict[str, Any]:
    tiers = _status_by_tier(readiness_payload)
    rejected_ids = {
        item.get("pattern_id")
        for item in readiness_payload.get("rejected_patterns", [])
        if isinstance(item, dict)
    }
    local_boundary_status = _pattern_coverage_status(
        readiness_payload,
        "local_deterministic_boundary",
    )
    requirements = [
        _completion_requirement(
            requirement_id="extract_openai_best_practices",
            description=(
                "OpenAI-derived interaction lessons are captured as a local "
                "playbook, pattern catalog, traceability table, and rejected "
                "pattern list."
            ),
            status=(
                "covered"
                if readiness_payload.get("patterns")
                and readiness_payload.get("playbook_section_coverage")
                and readiness_payload.get("rejected_patterns")
                else "partial"
            ),
            evidence=[
                artifacts["readiness_json"],
                "docs/openai_plugin_lessons_playbook.md",
                "docs/openai_plugin_interaction_patterns.json",
            ],
            remaining_gap="None for setup evidence; keep the catalog updated when new OpenAI patterns are considered.",
        ),
        _completion_requirement(
            requirement_id="preserve_local_deterministic_model",
            description=(
                "The adopted patterns preserve local source data, deterministic "
                "calculation ownership, and explicit rejection of remote/default "
                "warehouse or model-generated core calculations."
            ),
            status=(
                "covered"
                if local_boundary_status == "covered"
                and {
                    "remote_warehouse_default",
                    "model_generated_core_calculations",
                }
                <= rejected_ids
                else "partial"
            ),
            evidence=[
                artifacts["readiness_json"],
                "docs/openai_plugin_interaction_patterns.json",
            ],
            remaining_gap="None for policy/setup evidence; real runs must still preserve this posture in run_intake.json.",
        ),
        _completion_requirement(
            requirement_id="implement_selective_plugin_setup_gates",
            description=(
                "Interaction contracts, shared-workbench demos, workflow "
                "fixtures, and package validation gates enforce the useful "
                "OpenAI-style patterns without forcing unrelated plugin UI shapes."
            ),
            status=(
                "covered"
                if tiers.get("interaction_contracts") == "covered"
                and tiers.get("demo_ui_contracts") == "covered"
                and tiers.get("workflow_fixture_contracts") == "covered"
                else "partial"
            ),
            evidence=[
                artifacts["readiness_json"],
                "scripts/build_codex_plugin_zip.py --check",
            ],
            remaining_gap="None for current setup gates; new plugins must keep those gates green.",
        ),
        _completion_requirement(
            requirement_id="prove_review_writeback_mechanism",
            description=(
                "Generated non-plotting review UIs can act as decision surfaces "
                "that persist Save/Apply decisions and update target artifacts."
            ),
            status=tier_status_to_requirement_status(
                tiers.get("browser_writeback_mechanism", "not_assessed")
            ),
            evidence=[
                artifacts.get("browser_writeback_json", "not_provided"),
                artifacts.get("browser_writeback_gallery", "not_provided"),
                artifacts["readiness_json"],
            ],
            remaining_gap=(
                "Run the browser write-back report and rebuild the bundle."
                if tiers.get("browser_writeback_mechanism") != "covered"
                else "None for fixture/mechanism evidence."
            ),
        ),
        _completion_requirement(
            requirement_id="validate_real_customer_user_experience",
            description=(
                "Representative real customer-folder runs prove that the "
                "review UX is usable beyond fixtures: queue, evidence, decision "
                "controls, edits, handoff, and final artifacts."
            ),
            status=tier_status_to_requirement_status(
                tiers.get("real_customer_folder_validation", "not_assessed")
            ),
            evidence=[
                artifacts.get("customer_validation_manifest", "not_provided"),
                artifacts["customer_validation_plan_json"],
                artifacts["readiness_json"],
            ],
            remaining_gap=(
                "Record passing real customer-validation cases for every expected non-plotting plugin."
                if tiers.get("real_customer_folder_validation") != "covered"
                else "None for recorded representative cases."
            ),
        ),
    ]
    overall_status = (
        "complete_candidate"
        if all(item["status"] == "covered" for item in requirements)
        else "incomplete"
    )
    return {
        "schema_version": "1.0",
        "objective": (
            "Extract useful OpenAI plugin UI/interaction practices and "
            "selectively implement them while preserving local data and "
            "deterministic calculation ownership."
        ),
        "overall_status": overall_status,
        "requirements": requirements,
    }


def tier_status_to_requirement_status(tier_status: str) -> str:
    if tier_status == "covered":
        return "covered"
    if tier_status in {"partial", "needs_attention"}:
        return "partial"
    return "not_assessed"


def _completion_assessment_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Objective Completion Assessment",
        "",
        f"Overall status: `{payload['overall_status']}`",
        "",
        "| Requirement | Status | Remaining Gap |",
        "| --- | --- | --- |",
    ]
    for item in payload["requirements"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["requirement_id"],
                    item["status"],
                    item["remaining_gap"],
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "This assessment is intentionally conservative: `complete_candidate` "
            "requires every listed requirement to be covered, including real "
            "customer-folder validation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _artifact_href(path_value: str, output_dir: Path) -> str:
    path = Path(path_value)
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _dashboard_artifact_link(
    *,
    artifacts: dict[str, str],
    artifact_key: str,
    label: str,
    output_dir: Path,
) -> str:
    path_value = artifacts.get(artifact_key)
    if not path_value:
        return f'<span class="muted">{html.escape(label)} unavailable</span>'
    href = html.escape(_artifact_href(path_value, output_dir))
    return f'<a href="{href}">{html.escape(label)}</a>'


def _plugin_adoption_rows(readiness_payload: dict[str, Any]) -> list[dict[str, Any]]:
    workbench_items = (
        readiness_payload.get("workbench_evidence")
        if isinstance(readiness_payload.get("workbench_evidence"), list)
        else []
    )
    workbench_by_plugin = {
        str(item.get("plugin")): item
        for item in workbench_items
        if isinstance(item, dict) and item.get("plugin")
    }
    browser = (
        readiness_payload.get("browser_writeback")
        if isinstance(readiness_payload.get("browser_writeback"), dict)
        else {}
    )
    customer = (
        readiness_payload.get("customer_validation")
        if isinstance(readiness_payload.get("customer_validation"), dict)
        else {}
    )
    browser_expected_values = browser.get("expected_plugins")
    browser_expected_list = (
        browser_expected_values if isinstance(browser_expected_values, list) else []
    )
    browser_covered_values = browser.get("covered_plugins")
    browser_covered_list = (
        browser_covered_values if isinstance(browser_covered_values, list) else []
    )
    customer_expected_values = customer.get("expected_plugins")
    customer_expected_list = (
        customer_expected_values if isinstance(customer_expected_values, list) else []
    )
    customer_covered_values = customer.get("covered_plugins")
    customer_covered_list = (
        customer_covered_values if isinstance(customer_covered_values, list) else []
    )
    expected_plugins = sorted(
        {
            *(str(plugin) for plugin in workbench_by_plugin),
            *(str(plugin) for plugin in browser_expected_list),
            *(str(plugin) for plugin in customer_expected_list),
        }
    )
    browser_covered = set(str(plugin) for plugin in browser_covered_list)
    browser_expected = set(str(plugin) for plugin in browser_expected_list)
    customer_covered = set(str(plugin) for plugin in customer_covered_list)
    customer_expected = set(str(plugin) for plugin in customer_expected_list)
    rows: list[dict[str, Any]] = []
    for plugin in expected_plugins:
        workbench = workbench_by_plugin.get(plugin, {})
        scenario_files = (
            workbench.get("scenario_files")
            if isinstance(workbench.get("scenario_files"), list)
            else []
        )
        if plugin in browser_covered:
            browser_status = "covered"
        elif plugin in browser_expected:
            browser_status = "not_assessed"
        else:
            browser_status = "not_applicable"
        if plugin in customer_covered:
            customer_status = "covered"
        elif plugin in customer_expected:
            customer_status = "needs_real_customer_case"
        else:
            customer_status = "not_applicable"
        rows.append(
            {
                "plugin": plugin,
                "demo_status": str(workbench.get("demo_status", "not_assessed")),
                "contract_status": str(
                    workbench.get("contract_status", "not_assessed")
                ),
                "browser_writeback_status": browser_status,
                "customer_validation_status": customer_status,
                "scenario_files": scenario_files,
            }
        )
    return rows


def _adoption_dashboard_html(
    *,
    bundle_manifest: dict[str, Any],
    readiness_payload: dict[str, Any],
    completion_payload: dict[str, Any],
    output_dir: Path,
) -> str:
    artifacts = (
        bundle_manifest.get("artifacts")
        if isinstance(bundle_manifest.get("artifacts"), dict)
        else {}
    )
    validation_tiers = bundle_manifest.get("validation_tiers", {})
    if not isinstance(validation_tiers, dict):
        validation_tiers = {}
    pattern_coverage = (
        readiness_payload.get("pattern_coverage")
        if isinstance(readiness_payload.get("pattern_coverage"), list)
        else []
    )
    plugin_rows = _plugin_adoption_rows(readiness_payload)
    adopted_patterns = (
        readiness_payload.get("patterns")
        if isinstance(readiness_payload.get("patterns"), list)
        else []
    )
    rejected_patterns = (
        readiness_payload.get("rejected_patterns")
        if isinstance(readiness_payload.get("rejected_patterns"), list)
        else []
    )
    next_actions = (
        bundle_manifest.get("next_actions")
        if isinstance(bundle_manifest.get("next_actions"), list)
        else []
    )
    requirements = (
        completion_payload.get("requirements")
        if isinstance(completion_payload.get("requirements"), list)
        else []
    )
    quick_links = [
        ("readiness_markdown", "Readiness Report"),
        ("browser_writeback_gallery", "Browser Write-Back Gallery"),
        ("customer_validation_checklist", "Customer Validation Checklist"),
        ("completion_assessment_markdown", "Completion Assessment"),
        ("readme", "Reviewer README"),
        ("bundle_manifest", "Bundle Manifest"),
    ]
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>OpenAI-Pattern Adoption Dashboard</title>",
        "<style>",
        ":root { color-scheme: light; --ink: #1f2a24; --muted: #66736c; --line: #dbe2dd; --soft: #f6f8f6; --ok: #2f7d4f; --warn: #9a5f15; --bad: #a33b36; --code: #f3f5f3; }",
        "body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #ffffff; color: var(--ink); }",
        "main { max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }",
        "header { border-bottom: 1px solid var(--line); padding-bottom: 18px; margin-bottom: 22px; }",
        "h1 { margin: 0 0 8px; font-size: 1.75rem; line-height: 1.2; font-weight: 720; }",
        "h2 { margin: 0 0 12px; font-size: 1.08rem; line-height: 1.25; }",
        "p { margin: 0; color: var(--muted); line-height: 1.5; }",
        "a { color: #285f46; text-decoration-thickness: 1px; text-underline-offset: 3px; }",
        ".muted { color: var(--muted); }",
        ".meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }",
        ".chip { border: 1px solid var(--line); background: var(--soft); border-radius: 999px; padding: 6px 10px; font-size: 0.82rem; color: var(--ink); }",
        ".grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 16px; }",
        ".panel { border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #fff; }",
        ".card { border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; background: #fff; }",
        ".status { display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 8px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0; white-space: nowrap; }",
        ".status-covered, .status-ok, .status-complete_candidate { color: var(--ok); background: #eaf5ee; }",
        ".status-partial, .status-not_assessed, .status-incomplete, .status-needs_real_customer_case, .status-not_applicable { color: var(--warn); background: #fff4df; }",
        ".status-blocked, .status-high, .status-failed { color: var(--bad); background: #fae9e7; }",
        ".tier-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px; }",
        ".tier { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; flex-wrap: wrap; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; background: #fbfcfb; }",
        ".tier span:first-child { min-width: 0; overflow-wrap: anywhere; }",
        ".links { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }",
        ".links a, .links span { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; background: #fbfcfb; }",
        ".requirements { display: grid; gap: 10px; }",
        ".requirement { border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fbfcfb; }",
        ".requirement-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; margin-bottom: 8px; }",
        ".requirement strong { overflow-wrap: anywhere; }",
        ".requirement p { font-size: 0.9rem; }",
        ".lesson-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 10px; }",
        ".lesson { border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fbfcfb; }",
        ".lesson strong { display: block; margin-bottom: 6px; overflow-wrap: anywhere; }",
        ".lesson p { font-size: 0.9rem; margin-top: 6px; }",
        ".label { color: var(--muted); font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0; }",
        "table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }",
        "th, td { border-bottom: 1px solid var(--line); padding: 9px 8px; text-align: left; vertical-align: top; }",
        "th { color: var(--muted); font-weight: 650; background: #fbfcfb; }",
        "td { overflow-wrap: anywhere; }",
        "ul { margin: 8px 0 0 18px; padding: 0; line-height: 1.45; }",
        "li { margin: 3px 0; }",
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        "<header>",
        "<h1>OpenAI-Pattern Adoption Dashboard</h1>",
        "<p>Reviewer front door for selectively adopted OpenAI plugin interaction patterns. The dashboard separates setup evidence, browser mechanism evidence, and real customer-folder validation so the bundle cannot overclaim readiness.</p>",
        '<div class="meta">',
        f'<span class="chip">Readiness: {html.escape(str(bundle_manifest.get("status", "unknown")))}</span>',
        f'<span class="chip">Objective: {html.escape(str(completion_payload.get("overall_status", "unknown")))}</span>',
        f'<span class="chip">Generated: {html.escape(str(bundle_manifest.get("generated_at", "unknown")))}</span>',
        "</div>",
        "</header>",
        '<section class="grid">',
        '<article class="card">',
        "<h2>Boundary</h2>",
        "<p>Local data and deterministic-script ownership remain the default. Browser write-back is mechanism evidence; only recorded representative customer folders can close the real UX validation tier.</p>",
        "</article>",
        '<article class="card">',
        "<h2>Current Gap</h2>",
        "<p>Keep the objective incomplete until every expected non-plotting plugin has a passing real customer case with screenshots, decisions, and final artifact readback.</p>",
        "</article>",
        "</section>",
        '<section class="panel">',
        "<h2>Validation Tiers</h2>",
        '<div class="tier-grid">',
    ]
    for tier, status in validation_tiers.items():
        status_text = str(status)
        status_class = "status-" + _safe_asset_name(status_text).lower()
        lines.extend(
            [
                '<div class="tier">',
                f"<span>{html.escape(str(tier))}</span>",
                f'<span class="status {html.escape(status_class)}">{html.escape(status_text)}</span>',
                "</div>",
            ]
        )
    lines.extend(
        [
            "</div>",
            "</section>",
            '<section class="panel">',
            "<h2>Plugin Adoption Matrix</h2>",
            "<table>",
            "<thead><tr><th>Plugin</th><th>Demo UI</th><th>Workflow Contract</th><th>Browser Write-Back</th><th>Real Customer Validation</th><th>Scenario Evidence</th></tr></thead>",
            "<tbody>",
        ]
    )
    for row in plugin_rows:
        scenario_files = row.get("scenario_files")
        scenario_text = (
            ", ".join(str(path) for path in scenario_files)
            if isinstance(scenario_files, list) and scenario_files
            else "none"
        )
        status_cells = []
        for key in (
            "demo_status",
            "contract_status",
            "browser_writeback_status",
            "customer_validation_status",
        ):
            status_text = str(row.get(key, "unknown"))
            status_class = "status-" + _safe_asset_name(status_text).lower()
            status_cells.append(
                f'<span class="status {html.escape(status_class)}">{html.escape(status_text)}</span>'
            )
        lines.extend(
            [
                "<tr>",
                f"<td>{html.escape(str(row.get('plugin', 'unknown-plugin')))}</td>",
                f"<td>{status_cells[0]}</td>",
                f"<td>{status_cells[1]}</td>",
                f"<td>{status_cells[2]}</td>",
                f"<td>{status_cells[3]}</td>",
                f"<td>{html.escape(scenario_text)}</td>",
                "</tr>",
            ]
        )
    if not plugin_rows:
        lines.append(
            '<tr><td colspan="6" class="muted">No plugin-level adoption evidence reported.</td></tr>'
        )
    lines.extend(
        [
            "</tbody>",
            "</table>",
            "</section>",
            '<section class="panel">',
            "<h2>Open The Evidence</h2>",
            '<div class="links">',
        ]
    )
    for artifact_key, label in quick_links:
        lines.append(
            _dashboard_artifact_link(
                artifacts=artifacts,
                artifact_key=artifact_key,
                label=label,
                output_dir=output_dir,
            )
        )
    lines.extend(
        [
            "</div>",
            "</section>",
            '<section class="panel">',
            "<h2>Objective Requirements</h2>",
            '<div class="requirements">',
        ]
    )
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        status_text = str(requirement.get("status", "unknown"))
        status_class = "status-" + _safe_asset_name(status_text).lower()
        lines.extend(
            [
                '<article class="requirement">',
                '<div class="requirement-head">',
                f"<strong>{html.escape(str(requirement.get('requirement_id', 'unknown_requirement')))}</strong>",
                f'<span class="status {html.escape(status_class)}">{html.escape(status_text)}</span>',
                "</div>",
                f"<p>{html.escape(str(requirement.get('description', '')))}</p>",
                f"<p><strong>Remaining gap:</strong> {html.escape(str(requirement.get('remaining_gap', '')))}</p>",
                "</article>",
            ]
        )
    lines.extend(
        [
            "</div>",
            "</section>",
            '<section class="panel">',
            "<h2>Adopted OpenAI Lessons</h2>",
            '<div class="lesson-grid">',
        ]
    )
    for pattern in adopted_patterns:
        if not isinstance(pattern, dict):
            continue
        signals = pattern.get("evidence_signals")
        signals_text = (
            ", ".join(str(signal) for signal in signals)
            if isinstance(signals, list) and signals
            else "none"
        )
        lines.extend(
            [
                '<article class="lesson">',
                f"<strong>{html.escape(str(pattern.get('pattern_id', 'unknown_pattern')))}</strong>",
                f'<p><span class="label">Source</span><br>{html.escape(str(pattern.get("source_pattern", "")))}</p>',
                f'<p><span class="label">Local rule</span><br>{html.escape(str(pattern.get("local_rule", "")))}</p>',
                f'<p><span class="label">Evidence signals</span><br>{html.escape(signals_text)}</p>',
                "</article>",
            ]
        )
    if not adopted_patterns:
        lines.append(
            '<p class="muted">No adopted pattern catalog entries reported.</p>'
        )
    lines.extend(
        [
            "</div>",
            "</section>",
            '<section class="panel">',
            "<h2>Rejected OpenAI Patterns</h2>",
            "<table>",
            "<thead><tr><th>Rejected Pattern</th><th>Local Replacement</th><th>Guardrail Signals</th></tr></thead>",
            "<tbody>",
        ]
    )
    for item in rejected_patterns:
        if not isinstance(item, dict):
            continue
        guardrails = item.get("guardrail_signals")
        guardrail_text = (
            ", ".join(str(signal) for signal in guardrails)
            if isinstance(guardrails, list) and guardrails
            else "none"
        )
        lines.extend(
            [
                "<tr>",
                f"<td>{html.escape(str(item.get('playbook_text', 'unknown rejected pattern')))}</td>",
                f"<td>{html.escape(str(item.get('local_replacement', '')))}</td>",
                f"<td>{html.escape(guardrail_text)}</td>",
                "</tr>",
            ]
        )
    if not rejected_patterns:
        lines.append(
            '<tr><td colspan="3" class="muted">No rejected pattern entries reported.</td></tr>'
        )
    lines.extend(
        [
            "</tbody>",
            "</table>",
            "</section>",
            '<section class="panel">',
            "<h2>Pattern Coverage</h2>",
            "<table>",
            "<thead><tr><th>Pattern</th><th>Applicable</th><th>Satisfied</th><th>Missing</th></tr></thead>",
            "<tbody>",
        ]
    )
    for item in pattern_coverage:
        if not isinstance(item, dict):
            continue
        missing = item.get("missing_plugins")
        missing_text = (
            ", ".join(str(plugin) for plugin in missing)
            if isinstance(missing, list) and missing
            else "none"
        )
        lines.extend(
            [
                "<tr>",
                f"<td>{html.escape(str(item.get('pattern_id', 'unknown_pattern')))}</td>",
                f"<td>{html.escape(str(item.get('applicable_count', 'n/a')))}</td>",
                f"<td>{html.escape(str(item.get('satisfied_count', 'n/a')))}</td>",
                f"<td>{html.escape(missing_text)}</td>",
                "</tr>",
            ]
        )
    lines.extend(
        [
            "</tbody>",
            "</table>",
            "</section>",
            '<section class="panel">',
            "<h2>Next Actions</h2>",
        ]
    )
    if not next_actions:
        lines.append("<p>No next actions reported.</p>")
    else:
        lines.append("<ul>")
        for action in next_actions:
            if not isinstance(action, dict):
                continue
            lines.append(
                "<li>"
                f"<strong>{html.escape(str(action.get('id', 'unknown_action')))}</strong>"
                f" ({html.escape(str(action.get('priority', 'n/a')))}): "
                f"{html.escape(str(action.get('description', '')))}"
                "</li>"
            )
        lines.append("</ul>")
    lines.extend(["</section>", "</main>", "</body>", "</html>"])
    return "\n".join(lines) + "\n"


def _resolve_existing_report(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path.expanduser().resolve()


def build_evidence_bundle(
    *,
    root: Path = ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    browser_writeback_report_path: Path | None = None,
    customer_manifest_path: Path | None = None,
    expected_customer_plugins: tuple[str, ...] | None = None,
    require_browser_writeback: bool = False,
    verify_browser_writeback_screenshots: bool = False,
    require_customer_validation: bool = False,
    verify_customer_artifact_paths: bool = False,
    require_complete_objective: bool = False,
) -> dict[str, Any]:
    """Write a persisted OpenAI-pattern adoption evidence bundle."""

    root = root.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC)

    readiness = _load_script(
        "audit_openai_pattern_adoption_readiness",
        SCRIPT_DIR / "audit_openai_pattern_adoption_readiness.py",
    )
    browser_report_path = _resolve_existing_report(browser_writeback_report_path)
    customer_manifest_path = _resolve_existing_report(customer_manifest_path)
    artifacts: dict[str, str] = {}

    if browser_report_path is not None:
        artifacts["browser_writeback_json"] = browser_report_path.as_posix()
    if customer_manifest_path is not None:
        artifacts["customer_validation_manifest"] = customer_manifest_path.as_posix()

    report = readiness.audit_adoption_readiness(
        root,
        browser_writeback_report_path=browser_report_path,
        require_browser_writeback=require_browser_writeback,
        verify_browser_writeback_screenshots=verify_browser_writeback_screenshots,
        customer_manifest_path=customer_manifest_path,
        expected_customer_plugins=expected_customer_plugins,
        require_customer_validation=require_customer_validation,
        verify_customer_artifact_paths=verify_customer_artifact_paths,
    )
    readiness_json_path = output_dir / "readiness.json"
    readiness_markdown_path = output_dir / "readiness.md"
    readiness_json_path.write_text(readiness._json_report(report), encoding="utf-8")
    readiness_markdown_path.write_text(
        readiness._markdown_report(report),
        encoding="utf-8",
    )
    artifacts["readiness_json"] = readiness_json_path.as_posix()
    artifacts["readiness_markdown"] = readiness_markdown_path.as_posix()

    readiness_payload = report.to_dict()
    gallery_payload = _browser_writeback_gallery_payload(
        browser_report_path=browser_report_path,
        output_dir=output_dir,
    )
    gallery_json_path = output_dir / "browser_writeback_gallery.json"
    _write_json(gallery_json_path, gallery_payload)
    artifacts["browser_writeback_gallery_json"] = gallery_json_path.as_posix()
    gallery_path = output_dir / "browser_writeback_gallery.html"
    gallery_path.write_text(
        _browser_writeback_gallery_html(gallery_payload),
        encoding="utf-8",
    )
    artifacts["browser_writeback_gallery"] = gallery_path.as_posix()
    expected_plugins = tuple(
        readiness_payload["customer_validation"]["expected_plugins"]
    )
    template_path = output_dir / "customer_validation_template.json"
    _write_json(
        template_path,
        readiness.customer_validation_template(expected_plugins),
    )
    artifacts["customer_validation_template"] = template_path.as_posix()
    plan_path = output_dir / "customer_validation_plan.md"
    plan_path.write_text(
        _customer_validation_plan_text(readiness_payload),
        encoding="utf-8",
    )
    artifacts["customer_validation_plan"] = plan_path.as_posix()
    plan_json_path = output_dir / "customer_validation_plan.json"
    plan_payload = _customer_validation_plan_payload(readiness_payload)
    _write_json(
        plan_json_path,
        plan_payload,
    )
    artifacts["customer_validation_plan_json"] = plan_json_path.as_posix()
    checklist_path = output_dir / "customer_validation_checklist.html"
    checklist_path.write_text(
        _customer_validation_checklist_html(plan_payload),
        encoding="utf-8",
    )
    artifacts["customer_validation_checklist"] = checklist_path.as_posix()
    completion_payload = _completion_assessment_payload(readiness_payload, artifacts)
    completion_json_path = output_dir / "completion_assessment.json"
    completion_md_path = output_dir / "completion_assessment.md"
    _write_json(completion_json_path, completion_payload)
    completion_md_path.write_text(
        _completion_assessment_markdown(completion_payload),
        encoding="utf-8",
    )
    artifacts["completion_assessment_json"] = completion_json_path.as_posix()
    artifacts["completion_assessment_markdown"] = completion_md_path.as_posix()
    commands = {
        "generate_browser_writeback_report": _browser_writeback_command(output_dir),
        "build_evidence_bundle": _build_bundle_command(
            output_dir=output_dir,
            browser_writeback_report_path=browser_report_path,
            customer_manifest_path=customer_manifest_path,
            expected_customer_plugins=expected_customer_plugins,
            require_browser_writeback=require_browser_writeback,
            verify_browser_writeback_screenshots=verify_browser_writeback_screenshots,
            require_customer_validation=require_customer_validation,
            verify_customer_artifact_paths=verify_customer_artifact_paths,
            require_complete_objective=require_complete_objective,
        ),
        "strict_customer_validation_gate": _strict_customer_gate_command(
            customer_manifest_path,
            expected_customer_plugins,
        ),
    }

    bundle_manifest = {
        "schema_version": "1.0",
        "generated_at": generated_at.isoformat(),
        "root": root.as_posix(),
        "status": readiness_payload["status"],
        "artifacts": artifacts,
        "commands": commands,
        "validation_tiers": _status_by_tier(readiness_payload),
        "next_actions": readiness_payload["next_actions"],
        "limits": readiness_payload["limits"],
    }
    readme_path = output_dir / "README.md"
    bundle_manifest["artifacts"]["readme"] = readme_path.as_posix()
    manifest_path = output_dir / "bundle_manifest.json"
    bundle_manifest["artifacts"]["bundle_manifest"] = manifest_path.as_posix()
    dashboard_path = output_dir / "adoption_review_dashboard.html"
    bundle_manifest["artifacts"][
        "adoption_review_dashboard"
    ] = dashboard_path.as_posix()
    dashboard_path.write_text(
        _adoption_dashboard_html(
            bundle_manifest=bundle_manifest,
            readiness_payload=readiness_payload,
            completion_payload=completion_payload,
            output_dir=output_dir,
        ),
        encoding="utf-8",
    )
    readme_path.write_text(_readme_text(bundle_manifest), encoding="utf-8")
    _write_json(manifest_path, bundle_manifest)
    return bundle_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--browser-writeback-report",
        type=Path,
        default=None,
        help="Use an existing browser write-back JSON report instead of running it.",
    )
    parser.add_argument(
        "--customer-validation-manifest",
        type=Path,
        default=None,
        help=(
            "Optional manifest of recorded real customer-validation cases to "
            "include in the readiness report."
        ),
    )
    parser.add_argument(
        "--expected-customer-plugin",
        action="append",
        default=None,
        help=(
            "Plugin expected in the customer-validation template/readiness report. "
            "May be passed multiple times."
        ),
    )
    parser.add_argument("--require-browser-writeback", action="store_true")
    parser.add_argument("--verify-browser-writeback-screenshots", action="store_true")
    parser.add_argument("--require-customer-validation", action="store_true")
    parser.add_argument("--verify-customer-validation-artifacts", action="store_true")
    parser.add_argument(
        "--require-complete-objective",
        action="store_true",
        help=(
            "Exit nonzero unless completion_assessment.json reports "
            "overall_status complete_candidate."
        ),
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "blocker", "high", "medium", "info"),
        default="medium",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Build the evidence bundle and print the manifest path."""

    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    expected_plugins = (
        tuple(args.expected_customer_plugin)
        if args.expected_customer_plugin is not None
        else None
    )
    try:
        manifest = build_evidence_bundle(
            root=args.root,
            output_dir=args.output_dir,
            browser_writeback_report_path=args.browser_writeback_report,
            customer_manifest_path=args.customer_validation_manifest,
            expected_customer_plugins=expected_plugins,
            require_browser_writeback=args.require_browser_writeback,
            verify_browser_writeback_screenshots=args.verify_browser_writeback_screenshots,
            require_customer_validation=args.require_customer_validation,
            verify_customer_artifact_paths=args.verify_customer_validation_artifacts,
            require_complete_objective=args.require_complete_objective,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    manifest_path = Path(manifest["artifacts"]["bundle_manifest"])
    sys.stdout.write(f"Wrote OpenAI-pattern adoption evidence: {manifest_path}\n")
    if args.fail_on == "none":
        return 0
    readiness = _load_script(
        "audit_openai_pattern_adoption_readiness",
        SCRIPT_DIR / "audit_openai_pattern_adoption_readiness.py",
    )
    readiness_payload = json.loads(
        Path(manifest["artifacts"]["readiness_json"]).read_text(encoding="utf-8")
    )
    if args.require_complete_objective:
        completion_payload = json.loads(
            Path(manifest["artifacts"]["completion_assessment_json"]).read_text(
                encoding="utf-8"
            )
        )
        if completion_payload.get("overall_status") != "complete_candidate":
            sys.stderr.write(
                "OpenAI-pattern adoption objective is not complete: "
                f"{completion_payload.get('overall_status')}\n"
            )
            return 1
    issues = [
        readiness.AdoptionReadinessIssue(**issue)
        for issue in readiness_payload.get("issues", [])
    ]
    return 1 if readiness._issues_at_or_above(issues, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
