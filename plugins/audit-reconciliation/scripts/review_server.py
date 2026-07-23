from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import re
import shutil
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

__all__ = [
    "apply_decisions",
    "build_session_payload",
    "main",
    "render_review_html",
    "save_decisions",
    "serve_review",
]

SCHEMA_VERSION = "1.0"
PLUGIN_NAME = "audit-reconciliation"
WORKFLOW_NAME = "audit-reconciliation"
TOOL_VALIDATE = "validate_audit_reconciliation_review"
TOOL_RENDER = "render_audit_reconciliation_review"
TOOL_SAVE = "save_audit_reconciliation_decisions"
TOOL_APPLY = "apply_audit_reconciliation_decisions"
MAX_ITEMS = 2500
MAX_DECISION_TEXT_LENGTH = 10_000
ALLOWED_ACTIONS = {
    "accept",
    "reject",
    "edit",
    "mark_unclear",
    "request_more_documents",
    "skip",
}
ACTION_STATUSES = {
    "accept": "accepted",
    "reject": "rejected",
    "edit": "edited",
    "mark_unclear": "needs_evidence",
    "request_more_documents": "needs_evidence",
    "skip": "skipped",
}
BLOCKING_ACTIONS = {"reject", "mark_unclear", "request_more_documents"}
LOGGER = logging.getLogger(__name__)


def _validate_loopback_host(host: str) -> str:
    """Enforce the fixed local-only security boundary before socket binding."""

    normalized = host.strip()
    if normalized.lower() == "localhost":
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise ValueError(
            "review server host must be localhost or an IPv4 loopback address"
        ) from exc
    if not address.is_loopback or address.version != 4:
        raise ValueError(
            "review server host must be localhost or an IPv4 loopback address"
        )
    return normalized


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json_object(path: Path, *, required: bool = False) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise ValueError(f"{path.name} is required in the output folder")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path.name} is not readable JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _output_dir(path: str | Path) -> Path:
    output_dir = Path(path).expanduser().resolve()
    if not output_dir.is_dir():
        raise ValueError(f"output folder does not exist: {output_dir}")
    return output_dir


def _bounded_optional_string(value: Any, field_path: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_path} must be a string when provided")
    if len(value) > MAX_DECISION_TEXT_LENGTH:
        raise ValueError(f"{field_path} exceeds {MAX_DECISION_TEXT_LENGTH} characters")
    return value.strip()


def _require_string(value: Any, field_path: str) -> str:
    text = _bounded_optional_string(value, field_path)
    if not text:
        raise ValueError(f"{field_path} must be a non-empty string")
    return text


def _validate_item(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"review_payload.items[{index}] must be an object")
    _require_string(item.get("id"), f"review_payload.items[{index}].id")
    _require_string(item.get("item_type"), f"review_payload.items[{index}].item_type")
    _require_string(item.get("title"), f"review_payload.items[{index}].title")
    allowed_actions = item.get("allowed_actions")
    if not isinstance(allowed_actions, list) or not allowed_actions:
        raise ValueError(
            f"review_payload.items[{index}].allowed_actions must be a non-empty array"
        )
    for action in allowed_actions:
        if action not in ALLOWED_ACTIONS:
            raise ValueError(
                "review_payload.items"
                f"[{index}].allowed_actions contains unsupported action: {action}"
            )
    recommended_action = item.get("recommended_action")
    if recommended_action is not None and recommended_action not in ALLOWED_ACTIONS:
        raise ValueError(
            f"review_payload.items[{index}].recommended_action is not supported"
        )
    return item


