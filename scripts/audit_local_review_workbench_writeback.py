#!/usr/bin/env python3
"""Browser-level smoke audit for local review-workbench decision write-back."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import serve_review_workbench

__all__ = [
    "BrowserWritebackIssue",
    "BrowserWritebackReport",
    "audit_local_review_writebacks",
    "audit_local_review_writeback",
    "main",
    "write_plugin_fixture",
    "write_check_entries_fixture",
]

ROOT = SCRIPT_DIR.parents[0]
EDIT_VALUE = "Reviewed from browser audit"
REVIEWER_NOTE = "Applied through the shared local review server browser audit"
DEFAULT_PLUGIN = "check-entries"
STRUCTURED_TARGET_EXTENSIONS = {".csv", ".json", ".jsonl"}
TEXT_TARGET_EXTENSIONS = {
    ".htm",
    ".html",
    ".md",
    ".sql",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
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
class BrowserWritebackIssue:
    """One browser/local-server write-back finding."""

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
class BrowserWritebackReport:
    """Browser-level proof for one generated local review workbench."""

    plugin: str
    output_dir: str
    item_id: str = ""
    target_artifact: str = ""
    writeback_mode: str = "artifact_edit"
    url: str | None = None
    screenshot_path: str | None = None
    row_count: int = 0
    decision_control_count: int = 0
    status_text: str = ""
    ui_decision_source: str = ""
    applied_decision_source: str = ""
    final_status: str = ""
    csv_contains_edit: bool = False
    files_written: list[str] = field(default_factory=list)
    issues: list[BrowserWritebackIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Return a compact status for CLI output."""

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
            "output_dir": self.output_dir,
            "item_id": self.item_id,
            "target_artifact": self.target_artifact,
            "writeback_mode": self.writeback_mode,
            "url": self.url,
            "screenshot_path": self.screenshot_path,
            "row_count": self.row_count,
            "decision_control_count": self.decision_control_count,
            "status_text": self.status_text,
            "ui_decision_source": self.ui_decision_source,
            "applied_decision_source": self.applied_decision_source,
            "final_status": self.final_status,
            "csv_contains_edit": self.csv_contains_edit,
            "files_written": self.files_written,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _issue(severity: str, code: str, message: str) -> BrowserWritebackIssue:
    return BrowserWritebackIssue(
        severity=severity,
        code=code,
        message=message,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _prepare_output_dir(output_dir: Path | None) -> Path:
    if output_dir is None:
        temp_root = Path("/private/tmp")
        if not temp_root.exists():
            temp_root = Path(tempfile.gettempdir())
        return Path(
            tempfile.mkdtemp(
                prefix="mparanza-local-review-writeback-",
                dir=temp_root,
            )
        ).resolve()
    directory = output_dir.expanduser().resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(f"output directory must be empty: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _discover_workbench_plugins(root: Path = ROOT) -> list[str]:
    """Return plugins that use the generated non-plotting review workbench."""

    return sorted(
        path.parents[1].name
        for path in (root / "plugins").glob("*/assets/review-workbench-adapter.json")
    )


def _read_adapter(root: Path, plugin: str) -> dict[str, Any]:
    adapter_path = (
        root / "plugins" / plugin / "assets" / "review-workbench-adapter.json"
    )
    return json.loads(adapter_path.read_text(encoding="utf-8"))


def _editable_demo_item(adapter: dict[str, Any]) -> dict[str, Any]:
    items = adapter.get("demo", {}).get("items", [])
    if not isinstance(items, list):
        raise ValueError("adapter demo.items must be an array")
    for item in items:
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        if "edit" not in item.get("allowed_actions", []):
            continue
        target_artifact = str(data.get("target_artifact") or "")
        target_field = str(data.get("target_field") or "")
        target_id_field = str(data.get("target_id_field") or "")
        target_record_id = str(data.get("target_record_id") or "")
        target_records_key = str(data.get("target_records_key") or "")
        if (
            target_artifact
            and target_field
            and (
                target_artifact.endswith(tuple(TEXT_TARGET_EXTENSIONS))
                or (
                    target_artifact.endswith(tuple(STRUCTURED_TARGET_EXTENSIONS))
                    and target_id_field
                    and target_record_id
                )
            )
            and (target_record_id or target_records_key)
        ):
            return item
    raise ValueError("adapter demo has no editable item with a write-back target")


def _write_target_artifact(output_dir: Path, item: dict[str, Any]) -> str:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    target_artifact = str(data.get("target_artifact") or "")
    target_path = output_dir / target_artifact
    target_path.parent.mkdir(parents=True, exist_ok=True)
    extension = target_path.suffix.lower()
    id_field = str(data.get("target_id_field") or "")
    record_id = str(data.get("target_record_id") or "")
    target_field = str(data.get("target_field") or "")
    records_key = str(data.get("target_records_key") or "")

    if extension == ".csv":
        target_path.write_text(
            f"{id_field},{target_field}\n{record_id},\n",
            encoding="utf-8",
        )
    elif extension == ".jsonl":
        target_path.write_text(
            json.dumps({id_field: record_id, target_field: ""}) + "\n",
            encoding="utf-8",
        )
    elif extension == ".json":
        record = {id_field: record_id, target_field: ""}
        payload: Any = {records_key: [record]} if records_key else [record]
        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    elif extension in TEXT_TARGET_EXTENSIONS:
        target_path.write_text(
            f"Original review text for {item.get('id', 'item')}.\n",
            encoding="utf-8",
        )
    else:
        raise ValueError(
            f"unsupported browser-audit target artifact: {target_artifact}"
        )
    return target_artifact


def write_plugin_fixture(root: Path, plugin: str, output_dir: Path) -> dict[str, str]:
    """Write a browser-audit run fixture from a plugin's generated adapter demo."""

    if plugin == "new-client":
        return _write_new_client_fixture(root, output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = _read_adapter(root, plugin)
    item = json.loads(json.dumps(_editable_demo_item(adapter)))
    item["recommended_action"] = "edit"
    item["status"] = "ready_for_review"
    data = item.setdefault("data", {})
    if isinstance(data, dict):
        data.setdefault(
            "edit_hint",
            "Editing this fixture item writes the target artifact during the browser audit.",
        )
    target_artifact = _write_target_artifact(output_dir, item)
    run_id = f"{plugin}-browser-writeback"
    input_paths = ["input.xlsx", "evidence/"]
    _write_json(
        output_dir / "run_intake.json",
        {
            "schema_version": "1.0",
            "plugin": plugin,
            "workflow": plugin,
            "run_id": run_id,
            "created_at": "2026-06-08T10:00:00Z",
            "language": "en",
            "input_paths": input_paths,
            "output_dir": output_dir.as_posix(),
            "inferred_task": f"Browser write-back audit for {plugin} review.",
            "assumptions": [
                "Synthetic local fixture generated from the workbench adapter demo; not customer validation."
            ],
            "unresolved_questions": [],
            "dependency_check": {"status": "ok"},
            "data_posture": {
                "local_files_read": input_paths,
                "external_connectors_used": [],
                "upload_paths_used": [],
                "remote_sql_execution_used": False,
                "hosted_notebook_execution_used": False,
            },
            "execution_trace": [
                {
                    "step_id": "fixture_review_session",
                    "kind": "deterministic_review_session",
                    "status": "passed",
                    "execution_location": "local_codex_workspace",
                    "command": ["audit_local_review_workbench_writeback", "fixture"],
                    "inputs": input_paths,
                    "outputs": [
                        "run_intake.json",
                        "review_payload.json",
                        "final_artifacts.json",
                        target_artifact,
                    ],
                }
            ],
        },
    )
    _write_json(
        output_dir / "review_payload.json",
        {
            "schema_version": "1.0",
            "plugin": plugin,
            "workflow": plugin,
            "run_id": run_id,
            "source_paths": input_paths,
            "review_type": adapter.get("demo", {}).get(
                "review_type", f"{plugin.replace('-', '_')}_review"
            ),
            "items": [item],
            "item_count": 1,
            "evidence": item.get("evidence", []),
            "allowed_actions": item.get("allowed_actions", []),
            "status": "ready_for_review",
            "summary": {"issue_count": 1, "artifact_count": 1},
        },
    )
    _write_json(
        output_dir / "ui_decisions.json",
        {
            "schema_version": "1.0",
            "plugin": plugin,
            "workflow": plugin,
            "run_id": run_id,
            "review_payload_path": "review_payload.json",
            "decisions": [],
            "decision_count": 0,
            "item_count": 1,
            "status": "pending_review",
        },
    )
    _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": "1.0",
            "plugin": plugin,
            "workflow": plugin,
            "run_id": run_id,
            "outputs": [
                {
                    "path": target_artifact,
                    "kind": Path(target_artifact).suffix.lstrip(".") or "file",
                    "status": "written",
                }
            ],
            "caveats": [],
            "next_actions": [],
            "status": "written_pending_review",
        },
    )
    return {
        "item_id": str(item["id"]),
        "target_artifact": target_artifact,
        "writeback_mode": "artifact_edit",
    }


def _write_new_client_fixture(root: Path, output_dir: Path) -> dict[str, str]:
    """Build a real blocked package for immutable-domain review write-back."""

    plugin_root = root / "plugins" / "new-client"
    initialize = subprocess.run(
        [
            sys.executable,
            str(plugin_root / "scripts" / "initialize_case.py"),
            "--case-dir",
            str(output_dir),
            "--client-reference",
            "CLIENT-AUDIT-001",
            "--assessment-date",
            "2026-07-20",
        ],
        cwd=plugin_root,
        capture_output=True,
        check=False,
        text=True,
    )
    if initialize.returncode != 0:
        raise RuntimeError(
            "new-client audit initialization failed: "
            + (initialize.stderr or initialize.stdout).strip()
        )
    package = subprocess.run(
        [
            sys.executable,
            str(plugin_root / "scripts" / "package_new_client.py"),
            "--input",
            str(output_dir / "new_client_input.json"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=plugin_root,
        capture_output=True,
        check=False,
        text=True,
    )
    if package.returncode != 0:
        raise RuntimeError(
            "new-client audit packaging failed: "
            + (package.stderr or package.stdout).strip()
        )
    review = _read_json_if_present(output_dir / "review_payload.json")
    items = review.get("items")
    if not isinstance(items, list):
        raise RuntimeError("new-client audit package has no review items")
    item = next(
        (
            candidate
            for candidate in items
            if isinstance(candidate, dict)
            and candidate.get("item_type") == "aml_risk_factor"
            and "edit" in candidate.get("allowed_actions", [])
        ),
        None,
    )
    if item is None:
        raise RuntimeError("new-client audit package has no editable AML item")
    return {
        "item_id": str(item["id"]),
        "target_artifact": "aml_assessment_draft.json",
        "writeback_mode": "review_proposal",
    }


def write_check_entries_fixture(output_dir: Path) -> None:
    """Write a small local run fixture with a CSV edit target."""

    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = "check-entries-browser-writeback"
    _write_json(
        output_dir / "run_intake.json",
        {
            "schema_version": "1.0",
            "plugin": "check-entries",
            "workflow": "check-entries",
            "run_id": run_id,
            "created_at": "2026-06-08T10:00:00Z",
            "language": "en",
            "input_paths": ["entries.xlsx", "support_1001.pdf"],
            "output_dir": output_dir.as_posix(),
            "inferred_task": "Browser write-back audit for Check Entries review.",
            "assumptions": ["Synthetic local fixture; not customer validation."],
            "unresolved_questions": [],
            "dependency_check": {"status": "ok"},
            "data_posture": {
                "local_files_read": ["entries.xlsx", "support_1001.pdf"],
                "external_connectors_used": [],
                "upload_paths_used": [],
                "remote_sql_execution_used": False,
                "hosted_notebook_execution_used": False,
            },
            "execution_trace": [
                {
                    "step_id": "fixture_review_session",
                    "kind": "deterministic_review_session",
                    "status": "passed",
                    "execution_location": "local_codex_workspace",
                    "command": ["audit_local_review_workbench_writeback", "fixture"],
                    "inputs": ["entries.xlsx", "support_1001.pdf"],
                    "outputs": [
                        "run_intake.json",
                        "review_payload.json",
                        "final_artifacts.json",
                        "check_results.csv",
                    ],
                }
            ],
        },
    )
    _write_json(
        output_dir / "review_payload.json",
        {
            "schema_version": "1.0",
            "plugin": "check-entries",
            "workflow": "check-entries",
            "run_id": run_id,
            "source_paths": ["entries.xlsx", "support_1001.pdf"],
            "review_type": "journal_entry_support_review",
            "items": [
                {
                    "id": "entry-1",
                    "item_type": "supported_entry",
                    "title": "1001 | 123.45 | 2025-01-02",
                    "source_path": "entries.xlsx",
                    "output_path": "check_results.csv",
                    "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                    "recommended_action": "edit",
                    "status": "ready_for_review",
                    "data": {
                        "status": "ok",
                        "movement_number": "1001",
                        "entry_date": "2025-01-02",
                        "beneficiary": "ACME Spa",
                        "amount_abs": "123.45",
                        "matched_pdf": "support_1001.pdf",
                        "checks_run": "amount,date,beneficiary",
                        "source_row": "1",
                        "target_artifact": "check_results.csv",
                        "target_id_field": "source_row",
                        "target_record_id": "1",
                        "target_field": "review_notes",
                        "edit_hint": (
                            "Editing this row writes review_notes in "
                            "check_results.csv for source_row 1."
                        ),
                    },
                    "evidence": [
                        {
                            "kind": "deterministic_checks",
                            "status": "ok",
                            "matched_pdf": "support_1001.pdf",
                            "checks_run": "amount,date,beneficiary",
                            "review_notes": "All deterministic checks passed.",
                        }
                    ],
                }
            ],
            "item_count": 1,
            "columns": ["source_row", "review_notes"],
            "evidence": [{"kind": "deterministic_checks", "status": "ok"}],
            "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
            "status": "ready_for_review",
            "summary": {"issue_count": 1, "artifact_count": 1},
        },
    )
    _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": "1.0",
            "plugin": "check-entries",
            "workflow": "check-entries",
            "run_id": run_id,
            "outputs": [
                {
                    "path": "check_results.csv",
                    "kind": "csv",
                    "status": "written",
                    "required_columns": ["source_row", "review_notes"],
                }
            ],
            "caveats": [],
            "next_actions": [],
            "status": "written_pending_review",
        },
    )
    (output_dir / "check_results.csv").write_text(
        "source_row,review_notes\n1,\n",
        encoding="utf-8",
    )


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


def _read_json_if_present(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _inspect_written_artifacts(
    output_dir: Path, report: BrowserWritebackReport
) -> None:
    ui_decisions = _read_json_if_present(output_dir / "ui_decisions.json")
    applied_decisions = _read_json_if_present(output_dir / "applied_decisions.json")
    final_artifacts = _read_json_if_present(output_dir / "final_artifacts.json")
    target_text = ""
    target_path = (
        output_dir / report.target_artifact if report.target_artifact else None
    )
    if target_path and target_path.exists():
        target_text = target_path.read_text(encoding="utf-8")

    required_files = [
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    if report.target_artifact:
        required_files.append(report.target_artifact)
    report.files_written = [
        name for name in required_files if (output_dir / name).exists()
    ]
    report.ui_decision_source = str(ui_decisions.get("decision_source") or "")
    report.applied_decision_source = str(applied_decisions.get("decision_source") or "")
    if report.writeback_mode == "review_proposal":
        report.final_status = str(final_artifacts.get("status") or "")
    else:
        report.final_status = str(
            final_artifacts.get("review_status") or final_artifacts.get("status") or ""
        )
    report.csv_contains_edit = EDIT_VALUE in target_text

    if report.ui_decision_source != "local_review_server":
        report.issues.append(
            _issue(
                "high",
                "ui_decisions_not_from_local_server",
                "ui_decisions.json was not persisted by the local review server.",
            )
        )
    if report.applied_decision_source != "local_review_server":
        report.issues.append(
            _issue(
                "high",
                "applied_decisions_not_from_local_server",
                "applied_decisions.json was not applied by the local review server.",
            )
        )
    report.csv_contains_edit = EDIT_VALUE in target_text
    if report.writeback_mode == "review_proposal" and report.csv_contains_edit:
        report.issues.append(
            _issue(
                "high",
                "immutable_domain_artifact_modified",
                f"The proposal-only review modified {report.target_artifact}.",
            )
        )
    elif report.writeback_mode == "artifact_edit" and not report.csv_contains_edit:
        report.issues.append(
            _issue(
                "high",
                "target_artifact_not_updated",
                f"The target artifact {report.target_artifact or '<missing>'} does not contain the reviewer edit.",
            )
        )
    if report.final_status not in {
        "final_ready",
        "partial_review_applied",
        "proposals_ready",
        "blocked",
    }:
        report.issues.append(
            _issue(
                "medium",
                "final_status_not_review_applied",
                f"final_artifacts.json status is {report.final_status!r}.",
            )
        )


def _drive_browser(
    *,
    url: str,
    output_dir: Path,
    report: BrowserWritebackReport,
    browser_executable: str | None,
    screenshot_path: Path | None,
) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Python Playwright is not installed.") from exc

    executable = _browser_executable(browser_executable)
    with sync_playwright() as playwright:
        launch_args: dict[str, Any] = {"headless": True, "args": ["--disable-gpu"]}
        if executable:
            launch_args["executable_path"] = executable
        browser = playwright.chromium.launch(**launch_args)
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.goto(url, wait_until="load")
            row_selector = f'#rows button.row[data-id="{report.item_id}"]'
            page.locator(row_selector).wait_for(timeout=10_000)
            page.locator(row_selector).click()
            page.locator("[data-decision-action='edit']").click()
            page.locator("[data-decision-field='reviewer_note']").fill(REVIEWER_NOTE)
            page.locator("[data-decision-field='edit_value']").fill(EDIT_VALUE)
            page.locator("#apply-decisions").click()
            page.wait_for_function(
                """() => {
                  const node = document.querySelector("#save-status");
                  return node?.classList.contains("is-ok")
                    || node?.classList.contains("is-error");
                }""",
                timeout=15_000,
            )
            metrics = page.evaluate("""() => ({
                  rowCount: document.querySelectorAll("#rows button.row[data-id]").length,
                  decisionControlCount: document.querySelectorAll("[data-decision-action]").length,
                  statusText: document.querySelector("#save-status")?.innerText || "",
                })""")
            report.row_count = int(metrics["rowCount"])
            report.decision_control_count = int(metrics["decisionControlCount"])
            report.status_text = str(metrics["statusText"])
            if screenshot_path is not None:
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)
                report.screenshot_path = screenshot_path.as_posix()
            context.close()
        finally:
            browser.close()
    _inspect_written_artifacts(output_dir, report)


def audit_local_review_writeback(
    *,
    root: Path = ROOT,
    plugin: str = DEFAULT_PLUGIN,
    output_dir: Path | None = None,
    screenshots_dir: Path | None = None,
    browser_executable: str | None = None,
) -> BrowserWritebackReport:
    """Run a browser-level local review write-back audit for one plugin."""

    if shutil.which("node") is None:
        raise RuntimeError("Node.js is required for the plugin MCP save/apply bridge.")
    run_dir = _prepare_output_dir(output_dir)
    fixture = write_plugin_fixture(root, plugin, run_dir)
    report = BrowserWritebackReport(
        plugin=plugin,
        output_dir=run_dir.as_posix(),
        item_id=fixture["item_id"],
        target_artifact=fixture["target_artifact"],
        writeback_mode=fixture.get("writeback_mode", "artifact_edit"),
    )
    workbench = serve_review_workbench.LocalReviewWorkbench(
        plugin_dir=root / "plugins" / plugin,
        output_dir=run_dir,
    )
    httpd, url = serve_review_workbench.create_review_http_server(workbench)
    report.url = url
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    screenshot_path = (
        screenshots_dir or run_dir / "screenshots"
    ) / f"{plugin}-browser-writeback.png"
    try:
        _drive_browser(
            url=url,
            output_dir=run_dir,
            report=report,
            browser_executable=browser_executable,
            screenshot_path=screenshot_path,
        )
    except Exception as exc:  # noqa: BLE001 - surface browser/runtime failures.
        report.issues.append(
            _issue(
                "blocker",
                "browser_writeback_failed",
                str(exc),
            )
        )
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
    invalid_row_count = (
        report.row_count < 1
        if report.writeback_mode == "review_proposal"
        else report.row_count != 1
    )
    if invalid_row_count:
        expected_rows = (
            "at least one visible review row"
            if report.writeback_mode == "review_proposal"
            else "exactly one visible review row"
        )
        report.issues.append(
            _issue(
                "high",
                "review_row_not_visible",
                f"Expected {expected_rows}, found {report.row_count}.",
            )
        )
    if report.decision_control_count < 4:
        report.issues.append(
            _issue(
                "high",
                "decision_controls_not_visible",
                f"Expected at least 4 decision controls, found {report.decision_control_count}.",
            )
        )
    return report


def _prepare_suite_root(output_dir: Path | None) -> Path:
    if output_dir is None:
        temp_root = Path("/private/tmp")
        if not temp_root.exists():
            temp_root = Path(tempfile.gettempdir())
        return Path(
            tempfile.mkdtemp(
                prefix="mparanza-local-review-writeback-suite-",
                dir=temp_root,
            )
        ).resolve()
    directory = output_dir.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def audit_local_review_writebacks(
    *,
    root: Path = ROOT,
    plugins: list[str] | None = None,
    output_dir: Path | None = None,
    screenshots_dir: Path | None = None,
    browser_executable: str | None = None,
) -> list[BrowserWritebackReport]:
    """Run browser-level local review write-back audits for generated workbenches."""

    selected_plugins = plugins or _discover_workbench_plugins(root)
    suite_root = _prepare_suite_root(output_dir)
    reports: list[BrowserWritebackReport] = []
    for plugin in selected_plugins:
        plugin_output_dir = suite_root / plugin
        report = audit_local_review_writeback(
            root=root,
            plugin=plugin,
            output_dir=plugin_output_dir,
            screenshots_dir=screenshots_dir,
            browser_executable=browser_executable,
        )
        reports.append(report)
    return reports


def _markdown_report(report: BrowserWritebackReport, *, root: Path) -> str:
    issues = ", ".join(f"{issue.severity}:{issue.code}" for issue in report.issues)
    screenshot = (
        _relative_or_absolute(Path(report.screenshot_path), root)
        if report.screenshot_path
        else "none"
    )
    lines = [
        "# Local Review Workbench Write-Back Audit",
        "",
        f"Status: `{report.status}`",
        "",
        "| Plugin | URL | Rows | Decisions | Final Status | Artifact Updated | Screenshot | Issues |",
        "| --- | --- | ---: | ---: | --- | --- | --- | --- |",
        "| "
        + " | ".join(
            [
                report.plugin,
                report.url or "none",
                str(report.row_count),
                str(report.decision_control_count),
                report.final_status or "none",
                "yes" if report.csv_contains_edit else "no",
                screenshot,
                issues or "none",
            ]
        )
        + " |",
        "",
        f"Target artifact: `{report.target_artifact or 'none'}`",
        "",
        f"Output dir: `{report.output_dir}`",
        f"Files written: `{json.dumps(report.files_written)}`",
        "",
        "This is browser-level fixture evidence for the local write-back path; "
        "it is not real customer-folder validation.",
    ]
    return "\n".join(lines) + "\n"


def _suite_summary(reports: list[BrowserWritebackReport]) -> dict[str, Any]:
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


def _markdown_suite_report(reports: list[BrowserWritebackReport], *, root: Path) -> str:
    summary = _suite_summary(reports)
    lines = [
        "# Local Review Workbench Write-Back Audit",
        "",
        f"Plugins audited: {summary['plugin_count']}",
        f"Status counts: `{json.dumps(summary['status_counts'], sort_keys=True)}`",
        f"Issue counts: `{json.dumps(summary['issue_counts'], sort_keys=True)}`",
        "",
        "| Plugin | Status | Rows | Decisions | Target Artifact | Final Status | Updated | Screenshot | Issues |",
        "| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |",
    ]
    for report in reports:
        issues = ", ".join(f"{issue.severity}:{issue.code}" for issue in report.issues)
        screenshot = (
            _relative_or_absolute(Path(report.screenshot_path), root)
            if report.screenshot_path
            else "none"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    report.plugin,
                    report.status,
                    str(report.row_count),
                    str(report.decision_control_count),
                    report.target_artifact or "none",
                    report.final_status or "none",
                    "yes" if report.csv_contains_edit else "no",
                    screenshot,
                    issues or "none",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "This is browser-level fixture evidence for the local write-back path; "
            "it is not real customer-folder validation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _json_report(report: BrowserWritebackReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


def _json_suite_report(reports: list[BrowserWritebackReport]) -> str:
    return (
        json.dumps(
            {
                "summary": _suite_summary(reports),
                "reports": [report.to_dict() for report in reports],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _has_failure(
    report: BrowserWritebackReport | list[BrowserWritebackReport], threshold: str
) -> bool:
    if threshold == "none":
        return False
    threshold_value = SEVERITY_RANK[threshold]
    reports = report if isinstance(report, list) else [report]
    return any(
        SEVERITY_RANK.get(issue.severity, 0) >= threshold_value
        for current_report in reports
        for issue in current_report.issues
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Open a generated review workbench through the local server, click "
            "Save/Apply in a browser, and verify local artifacts changed."
        )
    )
    parser.add_argument(
        "--plugin",
        default="all",
        help='Plugin to audit, or "all" for every generated non-plotting workbench.',
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--screenshots-dir", type=Path)
    parser.add_argument("--browser-executable")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        help=(
            "Optional path where the generated markdown/json report should be "
            "written. Stdout is still emitted for terminal review."
        ),
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "blocker", "high", "medium"),
        default="high",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the browser-level local review write-back audit."""

    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.plugin == "all":
            report: BrowserWritebackReport | list[BrowserWritebackReport] = (
                audit_local_review_writebacks(
                    output_dir=args.output_dir,
                    screenshots_dir=args.screenshots_dir,
                    browser_executable=args.browser_executable,
                )
            )
        else:
            report = audit_local_review_writeback(
                plugin=args.plugin,
                output_dir=args.output_dir,
                screenshots_dir=args.screenshots_dir,
                browser_executable=args.browser_executable,
            )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        report = BrowserWritebackReport(
            plugin=args.plugin,
            output_dir=str(args.output_dir or ""),
            issues=[
                _issue(
                    "blocker",
                    "audit_setup_failed",
                    str(exc),
                )
            ],
        )
    if isinstance(report, list):
        output = (
            _json_suite_report(report)
            if args.format == "json"
            else _markdown_suite_report(report, root=ROOT)
        )
    else:
        output = (
            _json_report(report)
            if args.format == "json"
            else _markdown_report(report, root=ROOT)
        )
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(output, encoding="utf-8")
    sys.stdout.write(output)
    return 1 if _has_failure(report, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
