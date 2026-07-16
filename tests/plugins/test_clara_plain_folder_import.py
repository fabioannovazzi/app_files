from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    ROOT / "plugins" / "clara" / "scripts" / "import_hosted_voice_bundle_to_folder.py"
)
FIXED_NOW = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)


def load_importer() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_plain_folder_voice_importer",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def voice_payload(
    *,
    captured_at: str = "2026-07-10T14:04:07+00:00",
    transcript: str = "Facilitator presents the pilot. Taylor discusses benchmarking.",
    audio_file_name: str = "meeting.webm",
    source: str = "case_notes_hosted_voice",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": source,
        "captured_at": captured_at,
        "capture_elapsed_seconds": 1776.75,
        "capture_source": "uploaded_audio",
        "language": "it",
        "audio_file_name": audio_file_name,
        "raw_transcription_text": transcript,
        "user_transcript": transcript,
        "source_metadata": {
            "title": "Example Case",
            "participants": "Facilitator, Taylor, Alex",
        },
    }


def write_zip_bundle(
    path: Path,
    payload: dict[str, Any],
    *,
    audio_bytes: bytes = b"audio bytes",
    extra_member: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    json_name = f"{path.stem}.json"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(json_name, json.dumps(payload, ensure_ascii=False))
        audio_name = str(payload.get("audio_file_name", "")).strip()
        if audio_name:
            archive.writestr(audio_name, audio_bytes)
        if extra_member:
            archive.writestr("capture-note.txt", "same hosted payload")


def write_json_bundle(
    path: Path,
    payload: dict[str, Any],
    *,
    audio_bytes: bytes = b"audio bytes",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    audio_path = path.parent / str(payload["audio_file_name"])
    audio_path.write_bytes(audio_bytes)
    return audio_path


def test_plain_folder_import_creates_bundle_transcript_and_registry(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    source_dir = tmp_path / "Downloads"
    target_dir = tmp_path / "documents"
    bundle_path = source_dir / "case-notes-audio-20260710T140407.zip"
    write_zip_bundle(bundle_path, voice_payload())

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )

    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    transcript = result.transcript_path.read_text(encoding="utf-8")
    assert result.status == "imported"
    assert result.bundle_path.read_bytes() == bundle_path.read_bytes()
    assert result.transcript_path.name == (
        "case-notes-audio-20260710T140407-transcript.md"
    )
    assert "Example Case — Trascrizione della call" in transcript
    assert "Facilitator, Taylor, Alex" in transcript
    assert "Facilitator presents the pilot." in transcript
    assert registry["kind"] == "clara_plain_folder_voice_imports"
    assert len(registry["imports"]) == 1
    assert registry["imports"][0]["artifacts"]["bundle"]["path"] == (
        result.bundle_path.name
    )
    assert not (target_dir / "case_manifest.json").exists()
    assert not (target_dir / "voice_sessions").exists()


def test_plain_folder_import_exact_rerun_is_idempotent(tmp_path: Path) -> None:
    importer = load_importer()
    source_dir = tmp_path / "Downloads"
    target_dir = tmp_path / "documents"
    bundle_path = source_dir / "case-notes-audio-20260710T140407.zip"
    write_zip_bundle(bundle_path, voice_payload())
    first = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )
    transcript_before = first.transcript_path.read_bytes()
    registry_before = first.registry_path.read_bytes()

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )

    assert result.status == "already_imported"
    assert result.transcript_path == first.transcript_path
    assert result.bundle_path == first.bundle_path
    assert result.transcript_path.read_bytes() == transcript_before
    assert result.registry_path.read_bytes() == registry_before
    assert len(list(target_dir.glob("*-transcript*.md"))) == 1
    assert len(json.loads(registry_before)["imports"]) == 1