def _validate_review_payload(review_payload: Any) -> dict[str, Any]:
    if not isinstance(review_payload, dict):
        raise ValueError("review_payload must be an object")
    _require_string(
        review_payload.get("schema_version"), "review_payload.schema_version"
    )
    if review_payload.get("plugin") != PLUGIN_NAME:
        raise ValueError(f'review_payload.plugin must be "{PLUGIN_NAME}"')
    _require_string(review_payload.get("workflow"), "review_payload.workflow")
    _require_string(review_payload.get("run_id"), "review_payload.run_id")
    items = review_payload.get("items")
    if not isinstance(items, list):
        raise ValueError("review_payload.items must be an array")
    if len(items) > MAX_ITEMS:
        raise ValueError(f"review_payload.items exceeds {MAX_ITEMS} items")
    if review_payload.get("item_count") != len(items):
        raise ValueError(
            "review_payload.item_count must equal review_payload.items.length"
        )
    for index, item in enumerate(items):
        _validate_item(item, index)
    return review_payload


def build_session_payload(output_dir: str | Path) -> dict[str, Any]:
    """Load the review payload served to the local browser page."""

    directory = _output_dir(output_dir)
    run_intake = _read_json_object(directory / "run_intake.json", required=True)
    review_payload = _validate_review_payload(
        _read_json_object(directory / "review_payload.json", required=True)
    )
    ui_decisions = _read_json_object(directory / "ui_decisions.json")
    final_artifacts = _read_json_object(directory / "final_artifacts.json")
    if (
        run_intake.get("run_id")
        and run_intake.get("run_id") != review_payload["run_id"]
    ):
        raise ValueError("run_intake.run_id must match review_payload.run_id")
    return {
        "widget_type": "audit_reconciliation_review",
        "run_intake": run_intake,
        "review_payload": review_payload,
        "ui_decisions": ui_decisions or _empty_ui_decisions(review_payload),
        "final_artifacts": final_artifacts or None,
        "decision_policy": {
            "save_tool": TOOL_SAVE,
            "apply_tool": TOOL_APPLY,
            "can_persist": True,
            "fallback": "local_review_server",
        },
    }


def _empty_ui_decisions(review_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": review_payload.get("schema_version", SCHEMA_VERSION),
        "plugin": review_payload.get("plugin", PLUGIN_NAME),
        "workflow": review_payload.get("workflow", WORKFLOW_NAME),
        "run_id": review_payload["run_id"],
        "decided_at": None,
        "decision_source": "not_collected",
        "review_payload_path": "review_payload.json",
        "decisions": [],
        "decision_count": 0,
        "item_count": review_payload["item_count"],
        "status": "pending_review",
    }


def _requested_documents(value: Any, field_path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_path} must be an array when provided")
    documents: list[str] = []
    for index, entry in enumerate(value):
        document = _bounded_optional_string(entry, f"{field_path}[{index}]")
        if not document:
            raise ValueError(f"{field_path}[{index}] must be a non-empty string")
        documents.append(document)
    return documents


def _normalize_decision(
    decision: Any,
    *,
    item_by_id: dict[str, dict[str, Any]],
    seen_ids: set[str],
    decided_at: str,
    index: int,
) -> dict[str, Any]:
    if not isinstance(decision, dict):
        raise ValueError(f"decisions[{index}] must be an object")
    item_id = _bounded_optional_string(
        decision.get("item_id", decision.get("id")),
        f"decisions[{index}].item_id",
    )
    if not item_id:
        raise ValueError(f"decisions[{index}].item_id must be a non-empty string")
    if item_id in seen_ids:
        raise ValueError(f"decisions contains duplicate item_id: {item_id}")
    seen_ids.add(item_id)
    item = item_by_id.get(item_id)
    if item is None:
        raise ValueError(
            f"decisions[{index}].item_id is not in review_payload.items: {item_id}"
        )
    action = _bounded_optional_string(
        decision.get("action"),
        f"decisions[{index}].action",
    )
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"decisions[{index}].action is not supported: {action}")
    if action not in item["allowed_actions"]:
        raise ValueError(
            f"decisions[{index}].action is not allowed for item {item_id}: {action}"
        )
    reviewer_note = _bounded_optional_string(
        decision.get("reviewer_note", decision.get("note")),
        f"decisions[{index}].reviewer_note",
    )
    edit_value = _bounded_optional_string(
        decision.get("edit_value", decision.get("user_text")),
        f"decisions[{index}].edit_value",
    )
    if action == "edit" and not edit_value:
        raise ValueError(
            f"decisions[{index}].edit_value is required when action is edit"
        )
    normalized = {
        "item_id": item_id,
        "item_type": item["item_type"],
        "title": item["title"],
        "action": action,
        "status": ACTION_STATUSES[action],
        "decided_at": decided_at,
    }
    requested_documents = _requested_documents(
        decision.get("requested_documents"),
        f"decisions[{index}].requested_documents",
    )
    if reviewer_note:
        normalized["reviewer_note"] = reviewer_note
    if edit_value:
        normalized["edit_value"] = edit_value
    if requested_documents:
        normalized["requested_documents"] = requested_documents
    return normalized


