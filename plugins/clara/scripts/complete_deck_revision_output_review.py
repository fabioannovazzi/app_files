"""Complete Clara's final semantic review loop for a corrected deck."""

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
    "DeckRevisionOutputReviewCompletion",
    "complete_deck_revision_output_review",
    "main",
]

LOGGER = logging.getLogger(__name__)


REQUIRED_CONFIRMATIONS = {
    "audience_copy_reviewed": "audience-facing titles and copy reviewed",
    "process_language_reviewed": "process/internal language absence reviewed",
    "requested_structure_reviewed": "requested deck structure reviewed",
    "semantic_evidence_fit_reviewed": "semantic evidence fit reviewed",
    "visual_render_reviewed": "rendered visual output reviewed",
}


@dataclass(frozen=True)
class DeckRevisionOutputReviewCompletion:
    """Final output review completion artifacts."""

    session_dir: Path
    completion_path: Path
    completion_markdown_path: Path


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


def _resolve_case_file(case_dir: Path, raw_path: str | Path, *, label: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = case_dir / candidate
    if not candidate.is_file():
        raise CaseWorkspaceError(f"{label} does not exist: {candidate}")
    return candidate.resolve()


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Deck Revision Final Output Review Completion",
        "",
        f"Status: `{payload['summary']['status']}`",
        "",
        f"- Completed by: {payload['completed_by']}",
        f"- Corrected deck: `{payload['corrected_deck_path']}`",
        f"- Review artifact: `{payload['output_review_path']}`",
        f"- Note: {payload.get('review_note') or 'none'}",
        "",
        "## Confirmations",
        "",
    ]
    for key, label in REQUIRED_CONFIRMATIONS.items():
        lines.append(f"- `{key}`: `{payload['confirmations'][key]}` - {label}")
    lines.append("")
    return "\n".join(lines)


def complete_deck_revision_output_review(
    case_dir: Path,
    *,
    voice_session: Path | None = None,
    output_review_path: Path | None = None,
    reviewer: str,
    note: str = "",
    audience_copy_reviewed: bool = False,
    process_language_reviewed: bool = False,
    requested_structure_reviewed: bool = False,
    semantic_evidence_fit_reviewed: bool = False,
    visual_render_reviewed: bool = False,
    now: datetime | None = None,
) -> DeckRevisionOutputReviewCompletion:
    """Mark the final corrected deck review loop complete after Codex review."""

    reviewer_clean = reviewer.strip()
    if not reviewer_clean:
        raise CaseWorkspaceError("reviewer is required")
    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    confirmations = {
        "audience_copy_reviewed": audience_copy_reviewed,
        "process_language_reviewed": process_language_reviewed,
        "requested_structure_reviewed": requested_structure_reviewed,
        "semantic_evidence_fit_reviewed": semantic_evidence_fit_reviewed,
        "visual_render_reviewed": visual_render_reviewed,
    }
    missing = [
        REQUIRED_CONFIRMATIONS[key]
        for key, value in confirmations.items()
        if not bool(value)
    ]
    if missing:
        raise CaseWorkspaceError(
            "final output review is incomplete; missing: " + ", ".join(missing)
        )

    case_dir = case_dir.resolve()
    session_dir = _resolve_voice_session_dir(case_dir, voice_session)
    review_path = output_review_path or (
        session_dir / "deck_revision_output_review.json"
    )
    if not review_path.is_absolute():
        review_path = case_dir / review_path
    if not review_path.is_file():
        raise CaseWorkspaceError(
            f"deck revision output review is missing: {review_path}; run apply_deck_revision_plan.py first"
        )
    output_review = _read_json(review_path)
    corrected_deck_path = _resolve_case_file(
        case_dir,
        str(output_review.get("corrected_deck_path") or ""),
        label="corrected deck",
    )
    verification_status = str(output_review.get("verification_status") or "")
    if verification_status != "verified":
        raise CaseWorkspaceError(
            f"mechanical verification is not verified: {verification_status or 'missing'}"
        )

    payload: dict[str, Any] = {
        "schema_version": 1,
        "source": "clara_deck_revision_output_review_completion",
        "created_at": _now_iso(now),
        "voice_session": _relative_path(case_dir, session_dir),
        "completed_by": reviewer_clean,
        "review_note": note.strip() or None,
        "output_review_path": _relative_path(case_dir, review_path.resolve()),
        "output_review_sha256": _sha256(review_path.resolve()),
        "corrected_deck_path": _relative_path(case_dir, corrected_deck_path),
        "corrected_deck_sha256": _sha256(corrected_deck_path),
        "confirmations": confirmations,
        "summary": {
            "status": "complete",
            "final_delivery_allowed": True,
        },
    }
    completion_path = session_dir / "deck_revision_output_review_completion.json"
    completion_markdown_path = session_dir / "deck_revision_output_review_completion.md"
    _write_json(completion_path, payload)
    completion_markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return DeckRevisionOutputReviewCompletion(
        session_dir=session_dir,
        completion_path=completion_path,
        completion_markdown_path=completion_markdown_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Complete Clara's final semantic review loop for a corrected deck.",
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
        "--output-review",
        type=Path,
        default=None,
        help="Output review JSON path. Defaults to deck_revision_output_review.json.",
    )
    parser.add_argument("--audience-copy-reviewed", action="store_true")
    parser.add_argument("--process-language-reviewed", action="store_true")
    parser.add_argument("--requested-structure-reviewed", action="store_true")
    parser.add_argument("--semantic-evidence-fit-reviewed", action="store_true")
    parser.add_argument("--visual-render-reviewed", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = complete_deck_revision_output_review(
        args.case_dir,
        voice_session=args.voice_session,
        output_review_path=args.output_review,
        reviewer=args.reviewer,
        note=args.note,
        audience_copy_reviewed=args.audience_copy_reviewed,
        process_language_reviewed=args.process_language_reviewed,
        requested_structure_reviewed=args.requested_structure_reviewed,
        semantic_evidence_fit_reviewed=args.semantic_evidence_fit_reviewed,
        visual_render_reviewed=args.visual_render_reviewed,
    )
    LOGGER.info("wrote final output review completion to %s", result.completion_path)
    LOGGER.info(
        "wrote final output review completion markdown to %s",
        result.completion_markdown_path,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