def test_plain_folder_import_dedupes_repackaged_bundle(tmp_path: Path) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    payload = voice_payload()
    first_bundle = tmp_path / "first" / "case-notes-audio-first.zip"
    repackaged_bundle = tmp_path / "second" / "case-notes-audio-repacked.zip"
    write_zip_bundle(first_bundle, payload)
    write_zip_bundle(repackaged_bundle, payload, extra_member=True)
    first = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        first_bundle,
        now=FIXED_NOW,
    )

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        repackaged_bundle,
        now=FIXED_NOW,
    )

    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert result.status == "already_imported"
    assert result.dedupe_reason == "payload_sha256"
    assert result.bundle_path == first.bundle_path
    assert len(registry["imports"]) == 1
    assert not (target_dir / repackaged_bundle.name).exists()


def test_plain_folder_import_adopts_existing_manual_transcript(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    target_dir.mkdir()
    source_bundle = tmp_path / "Downloads" / "case-notes-audio-existing.zip"
    payload = voice_payload(transcript="Existing clean transcript text.")
    write_zip_bundle(source_bundle, payload)
    target_bundle = target_dir / source_bundle.name
    shutil.copy2(source_bundle, target_bundle)
    transcript_path = target_dir / "case-notes-audio-existing-transcript.md"
    manual_document = (
        "# Example Case — Trascrizione della call\n\n"
        "Manual metadata retained.\n\n"
        "## Trascrizione\n\n"
        "Existing clean transcript text.\n"
    )
    transcript_path.write_text(manual_document, encoding="utf-8")

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        source_bundle,
        now=FIXED_NOW,
    )

    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert result.status == "adopted"
    assert result.bundle_path == target_bundle
    assert result.transcript_path == transcript_path
    assert transcript_path.read_text(encoding="utf-8") == manual_document
    assert registry["imports"][0]["artifacts"]["bundle"]["managed"] is False
    assert registry["imports"][0]["artifacts"]["transcript"]["managed"] is False


def test_plain_folder_import_does_not_adopt_content_without_matching_bundle(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    target_dir.mkdir()
    source_bundle = tmp_path / "Downloads" / "case-notes-audio-call.zip"
    existing_bundle = target_dir / source_bundle.name
    shared_text = "The same generic words can occur in different calls."
    write_zip_bundle(
        existing_bundle,
        voice_payload(
            captured_at="2026-07-09T10:00:00+00:00",
            transcript=shared_text,
        ),
        audio_bytes=b"first call",
    )
    write_zip_bundle(
        source_bundle,
        voice_payload(
            captured_at="2026-07-10T10:00:00+00:00",
            transcript=shared_text,
        ),
        audio_bytes=b"second call",
    )
    manual_transcript = target_dir / "case-notes-audio-call-transcript.md"
    manual_transcript.write_text(
        f"# Existing transcript\n\n## Transcript\n\n{shared_text}\n",
        encoding="utf-8",
    )

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        source_bundle,
        now=FIXED_NOW,
    )

    assert result.status == "imported"
    assert result.bundle_path.name == "case-notes-audio-call-2.zip"
    assert result.transcript_path.name == "case-notes-audio-call-2-transcript.md"
    assert result.transcript_path != manual_transcript


def test_plain_folder_import_repairs_missing_transcript(tmp_path: Path) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    target_dir.mkdir()
    bundle_path = target_dir / "case-notes-audio-existing.zip"
    write_zip_bundle(bundle_path, voice_payload())

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )

    assert result.status == "repaired"
    assert result.bundle_path == bundle_path
    assert result.transcript_path.exists()
    assert result.transcript_path.name == "case-notes-audio-existing-transcript.md"


def test_plain_folder_import_repairs_missing_registered_transcript(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    bundle_path = tmp_path / "Downloads" / "case-notes-audio-repair.zip"
    write_zip_bundle(bundle_path, voice_payload())
    first = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )
    first.transcript_path.unlink()

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )

    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert result.status == "repaired"
    assert result.import_id == first.import_id
    assert result.transcript_path.exists()
    assert len(registry["imports"]) == 1
    assert registry["imports"][0]["artifacts"]["transcript"]["managed"] is True


