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
SPANISH_TRANSCRIPT_PROCESSING_NOTE = (
    "Tras la transcripción, Clara/Codex local debe atribuir los hablantes a partir "
    "de la transcripción depurada y los metadatos de la fuente, comprobar la calidad "
    "de la transcripción en el contexto del documento completo y corregir únicamente "
    "las palabras claramente mal transcritas cuando la formulación correcta resulte "
    "evidente por el contexto o por un glosario fiable del caso. La atribución de "
    "hablantes es un proceso local de texto de Codex/Clara: conserva la transcripción "
    "sin atribuir, crea una versión de trabajo con hablantes, revisa posibles turnos "
    "fusionados o etiquetas incorrectas y corrige solo los límites respaldados con "
    "claridad por el texto. No utilices un modelo de diarización de audio o voz para "
    "atribuir hablantes en Clara. Mantén visible la incertidumbre en lugar de adivinar."
)


def _normalise_language(value: Any) -> str:
    clean = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "spa": "es",
        "spanish": "es",
        "español": "es",
        "eng": "en",
        "english": "en",
        "ita": "it",
        "italian": "it",
        "fra": "fr",
        "fre": "fr",
        "french": "fr",
        "deu": "de",
        "ger": "de",
        "german": "de",
    }
    base = clean.split("-", 1)[0]
    return aliases.get(clean, aliases.get(base, base))


