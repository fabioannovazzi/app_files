from __future__ import annotations

import argparse
import csv
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

__all__ = [
    "ValidationReport",
    "main",
    "validate_contract",
]

REQUIRED_FILES = {
    "run_intake": "run_intake.json",
    "review_payload": "review_payload.json",
    "ui_decisions": "ui_decisions.json",
    "final_artifacts": "final_artifacts.json",
}

REQUIRED_FIELDS = {
    "run_intake": {
        "schema_version",
        "plugin",
        "workflow",
        "created_at",
        "language",
        "input_paths",
        "output_dir",
        "inferred_task",
        "assumptions",
        "unresolved_questions",
        "dependency_check",
    },
    "review_payload": {
        "schema_version",
        "plugin",
        "workflow",
        "run_id",
        "source_paths",
        "review_type",
        "items",
        "item_count",
        "columns",
        "source_artifacts",
        "allowed_actions",
        "status",
    },
    "ui_decisions": {
        "schema_version",
        "plugin",
        "workflow",
        "run_id",
        "decided_at",
        "decision_source",
        "review_payload_path",
        "decisions",
        "decision_count",
        "status",
    },
    "final_artifacts": {
        "schema_version",
        "plugin",
        "workflow",
        "run_id",
        "outputs",
        "caveats",
        "next_actions",
        "status",
    },
}

ALLOWED_ACTIONS = {
    "accept",
    "reject",
    "edit",
    "mark_unclear",
    "request_more_documents",
    "skip",
}

ALLOWED_STATUSES = {
    "accepted",
    "blocked",
    "edited",
    "empty",
    "final_ready",
    "needs_source_data",
    "partial",
    "partial_review",
    "partial_review_applied",
    "pending",
    "pending_review",
    "ready",
    "ready_for_distribution_run",
    "ready_for_extraction",
    "ready_for_journal_bank_reconciliation_run",
    "ready_for_journal_sampling_run",
    "ready_for_mix_contribution_run",
    "ready_for_period_comparison_run",
    "ready_for_prompt_review",
    "ready_for_reconciliation_run",
    "ready_for_review",
    "ready_for_scatter_bubble_run",
    "ready_for_set_overlap_run",
    "ready_for_variance_run",
    "rejected",
    "reviewed",
    "skipped",
    "written",
    "written_pending_review",
    "written_reviewed",
}

RECOMMENDED_DATA_POSTURE_FIELDS = {
    "local_files_read",
    "external_connectors_used",
    "upload_paths_used",
}
RECOMMENDED_EXECUTION_POSTURE_FIELDS = {
    "hosted_notebook_execution_used",
    "remote_sql_execution_used",
}
EXTERNAL_DATA_POSTURE_FIELDS = {
    "external_connectors_used",
    "upload_paths_used",
}
EXTERNAL_EXECUTION_APPROVAL_REQUIRED_FIELDS = {
    "approved_at",
    "approved_by",
    "reason",
    "scope",
}
EXECUTION_TRACE_REQUIRED_FIELDS = {
    "command",
    "execution_location",
    "inputs",
    "kind",
    "outputs",
    "status",
    "step_id",
}
REVIEW_APPLICATION_TRACE_KINDS = {
    "deterministic_review_apply",
    "review_application",
    "workflow_specific_review_apply",
}
REVIEW_APPLICATION_OUTPUT_FIELDS = {
    "applied_decisions_path",
    "downstream_regenerated_paths",
    "native_regenerated_paths",
    "native_regeneration_paths",
    "original_backup_paths",
    "revision_paths",
    "structured_update_paths",
    "target_update_paths",
}
REMOTE_EXECUTION_LOCATIONS = {
    "external_connector",
    "hosted_notebook",
    "remote_warehouse",
}
PDF_PRINTABLE_RE = re.compile(rb"[\x09\x0a\x0d\x20-\x7e]{8,}")
REVIEW_HANDOFF_REQUIRED_TEXT = [
    "Review Handoff",
    "review_payload.json",
    "ui_decisions.json",
    "applied_decisions.json",
    "final_artifacts.json",
]
REVIEW_HANDOFF_TOOLS = {
    "check-entries": [
        "validate_check_entries_review",
        "render_check_entries_review",
        "save_check_entries_decisions",
        "apply_check_entries_decisions",
    ],
    "client-file-preparation": [
        "validate_client_file_preparation_review",
        "render_client_file_preparation_review",
        "save_client_file_preparation_decisions",
        "apply_client_file_preparation_decisions",
    ],
    "new-client": [
        "validate_new_client_review",
        "render_new_client_review",
        "save_new_client_decisions",
        "apply_new_client_decisions",
    ],
    "journal-sampling": [
        "validate_journal_sampling_review",
        "render_journal_sampling_review",
        "save_journal_sampling_decisions",
        "apply_journal_sampling_decisions",
    ],
    "journal-bank-reconciliation": [
        "validate_journal_bank_review",
        "render_journal_bank_review",
        "save_journal_bank_decisions",
        "apply_journal_bank_decisions",
    ],
    "deep-research-validator": [
        "validate_deep_research_review",
        "render_deep_research_review",
        "save_deep_research_decisions",
        "apply_deep_research_decisions",
    ],
    "prompt-optimizer": [
        "validate_prompt_optimizer_review",
        "render_prompt_optimizer_review",
        "save_prompt_optimizer_decisions",
        "apply_prompt_optimizer_decisions",
    ],
    "report-builder": [
        "validate_report_builder_review",
        "render_report_builder_review",
        "save_report_builder_decisions",
        "apply_report_builder_decisions",
    ],
    "concordato-plan-review": [
        "validate_concordato_plan_review",
        "render_concordato_plan_review",
        "save_concordato_plan_decisions",
        "apply_concordato_plan_decisions",
    ],
    "registro-imprese-sari": [
        "validate_registro_imprese_sari_review",
        "render_registro_imprese_sari_review",
        "save_registro_imprese_sari_decisions",
        "apply_registro_imprese_sari_decisions",
    ],
}
ROOT = Path(__file__).resolve().parents[1]
MCP_SET_PATTERN_TEMPLATE = (
    r"const\s+{name}\s*=\s*new\s+Set\s*\(\s*\[(?P<body>.*?)\]\s*\)"
)