def test_plain_folder_import_repairs_missing_registered_bundle(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    bundle_path = tmp_path / "Downloads" / "case-notes-audio-repair.zip"
    write_zip_bundle(bundle_path, voice_payload())
    first = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )
    first.bundle_path.unlink()

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )

    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert result.status == "repaired"
    assert result.bundle_path.exists()
    assert len(registry["imports"]) == 1
    assert registry["imports"][0]["artifacts"]["bundle"]["managed"] is True


def test_plain_folder_import_preserves_edited_transcript_on_rerun(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    bundle_path = tmp_path / "Downloads" / "case-notes-audio-edit.zip"
    write_zip_bundle(bundle_path, voice_payload())
    first = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )
    edited = (
        first.transcript_path.read_text(encoding="utf-8") + "\nAdvisor correction.\n"
    )
    first.transcript_path.write_text(edited, encoding="utf-8")

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )

    assert result.status == "already_imported"
    assert result.transcript_path.read_text(encoding="utf-8") == edited
    assert result.warnings == (
        "The existing transcript document was edited after import and was preserved.",
    )


def test_plain_folder_import_adopts_loose_json_and_copies_companion_audio(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    target_dir.mkdir()
    source_json = tmp_path / "Downloads" / "case-notes-audio-loose.json"
    payload = voice_payload(transcript="Loose JSON transcript.")
    source_audio = write_json_bundle(source_json, payload)
    target_json = target_dir / source_json.name
    shutil.copy2(source_json, target_json)
    transcript_path = target_dir / "case-notes-audio-loose-transcript.md"
    transcript_path.write_text(
        "# Manual\n\n## Transcript\n\nLoose JSON transcript.\n",
        encoding="utf-8",
    )

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        source_json,
        now=FIXED_NOW,
    )

    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    copied_audio = target_dir / source_audio.name
    assert result.status == "adopted"
    assert result.media_paths == (copied_audio,)
    assert copied_audio.read_bytes() == source_audio.read_bytes()
    assert registry["imports"][0]["artifacts"]["media"][0]["managed"] is True


def test_plain_folder_import_repairs_missing_loose_companion_audio(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    source_json = tmp_path / "Downloads" / "case-notes-audio-loose.json"
    payload = voice_payload(transcript="Loose JSON transcript.")
    source_audio = write_json_bundle(source_json, payload)
    first = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        source_json,
        now=FIXED_NOW,
    )
    first.media_paths[0].unlink()

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        source_json,
        now=FIXED_NOW,
    )

    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert result.status == "repaired"
    assert result.media_paths[0].read_bytes() == source_audio.read_bytes()
    assert len(registry["imports"]) == 1
    assert registry["imports"][0]["artifacts"]["media"][0]["managed"] is True


def test_plain_folder_import_marks_preexisting_loose_media_unmanaged(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    target_dir.mkdir()
    bundle_path = target_dir / "case-notes-audio-loose.json"
    payload = voice_payload(transcript="Already local transcript.")
    write_json_bundle(bundle_path, payload)
    (target_dir / "case-notes-audio-loose-transcript.md").write_text(
        "# Manual\n\n## Transcript\n\nAlready local transcript.\n",
        encoding="utf-8",
    )

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        now=FIXED_NOW,
    )

    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert result.status == "adopted"
    assert registry["imports"][0]["artifacts"]["media"][0]["managed"] is False


def test_plain_folder_import_suffixes_unrelated_basename_collision(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    first_bundle = tmp_path / "first" / "case-notes-audio-call.zip"
    second_bundle = tmp_path / "second" / "case-notes-audio-call.zip"
    write_zip_bundle(
        first_bundle,
        voice_payload(
            captured_at="2026-07-10T10:00:00+00:00",
            transcript="First unrelated call.",
        ),
        audio_bytes=b"first audio",
    )
    write_zip_bundle(
        second_bundle,
        voice_payload(
            captured_at="2026-07-11T10:00:00+00:00",
            transcript="Second unrelated call.",
        ),
        audio_bytes=b"second audio",
    )
    importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        first_bundle,
        now=FIXED_NOW,
    )

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        second_bundle,
        now=FIXED_NOW,
    )

    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert result.status == "imported"
    assert result.bundle_path.name == "case-notes-audio-call-2.zip"
    assert result.transcript_path.name == "case-notes-audio-call-2-transcript.md"
    assert len(registry["imports"]) == 2