def _artifact_language(
    bundle: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> str:
    candidates = (
        bundle.get("language"),
        bundle.get("output_language"),
        manifest.get("output_language"),
    )
    normalized = [_normalise_language(value) for value in candidates]
    if "es" in normalized:
        return "es"
    return next((value for value in normalized if value), "en")


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


def _source_metadata_lines(
    metadata: Mapping[str, str],
    *,
    language: str = "en",
) -> list[str]:
    labels = (
        {
            "source_type": "Tipo de fuente",
            "title": "Título de la fuente",
            "interview_date": "Fecha de la entrevista",
            "participants": "Persona entrevistada / participantes",
            "interviewer": "Entrevistador",
            "notes": "Notas sobre la fuente",
        }
        if language == "es"
        else {
            "source_type": "Source type",
            "title": "Source title",
            "interview_date": "Interview date",
            "participants": "Interviewee / participants",
            "interviewer": "Interviewer",
            "notes": "Source notes",
        }
    )
    lines: list[str] = []
    for key, label in labels.items():
        value = str(metadata.get(key, "")).strip()
        if value:
            lines.append(f"{label}: {value}")
    return lines


def _source_metadata_markdown(
    metadata: Mapping[str, str],
    *,
    language: str = "en",
) -> str:
    lines = _source_metadata_lines(metadata, language=language)
    if not lines:
        return (
            "- No se han facilitado metadatos de la fuente."
            if language == "es"
            else "- No source metadata supplied."
        )
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


def _transcript_markdown(
    bundle: Mapping[str, Any],
    *,
    language: str = "en",
) -> str:
    if language == "es":
        copy = {
            "title": "Transcripción de Hosted Voice",
            "captured": "Capturada",
            "model": "Modelo",
            "capture_source": "Fuente de captura",
            "audio_file": "Archivo de audio",
            "screen_video": "Vídeo de pantalla",
            "display_surface": "Superficie capturada en pantalla",
            "resolution": "Resolución de la captura de pantalla",
            "consultant": "Consultor",
            "no_consultant": "No se capturó ninguna transcripción del consultor.",
            "prompted": "Transcripción de referencia con indicaciones",
            "voice_model": "Modelo de voz",
            "no_model": "No se capturó ninguna transcripción del modelo.",
        }
    else:
        copy = {
            "title": "Hosted Voice Transcript",
            "captured": "Captured",
            "model": "Model",
            "capture_source": "Capture source",
            "audio_file": "Audio file",
            "screen_video": "Screen video",
            "display_surface": "Screen capture display surface",
            "resolution": "Screen capture resolution",
            "consultant": "Consultant",
            "no_consultant": "No consultant transcript captured.",
            "prompted": "Prompted Reference Transcript",
            "voice_model": "Voice Model",
            "no_model": "No model transcript captured.",
        }
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
        source_lines.append(f"{copy['capture_source']}: {capture_source}")
    if audio_file_name:
        source_lines.append(f"{copy['audio_file']}: {audio_file_name}")
    if video_file_name:
        source_lines.append(f"{copy['screen_video']}: {video_file_name}")
    if isinstance(screen_capture_metadata, Mapping):
        display_surface = str(
            screen_capture_metadata.get("display_surface", "")
        ).strip()
        width = screen_capture_metadata.get("width")
        height = screen_capture_metadata.get("height")
        if display_surface:
            source_lines.append(f"{copy['display_surface']}: {display_surface}")
        if width and height:
            source_lines.append(f"{copy['resolution']}: {width}x{height}")
    source_lines.extend(_source_metadata_lines(metadata, language=language))
    lines = [
        f"# {copy['title']}",
        "",
        f"{copy['captured']}: {timestamp}",
        f"{copy['model']}: {bundle.get('model', '')}",
        *source_lines,
        "",
        f"## {copy['consultant']}",
        "",
        final_transcript or copy["no_consultant"],
        "",
    ]
    if prompted_transcript and prompted_transcript != final_transcript:
        lines.extend(
            [
                f"## {copy['prompted']}",
                "",
                prompted_transcript,
                "",
            ]
        )
    lines.extend(
        [
            f"## {copy['voice_model']}",
            "",
            str(bundle.get("assistant_transcript", "")).strip() or copy["no_model"],
            "",
        ]
    )
    return "\n".join(lines)


def _paragraphize_transcript_markdown(
    transcript: str,
    *,
    language: str = "en",
) -> str:
    """Format transcript text mechanically; semantic review remains model-led."""

    clean = " ".join(transcript.split())
    if not clean:
        return (
            "No hay ninguna transcripción disponible."
            if language == "es"
            else "No transcript available."
        )
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
    *,
    language: str = "en",
) -> str:
    """Build the locally stored review workspace from the downloaded transcript.

    The importer is deterministic: it formats the source transcript and creates
    review sections, but Codex/Clara must fill the semantic judgement.
    """

    _ = extraction
    final_transcript = str(bundle.get("user_transcript", "")).strip()
    prompted_transcript = (
        str(bundle.get("transcript_text_prompted", "")).strip()
        or str(bundle.get("raw_transcription_text", "")).strip()
        or final_transcript
    )
    supplied_processing_note = str(bundle.get("transcript_processing_note", "")).strip()
    if language == "es" and supplied_processing_note in {
        "",
        DEFAULT_TRANSCRIPT_PROCESSING_NOTE,
    }:
        transcript_processing_note = SPANISH_TRANSCRIPT_PROCESSING_NOTE
    else:
        transcript_processing_note = (
            supplied_processing_note or DEFAULT_TRANSCRIPT_PROCESSING_NOTE
        )
    cleaned_transcript = _paragraphize_transcript_markdown(
        final_transcript or prompted_transcript,
        language=language,
    )
    audio_file_name = str(bundle.get("audio_file_name", "")).strip()
    video_file_name = str(bundle.get("video_file_name", "")).strip()
    if language == "es":
        copy = {
            "title": "Revisión de audio de Clara",
            "intro": (
                "Generado localmente por el plugin de Clara a partir del paquete "
                "de transcripción descargado. El servidor alojado proporcionó la "
                "transcripción; Codex/Clara debe completar las secciones de revisión "
                "semántica siguientes mediante el plan de ChatGPT del usuario."
            ),
            "source": "Fuente",
            "captured": "Capturada",
            "audio_file": "Archivo de audio",
            "screen_video": "Vídeo de pantalla",
            "not_available": "no disponible",
            "processing": "Procesamiento obligatorio de la transcripción",
            "summary": "Resumen neutral",
            "claims": "Tesis y afirmaciones",
            "supported": "Puntos bien respaldados",
            "vulnerabilities": "Vulnerabilidades y supuestos débiles",
            "opinion": "Opinión de Clara",
            "questions": "Preguntas de seguimiento",
            "pending": "Pendiente de revisión local por Clara.",
            "prompted": "Transcripción de referencia con indicaciones",
            "cleaned": "Transcripción depurada",
        }
    else:
        copy = {
            "title": "Clara Audio Review",
            "intro": (
                "Generated locally by the Clara plugin from the downloaded "
                "transcript bundle. The hosted server supplied the transcript; "
                "Codex/Clara should fill the semantic review sections below through "
                "the user's existing ChatGPT plan."
            ),
            "source": "Source",
            "captured": "Captured",
            "audio_file": "Audio file",
            "screen_video": "Screen video",
            "not_available": "not available",
            "processing": "Required Transcript Processing",
            "summary": "Neutral Summary",
            "claims": "Thesis And Claims",
            "supported": "Well-Supported Points",
            "vulnerabilities": "Vulnerabilities And Weak Assumptions",
            "opinion": "Clara Opinion",
            "questions": "Follow-Up Questions",
            "pending": "Pending local Clara review.",
            "prompted": "Prompted Reference Transcript",
            "cleaned": "Cleaned Transcript",
        }
    lines = [
        f"# {copy['title']}",
        "",
        copy["intro"],
        "",
        f"## {copy['source']}",
        "",
        f"- **{copy['captured']}:** {str(bundle.get('captured_at', '')).strip() or copy['not_available']}",
        f"- **{copy['audio_file']}:** {audio_file_name or copy['not_available']}",
        f"- **{copy['screen_video']}:** {video_file_name or copy['not_available']}",
        _source_metadata_markdown(_source_metadata(bundle), language=language),
        "",
        f"## {copy['processing']}",
        "",
        transcript_processing_note,
        "",
        f"## {copy['summary']}",
        "",
        copy["pending"],
        "",
        f"## {copy['claims']}",
        "",
        copy["pending"],
        "",
        f"## {copy['supported']}",
        "",
        copy["pending"],
        "",
        f"## {copy['vulnerabilities']}",
        "",
        copy["pending"],
        "",
        f"## {copy['opinion']}",
        "",
        copy["pending"],
        "",
        f"## {copy['questions']}",
        "",
        copy["pending"],
        "",
    ]
    if prompted_transcript and prompted_transcript != final_transcript:
        lines.extend(
            [
                f"## {copy['prompted']}",
                "",
                prompted_transcript,
                "",
            ]
        )
    lines.extend(
        [
            f"## {copy['cleaned']}",
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
    language: str = "en",
) -> str:
    """Build a locally stored Codex review pack for the imported voice discussion."""

    brief_text = _read_text_or_empty(case_dir / CASE_BRIEF_FILENAME)
    raw_transcript = _read_text_or_empty(raw_transcript_path)
    cleaned_notes = _read_text_or_empty(cleaned_notes_path)
    judgement_candidates = _read_text_or_empty(judgement_candidates_path)
    open_questions = _read_text_or_empty(case_dir / "open_questions.json")
    judgement_log = _read_text_or_empty(case_dir / "judgement_log.json")
    relative_session = session_dir.relative_to(case_dir)
    spanish = language == "es"
    audio_line = (
        f"- {'Archivo de audio' if spanish else 'Audio file'}: `{audio_path.relative_to(case_dir)}`"
        if audio_path is not None
        else (
            "- Archivo de audio: no importado"
            if spanish
            else "- Audio file: not imported"
        )
    )
    video_line = (
        f"- {'Vídeo de pantalla' if spanish else 'Screen video'}: `{video_path.relative_to(case_dir)}`"
        if video_path is not None
        else (
            "- Vídeo de pantalla: no importado"
            if spanish
            else "- Screen video: not imported"
        )
    )
    timeline_line = (
        f"- {'Línea temporal del vídeo' if spanish else 'Video timeline'}: `{video_timeline_path.relative_to(case_dir)}`"
        if video_timeline_path is not None
        else (
            "- Línea temporal del vídeo: no disponible"
            if spanish
            else "- Video timeline: not available"
        )
    )
    feedback_timeline_line = (
        f"- {'Línea temporal de comentarios' if spanish else 'Feedback timeline'}: `{feedback_timeline_path.relative_to(case_dir)}`"
        if feedback_timeline_path is not None
        else (
            "- Línea temporal de comentarios: no disponible"
            if spanish
            else "- Feedback timeline: not available"
        )
    )
    attributed_transcript_line = (
        f"- {'Transcripción atribuida' if spanish else 'Attributed transcript'}: `{attributed_transcript_path.relative_to(case_dir)}`"
        if attributed_transcript_path is not None
        else (
            "- Transcripción atribuida: no disponible automáticamente"
            if spanish
            else "- Attributed transcript: not automatically available"
        )
    )
    attribution_report_line = (
        f"- {'Informe de atribución de hablantes' if spanish else 'Speaker attribution report'}: `{speaker_attribution_report_path.relative_to(case_dir)}`"
        if speaker_attribution_report_path is not None
        else (
            "- Informe de atribución de hablantes: no disponible"
            if spanish
            else "- Speaker attribution report: not available"
        )
    )
    attribution_task_line = (
        f"- {'Tarea de atribución de hablantes' if spanish else 'Speaker attribution task'}: `{speaker_attribution_task_path.relative_to(case_dir)}`"
        if speaker_attribution_task_path is not None
        else (
            "- Tarea de atribución de hablantes: no necesaria"
            if spanish
            else "- Speaker attribution task: not required"
        )
    )
    deck_revision_intake_line = (
        f"- {'Intake de revisión del deck' if spanish else 'Deck revision intake'}: `{deck_revision_intake_path.relative_to(case_dir)}`"
        if deck_revision_intake_path is not None
        else (
            "- Intake de revisión del deck: no preparado"
            if spanish
            else "- Deck revision intake: not prepared"
        )
    )
    deck_revision_gate_line = (
        f"- {'Control de revisión del deck' if spanish else 'Deck revision gate'}: `{deck_revision_gate_path.relative_to(case_dir)}`"
        if deck_revision_gate_path is not None
        else (
            "- Control de revisión del deck: no preparado"
            if spanish
            else "- Deck revision gate: not prepared"
        )
    )
    if spanish:
        return "\n".join(
            [
                "# Paquete de revisión de la conversación para Codex (archivo local)",
                "",
                "Utiliza este archivo almacenado localmente con Codex después de importar el paquete de voz.",
                "Su contenido puede entrar en el contexto del modelo mediante el plan de ChatGPT del usuario.",
                "No envíes este paquete de vuelta al servidor de voz alojado. El servidor se ocupó únicamente del procesamiento del audio alojado.",
                "",
                "## Tarea de revisión",
                "",
                "Revisa la conversación completa como un segundo revisor consultivo.",
                "Céntrate en lo que dijo realmente el consultor, lo que omitió el modelo de voz en directo y lo que debe convertirse en material local de Clara.",
                "",
                "Devuelve una revisión concisa con estas secciones:",
                "",
                "1. Lectura de la conversación: cuál parece ser la opinión real del consultor.",
                "2. Señales sólidas: afirmaciones o documentos concretos que respaldan esa lectura.",
                "3. Supuestos débiles o contradicciones: incluida cualquier respuesta cuyo hilo no siguió el modelo de voz.",
                "4. Preguntas pendientes: las próximas preguntas prácticas que debe responder el consultor.",
                "5. Elementos propuestos para Clara: solo JSON, manteniendo los elementos como `pending` y vinculados al material de transcripción indicado más abajo.",
                "",
                "Reglas:",
                "",
                "- Atribuye primero los hablantes localmente a partir del texto de la transcripción y los metadatos de la fuente cuando el paquete no proporcione nombres fiables; no utilices un modelo de diarización de audio o voz para atribuir hablantes en Clara.",
                "- Conserva la transcripción sin atribuir, crea o actualiza una versión de trabajo con hablantes, revisa posibles turnos fusionados o etiquetas incorrectas y corrige únicamente los límites respaldados con claridad por el texto.",
                "- Comprueba la calidad de la transcripción y corrige solo errores evidentes respaldados por el contexto o por un glosario fiable.",
                "- No marques ningún elemento como listo para el paquete de decisión.",
                "- No inventes hechos que no aparezcan en el resumen del caso o en la transcripción.",
                "- Separa el juicio consultivo de la inferencia de Codex.",
                "- Cuando exista vídeo de pantalla o una línea temporal del vídeo, utilízalos como procedencia de las referencias visuales solo después de comprobar el contenido visible; no infieras la diapositiva de destino únicamente a partir de la transcripción.",
                "- Cuando exista una línea temporal de comentarios, consulta `visual_evidence_status`, `use_as_visual_evidence`, `alignment_confidence_label` y `frame_extraction_status` en cada fila antes de utilizarla.",
                "- Trata las filas de la línea temporal como evidencia visual únicamente cuando `use_as_visual_evidence` sea verdadero y exista una ruta al fotograma extraído. Trata `timing_only`, `weak_alignment`, las rutas ausentes o los fallos de extracción como indicios de navegación para inspeccionar el vídeo o el deck originales, no como evidencia.",
                "- Si el modelo de voz en directo formuló preguntas genéricas o poco útiles, indícalo claramente y recupera el contenido útil de las respuestas del consultor.",
                f"- Vincula los elementos propuestos al id de material `{material_id}`.",
                "",
                "## Sesión local",
                "",
                f"- Carpeta de la sesión: `{relative_session}`",
                f"- Id del material de transcripción: `{material_id}`",
                f"- Transcripción original: `{raw_transcript_path.relative_to(case_dir)}`",
                attributed_transcript_line,
                attribution_report_line,
                attribution_task_line,
                audio_line,
                video_line,
                timeline_line,
                feedback_timeline_line,
                deck_revision_intake_line,
                deck_revision_gate_line,
                f"- Notas depuradas: `{cleaned_notes_path.relative_to(case_dir)}`",
                f"- Revisión de Clara: `{clara_review_path.relative_to(case_dir)}`",
                f"- Candidatos importados: `{judgement_candidates_path.relative_to(case_dir)}`",
                "",
                "## Resumen actual del caso",
                "",
                brief_text or "No hay ningún resumen del caso disponible.",
                "",
                "## Transcripción de voz importada",
                "",
                raw_transcript or "No hay ninguna transcripción disponible.",
                "",
                "## Notas iniciales extraídas",
                "",
                cleaned_notes or "No hay notas depuradas disponibles.",
                "",
                "## Candidatos iniciales importados",
                "",
                "```json",
                judgement_candidates or '{"entries": []}',
                "```",
                "",
                "## Registro actual de juicios",
                "",
                "```json",
                judgement_log or '{"entries": []}',
                "```",
                "",
                "## Preguntas abiertas actuales",
                "",
                "```json",
                open_questions or '{"questions": []}',
                "```",
                "",
            ]
        )
    return "\n".join(
        [
            "# Codex Discussion Review Pack (local file)",
            "",
            "Use this locally stored file with Codex after the voice bundle has been imported.",
            "Its contents may enter model context through the user's existing ChatGPT plan.",
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
    manifest = json.loads((case_dir / "case_manifest.json").read_text(encoding="utf-8"))
    language = _artifact_language(bundle, manifest)

    timestamp = str(bundle.get("captured_at", "")).strip() or _now_iso()
    session_dir = case_dir / "voice_sessions" / _compact_timestamp(timestamp)
    session_dir.mkdir(parents=True, exist_ok=True)

    extraction = _bundle_extraction(bundle)
    cleaned_notes = str(extraction.get("cleaned_notes_markdown", "")).strip()
    if not cleaned_notes:
        cleaned_notes = str(bundle.get("extraction_text", "")).strip()
    if not cleaned_notes:
        cleaned_notes = (
            "No se extrajeron notas depuradas."
            if language == "es"
            else "No cleaned notes extracted."
        )

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
    raw_transcript_path.write_text(
        _transcript_markdown(bundle, language=language),
        encoding="utf-8",
    )
    cleaned_notes_path.write_text(cleaned_notes + "\n", encoding="utf-8")
    clara_review_path.write_text(
        _clara_review_markdown(bundle, extraction, language=language),
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
        title=(
            str(_source_metadata(bundle).get("title", "")).strip()
            or (
                "Sesión de voz alojada"
                if language == "es" and title == "Hosted voice session"
                else title
            )
        ),
        summary=(
            "Transcripción de voz alojada importada desde un paquete local."
            if language == "es"
            else "Hosted voice transcript imported from local bundle."
        ),
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
        output_language=language,
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
            language=language,
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
    LOGGER.info("Local review pack for Codex: %s", result.discussion_review_pack_path)
    LOGGER.info("Session folder: %s", result.session_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
