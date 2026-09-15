"""Complete Clara's final semantic review loop for a corrected deck."""

from __future__ import annotations

# Direct CLI calls must select dependencies before importing workflow modules.
if __name__ == "__main__":
    import runpy as _runpy
    from pathlib import Path as _Path

    for _parent in _Path(__file__).resolve().parents:
        _launcher = _parent / "scripts" / "self_relaunch.py"
        if not _launcher.is_file():
            _launcher = _parent / "clara" / "scripts" / "self_relaunch.py"
        if _launcher.is_file():
            _runpy.run_path(str(_launcher))["ensure_running_in_managed_venv"](__file__)
            break
    else:
        # Standalone components retain their host's dependency setup.
        if any(
            (_p / "components.json").is_file()
            for _p in _Path(__file__).resolve().parents
        ):
            raise SystemExit(
                "Managed Python launcher is missing; rebuild the plugin package."
            )

import argparse
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from advisor_case_core import CaseWorkspaceError, validate_case_workspace
from verify_deck_revision_output import verification_ready_for_output_review

__all__ = [
    "DeckRevisionOutputReviewCompletion",
    "complete_deck_revision_output_review",
    "verify_deck_revision_output_review",
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


def _verified_output_review(case_dir: Path, review_path: Path) -> Path:
    """Verify the execution bytes behind a pending output review."""
    output_review = _read_json(review_path)
    # A prior verification label is meaningful only for its exact input bytes.
    # This check binds mechanical execution, not the reviewer's semantic judgment.
    inputs = output_review.get("execution_inputs")
    if (
        output_review.get("approved_execution") is not True
        or not isinstance(inputs, dict)
        or set(inputs)
        != {
            "corrected_deck",
            "plan",
            "source_deck",
            "verification",
            "approval",
            "understanding",
        }
    ):
        raise CaseWorkspaceError(
            "output review lacks approved execution identity; rerun approved application"
        )
    for role, item in inputs.items():
        if not isinstance(item, dict):
            raise CaseWorkspaceError("output review has malformed execution identity")
        path = _resolve_case_file(
            case_dir, str(item.get("path") or ""), label="review execution input"
        )
        if role in {"corrected_deck", "plan"} and path != _resolve_case_file(
            case_dir, str(output_review.get(f"{role}_path") or ""), label=role
        ):
            raise CaseWorkspaceError(
                "output review execution identity points to another artifact"
            )
        if _sha256(path) != item.get("sha256"):
            raise CaseWorkspaceError(
                "output review execution input changed; rerun application and review"
            )
    corrected_deck_path = _resolve_case_file(
        case_dir,
        str(output_review.get("corrected_deck_path") or ""),
        label="corrected deck",
    )
    verification_status = str(output_review.get("verification_status") or "")
    verification = _read_json(
        _resolve_case_file(
            case_dir, inputs["verification"]["path"], label="verification"
        )
    )
    if verification_status != verification["summary"][
        "status"
    ] or not verification_ready_for_output_review(verification):
        raise CaseWorkspaceError(
            f"mechanical verification is not verified: {verification_status or 'missing'}"
        )

    return corrected_deck_path


def _check_criterion_reviews(
    case_dir: Path, review_path: Path, reviews: Mapping[str, Any]
) -> None:
    review = _read_json(review_path)
    verification = _read_json(
        _resolve_case_file(
            case_dir,
            review["execution_inputs"]["verification"]["path"],
            label="verification",
        )
    )
    required = {
        criterion["criterion_id"]
        for change in verification["changes"]
        for criterion in change["success_criteria"]
        if criterion.get("review_required")
    }
    if not isinstance(reviews, dict) or set(reviews) != required:
        raise CaseWorkspaceError(
            "criterion reviews must cover exactly the pending criteria"
        )
    for criterion_id, item in reviews.items():
        if (
            not isinstance(item, dict)
            or item.get("reviewed") is not True
            or not isinstance(item.get("note"), str)
            or not item["note"].strip()
        ):
            raise CaseWorkspaceError(f"criterion review is incomplete: {criterion_id}")


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
    criterion_reviews: dict[str, Any] | None = None,
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
    corrected_deck_path = _verified_output_review(case_dir, review_path)
    _check_criterion_reviews(case_dir, review_path, criterion_reviews or {})

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
        "criterion_reviews": criterion_reviews or {},
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


def verify_deck_revision_output_review(
    case_dir: Path, *, voice_session: Path
) -> dict[str, Any]:
    """Check current byte bindings and declared final-review confirmations without writing."""
    case_dir = case_dir.resolve()
    session = _resolve_voice_session_dir(case_dir, voice_session)
    review_path = session / "deck_revision_output_review.json"
    deck = _verified_output_review(case_dir, review_path)
    completion = _read_json(session / "deck_revision_output_review_completion.json")
    _check_criterion_reviews(
        case_dir, review_path, completion.get("criterion_reviews", {})
    )
    if (
        completion.get("output_review_sha256") != _sha256(review_path)
        or completion.get("corrected_deck_sha256") != _sha256(deck)
        or _resolve_case_file(
            case_dir, completion.get("output_review_path", ""), label="output review"
        )
        != review_path.resolve()
        or _resolve_case_file(
            case_dir, completion.get("corrected_deck_path", ""), label="corrected deck"
        )
        != deck
        or completion.get("summary", {}).get("status") != "complete"
        or completion.get("summary", {}).get("final_delivery_allowed") is not True
        or any(
            completion.get("confirmations", {}).get(key) is not True
            for key in REQUIRED_CONFIRMATIONS
        )
    ):
        raise CaseWorkspaceError(
            "final review is stale or lacks required confirmations"
        )
    return completion


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Complete Clara's final semantic review loop for a corrected deck.",
    )
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument("--criterion-reviews", type=Path, default=None)
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
        criterion_reviews=(
            _read_json(args.criterion_reviews) if args.criterion_reviews else None
        ),
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
