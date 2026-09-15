"""Exercise authored transcript kits through Clara's real local import routes.

The sources are explicitly fictional written transcripts, without recorded audio.
The fixed review below interprets only those exact teaching inputs; it is not a
runtime speaker classifier or evidence of a learner's review.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tests.plugins._teaching_release import record_native_check

ROOT = Path(__file__).resolve().parents[2]
CLARA = ROOT / "plugins/clara"


def _load(name):
    spec = importlib.util.spec_from_file_location(
        "kit_" + name, CLARA / "scripts" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _kit(tmp_path, monkeypatch, language):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    monkeypatch.syspath_prepend(str(CLARA / "scripts"))
    from courseware.library import CourseLibrary

    return CourseLibrary(CLARA, {"transcribe"}).render(
        "transcribe", language, tmp_path / "kit"
    )


def _bundle(kit, phase):
    return next(
        Path(path)
        for path in kit["source_files" if phase == "demo" else "practice_files"]
        if Path(path).suffix == ".json"
    )


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_transcript_kit_imports_reviews_and_registers_actual_case_sources(
    tmp_path, monkeypatch, language, phase, record_property
):
    kit = _kit(tmp_path, monkeypatch, language)
    core = _load("advisor_case_core")
    importer = _load("import_hosted_voice_bundle")
    finalizer = _load("finalize_hosted_transcript")
    case = tmp_path / "case"
    core.initialize_case(
        case,
        client="Ciclo Arco — fictional kit",
        project="Review imported notes",
        objective="Preserve wording and review attribution without making a service decision.",
        audience="Owner",
        output_language=language,
    )
    earlier = {}
    receipts = []
    phases = ("demo",) if phase == "demo" else ("demo", "practice")
    for current_phase in phases:
        source = _bundle(kit, current_phase)
        original = source.read_bytes()
        payload = json.loads(original)
        assert payload["capture_source"] == "fictional_teaching_fixture"
        assert payload["model"] == "none-fictional-authored-text"
        result = importer.import_hosted_voice_bundle(case, source)
        assert result.audio_path is None
        assert result.judgement_count == result.open_question_count == 0
        raw = result.raw_transcript_path.read_bytes()
        assert payload["user_transcript"] in raw.decode()
        reviewed = result.session_dir / "kit-reviewed-transcript.md"
        # Text-only model-authored review of these exact authored notes. Sara
        # identifies herself in the first input; the other voices stay unnamed.
        reviewed.write_text(
            "# Ciclo Arco\n\n"
            + ("Sara Campione\n\n" if current_phase == "demo" else "")
            + payload["user_transcript"]
            + "\n",
            encoding="utf-8",
        )
        finished = finalizer.finalize_hosted_transcript(
            case,
            result.material_id,
            reviewed,
            raw_transcript_path=result.raw_transcript_path,
            speaker_attribution_note=(
                "Fictional source self-identifies Sara Campione."
                if current_phase == "demo"
                else "Preserve the two source speaker labels: names are undocumented."
            ),
            summary="Fictional written teaching source; no audio was captured or transcribed.",
        )
        assert finished.unattributed_transcript_backup_path.read_bytes() == raw
        register = json.loads((case / "advisory_evidence_register.json").read_text())
        receipt = next(
            item
            for item in register["evidence"]
            if item["id"] == finished.evidence_receipt_id
        )
        assert receipt["evidence_type"] == "interview_transcript"
        assert (
            payload["user_transcript"]
            in finished.attributed_transcript_path.read_text()
        )
        assert (
            receipt["source"]["artifact_refs"][0]["sha256"]
            == hashlib.sha256(
                finished.attributed_transcript_path.read_bytes()
            ).hexdigest()
        )
        materials = json.loads((case / "material_registry.json").read_text())[
            "materials"
        ]
        material = next(row for row in materials if row["id"] == finished.material_id)
        assert Path(material["path"]) == finished.attributed_transcript_path.resolve()
        assert material["status"] == "indexed"
        assert material["source_metadata"]["speaker_attribution"]
        receipts.append(receipt["id"])
        assert source.read_bytes() == original
        for path, content in earlier.items():
            assert path.read_bytes() == content
        earlier[finished.unattributed_transcript_backup_path] = raw
        earlier[finished.attributed_transcript_path] = (
            finished.attributed_transcript_path.read_bytes()
        )
    assert len(set(receipts)) == len(phases)
    assert core.validate_case_workspace(case) == []
    assert json.loads((case / "judgement_log.json").read_text())["entries"] == []
    record_native_check(
        record_property,
        root=ROOT,
        product="clara",
        workflow="transcribe",
        language=language,
        phase=phase,
    )


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_transcript_kit_ordinary_folder_preserves_bundle_and_reuses_duplicate(
    tmp_path, monkeypatch, language
):
    kit = _kit(tmp_path, monkeypatch, language)
    importer = _load("import_hosted_voice_bundle_to_folder")
    target = tmp_path / "ordinary-folder"
    source = _bundle(kit, "demo")
    first = importer.import_hosted_voice_bundle_to_folder(target, source)
    preserved = {
        path: path.read_bytes() for path in (first.bundle_path, first.transcript_path)
    }
    second = importer.import_hosted_voice_bundle_to_folder(target, source)
    assert second.import_id == first.import_id
    assert second.dedupe_reason is not None
    assert {path: path.read_bytes() for path in preserved} == preserved
    assert not (target / "case_manifest.json").exists()
    practice = importer.import_hosted_voice_bundle_to_folder(
        target, _bundle(kit, "practice")
    )
    assert practice.import_id != first.import_id
    assert {path: path.read_bytes() for path in preserved} == preserved
