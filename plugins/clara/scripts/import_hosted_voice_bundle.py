"""Import a hosted Clara voice bundle into a local case workspace."""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zipfile import BadZipFile, ZipFile

from advisor_case_core import (
    CASE_BRIEF_FILENAME,
    JUDGEMENT_KINDS,
    CaseWorkspaceError,
    add_judgement_entries,
    add_open_question,
    refresh_case_brief,
    register_material,
    validate_case_workspace,
)
from auto_attribute_hosted_transcript import (
    AutoTranscriptAttributionResult,
    auto_attribute_hosted_transcript,
)
from build_voice_feedback_timeline import FeedbackTimelineError, build_feedback_timeline
from prepare_voice_deck_revision import prepare_voice_deck_revision_intake

__all__ = [
    "HostedVoiceImportResult",
    "import_hosted_voice_bundle",
    "main",
    "read_hosted_voice_bundle_payload",
]

LOGGER = logging.getLogger(__name__)

DEFAULT_TRANSCRIPT_PROCESSING_NOTE = (
    "After transcription, local Clara/Codex must assign speaker attribution from "
    "the clean transcript and source metadata, check transcript quality against "
    "the document as a whole, and correct only obviously wrong transcription "
    "words when the intended wording is clear from transcript context or trusted "
    "case glossary. Speaker attribution is a local text-only Codex/Clara loop: "
    "preserve the unattributed transcript, create a speaker-attributed working "
    "transcript, inspect for obvious merged turns or wrong labels, and correct "
    "only clear text-supported boundary errors. Do not use an audio or voice "
    "diarization model for Clara speaker attribution. Preserve uncertainty "
    "instead of guessing."
)


