#!/usr/bin/env python3
"""Summarize OpenAI-pattern adoption evidence across local plugins.

This combines the three lower-level audits used by the plugin UI strategy:

- interaction-pattern extraction and coverage;
- shared non-plotting workbench demo quality;
- generated review-payload contract and workflow-scenario coverage.

It is a human-facing readiness report, not a replacement for workflow tests or
real customer-folder review.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "AdoptionReadinessIssue",
    "AdoptionReadinessReport",
    "audit_adoption_readiness",
    "build_customer_validation_case",
    "customer_validation_template",
    "infer_customer_validation_case_metadata",
    "record_customer_validation_case",
    "main",
]

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
DEFAULT_CUSTOMER_VALIDATION_MANIFEST = (
    ROOT / "docs" / "openai_pattern_customer_validation_manifest.json"
)
SEVERITY_RANK = {
    "info": 1,
    "medium": 2,
    "high": 3,
    "blocker": 4,
}


@dataclass(frozen=True)
class AdoptionReadinessIssue:
    """One finding from a lower-level OpenAI-pattern adoption audit."""

    source: str
    plugin: str
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable representation."""

        return {
            "source": self.source,
            "plugin": self.plugin,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class AdoptionReadinessReport:
    """Combined adoption-readiness evidence for the repo."""

    interaction_summary: dict[str, Any]
    demo_summary: dict[str, Any]
    contract_summary: dict[str, Any]
    pattern_catalog: list[dict[str, Any]]
    pattern_coverage: list[dict[str, Any]]
    playbook_section_coverage: list[dict[str, Any]]
    rejected_patterns: list[dict[str, Any]]
    workbench_evidence: list[dict[str, Any]]
    browser_writeback: dict[str, Any]
    customer_validation: dict[str, Any]
    validation_tiers: list[dict[str, Any]]
    next_actions: list[dict[str, Any]]
    issues: list[AdoptionReadinessIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Return a compact status for dashboards and CLI output."""

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
            "status": self.status,
            "summary": {
                "interaction": self.interaction_summary,
                "workbench_demo": self.demo_summary,
                "contract_coverage": self.contract_summary,
            },
            "patterns": self.pattern_catalog,
            "pattern_coverage": self.pattern_coverage,
            "playbook_section_coverage": self.playbook_section_coverage,
            "rejected_patterns": self.rejected_patterns,
            "workbench_evidence": self.workbench_evidence,
            "browser_writeback": self.browser_writeback,
            "customer_validation": self.customer_validation,
            "validation_tiers": self.validation_tiers,
            "next_actions": self.next_actions,
            "issues": [issue.to_dict() for issue in self.issues],
            "limits": [
                (
                    "This report proves adopted interaction contracts and "
                    "workflow-scenario evidence; it does not prove OpenAI-level "
                    "visual quality on real customer folders."
                ),
                (
                    "Native DOCX/XLSX/PDF regeneration still needs "
                    "workflow-specific validation when edits should update those "
                    "outputs."
                ),
            ],
        }


def _load_script(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _status_summary(reports: list[Any], *, count_key: str) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    issue_counts: dict[str, int] = {}
    for report in reports:
        status_counts[report.status] = status_counts.get(report.status, 0) + 1
        for issue in report.issues:
            issue_counts[issue.severity] = issue_counts.get(issue.severity, 0) + 1
    return {
        count_key: len(reports),
        "status_counts": dict(sorted(status_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
    }


def _collect_issues(
    reports: list[Any],
    *,
    source: str,
) -> list[AdoptionReadinessIssue]:
    issues: list[AdoptionReadinessIssue] = []
    for report in reports:
        for issue in report.issues:
            issues.append(
                AdoptionReadinessIssue(
                    source=source,
                    plugin=report.plugin,
                    severity=issue.severity,
                    code=issue.code,
                    message=issue.message,
                )
            )
    return issues


REQUIRED_CUSTOMER_CASE_FIELDS = (
    "case_id",
    "plugin",
    "scenario_name",
    "input_path_or_case_id",
    "language",
    "reviewer",
    "validated_at",
    "commands",
    "artifact_paths",
    "decision_summary",
    "ux_verdict",
    "ux_checks",
    "reviewer_notes",
    "status",
)
REQUIRED_CUSTOMER_ARTIFACT_PATHS = (
    "run_intake",
    "review_payload",
    "ui_decisions",
    "applied_decisions",
    "final_artifacts",
)
OPTIONAL_CUSTOMER_ARTIFACT_PATHS_TO_VERIFY = ("native_output_readback",)
CUSTOMER_CASE_STATUSES = {"pass", "partial", "blocked", "fail"}
CUSTOMER_UX_VERDICTS = {"usable", "usable_with_issues", "blocked"}
REQUIRED_CUSTOMER_UX_CHECKS = (
    "queue_clear",
    "evidence_comparison_clear",
    "decision_controls_complete",
    "edit_flow_usable",
    "artifact_handoff_clear",
    "no_blocking_issues",
)
DECISION_SUMMARY_KEYS = (
    "accepted",
    "edited",
    "rejected",
    "marked_unclear",
    "requested_more_documents",
    "skipped",
    "blocked",
)
DECISION_ACTION_TO_SUMMARY_KEY = {
    "accept": "accepted",
    "accepted": "accepted",
    "edit": "edited",
    "edited": "edited",
    "reject": "rejected",
    "rejected": "rejected",
    "mark_unclear": "marked_unclear",
    "unclear": "marked_unclear",
    "request_more_documents": "requested_more_documents",
    "more_documents": "requested_more_documents",
    "skip": "skipped",
    "skipped": "skipped",
    "block": "blocked",
    "blocked": "blocked",
}
SYNTHETIC_CUSTOMER_VALIDATION_MARKERS = (
    "adapter demo",
    "browser write-back audit",
    "browser-writeback",
    "demo payload",
    "not customer validation",
    "sample payload",
    "sample-review",
    "synthetic",
)


def _issue(
    *,
    source: str,
    plugin: str,
    severity: str,
    code: str,
    message: str,
) -> AdoptionReadinessIssue:
    return AdoptionReadinessIssue(
        source=source,
        plugin=plugin,
        severity=severity,
        code=code,
        message=message,
    )


def _customer_manifest_path(root: Path, path: Path | None) -> Path:
    if path is not None:
        return path
    return root / "docs" / DEFAULT_CUSTOMER_VALIDATION_MANIFEST.name


def _optional_report_path(root: Path, path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_absolute():
        return path
    return root / path


def _normalize_plugin_names(plugin_names: tuple[str, ...]) -> tuple[str, ...]:
    """Return stable, de-duplicated plugin names."""

    return tuple(sorted({name.strip() for name in plugin_names if name.strip()}))


def _discover_template_plugins(
    root: Path,
    *,
    expected_customer_plugins: tuple[str, ...] | None,
) -> tuple[str, ...]:
    """Return plugins that should receive customer-validation template cases."""

    if expected_customer_plugins is not None:
        return _normalize_plugin_names(expected_customer_plugins)

    plugin_root = root / "plugins"
    if not plugin_root.exists():
        return ()

    return _normalize_plugin_names(
        tuple(
            adapter_path.parent.parent.name
            for adapter_path in plugin_root.glob(
                "*/assets/review-workbench-adapter.json"
            )
        )
    )


def customer_validation_template(
    expected_plugins: tuple[str, ...],
) -> dict[str, Any]:
    """Return a JSON template for representative real-customer validation."""

    cases: list[dict[str, Any]] = []
    for plugin in _normalize_plugin_names(expected_plugins):
        cases.append(
            {
                "case_id": f"case-{plugin}-001",
                "plugin": plugin,
                "scenario_name": "TODO: representative customer scenario",
                "input_path_or_case_id": (
                    "TODO: anonymized local input path or customer case id"
                ),
                "language": "TODO: language code, for example it or en",
                "reviewer": "TODO: reviewer name",
                "validated_at": "TODO: ISO timestamp",
                "commands": [
                    "TODO: run workflow on local customer input",
                    "TODO: open local or MCP review surface",
                    "TODO: save and apply reviewer decisions",
                ],
                "artifact_paths": {
                    "run_intake": "TODO: output/run_intake.json",
                    "review_payload": "TODO: output/review_payload.json",
                    "ui_decisions": "TODO: output/ui_decisions.json",
                    "applied_decisions": "TODO: output/applied_decisions.json",
                    "final_artifacts": "TODO: output/final_artifacts.json",
                    "screenshot_paths": [
                        "TODO: screenshot path showing queue/detail/decision state"
                    ],
                    "native_output_readback": (
                        "TODO: readback path for DOCX/XLSX/PDF/report output, "
                        "or not_applicable"
                    ),
                },
                "decision_summary": {
                    "accepted": 0,
                    "edited": 0,
                    "rejected": 0,
                    "marked_unclear": 0,
                    "requested_more_documents": 0,
                    "skipped": 0,
                    "blocked": 0,
                },
                "ux_verdict": "usable_with_issues",
                "ux_checks": {name: False for name in REQUIRED_CUSTOMER_UX_CHECKS},
                "reviewer_notes": (
                    "TODO: reviewer notes on queue clarity, evidence comparison, "
                    "decision controls, edit flow, and artifact handoff"
                ),
                "status": "partial",
            }
        )

    return {
        "schema_version": "1.0",
        "purpose": (
            "Template for recording real customer-folder validation evidence. "
            "Replace TODO values with actual local run evidence before using "
            "this as the live readiness manifest."
        ),
        "cases": cases,
    }


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _manifest_path_value(manifest_dir: Path, path: Path) -> str:
    resolved_path = path.resolve()
    resolved_manifest_dir = manifest_dir.resolve()
    try:
        return str(resolved_path.relative_to(resolved_manifest_dir))
    except ValueError:
        return str(resolved_path)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _text_fragments(value: Any) -> list[str]:
    """Return string fragments from a nested JSON-like value."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        fragments: list[str] = []
        for key, child in value.items():
            if isinstance(key, str):
                fragments.append(key)
            fragments.extend(_text_fragments(child))
        return fragments
    if isinstance(value, list):
        fragments = []
        for child in value:
            fragments.extend(_text_fragments(child))
        return fragments
    return []


def _synthetic_marker_hits(payload: dict[str, Any]) -> list[str]:
    text = "\n".join(_text_fragments(payload)).lower()
    return [
        marker for marker in SYNTHETIC_CUSTOMER_VALIDATION_MARKERS if marker in text
    ]


def _customer_run_metadata_errors(run_output_dir: Path, *, plugin: str) -> list[str]:
    """Return reasons a run output folder is not acceptable real-customer evidence."""

    errors: list[str] = []
    for artifact_name in ("run_intake", "review_payload", "final_artifacts"):
        path = run_output_dir / f"{artifact_name}.json"
        try:
            payload = _load_json_object(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{artifact_name} metadata is not a JSON object: {exc}")
            continue
        payload_plugin = payload.get("plugin")
        if (
            isinstance(payload_plugin, str)
            and payload_plugin
            and payload_plugin != plugin
        ):
            errors.append(
                f"{artifact_name}.plugin is {payload_plugin!r}, expected {plugin!r}"
            )
        markers = _synthetic_marker_hits(payload)
        if markers:
            errors.append(
                f"{artifact_name} contains synthetic/demo marker(s): "
                + ", ".join(sorted(markers))
            )
    return errors


def _decision_summary_from_payload(payload: Any) -> dict[str, int]:
    summary = {key: 0 for key in DECISION_SUMMARY_KEYS}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            action = value.get("action") or value.get("decision") or value.get("status")
            if isinstance(action, str):
                summary_key = DECISION_ACTION_TO_SUMMARY_KEY.get(action.strip().lower())
                if summary_key is not None:
                    summary[summary_key] += 1
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return summary


def _decision_summary_from_run(run_output_dir: Path) -> dict[str, int]:
    ui_decisions_path = run_output_dir / "ui_decisions.json"
    if not ui_decisions_path.exists():
        return {key: 0 for key in DECISION_SUMMARY_KEYS}
    try:
        return _decision_summary_from_payload(
            json.loads(ui_decisions_path.read_text(encoding="utf-8"))
        )
    except json.JSONDecodeError:
        return {key: 0 for key in DECISION_SUMMARY_KEYS}


def _case_artifact_paths_from_run(
    *,
    manifest_dir: Path,
    run_output_dir: Path,
    screenshot_paths: tuple[Path, ...],
    native_output_readback: Path | None,
) -> tuple[dict[str, Any], list[str]]:
    artifact_paths: dict[str, Any] = {}
    missing: list[str] = []
    for name in REQUIRED_CUSTOMER_ARTIFACT_PATHS:
        file_path = run_output_dir / f"{name}.json"
        artifact_paths[name] = _manifest_path_value(manifest_dir, file_path)
        if not file_path.exists():
            missing.append(name)

    if screenshot_paths:
        artifact_paths["screenshot_paths"] = [
            _manifest_path_value(manifest_dir, path) for path in screenshot_paths
        ]
        for index, screenshot_path in enumerate(screenshot_paths, start=1):
            if not screenshot_path.exists():
                missing.append(f"screenshot_paths[{index}]")
    else:
        artifact_paths["screenshot_paths"] = []
        missing.append("screenshot_paths")

    if native_output_readback is None:
        artifact_paths["native_output_readback"] = "not_applicable"
    else:
        artifact_paths["native_output_readback"] = _manifest_path_value(
            manifest_dir,
            native_output_readback,
        )
        if not native_output_readback.exists():
            missing.append("native_output_readback")

    return artifact_paths, missing


def _customer_validation_manifest_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": "1.0",
            "purpose": (
                "Recorded real customer-folder validation evidence for the "
                "OpenAI-pattern adoption readiness scorecard."
            ),
            "cases": [],
        }
    payload = _load_json_object(path)
    if payload.get("schema_version") != "1.0":
        raise ValueError("Customer validation manifest schema_version must be '1.0'.")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Customer validation manifest must include cases[].")
    return payload


def _non_empty_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _nested_text(payload: dict[str, Any], *keys: str) -> str | None:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _non_empty_text(current)


def _first_text(*values: object) -> str | None:
    for value in values:
        text = _non_empty_text(value)
        if text is not None:
            return text
    return None


def _load_optional_run_json(run_output_dir: Path, artifact_name: str) -> dict[str, Any]:
    path = run_output_dir / f"{artifact_name}.json"
    if not path.exists():
        return {}
    try:
        return _load_json_object(path)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"Cannot infer customer validation metadata from {artifact_name}.json: {exc}"
        ) from exc


def infer_customer_validation_case_metadata(run_output_dir: Path) -> dict[str, str]:
    """Infer low-risk validation metadata from local run artifacts."""

    run_intake = _load_optional_run_json(run_output_dir, "run_intake")
    review_payload = _load_optional_run_json(run_output_dir, "review_payload")
    metadata: dict[str, str] = {}
    plugin = _first_text(
        review_payload.get("plugin"),
        review_payload.get("workflow"),
        run_intake.get("plugin"),
        run_intake.get("workflow"),
    )
    if plugin is not None:
        metadata["plugin"] = plugin
    scenario_name = _first_text(
        run_intake.get("scenario_name"),
        run_intake.get("inferred_task"),
        review_payload.get("review_type"),
        review_payload.get("workflow"),
        run_intake.get("workflow"),
        plugin,
    )
    if scenario_name is not None:
        metadata["scenario_name"] = scenario_name
    language = _first_text(
        run_intake.get("language"),
        _nested_text(run_intake, "assumptions", "language"),
        review_payload.get("language"),
        _nested_text(review_payload, "summary", "language"),
    )
    if language is not None:
        metadata["language"] = language
    return metadata


def build_customer_validation_case(
    *,
    manifest_path: Path,
    case_id: str,
    plugin: str,
    scenario_name: str,
    input_path_or_case_id: str,
    language: str,
    reviewer: str,
    run_output_dir: Path,
    screenshot_paths: tuple[Path, ...],
    native_output_readback: Path | None = None,
    status: str = "partial",
    ux_verdict: str = "usable_with_issues",
    ux_checks: tuple[str, ...] = (),
    reviewer_notes: str = "",
    commands: tuple[str, ...] = (),
    validated_at: str | None = None,
) -> dict[str, Any]:
    """Build and validate one customer-validation case without writing it."""

    if status not in CUSTOMER_CASE_STATUSES:
        raise ValueError(
            "Customer validation status must be one of: "
            + ", ".join(sorted(CUSTOMER_CASE_STATUSES))
        )
    if ux_verdict not in CUSTOMER_UX_VERDICTS:
        raise ValueError(
            "Customer validation ux_verdict must be one of: "
            + ", ".join(sorted(CUSTOMER_UX_VERDICTS))
        )
    if not reviewer_notes.strip():
        raise ValueError("Customer validation reviewer_notes must be non-empty.")
    unknown_ux_checks = sorted(set(ux_checks) - set(REQUIRED_CUSTOMER_UX_CHECKS))
    if unknown_ux_checks:
        raise ValueError(
            "Unknown customer validation UX check(s): " + ", ".join(unknown_ux_checks)
        )
    ux_check_payload = {
        name: name in set(ux_checks) for name in REQUIRED_CUSTOMER_UX_CHECKS
    }
    if (
        status == "pass"
        and ux_verdict == "usable"
        and not all(ux_check_payload.values())
    ):
        missing_ux_checks = [
            name for name, passed in ux_check_payload.items() if not passed
        ]
        raise ValueError(
            "Customer validation usable/pass cases must include UX checks: "
            + ", ".join(missing_ux_checks)
        )
    artifact_paths, missing_artifacts = _case_artifact_paths_from_run(
        manifest_dir=manifest_path.parent,
        run_output_dir=run_output_dir,
        screenshot_paths=screenshot_paths,
        native_output_readback=native_output_readback,
    )
    if missing_artifacts:
        raise ValueError(
            "Cannot record customer validation case with missing artifacts: "
            + ", ".join(missing_artifacts)
        )
    invalid_artifact_contents = _invalid_manifest_artifact_contents(
        artifact_paths,
        manifest_dir=manifest_path.parent,
    )
    if invalid_artifact_contents:
        raise ValueError(
            "Cannot record customer validation case with invalid artifact content: "
            + "; ".join(invalid_artifact_contents)
        )
    metadata_errors = _customer_run_metadata_errors(run_output_dir, plugin=plugin)
    if metadata_errors:
        raise ValueError(
            "Cannot record customer validation case with non-customer run metadata: "
            + "; ".join(metadata_errors)
        )

    return {
        "case_id": case_id,
        "plugin": plugin,
        "scenario_name": scenario_name,
        "input_path_or_case_id": input_path_or_case_id,
        "language": language,
        "reviewer": reviewer,
        "validated_at": validated_at or _utc_timestamp(),
        "commands": list(commands),
        "artifact_paths": artifact_paths,
        "decision_summary": _decision_summary_from_run(run_output_dir),
        "ux_verdict": ux_verdict,
        "ux_checks": ux_check_payload,
        "reviewer_notes": reviewer_notes,
        "status": status,
    }


def record_customer_validation_case(
    *,
    manifest_path: Path,
    case_id: str,
    plugin: str,
    scenario_name: str,
    input_path_or_case_id: str,
    language: str,
    reviewer: str,
    run_output_dir: Path,
    screenshot_paths: tuple[Path, ...],
    native_output_readback: Path | None = None,
    status: str = "partial",
    ux_verdict: str = "usable_with_issues",
    ux_checks: tuple[str, ...] = (),
    reviewer_notes: str = "",
    commands: tuple[str, ...] = (),
    validated_at: str | None = None,
) -> dict[str, Any]:
    """Upsert one customer-validation case from a local run output folder."""

    case = build_customer_validation_case(
        manifest_path=manifest_path,
        case_id=case_id,
        plugin=plugin,
        scenario_name=scenario_name,
        input_path_or_case_id=input_path_or_case_id,
        language=language,
        reviewer=reviewer,
        run_output_dir=run_output_dir,
        screenshot_paths=screenshot_paths,
        native_output_readback=native_output_readback,
        status=status,
        ux_verdict=ux_verdict,
        ux_checks=ux_checks,
        reviewer_notes=reviewer_notes,
        commands=commands,
        validated_at=validated_at,
    )
    payload = _customer_validation_manifest_payload(manifest_path)
    cases = payload["cases"]
    assert isinstance(cases, list)
    for index, existing_case in enumerate(cases):
        if isinstance(existing_case, dict) and existing_case.get("case_id") == case_id:
            cases[index] = case
            break
    else:
        cases.append(case)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return case


def _is_not_applicable_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"n/a", "na", "not applicable", "not_applicable"}


