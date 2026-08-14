from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import sys
import wave
import zipfile
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SKILL_ROOT = CLARA_ROOT / "skills" / "research-video"
SCRIPT_PATH = SKILL_ROOT / "scripts" / "research_video.py"


def _load_renderer() -> Any:
    """Load the packaged renderer from its editable source path."""

    spec = importlib.util.spec_from_file_location("clara_research_video", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_image(path: Path, color: tuple[int, int, int]) -> Path:
    """Write one small deterministic scene image."""

    Image.new("RGB", (320, 180), color).save(path)
    return path


def _scene_plan(
    first: Path,
    second: Path,
    *,
    language: str = "en",
) -> dict[str, Any]:
    """Return the smallest complete public scene-plan contract."""

    return {
        "schema_version": 1,
        "title": "Reviewed market finding",
        "language": language,
        "scenes": [
            {
                "id": "market-context",
                "image": str(first),
                "narration": "The supplied figure shows the reviewed market context.",
                "source_basis": [
                    {
                        "reference": "Research pack, figure 1",
                        "supports": "The figure is the approved market-context scene.",
                    }
                ],
            },
            {
                "id": "decision-implication",
                "image": str(second),
                "narration": "The supplied comparison supports the stated decision implication.",
                "source_basis": [
                    {
                        "reference": "Research pack, figure 2",
                        "supports": "The comparison is the approved decision scene.",
                    }
                ],
            },
        ],
    }


def _prepare_fixture(
    tmp_path: Path,
    *,
    layered: bool = False,
    language: str = "en",
) -> tuple[Any, Path, Path, Path]:
    """Prepare one two-scene run and return its paths."""

    renderer = _load_renderer()
    first = _write_image(tmp_path / "first.png", (0, 32, 96))
    second = _write_image(tmp_path / "second.png", (0, 160, 210))
    plan = _scene_plan(first, second, language=language)
    if layered:
        foreground = tmp_path / "foreground.png"
        layer = Image.new("RGBA", (320, 180), (0, 0, 0, 0))
        layer.paste((255, 240, 210, 180), (100, 45, 220, 150))
        layer.save(foreground)
        plan["scenes"][0]["foreground_image"] = str(foreground)
        plan["scenes"][0]["motion"] = "layered_parallax"
    plan_path = tmp_path / "scene-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    run_dir = tmp_path / "research-video"
    renderer.prepare_run(plan_path, run_dir)
    return renderer, run_dir, first, second


def _write_test_voice(path: Path, _text: str) -> bytes:
    """Write a short PCM test signal for media assembly, never semantic speech."""

    frame_rate = 16_000
    duration_seconds = 0.35
    frame_count = round(frame_rate * duration_seconds)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(frame_rate)
        samples = b"".join(
            struct.pack("<h", 500 if (index // 40) % 2 else -500)
            for index in range(frame_count)
        )
        output.writeframes(samples)
    return path.read_bytes()


def _write_fixture_voice_bundle(
    renderer: Any,
    run_dir: Path,
    tmp_path: Path,
    *,
    source: str = "mparanza_hosted_openai_voice",
) -> Path:
    """Write one complete hosted narration ZIP fixture."""

    plan = json.loads((run_dir / "scene_plan.json").read_text(encoding="utf-8"))
    approval = json.loads(
        (run_dir / "narration_approval.json").read_text(encoding="utf-8")
    )
    request = json.loads(
        (run_dir / "mparanza_voice_request.json").read_text(encoding="utf-8")
    )
    scenes: list[dict[str, object]] = []
    audio_files: list[tuple[str, bytes]] = []
    for index, scene in enumerate(plan["scenes"], start=1):
        audio = tmp_path / f"{scene['id']}.wav"
        audio_bytes = _write_test_voice(audio, scene["narration"])
        audio_name = f"audio/{index:02d}-{scene['id']}.wav"
        with wave.open(str(audio), "rb") as voice:
            frame_count = voice.getnframes()
            frame_rate = voice.getframerate()
            channels = voice.getnchannels()
            sample_width = voice.getsampwidth()
        scenes.append(
            {
                "id": scene["id"],
                "audio": audio_name,
                "sha256": hashlib.sha256(audio_bytes).hexdigest(),
                "size_bytes": len(audio_bytes),
                "frame_count": frame_count,
                "frame_rate": frame_rate,
                "channels": channels,
                "sample_width_bytes": sample_width,
                "duration_seconds": round(frame_count / frame_rate, 6),
            }
        )
        audio_files.append((audio_name, audio_bytes))
    manifest = {
        "schema_version": 1,
        "workflow": "clara:research-video",
        "source": source,
        "provider": "OpenAI",
        "model": "gpt-4o-mini-tts",
        "voice": "marin" if plan["language"] == "it" else "cedar",
        "language": plan["language"],
        "generated_at": "2026-08-14T12:00:00+00:00",
        "request_sha256": renderer._json_sha256(request),
        "scene_plan_sha256": renderer._json_sha256(plan),
        "approval_sha256": renderer._json_sha256(approval),
        "mparanza_application_retention": "in_memory_response_only",
        "scenes": scenes,
    }
    bundle_path = tmp_path / "hosted-voice.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest))
        for audio_name, audio_bytes in audio_files:
            bundle.writestr(audio_name, audio_bytes)
    return bundle_path


def _attach_fixture_voice(
    renderer: Any,
    run_dir: Path,
    tmp_path: Path,
    *,
    source: str = "mparanza_hosted_openai_voice",
) -> tuple[Path, dict[str, Any]]:
    """Attach one complete hosted voice bundle."""

    bundle_path = _write_fixture_voice_bundle(
        renderer,
        run_dir,
        tmp_path,
        source=source,
    )
    attached = renderer.attach_hosted_voice(run_dir, bundle_path)
    return bundle_path, attached


def test_prepare_run_writes_reviewable_contract_without_external_output(
    tmp_path: Path,
) -> None:
    renderer, run_dir, _first, _second = _prepare_fixture(tmp_path, layered=True)

    intake = json.loads((run_dir / "run_intake.json").read_text(encoding="utf-8"))
    script = (run_dir / "narration_script.md").read_text(encoding="utf-8")
    review = (run_dir / "review_packet.md").read_text(encoding="utf-8")

    assert intake["status"] == "ready_for_review"
    assert intake["scene_count"] == 2
    assert intake["data_posture"]["images_uploaded"] is False
    assert intake["data_posture"]["user_api_key_required"] is False
    assert (
        intake["data_posture"]["boundary_beyond_local_workspace"]
        == "Mparanza and OpenAI"
    )
    assert intake["voice"]["provider"] == "Mparanza"
    assert intake["voice"]["upstream_provider"] == "OpenAI"
    assert "No user API key" in review
    assert "Images and source-basis notes stay local" in review
    assert "Research pack, figure 1" in review
    assert not (run_dir / "narration_approval.json").exists()
    assert not (run_dir / "mparanza_voice_request.json").exists()
    assert not (run_dir / "research_video.mp4").exists()


def test_prepare_run_rejects_scene_without_source_basis(tmp_path: Path) -> None:
    renderer = _load_renderer()
    first = _write_image(tmp_path / "first.png", (10, 20, 30))
    second = _write_image(tmp_path / "second.png", (40, 50, 60))
    plan = _scene_plan(first, second)
    plan["scenes"][0]["source_basis"] = []
    plan_path = tmp_path / "scene-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(ValueError, match="requires 1-12 source_basis"):
        renderer.prepare_run(plan_path, tmp_path / "run")


def test_prepare_run_accepts_italian_and_records_visible_voice_disclosure(
    tmp_path: Path,
) -> None:
    _renderer, run_dir, _first, _second = _prepare_fixture(tmp_path, language="it")

    intake = json.loads((run_dir / "run_intake.json").read_text(encoding="utf-8"))
    narration = (run_dir / "narration_script.md").read_text(encoding="utf-8")
    review = (run_dir / "review_packet.md").read_text(encoding="utf-8")

    assert intake["language"] == "it"
    assert intake["voice"]["disclosure"] == "Voce generata dall'IA"
    assert intake["voice"]["disclosure_placement"] == "visible footer on every scene"
    assert "Narration language: Italian (`it`)" in narration
    assert "Voce generata dall'IA" in narration
    assert "Voce generata dall'IA" in review


def test_prepare_run_rejects_unsupported_narration_language(tmp_path: Path) -> None:
    renderer = _load_renderer()
    first = _write_image(tmp_path / "first.png", (10, 20, 30))
    second = _write_image(tmp_path / "second.png", (40, 50, 60))
    plan = _scene_plan(first, second, language="pt")
    plan_path = tmp_path / "scene-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(ValueError, match="language must be one of: de, en, es, fr, it"):
        renderer.prepare_run(plan_path, tmp_path / "run")


def test_approval_requires_explicit_user_confirmation(tmp_path: Path) -> None:
    renderer, run_dir, _first, _second = _prepare_fixture(tmp_path)

    with pytest.raises(ValueError, match="requires explicit --confirmed-by-user"):
        renderer.approve_run(run_dir)

    assert not (run_dir / "narration_approval.json").exists()


def test_renderer_rejects_approval_without_user_confirmation_evidence(
    tmp_path: Path,
) -> None:
    renderer, run_dir, _first, _second = _prepare_fixture(tmp_path)
    renderer.approve_run(run_dir, confirmed_by_user=True)
    approval_path = run_dir / "narration_approval.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval.pop("confirmed_by_user")
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    intake = json.loads((run_dir / "run_intake.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="lacks explicit user-confirmation evidence"):
        renderer._verify_approval(run_dir, intake)


def test_approval_fails_when_visual_bytes_change(tmp_path: Path) -> None:
    renderer, run_dir, first, _second = _prepare_fixture(tmp_path)
    _write_image(first, (255, 0, 0))

    with pytest.raises(ValueError, match="Visual changed after preparation"):
        renderer.approve_run(run_dir, confirmed_by_user=True)


def test_approval_writes_minimal_hash_bound_hosted_voice_request(
    tmp_path: Path,
) -> None:
    renderer, run_dir, _first, _second = _prepare_fixture(tmp_path, language="it")

    approval = renderer.approve_run(run_dir, confirmed_by_user=True)
    request = json.loads(
        (run_dir / "mparanza_voice_request.json").read_text(encoding="utf-8")
    )

    assert request["approval"] == {
        "approval_sha256": renderer._json_sha256(approval),
        "confirmed_by_user": True,
    }
    assert set(request) == {
        "schema_version",
        "workflow",
        "language",
        "scene_plan_sha256",
        "approval",
        "scenes",
    }
    assert request["scenes"][0] == {
        "id": "market-context",
        "narration": "The supplied figure shows the reviewed market context.",
    }
    assert "image" not in json.dumps(request)
    assert "source_basis" not in json.dumps(request)


def test_attach_hosted_voice_requires_mparanza_source(tmp_path: Path) -> None:
    renderer, run_dir, _first, _second = _prepare_fixture(tmp_path)
    renderer.approve_run(run_dir, confirmed_by_user=True)

    with pytest.raises(ValueError, match="does not match: source"):
        _attach_fixture_voice(
            renderer,
            run_dir,
            tmp_path,
            source="third_party_tts",
        )


def test_attach_voice_cli_records_hosted_manifest(tmp_path: Path) -> None:
    renderer, run_dir, _first, _second = _prepare_fixture(tmp_path)
    renderer.approve_run(run_dir, confirmed_by_user=True)
    bundle_path = _write_fixture_voice_bundle(renderer, run_dir, tmp_path)

    result = renderer.main(
        [
            "attach-voice",
            "--run-dir",
            str(run_dir),
            "--voice-bundle",
            str(bundle_path),
        ]
    )

    attached = json.loads(
        (run_dir / "hosted_voice_manifest.json").read_text(encoding="utf-8")
    )
    assert result == 0
    assert attached["source"] == "mparanza_hosted_openai_voice"
    assert attached["provider"] == "Mparanza"
    assert attached["upstream_provider"] == "OpenAI"
    assert len(attached["scenes"]) == 2


def test_render_requires_attached_hosted_voice_artifacts(tmp_path: Path) -> None:
    renderer, run_dir, _first, _second = _prepare_fixture(tmp_path)
    renderer.approve_run(run_dir, confirmed_by_user=True)

    with pytest.raises(ValueError, match="Hosted voice artifacts are missing"):
        renderer.render_run(run_dir)


def test_renderer_rejects_changed_hosted_voice_bytes(tmp_path: Path) -> None:
    renderer, run_dir, _first, _second = _prepare_fixture(tmp_path)
    renderer.approve_run(run_dir, confirmed_by_user=True)
    _attach_fixture_voice(renderer, run_dir, tmp_path)
    staged_audio = run_dir / "hosted_voice" / "01-market-context.wav"
    staged_audio.write_bytes(staged_audio.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="audio changed after attachment"):
        renderer.render_run(run_dir)


def test_render_run_builds_decodable_hosted_voice_artifacts_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("imageio_ffmpeg")
    renderer, run_dir, _first, _second = _prepare_fixture(
        tmp_path,
        layered=True,
        language="it",
    )
    renderer.approve_run(run_dir, confirmed_by_user=True)
    _manifest_path, attached = _attach_fixture_voice(
        renderer,
        run_dir,
        tmp_path,
    )
    monkeypatch.setattr(renderer, "FRAME_WIDTH", 320)
    monkeypatch.setattr(renderer, "FRAME_HEIGHT", 180)
    monkeypatch.setattr(renderer, "FRAME_RATE", 10)
    monkeypatch.setattr(renderer, "LEAD_SECONDS", 0.1)
    monkeypatch.setattr(renderer, "TAIL_SECONDS", 0.1)
    monkeypatch.setattr(renderer, "INTER_SCENE_PAUSE_SECONDS", 0.2)
    monkeypatch.setattr(renderer, "TRANSITION_SECONDS", 0.1)

    report = renderer.render_run(run_dir)
    artifacts = json.loads(
        (run_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )

    assert report["status"] == "ready_for_review"
    assert report["media"]["decoded_without_error"] is True
    assert report["requires_voice_content_review"] is True
    assert report["language"] == "it"
    assert report["voice"] == {
        "provider": "Mparanza",
        "upstream_provider": "OpenAI",
        "source": "mparanza_hosted_openai_voice",
        "model": "gpt-4o-mini-tts",
        "name": "marin",
        "disclosure": "Voce generata dall'IA",
        "disclosure_placement": "visible footer on every scene",
    }
    assert artifacts["review_status"] == "pending_semantic_and_visual_review"
    assert any("spoken words" in caveat for caveat in artifacts["caveats"])
    assert artifacts["voice_disclosure"] == {
        "text": "Voce generata dall'IA",
        "placement": "visible footer on every scene",
    }
    assert {item["path"] for item in artifacts["outputs"]} == {
        "captions.vtt",
        "hosted_voice/01-market-context.wav",
        "hosted_voice/02-decision-implication.wav",
        "hosted_voice_manifest.json",
        "mparanza_voice_request.json",
        "narration_approval.json",
        "narration_script.md",
        "poster.jpg",
        "render_report.json",
        "research_video.mp4",
        "review_packet.md",
        "run_intake.json",
        "scene_plan.json",
    }
    assert (run_dir / "research_video.mp4").stat().st_size > 0
    assert attached["source"] == "mparanza_hosted_openai_voice"
    assert (run_dir / "captions.vtt").read_text(encoding="utf-8").startswith("WEBVTT")
    with Image.open(run_dir / "poster.jpg") as poster:
        bottom_band = poster.crop(
            (0, round(poster.height * 0.82), poster.width, poster.height)
        )
        navy_pixels = sum(
            1
            for red, green, blue in bottom_band.getdata()
            if blue > red * 1.35 and blue > green * 1.1
        )
        bottom_edge = poster.crop(
            (
                round(poster.width * 0.5),
                round(poster.height * 0.96),
                poster.width,
                poster.height,
            )
        )
        navy_edge_pixels = sum(
            1
            for red, green, blue in bottom_edge.getdata()
            if blue > red * 1.35 and blue > green * 1.1
        )
    assert navy_pixels > 10
    assert navy_edge_pixels < 3

    (run_dir / "poster.jpg").unlink()
    with pytest.raises(ValueError, match="missing or changed: poster.jpg"):
        renderer.render_run(run_dir)


def test_skill_and_router_expose_the_research_video_contract() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())
    catalog = (
        CLARA_ROOT / "skills" / "clara" / "references" / "workflow-catalog.md"
    ).read_text(encoding="utf-8")
    fixtures = json.loads(
        (CLARA_ROOT / "evals" / "trigger_fixtures.json").read_text(encoding="utf-8")
    )
    routed = {
        item["id"]: item
        for item in fixtures["should_trigger"]
        if item.get("expected_skill") == "clara:research-video"
    }

    script_source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "authenticated Mparanza Research Video voice page" in normalized_skill
    assert "No user API key" in skill
    assert "OPENAI_API_KEY" not in script_source
    assert "api.openai.com" not in script_source
    assert "Flat images do not become true parallax" in normalized_skill
    assert "## Vera handoff boundary" in skill
    assert "--confirmed-by-user" in skill
    assert "localized disclosure" in normalized_skill
    assert '"language": {"enum": ["de", "en", "es", "fr", "it"]}' in (
        SKILL_ROOT / "references" / "scene-plan.schema.json"
    ).read_text(encoding="utf-8")
    voice_schema = (
        SKILL_ROOT / "references" / "hosted-voice-bundle.schema.json"
    ).read_text(encoding="utf-8")
    assert '"source": {"const": "mparanza_hosted_openai_voice"}' in voice_schema
    assert "https://mparanza.com/case-notes/research-video/voice" in skill
    assert "- `research-video`:" in catalog
    assert set(routed) == {"narrated-research-video"}
