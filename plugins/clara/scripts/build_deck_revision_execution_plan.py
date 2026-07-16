"""Build the execution plan for a finalized Clara deck-revision plan."""

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
    MODEL_OR_HUMAN_EXECUTION_STRATEGIES,
    PATCH_EXECUTION_STRATEGY,
    SUPPORTED_PATCH_OPERATIONS,
    execution_strategy_requirement,
)

__all__ = [
    "DeckRevisionExecutionPlanResult",
    "build_deck_revision_execution_plan",
    "main",
]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeckRevisionExecutionPlanResult:
    """Artifacts created for the deck-revision execution plan."""

    session_dir: Path
    execution_plan_path: Path
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


def _strategy_status(strategy: str, patch_ready: bool, patches: list[Any]) -> str:
    if strategy == PATCH_EXECUTION_STRATEGY:
        if not patches:
            return "blocked_missing_patch_details"
        return "ready_for_patcher" if patch_ready else "blocked_patch_details"
    if strategy == "needs_human_decision":
        return "needs_human_decision"
    if strategy in MODEL_OR_HUMAN_EXECUTION_STRATEGIES:
        return f"requires_{strategy}"
    return "unsupported_strategy"


def _next_action(strategy: str, status: str) -> str:
    if status == "ready_for_patcher":
        return "After approval, run apply_deck_revision_plan.py and verify output."
    if strategy == "model_assisted_edit":
        return (
            "Use Codex/presentation editing to modify the slide from the approved "
            "understanding, then run verification."
        )
    if strategy == "slide_rebuild":
        return (
            "Rebuild the affected slide from the style spec, deck context, and "
            "approved change before verification."
        )
    if strategy == "deck_restructure":
        return (
            "Apply the approved deck sequence or section-structure change before "
            "slide-level verification."
        )
    if strategy == "needs_human_decision":
        return "Resolve the listed human decision or missing material before editing."
    return "Provide a supported execution strategy and required execution details."


def _execution_record(change: Mapping[str, Any]) -> dict[str, Any]:
    strategy = str(change.get("execution_strategy", "")).strip()
    patches = change.get("application_patches")
    if not isinstance(patches, list):
        patches = []
    patch_records: list[dict[str, Any]] = []
    patch_missing: list[str] = []
    for patch in patches:
        if not isinstance(patch, dict):
            patch_missing.append("patch object")
            continue
        ready, missing = _patch_ready(patch)
        patch_records.append(
            {
                "patch_id": patch.get("patch_id"),
                "operation": patch.get("operation"),
                "ready": ready,
                "missing": missing,
            }
        )
        patch_missing.extend(f"{patch.get('patch_id')}: {item}" for item in missing)
    patch_ready = bool(patches) and not patch_missing
    status = _strategy_status(strategy, patch_ready, patches)
    material_requirements = change.get("material_requirements")
    if not isinstance(material_requirements, list):
        material_requirements = []
    return {
        "change_id": change.get("change_id"),
        "slide_number": change.get("slide_number"),
        "change_scope": change.get("change_scope"),
        "requested_change": change.get("requested_change"),
        "interpretation": change.get("interpretation"),
        "execution_strategy": strategy,
        "status": status,
        "requirement": execution_strategy_requirement(strategy),
        "next_action": _next_action(strategy, status),
        "ready_for_deterministic_apply": status == "ready_for_patcher",
        "requires_model_or_human_work": strategy in MODEL_OR_HUMAN_EXECUTION_STRATEGIES,
        "material_requirements": material_requirements,
        "patches": patch_records,
        "missing": patch_missing,
        "success_criteria": (
            change.get("success_criteria")
            if isinstance(change.get("success_criteria"), list)
            else []
        ),
    }


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Deck Revision Execution Plan",
        "",
        f"Status: `{payload['summary']['status']}`",
        "",
        f"- Total changes: {payload['summary']['total_changes']}",
        f"- Ready for deterministic patcher: {payload['summary']['ready_for_patcher']}",
        f"- Require model or human work: {payload['summary']['requires_model_or_human_work']}",
        "",
    ]
    for change in payload["changes"]:
        lines.extend(
            [
                f"## Slide {change['slide_number']} - {change['change_id']}",
                "",
                f"Status: `{change['status']}`",
                f"Strategy: `{change['execution_strategy']}`",
                f"Change: {change['requested_change']}",
                f"Interpretation: {change['interpretation']}",
                f"Next action: {change['next_action']}",
                "",
            ]
        )
        if change["material_requirements"]:
            lines.append("Material requirements:")
            lines.extend(f"- {item}" for item in change["material_requirements"])
            lines.append("")
        if change["patches"]:
            lines.append("Patches:")
            for patch in change["patches"]:
                patch_status = "ready" if patch["ready"] else "blocked"
                lines.append(
                    f"- `{patch['patch_id']}` `{patch['operation']}`: {patch_status}"
                )
                for item in patch["missing"]:
                    lines.append(f"  - Missing: {item}")
            lines.append("")
    return "\n".join(lines)


def build_deck_revision_execution_plan(
    case_dir: Path,
    *,
    voice_session: Path | None = None,
    plan_path: Path | None = None,
    now: datetime | None = None,
) -> DeckRevisionExecutionPlanResult:
    """Write the execution route for every interpreted deck-revision change."""

    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    case_dir = case_dir.resolve()
    session_dir = _resolve_voice_session_dir(case_dir, voice_session)
    resolved_plan_path, plan = _load_plan(session_dir, plan_path, case_dir)
    changes = plan.get("changes")
    if not isinstance(changes, list):
        raise CaseWorkspaceError("normalized deck revision plan has no changes list")

    change_records = [
        _execution_record(change) for change in changes if isinstance(change, dict)
    ]
    ready_count = sum(
        1 for change in change_records if change["ready_for_deterministic_apply"]
    )
    model_or_human_count = sum(
        1 for change in change_records if change["requires_model_or_human_work"]
    )
    if not change_records:
        status = "no_changes"
    elif ready_count == len(change_records):
        status = "ready_for_deterministic_apply"
    elif ready_count > 0:
        status = "mixed_execution_required"
    else:
        status = "model_or_human_execution_required"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "source": "clara_deck_revision_execution_plan",
        "created_at": _now_iso(now),
        "voice_session": _relative_path(case_dir, session_dir),
        "plan_path": _relative_path(case_dir, resolved_plan_path),
        "summary": {
            "status": status,
            "total_changes": len(change_records),
            "ready_for_patcher": ready_count,
            "requires_model_or_human_work": model_or_human_count,
        },
        "changes": change_records,
    }
    execution_plan_path = session_dir / "deck_revision_execution_plan.json"
    review_path = session_dir / "deck_revision_execution_plan.md"
    _write_json(execution_plan_path, payload)
    review_path.write_text(_render_markdown(payload), encoding="utf-8")
    return DeckRevisionExecutionPlanResult(
        session_dir=session_dir,
        execution_plan_path=execution_plan_path,
        review_path=review_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the execution plan for a Clara deck-revision plan.",
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
    result = build_deck_revision_execution_plan(
        args.case_dir,
        voice_session=args.voice_session,
        plan_path=args.plan,
    )
    LOGGER.info("wrote deck revision execution plan to %s", result.execution_plan_path)
    LOGGER.info("wrote deck revision execution review to %s", result.review_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