def _resolve_manifest_artifact_path(manifest_dir: Path, value: object) -> Path | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or _is_not_applicable_path(value)
    ):
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return manifest_dir / path


def _missing_manifest_artifact_paths(
    artifact_paths: dict[str, Any],
    *,
    manifest_dir: Path,
) -> list[str]:
    missing: list[str] = []
    names_to_verify = (
        REQUIRED_CUSTOMER_ARTIFACT_PATHS + OPTIONAL_CUSTOMER_ARTIFACT_PATHS_TO_VERIFY
    )
    for name in names_to_verify:
        path = _resolve_manifest_artifact_path(manifest_dir, artifact_paths.get(name))
        if path is not None and not path.exists():
            missing.append(name)
    screenshot_paths = artifact_paths.get("screenshot_paths")
    if isinstance(screenshot_paths, list):
        for index, screenshot_path in enumerate(screenshot_paths, start=1):
            path = _resolve_manifest_artifact_path(manifest_dir, screenshot_path)
            if path is not None and not path.exists():
                missing.append(f"screenshot_paths[{index}]")
    return missing


def _read_required_json_artifact(
    artifact_paths: dict[str, Any],
    *,
    manifest_dir: Path,
    name: str,
) -> tuple[Any, str | None]:
    path = _resolve_manifest_artifact_path(manifest_dir, artifact_paths.get(name))
    if path is None or not path.exists():
        return None, None
    try:
        if path.stat().st_size == 0:
            return None, f"{name} is empty"
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"{name} is not valid JSON: {exc.msg}"


