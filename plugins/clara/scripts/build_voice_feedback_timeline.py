"""Build feedback-unit video timelines from imported Clara voice captures."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "FeedbackTimelineError",
    "build_feedback_timeline",
    "build_feedback_timeline_payload",
    "main",
]

MAX_UNIT_WORDS = 95
MIN_UNIT_WORDS = 20
MAX_UNIT_CHARS = 700
MAX_ALIGNMENT_SEGMENT_WINDOW = 12
ALIGNMENT_LOOKAHEAD_SEGMENTS = 3
MIN_USABLE_ALIGNMENT_CONFIDENCE = 0.50


class FeedbackTimelineError(RuntimeError):
    """Raised when a feedback timeline cannot be built from supplied inputs."""


@dataclass(frozen=True)
class _FeedbackUnit:
    unit_id: str
    text: str
    word_count: int


@dataclass(frozen=True)
class _RealtimeSegment:
    segment_id: str
    text: str
    start_ms: int | None
    end_ms: int | None
    active_slide_id: str
    active_slide_title: str
    active_slide_index: int | None
    active_slide_number: int | None
    active_deck_title: str
    active_slide_relative_ms: int | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _relative_path(path: Path, base_dir: Path | None) -> str:
    if base_dir is None:
        return str(path)
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def _resolve_ffmpeg_path(explicit_path: str | None) -> str | None:
    if explicit_path is not None:
        clean = explicit_path.strip()
        return clean or None
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError:
        return None
    try:
        bundled_ffmpeg = str(get_ffmpeg_exe()).strip()
    except (OSError, RuntimeError):
        return None
    return bundled_ffmpeg or None


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower(), flags=re.UNICODE)


def _sentence_parts(text: str) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", clean)
    return [part.strip() for part in parts if part.strip()]


def _feedback_units(clean_transcript: str) -> list[_FeedbackUnit]:
    """Create mechanical candidate units; semantic judgement remains model-led."""

    sentences = _sentence_parts(clean_transcript)
    units: list[_FeedbackUnit] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        sentence_words = len(_word_tokens(sentence))
        too_large = current and (
            current_words + sentence_words > MAX_UNIT_WORDS
            or len(" ".join([*current, sentence])) > MAX_UNIT_CHARS
        )
        enough_to_close = current_words >= MIN_UNIT_WORDS
        if too_large and enough_to_close:
            text = " ".join(current).strip()
            units.append(
                _FeedbackUnit(
                    unit_id=f"F{len(units) + 1:03d}",
                    text=text,
                    word_count=len(_word_tokens(text)),
                )
            )
            current = []
            current_words = 0
        current.append(sentence)
        current_words += sentence_words
    if current:
        text = " ".join(current).strip()
        units.append(
            _FeedbackUnit(
                unit_id=f"F{len(units) + 1:03d}",
                text=text,
                word_count=len(_word_tokens(text)),
            )
        )
    return units


def _clean_realtime_segments(raw_segments: Sequence[object]) -> list[_RealtimeSegment]:
    segments: list[_RealtimeSegment] = []
    for index, raw_segment in enumerate(raw_segments):
        if not isinstance(raw_segment, Mapping):
            continue
        text = str(raw_segment.get("text", "")).strip()
        if not text:
            continue
        start_ms = _coerce_ms(raw_segment.get("start_ms"))
        end_ms = _coerce_ms(raw_segment.get("end_ms"))
        if start_ms is None and end_ms is not None:
            start_ms = end_ms
        if end_ms is None and start_ms is not None:
            end_ms = start_ms
        segment_id = str(
            raw_segment.get("segment_id")
            or raw_segment.get("item_id")
            or raw_segment.get("segment_index")
            or f"R{index + 1:04d}"
        )
        segments.append(
            _RealtimeSegment(
                segment_id=segment_id,
                text=text,
                start_ms=start_ms,
                end_ms=end_ms,
                active_slide_id=str(raw_segment.get("active_slide_id", "")).strip(),
                active_slide_title=str(
                    raw_segment.get("active_slide_title", "")
                ).strip(),
                active_slide_index=_coerce_ms(raw_segment.get("active_slide_index")),
                active_slide_number=_coerce_ms(raw_segment.get("active_slide_number")),
                active_deck_title=str(raw_segment.get("active_deck_title", "")).strip(),
                active_slide_relative_ms=_coerce_ms(
                    raw_segment.get("active_slide_relative_ms")
                ),
            )
        )
    return segments


def _active_slide_context(
    segment: _RealtimeSegment,
) -> dict[str, Any] | None:
    if not segment.active_slide_id and not segment.active_slide_title:
        return None
    return {
        "slide_id": segment.active_slide_id,
        "slide_title": segment.active_slide_title,
        "slide_index": segment.active_slide_index,
        "slide_number": segment.active_slide_number,
        "deck_title": segment.active_deck_title,
        "relative_ms": segment.active_slide_relative_ms,
        "source": "capture_handle",
    }


def _active_slides_for_segments(
    segments: Sequence[_RealtimeSegment],
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    seen: set[tuple[object, ...]] = set()
    for segment in segments:
        context = _active_slide_context(segment)
        if context is None:
            continue
        identity = (
            context["slide_id"],
            context["slide_title"],
            context["slide_index"],
            context["slide_number"],
            context["deck_title"],
        )
        if identity in seen:
            continue
        seen.add(identity)
        contexts.append(context)
    return contexts


def _coerce_ms(value: object) -> int | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0, int(round(number)))


def _token_similarity(left: str, right: str) -> float:
    left_tokens = _word_tokens(left)
    right_tokens = _word_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    left_text = " ".join(left_tokens)
    right_text = " ".join(right_tokens)
    sequence_score = SequenceMatcher(None, left_text, right_text).ratio()
    left_set = set(left_tokens)
    right_set = set(right_tokens)
    overlap = len(left_set & right_set)
    if overlap == 0:
        overlap_score = 0.0
    else:
        precision = overlap / len(right_set)
        recall = overlap / len(left_set)
        overlap_score = (2 * precision * recall) / (precision + recall)
    ratio = min(len(left_tokens), len(right_tokens)) / max(
        len(left_tokens), len(right_tokens)
    )
    return round((0.55 * sequence_score) + (0.35 * overlap_score) + (0.10 * ratio), 4)


def _confidence_label(score: float) -> str:
    if score >= 0.72:
        return "high"
    if score >= 0.50:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def _has_extracted_frame(entry: Mapping[str, Any]) -> bool:
    frames = entry.get("frames", [])
    if not isinstance(frames, list):
        return False
    return any(
        isinstance(frame, Mapping)
        and frame.get("status") == "extracted"
        and str(frame.get("path", "")).strip()
        for frame in frames
    )


def _annotate_entry_evidence_status(entry: dict[str, Any]) -> None:
    """Label mechanical evidence quality without making semantic slide judgements."""

    segment_ids = entry.get("realtime_segment_ids", [])
    score = float(entry.get("alignment_confidence", 0.0))
    if not isinstance(segment_ids, list) or not segment_ids:
        entry["visual_evidence_status"] = "no_alignment"
        entry["use_as_visual_evidence"] = False
        entry["evidence_note"] = (
            "No timed realtime segment was aligned; do not use this row as "
            "visual evidence."
        )
        return
    if score < MIN_USABLE_ALIGNMENT_CONFIDENCE:
        entry["visual_evidence_status"] = "weak_alignment"
        entry["use_as_visual_evidence"] = False
        entry["evidence_note"] = (
            "Text alignment confidence is below the usable threshold; treat this "
            "row only as a weak timing hint and inspect the raw video/deck before "
            "using it."
        )
        return
    if _has_extracted_frame(entry):
        entry["visual_evidence_status"] = "visual_evidence"
        entry["use_as_visual_evidence"] = True
        entry["evidence_note"] = (
            "This row has usable text alignment and at least one extracted frame; "
            "the frame may be used as visual provenance, subject to human/model "
            "review of the visible content."
        )
        return
    entry["visual_evidence_status"] = "timing_only"
    entry["use_as_visual_evidence"] = False
    entry["evidence_note"] = (
        "This row has usable text alignment but no extracted frame path; use it "
        "only to navigate the raw video, not as standalone visual evidence."
    )


def _evidence_summary(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    active_slide_status_counts: dict[str, int] = {}
    skipped_segment_ids: list[str] = []
    for entry in entries:
        status = str(entry.get("visual_evidence_status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
        active_slide_status = str(
            entry.get("active_slide_context_status", "not_available")
        )
        active_slide_status_counts[active_slide_status] = (
            active_slide_status_counts.get(active_slide_status, 0) + 1
        )
        raw_skipped = entry.get("skipped_realtime_segment_ids_before_match", [])
        if isinstance(raw_skipped, list):
            skipped_segment_ids.extend(str(segment_id) for segment_id in raw_skipped)
    return {
        "entry_count": len(entries),
        "visual_evidence_entries": status_counts.get("visual_evidence", 0),
        "timing_only_entries": status_counts.get("timing_only", 0),
        "weak_alignment_entries": status_counts.get("weak_alignment", 0),
        "no_alignment_entries": status_counts.get("no_alignment", 0),
        "status_counts": status_counts,
        "active_slide_identified_entries": active_slide_status_counts.get(
            "identified", 0
        ),
        "active_slide_changed_entries": active_slide_status_counts.get("changed", 0),
        "active_slide_status_counts": active_slide_status_counts,
        "skipped_realtime_segment_count": len(skipped_segment_ids),
        "skipped_realtime_segment_ids": skipped_segment_ids,
        "minimum_usable_alignment_confidence": MIN_USABLE_ALIGNMENT_CONFIDENCE,
    }


def _best_monotonic_window(
    unit: _FeedbackUnit,
    realtime_segments: Sequence[_RealtimeSegment],
    cursor: int,
) -> tuple[int, int, float]:
    clean_words = max(1, unit.word_count)
    dynamic_window = max(
        2,
        min(MAX_ALIGNMENT_SEGMENT_WINDOW, math.ceil(clean_words / 10) + 2),
    )
    best_start = cursor
    best_end = cursor
    best_score = 0.0
    max_start = min(len(realtime_segments), cursor + ALIGNMENT_LOOKAHEAD_SEGMENTS + 1)
    for start in range(cursor, max_start):
        max_end = min(len(realtime_segments), start + dynamic_window)
        for end in range(start + 1, max_end + 1):
            candidate_text = " ".join(
                segment.text for segment in realtime_segments[start:end]
            )
            score = _token_similarity(unit.text, candidate_text)
            if score > best_score:
                best_start = start
                best_end = end
                best_score = score
    return best_start, best_end, best_score


def _frame_times_for_window(start_ms: int | None, end_ms: int | None) -> list[int]:
    if start_ms is None and end_ms is None:
        return []
    if start_ms is None:
        start_ms = end_ms
    if end_ms is None:
        end_ms = start_ms
    if start_ms is None or end_ms is None:
        return []
    if end_ms < start_ms:
        start_ms, end_ms = end_ms, start_ms
    duration = end_ms - start_ms
    if duration <= 3000:
        return [start_ms + max(0, duration // 2)]
    midpoint = start_ms + duration // 2
    if duration <= 12000:
        return [start_ms + 1000, midpoint, max(start_ms, end_ms - 1000)]
    return [start_ms + 2000, midpoint, max(start_ms, end_ms - 2000)]


def _extract_frame(
    *,
    ffmpeg_path: str,
    video_path: Path,
    frame_path: Path,
    frame_time_ms: int,
) -> tuple[bool, str]:
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    seconds = max(0, frame_time_ms) / 1000
    command = [
        ffmpeg_path,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{seconds:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(frame_path),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "ffmpeg failed").strip()
    if not frame_path.is_file():
        return False, "ffmpeg did not write a frame"
    return True, ""


def _extract_frames_for_entry(
    *,
    entry: dict[str, Any],
    video_path: Path,
    frames_dir: Path,
    base_dir: Path | None,
    ffmpeg_path: str | None,
) -> None:
    frame_times = _frame_times_for_window(entry.get("start_ms"), entry.get("end_ms"))
    frame_entries: list[dict[str, Any]] = []
    if not frame_times:
        entry["frame_extraction_status"] = "not_available"
        entry["frames"] = frame_entries
        return
    if not ffmpeg_path:
        entry["frame_extraction_status"] = "skipped"
        entry["frame_extraction_note"] = "ffmpeg was not available"
        entry["frames"] = [
            {"frame_time_ms": frame_time_ms, "path": "", "status": "not_extracted"}
            for frame_time_ms in frame_times
        ]
        return
    all_ok = True
    errors: list[str] = []
    for frame_time_ms in frame_times:
        frame_name = f"{entry['feedback_unit_id']}_{frame_time_ms:09d}.png"
        frame_path = frames_dir / frame_name
        ok, error = _extract_frame(
            ffmpeg_path=ffmpeg_path,
            video_path=video_path,
            frame_path=frame_path,
            frame_time_ms=frame_time_ms,
        )
        all_ok = all_ok and ok
        if error:
            errors.append(error[:300])
        frame_entries.append(
            {
                "frame_time_ms": frame_time_ms,
                "path": _relative_path(frame_path, base_dir) if ok else "",
                "status": "extracted" if ok else "error",
            }
        )
    entry["frames"] = frame_entries
    entry["frame_extraction_status"] = "complete" if all_ok else "partial_or_failed"
    if errors:
        entry["frame_extraction_note"] = "; ".join(dict.fromkeys(errors))[:800]


def _timeline_entries(
    *,
    clean_transcript: str,
    realtime_segments: Sequence[_RealtimeSegment],
) -> list[dict[str, Any]]:
    units = _feedback_units(clean_transcript)
    entries: list[dict[str, Any]] = []
    cursor = 0
    for unit in units:
        matched_segments: Sequence[_RealtimeSegment] = []
        start_index = cursor
        end_index = cursor
        score = 0.0
        previous_cursor = cursor
        if realtime_segments and cursor < len(realtime_segments):
            start_index, end_index, score = _best_monotonic_window(
                unit,
                realtime_segments,
                cursor,
            )
            matched_segments = realtime_segments[previous_cursor:end_index]
            cursor = max(end_index, cursor)
        scored_segments = realtime_segments[start_index:end_index]
        skipped_segments = realtime_segments[previous_cursor:start_index]
        start_ms_values = [
            segment.start_ms
            for segment in matched_segments
            if segment.start_ms is not None
        ]
        end_ms_values = [
            segment.end_ms for segment in matched_segments if segment.end_ms is not None
        ]
        start_ms = min(start_ms_values) if start_ms_values else None
        end_ms = max(end_ms_values) if end_ms_values else None
        active_slides = _active_slides_for_segments(matched_segments)
        active_slide_context_status = (
            "changed"
            if len(active_slides) > 1
            else "identified" if active_slides else "not_available"
        )
        entries.append(
            {
                "feedback_unit_id": unit.unit_id,
                "clean_text": unit.text,
                "clean_word_count": unit.word_count,
                "realtime_segment_ids": [
                    segment.segment_id for segment in matched_segments
                ],
                "scored_realtime_segment_ids": [
                    segment.segment_id for segment in scored_segments
                ],
                "skipped_realtime_segment_ids_before_match": [
                    segment.segment_id for segment in skipped_segments
                ],
                "skipped_realtime_text_before_match": " ".join(
                    segment.text for segment in skipped_segments
                ),
                "matched_realtime_text": " ".join(
                    segment.text for segment in matched_segments
                ),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "active_slide_at_start": active_slides[0] if active_slides else None,
                "active_slides": active_slides,
                "active_slide_context_status": active_slide_context_status,
                "active_slide_context_note": (
                    "Slide identity was recorded mechanically on the same capture-relative "
                    "clock as the realtime transcript; semantic interpretation remains "
                    "out of scope."
                    if active_slides
                    else "No active slide identity was attached to the aligned realtime "
                    "segments; use the screen video as fallback context."
                ),
                "alignment_confidence": score,
                "alignment_confidence_label": _confidence_label(score),
                "alignment_note": (
                    "Deterministic monotonic fuzzy alignment from clean transcript "
                    "unit to realtime timed transcript segments. The timing window "
                    "includes any realtime segments skipped before the best text "
                    "match so audio/video context is not silently dropped."
                    if matched_segments
                    else "No realtime timed segment was available for this unit."
                ),
            }
        )
    return entries


def build_feedback_timeline_payload(
    *,
    clean_transcript: str,
    timed_transcript_segments: Sequence[object],
    video_path: Path | None = None,
    transcript_path: Path | None = None,
    output_path: Path | None = None,
    base_dir: Path | None = None,
    extract_frames: bool = True,
    ffmpeg_path: str | None = None,
) -> dict[str, Any]:
    """Build a reviewable feedback-unit timeline.

    Deterministic alignment is justified here because both transcripts are from
    the same audio and must preserve chronology; semantic deck interpretation is
    intentionally left to a later model/Codex review step.
    """

    clean = clean_transcript.strip()
    if not clean:
        raise FeedbackTimelineError("clean transcript is missing")
    if video_path is None:
        raise FeedbackTimelineError("screen video path is missing")
    if not video_path.is_file():
        raise FeedbackTimelineError(f"screen video file is missing: {video_path}")
    realtime_segments = _clean_realtime_segments(timed_transcript_segments)
    if not realtime_segments:
        raise FeedbackTimelineError("timed transcript segments are missing")
    has_timestamps = any(
        segment.start_ms is not None or segment.end_ms is not None
        for segment in realtime_segments
    )
    if not has_timestamps:
        raise FeedbackTimelineError(
            "timed transcript segments do not include timestamps"
        )
    entries = _timeline_entries(
        clean_transcript=clean,
        realtime_segments=realtime_segments,
    )
    frames_dir = (output_path.parent if output_path else Path.cwd()) / "frames"
    resolved_ffmpeg = _resolve_ffmpeg_path(ffmpeg_path)
    if extract_frames and video_path is not None and video_path.is_file():
        for entry in entries:
            _extract_frames_for_entry(
                entry=entry,
                video_path=video_path,
                frames_dir=frames_dir,
                base_dir=base_dir,
                ffmpeg_path=resolved_ffmpeg,
            )
    else:
        for entry in entries:
            entry["frames"] = [
                {"frame_time_ms": frame_time_ms, "path": "", "status": "not_extracted"}
                for frame_time_ms in _frame_times_for_window(
                    entry.get("start_ms"),
                    entry.get("end_ms"),
                )
            ]
            entry["frame_extraction_status"] = (
                "not_requested" if not extract_frames else "not_available"
            )
    for entry in entries:
        _annotate_entry_evidence_status(entry)
    return {
        "schema_version": 1,
        "created_at": _now_iso(),
        "source": "case_notes_voice_feedback_timeline",
        "transcript_path": (
            _relative_path(transcript_path, base_dir)
            if transcript_path is not None
            else ""
        ),
        "video_path": (
            _relative_path(video_path, base_dir) if video_path is not None else ""
        ),
        "frames_dir": _relative_path(frames_dir, base_dir),
        "alignment": {
            "method": "monotonic_fuzzy_text_alignment",
            "unit_source": "clean_transcript_candidate_feedback_units",
            "timing_source": "realtime_timed_transcript_segments",
            "active_slide_source": (
                "capture_handle_fields_embedded_in_timed_transcript_segments"
            ),
            "realtime_segment_count": len(realtime_segments),
            "active_slide_segment_count": sum(
                1 for segment in realtime_segments if _active_slide_context(segment)
            ),
            "feedback_unit_count": len(entries),
            "minimum_usable_alignment_confidence": MIN_USABLE_ALIGNMENT_CONFIDENCE,
            "deterministic_reason": (
                "Chronological text alignment is mechanically constrained by "
                "same-source audio order; semantic interpretation remains out of scope."
            ),
        },
        "evidence_summary": _evidence_summary(entries),
        "entries": entries,
    }


def build_feedback_timeline(
    *,
    clean_transcript: str,
    timed_transcript_segments: Sequence[object],
    output_path: Path,
    video_path: Path | None = None,
    transcript_path: Path | None = None,
    base_dir: Path | None = None,
    extract_frames: bool = True,
    ffmpeg_path: str | None = None,
) -> dict[str, Any]:
    payload = build_feedback_timeline_payload(
        clean_transcript=clean_transcript,
        timed_transcript_segments=timed_transcript_segments,
        video_path=video_path,
        transcript_path=transcript_path,
        output_path=output_path,
        base_dir=base_dir,
        extract_frames=extract_frames,
        ffmpeg_path=ffmpeg_path,
    )
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FeedbackTimelineError(f"could not read JSON: {path}") from error
    if not isinstance(payload, dict):
        raise FeedbackTimelineError(f"JSON payload must be an object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_json", type=Path)
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--transcript-path", type=Path)
    parser.add_argument("--base-dir", type=Path)
    parser.add_argument("--no-frames", action="store_true")
    parser.add_argument("--ffmpeg", default=None)
    args = parser.parse_args()
    bundle = _read_json(args.bundle_json)
    build_feedback_timeline(
        clean_transcript=str(bundle.get("user_transcript", "")),
        timed_transcript_segments=bundle.get("timed_transcript_segments", []),
        video_path=args.video,
        transcript_path=args.transcript_path,
        output_path=args.output,
        base_dir=args.base_dir,
        extract_frames=not args.no_frames,
        ffmpeg_path=args.ffmpeg,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