@dataclass(frozen=True)
class ValidationReport:
    """Structured result for review-session contract validation."""

    output_dir: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_checked: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report."""

        return {
            "output_dir": self.output_dir,
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "files_checked": self.files_checked,
        }


def _read_json_object(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.exists():
        errors.append(f"{path.name} is missing")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name} is not valid JSON: {exc.msg}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{path.name} must contain a JSON object")
        return {}
    return payload


def _require_fields(name: str, payload: dict[str, Any], errors: list[str]) -> None:
    missing = sorted(REQUIRED_FIELDS[name] - set(payload))
    if missing:
        errors.append(f"{REQUIRED_FILES[name]} missing fields: {', '.join(missing)}")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _status(value: Any) -> str:
    return str(value or "")


def _is_allowed_status(status: str) -> bool:
    return status in ALLOWED_STATUSES or status.startswith("ready_for_")


def _read_plugin_mcp_string_set(plugin: Any, const_name: str) -> set[str] | None:
    """Return a simple string set declared by a plugin MCP server, if present."""

    if not isinstance(plugin, str) or not plugin.strip():
        return None
    server_path = ROOT / "plugins" / plugin / "mcp" / "server.cjs"
    if not server_path.exists():
        return None
    pattern = MCP_SET_PATTERN_TEMPLATE.format(name=re.escape(const_name))
    match = re.search(pattern, server_path.read_text(encoding="utf-8"), re.DOTALL)
    if match is None:
        return None
    return set(re.findall(r'"([^"]+)"', match.group("body")))


def _validate_statuses(payloads: dict[str, dict[str, Any]], errors: list[str]) -> None:
    for name, payload in payloads.items():
        status = _status(payload.get("status"))
        if status and not _is_allowed_status(status):
            errors.append(f"{REQUIRED_FILES[name]} has unsupported status: {status}")


def _validate_consistency(
    payloads: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    reference_plugin = payloads["review_payload"].get("plugin")
    reference_workflow = payloads["review_payload"].get("workflow")
    reference_run_id = payloads["review_payload"].get("run_id")

    for name, payload in payloads.items():
        plugin = payload.get("plugin")
        workflow = payload.get("workflow")
        if reference_plugin and plugin and plugin != reference_plugin:
            errors.append(
                f"{REQUIRED_FILES[name]} plugin {plugin!r} does not match "
                f"review_payload plugin {reference_plugin!r}"
            )
        if reference_workflow and workflow and workflow != reference_workflow:
            errors.append(
                f"{REQUIRED_FILES[name]} workflow {workflow!r} does not match "
                f"review_payload workflow {reference_workflow!r}"
            )

    for name in ("ui_decisions", "final_artifacts"):
        run_id = payloads[name].get("run_id")
        if reference_run_id and run_id and run_id != reference_run_id:
            errors.append(
                f"{REQUIRED_FILES[name]} run_id {run_id!r} does not match "
                f"review_payload run_id {reference_run_id!r}"
            )


def _validate_review_payload(
    payload: dict[str, Any],
    errors: list[str],
) -> dict[str, set[str]]:
    items = _as_list(payload.get("items"))
    mcp_item_types = _read_plugin_mcp_string_set(payload.get("plugin"), "ITEM_TYPES")
    mcp_actions = _read_plugin_mcp_string_set(payload.get("plugin"), "ALLOWED_ACTIONS")
    item_count = payload.get("item_count")
    if isinstance(item_count, int) and item_count != len(items):
        errors.append(
            "review_payload.json item_count does not match the number of items"
        )

    allowed_actions = set(
        str(action) for action in _as_list(payload.get("allowed_actions"))
    )
    unsupported = sorted(allowed_actions - ALLOWED_ACTIONS)
    if unsupported:
        errors.append(
            "review_payload.json allowed_actions contains unsupported actions: "
            + ", ".join(unsupported)
        )
    if mcp_actions is not None:
        unsupported_mcp_actions = sorted(allowed_actions - mcp_actions)
        if unsupported_mcp_actions:
            errors.append(
                "review_payload.json allowed_actions contains actions rejected by "
                "the plugin MCP validator: " + ", ".join(unsupported_mcp_actions)
            )

    item_actions: dict[str, set[str]] = {}
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"review_payload.json items[{index}] must be an object")
            continue
        item_id = str(item.get("id") or "")
        if not item_id:
            errors.append(f"review_payload.json items[{index}] is missing id")
            continue
        if item_id in seen_ids:
            errors.append(f"review_payload.json duplicate item id: {item_id}")
        seen_ids.add(item_id)
        item_type = item.get("item_type")
        if mcp_item_types is not None and (
            not isinstance(item_type, str) or item_type not in mcp_item_types
        ):
            errors.append(
                f"review_payload.json item {item_id!r} has item_type "
                f"{item_type!r}, which is rejected by the plugin MCP validator"
            )
        allowed = set(str(action) for action in _as_list(item.get("allowed_actions")))
        unsupported_item_actions = sorted(allowed - ALLOWED_ACTIONS)
        if unsupported_item_actions:
            errors.append(
                f"review_payload.json item {item_id!r} has unsupported actions: "
                + ", ".join(unsupported_item_actions)
            )
        if mcp_actions is not None:
            unsupported_item_mcp_actions = sorted(allowed - mcp_actions)
            if unsupported_item_mcp_actions:
                errors.append(
                    f"review_payload.json item {item_id!r} has actions rejected by "
                    "the plugin MCP validator: "
                    + ", ".join(unsupported_item_mcp_actions)
                )
            recommended_action = item.get("recommended_action")
            if (
                isinstance(recommended_action, str)
                and recommended_action
                and recommended_action not in mcp_actions
            ):
                errors.append(
                    f"review_payload.json item {item_id!r} recommends action "
                    f"{recommended_action!r}, which is rejected by the plugin MCP validator"
                )
        item_actions[item_id] = allowed or allowed_actions
    return item_actions


def _validate_ui_decisions(
    payload: dict[str, Any],
    item_actions: dict[str, set[str]],
    errors: list[str],
) -> None:
    decisions = _as_list(payload.get("decisions"))
    decision_count = payload.get("decision_count")
    if isinstance(decision_count, int) and decision_count != len(decisions):
        errors.append(
            "ui_decisions.json decision_count does not match the number of decisions"
        )

    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            errors.append(f"ui_decisions.json decisions[{index}] must be an object")
            continue
        item_id = str(
            decision.get("item_id")
            or decision.get("id")
            or decision.get("review_item_id")
            or ""
        )
        action = str(decision.get("action") or decision.get("decision") or "")
        if not item_id:
            errors.append(f"ui_decisions.json decisions[{index}] is missing item_id")
            continue
        if item_id not in item_actions:
            errors.append(
                f"ui_decisions.json decision references unknown item_id: {item_id}"
            )
            continue
        if action and action not in item_actions[item_id]:
            errors.append(
                f"ui_decisions.json decision {item_id!r} action {action!r} "
                "is not allowed by review_payload.json"
            )


def _validate_data_posture(
    run_intake: dict[str, Any],
    *,
    strict: bool,
    errors: list[str],
    warnings: list[str],
) -> None:
    data_posture = run_intake.get("data_posture")
    if data_posture is None:
        message = (
            "run_intake.json missing recommended data_posture; add local_files_read, "
            "external_connectors_used, upload_paths_used, remote_sql_execution_used, "
            "and hosted_notebook_execution_used"
        )
        if strict:
            errors.append(message)
        else:
            warnings.append(message)
        return
    if not isinstance(data_posture, dict):
        errors.append("run_intake.json data_posture must be an object")
        return
    missing = sorted(RECOMMENDED_DATA_POSTURE_FIELDS - set(data_posture))
    if missing:
        message = "run_intake.json data_posture missing fields: " + ", ".join(missing)
        if strict:
            errors.append(message)
        else:
            warnings.append(message)
    missing_execution = sorted(RECOMMENDED_EXECUTION_POSTURE_FIELDS - set(data_posture))
    if missing_execution:
        message = "run_intake.json data_posture missing execution fields: " + ", ".join(
            missing_execution
        )
        if strict:
            errors.append(message)
        else:
            warnings.append(message)
    for field_name in sorted(RECOMMENDED_DATA_POSTURE_FIELDS & set(data_posture)):
        if not isinstance(data_posture[field_name], list):
            errors.append(f"run_intake.json data_posture.{field_name} must be a list")
    external_entries = [
        entry
        for field_name in sorted(EXTERNAL_DATA_POSTURE_FIELDS)
        for entry in _as_list(data_posture.get(field_name))
        if entry
    ]
    remote_sql = data_posture.get("remote_sql_execution_used")
    hosted_execution = data_posture.get("hosted_notebook_execution_used")
    if remote_sql is not None and not isinstance(remote_sql, bool):
        errors.append(
            "run_intake.json data_posture.remote_sql_execution_used must be a boolean"
        )
    if hosted_execution is not None and not isinstance(hosted_execution, bool):
        errors.append(
            "run_intake.json data_posture.hosted_notebook_execution_used must be a boolean"
        )
    if external_entries or remote_sql is True or hosted_execution is True:
        approval = data_posture.get("external_execution_approval")
        if not isinstance(approval, dict) or approval.get("approved") is not True:
            errors.append(
                "run_intake.json data_posture external execution requires "
                "external_execution_approval.approved=true"
            )
            return
        missing_approval_fields = sorted(
            EXTERNAL_EXECUTION_APPROVAL_REQUIRED_FIELDS - set(approval)
        )
        if missing_approval_fields:
            errors.append(
                "run_intake.json data_posture external_execution_approval "
                "missing fields: " + ", ".join(missing_approval_fields)
            )
        for field_name in sorted(EXTERNAL_EXECUTION_APPROVAL_REQUIRED_FIELDS):
            value = approval.get(field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                errors.append(
                    "run_intake.json data_posture external_execution_approval."
                    f"{field_name} must be a non-empty string"
                )


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalize_locator_ref(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text or "://" in text:
        return text
    return posixpath.normpath(text)


def _extract_trace_locator(value: Any) -> str | None:
    if isinstance(value, str):
        locator = value.strip()
    elif isinstance(value, dict):
        locator = ""
        for key in ("path", "uri", "id", "name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                locator = candidate
                break
    else:
        locator = ""
    if not locator:
        return None
    return _normalize_locator_ref(locator)


def _validate_trace_locator_list(
    value: Any,
    *,
    prefix: str,
    errors: list[str],
) -> set[str]:
    if not isinstance(value, list):
        errors.append(f"{prefix} must be a list")
        return set()
    locators: set[str] = set()
    for index, entry in enumerate(value):
        locator = _extract_trace_locator(entry)
        if locator is None:
            errors.append(
                f"{prefix}[{index}] must be a non-empty string or object with "
                "path, uri, id, or name"
            )
            continue
        locators.add(locator)
    return locators


def _is_valid_command(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(_is_non_empty_string(entry) for entry in value)
    return False


def _trace_refs_include(expected: str, refs: set[str]) -> bool:
    expected_ref = _normalize_locator_ref(expected)
    if not expected_ref:
        return False
    for ref in refs:
        if ref == expected_ref:
            return True
        if ref.endswith(f"/{expected_ref}") or expected_ref.endswith(f"/{ref}"):
            return True
    return False


def _should_trace_output(output: dict[str, Any]) -> bool:
    return (
        _should_check_output_path(output) and output.get("status") != "backup_original"
    )


def _review_application_expected_outputs(
    review_application: dict[str, Any],
) -> set[str]:
    expected = {"final_artifacts.json"}
    for field_name in sorted(REVIEW_APPLICATION_OUTPUT_FIELDS):
        value = review_application.get(field_name)
        if isinstance(value, str) and value.strip():
            expected.add(value.strip())
        elif isinstance(value, list):
            expected.update(
                entry.strip()
                for entry in value
                if isinstance(entry, str) and entry.strip()
            )
    return expected


def _has_review_application(final_artifacts: dict[str, Any]) -> bool:
    review_application = final_artifacts.get("review_application")
    if not isinstance(review_application, dict):
        return False
    return bool(
        review_application.get("application_status")
        or review_application.get("applied_at")
        or review_application.get("applied_decisions_path")
    )


def _validate_execution_trace(
    run_intake: dict[str, Any],
    final_artifacts: dict[str, Any],
    *,
    strict: bool,
    errors: list[str],
) -> None:
    """Validate replayable local execution provenance for auditability."""

    trace = run_intake.get("execution_trace")
    if trace is None:
        if strict:
            errors.append(
                "run_intake.json missing execution_trace; add deterministic steps "
                "with step_id, kind, command, execution_location, inputs, outputs, "
                "and status"
            )
        return
    if not isinstance(trace, list):
        errors.append("run_intake.json execution_trace must be a list")
        return
    if strict and not trace:
        errors.append("run_intake.json execution_trace must include at least one step")

    output_refs: set[str] = set()
    review_apply_output_refs: set[str] = set()
    has_review_apply_step = False
    remote_locations: set[str] = set()
    for index, step in enumerate(trace):
        prefix = f"run_intake.json execution_trace[{index}]"
        if not isinstance(step, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = sorted(EXECUTION_TRACE_REQUIRED_FIELDS - set(step))
        if missing:
            errors.append(f"{prefix} missing fields: " + ", ".join(missing))
        for field_name in ("execution_location", "kind", "status", "step_id"):
            if field_name in step and not _is_non_empty_string(step[field_name]):
                errors.append(f"{prefix}.{field_name} must be a non-empty string")
        if "command" in step and not _is_valid_command(step["command"]):
            errors.append(f"{prefix}.command must be a non-empty string or argv list")
        if "inputs" in step:
            _validate_trace_locator_list(
                step["inputs"],
                prefix=f"{prefix}.inputs",
                errors=errors,
            )
        if "outputs" in step:
            step_output_refs = _validate_trace_locator_list(
                step["outputs"],
                prefix=f"{prefix}.outputs",
                errors=errors,
            )
            output_refs.update(step_output_refs)
            if step.get("kind") in REVIEW_APPLICATION_TRACE_KINDS:
                has_review_apply_step = True
                review_apply_output_refs.update(step_output_refs)
        location = str(step.get("execution_location") or "").strip()
        if location in REMOTE_EXECUTION_LOCATIONS:
            remote_locations.add(location)

    if remote_locations:
        data_posture = run_intake.get("data_posture")
        approval = (
            data_posture.get("external_execution_approval")
            if isinstance(data_posture, dict)
            else None
        )
        if not isinstance(approval, dict) or approval.get("approved") is not True:
            errors.append(
                "run_intake.json execution_trace includes remote execution_location "
                f"{', '.join(sorted(remote_locations))} but data_posture "
                "external_execution_approval.approved=true is missing"
            )

    if not strict:
        return
    outputs = final_artifacts.get("outputs")
    if not isinstance(outputs, list):
        return
    for output in outputs:
        if not isinstance(output, dict) or not _should_trace_output(output):
            continue
        path_value = str(output.get("path") or "")
        if path_value and not _trace_refs_include(path_value, output_refs):
            errors.append(
                "final_artifacts.json output "
                f"{path_value} is not listed in run_intake.json execution_trace outputs"
            )
    if _has_review_application(final_artifacts):
        if not has_review_apply_step:
            errors.append(
                "run_intake.json execution_trace missing deterministic_review_apply "
                "step for final_artifacts.json review_application"
            )
            return
        review_application = final_artifacts["review_application"]
        for path_value in sorted(
            _review_application_expected_outputs(review_application)
        ):
            if not _trace_refs_include(path_value, review_apply_output_refs):
                errors.append(
                    "final_artifacts.json review_application path "
                    f"{path_value} is not listed in a review-apply execution_trace output"
                )


def _should_check_output_path(output: dict[str, Any]) -> bool:
    status = str(output.get("status") or "")
    path_value = str(output.get("path") or "")
    if not path_value or "://" in path_value:
        return False
    return (
        not status
        or status.startswith("written")
        or status in {"backup_original", "final_ready", "updated_from_review"}
    )


def _validate_final_artifact_outputs(
    output_dir: Path,
    final_artifacts: dict[str, Any],
    *,
    strict: bool,
    errors: list[str],
    warnings: list[str],
) -> None:
    outputs = final_artifacts.get("outputs")
    if not isinstance(outputs, list):
        return
    for index, output in enumerate(outputs):
        if not isinstance(output, dict):
            errors.append(f"final_artifacts.json outputs[{index}] must be an object")
            continue
        if not _should_check_output_path(output):
            continue
        output_path = Path(str(output.get("path")))
        if not output_path.is_absolute():
            output_path = output_dir / output_path
        if output_path.exists():
            continue
        message = (
            "final_artifacts.json references missing written output: "
            f"{output.get('path')}"
        )
        if strict:
            errors.append(message)
        else:
            warnings.append(message)


def _validate_final_artifact_gallery(
    final_artifacts: dict[str, Any], errors: list[str]
) -> None:
    outputs = final_artifacts.get("outputs")
    if not isinstance(outputs, list):
        errors.append("final_artifacts.json outputs must be a list")
    else:
        for index, output in enumerate(outputs):
            if not isinstance(output, dict):
                errors.append(
                    f"final_artifacts.json outputs[{index}] must be an object"
                )
                continue
            for field_name in ("path", "kind", "status"):
                value = output.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    errors.append(
                        f"final_artifacts.json outputs[{index}].{field_name} "
                        "must be a non-empty string"
                    )
    for field_name in ("caveats", "next_actions"):
        if not isinstance(final_artifacts.get(field_name), list):
            errors.append(f"final_artifacts.json {field_name} must be a list")
    blockers = final_artifacts.get("blockers")
    if blockers is not None and not isinstance(blockers, list):
        errors.append("final_artifacts.json blockers must be a list when provided")


def _output_records_by_path(
    final_artifacts: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    records: dict[str, list[dict[str, Any]]] = {}
    outputs = final_artifacts.get("outputs")
    if not isinstance(outputs, list):
        return records
    for output in outputs:
        if not isinstance(output, dict):
            continue
        path_value = output.get("path")
        if isinstance(path_value, str) and path_value.strip():
            records.setdefault(path_value.strip(), []).append(output)
    return records


def _validate_review_handoff_card(
    output_dir: Path,
    review_payload: dict[str, Any],
    final_artifacts: dict[str, Any],
    errors: list[str],
) -> None:
    plugin = str(final_artifacts.get("plugin") or review_payload.get("plugin") or "")
    expected_tools = REVIEW_HANDOFF_TOOLS.get(plugin)
    if not expected_tools:
        return

    records = _output_records_by_path(final_artifacts).get("review_handoff.md", [])
    if not records:
        errors.append(
            f"final_artifacts.json must include review_handoff.md for {plugin} review handoff"
        )
        return
    if len(records) > 1:
        errors.append(
            "final_artifacts.json must not duplicate review_handoff.md outputs"
        )
    record = records[0]
    if str(record.get("kind") or "").lower() != "md":
        errors.append("final_artifacts.json output review_handoff.md kind must be md")
    required_text = _required_text(record)
    if isinstance(required_text, str):
        errors.append(f"final_artifacts.json output review_handoff.md {required_text}")
        required_fragments: list[str] = []
    else:
        required_fragments = required_text
    for fragment in REVIEW_HANDOFF_REQUIRED_TEXT:
        if fragment not in required_fragments:
            errors.append(
                "final_artifacts.json output review_handoff.md required_text "
                f"must include {fragment}"
            )
    qa_checks = record.get("qa_checks")
    if not isinstance(qa_checks, list) or not {
        "nonempty_text",
        "required_text",
    } <= {str(check) for check in qa_checks}:
        errors.append(
            "final_artifacts.json output review_handoff.md qa_checks must include "
            "nonempty_text and required_text"
        )

    handoff_path = output_dir / "review_handoff.md"
    if not handoff_path.exists():
        errors.append("review_handoff.md is missing")
        return
    text = _read_text_for_validation(handoff_path)
    for fragment in [*REVIEW_HANDOFF_REQUIRED_TEXT, *expected_tools]:
        if fragment not in text:
            errors.append(f"review_handoff.md is missing required text: {fragment}")


def _output_kind(output_path: Path, output: dict[str, Any]) -> str:
    kind = str(output.get("kind") or "").lower().lstrip(".")
    if kind:
        return kind
    return output_path.suffix.lower().lstrip(".") or "file"


def _read_text_for_validation(output_path: Path) -> str:
    return output_path.read_text(encoding="utf-8", errors="ignore").strip()


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "template", "noscript"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template", "noscript"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text and self.hidden_depth == 0:
            self.parts.append(text)


def _html_visible_text(text: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(text)
    parser.close()
    return " ".join(parser.parts)


def _validate_required_text(text: str, output: dict[str, Any]) -> str | None:
    required_fragments = _required_text(output)
    if isinstance(required_fragments, str):
        return required_fragments
    missing_fragments = [
        fragment for fragment in required_fragments if fragment not in text
    ]
    if missing_fragments:
        return "is missing required text: " + ", ".join(missing_fragments)
    return None


def _validate_text_file(
    output_path: Path, output: dict[str, Any], *, html_visible: bool = False
) -> str | None:
    text = _read_text_for_validation(output_path)
    if not text:
        return "is empty"
    searchable_text = _html_visible_text(text) if html_visible else text
    return _validate_required_text(searchable_text, output)


def _validate_json_file(output_path: Path) -> str | None:
    try:
        json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"is not valid JSON: {exc.msg}"
    return None


def _validate_jsonl_file(output_path: Path) -> str | None:
    lines = [
        line
        for line in output_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        return "has no JSONL records"
    for index, line in enumerate(lines, start=1):
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            return f"has invalid JSON on line {index}: {exc.msg}"
    return None


def _optional_nonnegative_int(
    output: dict[str, Any], field_name: str
) -> int | str | None:
    value = output.get(field_name)
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        return f"has invalid {field_name} metadata; expected a non-negative integer"
    return value


def _required_columns(output: dict[str, Any]) -> list[str] | str:
    value = output.get("required_columns")
    if value is None:
        return []
    if not isinstance(value, list):
        return "has invalid required_columns metadata; expected a list"
    required = [str(column).strip() for column in value if str(column).strip()]
    if len(required) != len(value):
        return "has invalid required_columns metadata; expected non-empty strings"
    return required


def _validate_table_numbers(
    row_count: int,
    columns: list[str],
    output: dict[str, Any],
) -> str | None:
    expected_row_count = _optional_nonnegative_int(output, "row_count")
    if isinstance(expected_row_count, str):
        return expected_row_count
    min_rows = _optional_nonnegative_int(output, "min_rows")
    if isinstance(min_rows, str):
        return min_rows
    required_columns = _required_columns(output)
    if isinstance(required_columns, str):
        return required_columns

    if expected_row_count is not None and row_count != expected_row_count:
        return (
            f"row_count metadata {expected_row_count} does not match actual {row_count}"
        )
    if min_rows is not None and row_count < min_rows:
        return f"has {row_count} rows, below min_rows {min_rows}"
    missing_columns = [column for column in required_columns if column not in columns]
    if missing_columns:
        return "is missing required columns: " + ", ".join(missing_columns)
    return None


def _csv_table_info(output_path: Path) -> tuple[int, list[str], str | None]:
    try:
        with output_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or [])
            row_count = sum(1 for _row in reader)
    except csv.Error as exc:
        return 0, [], f"is not a readable CSV table: {exc}"
    return row_count, columns, None


def _json_record_rows(
    payload: Any, output: dict[str, Any]
) -> tuple[list[Any], str | None]:
    records_key = output.get("records_key")
    if records_key is not None:
        if not isinstance(records_key, str) or not records_key.strip():
            return [], "has invalid records_key metadata; expected a non-empty string"
        if not isinstance(payload, dict):
            return [], "declares records_key but JSON root is not an object"
        if records_key not in payload:
            return [], f"declares records_key {records_key!r} but JSON key is missing"
        records = payload[records_key]
    elif isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = None
        for candidate_key in ("rows", "records", "items", "tables"):
            candidate = payload.get(candidate_key)
            if isinstance(candidate, list):
                records = candidate
                break
        if records is None:
            return [], "has table metadata but JSON does not contain a list record set"
    else:
        return [], "has table metadata but JSON root is not a list or object"
    if not isinstance(records, list):
        return [], "table record set is not a list"
    return records, None


def _json_columns(records: list[Any]) -> list[str]:
    columns: set[str] = set()
    for record in records:
        if isinstance(record, dict):
            columns.update(str(key) for key in record)
    return sorted(columns)


def _jsonl_table_info(output_path: Path) -> tuple[int, list[str], str | None]:
    records: list[Any] = []
    for index, line in enumerate(
        output_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            return 0, [], f"has invalid JSON on line {index}: {exc.msg}"
    return len(records), _json_columns(records), None


def _json_table_info(
    output_path: Path,
    output: dict[str, Any],
) -> tuple[int, list[str], str | None]:
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return 0, [], f"is not valid JSON: {exc.msg}"
    records, problem = _json_record_rows(payload, output)
    if problem is not None:
        return 0, [], problem
    return len(records), _json_columns(records), None


def _has_table_expectations(output: dict[str, Any]) -> bool:
    return any(
        field_name in output
        for field_name in ("row_count", "min_rows", "required_columns", "records_key")
    )


def _validate_table_expectations(
    output_path: Path,
    output: dict[str, Any],
) -> str | None:
    if not _has_table_expectations(output):
        return None
    kind = _output_kind(output_path, output)
    if kind == "csv":
        row_count, columns, problem = _csv_table_info(output_path)
    elif kind == "jsonl":
        row_count, columns, problem = _jsonl_table_info(output_path)
    elif kind == "json":
        row_count, columns, problem = _json_table_info(output_path, output)
    else:
        return f"has table metadata but kind {kind!r} is not supported"
    if problem is not None:
        return problem
    return _validate_table_numbers(row_count, columns, output)


def _validate_zip_member(output_path: Path, member_name: str) -> str | None:
    try:
        with zipfile.ZipFile(output_path) as archive:
            if member_name not in archive.namelist():
                return f"does not contain {member_name}"
    except zipfile.BadZipFile:
        return "is not a valid ZIP-based Office file"
    return None


def _local_xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _required_sheets(output: dict[str, Any]) -> list[str] | str:
    value = output.get("required_sheets")
    if value is None:
        return []
    if not isinstance(value, list):
        return "has invalid required_sheets metadata; expected a list"
    required = [str(sheet).strip() for sheet in value if str(sheet).strip()]
    if len(required) != len(value):
        return "has invalid required_sheets metadata; expected non-empty strings"
    return required


def _required_sheet_headers(output: dict[str, Any]) -> dict[str, list[str]] | str:
    value = output.get("required_sheet_headers")
    if value is None:
        return {}
    if not isinstance(value, dict):
        return "has invalid required_sheet_headers metadata; expected an object"
    required: dict[str, list[str]] = {}
    for sheet_name, headers in value.items():
        name = str(sheet_name).strip()
        if not name:
            return "has invalid required_sheet_headers metadata; expected non-empty sheet names"
        if not isinstance(headers, list):
            return "has invalid required_sheet_headers metadata; expected header lists"
        header_values = [
            str(header).strip() for header in headers if str(header).strip()
        ]
        if len(header_values) != len(headers):
            return "has invalid required_sheet_headers metadata; expected non-empty headers"
        required[name] = header_values
    return required


def _required_cells(output: dict[str, Any]) -> dict[str, dict[str, str]] | str:
    value = output.get("required_cells")
    if value is None:
        return {}
    if not isinstance(value, dict):
        return "has invalid required_cells metadata; expected an object"
    required: dict[str, dict[str, str]] = {}
    for sheet_name, cells in value.items():
        name = str(sheet_name).strip()
        if not name:
            return "has invalid required_cells metadata; expected non-empty sheet names"
        if not isinstance(cells, dict):
            return "has invalid required_cells metadata; expected cell maps"
        required[name] = {}
        for cell_ref, expected in cells.items():
            reference = str(cell_ref).strip().upper()
            if not re.fullmatch(r"[A-Z]+[1-9][0-9]*", reference):
                return "has invalid required_cells metadata; expected A1-style cell references"
            if isinstance(expected, (dict, list)) or expected is None:
                return (
                    "has invalid required_cells metadata; expected scalar cell values"
                )
            expected_text = str(expected).strip()
            if not expected_text:
                return "has invalid required_cells metadata; expected non-empty cell values"
            required[name][reference] = expected_text
    return required


def _required_text(output: dict[str, Any]) -> list[str] | str:
    value = output.get("required_text")
    if value is None:
        return []
    if not isinstance(value, list):
        return "has invalid required_text metadata; expected a list"
    required = [str(fragment).strip() for fragment in value if str(fragment).strip()]
    if len(required) != len(value):
        return "has invalid required_text metadata; expected non-empty strings"
    return required


def _relationship_targets(archive: zipfile.ZipFile) -> dict[str, str]:
    try:
        rels_xml = archive.read("xl/_rels/workbook.xml.rels")
    except KeyError:
        return {}
    try:
        root = ET.fromstring(rels_xml)
    except ET.ParseError:
        return {}
    targets: dict[str, str] = {}
    for relationship in root.iter():
        if _local_xml_name(relationship.tag) != "relationship":
            continue
        rel_id = str(relationship.attrib.get("Id") or "").strip()
        target = str(relationship.attrib.get("Target") or "").strip()
        if not rel_id or not target:
            continue
        if target.startswith("/"):
            member = target.lstrip("/")
        else:
            member = posixpath.normpath(posixpath.join("xl", target))
        targets[rel_id] = member
    return targets


def _workbook_sheet_members(
    archive: zipfile.ZipFile, workbook_xml: bytes
) -> tuple[list[str], dict[str, str], str | None]:
    try:
        root = ET.fromstring(workbook_xml)
    except ET.ParseError as exc:
        return [], {}, f"has invalid workbook XML: {exc}"
    rel_targets = _relationship_targets(archive)
    sheets = [
        element for element in root.iter() if _local_xml_name(element.tag) == "sheet"
    ]
    sheet_names = [str(sheet.attrib.get("name") or "").strip() for sheet in sheets]
    sheet_members: dict[str, str] = {}
    for index, sheet in enumerate(sheets, start=1):
        name = str(sheet.attrib.get("name") or "").strip()
        rel_id = str(
            sheet.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            or ""
        ).strip()
        member = rel_targets.get(rel_id) or f"xl/worksheets/sheet{index}.xml"
        if name:
            sheet_members[name] = member
    return sheet_names, sheet_members, None


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        xml = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    strings: list[str] = []
    for item in root.iter():
        if _local_xml_name(item.tag) != "si":
            continue
        parts = [
            text.text or "" for text in item.iter() if _local_xml_name(text.tag) == "t"
        ]
        strings.append("".join(parts))
    return strings


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = str(cell.attrib.get("t") or "")
    if cell_type == "s":
        value = next(
            (
                child.text or ""
                for child in cell.iter()
                if _local_xml_name(child.tag) == "v"
            ),
            "",
        )
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError):
            return ""
    if cell_type == "inlineStr":
        return "".join(
            child.text or ""
            for child in cell.iter()
            if _local_xml_name(child.tag) == "t"
        )
    return next(
        (
            child.text or ""
            for child in cell.iter()
            if _local_xml_name(child.tag) in {"v", "t"}
        ),
        "",
    )


def _column_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _worksheet_cell_values(
    archive: zipfile.ZipFile,
    member_name: str,
    shared_strings: list[str],
) -> dict[str, str] | str:
    try:
        worksheet_xml = archive.read(member_name)
    except KeyError:
        return f"cannot inspect cells because {member_name} is missing"
    try:
        root = ET.fromstring(worksheet_xml)
    except ET.ParseError as exc:
        return f"has invalid worksheet XML in {member_name}: {exc}"
    values: dict[str, str] = {}
    for inferred_row, row in enumerate(
        (item for item in root.iter() if _local_xml_name(item.tag) == "row"),
        start=1,
    ):
        try:
            row_index = int(str(row.attrib.get("r") or inferred_row))
        except ValueError:
            row_index = inferred_row
        for inferred_column, cell in enumerate(
            (item for item in row if _local_xml_name(item.tag) == "c"),
            start=1,
        ):
            reference = str(cell.attrib.get("r") or "").strip().upper()
            if not reference:
                reference = f"{_column_letters(inferred_column)}{row_index}"
            values[reference] = _cell_text(cell, shared_strings).strip()
    return values


def _worksheet_headers(
    archive: zipfile.ZipFile,
    member_name: str,
    shared_strings: list[str],
) -> list[str] | str:
    try:
        worksheet_xml = archive.read(member_name)
    except KeyError:
        return f"cannot inspect headers because {member_name} is missing"
    try:
        root = ET.fromstring(worksheet_xml)
    except ET.ParseError as exc:
        return f"has invalid worksheet XML in {member_name}: {exc}"
    rows = [row for row in root.iter() if _local_xml_name(row.tag) == "row"]
    if not rows:
        return []
    first_row = next(
        (row for row in rows if str(row.attrib.get("r") or "") == "1"),
        rows[0],
    )
    return [
        _cell_text(cell, shared_strings).strip()
        for cell in first_row
        if _local_xml_name(cell.tag) == "c"
    ]


def _validate_xlsx_workbook(output_path: Path, output: dict[str, Any]) -> str | None:
    # Mechanical workbook gate: a listed Excel artifact should declare at
    # least one worksheet and include worksheet XML before the UI presents it.
    required_sheets = _required_sheets(output)
    if isinstance(required_sheets, str):
        return required_sheets
    required_headers = _required_sheet_headers(output)
    if isinstance(required_headers, str):
        return required_headers
    required_cells = _required_cells(output)
    if isinstance(required_cells, str):
        return required_cells
    try:
        with zipfile.ZipFile(output_path) as archive:
            names = set(archive.namelist())
            if "xl/workbook.xml" not in names:
                return "does not contain xl/workbook.xml"
            workbook_xml = archive.read("xl/workbook.xml")
            worksheet_members = [
                name
                for name in names
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            ]
    except zipfile.BadZipFile:
        return "is not a valid ZIP-based Office file"

    with zipfile.ZipFile(output_path) as archive:
        sheet_names, sheet_members, workbook_problem = _workbook_sheet_members(
            archive, workbook_xml
        )
        if workbook_problem is not None:
            return workbook_problem

    if not sheet_names:
        return "does not declare any worksheets"
    if not worksheet_members:
        return "does not contain worksheet XML"
    missing_sheets = [name for name in required_sheets if name not in sheet_names]
    if missing_sheets:
        return "is missing required sheets: " + ", ".join(missing_sheets)
    if required_headers:
        with zipfile.ZipFile(output_path) as archive:
            shared_strings = _shared_strings(archive)
            for sheet_name, headers in required_headers.items():
                if sheet_name not in sheet_members:
                    return f"is missing required sheet for header check: {sheet_name}"
                actual_headers = _worksheet_headers(
                    archive, sheet_members[sheet_name], shared_strings
                )
                if isinstance(actual_headers, str):
                    return actual_headers
                missing_headers = [
                    header for header in headers if header not in actual_headers
                ]
                if missing_headers:
                    return (
                        f"sheet {sheet_name} is missing required headers: "
                        + ", ".join(missing_headers)
                    )
    if required_cells:
        with zipfile.ZipFile(output_path) as archive:
            shared_strings = _shared_strings(archive)
            for sheet_name, cells in required_cells.items():
                if sheet_name not in sheet_members:
                    return f"is missing required sheet for cell check: {sheet_name}"
                actual_cells = _worksheet_cell_values(
                    archive, sheet_members[sheet_name], shared_strings
                )
                if isinstance(actual_cells, str):
                    return actual_cells
                for reference, expected in cells.items():
                    actual = actual_cells.get(reference, "")
                    if actual != expected:
                        return (
                            f"sheet {sheet_name} cell {reference} expected "
                            f"{expected!r} but found {actual!r}"
                        )
    return None


def _docx_visible_text(output_path: Path) -> tuple[str, str | None]:
    try:
        with zipfile.ZipFile(output_path) as archive:
            document_xml = archive.read("word/document.xml")
    except zipfile.BadZipFile:
        return "", "is not a valid ZIP-based Office file"
    except KeyError:
        return "", "does not contain word/document.xml"
    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        return "", f"has invalid word/document.xml: {exc}"
    parts = [
        element.text or ""
        for element in root.iter()
        if _local_xml_name(element.tag) == "t"
    ]
    return " ".join(part.strip() for part in parts if part.strip()), None


def _validate_docx_file(output_path: Path, output: dict[str, Any]) -> str | None:
    # Mechanical DOCX gate: listed Word reports can declare required visible
    # sections so the gallery does not present an empty native shell as final.
    text, problem = _docx_visible_text(output_path)
    if problem is not None:
        return problem
    return _validate_required_text(text, output)


def _pdf_text_with_pypdf(output_path: Path) -> str:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(output_path))
    except (PdfReadError, OSError, TypeError, ValueError):
        return ""
    parts: list[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except (AttributeError, KeyError, PdfReadError, TypeError, ValueError):
            continue
        if page_text.strip():
            parts.append(page_text.strip())
    return "\n".join(parts)


def _pdf_printable_text(data: bytes) -> str:
    chunks = [
        chunk.decode("latin-1", errors="ignore").strip()
        for chunk in PDF_PRINTABLE_RE.findall(data)
    ]
    return "\n".join(chunk for chunk in chunks if chunk)


def _validate_pdf_file(output_path: Path, output: dict[str, Any]) -> str | None:
    data = output_path.read_bytes()
    if not data.startswith(b"%PDF"):
        return "does not start with a PDF header"
    required_fragments = _required_text(output)
    if isinstance(required_fragments, str):
        return required_fragments
    if not required_fragments:
        return None
    text = _pdf_text_with_pypdf(output_path) or _pdf_printable_text(data)
    if not text:
        return "does not expose searchable text for required_text check"
    return _validate_required_text(text, output)


def _validate_png_file(output_path: Path) -> str | None:
    # Mechanical file-format gate: enough to prove the gallery is not
    # advertising an empty or mislabeled image artifact.
    data = output_path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "does not start with a PNG signature"
    return None


def _validate_svg_file(output_path: Path) -> str | None:
    # Mechanical XML/root check only; visual quality remains workflow-specific QA.
    text = output_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return "is empty"
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return f"is not valid SVG XML: {exc}"
    root_name = root.tag.rsplit("}", 1)[-1].lower()
    if root_name != "svg":
        return "does not have an SVG root element"
    return None


def _validate_output_content(output_path: Path, output: dict[str, Any]) -> str | None:
    kind = _output_kind(output_path, output)
    problem: str | None
    if kind == "json":
        problem = _validate_json_file(output_path)
    elif kind == "jsonl":
        problem = _validate_jsonl_file(output_path)
    elif kind == "docx":
        problem = _validate_docx_file(output_path, output)
    elif kind in {"xlsx", "xlsm"}:
        problem = _validate_xlsx_workbook(output_path, output)
    elif kind == "pdf":
        problem = _validate_pdf_file(output_path, output)
    elif kind in {"png", "image/png"}:
        problem = _validate_png_file(output_path)
    elif kind in {"svg", "svg+xml", "image/svg+xml"}:
        problem = _validate_svg_file(output_path)
    elif kind in {"html", "htm"}:
        problem = _validate_text_file(output_path, output, html_visible=True)
    elif kind in {"csv", "md", "txt", "xml", "yaml", "yml", "sql"}:
        problem = _validate_text_file(output_path, output)
    elif kind == "file":
        problem = None if output_path.stat().st_size > 0 else "is empty"
    else:
        problem = None
    if problem is not None:
        return problem
    return _validate_table_expectations(output_path, output)


def _validate_final_artifact_output_content(
    output_dir: Path,
    final_artifacts: dict[str, Any],
    *,
    strict: bool,
    errors: list[str],
    warnings: list[str],
) -> None:
    outputs = final_artifacts.get("outputs")
    if not isinstance(outputs, list):
        return
    for output in outputs:
        if not isinstance(output, dict) or not _should_check_output_path(output):
            continue
        output_path = Path(str(output.get("path")))
        if not output_path.is_absolute():
            output_path = output_dir / output_path
        if not output_path.exists():
            continue
        problem = _validate_output_content(output_path, output)
        if problem is None:
            continue
        message = f"final_artifacts.json output {output.get('path')} {problem}"
        if strict:
            errors.append(message)
        else:
            warnings.append(message)


def validate_contract(
    output_dir: str | Path,
    *,
    strict_data_posture: bool = False,
    strict_execution_trace: bool = False,
    strict_output_paths: bool = False,
    strict_output_content: bool = False,
) -> ValidationReport:
    """Validate shared review-session artifacts in an output directory."""

    directory = Path(output_dir)
    errors: list[str] = []
    warnings: list[str] = []
    payloads = {
        name: _read_json_object(directory / file_name, errors)
        for name, file_name in REQUIRED_FILES.items()
    }
    files_checked = [
        file_name
        for file_name in REQUIRED_FILES.values()
        if (directory / file_name).exists()
    ]

    for name, payload in payloads.items():
        if payload:
            _require_fields(name, payload, errors)

    _validate_statuses(payloads, errors)
    _validate_consistency(payloads, errors)
    item_actions = _validate_review_payload(payloads["review_payload"], errors)
    _validate_ui_decisions(payloads["ui_decisions"], item_actions, errors)
    _validate_data_posture(
        payloads["run_intake"],
        strict=strict_data_posture,
        errors=errors,
        warnings=warnings,
    )
    _validate_execution_trace(
        payloads["run_intake"],
        payloads["final_artifacts"],
        strict=strict_execution_trace,
        errors=errors,
    )
    _validate_final_artifact_outputs(
        directory,
        payloads["final_artifacts"],
        strict=strict_output_paths,
        errors=errors,
        warnings=warnings,
    )
    _validate_final_artifact_gallery(payloads["final_artifacts"], errors)
    _validate_review_handoff_card(
        directory,
        payloads["review_payload"],
        payloads["final_artifacts"],
        errors,
    )
    _validate_final_artifact_output_content(
        directory,
        payloads["final_artifacts"],
        strict=strict_output_content,
        errors=errors,
        warnings=warnings,
    )

    return ValidationReport(
        output_dir=directory.as_posix(),
        ok=not errors,
        errors=errors,
        warnings=warnings,
        files_checked=files_checked,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate shared Codex plugin review-session JSON artifacts."
    )
    parser.add_argument("output_dir", help="Run output folder to validate.")
    parser.add_argument(
        "--strict-data-posture",
        action="store_true",
        help="Fail when run_intake.json does not include the recommended data_posture.",
    )
    parser.add_argument(
        "--strict-output-paths",
        action="store_true",
        help="Fail when final_artifacts.json references a missing written output path.",
    )
    parser.add_argument(
        "--strict-execution-trace",
        action="store_true",
        help=(
            "Fail when run_intake.json does not include replayable execution_trace "
            "steps for written final outputs."
        ),
    )
    parser.add_argument(
        "--strict-output-content",
        action="store_true",
        help="Fail when known final artifact output types are unreadable or empty.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = validate_contract(
        args.output_dir,
        strict_data_posture=args.strict_data_posture,
        strict_execution_trace=args.strict_execution_trace,
        strict_output_paths=args.strict_output_paths,
        strict_output_content=args.strict_output_content,
    )
    json.dump(report.as_dict(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
