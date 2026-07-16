from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "plugins" / "clara" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from advisor_case_core import validate_case_workspace  # noqa: E402
from finalize_hosted_transcript import finalize_hosted_transcript  # noqa: E402
from repair_audio_pointer_links import repair_audio_pointer_links  # noqa: E402

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def _build_workspace(case_dir: Path) -> dict[str, Path]:
    session_dir = case_dir / "voice_sessions" / "20260102T030405Z"
    pointer_dir = case_dir / "source_materials" / "interviews"
    session_dir.mkdir(parents=True)
    pointer_dir.mkdir(parents=True)

    raw_transcript = session_dir / "raw_transcript.md"
    attributed_transcript = session_dir / "attributed_transcript.md"
    pointer_file = pointer_dir / "audio-pointer.md"
    raw_transcript.write_text("# Raw transcript\n\nOriginal words.\n", encoding="utf-8")
    attributed_transcript.write_text(
        "# Attributed transcript\n\nSpeaker 1: Original words.\n",
        encoding="utf-8",
    )
    pointer_file.write_text(
        "# Audio pointer\n\n"
        "- Stato trascrizione: non ancora trascritto\n"
        "- Quando sara' prodotta la trascrizione, collegarla qui.\n",
        encoding="utf-8",
    )

    _write_json(
        case_dir / "case_manifest.json",
        {
            "schema_version": 1,
            "client": "Client",
            "project": "Project",
            "objective": "Objective",
            "audience": "Audience",
            "status": "active",
            "output_language": "it",
            "created_at": "2026-01-02T03:04:05+00:00",
            "updated_at": "2026-01-02T03:04:05+00:00",
        },
    )
    _write_json(
        case_dir / "material_registry.json",
        {
            "schema_version": 1,
            "materials": [
                {
                    "id": "mat-0001",
                    "path": str(raw_transcript.relative_to(case_dir)),
                    "title": "Hosted voice session",
                    "material_type": "transcript",
                    "status": "indexed",
                    "summary": "Hosted voice transcript imported from local bundle.",
                    "added_at": "2026-01-02T03:04:05+00:00",
                    "updated_at": "2026-01-02T03:04:05+00:00",
                    "last_reviewed": None,
                    "source_metadata": {
                        "raw_audio_pointer_material_id": "mat-0002",
                    },
                },
                {
                    "id": "mat-0002",
                    "path": str(pointer_file.relative_to(case_dir)),
                    "title": "Audio pointer",
                    "material_type": "source",
                    "status": "indexed",
                    "summary": "Pointer to raw interview audio.",
                    "added_at": "2026-01-02T03:04:05+00:00",
                    "updated_at": "2026-01-02T03:04:05+00:00",
                    "last_reviewed": None,
                    "source_metadata": {
                        "transcription_status": "pending",
                        "linked_transcript_material_id": "old-mat",
                        "linked_transcript_path": "old/path.md",
                    },
                },
            ],
        },
    )
    _write_json(case_dir / "judgement_log.json", {"schema_version": 1, "entries": []})
    _write_json(
        case_dir / "open_questions.json",
        {"schema_version": 1, "questions": []},
    )
    _write_json(case_dir / "case_issues.json", {"schema_version": 1, "issues": []})
    _write_json(
        case_dir / "clara_mandate.json",
        {
            "schema_version": 1,
            "preparation": {},
            "mandate": {},
            "source_material_ids": [],
            "voice_session_paths": [],
        },
    )
    return {
        "raw_transcript": raw_transcript,
        "attributed_transcript": attributed_transcript,
        "pointer_file": pointer_file,
    }


def _read_registry(case_dir: Path) -> dict[str, Any]:
    return json.loads((case_dir / "material_registry.json").read_text())


def test_repair_audio_pointer_links_runs_before_full_validation(tmp_path: Path) -> None:
    paths = _build_workspace(tmp_path)
    assert validate_case_workspace(tmp_path)

    result = repair_audio_pointer_links(tmp_path, now=FIXED_NOW)

    assert result.repaired_pointer_ids == ("mat-0002",)
    assert validate_case_workspace(tmp_path) == []
    registry = _read_registry(tmp_path)
    pointer = registry["materials"][1]
    assert pointer["source_metadata"]["transcription_status"] == "transcribed"
    assert pointer["source_metadata"]["linked_transcript_material_id"] == "mat-0001"
    assert (
        pointer["source_metadata"]["linked_transcript_path"]
        == "voice_sessions/20260102T030405Z/raw_transcript.md"
    )
    pointer_text = paths["pointer_file"].read_text(encoding="utf-8")
    assert "not yet transcribed" not in pointer_text
    assert "non ancora trascritto" not in pointer_text


def test_finalize_hosted_transcript_repairs_stale_pointer_validation(
    tmp_path: Path,
) -> None:
    paths = _build_workspace(tmp_path)
    assert validate_case_workspace(tmp_path)

    result = finalize_hosted_transcript(
        tmp_path,
        "mat-0001",
        paths["attributed_transcript"],
        raw_transcript_path=paths["raw_transcript"],
        now=FIXED_NOW,
    )

    assert result.audio_pointer_material_id == "mat-0002"
    assert validate_case_workspace(tmp_path) == []
    registry = _read_registry(tmp_path)
    transcript = registry["materials"][0]
    pointer = registry["materials"][1]
    assert transcript["path"] == str(paths["attributed_transcript"].resolve())
    assert (
        pointer["source_metadata"]["linked_transcript_path"]
        == "voice_sessions/20260102T030405Z/attributed_transcript.md"
    )