def test_plain_folder_import_rejects_changed_transcript_for_same_audio(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    first_bundle = tmp_path / "first" / "case-notes-audio-first.zip"
    variant_bundle = tmp_path / "second" / "case-notes-audio-variant.zip"
    write_zip_bundle(
        first_bundle,
        voice_payload(transcript="First transcript."),
        audio_bytes=b"same audio",
    )
    write_zip_bundle(
        variant_bundle,
        voice_payload(transcript="Changed transcript."),
        audio_bytes=b"same audio",
    )
    importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        first_bundle,
        now=FIXED_NOW,
    )

    with pytest.raises(
        importer.PlainFolderImportError,
        match="conflicts with an existing recording identity",
    ):
        importer.import_hosted_voice_bundle_to_folder(
            target_dir,
            variant_bundle,
            now=FIXED_NOW,
        )

    registry = json.loads(
        (target_dir / ".clara" / "voice_imports.json").read_text(encoding="utf-8")
    )
    assert len(registry["imports"]) == 1
    assert len(list(target_dir.glob("*.zip"))) == 1


def test_plain_folder_import_rejects_changed_audio_for_same_payload(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    payload = voice_payload(transcript="Same transcript and payload.")
    first_bundle = tmp_path / "first" / "case-notes-audio-first.zip"
    changed_media_bundle = tmp_path / "second" / "case-notes-audio-second.zip"
    write_zip_bundle(first_bundle, payload, audio_bytes=b"first audio")
    write_zip_bundle(changed_media_bundle, payload, audio_bytes=b"changed audio")
    importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        first_bundle,
        now=FIXED_NOW,
    )

    with pytest.raises(
        importer.PlainFolderImportError,
        match="conflicts with an existing recording identity",
    ):
        importer.import_hosted_voice_bundle_to_folder(
            target_dir,
            changed_media_bundle,
            now=FIXED_NOW,
        )

    registry = json.loads(
        (target_dir / ".clara" / "voice_imports.json").read_text(encoding="utf-8")
    )
    assert len(registry["imports"]) == 1