def _final_artifacts_status_is_pending(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    status = payload.get("status") or payload.get("review_status")
    return isinstance(status, str) and "pending" in status.lower()


def _invalid_manifest_artifact_contents(
    artifact_paths: dict[str, Any],
    *,
    manifest_dir: Path,
) -> list[str]:
    invalid: list[str] = []
    for name in REQUIRED_CUSTOMER_ARTIFACT_PATHS:
        payload, error = _read_required_json_artifact(
            artifact_paths,
            manifest_dir=manifest_dir,
            name=name,
        )
        if error is not None:
            invalid.append(error)
            continue
        if payload is not None and not payload:
            invalid.append(f"{name} has no review evidence")
        if name == "final_artifacts" and payload is not None:
            if not isinstance(payload, dict):
                invalid.append("final_artifacts must be a JSON object")
            elif not payload.get("status") and not payload.get("review_status"):
                invalid.append("final_artifacts has no status or review_status")
            elif _final_artifacts_status_is_pending(payload):
                invalid.append("final_artifacts is still pending review")

    screenshot_paths = artifact_paths.get("screenshot_paths")
    if isinstance(screenshot_paths, list):
        for index, screenshot_path in enumerate(screenshot_paths, start=1):
            path = _resolve_manifest_artifact_path(manifest_dir, screenshot_path)
            if path is not None and path.exists() and path.stat().st_size == 0:
                invalid.append(f"screenshot_paths[{index}] is empty")

    native_output_readback = _resolve_manifest_artifact_path(
        manifest_dir,
        artifact_paths.get("native_output_readback"),
    )
    if (
        native_output_readback is not None
        and native_output_readback.exists()
        and native_output_readback.stat().st_size == 0
    ):
        invalid.append("native_output_readback is empty")

    return invalid


def _audit_customer_validation_manifest(
    root: Path,
    *,
    manifest_path: Path | None = None,
    expected_plugins: tuple[str, ...] = (),
    verify_artifact_paths: bool = False,
) -> tuple[dict[str, Any], list[AdoptionReadinessIssue]]:
    """Return real-customer validation evidence from an optional manifest."""

    path = _customer_manifest_path(root, manifest_path)
    expected_plugin_set = set(expected_plugins)
    if not path.exists():
        return (
            {
                "status": "not_assessed",
                "manifest_path": str(path),
                "case_count": 0,
                "valid_case_count": 0,
                "verified_artifact_case_count": 0,
                "artifact_path_verification": verify_artifact_paths,
                "covered_plugins": [],
                "expected_plugins": sorted(expected_plugin_set),
                "missing_expected_plugins": sorted(expected_plugin_set),
                "case_status_counts": {},
            },
            [],
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return (
            {
                "status": "needs_attention",
                "manifest_path": str(path),
                "case_count": 0,
                "valid_case_count": 0,
                "verified_artifact_case_count": 0,
                "artifact_path_verification": verify_artifact_paths,
                "covered_plugins": [],
                "expected_plugins": sorted(expected_plugin_set),
                "missing_expected_plugins": sorted(expected_plugin_set),
                "case_status_counts": {},
            },
            [
                _issue(
                    source="customer_validation",
                    plugin="manifest",
                    severity="high",
                    code="customer_validation_manifest_invalid_json",
                    message=f"Customer validation manifest is not valid JSON: {exc}",
                )
            ],
        )

    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        return (
            {
                "status": "partial",
                "manifest_path": str(path),
                "case_count": 0,
                "valid_case_count": 0,
                "verified_artifact_case_count": 0,
                "artifact_path_verification": verify_artifact_paths,
                "covered_plugins": [],
                "expected_plugins": sorted(expected_plugin_set),
                "missing_expected_plugins": sorted(expected_plugin_set),
                "case_status_counts": {},
            },
            [
                _issue(
                    source="customer_validation",
                    plugin="manifest",
                    severity="medium",
                    code="customer_validation_cases_missing",
                    message=(
                        "Customer validation manifest must include at least one "
                        "case in cases[]."
                    ),
                )
            ],
        )

    issues: list[AdoptionReadinessIssue] = []
    status_counts: dict[str, int] = {}
    covered_plugins: set[str] = set()
    valid_case_count = 0
    verified_artifact_case_count = 0
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            issues.append(
                _issue(
                    source="customer_validation",
                    plugin="manifest",
                    severity="high",
                    code="customer_validation_case_not_object",
                    message=f"Customer validation case {index} is not an object.",
                )
            )
            continue
        plugin = str(case.get("plugin") or "unknown")
        missing_fields = [
            field for field in REQUIRED_CUSTOMER_CASE_FIELDS if not case.get(field)
        ]
        case_status_is_pass = False
        ux_verdict_is_usable = False
        ux_checks_complete = False
        artifact_paths_complete = False
        screenshots_present = False
        artifact_paths_verified = not verify_artifact_paths
        if missing_fields:
            issues.append(
                _issue(
                    source="customer_validation",
                    plugin=plugin,
                    severity="medium",
                    code="customer_validation_case_fields_missing",
                    message=(
                        f"Case {case.get('case_id', index)!r} is missing fields: "
                        + ", ".join(missing_fields)
                    ),
                )
            )
        status = case.get("status")
        if not isinstance(status, str) or status not in CUSTOMER_CASE_STATUSES:
            issues.append(
                _issue(
                    source="customer_validation",
                    plugin=plugin,
                    severity="medium",
                    code="customer_validation_case_status_invalid",
                    message=(
                        f"Case {case.get('case_id', index)!r} has invalid status "
                        f"{status!r}; expected one of "
                        + ", ".join(sorted(CUSTOMER_CASE_STATUSES))
                    ),
                )
            )
        else:
            status_counts[status] = status_counts.get(status, 0) + 1
            case_status_is_pass = status == "pass"
            if status == "fail":
                issues.append(
                    _issue(
                        source="customer_validation",
                        plugin=plugin,
                        severity="high",
                        code="customer_validation_case_failed",
                        message=f"Case {case.get('case_id', index)!r} is marked fail.",
                    )
                )
        ux_verdict = case.get("ux_verdict")
        if not isinstance(ux_verdict, str) or ux_verdict not in CUSTOMER_UX_VERDICTS:
            issues.append(
                _issue(
                    source="customer_validation",
                    plugin=plugin,
                    severity="medium",
                    code="customer_validation_ux_verdict_invalid",
                    message=(
                        f"Case {case.get('case_id', index)!r} has invalid "
                        f"ux_verdict {ux_verdict!r}; expected one of "
                        + ", ".join(sorted(CUSTOMER_UX_VERDICTS))
                    ),
                )
            )
        else:
            ux_verdict_is_usable = ux_verdict == "usable"
            if status == "pass" and not ux_verdict_is_usable:
                issues.append(
                    _issue(
                        source="customer_validation",
                        plugin=plugin,
                        severity="medium",
                        code="customer_validation_ux_not_usable",
                        message=(
                            f"Case {case.get('case_id', index)!r} is marked pass "
                            f"but ux_verdict is {ux_verdict!r}."
                        ),
                    )
                )
        ux_checks = case.get("ux_checks")
        if not isinstance(ux_checks, dict):
            issues.append(
                _issue(
                    source="customer_validation",
                    plugin=plugin,
                    severity="medium",
                    code="customer_validation_ux_checks_missing",
                    message=(
                        f"Case {case.get('case_id', index)!r} must include "
                        "ux_checks as an object."
                    ),
                )
            )
        else:
            missing_ux_checks = [
                name for name in REQUIRED_CUSTOMER_UX_CHECKS if name not in ux_checks
            ]
            non_boolean_ux_checks = [
                name
                for name in REQUIRED_CUSTOMER_UX_CHECKS
                if not isinstance(ux_checks.get(name), bool)
            ]
            failed_ux_checks = [
                name
                for name in REQUIRED_CUSTOMER_UX_CHECKS
                if ux_checks.get(name) is False
            ]
            if missing_ux_checks:
                issues.append(
                    _issue(
                        source="customer_validation",
                        plugin=plugin,
                        severity="medium",
                        code="customer_validation_ux_checks_incomplete",
                        message=(
                            f"Case {case.get('case_id', index)!r} is missing UX "
                            "checks: " + ", ".join(missing_ux_checks)
                        ),
                    )
                )
            elif non_boolean_ux_checks:
                issues.append(
                    _issue(
                        source="customer_validation",
                        plugin=plugin,
                        severity="medium",
                        code="customer_validation_ux_checks_invalid",
                        message=(
                            f"Case {case.get('case_id', index)!r} has non-boolean "
                            "UX checks: " + ", ".join(non_boolean_ux_checks)
                        ),
                    )
                )
            else:
                ux_checks_complete = not failed_ux_checks
                if status == "pass" and ux_verdict == "usable" and failed_ux_checks:
                    issues.append(
                        _issue(
                            source="customer_validation",
                            plugin=plugin,
                            severity="medium",
                            code="customer_validation_ux_checks_incomplete",
                            message=(
                                f"Case {case.get('case_id', index)!r} is marked "
                                "usable/pass but failed UX checks: "
                                + ", ".join(failed_ux_checks)
                            ),
                        )
                    )
        artifact_paths = case.get("artifact_paths")
        if not isinstance(artifact_paths, dict):
            issues.append(
                _issue(
                    source="customer_validation",
                    plugin=plugin,
                    severity="medium",
                    code="customer_validation_artifact_paths_missing",
                    message=(
                        f"Case {case.get('case_id', index)!r} must include "
                        "artifact_paths as an object."
                    ),
                )
            )
        else:
            missing_artifacts = [
                name
                for name in REQUIRED_CUSTOMER_ARTIFACT_PATHS
                if not artifact_paths.get(name)
            ]
            if missing_artifacts:
                issues.append(
                    _issue(
                        source="customer_validation",
                        plugin=plugin,
                        severity="medium",
                        code="customer_validation_artifact_paths_incomplete",
                        message=(
                            f"Case {case.get('case_id', index)!r} is missing "
                            "artifact paths: " + ", ".join(missing_artifacts)
                        ),
                    )
                )
            else:
                artifact_paths_complete = True
            if not artifact_paths.get("screenshot_paths"):
                issues.append(
                    _issue(
                        source="customer_validation",
                        plugin=plugin,
                        severity="medium",
                        code="customer_validation_screenshots_missing",
                        message=(
                            f"Case {case.get('case_id', index)!r} must include "
                            "review screenshot paths."
                        ),
                    )
                )
            else:
                screenshots_present = True
            if verify_artifact_paths:
                missing_path_names = _missing_manifest_artifact_paths(
                    artifact_paths,
                    manifest_dir=path.parent,
                )
                if missing_path_names:
                    issues.append(
                        _issue(
                            source="customer_validation",
                            plugin=plugin,
                            severity="medium",
                            code="customer_validation_artifact_files_missing",
                            message=(
                                f"Case {case.get('case_id', index)!r} lists "
                                "artifact paths that do not exist: "
                                + ", ".join(missing_path_names)
                            ),
                        )
                    )
                else:
                    invalid_artifact_contents = _invalid_manifest_artifact_contents(
                        artifact_paths,
                        manifest_dir=path.parent,
                    )
                    if invalid_artifact_contents:
                        issues.append(
                            _issue(
                                source="customer_validation",
                                plugin=plugin,
                                severity="medium",
                                code="customer_validation_artifact_contents_invalid",
                                message=(
                                    f"Case {case.get('case_id', index)!r} has "
                                    "invalid artifact content: "
                                    + "; ".join(invalid_artifact_contents)
                                ),
                            )
                        )
                    else:
                        artifact_paths_verified = True
        if (
            not missing_fields
            and case_status_is_pass
            and ux_verdict_is_usable
            and ux_checks_complete
            and artifact_paths_complete
            and screenshots_present
            and artifact_paths_verified
        ):
            covered_plugins.add(plugin)
            valid_case_count += 1
            if verify_artifact_paths:
                verified_artifact_case_count += 1

    missing_expected_plugins = sorted(expected_plugin_set - covered_plugins)
    if missing_expected_plugins:
        issues.append(
            _issue(
                source="customer_validation",
                plugin="manifest",
                severity="medium",
                code="customer_validation_expected_plugins_missing",
                message=(
                    "Customer validation manifest has no passing complete case "
                    "for expected plugins: " + ", ".join(missing_expected_plugins)
                ),
            )
        )

    severe_issues = [
        issue for issue in issues if issue.severity in {"blocker", "high", "medium"}
    ]
    if any(issue.severity in {"blocker", "high"} for issue in severe_issues):
        status = "needs_attention"
    elif severe_issues or status_counts.get("partial") or status_counts.get("blocked"):
        status = "partial"
    else:
        status = "covered"

    return (
        {
            "status": status,
            "manifest_path": str(path),
            "case_count": len(cases),
            "valid_case_count": valid_case_count,
            "verified_artifact_case_count": verified_artifact_case_count,
            "artifact_path_verification": verify_artifact_paths,
            "covered_plugins": sorted(covered_plugins),
            "expected_plugins": sorted(expected_plugin_set),
            "missing_expected_plugins": missing_expected_plugins,
            "case_status_counts": dict(sorted(status_counts.items())),
        },
        issues,
    )


def _browser_reports_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    reports = payload.get("reports")
    if isinstance(reports, list):
        return [report for report in reports if isinstance(report, dict)]
    if isinstance(payload.get("plugin"), str):
        return [payload]
    return []


def _report_status_is_ok(report: dict[str, Any]) -> bool:
    return report.get("status") == "ok"


def _report_artifact_was_updated(report: dict[str, Any]) -> bool:
    return (
        report.get("csv_contains_edit") is True
        or report.get("artifact_updated") is True
    )


def _browser_report_has_severe_issue(report: dict[str, Any]) -> bool:
    issues = report.get("issues")
    if not isinstance(issues, list):
        return False
    return any(
        isinstance(issue, dict)
        and issue.get("severity") in {"blocker", "high", "medium"}
        for issue in issues
    )


def _browser_screenshot_missing(
    report: dict[str, Any],
    *,
    report_dir: Path,
) -> bool:
    screenshot = report.get("screenshot_path")
    if not isinstance(screenshot, str) or not screenshot.strip():
        return True
    path = Path(screenshot)
    if not path.is_absolute():
        path = report_dir / path
    return not path.exists() or path.stat().st_size == 0


def _audit_browser_writeback_report(
    root: Path,
    *,
    report_path: Path | None,
    expected_plugins: tuple[str, ...],
    verify_screenshots: bool = False,
) -> tuple[dict[str, Any], list[AdoptionReadinessIssue]]:
    """Return local-browser write-back mechanism evidence from an optional report."""

    expected_plugin_set = set(expected_plugins)
    path = _optional_report_path(root, report_path)
    if path is None:
        return (
            {
                "status": "not_assessed",
                "report_path": None,
                "plugin_count": 0,
                "covered_plugins": [],
                "expected_plugins": sorted(expected_plugin_set),
                "missing_expected_plugins": sorted(expected_plugin_set),
                "screenshot_verification": verify_screenshots,
            },
            [],
        )
    if not path.exists():
        return (
            {
                "status": "partial",
                "report_path": str(path),
                "plugin_count": 0,
                "covered_plugins": [],
                "expected_plugins": sorted(expected_plugin_set),
                "missing_expected_plugins": sorted(expected_plugin_set),
                "screenshot_verification": verify_screenshots,
            },
            [
                _issue(
                    source="browser_writeback",
                    plugin="report",
                    severity="medium",
                    code="browser_writeback_report_missing",
                    message=f"Browser write-back report does not exist: {path}",
                )
            ],
        )
    try:
        payload = _load_json_object(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return (
            {
                "status": "needs_attention",
                "report_path": str(path),
                "plugin_count": 0,
                "covered_plugins": [],
                "expected_plugins": sorted(expected_plugin_set),
                "missing_expected_plugins": sorted(expected_plugin_set),
                "screenshot_verification": verify_screenshots,
            },
            [
                _issue(
                    source="browser_writeback",
                    plugin="report",
                    severity="high",
                    code="browser_writeback_report_invalid",
                    message=f"Browser write-back report is not valid JSON evidence: {exc}",
                )
            ],
        )

    reports = _browser_reports_from_payload(payload)
    if not reports:
        return (
            {
                "status": "partial",
                "report_path": str(path),
                "plugin_count": 0,
                "covered_plugins": [],
                "expected_plugins": sorted(expected_plugin_set),
                "missing_expected_plugins": sorted(expected_plugin_set),
                "screenshot_verification": verify_screenshots,
            },
            [
                _issue(
                    source="browser_writeback",
                    plugin="report",
                    severity="medium",
                    code="browser_writeback_reports_missing",
                    message="Browser write-back report must include reports[] or one plugin report.",
                )
            ],
        )

    issues: list[AdoptionReadinessIssue] = []
    covered_plugins: set[str] = set()
    for index, report in enumerate(reports, start=1):
        plugin = str(report.get("plugin") or f"report[{index}]")
        if not _report_status_is_ok(report):
            issues.append(
                _issue(
                    source="browser_writeback",
                    plugin=plugin,
                    severity="medium",
                    code="browser_writeback_plugin_not_ok",
                    message=(
                        f"Browser write-back report for {plugin} has status "
                        f"{report.get('status')!r}."
                    ),
                )
            )
            continue
        if _browser_report_has_severe_issue(report):
            issues.append(
                _issue(
                    source="browser_writeback",
                    plugin=plugin,
                    severity="medium",
                    code="browser_writeback_plugin_has_issues",
                    message=f"Browser write-back report for {plugin} includes severe issues.",
                )
            )
            continue
        if not _report_artifact_was_updated(report):
            issues.append(
                _issue(
                    source="browser_writeback",
                    plugin=plugin,
                    severity="medium",
                    code="browser_writeback_target_not_updated",
                    message=(
                        f"Browser write-back report for {plugin} does not prove "
                        "the declared target artifact was updated."
                    ),
                )
            )
            continue
        if verify_screenshots and _browser_screenshot_missing(
            report, report_dir=path.parent
        ):
            issues.append(
                _issue(
                    source="browser_writeback",
                    plugin=plugin,
                    severity="medium",
                    code="browser_writeback_screenshot_missing",
                    message=(
                        f"Browser write-back report for {plugin} does not point "
                        "to an existing non-empty screenshot."
                    ),
                )
            )
            continue
        covered_plugins.add(plugin)

    missing_expected_plugins = sorted(expected_plugin_set - covered_plugins)
    if missing_expected_plugins:
        issues.append(
            _issue(
                source="browser_writeback",
                plugin="report",
                severity="medium",
                code="browser_writeback_expected_plugins_missing",
                message=(
                    "Browser write-back report has no complete mechanism evidence "
                    "for expected plugins: " + ", ".join(missing_expected_plugins)
                ),
            )
        )

    severe_issues = [
        issue for issue in issues if issue.severity in {"blocker", "high", "medium"}
    ]
    if any(issue.severity in {"blocker", "high"} for issue in severe_issues):
        status = "needs_attention"
    elif severe_issues:
        status = "partial"
    else:
        status = "covered"

    return (
        {
            "status": status,
            "report_path": str(path),
            "plugin_count": len(reports),
            "covered_plugins": sorted(covered_plugins),
            "expected_plugins": sorted(expected_plugin_set),
            "missing_expected_plugins": missing_expected_plugins,
            "screenshot_verification": verify_screenshots,
        },
        issues,
    )


def _validation_tiers(
    *,
    interaction_reports: list[Any],
    demo_reports: list[Any],
    contract_reports: list[Any],
    browser_writeback: dict[str, Any],
    customer_validation: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return explicit evidence tiers for the adoption scorecard."""

    severe_interaction = [
        issue
        for report in interaction_reports
        for issue in report.issues
        if issue.severity in {"blocker", "high", "medium"}
    ]
    severe_demo = [
        issue
        for report in demo_reports
        for issue in report.issues
        if issue.severity in {"blocker", "high", "medium"}
    ]
    severe_contract = [
        issue
        for report in contract_reports
        for issue in report.issues
        if issue.severity in {"blocker", "high", "medium"}
    ]
    return [
        {
            "tier": "interaction_contracts",
            "status": "covered" if not severe_interaction else "needs_attention",
            "evidence": (
                "OpenAI-derived interaction patterns are mapped to local rules "
                "and checked across plugin skills/MCP surfaces."
            ),
        },
        {
            "tier": "demo_ui_contracts",
            "status": "covered" if not severe_demo else "needs_attention",
            "evidence": (
                "Generated shared-workbench demo payloads exercise queue, "
                "detail, evidence, actions, edit metadata, and localization."
            ),
        },
        {
            "tier": "workflow_fixture_contracts",
            "status": "covered" if not severe_contract else "needs_attention",
            "evidence": (
                "Workflow-like fixture tests validate generated run_intake, "
                "review_payload, ui_decisions, and final_artifacts contracts."
            ),
        },
        {
            "tier": "browser_writeback_mechanism",
            "status": browser_writeback["status"],
            "evidence": (
                "Optional local-browser mechanism evidence from "
                "scripts/audit_local_review_workbench_writeback.py. This proves "
                "Save/Apply can persist decisions and target-artifact updates "
                "through the shared workbench, but it is not real-customer evidence."
            ),
        },
        {
            "tier": "real_customer_folder_validation",
            "status": customer_validation["status"],
            "evidence": (
                "Representative customer-folder manifest evidence. Requires "
                "local browser review, saved decisions, screenshots, and "
                "workflow-specific semantic/native-output acceptance checks."
            ),
        },
    ]


def _next_actions(validation_tiers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return concrete follow-up evidence requirements."""

    browser_writeback_status = next(
        (
            item["status"]
            for item in validation_tiers
            if item["tier"] == "browser_writeback_mechanism"
        ),
        "not_assessed",
    )
    real_customer_status = next(
        (
            item["status"]
            for item in validation_tiers
            if item["tier"] == "real_customer_folder_validation"
        ),
        "not_assessed",
    )
    actions: list[dict[str, Any]] = []
    if browser_writeback_status != "covered" and real_customer_status != "covered":
        actions.append(
            {
                "id": "run_browser_writeback_mechanism_audit",
                "priority": "medium",
                "description": (
                    "Run the shared local-browser write-back audit and pass its "
                    "JSON report into the readiness scorecard when mechanism "
                    "evidence is needed."
                ),
                "evidence_required": [
                    "scripts/audit_local_review_workbench_writeback.py --format json",
                    "covered generated workbench plugins",
                    "updated target artifacts",
                    "screenshots when available",
                ],
            }
        )
    if real_customer_status != "covered":
        actions.extend(
            [
                {
                    "id": "collect_representative_customer_cases",
                    "priority": "high",
                    "description": (
                        "Select anonymized representative local folders or files "
                        "for each material non-plotting workflow being validated."
                    ),
                    "evidence_required": [
                        "plugin",
                        "scenario_name",
                        "input_path_or_case_id",
                        "language",
                        "expected_review_decisions",
                    ],
                },
                {
                    "id": "run_local_review_surface",
                    "priority": "high",
                    "description": (
                        "Run the workflow from local inputs, open the MCP or "
                        "local-browser review surface, and capture queue/detail/"
                        "decision screenshots plus saved decisions."
                    ),
                    "evidence_required": [
                        "run_intake.json",
                        "review_payload.json",
                        "ui_decisions.json",
                        "screenshot_paths",
                        "ux_verdict",
                        "reviewer_notes",
                    ],
                },
                {
                    "id": "validate_final_artifact_semantics",
                    "priority": "high",
                    "description": (
                        "Apply representative accept/edit/request-more-documents "
                        "decisions and verify final artifacts, native outputs, "
                        "blockers, and caveats against the scenario expectations."
                    ),
                    "evidence_required": [
                        "applied_decisions.json",
                        "final_artifacts.json",
                        "native_output_readback",
                        "blocker_or_final_ready_status",
                    ],
                },
                {
                    "id": "record_customer_validation_manifest",
                    "priority": "medium",
                    "description": (
                        "Record the validation pass in a manifest so future "
                        "readiness reports can distinguish real-customer evidence "
                        "from fixture evidence."
                    ),
                    "evidence_required": [
                        "case_id",
                        "plugin",
                        "reviewer",
                        "validated_at",
                        "commands",
                        "artifact_paths",
                        "decision_summary",
                        "ux_verdict",
                        "reviewer_notes",
                        "status",
                    ],
                },
            ]
        )
    return actions


def audit_adoption_readiness(
    root: Path = ROOT,
    *,
    browser_writeback_report_path: Path | None = None,
    require_browser_writeback: bool = False,
    verify_browser_writeback_screenshots: bool = False,
    customer_manifest_path: Path | None = None,
    expected_customer_plugins: tuple[str, ...] | None = None,
    require_customer_validation: bool = False,
    verify_customer_artifact_paths: bool = False,
) -> AdoptionReadinessReport:
    """Return a combined OpenAI-pattern adoption readiness report."""

    interaction = _load_script(
        "audit_plugin_interaction_patterns",
        SCRIPT_DIR / "audit_plugin_interaction_patterns.py",
    )
    demo = _load_script(
        "audit_non_plotting_review_workbench_demos",
        SCRIPT_DIR / "audit_non_plotting_review_workbench_demos.py",
    )
    contract = _load_script(
        "audit_review_payload_contract_coverage",
        SCRIPT_DIR / "audit_review_payload_contract_coverage.py",
    )

    interaction_reports = interaction.audit_plugins(root)
    demo_reports = demo.audit_adapters(root)
    test_roots = (
        root / "tests" / "plugins",
        root / "plugins" / "client-file-preparation" / "tests",
    )
    contract_reports = contract.audit_contract_coverage(
        root,
        test_roots=test_roots,
    )

    demo_by_plugin = {report.plugin: report for report in demo_reports}
    contract_by_plugin = {report.plugin: report for report in contract_reports}
    workbench_plugins = sorted(set(demo_by_plugin) | set(contract_by_plugin))
    expected_customer_plugin_names = (
        tuple(expected_customer_plugins)
        if expected_customer_plugins is not None
        else tuple(workbench_plugins)
    )
    workbench_evidence = [
        {
            "plugin": plugin,
            "demo_status": (
                demo_by_plugin[plugin].status if plugin in demo_by_plugin else "missing"
            ),
            "contract_status": (
                contract_by_plugin[plugin].status
                if plugin in contract_by_plugin
                else "missing"
            ),
            "scenario_files": (
                list(contract_by_plugin[plugin].scenario_files)
                if plugin in contract_by_plugin
                else []
            ),
            "demo_item_count": (
                demo_by_plugin[plugin].item_count if plugin in demo_by_plugin else 0
            ),
        }
        for plugin in workbench_plugins
    ]

    issues = (
        _collect_issues(interaction_reports, source="interaction")
        + _collect_issues(demo_reports, source="workbench_demo")
        + _collect_issues(contract_reports, source="contract_coverage")
    )
    browser_writeback, browser_issues = _audit_browser_writeback_report(
        root,
        report_path=browser_writeback_report_path,
        expected_plugins=expected_customer_plugin_names,
        verify_screenshots=verify_browser_writeback_screenshots,
    )
    if require_browser_writeback and browser_writeback["status"] != "covered":
        browser_issues.append(
            _issue(
                source="browser_writeback",
                plugin="report",
                severity="medium",
                code="browser_writeback_required_not_covered",
                message=(
                    "Local browser write-back mechanism evidence was required, "
                    "but the supplied report does not cover all expected plugins."
                ),
            )
        )
    issues.extend(browser_issues)
    customer_validation, customer_issues = _audit_customer_validation_manifest(
        root,
        manifest_path=customer_manifest_path,
        expected_plugins=expected_customer_plugin_names,
        verify_artifact_paths=verify_customer_artifact_paths,
    )
    if require_customer_validation and customer_validation["status"] != "covered":
        customer_issues.append(
            _issue(
                source="customer_validation",
                plugin="manifest",
                severity="medium",
                code="customer_validation_required_not_covered",
                message=(
                    "Real customer-folder validation was required, but the "
                    "manifest does not have passing complete coverage for all "
                    "expected plugins."
                ),
            )
        )
    issues.extend(customer_issues)

    validation_tiers = _validation_tiers(
        interaction_reports=interaction_reports,
        demo_reports=demo_reports,
        contract_reports=contract_reports,
        browser_writeback=browser_writeback,
        customer_validation=customer_validation,
    )

    return AdoptionReadinessReport(
        interaction_summary=_status_summary(
            interaction_reports,
            count_key="plugin_count",
        ),
        demo_summary=_status_summary(demo_reports, count_key="adapter_count"),
        contract_summary=_status_summary(
            contract_reports,
            count_key="plugin_count",
        ),
        pattern_catalog=[
            pattern.to_dict() for pattern in interaction.pattern_catalog()
        ],
        pattern_coverage=[
            item.to_dict() for item in interaction.pattern_coverage(interaction_reports)
        ],
        playbook_section_coverage=[
            item.to_dict() for item in interaction.playbook_section_coverage()
        ],
        rejected_patterns=[item.to_dict() for item in interaction.rejected_patterns()],
        workbench_evidence=workbench_evidence,
        browser_writeback=browser_writeback,
        customer_validation=customer_validation,
        validation_tiers=validation_tiers,
        next_actions=_next_actions(validation_tiers),
        issues=issues,
    )


def _issues_at_or_above(
    issues: list[AdoptionReadinessIssue],
    severity: str,
) -> list[AdoptionReadinessIssue]:
    threshold = SEVERITY_RANK[severity]
    return [
        issue for issue in issues if SEVERITY_RANK.get(issue.severity, 0) >= threshold
    ]


def _markdown_report(report: AdoptionReadinessReport) -> str:
    payload = report.to_dict()
    lines = [
        "# OpenAI Pattern Adoption Readiness",
        "",
        f"Status: `{report.status}`",
        "",
        "## Summary",
        "",
        f"- Interaction plugins audited: {payload['summary']['interaction']['plugin_count']}",
        f"- Workbench demos audited: {payload['summary']['workbench_demo']['adapter_count']}",
        f"- Workflow contract plugins audited: {payload['summary']['contract_coverage']['plugin_count']}",
        f"- Browser write-back mechanism: {payload['browser_writeback']['status']}",
        f"- Customer validation manifest: {payload['customer_validation']['status']}",
        "",
        "## Pattern Coverage",
        "",
        "| Pattern | Applicable | Satisfied | Missing |",
        "| --- | ---: | ---: | --- |",
    ]
    for item in report.pattern_coverage:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["pattern_id"],
                    str(item["applicable_count"]),
                    str(item["satisfied_count"]),
                    ", ".join(item["missing_plugins"]) or "none",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Playbook Traceability",
            "",
            "| Playbook Section | Coverage | Patterns | Verifiers |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in report.playbook_section_coverage:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["section"],
                    item["coverage_mode"],
                    ", ".join(item["pattern_ids"]) or "none",
                    "<br>".join(item["verifier_paths"]),
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
    for item in report.rejected_patterns:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["playbook_text"],
                    item["local_replacement"],
                    ", ".join(item["guardrail_signals"]),
                    "<br>".join(item["verifier_paths"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Validation Tiers",
            "",
            "| Tier | Status | Evidence |",
            "| --- | --- | --- |",
        ]
    )
    for item in report.validation_tiers:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["tier"],
                    item["status"],
                    item["evidence"],
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Browser Write-Back",
            "",
            f"- Report: {report.browser_writeback['report_path'] or 'none'}",
            f"- Status: {report.browser_writeback['status']}",
            f"- Plugin reports: {report.browser_writeback['plugin_count']}",
            f"- Screenshot verification: {report.browser_writeback['screenshot_verification']}",
            "- Covered plugins: "
            + (", ".join(report.browser_writeback["covered_plugins"]) or "none"),
            "- Missing expected plugins: "
            + (
                ", ".join(report.browser_writeback["missing_expected_plugins"])
                or "none"
            ),
        ]
    )
    lines.extend(
        [
            "",
            "## Next Actions",
            "",
            "| Action | Priority | Evidence Required |",
            "| --- | --- | --- |",
        ]
    )
    if report.next_actions:
        for item in report.next_actions:
            lines.append(
                "| "
                + " | ".join(
                    [
                        item["id"],
                        item["priority"],
                        "<br>".join(item["evidence_required"]),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| none | none | none |")
    lines.extend(
        [
            "",
            "## Customer Validation",
            "",
            f"- Manifest: {report.customer_validation['manifest_path']}",
            f"- Cases: {report.customer_validation['case_count']}",
            f"- Artifact path verification: {report.customer_validation['artifact_path_verification']}",
            f"- Expected plugins: {', '.join(report.customer_validation['expected_plugins']) or 'none'}",
            f"- Covered plugins: {', '.join(report.customer_validation['covered_plugins']) or 'none'}",
            f"- Missing expected plugins: {', '.join(report.customer_validation['missing_expected_plugins']) or 'none'}",
            "",
            "## Workbench Evidence",
            "",
            "| Plugin | Demo | Contract | Scenario Tests | Items |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    for item in report.workbench_evidence:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["plugin"],
                    item["demo_status"],
                    item["contract_status"],
                    "<br>".join(item["scenario_files"]) or "none",
                    str(item["demo_item_count"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Issues",
            "",
            "| Source | Plugin | Severity | Code |",
            "| --- | --- | --- | --- |",
        ]
    )
    if report.issues:
        for issue in report.issues:
            lines.append(
                "| "
                + " | ".join(
                    [
                        issue.source,
                        issue.plugin,
                        issue.severity,
                        issue.code,
                    ]
                )
                + " |"
            )
    else:
        lines.append("| none | none | none | none |")
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {item}" for item in payload["limits"])
    return "\n".join(lines) + "\n"


def _json_report(report: AdoptionReadinessReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--browser-writeback-report",
        type=Path,
        default=None,
        help=(
            "Optional JSON report from scripts/audit_local_review_workbench_writeback.py "
            "--format json. This records local-browser mechanism evidence, not "
            "real customer-folder validation."
        ),
    )
    parser.add_argument(
        "--require-browser-writeback",
        action="store_true",
        help=(
            "Add a medium finding unless the browser write-back report covers "
            "every expected generated workbench plugin."
        ),
    )
    parser.add_argument(
        "--verify-browser-writeback-screenshots",
        action="store_true",
        help=(
            "When a browser write-back report is supplied, verify that declared "
            "screenshot paths exist and are non-empty."
        ),
    )
    parser.add_argument(
        "--customer-validation-manifest",
        type=Path,
        default=None,
        help=(
            "Optional JSON manifest of representative real-customer validation "
            "cases. Defaults to docs/openai_pattern_customer_validation_manifest.json "
            "under --root when present."
        ),
    )
    parser.add_argument(
        "--expected-customer-plugin",
        action="append",
        default=None,
        help=(
            "Plugin expected in the customer-validation manifest. May be passed "
            "multiple times. Defaults to generated non-plotting workbench plugins."
        ),
    )
    parser.add_argument(
        "--write-customer-validation-template",
        type=Path,
        default=None,
        help=(
            "Write a customer-validation manifest template for the expected "
            "plugin set and exit. Without --expected-customer-plugin, the "
            "template uses plugins with review-workbench adapters under --root."
        ),
    )
    parser.add_argument(
        "--record-customer-validation-case",
        action="store_true",
        help=(
            "Upsert one customer-validation case into the manifest from a local "
            "run output folder, then exit."
        ),
    )
    parser.add_argument(
        "--preflight-customer-validation-case",
        action="store_true",
        help=(
            "Validate one customer-validation case and the target manifest shape "
            "without writing or creating the manifest."
        ),
    )
    parser.add_argument(
        "--infer-case-metadata-from-run",
        action="store_true",
        help=(
            "For record/preflight, infer missing --plugin, --scenario-name, "
            "and --language from run_intake.json/review_payload.json. Evidence "
            "fields such as case id, input case, reviewer, screenshots, UX "
            "checks, and reviewer notes remain required."
        ),
    )
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--plugin", default=None)
    parser.add_argument("--scenario-name", default=None)
    parser.add_argument("--input-path-or-case-id", default=None)
    parser.add_argument("--language", default=None)
    parser.add_argument("--reviewer", default=None)
    parser.add_argument("--run-output-dir", type=Path, default=None)
    parser.add_argument(
        "--screenshot-path",
        action="append",
        type=Path,
        default=None,
        help="Screenshot path for the reviewed local/MCP UI. May be repeated.",
    )
    parser.add_argument("--native-output-readback", type=Path, default=None)
    parser.add_argument(
        "--validation-status",
        choices=tuple(sorted(CUSTOMER_CASE_STATUSES)),
        default="partial",
    )
    parser.add_argument(
        "--ux-verdict",
        choices=tuple(sorted(CUSTOMER_UX_VERDICTS)),
        default=None,
    )
    parser.add_argument(
        "--ux-check",
        action="append",
        choices=tuple(sorted(REQUIRED_CUSTOMER_UX_CHECKS)),
        default=None,
        help=(
            "Passed UX check for the reviewed surface. Repeat for each satisfied "
            "check. Usable/pass cases must include every required UX check."
        ),
    )
    parser.add_argument("--reviewer-notes", default=None)
    parser.add_argument(
        "--validation-command",
        action="append",
        default=None,
        help="Command or manual step used during validation. May be repeated.",
    )
    parser.add_argument("--validated-at", default=None)
    parser.add_argument(
        "--require-customer-validation",
        action="store_true",
        help=(
            "Add a medium finding unless the customer-validation manifest has "
            "passing complete cases for every expected plugin."
        ),
    )
    parser.add_argument(
        "--verify-customer-validation-artifacts",
        action="store_true",
        help=(
            "When a customer-validation manifest exists, verify that declared "
            "artifact and screenshot paths exist on disk. Relative paths are "
            "resolved from the manifest directory."
        ),
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help=(
            "Optional path where the generated markdown/json readiness report "
            "should be written. Stdout is still emitted for terminal review."
        ),
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "blocker", "high", "medium", "info"),
        default="medium",
        help="Exit nonzero when findings at or above this severity exist.",
    )
    return parser.parse_args(argv)


def _missing_record_args(
    args: argparse.Namespace,
    case_kwargs: dict[str, Any],
) -> list[str]:
    required_args = {
        "--case-id": case_kwargs["case_id"],
        "--plugin": case_kwargs["plugin"],
        "--scenario-name": case_kwargs["scenario_name"],
        "--input-path-or-case-id": case_kwargs["input_path_or_case_id"],
        "--language": case_kwargs["language"],
        "--reviewer": case_kwargs["reviewer"],
        "--run-output-dir": case_kwargs["run_output_dir"],
        "--screenshot-path": case_kwargs["screenshot_paths"],
        "--ux-verdict": case_kwargs["ux_verdict"],
        "--ux-check": case_kwargs["ux_checks"],
        "--reviewer-notes": case_kwargs["reviewer_notes"],
    }
    return [flag for flag, value in required_args.items() if not value]


def _customer_validation_case_kwargs(
    args: argparse.Namespace,
    inferred_metadata: dict[str, str],
) -> dict[str, Any]:
    return {
        "case_id": args.case_id,
        "plugin": args.plugin or inferred_metadata.get("plugin"),
        "scenario_name": args.scenario_name or inferred_metadata.get("scenario_name"),
        "input_path_or_case_id": args.input_path_or_case_id,
        "language": args.language or inferred_metadata.get("language"),
        "reviewer": args.reviewer,
        "run_output_dir": args.run_output_dir,
        "screenshot_paths": tuple(args.screenshot_path or ()),
        "native_output_readback": args.native_output_readback,
        "status": args.validation_status,
        "ux_verdict": args.ux_verdict,
        "ux_checks": tuple(args.ux_check or ()),
        "reviewer_notes": args.reviewer_notes,
        "commands": tuple(args.validation_command or ()),
        "validated_at": args.validated_at,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the combined adoption readiness report."""

    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    expected_customer_plugins = (
        tuple(args.expected_customer_plugin)
        if args.expected_customer_plugin is not None
        else None
    )
    if args.write_customer_validation_template is not None:
        template_plugins = _discover_template_plugins(
            args.root,
            expected_customer_plugins=expected_customer_plugins,
        )
        template_path = args.write_customer_validation_template
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(
            json.dumps(
                customer_validation_template(template_plugins),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        sys.stdout.write(
            "Wrote customer validation template for "
            f"{len(template_plugins)} plugin(s): {template_path}\n"
        )
        return 0

    if args.record_customer_validation_case and args.preflight_customer_validation_case:
        sys.stderr.write(
            "Choose either --record-customer-validation-case or "
            "--preflight-customer-validation-case, not both.\n"
        )
        return 1

    if args.record_customer_validation_case or args.preflight_customer_validation_case:
        inferred_metadata = {}
        if args.infer_case_metadata_from_run and args.run_output_dir is not None:
            try:
                inferred_metadata = infer_customer_validation_case_metadata(
                    args.run_output_dir
                )
            except ValueError as exc:
                sys.stderr.write(f"{exc}\n")
                return 1
        case_kwargs = _customer_validation_case_kwargs(args, inferred_metadata)
        missing_record_args = _missing_record_args(args, case_kwargs)
        if missing_record_args:
            sys.stderr.write(
                "Missing required validation-case argument(s): "
                + ", ".join(missing_record_args)
                + "\n"
            )
            return 1
        manifest_path = _customer_manifest_path(
            args.root,
            args.customer_validation_manifest,
        )
        try:
            if args.preflight_customer_validation_case:
                case = build_customer_validation_case(
                    manifest_path=manifest_path,
                    **case_kwargs,
                )
                _customer_validation_manifest_payload(manifest_path)
            else:
                case = record_customer_validation_case(
                    manifest_path=manifest_path,
                    **case_kwargs,
                )
        except (json.JSONDecodeError, ValueError) as exc:
            sys.stderr.write(f"{exc}\n")
            return 1
        if args.preflight_customer_validation_case:
            sys.stdout.write(
                "Customer validation case preflight passed "
                f"for {case['case_id']} ({case['plugin']}); "
                f"manifest not written: {manifest_path}\n"
            )
        else:
            sys.stdout.write(
                "Recorded customer validation case "
                f"{case['case_id']} for {case['plugin']}: {manifest_path}\n"
            )
        if inferred_metadata:
            sys.stdout.write(
                "Inferred case metadata: "
                + ", ".join(
                    f"{key}={value}" for key, value in sorted(inferred_metadata.items())
                )
                + "\n"
            )
        return 0

    report = audit_adoption_readiness(
        args.root,
        browser_writeback_report_path=args.browser_writeback_report,
        require_browser_writeback=args.require_browser_writeback,
        verify_browser_writeback_screenshots=args.verify_browser_writeback_screenshots,
        customer_manifest_path=args.customer_validation_manifest,
        expected_customer_plugins=expected_customer_plugins,
        require_customer_validation=args.require_customer_validation,
        verify_customer_artifact_paths=args.verify_customer_validation_artifacts,
    )
    output = _json_report(report) if args.format == "json" else _markdown_report(report)
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(output, encoding="utf-8")
    sys.stdout.write(output)
    if args.fail_on == "none":
        return 0
    return 1 if _issues_at_or_above(report.issues, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