@dataclass(frozen=True)
class HostedVoiceImportResult:
    """Local files and records created from a hosted voice bundle."""

    session_dir: Path
    raw_transcript_path: Path
    cleaned_notes_path: Path
    clara_review_path: Path
    judgement_candidates_path: Path
    discussion_review_pack_path: Path
    audio_path: Path | None
    video_path: Path | None
    video_timeline_path: Path | None
    feedback_timeline_path: Path | None
    attributed_transcript_path: Path | None
    speaker_attribution_report_path: Path | None
    speaker_attribution_task_path: Path | None
    deck_revision_intake_path: Path | None
    deck_revision_gate_path: Path | None
    material_id: str
    judgement_count: int
    open_question_count: int
    clara_mandate_updated: bool


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _compact_timestamp(timestamp: str) -> str:
    compact = re.sub(r"[^0-9]", "", timestamp)
    if len(compact) >= 14:
        return compact[:14] + "Z"
    return re.sub(r"[^0-9]", "", _now_iso())[:14] + "Z"


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    clean = text.strip()
    if not clean:
        return None
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, re.DOTALL)
    if fence_match:
        clean = fence_match.group(1)
    try:
        payload = json.loads(clean)
    except json.JSONDecodeError:
        object_match = re.search(r"\{.*\}", clean, re.DOTALL)
        if object_match is None:
            return None
        try:
            payload = json.loads(object_match.group(0))
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _hosted_voice_json_from_zip(bundle_path: Path) -> dict[str, Any]:
    try:
        with ZipFile(bundle_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                member_name = Path(member.filename).name
                if not member_name.startswith(
                    ("case-notes-voice-", "case-notes-audio-")
                ):
                    continue
                if Path(member_name).suffix.lower() != ".json":
                    continue
                try:
                    payload = json.loads(archive.read(member).decode("utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if (
                    isinstance(payload, dict)
                    and payload.get("source") == "case_notes_hosted_voice"
                ):
                    return payload
    except BadZipFile as error:
        raise CaseWorkspaceError(
            "hosted voice ZIP bundle is not a valid zip file"
        ) from error
    raise CaseWorkspaceError(
        "hosted voice ZIP bundle does not contain a valid case-notes JSON file"
    )


def read_hosted_voice_bundle_payload(bundle_path: Path) -> dict[str, Any]:
    """Read a hosted voice bundle from a JSON file or browser ZIP export."""

    if bundle_path.suffix.lower() == ".zip":
        return _hosted_voice_json_from_zip(bundle_path)
    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CaseWorkspaceError("hosted voice bundle JSON is not readable") from error
    if not isinstance(payload, dict):
        raise CaseWorkspaceError("hosted voice bundle must be a JSON object")
    return payload


def _bundle_extraction(bundle: Mapping[str, Any]) -> Mapping[str, Any]:
    extraction_json = bundle.get("extraction_json")
    if isinstance(extraction_json, Mapping):
        return extraction_json
    parsed = _extract_json_payload(str(bundle.get("extraction_text", "")))
    return parsed or {}


def _pending_entries(
    extraction: Mapping[str, Any],
    *,
    material_id: str,
) -> list[dict[str, Any]]:
    raw_entries = extraction.get("entries", [])
    if not isinstance(raw_entries, list):
        return []
    entries: list[dict[str, Any]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            continue
        kind = str(raw_entry.get("kind", "")).strip()
        text = str(raw_entry.get("text", "")).strip()
        if kind not in JUDGEMENT_KINDS or not text:
            continue
        entries.append(
            {
                "kind": kind,
                "text": text,
                "status": "pending",
                "source_material_ids": [material_id],
                "rationale": str(raw_entry.get("rationale", "")).strip(),
            }
        )
    return entries


def _open_questions(extraction: Mapping[str, Any]) -> list[dict[str, str]]:
    raw_questions = extraction.get("open_questions", [])
    if not isinstance(raw_questions, list):
        return []
    questions: list[dict[str, str]] = []
    for raw_question in raw_questions:
        if isinstance(raw_question, Mapping):
            question = str(raw_question.get("question", "")).strip()
            why_it_matters = str(raw_question.get("why_it_matters", "")).strip()
        else:
            question = str(raw_question).strip()
            why_it_matters = ""
        if question:
            questions.append({"question": question, "why_it_matters": why_it_matters})
    return questions


def _source_metadata(bundle: Mapping[str, Any]) -> dict[str, str]:
    raw_metadata = bundle.get("source_metadata")
    if not isinstance(raw_metadata, Mapping):
        return {}
    allowed_keys = {
        "source_type",
        "recording_type",
        "title",
        "interview_date",
        "participants",
        "interviewer",
        "notes",
    }
    metadata: dict[str, str] = {}
    for key, value in raw_metadata.items():
        clean_key = str(key).strip()
        if clean_key not in allowed_keys:
            continue
        clean_value = str(value).strip()
        if clean_key and clean_value:
            metadata[clean_key] = clean_value
    return metadata


def _call_metadata(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return machine-captured bundle metadata relevant to local attribution."""

    metadata: dict[str, Any] = {}
    for key in (
        "capture_source",
        "captured_at",
        "capture_started_at",
        "capture_stopped_at",
        "capture_elapsed_seconds",
        "language",
        "model",
        "transcription_model",
        "audio_file_name",
        "video_file_name",
        "speaker_label_note",
    ):
        value = bundle.get(key)
        if isinstance(value, str):
            clean = value.strip()
            if clean:
                metadata[key] = clean
        elif value is not None:
            metadata[key] = value
    screen_metadata = bundle.get("screen_capture_metadata")
    if isinstance(screen_metadata, Mapping):
        compact_screen_metadata = {}
        for key in (
            "display_surface",
            "width",
            "height",
            "started_at",
            "stopped_at",
            "capture_reason",
        ):
            value = screen_metadata.get(key)
            if value not in (None, ""):
                compact_screen_metadata[key] = value
        audio_sources = screen_metadata.get("audio_sources")
        if isinstance(audio_sources, Mapping):
            compact_screen_metadata["audio_sources"] = dict(audio_sources)
        if compact_screen_metadata:
            metadata["screen_capture_metadata"] = compact_screen_metadata
    return metadata


def _source_metadata_lines(metadata: Mapping[str, str]) -> list[str]:
    labels = {
        "source_type": "Source type",
        "title": "Source title",
        "interview_date": "Interview date",
        "participants": "Interviewee / participants",
        "interviewer": "Interviewer",
        "notes": "Source notes",
    }
    lines: list[str] = []
    for key, label in labels.items():
        value = str(metadata.get(key, "")).strip()
        if value:
            lines.append(f"{label}: {value}")
    return lines


def _source_metadata_markdown(metadata: Mapping[str, str]) -> str:
    lines = _source_metadata_lines(metadata)
    if not lines:
        return "- No source metadata supplied."
    formatted_lines = []
    for line in lines:
        label, value = line.split(":", 1)
        formatted_lines.append(f"- **{label}:** {value.strip()}")
    return "\n".join(formatted_lines)


def _copy_companion_audio_file(
    bundle_path: Path,
    session_dir: Path,
    bundle: Mapping[str, Any],
    *,
    companion_audio_path: Path | None = None,
) -> Path | None:
    """Copy a downloaded or zipped audio file into the voice session folder."""

    audio_file_name = Path(str(bundle.get("audio_file_name", "")).strip()).name
    if not audio_file_name:
        return None
    if companion_audio_path is not None:
        source_audio_path = companion_audio_path.expanduser()
        if not source_audio_path.is_file():
            raise CaseWorkspaceError(
                f"companion audio file does not exist: {source_audio_path}"
            )
        destination = session_dir / audio_file_name
        if source_audio_path.resolve() != destination.resolve():
            shutil.copy2(source_audio_path, destination)
        return destination
    if bundle_path.suffix.lower() == ".zip":
        return _copy_companion_audio_from_zip(
            bundle_zip_path=bundle_path,
            session_dir=session_dir,
            audio_file_name=audio_file_name,
        )
    source_audio_path = bundle_path.parent / audio_file_name
    if not source_audio_path.is_file():
        return None
    destination = session_dir / audio_file_name
    if source_audio_path.resolve() != destination.resolve():
        shutil.copy2(source_audio_path, destination)
    return destination


def _copy_companion_audio_from_zip(
    *,
    bundle_zip_path: Path,
    session_dir: Path,
    audio_file_name: str,
) -> Path | None:
    try:
        with ZipFile(bundle_zip_path) as archive:
            for member in archive.infolist():
                if member.is_dir() or Path(member.filename).name != audio_file_name:
                    continue
                destination = session_dir / audio_file_name
                with archive.open(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                return destination
    except BadZipFile as error:
        raise CaseWorkspaceError(
            "hosted voice ZIP bundle is not a valid zip file"
        ) from error
    return None


def _copy_companion_video_file(
    bundle_path: Path,
    session_dir: Path,
    bundle: Mapping[str, Any],
) -> Path | None:
    """Copy a downloaded or zipped screen video file into the session folder."""

    video_file_name = Path(str(bundle.get("video_file_name", "")).strip()).name
    if not video_file_name:
        return None
    if bundle_path.suffix.lower() == ".zip":
        return _copy_companion_video_from_zip(
            bundle_zip_path=bundle_path,
            session_dir=session_dir,
            video_file_name=video_file_name,
        )
    source_video_path = bundle_path.parent / video_file_name
    if not source_video_path.is_file():
        return None
    destination = session_dir / video_file_name
    if source_video_path.resolve() != destination.resolve():
        shutil.copy2(source_video_path, destination)
    return destination


def _copy_companion_video_from_zip(
    *,
    bundle_zip_path: Path,
    session_dir: Path,
    video_file_name: str,
) -> Path | None:
    try:
        with ZipFile(bundle_zip_path) as archive:
            for member in archive.infolist():
                if member.is_dir() or Path(member.filename).name != video_file_name:
                    continue
                destination = session_dir / video_file_name
                with archive.open(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                return destination
    except BadZipFile as error:
        raise CaseWorkspaceError(
            "hosted voice ZIP bundle is not a valid zip file"
        ) from error
    return None


def _update_material_source_metadata(
    case_dir: Path,
    material_id: str,
    metadata: Mapping[str, Any],
) -> None:
    if not metadata:
        return
    registry_path = case_dir / "material_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for material in registry.get("materials", []):
        if material.get("id") == material_id:
            existing = material.get("source_metadata")
            if existing is not None and not isinstance(existing, dict):
                raise CaseWorkspaceError("source_metadata must be an object")
            material["source_metadata"] = {
                **dict(existing or {}),
                **dict(metadata),
            }
            break
    registry_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _transcript_markdown(bundle: Mapping[str, Any]) -> str:
    timestamp = str(bundle.get("captured_at", "")).strip() or _now_iso()
    capture_source = str(bundle.get("capture_source", "")).strip()
    audio_file_name = str(bundle.get("audio_file_name", "")).strip()
    video_file_name = str(bundle.get("video_file_name", "")).strip()
    screen_capture_metadata = bundle.get("screen_capture_metadata")
    metadata = _source_metadata(bundle)
    final_transcript = str(bundle.get("user_transcript", "")).strip()
    prompted_transcript = (
        str(bundle.get("transcript_text_prompted", "")).strip()
        or str(bundle.get("raw_transcription_text", "")).strip()
        or final_transcript
    )
    source_lines = []
    if capture_source:
        source_lines.append(f"Capture source: {capture_source}")
    if audio_file_name:
        source_lines.append(f"Audio file: {audio_file_name}")
    if video_file_name:
        source_lines.append(f"Screen video: {video_file_name}")
    if isinstance(screen_capture_metadata, Mapping):
        display_surface = str(
            screen_capture_metadata.get("display_surface", "")
        ).strip()
        width = screen_capture_metadata.get("width")
        height = screen_capture_metadata.get("height")
        if display_surface:
            source_lines.append(f"Screen capture display surface: {display_surface}")
        if width and height:
            source_lines.append(f"Screen capture resolution: {width}x{height}")
    source_lines.extend(_source_metadata_lines(metadata))
    lines = [
        "# Hosted Voice Transcript",
        "",
        f"Captured: {timestamp}",
        f"Model: {bundle.get('model', '')}",
        *source_lines,
        "",
        "## Consultant",
        "",
        final_transcript or "No consultant transcript captured.",
        "",
    ]
    if prompted_transcript and prompted_transcript != final_transcript:
        lines.extend(
            [
                "## Prompted Reference Transcript",
                "",
                prompted_transcript,
                "",
            ]
        )
    lines.extend(
        [
            "## Voice Model",
            "",
            str(bundle.get("assistant_transcript", "")).strip()
            or "No model transcript captured.",
            "",
        ]
    )
    return "\n".join(lines)


def _paragraphize_transcript_markdown(transcript: str) -> str:
    """Format transcript text mechanically; semantic review remains model-led."""

    clean = " ".join(transcript.split())
    if not clean:
        return "No transcript available."
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    paragraphs: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        if not sentence:
            continue
        current.append(sentence)
        if len(current) >= 4:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def _open_questions_markdown(extraction: Mapping[str, Any]) -> str:
    questions = _open_questions(extraction)
    if not questions:
        return "- No follow-up questions were generated."
    lines: list[str] = []
    for item in questions:
        why = (
            f" Why it matters: {item['why_it_matters']}"
            if item["why_it_matters"]
            else ""
        )
        lines.append(f"- {item['question']}{why}")
    return "\n".join(lines)


def _clara_review_markdown(
    bundle: Mapping[str, Any],
    extraction: Mapping[str, Any],
) -> str:
    """Build the local review workspace from the downloaded transcript.

    The importer is deterministic: it formats the source transcript and creates
    review sections, but local Codex/Clara must fill the semantic judgement.
    """

    _ = extraction
    final_transcript = str(bundle.get("user_transcript", "")).strip()
    prompted_transcript = (
        str(bundle.get("transcript_text_prompted", "")).strip()
        or str(bundle.get("raw_transcription_text", "")).strip()
        or final_transcript
    )
    transcript_processing_note = (
        str(bundle.get("transcript_processing_note", "")).strip()
        or DEFAULT_TRANSCRIPT_PROCESSING_NOTE
    )
    cleaned_transcript = _paragraphize_transcript_markdown(
        final_transcript or prompted_transcript,
    )
    audio_file_name = str(bundle.get("audio_file_name", "")).strip()
    video_file_name = str(bundle.get("video_file_name", "")).strip()
    lines = [
        "# Clara Audio Review",
        "",
        "Generated locally by the Clara plugin from the downloaded transcript bundle. "
        "The hosted server supplied the transcript; local Codex/Clara should fill the "
        "semantic review sections below.",
        "",
        "## Source",
        "",
        f"- **Captured:** {str(bundle.get('captured_at', '')).strip() or 'not available'}",
        f"- **Audio file:** {audio_file_name or 'not available'}",
        f"- **Screen video:** {video_file_name or 'not available'}",
        _source_metadata_markdown(_source_metadata(bundle)),
        "",
        "## Required Transcript Processing",
        "",
        transcript_processing_note,
        "",
        "## Neutral Summary",
        "",
        "Pending local Clara review.",
        "",
        "## Thesis And Claims",
        "",
        "Pending local Clara review.",
        "",
        "## Well-Supported Points",
        "",
        "Pending local Clara review.",
        "",
        "## Vulnerabilities And Weak Assumptions",
        "",
        "Pending local Clara review.",
        "",
        "## Clara Opinion",
        "",
        "Pending local Clara review.",
        "",
        "## Follow-Up Questions",
        "",
        "Pending local Clara review.",
        "",
    ]
    if prompted_transcript and prompted_transcript != final_transcript:
        lines.extend(
            [
                "## Prompted Reference Transcript",
                "",
                prompted_transcript,
                "",
            ]
        )
    lines.extend(
        [
            "## Cleaned Transcript",
            "",
            cleaned_transcript,
            "",
        ]
    )
    return "\n".join(lines)


def _read_text_or_empty(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _discussion_review_pack_markdown(
    *,
    case_dir: Path,
    session_dir: Path,
    material_id: str,
    raw_transcript_path: Path,
    audio_path: Path | None,
    video_path: Path | None,
    video_timeline_path: Path | None,
    feedback_timeline_path: Path | None,
    attributed_transcript_path: Path | None,
    speaker_attribution_report_path: Path | None,
    speaker_attribution_task_path: Path | None,
    deck_revision_intake_path: Path | None,
    deck_revision_gate_path: Path | None,
    cleaned_notes_path: Path,
    clara_review_path: Path,
    judgement_candidates_path: Path,
) -> str:
    """Build a local Codex review pack for the imported voice discussion."""

    brief_text = _read_text_or_empty(case_dir / CASE_BRIEF_FILENAME)
    raw_transcript = _read_text_or_empty(raw_transcript_path)
    cleaned_notes = _read_text_or_empty(cleaned_notes_path)
    judgement_candidates = _read_text_or_empty(judgement_candidates_path)
    open_questions = _read_text_or_empty(case_dir / "open_questions.json")
    judgement_log = _read_text_or_empty(case_dir / "judgement_log.json")
    relative_session = session_dir.relative_to(case_dir)
    audio_line = (
        f"- Audio file: `{audio_path.relative_to(case_dir)}`"
        if audio_path is not None
        else "- Audio file: not imported"
    )
    video_line = (
        f"- Screen video: `{video_path.relative_to(case_dir)}`"
        if video_path is not None
        else "- Screen video: not imported"
    )
    timeline_line = (
        f"- Video timeline: `{video_timeline_path.relative_to(case_dir)}`"
        if video_timeline_path is not None
        else "- Video timeline: not available"
    )
    feedback_timeline_line = (
        f"- Feedback timeline: `{feedback_timeline_path.relative_to(case_dir)}`"
        if feedback_timeline_path is not None
        else "- Feedback timeline: not available"
    )
    attributed_transcript_line = (
        f"- Attributed transcript: `{attributed_transcript_path.relative_to(case_dir)}`"
        if attributed_transcript_path is not None
        else "- Attributed transcript: not automatically available"
    )
    attribution_report_line = (
        f"- Speaker attribution report: `{speaker_attribution_report_path.relative_to(case_dir)}`"
        if speaker_attribution_report_path is not None
        else "- Speaker attribution report: not available"
    )
    attribution_task_line = (
        f"- Speaker attribution task: `{speaker_attribution_task_path.relative_to(case_dir)}`"
        if speaker_attribution_task_path is not None
        else "- Speaker attribution task: not required"
    )
    deck_revision_intake_line = (
        f"- Deck revision intake: `{deck_revision_intake_path.relative_to(case_dir)}`"
        if deck_revision_intake_path is not None
        else "- Deck revision intake: not prepared"
    )
    deck_revision_gate_line = (
        f"- Deck revision gate: `{deck_revision_gate_path.relative_to(case_dir)}`"
        if deck_revision_gate_path is not None
        else "- Deck revision gate: not prepared"
    )
    return "\n".join(
        [
            "# Local Codex Discussion Review Pack",
            "",
            "Use this file with local Codex after the voice bundle has been imported.",
            "Do not send this pack back to the hosted voice server. The server handled hosted audio processing only.",
            "",
            "## Review Task",
            "",
            "Review the full discussion as a second-pass advisory reviewer.",
            "Focus on what the consultant actually said, what the live voice model missed, and what should become local Clara material.",
            "",
            "Return a concise review with these sections:",
            "",
            "1. Discussion readout - what the consultant's actual view appears to be.",
            "2. Strong signals - concrete statements or documents supporting that readout.",
            "3. Weak assumptions or contradictions - including any answer the voice model failed to follow.",
            "4. Missing questions - the next practical questions the consultant should answer.",
            "5. Proposed Clara entries - JSON only, with entries kept `pending` and sourced to the transcript material below.",
            "",
            "Rules:",
            "",
            "- First assign speakers locally from transcript text and source metadata where the bundle did not provide reliable names; do not use an audio or voice diarization model for Clara speaker attribution.",
            "- Preserve the unattributed transcript, create or update a speaker-attributed working transcript, inspect for obvious merged turns or wrong labels, and correct only clear text-supported boundary errors.",
            "- Check transcript quality and correct only obvious transcription errors supported by context or trusted glossary.",
            "- Do not mark anything decision-pack ready.",
            "- Do not invent facts not present in the case brief or transcript.",
            "- Separate consultant judgement from Codex inference.",
            "- When screen video or a video timeline is available, use it as provenance for visual references only after checking the visible content; do not infer the target slide from transcript text alone.",
            "- When a feedback timeline is available, use row-level `visual_evidence_status`, `use_as_visual_evidence`, `alignment_confidence_label`, and `frame_extraction_status` before relying on it.",
            "- Treat feedback timeline rows as visual evidence only when `use_as_visual_evidence` is true and an extracted frame path is present. Treat `timing_only`, `weak_alignment`, missing frame paths, or failed frame extraction as navigation hints for inspecting the raw video/deck, not as evidence.",
            "- If the live voice model asked generic or unhelpful questions, say that plainly and recover the useful substance from the consultant's answers.",
            f"- Source proposed entries to material id `{material_id}`.",
            "",
            "## Local Session",
            "",
            f"- Session folder: `{relative_session}`",
            f"- Transcript material id: `{material_id}`",
            f"- Raw transcript: `{raw_transcript_path.relative_to(case_dir)}`",
            attributed_transcript_line,
            attribution_report_line,
            attribution_task_line,
            audio_line,
            video_line,
            timeline_line,
            feedback_timeline_line,
            deck_revision_intake_line,
            deck_revision_gate_line,
            f"- Cleaned notes: `{cleaned_notes_path.relative_to(case_dir)}`",
            f"- Clara review: `{clara_review_path.relative_to(case_dir)}`",
            f"- Imported candidates: `{judgement_candidates_path.relative_to(case_dir)}`",
            "",
            "## Current Case Brief",
            "",
            brief_text or "No case brief available.",
            "",
            "## Imported Voice Transcript",
            "",
            raw_transcript or "No transcript available.",
            "",
            "## Initial Extracted Notes",
            "",
            cleaned_notes or "No cleaned notes available.",
            "",
            "## Initial Imported Candidates",
            "",
            "```json",
            judgement_candidates or '{"entries": []}',
            "```",
            "",
            "## Current Judgement Log",
            "",
            "```json",
            judgement_log or '{"entries": []}',
            "```",
            "",
            "## Current Open Questions",
            "",
            "```json",
            open_questions or '{"questions": []}',
            "```",
            "",
        ]
    )


def _write_initial_video_timeline(
    *,
    path: Path,
    case_dir: Path,
    raw_transcript_path: Path,
    video_path: Path,
    bundle: Mapping[str, Any],
) -> None:
    payload = {
        "schema_version": 1,
        "created_at": _now_iso(),
        "source": "case_notes_hosted_voice",
        "transcript_path": str(raw_transcript_path.relative_to(case_dir)),
        "video_path": str(video_path.relative_to(case_dir)),
        "screen_capture_metadata": bundle.get("screen_capture_metadata", {}),
        "active_slide_capture": bundle.get("active_slide_capture", {}),
        "active_slide_timeline": bundle.get("active_slide_timeline", []),
        "entries": [],
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _build_import_feedback_timeline(
    *,
    case_dir: Path,
    session_dir: Path,
    raw_transcript_path: Path,
    video_path: Path | None,
    bundle: Mapping[str, Any],
) -> Path | None:
    if video_path is None:
        return None
    raw_segments = bundle.get("timed_transcript_segments", [])
    if not isinstance(raw_segments, list) or not raw_segments:
        return None
    clean_transcript = str(bundle.get("user_transcript", "")).strip()
    if not clean_transcript:
        return None
    output_path = session_dir / "feedback_timeline.json"
    try:
        build_feedback_timeline(
            clean_transcript=clean_transcript,
            timed_transcript_segments=raw_segments,
            video_path=video_path,
            transcript_path=raw_transcript_path,
            output_path=output_path,
            base_dir=case_dir,
            extract_frames=True,
        )
    except (FeedbackTimelineError, OSError) as error:
        LOGGER.warning("Could not build feedback timeline: %s", error)
        return None
    return output_path


def import_hosted_voice_bundle(
    case_dir: Path,
    bundle_path: Path,
    *,
    title: str = "Hosted voice session",
    companion_audio_path: Path | None = None,
) -> HostedVoiceImportResult:
    """Import one downloaded hosted voice bundle into *case_dir*."""

    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))
    bundle = read_hosted_voice_bundle_payload(bundle_path)
    if bundle.get("source") != "case_notes_hosted_voice":
        raise CaseWorkspaceError("hosted voice bundle has unsupported source")

    timestamp = str(bundle.get("captured_at", "")).strip() or _now_iso()
    session_dir = case_dir / "voice_sessions" / _compact_timestamp(timestamp)
    session_dir.mkdir(parents=True, exist_ok=True)

    extraction = _bundle_extraction(bundle)
    cleaned_notes = str(extraction.get("cleaned_notes_markdown", "")).strip()
    if not cleaned_notes:
        cleaned_notes = str(bundle.get("extraction_text", "")).strip()
    if not cleaned_notes:
        cleaned_notes = "No cleaned notes extracted."

    raw_transcript_path = session_dir / "raw_transcript.md"
    cleaned_notes_path = session_dir / "cleaned_notes.md"
    clara_review_path = session_dir / "clara_review.md"
    judgement_candidates_path = session_dir / "judgement_candidates.json"
    discussion_review_pack_path = session_dir / "codex_discussion_review.md"
    deck_revision_intake_path: Path | None = None
    deck_revision_gate_path: Path | None = None
    attribution_result: AutoTranscriptAttributionResult | None = None
    audio_path = _copy_companion_audio_file(
        bundle_path,
        session_dir,
        bundle,
        companion_audio_path=companion_audio_path,
    )
    video_path = _copy_companion_video_file(bundle_path, session_dir, bundle)
    video_timeline_path = (
        session_dir / "video_timeline.json" if video_path is not None else None
    )
    raw_transcript_path.write_text(_transcript_markdown(bundle), encoding="utf-8")
    cleaned_notes_path.write_text(cleaned_notes + "\n", encoding="utf-8")
    clara_review_path.write_text(
        _clara_review_markdown(bundle, extraction),
        encoding="utf-8",
    )
    feedback_timeline_path = _build_import_feedback_timeline(
        case_dir=case_dir,
        session_dir=session_dir,
        raw_transcript_path=raw_transcript_path,
        video_path=video_path,
        bundle=bundle,
    )

    material = register_material(
        case_dir,
        raw_transcript_path,
        material_type="transcript",
        title=str(_source_metadata(bundle).get("title", "")).strip() or title,
        summary="Hosted voice transcript imported from local bundle.",
    )
    source_metadata = _source_metadata(bundle)
    if audio_path is not None:
        source_metadata["audio_file"] = str(audio_path.relative_to(case_dir))
    if video_path is not None:
        source_metadata["screen_video"] = str(video_path.relative_to(case_dir))
    if video_timeline_path is not None:
        source_metadata["screen_video_timeline"] = str(
            video_timeline_path.relative_to(case_dir)
        )
    if feedback_timeline_path is not None:
        source_metadata["feedback_timeline"] = str(
            feedback_timeline_path.relative_to(case_dir)
        )
    _update_material_source_metadata(case_dir, material["id"], source_metadata)
    attribution_result = auto_attribute_hosted_transcript(
        case_dir,
        str(material["id"]),
        raw_transcript_path,
        source_metadata=source_metadata,
        call_metadata=_call_metadata(bundle),
    )
    source_metadata["speaker_attribution_report"] = str(
        attribution_result.report_path.relative_to(case_dir)
    )
    if attribution_result.attributed_transcript_path is not None:
        source_metadata["attributed_transcript"] = str(
            attribution_result.attributed_transcript_path.relative_to(case_dir)
        )
    if attribution_result.attribution_task_path is not None:
        source_metadata["speaker_attribution_task"] = str(
            attribution_result.attribution_task_path.relative_to(case_dir)
        )
    _update_material_source_metadata(case_dir, material["id"], source_metadata)
    pending_entries = _pending_entries(extraction, material_id=material["id"])
    added_entries = add_judgement_entries(case_dir, pending_entries)
    judgement_candidates_path.write_text(
        json.dumps({"entries": pending_entries}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    questions = _open_questions(extraction)
    for item in questions:
        add_open_question(
            case_dir,
            question=item["question"],
            why_it_matters=item["why_it_matters"],
        )

    clara_mandate_updated = False

    if video_timeline_path is not None and video_path is not None:
        _write_initial_video_timeline(
            path=video_timeline_path,
            case_dir=case_dir,
            raw_transcript_path=raw_transcript_path,
            video_path=video_path,
            bundle=bundle,
        )
        deck_revision_result = prepare_voice_deck_revision_intake(
            case_dir,
            voice_session=session_dir,
            transcript_material_id=str(material["id"]),
        )
        deck_revision_intake_path = deck_revision_result.intake_path
        deck_revision_gate_path = deck_revision_result.gate_path
        source_metadata["deck_revision_intake"] = str(
            deck_revision_intake_path.relative_to(case_dir)
        )
        source_metadata["deck_revision_gate"] = str(
            deck_revision_gate_path.relative_to(case_dir)
        )
        _update_material_source_metadata(case_dir, material["id"], source_metadata)

    refresh_case_brief(case_dir)
    discussion_review_pack_path.write_text(
        _discussion_review_pack_markdown(
            case_dir=case_dir,
            session_dir=session_dir,
            material_id=material["id"],
            raw_transcript_path=raw_transcript_path,
            audio_path=audio_path,
            video_path=video_path,
            video_timeline_path=video_timeline_path,
            feedback_timeline_path=feedback_timeline_path,
            attributed_transcript_path=(
                attribution_result.attributed_transcript_path
                if attribution_result is not None
                else None
            ),
            speaker_attribution_report_path=(
                attribution_result.report_path
                if attribution_result is not None
                else None
            ),
            speaker_attribution_task_path=(
                attribution_result.attribution_task_path
                if attribution_result is not None
                else None
            ),
            deck_revision_intake_path=deck_revision_intake_path,
            deck_revision_gate_path=deck_revision_gate_path,
            cleaned_notes_path=cleaned_notes_path,
            clara_review_path=clara_review_path,
            judgement_candidates_path=judgement_candidates_path,
        ),
        encoding="utf-8",
    )

    return HostedVoiceImportResult(
        session_dir=session_dir,
        raw_transcript_path=raw_transcript_path,
        cleaned_notes_path=cleaned_notes_path,
        clara_review_path=clara_review_path,
        judgement_candidates_path=judgement_candidates_path,
        discussion_review_pack_path=discussion_review_pack_path,
        audio_path=audio_path,
        video_path=video_path,
        video_timeline_path=video_timeline_path,
        feedback_timeline_path=feedback_timeline_path,
        attributed_transcript_path=(
            attribution_result.attributed_transcript_path
            if attribution_result is not None
            else None
        ),
        speaker_attribution_report_path=(
            attribution_result.report_path if attribution_result is not None else None
        ),
        speaker_attribution_task_path=(
            attribution_result.attribution_task_path
            if attribution_result is not None
            else None
        ),
        deck_revision_intake_path=deck_revision_intake_path,
        deck_revision_gate_path=deck_revision_gate_path,
        material_id=material["id"],
        judgement_count=len(added_entries),
        open_question_count=len(questions),
        clara_mandate_updated=clara_mandate_updated,
    )


def main() -> int:
    """Run hosted voice bundle import."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--title", default="Hosted voice session")
    parser.add_argument(
        "--companion-audio",
        type=Path,
        help="Local audio file to copy into the imported voice session.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = import_hosted_voice_bundle(
        args.case_dir,
        args.bundle,
        title=args.title,
        companion_audio_path=args.companion_audio,
    )
    LOGGER.info("Transcript material: %s", result.material_id)
    LOGGER.info("Pending judgement entries added: %s", result.judgement_count)
    LOGGER.info("Open questions added: %s", result.open_question_count)
    LOGGER.info("Clara review: %s", result.clara_review_path)
    if result.audio_path is not None:
        LOGGER.info("Audio file: %s", result.audio_path)
    if result.video_path is not None:
        LOGGER.info("Screen video: %s", result.video_path)
    if result.video_timeline_path is not None:
        LOGGER.info("Video timeline: %s", result.video_timeline_path)
    if result.feedback_timeline_path is not None:
        LOGGER.info("Feedback timeline: %s", result.feedback_timeline_path)
    if result.attributed_transcript_path is not None:
        LOGGER.info("Attributed transcript: %s", result.attributed_transcript_path)
    if result.speaker_attribution_task_path is not None:
        LOGGER.info(
            "Speaker attribution task for Codex/Clara: %s",
            result.speaker_attribution_task_path,
        )
    if result.speaker_attribution_report_path is not None:
        LOGGER.info(
            "Speaker attribution report: %s",
            result.speaker_attribution_report_path,
        )
    LOGGER.info("Local Codex review pack: %s", result.discussion_review_pack_path)
    LOGGER.info("Session folder: %s", result.session_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
