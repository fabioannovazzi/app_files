"""Build quote candidates for Clara deck-revision evidence slides."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from advisor_case_core import CaseWorkspaceError, validate_case_workspace

__all__ = [
    "DeckRevisionQuoteCandidateMatrixResult",
    "build_deck_revision_quote_candidate_matrix",
    "main",
]

LOGGER = logging.getLogger(__name__)

QUOTE_TRIGGER_TERMS = {
    "deck_revision_quote_candidate_matrix",
    "quote_candidate_matrix",
    "better quotes",
    "stronger quotes",
    "pull quotes",
    "source quotes",
    "select quotes",
    "replace quotes",
    "extract quotes",
    "interview evidence",
    "transcript evidence",
    "transcript excerpts",
    "source-backed examples",
    "citazioni migliori",
    "selezionare citazioni",
    "estrarre citazioni",
    "sostituire citazioni",
    "evidenze dalle interviste",
    "estratti dai transcript",
}

QUOTE_ACTION_TERMS = {
    "better",
    "estrarre",
    "extract",
    "find",
    "improve",
    "migliori",
    "mine",
    "pull",
    "replace",
    "select",
    "selezionare",
    "source",
    "stronger",
    "sostituire",
    "trovare",
}

QUOTE_OBJECT_TERMS = {
    "citazione",
    "citazioni",
    "evidence",
    "evidenza",
    "evidenze",
    "excerpt",
    "excerpts",
    "interview",
    "interviews",
    "intervista",
    "interviste",
    "quote",
    "quotes",
    "transcript",
    "transcripts",
}

STOPWORDS = {
    "about",
    "after",
    "again",
    "anche",
    "before",
    "better",
    "change",
    "changes",
    "dalla",
    "dalle",
    "degli",
    "della",
    "delle",
    "devono",
    "evidence",
    "interview",
    "interviews",
    "main",
    "meglio",
    "nella",
    "nelle",
    "only",
    "point",
    "points",
    "project",
    "pull",
    "quote",
    "quotes",
    "slide",
    "these",
    "this",
    "transcript",
    "transcripts",
    "using",
    "with",
}


@dataclass(frozen=True)
class DeckRevisionQuoteCandidateMatrixResult:
    """Quote-candidate matrix artifacts for a deck-revision plan."""

    session_dir: Path
    matrix_path: Path
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


def _clean_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_clean_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_clean_text(item) for item in value.values())
    return str(value or "")


def change_needs_quote_candidate_matrix(change: Mapping[str, Any]) -> bool:
    """Return true when a change asks Clara to source quotes/transcript evidence."""

    fields = [
        change.get("change_type"),
        change.get("requested_change"),
        change.get("interpretation"),
        change.get("rationale"),
        change.get("material_requirements"),
        change.get("success_criteria"),
    ]
    haystack = _clean_text(fields).casefold()
    if any(term in haystack for term in QUOTE_TRIGGER_TERMS):
        return True
    tokens = set(re.findall(r"[\w']+", haystack))
    return bool(tokens & QUOTE_ACTION_TERMS and tokens & QUOTE_OBJECT_TERMS)


def _terms_for_change(change: Mapping[str, Any]) -> list[str]:
    raw = " ".join(
        _clean_text(change.get(key))
        for key in (
            "slide_title",
            "change_type",
            "requested_change",
            "interpretation",
            "rationale",
            "material_requirements",
        )
    )
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]{5,}", raw.casefold())
    counts = Counter(word for word in words if word not in STOPWORDS)
    return [word for word, _count in counts.most_common(18)]


def _iter_source_files(case_dir: Path, session_dir: Path) -> Iterable[Path]:
    allowed_suffixes = {".md", ".txt"}
    skipped_names = {
        "deck_revision_changes.md",
        "deck_revision_understanding.md",
        "deck_revision_handoff.md",
        "deck_revision_material_needs.md",
        "deck_revision_prompt.md",
    }
    for path in sorted(case_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in allowed_suffixes:
            continue
        rel_parts = path.resolve().relative_to(case_dir.resolve()).parts
        rel_parts_lower = {part.casefold() for part in rel_parts}
        name_lower = path.name.casefold()
        is_interview_source = (
            "interviews" in rel_parts_lower
            or "voice_sessions" in rel_parts_lower
            or (
                "notes" in rel_parts_lower
                and (
                    "transcript" in name_lower
                    or "intervista" in name_lower
                    or "interview" in name_lower
                )
            )
        )
        if not is_interview_source:
            continue
        if path.name in skipped_names:
            continue
        if path.name.startswith("deck_revision_"):
            continue
        if session_dir in path.parents:
            continue
        yield path


def _passages(path: Path) -> Iterable[tuple[int, str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    buffer: list[str] = []
    start_line = 1
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            if buffer:
                yield start_line, " ".join(buffer)
                buffer = []
            start_line = index + 1
            continue
        if not buffer:
            start_line = index
        buffer.append(stripped)
        if len(" ".join(buffer)) > 900:
            yield start_line, " ".join(buffer)
            buffer = []
            start_line = index + 1
    if buffer:
        yield start_line, " ".join(buffer)


def _speaker_from_passage(text: str) -> str | None:
    bracket_match = re.match(r"\[[0-9:]+\]\s*([^:]{2,80}):", text)
    if bracket_match:
        return bracket_match.group(1).strip()
    markdown_match = re.match(r"\*\*([^:*]{2,80})\*\*:", text)
    if markdown_match:
        return markdown_match.group(1).strip()
    label_match = re.match(r"([A-ZÀ-ÖØ-Þ][^:]{2,80}):", text)
    if label_match:
        return label_match.group(1).strip()
    return None


def _score_passage(text: str, terms: list[str]) -> tuple[int, list[str]]:
    folded = text.casefold()
    hits = [term for term in terms if term in folded]
    return len(hits), hits


def _candidate_rows(
    *,
    case_dir: Path,
    session_dir: Path,
    change: Mapping[str, Any],
    max_candidates: int,
) -> list[dict[str, Any]]:
    terms = _terms_for_change(change)
    rows: list[dict[str, Any]] = []
    if not terms:
        return rows
    for source_path in _iter_source_files(case_dir, session_dir):
        for line_number, passage in _passages(source_path):
            score, hits = _score_passage(passage, terms)
            if score <= 0:
                continue
            excerpt = passage
            if len(excerpt) > 700:
                excerpt = excerpt[:697].rstrip() + "..."
            rows.append(
                {
                    "source_path": _relative_path(case_dir, source_path),
                    "line_number": line_number,
                    "speaker": _speaker_from_passage(passage),
                    "excerpt": excerpt,
                    "mechanical_hit_count": score,
                    "matched_terms": hits[:12],
                    "selection_status": "candidate",
                    "codex_review_note": "",
                }
            )
    rows.sort(
        key=lambda row: (
            -int(row["mechanical_hit_count"]),
            str(row["source_path"]),
            int(row["line_number"]),
        )
    )
    return rows[:max_candidates]


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Deck Revision Quote Candidate Matrix",
        "",
        f"Status: `{payload['summary']['status']}`",
        "",
        f"- Changes requiring quote mining: {payload['summary']['required_changes']}",
        f"- Candidate rows: {payload['summary']['candidate_rows']}",
        "",
        "This is an evidence-preparation artifact. It does not decide which quotes are best; Clara/Codex must review candidates for relevance, source diversity, sharpness, and room-safe wording before editing slides.",
        "",
    ]
    for change in payload["changes"]:
        lines.extend(
            [
                f"## {change['change_id']} - Slide {change.get('slide_number')}",
                "",
                f"Requested change: {change.get('requested_change') or 'not recorded'}",
                "",
                f"Search terms: {', '.join(change['search_terms']) or 'none'}",
                "",
            ]
        )
        candidates = change.get("candidates", [])
        if not candidates:
            lines.extend(["No candidates found.", ""])
            continue
        for index, candidate in enumerate(candidates[:12], start=1):
            speaker = candidate.get("speaker") or "speaker not inferred"
            lines.extend(
                [
                    f"{index}. `{candidate['source_path']}:{candidate['line_number']}` ({speaker})",
                    f"   - Hits: {candidate['mechanical_hit_count']} ({', '.join(candidate['matched_terms'])})",
                    f"   - Excerpt: {candidate['excerpt']}",
                ]
            )
        lines.append("")
    return "\n".join(lines)


def build_deck_revision_quote_candidate_matrix(
    case_dir: Path,
    *,
    voice_session: Path | None = None,
    plan_path: Path | None = None,
    max_candidates_per_change: int = 30,
    now: datetime | None = None,
) -> DeckRevisionQuoteCandidateMatrixResult:
    """Write candidate transcript passages for quote-backed deck changes."""

    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))
    if max_candidates_per_change < 1:
        raise CaseWorkspaceError("max_candidates_per_change must be at least 1")

    case_dir = case_dir.resolve()
    session_dir = _resolve_voice_session_dir(case_dir, voice_session)
    resolved_plan_path, plan = _load_plan(session_dir, plan_path, case_dir)
    raw_changes = plan.get("changes")
    if not isinstance(raw_changes, list):
        raise CaseWorkspaceError("normalized deck revision plan has no changes list")

    change_records: list[dict[str, Any]] = []
    for raw_change in raw_changes:
        if not isinstance(raw_change, dict) or not change_needs_quote_candidate_matrix(
            raw_change
        ):
            continue
        terms = _terms_for_change(raw_change)
        candidates = _candidate_rows(
            case_dir=case_dir,
            session_dir=session_dir,
            change=raw_change,
            max_candidates=max_candidates_per_change,
        )
        change_records.append(
            {
                "change_id": raw_change.get("change_id"),
                "slide_number": raw_change.get("slide_number"),
                "requested_change": raw_change.get("requested_change"),
                "interpretation": raw_change.get("interpretation"),
                "search_terms": terms,
                "candidate_count": len(candidates),
                "candidates": candidates,
            }
        )

    candidate_count = sum(int(change["candidate_count"]) for change in change_records)
    status = (
        "not_required"
        if not change_records
        else "ready_for_codex_review" if candidate_count else "no_candidates_found"
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "source": "clara_deck_revision_quote_candidate_matrix",
        "created_at": _now_iso(now),
        "voice_session": _relative_path(case_dir, session_dir),
        "plan_path": _relative_path(case_dir, resolved_plan_path),
        "summary": {
            "status": status,
            "required_changes": len(change_records),
            "candidate_rows": candidate_count,
            "max_candidates_per_change": max_candidates_per_change,
        },
        "changes": change_records,
    }
    matrix_path = session_dir / "deck_revision_quote_candidate_matrix.json"
    review_path = session_dir / "deck_revision_quote_candidate_matrix.md"
    _write_json(matrix_path, payload)
    review_path.write_text(_render_markdown(payload), encoding="utf-8")
    return DeckRevisionQuoteCandidateMatrixResult(
        session_dir=session_dir,
        matrix_path=matrix_path,
        review_path=review_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build quote candidates for Clara deck-revision evidence slides.",
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
    parser.add_argument(
        "--max-candidates-per-change",
        type=int,
        default=30,
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build_deck_revision_quote_candidate_matrix(
        args.case_dir,
        voice_session=args.voice_session,
        plan_path=args.plan,
        max_candidates_per_change=args.max_candidates_per_change,
    )
    LOGGER.info("wrote deck revision quote matrix to %s", result.matrix_path)
    LOGGER.info("wrote deck revision quote-matrix review to %s", result.review_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
