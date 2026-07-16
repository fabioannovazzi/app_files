"""Validate and render a Clara deck-revision change plan."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from advisor_case_core import CaseWorkspaceError, validate_case_workspace
from deck_revision_execution_contract import (
    CHANGE_SCOPES,
    EXECUTION_STRATEGIES,
    SUCCESS_CRITERION_TYPES,
    SUPPORTED_PATCH_OPERATIONS,
    execution_strategy_requirement,
)

__all__ = [
    "DeckRevisionPlanResult",
    "finalize_deck_revision_plan",
    "main",
]

LOGGER = logging.getLogger(__name__)
CONFIDENCE_VALUES = {"high", "medium", "low"}
EXPLICITNESS_VALUES = {"explicit", "inferred", "uncertain"}
VISUAL_EVIDENCE_TYPES = {
    "deck_snapshot",
    "feedback_timeline",
    "video_frame",
    "screen_video",
    "manual_review",
}


@dataclass(frozen=True)
class DeckRevisionPlanResult:
    """Rendered and normalized deck-revision plan artifacts."""

    session_dir: Path
    normalized_plan_path: Path
    review_path: Path
    handoff_path: Path
    understanding_path: Path


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CaseWorkspaceError(f"expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _relative_path(case_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(case_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def _resolve_voice_session_dir(case_dir: Path, voice_session: Path | None) -> Path:
    sessions_root = case_dir / "voice_sessions"
    if voice_session is None:
        if not sessions_root.is_dir():
            raise CaseWorkspaceError("case has no voice_sessions folder")
        sessions = sorted(path for path in sessions_root.iterdir() if path.is_dir())
        if not sessions:
            raise CaseWorkspaceError("case has no imported voice sessions")
        return sessions[-1].resolve()

    candidate = voice_session.expanduser()
    candidates = (
        [candidate]
        if candidate.is_absolute()
        else [case_dir / candidate, sessions_root / candidate]
    )
    for path in candidates:
        if path.is_dir():
            resolved = path.resolve()
            try:
                resolved.relative_to(sessions_root.resolve())
            except ValueError as error:
                raise CaseWorkspaceError(
                    f"voice session must live under {sessions_root}: {resolved}"
                ) from error
            return resolved
    raise CaseWorkspaceError(f"voice session does not exist: {voice_session}")


def _non_empty_text(value: Any, *, field: str, change_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaseWorkspaceError(f"{change_id}: `{field}` must be a non-empty string")
    return value.strip()


def _optional_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _integer(value: Any, *, field: str, change_id: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CaseWorkspaceError(f"{change_id}: `{field}` must be an integer")
    return value


def _optional_timestamp_ms(value: Any, *, field: str, change_id: str) -> int | None:
    if value is None:
        return None
    timestamp_ms = _integer(value, field=field, change_id=change_id)
    if timestamp_ms < 0:
        raise CaseWorkspaceError(f"{change_id}: `{field}` must be non-negative")
    return timestamp_ms


def _list_of_texts(value: Any, *, field: str, change_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CaseWorkspaceError(f"{change_id}: `{field}` must be a list")
    result: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise CaseWorkspaceError(
                f"{change_id}: `{field}` item {index} must be a non-empty string"
            )
        result.append(item.strip())
    return result


def _optional_packet_scope(value: Any, *, change_id: str) -> str | None:
    if value is None:
        return None
    packet_scope = _non_empty_text(
        value,
        field="packet_scope",
        change_id=change_id,
    )
    if packet_scope not in {"slide", "slide_cluster", "deck"}:
        raise CaseWorkspaceError(
            f"{change_id}: unsupported packet_scope `{packet_scope}`; "
            "expected deck, slide, or slide_cluster"
        )
    return packet_scope


def _normalize_affected_slide_numbers(
    value: Any,
    *,
    slide_number: int,
    slide_lookup: Mapping[int, Mapping[str, Any]],
    change_id: str,
) -> list[int]:
    if value is None:
        return [slide_number]
    if not isinstance(value, list):
        raise CaseWorkspaceError(
            f"{change_id}: `affected_slide_numbers` must be a list"
        )
    numbers: list[int] = []
    seen: set[int] = set()
    for index, item in enumerate(value, start=1):
        if isinstance(item, bool) or not isinstance(item, int):
            raise CaseWorkspaceError(
                f"{change_id}: affected_slide_numbers item {index} must be an integer"
            )
        if item not in slide_lookup:
            valid = ", ".join(str(number) for number in sorted(slide_lookup))
            raise CaseWorkspaceError(
                f"{change_id}: affected slide {item} is not in deck snapshot; "
                f"valid slides: {valid}"
            )
        if item not in seen:
            numbers.append(item)
            seen.add(item)
    if not numbers:
        raise CaseWorkspaceError(
            f"{change_id}: `affected_slide_numbers` must not be empty"
        )
    if slide_number not in seen:
        numbers.insert(0, slide_number)
    return numbers


def _normalize_transcript_evidence(
    value: Any,
    *,
    change_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise CaseWorkspaceError(
            f"{change_id}: `transcript_evidence` must be a non-empty list"
        )
    records: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise CaseWorkspaceError(
                f"{change_id}: transcript evidence {index} must be an object"
            )
        timestamp_ms = _optional_timestamp_ms(
            item.get("timestamp_ms"),
            field="timestamp_ms",
            change_id=change_id,
        )
        records.append(
            {
                "speaker": _optional_text(item.get("speaker")) or None,
                "timestamp_ms": timestamp_ms,
                "quote": _non_empty_text(
                    item.get("quote"),
                    field="quote",
                    change_id=change_id,
                ),
                "note": _optional_text(item.get("note")) or None,
            }
        )
    return records


def _normalize_visual_evidence(
    value: Any,
    *,
    change_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise CaseWorkspaceError(
            f"{change_id}: `visual_evidence` must be a non-empty list"
        )
    records: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise CaseWorkspaceError(
                f"{change_id}: visual evidence {index} must be an object"
            )
        evidence_type = _non_empty_text(
            item.get("evidence_type"),
            field="evidence_type",
            change_id=change_id,
        )
        if evidence_type not in VISUAL_EVIDENCE_TYPES:
            allowed = ", ".join(sorted(VISUAL_EVIDENCE_TYPES))
            raise CaseWorkspaceError(
                f"{change_id}: unsupported visual evidence type `{evidence_type}`; "
                f"expected one of {allowed}"
            )
        timestamp_ms = _optional_timestamp_ms(
            item.get("timestamp_ms"),
            field="timestamp_ms",
            change_id=change_id,
        )
        records.append(
            {
                "evidence_type": evidence_type,
                "timestamp_ms": timestamp_ms,
                "path": _optional_text(item.get("path")) or None,
                "note": _non_empty_text(
                    item.get("note"),
                    field="note",
                    change_id=change_id,
                ),
            }
        )
    return records


def _optional_int_from_mapping(
    payload: Mapping[str, Any],
    key: str,
    *,
    change_id: str,
    patch_id: str,
) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CaseWorkspaceError(f"{change_id}/{patch_id}: `{key}` must be an integer")
    return value


def _required_int_from_mapping(
    payload: Mapping[str, Any],
    key: str,
    *,
    change_id: str,
    patch_id: str,
) -> int:
    value = _optional_int_from_mapping(
        payload,
        key,
        change_id=change_id,
        patch_id=patch_id,
    )
    if value is None:
        raise CaseWorkspaceError(f"{change_id}/{patch_id}: `{key}` is required")
    return value


def _optional_text_from_mapping(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _required_text_from_mapping(
    payload: Mapping[str, Any],
    key: str,
    *,
    change_id: str,
    patch_id: str,
) -> str:
    value = _optional_text_from_mapping(payload, key)
    if not value:
        raise CaseWorkspaceError(f"{change_id}/{patch_id}: `{key}` is required")
    return value


def _normalize_patch_target(
    target: Any,
    *,
    operation: str,
    change_id: str,
    patch_id: str,
) -> dict[str, Any]:
    if target is None:
        target = {}
    if not isinstance(target, dict):
        raise CaseWorkspaceError(f"{change_id}/{patch_id}: `target` must be an object")
    normalized: dict[str, Any] = {}
    shape_index = _optional_int_from_mapping(
        target,
        "shape_index",
        change_id=change_id,
        patch_id=patch_id,
    )
    if shape_index is not None:
        if shape_index < 1:
            raise CaseWorkspaceError(
                f"{change_id}/{patch_id}: `shape_index` must be >= 1"
            )
        normalized["shape_index"] = shape_index
    old_text = _optional_text_from_mapping(target, "old_text")
    if old_text:
        normalized["old_text"] = old_text
    expected_text = _optional_text_from_mapping(target, "expected_text") or old_text
    if expected_text:
        normalized["expected_text"] = expected_text
    if (
        operation in {"set_shape_text", "replace_text", "delete_shape", "move_shape"}
        and shape_index is None
    ):
        raise CaseWorkspaceError(
            f"{change_id}/{patch_id}: `{operation}` requires target.shape_index"
        )
    if (
        operation
        in {
            "set_title_text",
            "set_shape_text",
            "replace_text",
            "delete_shape",
            "move_shape",
        }
        and not expected_text
    ):
        raise CaseWorkspaceError(
            f"{change_id}/{patch_id}: `{operation}` requires target.expected_text"
        )
    return normalized


def _normalize_patch_value(
    value: Any,
    *,
    operation: str,
    change_id: str,
    patch_id: str,
) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise CaseWorkspaceError(f"{change_id}/{patch_id}: `value` must be an object")
    normalized: dict[str, Any] = {}
    if operation in {"set_title_text", "set_shape_text", "add_textbox"}:
        normalized["text"] = _required_text_from_mapping(
            value,
            "text",
            change_id=change_id,
            patch_id=patch_id,
        )
    if operation == "replace_text":
        normalized["old_text"] = _required_text_from_mapping(
            value,
            "old_text",
            change_id=change_id,
            patch_id=patch_id,
        )
        normalized["new_text"] = _required_text_from_mapping(
            value,
            "new_text",
            change_id=change_id,
            patch_id=patch_id,
        )
    if operation == "move_shape":
        left = _optional_int_from_mapping(
            value,
            "left",
            change_id=change_id,
            patch_id=patch_id,
        )
        top = _optional_int_from_mapping(
            value,
            "top",
            change_id=change_id,
            patch_id=patch_id,
        )
        if left is None and top is None:
            raise CaseWorkspaceError(
                f"{change_id}/{patch_id}: `move_shape` requires value.left or value.top"
            )
        if left is not None:
            normalized["left"] = left
        if top is not None:
            normalized["top"] = top
    if operation == "add_textbox":
        for key in ("left", "top", "width", "height"):
            int_value = _optional_int_from_mapping(
                value,
                key,
                change_id=change_id,
                patch_id=patch_id,
            )
            if int_value is not None:
                normalized[key] = int_value
    expected_absent = _optional_text_from_mapping(value, "expected_absent_text")
    if expected_absent:
        normalized["expected_absent_text"] = expected_absent
    return normalized


def _normalize_application_patches(
    value: Any,
    *,
    change_id: str,
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CaseWorkspaceError(f"{change_id}: `application_patches` must be a list")
    patches: list[dict[str, Any]] = []
    for index, raw_patch in enumerate(value, start=1):
        patch_id = f"{change_id}-p{index:03d}"
        if not isinstance(raw_patch, dict):
            raise CaseWorkspaceError(f"{change_id}/{patch_id}: patch must be an object")
        patch_id = _optional_text(raw_patch.get("patch_id")) or patch_id
        operation = _non_empty_text(
            raw_patch.get("operation"),
            field="operation",
            change_id=f"{change_id}/{patch_id}",
        )
        if operation not in SUPPORTED_PATCH_OPERATIONS:
            allowed = ", ".join(sorted(SUPPORTED_PATCH_OPERATIONS))
            raise CaseWorkspaceError(
                f"{change_id}/{patch_id}: unsupported operation `{operation}`; expected {allowed}"
            )
        target = _normalize_patch_target(
            raw_patch.get("target"),
            operation=operation,
            change_id=change_id,
            patch_id=patch_id,
        )
        patch_value = _normalize_patch_value(
            raw_patch.get("value"),
            operation=operation,
            change_id=change_id,
            patch_id=patch_id,
        )
        if (
            operation == "delete_shape"
            and "expected_absent_text" not in patch_value
            and target.get("expected_text")
        ):
            patch_value["expected_absent_text"] = target["expected_text"]
        patches.append(
            {
                "patch_id": patch_id,
                "operation": operation,
                "target": target,
                "value": patch_value,
            }
        )
    return patches


def _normalize_success_criteria(
    value: Any,
    *,
    change_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise CaseWorkspaceError(
            f"{change_id}: `success_criteria` must be a non-empty list"
        )
    criteria: list[dict[str, Any]] = []
    for index, raw_criterion in enumerate(value, start=1):
        criterion_id = f"{change_id}-c{index:03d}"
        if not isinstance(raw_criterion, dict):
            raise CaseWorkspaceError(
                f"{change_id}/{criterion_id}: success criterion must be an object"
            )
        criterion_id = _optional_text(raw_criterion.get("criterion_id")) or criterion_id
        check_type = _non_empty_text(
            raw_criterion.get("check_type"),
            field="check_type",
            change_id=f"{change_id}/{criterion_id}",
        )
        if check_type not in SUCCESS_CRITERION_TYPES:
            allowed = ", ".join(sorted(SUCCESS_CRITERION_TYPES))
            raise CaseWorkspaceError(
                f"{change_id}/{criterion_id}: unsupported success criterion "
                f"`{check_type}`; expected {allowed}"
            )
        criterion: dict[str, Any] = {
            "criterion_id": criterion_id,
            "check_type": check_type,
            "description": _non_empty_text(
                raw_criterion.get("description"),
                field="description",
                change_id=f"{change_id}/{criterion_id}",
            ),
        }
        for key in ("expected_text", "absent_text", "note"):
            text = _optional_text(raw_criterion.get(key))
            if text:
                criterion[key] = text
        for key in ("shape_index", "expected_left", "expected_top", "expected_count"):
            int_value = _optional_int_from_mapping(
                raw_criterion,
                key,
                change_id=change_id,
                patch_id=criterion_id,
            )
            if int_value is not None:
                if key in {"shape_index", "expected_count"} and int_value < 0:
                    raise CaseWorkspaceError(
                        f"{change_id}/{criterion_id}: `{key}` must be non-negative"
                    )
                if key == "shape_index" and int_value < 1:
                    raise CaseWorkspaceError(
                        f"{change_id}/{criterion_id}: `shape_index` must be >= 1"
                    )
                criterion[key] = int_value
        if check_type in {"title_equals", "text_present"} and not criterion.get(
            "expected_text"
        ):
            raise CaseWorkspaceError(
                f"{change_id}/{criterion_id}: `{check_type}` requires expected_text"
            )
        if check_type == "text_absent" and not (
            criterion.get("absent_text") or criterion.get("expected_text")
        ):
            raise CaseWorkspaceError(
                f"{change_id}/{criterion_id}: `text_absent` requires absent_text"
            )
        if check_type == "slide_count_equals" and "expected_count" not in criterion:
            raise CaseWorkspaceError(
                f"{change_id}/{criterion_id}: `slide_count_equals` requires expected_count"
            )
        if check_type == "shape_position":
            if "shape_index" not in criterion:
                raise CaseWorkspaceError(
                    f"{change_id}/{criterion_id}: `shape_position` requires shape_index"
                )
            if "expected_left" not in criterion and "expected_top" not in criterion:
                raise CaseWorkspaceError(
                    f"{change_id}/{criterion_id}: `shape_position` requires expected_left or expected_top"
                )
        criteria.append(criterion)
    return criteria


def _slide_lookup(workbench: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    deck = workbench.get("deck")
    if not isinstance(deck, dict):
        raise CaseWorkspaceError("deck revision workbench is missing deck metadata")
    lookup: dict[int, dict[str, Any]] = {}
    for raw_slide in deck.get("slides", []):
        if not isinstance(raw_slide, dict):
            continue
        slide_number = raw_slide.get("slide_number")
        if isinstance(slide_number, int) and not isinstance(slide_number, bool):
            lookup[slide_number] = raw_slide
    if not lookup:
        raise CaseWorkspaceError("deck revision workbench has no slide records")
    return lookup


def _normalize_change(
    raw_change: Any,
    *,
    index: int,
    slide_lookup: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw_change, dict):
        raise CaseWorkspaceError(f"change {index}: must be an object")
    change_id = _optional_text(raw_change.get("change_id")) or f"chg-{index:03d}"
    slide_number = _integer(
        raw_change.get("slide_number"),
        field="slide_number",
        change_id=change_id,
    )
    if slide_number not in slide_lookup:
        valid = ", ".join(str(number) for number in sorted(slide_lookup))
        raise CaseWorkspaceError(
            f"{change_id}: slide_number {slide_number} is not in deck snapshot; "
            f"valid slides: {valid}"
        )
    confidence = _non_empty_text(
        raw_change.get("confidence"),
        field="confidence",
        change_id=change_id,
    )
    if confidence not in CONFIDENCE_VALUES:
        allowed = ", ".join(sorted(CONFIDENCE_VALUES))
        raise CaseWorkspaceError(
            f"{change_id}: unsupported confidence `{confidence}`; expected {allowed}"
        )
    explicitness = _non_empty_text(
        raw_change.get("explicitness"),
        field="explicitness",
        change_id=change_id,
    )
    if explicitness not in EXPLICITNESS_VALUES:
        allowed = ", ".join(sorted(EXPLICITNESS_VALUES))
        raise CaseWorkspaceError(
            f"{change_id}: unsupported explicitness `{explicitness}`; expected {allowed}"
        )
    change_scope = _non_empty_text(
        raw_change.get("change_scope"),
        field="change_scope",
        change_id=change_id,
    )
    if change_scope not in CHANGE_SCOPES:
        allowed = ", ".join(sorted(CHANGE_SCOPES))
        raise CaseWorkspaceError(
            f"{change_id}: unsupported change_scope `{change_scope}`; expected {allowed}"
        )
    execution_strategy = _non_empty_text(
        raw_change.get("execution_strategy"),
        field="execution_strategy",
        change_id=change_id,
    )
    if execution_strategy not in EXECUTION_STRATEGIES:
        allowed = ", ".join(sorted(EXECUTION_STRATEGIES))
        raise CaseWorkspaceError(
            f"{change_id}: unsupported execution_strategy `{execution_strategy}`; expected {allowed}"
        )
    slide = slide_lookup[slide_number]
    application_patches = _normalize_application_patches(
        raw_change.get("application_patches"),
        change_id=change_id,
    )
    if execution_strategy == "deterministic_patch" and not application_patches:
        raise CaseWorkspaceError(
            f"{change_id}: deterministic_patch requires application_patches"
        )
    return {
        "change_id": change_id,
        "slide_number": slide_number,
        "affected_slide_numbers": _normalize_affected_slide_numbers(
            raw_change.get("affected_slide_numbers"),
            slide_number=slide_number,
            slide_lookup=slide_lookup,
            change_id=change_id,
        ),
        "slide_title": _optional_text(raw_change.get("slide_title"))
        or _optional_text(slide.get("title")),
        "packet_scope": _optional_packet_scope(
            raw_change.get("packet_scope"),
            change_id=change_id,
        ),
        "execution_group_id": _optional_text(raw_change.get("execution_group_id")),
        "dependency_change_ids": _list_of_texts(
            raw_change.get("dependency_change_ids"),
            field="dependency_change_ids",
            change_id=change_id,
        ),
        "change_scope": change_scope,
        "change_type": _non_empty_text(
            raw_change.get("change_type"),
            field="change_type",
            change_id=change_id,
        ),
        "requested_change": _non_empty_text(
            raw_change.get("requested_change"),
            field="requested_change",
            change_id=change_id,
        ),
        "interpretation": _non_empty_text(
            raw_change.get("interpretation"),
            field="interpretation",
            change_id=change_id,
        ),
        "rationale": _non_empty_text(
            raw_change.get("rationale"),
            field="rationale",
            change_id=change_id,
        ),
        "explicitness": explicitness,
        "confidence": confidence,
        "execution_strategy": execution_strategy,
        "execution_requirement": execution_strategy_requirement(execution_strategy),
        "transcript_evidence": _normalize_transcript_evidence(
            raw_change.get("transcript_evidence"),
            change_id=change_id,
        ),
        "visual_evidence": _normalize_visual_evidence(
            raw_change.get("visual_evidence"),
            change_id=change_id,
        ),
        "style_notes": _list_of_texts(
            raw_change.get("style_notes"),
            field="style_notes",
            change_id=change_id,
        ),
        "consultant_review_note": _optional_text(
            raw_change.get("consultant_review_note")
        ),
        "material_requirements": _list_of_texts(
            raw_change.get("material_requirements"),
            field="material_requirements",
            change_id=change_id,
        ),
        "success_criteria": _normalize_success_criteria(
            raw_change.get("success_criteria"),
            change_id=change_id,
        ),
        "application_patches": application_patches,
    }


def _format_timestamp(timestamp_ms: Any) -> str:
    if not isinstance(timestamp_ms, int):
        return ""
    total_seconds = timestamp_ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def _render_transcript_evidence(records: list[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for record in records:
        speaker = record.get("speaker") or "Speaker"
        timestamp = _format_timestamp(record.get("timestamp_ms"))
        prefix = f"{speaker}"
        if timestamp:
            prefix += f" at {timestamp}"
        lines.append(f"  - {prefix}: \"{record['quote']}\"")
        if record.get("note"):
            lines.append(f"    Note: {record['note']}")
    return lines


def _render_visual_evidence(records: list[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for record in records:
        timestamp = _format_timestamp(record.get("timestamp_ms"))
        evidence_type = str(record["evidence_type"]).replace("_", " ")
        prefix = evidence_type
        if timestamp:
            prefix += f" at {timestamp}"
        path = f" (`{record['path']}`)" if record.get("path") else ""
        lines.append(f"  - {prefix}{path}: {record['note']}")
    return lines


def _render_success_criteria(records: list[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for record in records:
        lines.append(
            f"  - `{record['criterion_id']}` `{record['check_type']}`: {record['description']}"
        )
    return lines


def _render_changes_markdown(
    *,
    normalized: Mapping[str, Any],
    workbench: Mapping[str, Any],
) -> str:
    deck = workbench["deck"]
    style = workbench["deck_style"]
    approved = bool(normalized.get("approved_for_pptx_revision"))
    lines = [
        "# Deck Revision Changes",
        "",
        (
            "Status: approved for controlled PPTX revision."
            if approved
            else "Status: consultant review required before PPTX revision."
        ),
        "",
        f"- Deck: `{deck['path']}`",
        f"- Deck style: `{style.get('style_name') or style.get('style_key')}`",
        f"- Voice session: `{workbench['voice_session']}`",
        "",
    ]
    changes = normalized["changes"]
    if not changes:
        lines.extend(
            [
                "## No Actionable Slide Changes",
                "",
                "No slide-level changes were interpreted from the provided transcript and visual context.",
                "",
            ]
        )
    for change in changes:
        title = f" - {change['slide_title']}" if change.get("slide_title") else ""
        lines.extend(
            [
                f"## Slide {change['slide_number']}{title}",
                "",
                f"Change: {change['requested_change']}",
                "",
                f"Clara interpretation: {change['interpretation']}",
                "",
                f"- Scope: `{change['change_scope']}`",
                f"- Type: `{change['change_type']}`",
                f"- Packet scope: `{change.get('packet_scope') or 'auto'}`",
                f"- Affected slides: `{change['affected_slide_numbers']}`",
                f"- Execution strategy: `{change['execution_strategy']}`",
                f"- Execution requirement: {change['execution_requirement']}",
                f"- Confidence: `{change['confidence']}`",
                f"- Explicitness: `{change['explicitness']}`",
                f"- Rationale: {change['rationale']}",
            ]
        )
        if change.get("material_requirements"):
            lines.append("- Material requirements:")
            lines.extend(f"  - {item}" for item in change["material_requirements"])
        if change.get("style_notes"):
            lines.append("- Style notes:")
            lines.extend(f"  - {note}" for note in change["style_notes"])
        if change.get("consultant_review_note"):
            lines.append(f"- Consultant note: {change['consultant_review_note']}")
        lines.extend(["", "Success criteria:"])
        lines.extend(_render_success_criteria(change["success_criteria"]))
        if change.get("application_patches"):
            lines.append("- Automatic PPTX patches:")
            for patch in change["application_patches"]:
                lines.append(f"  - `{patch['patch_id']}`: `{patch['operation']}`")
        else:
            lines.append(
                "- Automatic PPTX patches: none; this change requires manual/Codex execution detail before auto-apply."
            )
        lines.extend(["", "Transcript evidence:"])
        lines.extend(_render_transcript_evidence(change["transcript_evidence"]))
        lines.extend(["", "Visual/deck evidence:"])
        lines.extend(_render_visual_evidence(change["visual_evidence"]))
        lines.append("")
    open_questions = normalized.get("open_questions") or []
    if open_questions:
        lines.extend(["## Open Questions", ""])
        lines.extend(f"- {question}" for question in open_questions)
        lines.append("")
    return "\n".join(lines)


def _render_understanding_markdown(
    *,
    normalized: Mapping[str, Any],
    workbench: Mapping[str, Any],
) -> str:
    deck = workbench["deck"]
    lines = [
        "# Deck Revision Understanding",
        "",
        "Status: consultant review checkpoint. This file states what Clara understood should change; it does not prove the PPTX was edited.",
        "",
        f"- Deck: `{deck['path']}`",
        f"- Voice session: `{workbench['voice_session']}`",
        "",
    ]
    changes = normalized["changes"]
    if not changes:
        lines.extend(
            [
                "## No Interpreted Changes",
                "",
                "Clara did not identify actionable slide changes from the current evidence.",
                "",
            ]
        )
        return "\n".join(lines)
    for change in changes:
        title = f" - {change['slide_title']}" if change.get("slide_title") else ""
        lines.extend(
            [
                f"## Slide {change['slide_number']}{title}",
                "",
                f"Should change: {change['requested_change']}",
                "",
                f"Clara understood this as: {change['interpretation']}",
                "",
                f"Execution: `{change['execution_strategy']}`",
                f"Execution packet: `{change.get('packet_scope') or 'auto'}` / slides `{change['affected_slide_numbers']}`",
                f"Confidence: `{change['confidence']}` / `{change['explicitness']}`",
                "",
                "Success criteria:",
            ]
        )
        lines.extend(_render_success_criteria(change["success_criteria"]))
        if change.get("material_requirements"):
            lines.append("")
            lines.append("Needs before execution:")
            lines.extend(f"- {item}" for item in change["material_requirements"])
        if change.get("consultant_review_note"):
            lines.append("")
            lines.append(f"Review note: {change['consultant_review_note']}")
        lines.append("")
    return "\n".join(lines)


def _render_handoff(
    *,
    normalized: Mapping[str, Any],
    workbench: Mapping[str, Any],
) -> str:
    source_paths = workbench["source_paths"]
    lines = [
        "# Controlled PPTX Revision Handoff",
        "",
        "Status: waiting for separate plan approval.",
        "",
        "This file is the boundary between interpretation and deck editing. Clara/Codex should not modify the PPTX merely because a transcript was imported.",
        "",
        "## Inputs for the Editing Step",
        "",
        f"- Approved change plan: `{source_paths['changes_output_path']}`",
        f"- Consultant-readable changes: `{source_paths['changes_review_path']}`",
        "- Consultant-readable understanding: `deck_revision_understanding.md`",
        "- Interpretation packets: `deck_revision_interpretation_packets.json` / `deck_revision_interpretation_packets.md`",
        "- Execution plan: `deck_revision_execution_plan.json` / `deck_revision_execution_plan.md`",
        "- Execution packets: `deck_revision_execution_packets.json` / `deck_revision_execution_packets.md`",
        "- Required approval artifact: `deck_revision_approval.json`",
        f"- PPTX deck: `{source_paths['deck_path']}`",
        f"- Deck snapshot: `{source_paths['deck_snapshot_path']}`",
        f"- Deck style spec: `{source_paths['deck_style_spec_path']}`",
        f"- Attributed transcript: `{source_paths['attributed_transcript_path']}`",
        "",
        "## Rules for Editing",
        "",
        "- Apply only the changes listed in the reviewed change plan.",
        "- Execute through focused packets; do not feed the full change list into one deck-editing prompt.",
        "- Follow each change's execution strategy: deterministic patch, model-assisted edit, slide rebuild, deck restructure, or human decision.",
        "- Treat success criteria as the verification contract for the corrected deck.",
        "- Keep explicit partner instructions separate from inferred improvements.",
        "- Use the resolved deck style spec for any added, rebuilt, or materially reformatted slide.",
        "- Create a corrected PPTX as a new output; keep the original deck untouched.",
        "- Preserve a short change log linking edited slides back to the reviewed plan.",
        "",
        "## Approval Step",
        "",
        "After consultant/user review, run `approve_deck_revision_plan.py` to create an approval artifact tied to the exact normalized plan hash. Applying the PPTX must check that approval hash before editing.",
        "",
    ]
    return "\n".join(lines)


def finalize_deck_revision_plan(
    case_dir: Path,
    changes_path: Path,
    *,
    voice_session: Path | None = None,
    now: datetime | None = None,
) -> DeckRevisionPlanResult:
    """Validate a Codex-authored plan and render consultant-facing artifacts."""

    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    case_dir = case_dir.resolve()
    session_dir = _resolve_voice_session_dir(case_dir, voice_session)
    workbench_path = session_dir / "deck_revision_workbench.json"
    if not workbench_path.is_file():
        raise CaseWorkspaceError(
            f"deck revision workbench is missing: {workbench_path}; run build_deck_revision_workbench.py first"
        )

    candidate_changes_path = changes_path.expanduser()
    if not candidate_changes_path.is_absolute():
        candidate_changes_path = case_dir / candidate_changes_path
    if not candidate_changes_path.is_file():
        raise CaseWorkspaceError(
            f"deck revision changes file is missing: {changes_path}"
        )

    workbench = _read_json(workbench_path)
    raw_plan = _read_json(candidate_changes_path.resolve())
    if raw_plan.get("schema_version") != 1:
        raise CaseWorkspaceError("deck revision changes must use schema_version 1")
    if not isinstance(raw_plan.get("changes"), list):
        raise CaseWorkspaceError("deck revision changes must include a `changes` list")

    slides = _slide_lookup(workbench)
    normalized_changes = [
        _normalize_change(raw_change, index=index, slide_lookup=slides)
        for index, raw_change in enumerate(raw_plan["changes"], start=1)
    ]
    open_questions = _list_of_texts(
        raw_plan.get("open_questions"),
        field="open_questions",
        change_id="plan",
    )
    normalized: dict[str, Any] = {
        "schema_version": 1,
        "source": "clara_deck_revision_changes",
        "created_at": _now_iso(now),
        "input_plan_path": _relative_path(case_dir, candidate_changes_path.resolve()),
        "workbench_path": _relative_path(case_dir, workbench_path),
        "approved_for_pptx_revision": False,
        "model_requested_pptx_revision_approval": bool(
            raw_plan.get("approved_for_pptx_revision", False)
        ),
        "changes": normalized_changes,
        "open_questions": open_questions,
    }

    normalized_plan_path = session_dir / "deck_revision_changes.normalized.json"
    review_path = session_dir / "deck_revision_changes.md"
    handoff_path = session_dir / "deck_revision_handoff.md"
    understanding_path = session_dir / "deck_revision_understanding.md"
    _write_json(normalized_plan_path, normalized)
    review_path.write_text(
        _render_changes_markdown(normalized=normalized, workbench=workbench),
        encoding="utf-8",
    )
    understanding_path.write_text(
        _render_understanding_markdown(normalized=normalized, workbench=workbench),
        encoding="utf-8",
    )
    handoff_path.write_text(
        _render_handoff(normalized=normalized, workbench=workbench),
        encoding="utf-8",
    )
    return DeckRevisionPlanResult(
        session_dir=session_dir,
        normalized_plan_path=normalized_plan_path,
        review_path=review_path,
        handoff_path=handoff_path,
        understanding_path=understanding_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and render a Clara deck-revision change plan.",
    )
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("changes_json", type=Path)
    parser.add_argument(
        "--voice-session",
        type=Path,
        default=None,
        help="Voice session folder name/path. Defaults to latest voice session.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = finalize_deck_revision_plan(
        args.case_dir,
        args.changes_json,
        voice_session=args.voice_session,
    )
    LOGGER.info(
        "wrote normalized deck revision plan to %s", result.normalized_plan_path
    )
    LOGGER.info("wrote consultant-readable changes to %s", result.review_path)
    LOGGER.info(
        "wrote consultant-readable understanding to %s", result.understanding_path
    )
    LOGGER.info("wrote controlled PPTX handoff to %s", result.handoff_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