def _build_ui_decisions(
    output_dir: str | Path,
    input_args: dict[str, Any],
) -> dict[str, Any]:
    session = build_session_payload(output_dir)
    review_payload = session["review_payload"]
    if not isinstance(input_args.get("decisions"), list):
        raise ValueError("decisions must be an array")
    raw_decisions = input_args["decisions"]
    if len(raw_decisions) > review_payload["item_count"]:
        raise ValueError("decisions cannot exceed review_payload.items.length")
    decided_at = _utc_now()
    item_by_id = {item["id"]: item for item in review_payload["items"]}
    seen_ids: set[str] = set()
    decisions = [
        _normalize_decision(
            decision,
            item_by_id=item_by_id,
            seen_ids=seen_ids,
            decided_at=decided_at,
            index=index,
        )
        for index, decision in enumerate(raw_decisions)
    ]
    reviewer = _bounded_optional_string(input_args.get("reviewer"), "reviewer")
    status = (
        "pending_review"
        if not decisions
        else (
            "reviewed"
            if len(decisions) == review_payload["item_count"]
            else "partial_review"
        )
    )
    ui_decisions = {
        "schema_version": review_payload["schema_version"],
        "plugin": review_payload["plugin"],
        "workflow": review_payload["workflow"],
        "run_id": review_payload["run_id"],
        "decided_at": decided_at if decisions else None,
        "decision_source": "local_review_server",
        "review_payload_path": "review_payload.json",
        "decisions": decisions,
        "decision_count": len(decisions),
        "item_count": review_payload["item_count"],
        "status": status,
    }
    if reviewer:
        ui_decisions["reviewer"] = reviewer
    return ui_decisions


def save_decisions(
    output_dir: str | Path,
    input_args: dict[str, Any],
) -> dict[str, Any]:
    """Validate and persist browser review decisions to ui_decisions.json."""

    directory = _output_dir(output_dir)
    ui_decisions = _build_ui_decisions(directory, input_args)
    decision_output_path = directory / "ui_decisions.json"
    _write_json(decision_output_path, ui_decisions)
    return {
        "ok": True,
        "validation_type": "audit_reconciliation_decisions",
        "run_id": ui_decisions["run_id"],
        "decision_count": ui_decisions["decision_count"],
        "item_count": ui_decisions["item_count"],
        "status": ui_decisions["status"],
        "persisted": True,
        "ui_decisions_path": decision_output_path.as_posix(),
        "message": (
            f"Saved {ui_decisions['decision_count']} Audit Reconciliation decisions."
        ),
        "ui_decisions": ui_decisions,
    }


