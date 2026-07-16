"""Analyze what is needed to apply a Clara deck-revision plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from advisor_case_core import CaseWorkspaceError, validate_case_workspace
from build_deck_revision_quote_candidate_matrix import (
    change_needs_quote_candidate_matrix,
)
from deck_revision_execution_contract import (
    PATCH_EXECUTION_STRATEGY,
    SUPPORTED_PATCH_OPERATIONS,
    execution_strategy_requirement,
)

__all__ = [
    "DeckRevisionMaterialNeedsResult",
    "analyze_deck_revision_materials",
    "main",
]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeckRevisionMaterialNeedsResult:
    """Material-needs artifacts for a deck-revision plan."""

    session_dir: Path
    needs_path: Path
    review_path: Path


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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _load_plan(
    session_dir: Path, plan_path: Path | None, case_dir: Path
) -> tuple[Path, dict[str, Any]]:
    candidate = plan_path or (session_dir / "deck_revision_changes.normalized.json")
    if not candidate.is_absolute():
        candidate = case_dir / candidate
    if not candidate.is_file():
        raise CaseWorkspaceError(
            f"normalized deck revision plan is missing: {candidate}; run finalize_deck_revision_plan.py first"
        )
    return candidate.resolve(), _read_json(candidate)


def _required_workbench(session_dir: Path) -> dict[str, Any]:
    workbench_path = session_dir / "deck_revision_workbench.json"
    if not workbench_path.is_file():
        raise CaseWorkspaceError(
            f"deck revision workbench is missing: {workbench_path}; run build_deck_revision_workbench.py first"
        )
    return _read_json(workbench_path)


def _approval_status(
    case_dir: Path, session_dir: Path, plan_path: Path
) -> dict[str, Any]:
    approval_path = session_dir / "deck_revision_approval.json"
    if not approval_path.is_file():
        return {
            "status": "missing",
            "path": None,
            "approved": False,
            "reason": "run approve_deck_revision_plan.py after consultant review",
        }
    approval = _read_json(approval_path)
    expected_hash = _sha256(plan_path)
    approved = bool(approval.get("approved"))
    hash_matches = approval.get("plan_sha256") == expected_hash
    understanding_reviewed = bool(approval.get("understanding_reviewed"))
    raw_understanding_path = approval.get("understanding_path")
    understanding_path: Path | None = None
    understanding_exists = False
    understanding_hash_matches = False
    if isinstance(raw_understanding_path, str) and raw_understanding_path.strip():
        understanding_path = Path(raw_understanding_path).expanduser()
        if not understanding_path.is_absolute():
            understanding_path = case_dir / understanding_path
        understanding_exists = understanding_path.is_file()
        if understanding_exists:
            understanding_hash_matches = approval.get(
                "understanding_sha256"
            ) == _sha256(understanding_path)
    approval_valid = (
        approved
        and hash_matches
        and understanding_reviewed
        and understanding_hash_matches
    )
    status = "approved" if approval_valid else "stale_or_invalid"
    reason = None
    if not approved:
        reason = "approval is not marked approved"
    elif not hash_matches:
        reason = "plan hash changed after approval"
    elif not understanding_reviewed:
        reason = "understanding checkpoint was not marked reviewed"
    elif not understanding_exists:
        reason = "understanding checkpoint is missing"
    elif not understanding_hash_matches:
        reason = "understanding checkpoint changed after approval"
    return {
        "status": status,
        "path": _relative_path(case_dir, approval_path),
        "approved": approval_valid,
        "approved_by": approval.get("approved_by"),
        "plan_sha256": approval.get("plan_sha256"),
        "current_plan_sha256": expected_hash,
        "hash_matches": hash_matches,
        "understanding_reviewed": understanding_reviewed,
        "understanding_path": (
            _relative_path(case_dir, understanding_path)
            if understanding_path is not None
            else None
        ),
        "understanding_exists": understanding_exists,
        "understanding_hash_matches": understanding_hash_matches,
        "reason": reason,
    }


def _patch_ready(patch: Mapping[str, Any]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    operation = str(patch.get("operation", "")).strip()
    if operation not in SUPPORTED_PATCH_OPERATIONS:
        missing.append(f"unsupported patch operation `{operation or 'missing'}`")
    target = patch.get("target") if isinstance(patch.get("target"), dict) else {}
    value = patch.get("value") if isinstance(patch.get("value"), dict) else {}
    if operation in {"set_shape_text", "delete_shape", "move_shape"} and not target.get(
        "shape_index"
    ):
        missing.append("target.shape_index")
    if (
        operation in {"set_title_text", "set_shape_text", "add_textbox"}
        and not str(value.get("text", "")).strip()
    ):
        missing.append("value.text")
    if operation == "replace_text":
        if not str(value.get("old_text", "")).strip():
            missing.append("value.old_text")
        if not str(value.get("new_text", "")).strip():
            missing.append("value.new_text")
    if operation == "move_shape" and "left" not in value and "top" not in value:
        missing.append("value.left or value.top")
    return not missing, missing


def _quote_matrix_status(
    case_dir: Path, session_dir: Path, changes: list[Mapping[str, Any]]
) -> dict[str, Any]:
    required_change_ids = [
        str(change.get("change_id") or "")
        for change in changes
        if change_needs_quote_candidate_matrix(change)
    ]
    required_change_ids = [change_id for change_id in required_change_ids if change_id]
    matrix_path = session_dir / "deck_revision_quote_candidate_matrix.json"
    review_path = session_dir / "deck_revision_quote_candidate_matrix.md"
    available = matrix_path.is_file() and review_path.is_file()
    status = (
        "not_required"
        if not required_change_ids
        else "available" if available else "required_missing"
    )
    return {
        "status": status,
        "required": bool(required_change_ids),
        "required_change_ids": required_change_ids,
        "matrix_path": _relative_path(case_dir, matrix_path) if available else None,
        "review_path": _relative_path(case_dir, review_path) if available else None,
        "reason": (
            None
            if status != "required_missing"
            else "run build_deck_revision_quote_candidate_matrix.py before selecting or applying transcript-backed quotes"
        ),
    }


def _analyze_change(
    change: Mapping[str, Any],
    *,
    quote_matrix_available: bool,
) -> dict[str, Any]:
    strategy = str(change.get("execution_strategy", "")).strip()
    patches = change.get("application_patches")
    if not isinstance(patches, list):
        patches = []
    patch_records: list[dict[str, Any]] = []
    missing: list[str] = []
    for patch in patches:
        if not isinstance(patch, dict):
            missing.append("patch object")
            continue
        ready, patch_missing = _patch_ready(patch)
        patch_records.append(
            {
                "patch_id": patch.get("patch_id"),
                "operation": patch.get("operation"),
                "ready": ready,
                "missing": patch_missing,
            }
        )
        missing.extend(f"{patch.get('patch_id')}: {item}" for item in patch_missing)
    material_requirements = change.get("material_requirements")
    if not isinstance(material_requirements, list):
        material_requirements = []
    quote_matrix_required = change_needs_quote_candidate_matrix(change)
    missing_material_requirements = [
        str(item)
        for item in material_requirements
        if str(item).strip()
        and not (
            quote_matrix_required
            and quote_matrix_available
            and "deck_revision_quote_candidate_matrix" in str(item)
        )
    ]
    if strategy == PATCH_EXECUTION_STRATEGY and not patches:
        missing.append(
            "application_patches: provide supported concrete PPTX patch operations"
        )
    if strategy != PATCH_EXECUTION_STRATEGY:
        missing.append(execution_strategy_requirement(strategy))
        missing.extend(missing_material_requirements)
    if quote_matrix_required and not quote_matrix_available:
        missing.append(
            "deck_revision_quote_candidate_matrix: run quote candidate mining before selecting transcript-backed evidence"
        )
    ready = strategy == PATCH_EXECUTION_STRATEGY and bool(patches) and not missing
    return {
        "change_id": change.get("change_id"),
        "slide_number": change.get("slide_number"),
        "change_scope": change.get("change_scope"),
        "requested_change": change.get("requested_change"),
        "interpretation": change.get("interpretation"),
        "execution_strategy": strategy,
        "execution_requirement": execution_strategy_requirement(strategy),
        "ready_for_auto_apply": ready,
        "patches": patch_records,
        "missing": missing,
        "material_requirements": material_requirements,
        "quote_candidate_matrix_required": quote_matrix_required,
        "quote_candidate_matrix_available": quote_matrix_available,
        "manual_or_codex_work_required": not ready,
    }


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Deck Revision Material Needs",
        "",
        f"Status: `{payload['summary']['status']}`",
        "",
        f"- Changes ready for auto-apply: {payload['summary']['ready_changes']}",
        f"- Changes needing manual/Codex detail: {payload['summary']['blocked_changes']}",
        f"- Approval status: `{payload['approval']['status']}`",
        f"- Quote candidate matrix: `{payload['quote_candidate_matrix']['status']}`",
        f"- Supported patch operations: {', '.join(payload['supported_patch_operations'])}",
        "",
    ]
    for change in payload["changes"]:
        status = "ready" if change["ready_for_auto_apply"] else "blocked"
        lines.extend(
            [
                f"## Slide {change['slide_number']} - {change['change_id']}",
                "",
                f"Status: `{status}`",
                "",
                f"Change: {change['requested_change']}",
                f"Strategy: `{change['execution_strategy']}`",
                f"Interpretation: {change.get('interpretation') or 'not recorded'}",
                "",
            ]
        )
        if change["patches"]:
            lines.append("Patches:")
            for patch in change["patches"]:
                patch_status = "ready" if patch["ready"] else "blocked"
                lines.append(
                    f"- `{patch['patch_id']}` `{patch['operation']}`: {patch_status}"
                )
        if change["missing"]:
            lines.append("Missing before automatic application:")
            lines.extend(f"- {item}" for item in change["missing"])
        if change["quote_candidate_matrix_required"]:
            matrix_status = (
                "available" if change["quote_candidate_matrix_available"] else "missing"
            )
            lines.append(f"Quote candidate matrix: `{matrix_status}`")
        lines.append("")
    return "\n".join(lines)


def analyze_deck_revision_materials(
    case_dir: Path,
    *,
    voice_session: Path | None = None,
    plan_path: Path | None = None,
    now: datetime | None = None,
) -> DeckRevisionMaterialNeedsResult:
    """Write material-needs artifacts for applying a deck-revision plan."""

    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    case_dir = case_dir.resolve()
    session_dir = _resolve_voice_session_dir(case_dir, voice_session)
    workbench = _required_workbench(session_dir)
    resolved_plan_path, plan = _load_plan(session_dir, plan_path, case_dir)
    approval = _approval_status(case_dir, session_dir, resolved_plan_path)
    changes = plan.get("changes")
    if not isinstance(changes, list):
        raise CaseWorkspaceError("normalized deck revision plan has no changes list")

    semantic_changes = [change for change in changes if isinstance(change, dict)]
    quote_matrix = _quote_matrix_status(case_dir, session_dir, semantic_changes)
    change_records = [
        _analyze_change(
            change,
            quote_matrix_available=quote_matrix["status"] == "available",
        )
        for change in semantic_changes
    ]
    ready_count = sum(1 for change in change_records if change["ready_for_auto_apply"])
    blocked_count = len(change_records) - ready_count
    if not change_records:
        status = "no_changes"
    elif blocked_count > 0:
        status = "partial_or_manual_work_required"
    elif approval["approved"]:
        status = "ready_for_auto_apply"
    else:
        status = "ready_for_approval"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "source": "clara_deck_revision_material_needs",
        "created_at": _now_iso(now),
        "voice_session": _relative_path(case_dir, session_dir),
        "plan_path": _relative_path(case_dir, resolved_plan_path),
        "workbench_path": _relative_path(
            case_dir, session_dir / "deck_revision_workbench.json"
        ),
        "deck_path": workbench.get("source_paths", {}).get("deck_path"),
        "approval": approval,
        "quote_candidate_matrix": quote_matrix,
        "supported_patch_operations": sorted(SUPPORTED_PATCH_OPERATIONS),
        "summary": {
            "status": status,
            "approved_for_pptx_revision": bool(approval["approved"]),
            "total_changes": len(change_records),
            "ready_changes": ready_count,
            "blocked_changes": blocked_count,
        },
        "changes": change_records,
    }

    needs_path = session_dir / "deck_revision_material_needs.json"
    review_path = session_dir / "deck_revision_material_needs.md"
    _write_json(needs_path, payload)
    review_path.write_text(_render_markdown(payload), encoding="utf-8")
    return DeckRevisionMaterialNeedsResult(
        session_dir=session_dir,
        needs_path=needs_path,
        review_path=review_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze what is needed to apply a Clara deck-revision plan.",
    )
    parser.add_argument("case_dir", type=Path)
    parser.add_argument(
        "--voice-session",
        type=Path,
        default=None,
        help="Voice session folder name/path. Defaults to latest voice session.",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="Normalized change plan. Defaults to deck_revision_changes.normalized.json.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = analyze_deck_revision_materials(
        args.case_dir,
        voice_session=args.voice_session,
        plan_path=args.plan,
    )
    LOGGER.info("wrote deck revision material needs to %s", result.needs_path)
    LOGGER.info("wrote deck revision material-needs review to %s", result.review_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
