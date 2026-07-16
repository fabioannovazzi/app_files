"""Approve a reviewed Clara deck-revision plan for PPTX application."""

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

__all__ = [
    "DeckRevisionApprovalResult",
    "approve_deck_revision_plan",
    "main",
]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeckRevisionApprovalResult:
    """Approval artifact for a reviewed deck-revision plan."""

    session_dir: Path
    approval_path: Path
    review_path: Path
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _resolve_plan_path(
    case_dir: Path,
    session_dir: Path,
    plan_path: Path | None,
) -> Path:
    candidate = plan_path or (session_dir / "deck_revision_changes.normalized.json")
    if not candidate.is_absolute():
        candidate = case_dir / candidate
    if not candidate.is_file():
        raise CaseWorkspaceError(
            f"normalized deck revision plan is missing: {candidate}; run finalize_deck_revision_plan.py first"
        )
    return candidate.resolve()


def _resolve_understanding_path(
    case_dir: Path,
    session_dir: Path,
    understanding_path: Path | None,
) -> Path:
    candidate = understanding_path or (session_dir / "deck_revision_understanding.md")
    if not candidate.is_absolute():
        candidate = case_dir / candidate
    if not candidate.is_file():
        raise CaseWorkspaceError(
            "deck revision understanding checkpoint is missing: "
            f"{candidate}; run finalize_deck_revision_plan.py and show "
            "deck_revision_understanding.md before approval"
        )
    if not candidate.read_text(encoding="utf-8").strip():
        raise CaseWorkspaceError(
            f"deck revision understanding checkpoint is empty: {candidate}"
        )
    return candidate.resolve()


def _render_markdown(payload: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Deck Revision Approval",
            "",
            f"Status: `{'approved' if payload['approved'] else 'not approved'}`",
            "",
            f"- Approved by: {payload['approved_by']}",
            f"- Plan: `{payload['plan_path']}`",
            f"- Plan SHA-256: `{payload['plan_sha256']}`",
            f"- Understanding reviewed: `{payload['understanding_reviewed']}`",
            f"- Understanding: `{payload['understanding_path']}`",
            f"- Understanding SHA-256: `{payload['understanding_sha256']}`",
            f"- Note: {payload.get('approval_note') or 'none'}",
            "",
        ]
    )


def approve_deck_revision_plan(
    case_dir: Path,
    *,
    voice_session: Path | None = None,
    plan_path: Path | None = None,
    understanding_path: Path | None = None,
    reviewer: str,
    note: str = "",
    understanding_reviewed: bool = False,
    allow_open_questions: bool = False,
    now: datetime | None = None,
) -> DeckRevisionApprovalResult:
    """Write an approval artifact tied to the exact normalized plan hash."""

    reviewer_clean = reviewer.strip()
    if not reviewer_clean:
        raise CaseWorkspaceError("reviewer is required")
    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    case_dir = case_dir.resolve()
    session_dir = _resolve_voice_session_dir(case_dir, voice_session)
    resolved_plan_path = _resolve_plan_path(case_dir, session_dir, plan_path)
    plan = _read_json(resolved_plan_path)
    open_questions = plan.get("open_questions")
    if isinstance(open_questions, list) and open_questions and not allow_open_questions:
        raise CaseWorkspaceError(
            "deck revision plan has open questions; resolve them or pass --allow-open-questions"
        )
    changes = plan.get("changes")
    if not isinstance(changes, list) or not changes:
        raise CaseWorkspaceError("deck revision plan has no changes to approve")
    if not understanding_reviewed:
        raise CaseWorkspaceError(
            "deck revision understanding checkpoint has not been marked reviewed; "
            "show deck_revision_understanding.md to the user, then rerun approval "
            "with --understanding-reviewed"
        )
    resolved_understanding_path = _resolve_understanding_path(
        case_dir,
        session_dir,
        understanding_path,
    )

    payload: dict[str, Any] = {
        "schema_version": 1,
        "source": "clara_deck_revision_approval",
        "created_at": _now_iso(now),
        "approved": True,
        "approved_by": reviewer_clean,
        "approval_note": note.strip() or None,
        "voice_session": _relative_path(case_dir, session_dir),
        "plan_path": _relative_path(case_dir, resolved_plan_path),
        "plan_sha256": _sha256(resolved_plan_path),
        "understanding_reviewed": True,
        "understanding_path": _relative_path(case_dir, resolved_understanding_path),
        "understanding_sha256": _sha256(resolved_understanding_path),
    }
    approval_path = session_dir / "deck_revision_approval.json"
    review_path = session_dir / "deck_revision_approval.md"
    _write_json(approval_path, payload)
    review_path.write_text(_render_markdown(payload), encoding="utf-8")
    return DeckRevisionApprovalResult(
        session_dir=session_dir,
        approval_path=approval_path,
        review_path=review_path,
        understanding_path=resolved_understanding_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Approve a reviewed Clara deck-revision plan for PPTX application.",
    )
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--note", default="")
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
    parser.add_argument(
        "--understanding",
        type=Path,
        default=None,
        help="Consultant-readable understanding checkpoint. Defaults to deck_revision_understanding.md.",
    )
    parser.add_argument(
        "--understanding-reviewed",
        action="store_true",
        help=(
            "Confirm deck_revision_understanding.md was shown to and reviewed with "
            "the user before approving PPTX edits."
        ),
    )
    parser.add_argument(
        "--allow-open-questions",
        action="store_true",
        help="Allow approval even when the normalized plan still has open questions.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = approve_deck_revision_plan(
        args.case_dir,
        voice_session=args.voice_session,
        plan_path=args.plan,
        understanding_path=args.understanding,
        reviewer=args.reviewer,
        note=args.note,
        understanding_reviewed=args.understanding_reviewed,
        allow_open_questions=args.allow_open_questions,
    )
    LOGGER.info("wrote deck revision approval to %s", result.approval_path)
    LOGGER.info("wrote deck revision approval review to %s", result.review_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