def _short_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _application_effect(
    decision: dict[str, Any],
    item: dict[str, Any],
    applied_at: str,
) -> dict[str, Any]:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    target_artifact = (
        _short_string(data.get("target_artifact"))
        or _short_string(item.get("output_path"))
        or _short_string(data.get("path"))
    )
    target_path = (
        _short_string(data.get("target_path"))
        or _short_string(data.get("field_path"))
        or _short_string(data.get("field"))
    )
    target_id_field = _short_string(data.get("target_id_field")) or _short_string(
        data.get("record_id_field")
    )
    target_record_id = _short_string(data.get("target_record_id")) or _short_string(
        data.get("record_id")
    )
    target_field = _short_string(data.get("target_field")) or _short_string(
        data.get("edit_field")
    )
    target_records_key = _short_string(data.get("target_records_key")) or _short_string(
        data.get("records_key")
    )
    requires_followup = decision["action"] in BLOCKING_ACTIONS
    effect = {
        "item_id": decision["item_id"],
        "item_type": decision["item_type"],
        "title": decision["title"],
        "action": decision["action"],
        "status": decision["status"],
        "applied_at": applied_at,
        "applied": True,
        "requires_followup": requires_followup,
        "target_artifact": target_artifact or None,
        "target_path": target_path or None,
        "target_id_field": target_id_field or None,
        "target_record_id": target_record_id or None,
        "target_field": target_field or None,
        "target_records_key": target_records_key or None,
        "source_path": _short_string(item.get("source_path")) or None,
        "artifact_update": (
            "revision_artifact_pending"
            if decision["action"] == "edit"
            else ("decision_manifest_only" if target_artifact else "review_record_only")
        ),
    }
    for field in ("reviewer_note", "edit_value", "requested_documents"):
        if field in decision:
            effect[field] = decision[field]
    return effect


def _safe_path_segment(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", _short_string(value)).strip("-._")
    return cleaned or fallback


def _resolve_safe_output_path(output_dir: Path, value: Any) -> tuple[str, Path] | None:
    raw_path = _short_string(value)
    if not raw_path or Path(raw_path).is_absolute():
        return None
    candidate = (output_dir / raw_path).resolve()
    try:
        relative = candidate.relative_to(output_dir.resolve()).as_posix()
    except ValueError:
        return None
    return relative, candidate


def _structured_update_spec(effect: dict[str, Any]) -> dict[str, str] | None:
    if effect.get("action") != "edit" or not _short_string(effect.get("edit_value")):
        return None
    if not (
        effect.get("target_artifact")
        and effect.get("target_id_field")
        and effect.get("target_record_id")
        and effect.get("target_field")
    ):
        return None
    return {
        "id_field": _short_string(effect.get("target_id_field")),
        "record_id": _short_string(effect.get("target_record_id")),
        "target_field": _short_string(effect.get("target_field")),
        "records_key": _short_string(effect.get("target_records_key")),
    }


def _update_matching_record(
    records: list[Any],
    spec: dict[str, str],
    edit_value: str,
) -> int:
    updated_rows = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get(spec["id_field"]) or "") != spec["record_id"]:
            continue
        record[spec["target_field"]] = edit_value
        updated_rows += 1
    if updated_rows != 1:
        raise ValueError(
            "structured edit expected exactly one row for "
            f"{spec['id_field']}={spec['record_id']}, found {updated_rows}"
        )
    return updated_rows


