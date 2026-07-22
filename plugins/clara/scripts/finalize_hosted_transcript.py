"""Finalize local transcript processing after a hosted Clara import."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from advisor_case_core import (
    CaseWorkspaceError,
    refresh_case_brief,
    register_material,
    validate_case_workspace,
)
from repair_audio_pointer_links import (
    is_repairable_audio_pointer_validation_error,
    repair_audio_pointer_links,
)

__all__ = [
    "FinalizeHostedTranscriptResult",
    "finalize_hosted_transcript",
    "main",
]

LOGGER = logging.getLogger(__name__)

DEFAULT_SPEAKER_ATTRIBUTION_NOTE = (
    "post-import Codex/Clara text-only pass from clean transcript and source metadata; "
    "no audio or voice diarization model used"
)
DEFAULT_TRANSCRIPT_SUMMARY = (
    "Locally stored hosted voice transcript processed by Codex/Clara through the "
    "user's ChatGPT plan with reviewable text-only speaker attribution. Original "
    "unattributed hosted transcript preserved in the same voice session."
)


@dataclass(frozen=True)
class FinalizeHostedTranscriptResult:
    """Files and registry records updated by transcript finalization."""

    material_id: str
    attributed_transcript_path: Path
    unattributed_transcript_backup_path: Path
    audio_pointer_material_id: str | None


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _read_registry(case_dir: Path) -> dict[str, Any]:
    registry_path = case_dir / "material_registry.json"
    return json.loads(registry_path.read_text(encoding="utf-8"))


def _validate_workspace_or_repair_audio_pointer(
    case_dir: Path,
    *,
    transcript_material_id: str,
    now: datetime | None,
) -> None:
    errors = validate_case_workspace(case_dir)
    if not errors:
        return
    if not all(
        is_repairable_audio_pointer_validation_error(
            error,
            transcript_material_id=transcript_material_id,
        )
        for error in errors
    ):
        raise CaseWorkspaceError("; ".join(errors))

    repair_audio_pointer_links(
        case_dir,
        transcript_material_id=transcript_material_id,
        validate_after=False,
        now=now,
    )
    remaining_errors = validate_case_workspace(case_dir)
    if remaining_errors:
        raise CaseWorkspaceError("; ".join(remaining_errors))


def _write_registry(case_dir: Path, registry: dict[str, Any]) -> None:
    registry_path = case_dir / "material_registry.json"
    registry_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _find_material(registry: dict[str, Any], material_id: str) -> dict[str, Any]:
    for material in registry.get("materials", []):
        if material.get("id") == material_id:
            return material
    raise CaseWorkspaceError(f"transcript material not found: {material_id}")


def _relative_path(case_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(case_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def _default_raw_transcript_path(
    *,
    material: dict[str, Any],
    attributed_transcript_path: Path,
) -> Path:
    current_path = Path(str(material.get("path", ""))).expanduser()
    if current_path.name == "raw_transcript.md" and current_path.is_file():
        return current_path
    candidate = attributed_transcript_path.parent / "raw_transcript.md"
    if candidate.is_file():
        return candidate
    if current_path.is_file():
        return current_path
    raise CaseWorkspaceError(
        "raw transcript path could not be inferred; pass --raw-transcript"
    )


def _preserve_unattributed_transcript(
    *,
    raw_transcript_path: Path,
    unattributed_transcript_backup_path: Path,
) -> None:
    if not raw_transcript_path.is_file():
        raise CaseWorkspaceError(
            f"raw transcript does not exist: {raw_transcript_path}"
        )
    if raw_transcript_path.resolve() == unattributed_transcript_backup_path.resolve():
        return
    if unattributed_transcript_backup_path.exists():
        return
    unattributed_transcript_backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_transcript_path, unattributed_transcript_backup_path)


def _resolve_audio_pointer_material_id(
    *,
    case_dir: Path,
    audio_pointer_path: Path | None,
    audio_pointer_material_id: str,
    title: str,
    now: datetime | None,
) -> str | None:
    if audio_pointer_path is not None and audio_pointer_material_id:
        raise CaseWorkspaceError(
            "pass either --audio-pointer or --audio-pointer-material-id, not both"
        )
    if audio_pointer_material_id:
        registry = _read_registry(case_dir)
        _find_material(registry, audio_pointer_material_id)
        return audio_pointer_material_id
    if audio_pointer_path is None:
        return None
    pointer = register_material(
        case_dir,
        audio_pointer_path,
        material_type="source",
        title=title,
        summary=(
            "Pointer to raw interview audio retained for provenance and hosted "
            "transcription."
        ),
        now=now,
    )
    return str(pointer["id"])


def _replace_audio_pointer_transcription_section(
    *,
    text: str,
    transcript_material_id: str,
    transcript_path: str,
    timestamp: str,
) -> str:
    lines = text.splitlines()
    kept_lines: list[str] = []
    skipping_existing_section = False
    status_line_seen = False
    for line in lines:
        if line.strip() == "## Trascrizione Clara":
            skipping_existing_section = True
            continue
        if skipping_existing_section:
            if line.startswith("## "):
                skipping_existing_section = False
            else:
                continue
        if line.startswith("- Stato trascrizione:"):
            kept_lines.append("- Stato trascrizione: trascritto in Clara")
            status_line_seen = True
            continue
        if "Quando sara' prodotta la trascrizione" in line:
            continue
        if "Quando sarà prodotta la trascrizione" in line:
            continue
        kept_lines.append(line)

    while kept_lines and kept_lines[-1] == "":
        kept_lines.pop()
    if not status_line_seen:
        kept_lines.append("")
        kept_lines.append("- Stato trascrizione: trascritto in Clara")
    kept_lines.extend(
        [
            "",
            "## Trascrizione Clara",
            "",
            "- Stato trascrizione: trascritto in Clara",
            f"- Materiale trascrizione: `{transcript_material_id}`",
            f"- Trascrizione collegata: `{transcript_path}`",
            f"- Aggiornato: `{timestamp}`",
        ]
    )
    return "\n".join(kept_lines) + "\n"


def _reconcile_audio_pointer(
    *,
    case_dir: Path,
    registry: dict[str, Any],
    pointer_id: str,
    transcript_material_id: str,
    attributed_transcript_path: Path,
    timestamp: str,
) -> None:
    pointer = _find_material(registry, pointer_id)
    transcript_path = _relative_path(case_dir, attributed_transcript_path)
    metadata = dict(pointer.get("source_metadata") or {})
    metadata["transcription_status"] = "transcribed"
    metadata["linked_transcript_material_id"] = transcript_material_id
    metadata["linked_transcript_path"] = transcript_path
    metadata["transcribed_at"] = timestamp
    pointer["source_metadata"] = metadata
    pointer["summary"] = (
        "Pointer to raw interview audio retained for provenance. "
        f"Transcribed in Clara and linked to {transcript_material_id} "
        f"({transcript_path})."
    )
    pointer["updated_at"] = timestamp

    pointer_path = Path(str(pointer.get("path", ""))).expanduser()
    if not pointer_path.is_absolute():
        pointer_path = case_dir / pointer_path
    if not pointer_path.is_file():
        return
    pointer_text = pointer_path.read_text(encoding="utf-8")
    pointer_path.write_text(
        _replace_audio_pointer_transcription_section(
            text=pointer_text,
            transcript_material_id=transcript_material_id,
            transcript_path=transcript_path,
            timestamp=timestamp,
        ),
        encoding="utf-8",
    )


def finalize_hosted_transcript(
    case_dir: Path,
    material_id: str,
    attributed_transcript_path: Path,
    *,
    raw_transcript_path: Path | None = None,
    unattributed_transcript_backup_path: Path | None = None,
    audio_pointer_path: Path | None = None,
    audio_pointer_material_id: str = "",
    audio_pointer_title: str = "Audio interview pointer",
    speaker_attribution_note: str = DEFAULT_SPEAKER_ATTRIBUTION_NOTE,
    summary: str = DEFAULT_TRANSCRIPT_SUMMARY,
    now: datetime | None = None,
) -> FinalizeHostedTranscriptResult:
    """Record the locally stored text-only transcript review in the Clara registry.

    This is deterministic because it only copies exact files and updates stable
    JSON fields; speaker assignment and boundary judgement happen before this
    helper in the post-import Codex/Clara review loop.
    """

    _validate_workspace_or_repair_audio_pointer(
        case_dir,
        transcript_material_id=material_id,
        now=now,
    )
    attributed_path = attributed_transcript_path.expanduser()
    if not attributed_path.is_file():
        raise CaseWorkspaceError(
            f"attributed transcript does not exist: {attributed_path}"
        )

    registry = _read_registry(case_dir)
    material = _find_material(registry, material_id)
    raw_path = (
        raw_transcript_path.expanduser()
        if raw_transcript_path is not None
        else _default_raw_transcript_path(
            material=material,
            attributed_transcript_path=attributed_path,
        )
    )
    backup_path = (
        unattributed_transcript_backup_path.expanduser()
        if unattributed_transcript_backup_path is not None
        else raw_path.parent / "raw_transcript_unattributed.md"
    )
    _preserve_unattributed_transcript(
        raw_transcript_path=raw_path,
        unattributed_transcript_backup_path=backup_path,
    )

    pointer_id = _resolve_audio_pointer_material_id(
        case_dir=case_dir,
        audio_pointer_path=(
            audio_pointer_path.expanduser() if audio_pointer_path is not None else None
        ),
        audio_pointer_material_id=audio_pointer_material_id,
        title=audio_pointer_title,
        now=now,
    )

    registry = _read_registry(case_dir)
    material = _find_material(registry, material_id)
    timestamp = _now_iso(now)
    material["path"] = str(attributed_path.resolve())
    material["material_type"] = "transcript"
    material["status"] = "indexed"
    material["summary"] = summary
    material["updated_at"] = timestamp
    metadata = dict(material.get("source_metadata") or {})
    metadata["speaker_attribution"] = speaker_attribution_note
    metadata["unattributed_transcript_backup"] = _relative_path(case_dir, backup_path)
    if pointer_id is None:
        existing_pointer_id = str(
            metadata.get("raw_audio_pointer_material_id") or ""
        ).strip()
        pointer_id = existing_pointer_id or None
    if pointer_id is not None:
        metadata["raw_audio_pointer_material_id"] = pointer_id
    material["source_metadata"] = metadata
    if pointer_id is not None:
        _reconcile_audio_pointer(
            case_dir=case_dir,
            registry=registry,
            pointer_id=pointer_id,
            transcript_material_id=material_id,
            attributed_transcript_path=attributed_path,
            timestamp=timestamp,
        )
    _write_registry(case_dir, registry)
    refresh_case_brief(case_dir, now=now)

    return FinalizeHostedTranscriptResult(
        material_id=material_id,
        attributed_transcript_path=attributed_path,
        unattributed_transcript_backup_path=backup_path,
        audio_pointer_material_id=pointer_id,
    )


def main() -> int:
    """Run local hosted transcript finalization."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("material_id")
    parser.add_argument("attributed_transcript", type=Path)
    parser.add_argument("--raw-transcript", type=Path)
    parser.add_argument("--unattributed-backup", type=Path)
    parser.add_argument("--audio-pointer", type=Path)
    parser.add_argument("--audio-pointer-material-id", default="")
    parser.add_argument("--audio-pointer-title", default="Audio interview pointer")
    parser.add_argument(
        "--speaker-attribution-note",
        default=DEFAULT_SPEAKER_ATTRIBUTION_NOTE,
    )
    parser.add_argument("--summary", default=DEFAULT_TRANSCRIPT_SUMMARY)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = finalize_hosted_transcript(
        args.case_dir,
        args.material_id,
        args.attributed_transcript,
        raw_transcript_path=args.raw_transcript,
        unattributed_transcript_backup_path=args.unattributed_backup,
        audio_pointer_path=args.audio_pointer,
        audio_pointer_material_id=args.audio_pointer_material_id,
        audio_pointer_title=args.audio_pointer_title,
        speaker_attribution_note=args.speaker_attribution_note,
        summary=args.summary,
    )
    LOGGER.info("Transcript material finalized: %s", result.material_id)
    LOGGER.info(
        "Attributed transcript: %s",
        result.attributed_transcript_path,
    )
    LOGGER.info(
        "Unattributed transcript backup: %s",
        result.unattributed_transcript_backup_path,
    )
    if result.audio_pointer_material_id is not None:
        LOGGER.info("Audio pointer material: %s", result.audio_pointer_material_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
