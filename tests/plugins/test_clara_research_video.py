from __future__ import annotations

import importlib.util
import json
import math
import struct
import sys
import wave
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


def _scene_plan(first: Path, second: Path) -> dict[str, Any]:
    """Return the smallest complete public scene-plan contract."""

    return {
        "schema_version": 1,
        "title": "Reviewed market finding",
        "language": "en",
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
    tmp_path: Path, *, layered: bool = False
) -> tuple[Any, Path, Path, Path]:
    """Prepare one two-scene run and return its paths."""

    renderer = _load_renderer()
    first = _write_image(tmp_path / "first.png", (0, 32, 96))
    second = _write_image(tmp_path / "second.png", (0, 160, 210))
    plan = _scene_plan(first, second)
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


def _write_test_voice(path: Path, _text: str) -> None:
    """Write a short PCM tone in place of the external speech call."""

    frame_rate = 16_000
    duration_seconds = 0.35
    frame_count = round(frame_rate * duration_seconds)
    samples = b"".join(
        struct.pack(
            "<h",
            round(1200 * math.sin(2 * math.pi * 220 * index / frame_rate)),
        )
        for index in range(frame_count)
    )
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(frame_rate)
        output.writeframes(samples)


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
    assert renderer.OPENAI_TTS_MODEL not in script
    assert "Research pack, figure 1" in review
    assert not (run_dir / "narration_approval.json").exists()
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


def test_approval_fails_when_visual_bytes_change(tmp_path: Path) -> None:
    renderer, run_dir, first, _second = _prepare_fixture(tmp_path)
    _write_image(first, (255, 0, 0))

    with pytest.raises(ValueError, match="Visual changed after preparation"):
        renderer.approve_run(run_dir)


def test_speech_payload_uses_approved_english_voice_policy() -> None:
    renderer = _load_renderer()

    payload = renderer._speech_payload("Approved narration.")

    assert payload == {
        "model": "gpt-4o-mini-tts",
        "voice": "cedar",
        "input": "Approved narration.",
        "instructions": renderer.TTS_INSTRUCTIONS,
        "response_format": "wav",
    }


def test_render_run_builds_decodable_review_artifacts_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("imageio_ffmpeg")
    renderer, run_dir, _first, _second = _prepare_fixture(tmp_path, layered=True)
    renderer.approve_run(run_dir)
    monkeypatch.setattr(renderer, "FRAME_WIDTH", 320)
    monkeypatch.setattr(renderer, "FRAME_HEIGHT", 180)
    monkeypatch.setattr(renderer, "FRAME_RATE", 10)
    monkeypatch.setattr(renderer, "LEAD_SECONDS", 0.1)
    monkeypatch.setattr(renderer, "TAIL_SECONDS", 0.1)
    monkeypatch.setattr(renderer, "INTER_SCENE_PAUSE_SECONDS", 0.2)
    monkeypatch.setattr(renderer, "TRANSITION_SECONDS", 0.1)

    def synthesize(_api_key: str, text: str, output_path: Path) -> None:
        _write_test_voice(output_path, text)

    monkeypatch.setattr(renderer, "_synthesize_scene", synthesize)

    report = renderer.render_run(run_dir, api_key="test-key-with-sufficient-length")
    artifacts = json.loads(
        (run_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )

    assert report["status"] == "ready_for_review"
    assert report["media"]["decoded_without_error"] is True
    assert report["voice"] == {
        "provider": "OpenAI",
        "model": "gpt-4o-mini-tts",
        "name": "cedar",
    }
    assert artifacts["review_status"] == "pending_semantic_and_visual_review"
    assert (run_dir / "research_video.mp4").stat().st_size > 0
    assert (run_dir / "captions.vtt").read_text(encoding="utf-8").startswith("WEBVTT")

    (run_dir / "poster.jpg").unlink()
    with pytest.raises(ValueError, match="missing or changed: poster.jpg"):
        renderer.render_run(run_dir, api_key="test-key-with-sufficient-length")


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

    assert "OpenAI `gpt-4o-mini-tts`, voice `cedar`" in normalized_skill
    assert "Flat images do not become true parallax" in normalized_skill
    assert "- `research-video`:" in catalog
    assert set(routed) == {"narrated-research-video"}