def test_plain_folder_import_invalid_source_leaves_folder_unchanged(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    bundle_path = tmp_path / "Downloads" / "case-notes-audio-invalid.zip"
    write_zip_bundle(bundle_path, voice_payload(source="unsupported"))

    with pytest.raises(
        importer.PlainFolderImportError,
        match="unsupported source",
    ):
        importer.import_hosted_voice_bundle_to_folder(
            target_dir,
            bundle_path,
            now=FIXED_NOW,
        )

    assert not target_dir.exists()


def test_plain_folder_import_prefers_final_user_transcript(tmp_path: Path) -> None:
    importer = load_importer()
    payload = voice_payload(transcript="Final reviewed transcript.")
    payload["raw_transcription_text"] = "Earlier raw transcript."
    bundle_path = tmp_path / "case-notes-audio-fields.zip"
    write_zip_bundle(bundle_path, payload)

    result = importer.import_hosted_voice_bundle_to_folder(
        tmp_path / "documents",
        bundle_path,
        now=FIXED_NOW,
    )

    transcript = result.transcript_path.read_text(encoding="utf-8")
    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert "Final reviewed transcript." in transcript
    assert "Earlier raw transcript." not in transcript
    assert registry["imports"][0]["metadata"]["transcript_field"] == ("user_transcript")


def test_plain_folder_import_ignores_non_string_transcript_field(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    payload = voice_payload(transcript="Raw fallback transcript.")
    payload["user_transcript"] = None
    bundle_path = tmp_path / "case-notes-audio-fields.zip"
    write_zip_bundle(bundle_path, payload)

    result = importer.import_hosted_voice_bundle_to_folder(
        tmp_path / "documents",
        bundle_path,
        now=FIXED_NOW,
    )

    transcript = result.transcript_path.read_text(encoding="utf-8")
    assert "Raw fallback transcript." in transcript
    assert "None" not in transcript


def test_plain_folder_import_dry_run_writes_nothing(tmp_path: Path) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    bundle_path = tmp_path / "Downloads" / "case-notes-audio-dry-run.zip"
    write_zip_bundle(bundle_path, voice_payload())

    result = importer.import_hosted_voice_bundle_to_folder(
        target_dir,
        bundle_path,
        dry_run=True,
        now=FIXED_NOW,
    )

    assert result.status == "imported"
    assert not target_dir.exists()


def test_plain_folder_import_rejects_case_workspace(tmp_path: Path) -> None:
    importer = load_importer()
    target_dir = tmp_path / "case"
    target_dir.mkdir()
    (target_dir / "case_manifest.json").write_text("{}\n", encoding="utf-8")
    bundle_path = tmp_path / "Downloads" / "case-notes-audio-case.zip"
    write_zip_bundle(bundle_path, voice_payload())

    with pytest.raises(
        importer.PlainFolderImportError,
        match="use import_hosted_voice_bundle.py",
    ):
        importer.import_hosted_voice_bundle_to_folder(
            target_dir,
            bundle_path,
            now=FIXED_NOW,
        )


def test_plain_folder_import_rejects_unsafe_zip_member(tmp_path: Path) -> None:
    importer = load_importer()
    bundle_path = tmp_path / "case-notes-audio-unsafe.zip"
    payload = voice_payload()
    with ZipFile(bundle_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("case-notes-audio-unsafe.json", json.dumps(payload))
        archive.writestr("../meeting.webm", b"unsafe")

    with pytest.raises(
        importer.PlainFolderImportError,
        match="unsafe member path",
    ):
        importer.import_hosted_voice_bundle_to_folder(
            tmp_path / "documents",
            bundle_path,
            now=FIXED_NOW,
        )


def test_plain_folder_import_rejects_symlinked_control_directory(
    tmp_path: Path,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    outside_dir = tmp_path / "outside"
    target_dir.mkdir()
    outside_dir.mkdir()
    (target_dir / ".clara").symlink_to(outside_dir, target_is_directory=True)
    bundle_path = tmp_path / "case-notes-audio-symlink.zip"
    write_zip_bundle(bundle_path, voice_payload())

    with pytest.raises(
        importer.PlainFolderImportError,
        match="control directory must not be a symlink",
    ):
        importer.import_hosted_voice_bundle_to_folder(
            target_dir,
            bundle_path,
            now=FIXED_NOW,
        )

    assert not (outside_dir / "voice_imports.json").exists()


def test_plain_folder_import_refuses_concurrent_artifact_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = load_importer()
    target_dir = tmp_path / "documents"
    bundle_path = tmp_path / "case-notes-audio-race.zip"
    write_zip_bundle(bundle_path, voice_payload())
    original_available_path = importer._available_path

    def reserve_after_selection(folder: Path, name: str) -> Path:
        selected = original_available_path(folder, name)
        if selected.suffix == ".zip":
            selected.parent.mkdir(parents=True, exist_ok=True)
            selected.write_bytes(b"concurrent file")
        return selected

    monkeypatch.setattr(importer, "_available_path", reserve_after_selection)

    with pytest.raises(
        importer.PlainFolderImportError,
        match="refusing to overwrite a concurrently created artifact",
    ):
        importer.import_hosted_voice_bundle_to_folder(
            target_dir,
            bundle_path,
            now=FIXED_NOW,
        )

    assert (target_dir / bundle_path.name).read_bytes() == b"concurrent file"
    assert not (target_dir / ".clara" / "voice_imports.json").exists()


def test_plain_folder_import_json_cli_writes_result_to_stdout(
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "case-notes-audio-cli.zip"
    write_zip_bundle(bundle_path, voice_payload())

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            str(tmp_path / "documents"),
            str(bundle_path),
            "--dry-run",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert payload["status"] == "imported"
