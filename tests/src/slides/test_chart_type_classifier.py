from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

from src.slides.chart_type_classifier import classify_deck_chart_regions
from src.slides.models import Deck, Slide


def _build_deck_with_image(tmp_path: Path) -> tuple[Deck, Path]:
    deck_id = "deck-test"
    deck_path = tmp_path / deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)
    image_path = assets_path / "slide-1.png"
    Image.new("RGB", (200, 120), color=(240, 240, 240)).save(image_path, form="PNG")
    slide = Slide(
        id="slide-1",
        title_html="",
        body_html=f'<img src="/slides/deck/{deck_id}/assets/slide-1.png" />',
        notes_html="",
        source_html="",
        full_html="",
    )
    deck = Deck(deck_id=deck_id, prompt_style="uniform", slides=[slide], sections=[])
    return deck, deck_path


def test_classify_deck_chart_regions_runs_batch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deck, deck_path = _build_deck_with_image(tmp_path)
    payload = {
        "deck_id": deck.deck_id,
        "lang": "eng",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "ocr_text": "Sales in % by form",
                "title_text": "Sales in % by form",
                "figure_regions": [{"x": 20, "y": 20, "w": 120, "h": 80}],
            }
        ],
    }
    captured: dict[str, object] = {}

    def _fake_should_use_batch(step: str) -> bool:
        captured["step"] = step
        return True

    def _fake_run_step_json(
        llm_wrapper, step, system_prompt, prompts, **kwargs
    ):  # noqa: ANN001
        prompts_list = list(prompts)
        captured["called_step"] = step
        captured["prompts"] = prompts_list
        return [{"chartType": "area", "confidence": 0.88}]

    monkeypatch.setattr(
        "src.slides.chart_type_classifier.should_use_batch",
        _fake_should_use_batch,
    )
    monkeypatch.setattr(
        "src.slides.chart_type_classifier.run_step_json",
        _fake_run_step_json,
    )

    result = classify_deck_chart_regions(
        object(),
        deck=deck,
        deck_path=deck_path,
        ocr_payload=payload,
    )

    assert captured["step"] == "slidesChartTypeQuery"
    assert captured["called_step"] == "slidesChartTypeQuery"
    prompts = captured["prompts"]
    assert isinstance(prompts, list)
    assert len(prompts) == 1
    user_content = prompts[0]["user_content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "input_text"
    assert user_content[1]["type"] == "input_image"
    assert str(user_content[1]["image_url"]).startswith("data:image/png;base64,")

    assert "slide-1" in result
    assert result["slide-1"][0]["chart_type"] == "area"
    assert result["slide-1"][0]["confidence"] == 0.88


def test_classify_deck_chart_regions_requires_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deck, deck_path = _build_deck_with_image(tmp_path)
    payload = {"deck_id": deck.deck_id, "lang": "eng", "slides": []}
    monkeypatch.setattr(
        "src.slides.chart_type_classifier.should_use_batch",
        lambda step: False,
    )

    with pytest.raises(RuntimeError, match="Batch mode is required"):
        classify_deck_chart_regions(
            object(),
            deck=deck,
            deck_path=deck_path,
            ocr_payload=payload,
        )