def _update_json_artifact(
    path: Path,
    effect: dict[str, Any],
    spec: dict[str, str],
) -> tuple[int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    edit_value = _short_string(effect.get("edit_value"))
    if isinstance(payload, list):
        updated_rows = _update_matching_record(payload, spec, edit_value)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        return updated_rows, len(payload)
    if (
        isinstance(payload, dict)
        and spec["records_key"]
        and isinstance(payload.get(spec["records_key"]), list)
    ):
        records = payload[spec["records_key"]]
        updated_rows = _update_matching_record(records, spec, edit_value)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        return updated_rows, len(records)
    if (
        isinstance(payload, dict)
        and str(payload.get(spec["id_field"]) or "") == spec["record_id"]
    ):
        payload[spec["target_field"]] = edit_value
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        return 1, 1
    raise ValueError("JSON structured edit requires an object, array, or records key")


def _original_backup_path(effect: dict[str, Any], target_relative_path: str) -> str:
    target = Path(target_relative_path)
    suffix = target.suffix or ".json"
    stem = target.stem or "artifact"
    item_id = _safe_path_segment(effect.get("item_id"), "item")
    return (Path("revisions") / "originals" / f"{stem}__{item_id}{suffix}").as_posix()


def _write_structured_artifact_updates(
    output_dir: Path,
    effects: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    target_outputs: list[dict[str, Any]] = []
    backup_outputs: list[dict[str, Any]] = []
    for effect in effects:
        spec = _structured_update_spec(effect)
        if spec is None:
            continue
        resolved = _resolve_safe_output_path(output_dir, effect.get("target_artifact"))
        if resolved is None:
            continue
        target_relative_path, target_path = resolved
        if target_path.suffix.lower() != ".json" or not target_path.exists():
            continue
        backup_relative_path = _original_backup_path(effect, target_relative_path)
        backup_path = output_dir / backup_relative_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        if not backup_path.exists():
            shutil.copy2(target_path, backup_path)
        updated_rows, row_count = _update_json_artifact(target_path, effect, spec)
        effect["target_artifact"] = target_relative_path
        effect["original_artifact_backup"] = backup_relative_path
        effect["artifact_update"] = "structured_artifact_updated"
        effect["structured_update"] = {
            "id_field": spec["id_field"],
            "record_id": spec["record_id"],
            "target_field": spec["target_field"],
            "records_key": spec["records_key"],
            "updated_rows": updated_rows,
        }
        target_outputs.append(
            {
                "path": target_relative_path,
                "kind": "json",
                "status": "updated_from_review",
                "item_id": effect["item_id"],
                "row_count": row_count,
                "required_columns": [spec["id_field"], spec["target_field"]],
            }
        )
        backup_outputs.append(
            {
                "path": backup_relative_path,
                "kind": "json",
                "status": "backup_original",
                "source_artifact": target_relative_path,
                "item_id": effect["item_id"],
            }
        )
    return target_outputs, backup_outputs


def _application_status(effects: list[dict[str, Any]], item_count: int) -> str:
    if not effects:
        return "pending_review"
    if any(effect["requires_followup"] for effect in effects):
        return "blocked"
    if len(effects) < item_count:
        return "partial_review_applied"
    return "final_ready"


def _upsert_output(
    outputs: list[dict[str, Any]],
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    for index, output in enumerate(outputs):
        if isinstance(output, dict) and output.get("path") == record["path"]:
            outputs[index] = {**output, **record}
            return outputs
    outputs.append(record)
    return outputs


def _final_artifacts_with_application(
    output_dir: Path,
    applied_decisions: dict[str, Any],
    target_outputs: list[dict[str, Any]] | None = None,
    backup_outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    current = _read_json_object(output_dir / "final_artifacts.json")
    outputs = list(
        current.get("outputs") if isinstance(current.get("outputs"), list) else []
    )
    _upsert_output(
        outputs,
        {"path": "ui_decisions.json", "kind": "json", "status": "written_reviewed"},
    )
    _upsert_output(
        outputs,
        {
            "path": "applied_decisions.json",
            "kind": "json",
            "status": applied_decisions["application_status"],
        },
    )
    for output in target_outputs or []:
        _upsert_output(outputs, output)
    for output in backup_outputs or []:
        _upsert_output(outputs, output)
    final_artifacts = {
        **current,
        "schema_version": current.get("schema_version", SCHEMA_VERSION),
        "plugin": current.get("plugin", PLUGIN_NAME),
        "workflow": current.get("workflow", WORKFLOW_NAME),
        "run_id": current.get("run_id", applied_decisions["run_id"]),
        "outputs": outputs,
        "status": applied_decisions["application_status"],
        "review_application": {
            "applied_at": applied_decisions["applied_at"],
            "application_status": applied_decisions["application_status"],
            "decision_count": applied_decisions["decision_count"],
            "item_count": applied_decisions["item_count"],
            "blocker_count": applied_decisions["blocker_count"],
            "target_update_count": applied_decisions.get("target_update_count", 0),
            "target_update_paths": applied_decisions.get("target_update_paths", []),
            "structured_update_count": applied_decisions.get(
                "structured_update_count", 0
            ),
            "structured_update_paths": applied_decisions.get(
                "structured_update_paths", []
            ),
            "original_backup_paths": applied_decisions.get("original_backup_paths", []),
            "applied_decisions_path": "applied_decisions.json",
        },
    }
    return final_artifacts


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _review_application_trace_outputs(
    applied_decisions: dict[str, Any],
    final_artifacts: dict[str, Any],
) -> list[str]:
    outputs: list[Any] = [
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    review_application = final_artifacts.get("review_application")
    if not isinstance(review_application, dict):
        review_application = {}
    for field_name in [
        "applied_decisions_path",
        "revision_paths",
        "target_update_paths",
        "structured_update_paths",
        "native_regeneration_paths",
        "native_regenerated_paths",
        "downstream_regenerated_paths",
        "original_backup_paths",
    ]:
        value = review_application.get(field_name, applied_decisions.get(field_name))
        if isinstance(value, list):
            outputs.extend(value)
        else:
            outputs.append(value)
    return _unique_strings(outputs)


def _append_review_application_trace(
    output_dir: Path,
    applied_decisions: dict[str, Any],
    final_artifacts: dict[str, Any],
) -> Path | None:
    """Record the deterministic local decision-application step for auditability."""

    run_intake_path = output_dir / "run_intake.json"
    run_intake = _read_json_object(run_intake_path)
    if not run_intake:
        return None
    trace = run_intake.get("execution_trace")
    if not isinstance(trace, list):
        trace = []
    applied_at = str(applied_decisions.get("applied_at") or _utc_now())
    step_id_suffix = re.sub(r"[^A-Za-z0-9]+", "_", applied_at).strip("_")
    trace.append(
        {
            "step_id": f"{WORKFLOW_NAME}_review_apply_{step_id_suffix}",
            "kind": "deterministic_review_apply",
            "status": "passed",
            "execution_location": "local_codex_workspace",
            "command": ["audit-reconciliation-review-server", "apply_decisions"],
            "inputs": _unique_strings(
                [
                    applied_decisions.get("review_payload", {}).get(
                        "path", "review_payload.json"
                    ),
                    "ui_decisions.json",
                    "final_artifacts.json",
                ]
            ),
            "outputs": _review_application_trace_outputs(
                applied_decisions,
                final_artifacts,
            ),
        }
    )
    run_intake["execution_trace"] = trace
    _write_json(run_intake_path, run_intake)
    return run_intake_path


def apply_decisions(
    output_dir: str | Path,
    input_args: dict[str, Any],
) -> dict[str, Any]:
    """Persist browser review decisions and write application manifests."""

    directory = _output_dir(output_dir)
    ui_decisions = _build_ui_decisions(directory, input_args)
    review_payload = build_session_payload(directory)["review_payload"]
    item_by_id = {item["id"]: item for item in review_payload["items"]}
    applied_at = _utc_now()
    effects = [
        _application_effect(decision, item_by_id[decision["item_id"]], applied_at)
        for decision in ui_decisions["decisions"]
    ]
    target_outputs, backup_outputs = _write_structured_artifact_updates(
        directory,
        effects,
    )
    structured_update_paths = [
        effect["target_artifact"]
        for effect in effects
        if effect.get("artifact_update") == "structured_artifact_updated"
    ]
    blocker_count = sum(1 for effect in effects if effect["requires_followup"])
    application_status = _application_status(effects, review_payload["item_count"])
    applied_decisions = {
        "schema_version": review_payload["schema_version"],
        "plugin": review_payload["plugin"],
        "workflow": review_payload["workflow"],
        "run_id": review_payload["run_id"],
        "applied_at": applied_at,
        "decision_source": "local_review_server",
        "review_payload": {
            "path": ui_decisions["review_payload_path"],
            "item_count": review_payload["item_count"],
            "review_type": review_payload.get("review_type"),
        },
        "decisions": ui_decisions["decisions"],
        "effects": effects,
        "decision_count": ui_decisions["decision_count"],
        "item_count": review_payload["item_count"],
        "blocker_count": blocker_count,
        "target_update_count": len(target_outputs),
        "target_update_paths": [output["path"] for output in target_outputs],
        "structured_update_count": len(structured_update_paths),
        "structured_update_paths": structured_update_paths,
        "original_backup_paths": [output["path"] for output in backup_outputs],
        "application_status": application_status,
    }
    if "reviewer" in ui_decisions:
        applied_decisions["reviewer"] = ui_decisions["reviewer"]
    final_artifacts = _final_artifacts_with_application(
        directory,
        applied_decisions,
        target_outputs,
        backup_outputs,
    )
    ui_decisions_path = directory / "ui_decisions.json"
    applied_decisions_path = directory / "applied_decisions.json"
    final_artifacts_path = directory / "final_artifacts.json"
    _write_json(ui_decisions_path, ui_decisions)
    _write_json(applied_decisions_path, applied_decisions)
    _write_json(final_artifacts_path, final_artifacts)
    run_intake_path = _append_review_application_trace(
        directory,
        applied_decisions,
        final_artifacts,
    )
    return {
        "ok": True,
        "validation_type": "audit_reconciliation_application",
        "run_id": applied_decisions["run_id"],
        "decision_count": applied_decisions["decision_count"],
        "item_count": applied_decisions["item_count"],
        "blocker_count": blocker_count,
        "target_update_count": applied_decisions["target_update_count"],
        "structured_update_count": applied_decisions["structured_update_count"],
        "application_status": application_status,
        "persisted": True,
        "ui_decisions_path": ui_decisions_path.as_posix(),
        "applied_decisions_path": applied_decisions_path.as_posix(),
        "final_artifacts_path": final_artifacts_path.as_posix(),
        "run_intake_path": run_intake_path.as_posix() if run_intake_path else None,
        "message": (
            f"Applied {applied_decisions['decision_count']} "
            "Audit Reconciliation decisions."
        ),
        "applied_decisions": applied_decisions,
        "final_artifacts": final_artifacts,
    }


def _widget_html(output_dir: Path) -> str:
    widget_path = (
        Path(__file__).resolve().parents[1]
        / "assets"
        / "audit-reconciliation-review-widget.html"
    )
    html = widget_path.read_text(encoding="utf-8")
    payload_json = json.dumps(
        build_session_payload(output_dir),
        ensure_ascii=False,
        default=str,
    )
    bridge = f"""<script>
    (function () {{
      const serverPayload = {payload_json};
      const stateKey = `audit-reconciliation:${{serverPayload.review_payload?.run_id || "run"}}`;
      function readState() {{
        try {{ return JSON.parse(window.sessionStorage.getItem(stateKey) || "null"); }}
        catch {{ return null; }}
      }}
      window.openai = {{
        toolOutput: serverPayload,
        widgetState: readState(),
        setWidgetState(value) {{
          try {{ window.sessionStorage.setItem(stateKey, JSON.stringify(value || null)); }}
          catch {{ }}
        }},
        async callTool(name, args) {{
          const response = await fetch("/api/call-tool", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ name, args: args || {{}} }}),
          }});
          const result = await response.json();
          if (!response.ok || result.ok === false) {{
            throw new Error(result.error || `Local review server call failed: ${{name}}`);
          }}
          if (result.ui_decisions) serverPayload.ui_decisions = result.ui_decisions;
          if (result.final_artifacts) serverPayload.final_artifacts = result.final_artifacts;
          if (result.applied_decisions) serverPayload.applied_decisions = result.applied_decisions;
          return result;
        }},
      }};
    }}());
</script>
  """
    needle = "  <script>\n    const CONFIG = "
    if needle not in html:
        raise ValueError("audit reconciliation widget script insertion point not found")
    return html.replace(needle, bridge + needle, 1)


def render_review_html(output_dir: str | Path) -> str:
    """Render the browser review page HTML with the local persistence bridge."""

    return _widget_html(_output_dir(output_dir))


def _tool_result(output_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    name = _bounded_optional_string(payload.get("name"), "name")
    args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
    if name == TOOL_VALIDATE:
        session = build_session_payload(output_dir)
        return {
            "ok": True,
            "validation_type": "audit_reconciliation_review",
            "run_id": session["review_payload"]["run_id"],
            "item_count": session["review_payload"]["item_count"],
            "review_type": session["review_payload"].get("review_type"),
            "message": "Audit Reconciliation review payload is valid.",
            "review_payload": session["review_payload"],
        }
    if name == TOOL_RENDER:
        return build_session_payload(output_dir)
    if name == TOOL_SAVE:
        return save_decisions(output_dir, args)
    if name == TOOL_APPLY:
        return apply_decisions(output_dir, args)
    raise ValueError(f"unknown Audit Reconciliation widget tool: {name}")


def _handler(output_dir: Path) -> type[BaseHTTPRequestHandler]:
    class ReviewServerHandler(BaseHTTPRequestHandler):
        server_version = "AuditReconciliationReviewServer/1.0"

        def log_message(self, format_string: str, *args: object) -> None:
            LOGGER.info("%s - %s", self.client_address[0], format_string % args)

        def _json_response(
            self,
            payload: dict[str, Any],
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _html_response(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            route = urlparse(self.path).path
            try:
                if route in {"/", "/review", "/review_ui.html"}:
                    self._html_response(_widget_html(output_dir))
                    return
                if route == "/api/session":
                    self._json_response(build_session_payload(output_dir))
                    return
                if route == "/api/health":
                    session = build_session_payload(output_dir)
                    self._json_response(
                        {
                            "ok": True,
                            "plugin": PLUGIN_NAME,
                            "run_id": session["review_payload"]["run_id"],
                            "output_dir": output_dir.as_posix(),
                        }
                    )
                    return
                self.send_error(HTTPStatus.NOT_FOUND.value, "Not found")
            except (OSError, TypeError, ValueError) as exc:
                self._json_response(
                    {"ok": False, "error": str(exc)},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def do_POST(self) -> None:
            route = urlparse(self.path).path
            if route != "/api/call-tool":
                self.send_error(HTTPStatus.NOT_FOUND.value, "Not found")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                self._json_response(_tool_result(output_dir, payload))
            except json.JSONDecodeError as exc:
                self._json_response(
                    {"ok": False, "error": f"invalid JSON request: {exc}"},
                    status=HTTPStatus.BAD_REQUEST,
                )
            except (OSError, TypeError, ValueError) as exc:
                self._json_response(
                    {"ok": False, "error": str(exc)},
                    status=HTTPStatus.BAD_REQUEST,
                )

    return ReviewServerHandler


def serve_review(
    output_dir: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
) -> None:
    """Serve the review UI on localhost and optionally open the system browser."""

    directory = _output_dir(output_dir)
    build_session_payload(directory)
    safe_host = _validate_loopback_host(host)
    httpd = ThreadingHTTPServer((safe_host, port), _handler(directory))
    actual_port = httpd.server_address[1]
    url = f"http://{safe_host}:{actual_port}/review"
    LOGGER.info("Audit Reconciliation review server: %s", url)
    LOGGER.info("Output folder: %s", directory)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Stopping Audit Reconciliation review server")
    finally:
        httpd.server_close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Open the Audit Reconciliation review UI in a local browser and "
            "persist decisions into the run output folder."
        )
    )
    parser.add_argument("output_dir", help="Run output folder with review_payload.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Start the server without opening the browser automatically.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parser().parse_args(argv)
    try:
        serve_review(
            args.output_dir,
            host=args.host,
            port=args.port,
            open_browser=not args.no_open,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
