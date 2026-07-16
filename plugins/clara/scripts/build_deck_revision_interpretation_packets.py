"""Build focused Clara deck-revision interpretation packets."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from advisor_case_core import CaseWorkspaceError, validate_case_workspace

__all__ = [
    "DeckRevisionInterpretationPacketsResult",
    "build_deck_revision_interpretation_packets",
    "main",
]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeckRevisionInterpretationPacketsResult:
    """Artifacts created for focused deck-revision interpretation."""

    session_dir: Path
    packet_index_path: Path
    review_path: Path
    packet_dir: Path


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


def _required_workbench(session_dir: Path) -> dict[str, Any]:
    workbench_path = session_dir / "deck_revision_workbench.json"
    if not workbench_path.is_file():
        raise CaseWorkspaceError(
            f"deck revision workbench is missing: {workbench_path}; run build_deck_revision_workbench.py first"
        )
    return _read_json(workbench_path)


def _slide_records(workbench: Mapping[str, Any]) -> list[dict[str, Any]]:
    deck = workbench.get("deck")
    if not isinstance(deck, Mapping):
        raise CaseWorkspaceError("deck revision workbench is missing deck metadata")
    slides: list[dict[str, Any]] = []
    for slide in deck.get("slides", []):
        if isinstance(slide, dict) and isinstance(slide.get("slide_number"), int):
            slides.append(dict(slide))
    if not slides:
        raise CaseWorkspaceError("deck revision workbench has no slide records")
    return slides


def _deck_outline(slides: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "slide_number": slide.get("slide_number"),
            "title": slide.get("title") or "",
        }
        for slide in slides
    ]


def _feedback_entries(workbench: Mapping[str, Any]) -> list[dict[str, Any]]:
    visual_context = workbench.get("visual_context")
    if not isinstance(visual_context, Mapping):
        return []
    timeline = visual_context.get("feedback_timeline")
    if not isinstance(timeline, Mapping):
        return []
    entries = timeline.get("entries")
    if not isinstance(entries, list):
        return []
    return [dict(entry) for entry in entries if isinstance(entry, dict)]


def _entry_text(entry: Mapping[str, Any]) -> str:
    for key in ("clean_text", "matched_realtime_text", "text"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _entry_slide_number(entry: Mapping[str, Any]) -> int | None:
    match = entry.get("slide_match")
    if not isinstance(match, Mapping):
        return None
    confidence = str(match.get("confidence") or "")
    if confidence not in {"high", "medium"}:
        return None
    slide_number = match.get("best_slide_number")
    if isinstance(slide_number, int) and not isinstance(slide_number, bool):
        return slide_number
    return None


def _frame_summary(frame: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": frame.get("status"),
        "path": frame.get("path"),
        "frame_time_ms": frame.get("frame_time_ms"),
        "slide_match": (
            frame.get("slide_match")
            if isinstance(frame.get("slide_match"), dict)
            else None
        ),
    }


def _entry_summary(entry: Mapping[str, Any]) -> dict[str, Any]:
    frames = entry.get("frames")
    frame_records = (
        [_frame_summary(frame) for frame in frames if isinstance(frame, Mapping)]
        if isinstance(frames, list)
        else []
    )
    return {
        "feedback_unit_id": entry.get("feedback_unit_id"),
        "text": _entry_text(entry),
        "start_ms": entry.get("start_ms"),
        "end_ms": entry.get("end_ms"),
        "alignment_confidence": entry.get("alignment_confidence"),
        "alignment_confidence_label": entry.get("alignment_confidence_label"),
        "slide_match": (
            entry.get("slide_match")
            if isinstance(entry.get("slide_match"), dict)
            else None
        ),
        "frames": frame_records,
    }


def _packet_markdown(packet: Mapping[str, Any]) -> str:
    lines = [
        f"# Deck Revision Interpretation Packet {packet['packet_id']}",
        "",
        f"Scope: `{packet['packet_scope']}`",
        f"Slides: `{packet['slide_numbers']}`",
        "",
        "This packet is a focused semantic input. Clara/Codex should interpret only",
        "the feedback in this packet, draft candidate change records if needed, and",
        "avoid using the full workbench as one giant prompt.",
        "",
        "## Slides",
        "",
    ]
    for slide in packet["slides"]:
        lines.append(f"- Slide {slide['slide_number']}: {slide.get('title') or ''}")
    lines.extend(["", "## Feedback Units", ""])
    if packet["feedback_units"]:
        for entry in packet["feedback_units"]:
            unit_id = entry.get("feedback_unit_id") or "feedback"
            text = entry.get("text") or ""
            lines.append(f"- `{unit_id}`: {text}")
    else:
        lines.append("- No routed feedback units; use this only for deck-level review.")
    lines.extend(
        [
            "",
            "## Expected Output",
            "",
            "- Candidate changes for this packet only, or an explicit no-change note.",
            "- Each candidate change must keep transcript evidence separate from visual/deck evidence.",
            "- Do not edit the PPTX in this step.",
            "",
        ]
    )
    return "\n".join(lines)


def _index_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Deck Revision Interpretation Packets",
        "",
        f"Status: `{payload['summary']['status']}`",
        "",
        "Use these packets before writing `deck_revision_changes.json`. The global",
        "workbench remains an evidence index; semantic interpretation should happen",
        "inside the focused slide/deck packets, not as one huge semantic prompt.",
        "",
        f"- Packet count: {payload['summary']['packet_count']}",
        f"- Slide packets: {payload['summary']['slide_packets']}",
        f"- Deck/general packets: {payload['summary']['deck_packets']}",
        "",
        "## Packets",
        "",
    ]
    for packet in payload["packets"]:
        lines.append(
            f"- `{packet['packet_id']}` `{packet['packet_scope']}` slides "
            f"`{packet['slide_numbers']}`: `{packet['packet_path']}`"
        )
    lines.append("")
    return "\n".join(lines)


def build_deck_revision_interpretation_packets(
    case_dir: Path,
    *,
    voice_session: Path | None = None,
    now: datetime | None = None,
) -> DeckRevisionInterpretationPacketsResult:
    """Build focused evidence packets before Clara writes the change list.

    This deterministic step is justified because it only packages slide records
    and already-computed timeline/slide-match evidence into smaller inputs. It
    does not decide what a speaker meant or what deck edits are required.
    """

    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    case_dir = case_dir.resolve()
    session_dir = _resolve_voice_session_dir(case_dir, voice_session)
    workbench = _required_workbench(session_dir)
    slides = _slide_records(workbench)
    slide_lookup = {slide["slide_number"]: slide for slide in slides}
    entries = _feedback_entries(workbench)

    routed_entries: dict[int, list[dict[str, Any]]] = {}
    general_entries: list[dict[str, Any]] = []
    for entry in entries:
        slide_number = _entry_slide_number(entry)
        if slide_number in slide_lookup:
            routed_entries.setdefault(slide_number, []).append(_entry_summary(entry))
        else:
            general_entries.append(_entry_summary(entry))

    packet_dir = session_dir / "deck_revision_interpretation_packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    created_at = _now_iso(now)
    packets: list[dict[str, Any]] = []
    packet_payloads: list[dict[str, Any]] = []
    deck_outline = _deck_outline(slides)

    for slide_number in sorted(routed_entries):
        packet_id = f"packet-{len(packet_payloads) + 1:03d}"
        packet_path = packet_dir / f"{packet_id}.json"
        review_path = packet_dir / f"{packet_id}.md"
        packet = {
            "schema_version": 1,
            "source": "clara_deck_revision_interpretation_packet",
            "created_at": created_at,
            "packet_id": packet_id,
            "packet_scope": "slide",
            "slide_numbers": [slide_number],
            "workbench_path": _relative_path(
                case_dir, session_dir / "deck_revision_workbench.json"
            ),
            "changes_output_path": workbench["source_paths"]["changes_output_path"],
            "deck_outline": deck_outline,
            "slides": [slide_lookup[slide_number]],
            "feedback_units": routed_entries[slide_number],
            "semantic_boundary": (
                "Packet creation is deterministic evidence routing only; Clara/Codex "
                "must decide whether the packet contains a requested deck change."
            ),
        }
        _write_json(packet_path, packet)
        review_path.write_text(_packet_markdown(packet), encoding="utf-8")
        packet_payloads.append(packet)
        packets.append(
            {
                "packet_id": packet_id,
                "packet_scope": "slide",
                "slide_numbers": [slide_number],
                "feedback_unit_count": len(routed_entries[slide_number]),
                "packet_path": _relative_path(case_dir, packet_path),
                "review_path": _relative_path(case_dir, review_path),
            }
        )

    if general_entries or not packets:
        packet_id = f"packet-{len(packet_payloads) + 1:03d}"
        packet_path = packet_dir / f"{packet_id}.json"
        review_path = packet_dir / f"{packet_id}.md"
        packet = {
            "schema_version": 1,
            "source": "clara_deck_revision_interpretation_packet",
            "created_at": created_at,
            "packet_id": packet_id,
            "packet_scope": "deck_or_unmatched_context",
            "slide_numbers": [slide["slide_number"] for slide in slides],
            "workbench_path": _relative_path(
                case_dir, session_dir / "deck_revision_workbench.json"
            ),
            "changes_output_path": workbench["source_paths"]["changes_output_path"],
            "deck_outline": deck_outline,
            "slides": slides,
            "feedback_units": general_entries,
            "semantic_boundary": (
                "This packet exists for deck-level, global, unmatched, or low-confidence "
                "feedback. Clara/Codex decides whether it contains actionable changes."
            ),
        }
        _write_json(packet_path, packet)
        review_path.write_text(_packet_markdown(packet), encoding="utf-8")
        packet_payloads.append(packet)
        packets.append(
            {
                "packet_id": packet_id,
                "packet_scope": "deck_or_unmatched_context",
                "slide_numbers": [slide["slide_number"] for slide in slides],
                "feedback_unit_count": len(general_entries),
                "packet_path": _relative_path(case_dir, packet_path),
                "review_path": _relative_path(case_dir, review_path),
            }
        )

    payload: dict[str, Any] = {
        "schema_version": 1,
        "source": "clara_deck_revision_interpretation_packets",
        "created_at": created_at,
        "voice_session": _relative_path(case_dir, session_dir),
        "workbench_path": _relative_path(
            case_dir, session_dir / "deck_revision_workbench.json"
        ),
        "changes_output_path": workbench["source_paths"]["changes_output_path"],
        "summary": {
            "status": "ready_for_packet_interpretation",
            "packet_count": len(packets),
            "slide_packets": sum(
                1 for packet in packets if packet["packet_scope"] == "slide"
            ),
            "deck_packets": sum(
                1
                for packet in packets
                if packet["packet_scope"] == "deck_or_unmatched_context"
            ),
            "routed_feedback_units": sum(
                packet["feedback_unit_count"]
                for packet in packets
                if packet["packet_scope"] == "slide"
            ),
            "unmatched_feedback_units": len(general_entries),
        },
        "deterministic_boundary": (
            "Packets route available evidence into smaller prompts; they do not "
            "classify feedback as a deck change."
        ),
        "packets": packets,
    }
    index_path = session_dir / "deck_revision_interpretation_packets.json"
    review_path = session_dir / "deck_revision_interpretation_packets.md"
    _write_json(index_path, payload)
    review_path.write_text(_index_markdown(payload), encoding="utf-8")
    return DeckRevisionInterpretationPacketsResult(
        session_dir=session_dir,
        packet_index_path=index_path,
        review_path=review_path,
        packet_dir=packet_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build focused Clara deck-revision interpretation packets.",
    )
    parser.add_argument("case_dir", type=Path)
    parser.add_argument(
        "--voice-session",
        type=Path,
        default=None,
        help="Voice session folder name/path. Defaults to latest voice session.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build_deck_revision_interpretation_packets(
        args.case_dir,
        voice_session=args.voice_session,
    )
    LOGGER.info("wrote interpretation packets to %s", result.packet_index_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
