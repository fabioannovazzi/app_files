"""Repair stale Clara raw-audio pointer links before full workspace validation."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from advisor_case_core import (
    CaseWorkspaceError,
    refresh_case_brief,
    validate_case_workspace,
)

__all__ = [
    "AudioPointerRepairResult",
    "is_repairable_audio_pointer_validation_error",
    "repair_audio_pointer_links",
    "main",
]

LOGGER = logging.getLogger(__name__)

REPAIRABLE_AUDIO_POINTER_ERROR_MARKERS = (
    "has no source_metadata",
    "is not marked transcribed",
    "does not link back to transcript",
    "has stale linked transcript path",
    "still says not transcribed",
)
STALE_POINTER_TEXT_MARKERS = (
    "non ancora trascritto",
    "not yet transcribed",
    "Quando sara' prodotta la trascrizione",
    "Quando sarà prodotta la trascrizione",
)


@dataclass(frozen=True)
class AudioPointerRepairResult:
    """Audio pointer records repaired by the targeted helper."""

    repaired_pointer_ids: tuple[str, ...]
    skipped_transcript_ids: tuple[str, ...]
    registry_path: Path


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _read_registry(case_dir: Path) -> dict[str, Any]:
    registry_path = case_dir / "material_registry.json"
    return json.loads(registry_path.read_text(encoding="utf-8"))


def _write_registry(case_dir: Path, registry: Mapping[str, Any]) -> None:
    registry_path = case_dir / "material_registry.json"
    registry_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _material_path(case_dir: Path, material: Mapping[str, Any]) -> Path:
    raw_path = Path(str(material.get("path", ""))).expanduser()
    if raw_path.is_absolute():
        return raw_path.resolve()
    return (case_dir / raw_path).resolve()


def _relative_path(case_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(case_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def is_repairable_audio_pointer_validation_error(
    error: str,
    *,
    transcript_material_id: str = "",
) -> bool:
    """Return whether a validation error is safe for targeted pointer repair."""

    if "material_registry.json: audio pointer " not in error:
        return False
    if transcript_material_id and transcript_material_id not in error:
        return False
    return any(marker in error for marker in REPAIRABLE_AUDIO_POINTER_ERROR_MARKERS)


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
        if any(marker in line for marker in STALE_POINTER_TEXT_MARKERS):
            continue
        kept_lines.append(line)

    while kept_lines and kept_lines[-1] == "":
        kept_lines.pop()
    if not status_line_seen:
        kept_lines.extend(["", "- Stato trascrizione: trascritto in Clara"])
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


def repair_audio_pointer_links(
    case_dir: Path,
    *,
    transcript_material_id: str = "",
    validate_after: bool = True,
    now: datetime | None = None,
) -> AudioPointerRepairResult:
    """Repair existing transcript-to-audio-pointer links without pre-validation."""

    timestamp = _now_iso(now)
    registry_path = case_dir / "material_registry.json"
    registry = _read_registry(case_dir)
    materials = registry.get("materials")
    if not isinstance(materials, list):
        raise CaseWorkspaceError("material_registry.json: materials must be a list")

    material_by_id = {
        str(material.get("id")): material
        for material in materials
        if isinstance(material, dict) and material.get("id")
    }
    repaired_pointer_ids: list[str] = []
    skipped_transcript_ids: list[str] = []
    matched_transcript = False

    for material in materials:
        if not isinstance(material, dict):
            continue
        transcript_id = str(material.get("id") or "").strip()
        if transcript_material_id and transcript_id != transcript_material_id:
            continue
        if material.get("material_type") != "transcript":
            continue
        matched_transcript = True
        metadata = material.get("source_metadata")
        if not isinstance(metadata, dict):
            skipped_transcript_ids.append(transcript_id)
            continue
        pointer_id = str(metadata.get("raw_audio_pointer_material_id") or "").strip()
        if not pointer_id:
            skipped_transcript_ids.append(transcript_id)
            continue
        pointer = material_by_id.get(pointer_id)
        if not isinstance(pointer, dict):
            raise CaseWorkspaceError(
                "material_registry.json: transcript "
                f"{transcript_id} links missing raw audio pointer {pointer_id}"
            )

        transcript_path = _relative_path(case_dir, _material_path(case_dir, material))
        pointer_metadata = dict(pointer.get("source_metadata") or {})
        pointer_metadata["transcription_status"] = "transcribed"
        pointer_metadata["linked_transcript_material_id"] = transcript_id
        pointer_metadata["linked_transcript_path"] = transcript_path
        pointer_metadata["transcribed_at"] = timestamp
        pointer["source_metadata"] = pointer_metadata
        pointer["summary"] = (
            "Pointer to raw interview audio retained for provenance. "
            f"Transcribed in Clara and linked to {transcript_id} "
            f"({transcript_path})."
        )
        pointer["updated_at"] = timestamp
        repaired_pointer_ids.append(pointer_id)

        pointer_path = _material_path(case_dir, pointer)
        if pointer_path.is_file():
            pointer_text = pointer_path.read_text(encoding="utf-8")
            pointer_path.write_text(
                _replace_audio_pointer_transcription_section(
                    text=pointer_text,
                    transcript_material_id=transcript_id,
                    transcript_path=transcript_path,
                    timestamp=timestamp,
                ),
                encoding="utf-8",
            )

    if transcript_material_id and not matched_transcript:
        raise CaseWorkspaceError(
            f"transcript material not found: {transcript_material_id}"
        )

    if repaired_pointer_ids:
        _write_registry(case_dir, registry)

    result = AudioPointerRepairResult(
        repaired_pointer_ids=tuple(repaired_pointer_ids),
        skipped_transcript_ids=tuple(skipped_transcript_ids),
        registry_path=registry_path,
    )
    if validate_after:
        errors = validate_case_workspace(case_dir)
        if errors:
            raise CaseWorkspaceError("; ".join(errors))
        if repaired_pointer_ids:
            refresh_case_brief(case_dir, now=now)
    return result


def main() -> int:
    """Run targeted Clara audio pointer link repair."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument(
        "--transcript-material-id",
        default="",
        help="Limit repair to one transcript material id.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = repair_audio_pointer_links(
        args.case_dir,
        transcript_material_id=args.transcript_material_id,
    )
    LOGGER.info(
        "Repaired audio pointer link(s): %s",
        ", ".join(result.repaired_pointer_ids) or "none",
    )
    if result.skipped_transcript_ids:
        LOGGER.info(
            "Skipped transcript(s) without pointer links: %s",
            ", ".join(result.skipped_transcript_ids),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
