from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from src.slides import layout_service
from src.slides.layout_service import (
    SlideLayoutOpenAIError,
    apply_semantic_layout_corrections_to_payload,
)
from src.slides.models import Deck, Slide


def test_apply_semantic_layout_corrections_to_payload_relabels_and_groups_blocks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    deck = Deck(
        deck_id="deckSemanticLayout",
        slides=[
            Slide(
                id="slide0.html",
                title_html="Popolazione totale",
                body_html="<img src='/slides/deck/deckSemanticLayout/assets/slide.png' />",
            )
        ],
    )
    deck_path = tmp_path / deck.deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 700), "white").save(assets_path / "slide.png")

    layout_payload = {
        "deck_id": deck.deck_id,
        "lang": "ita",
        "slides": [
            {
                "slide_id": "slide0.html",
                "slide_number": 1,
                "page_number": 1,
                "asset_path": "assets/slide.png",
                "blocks": [
                    {
                        "block_id": "block-title",
                        "type": "unknown",
                        "bbox": {"x": 40.0, "y": 30.0, "w": 520.0, "h": 110.0},
                    },
                    {
                        "block_id": "block-metric",
                        "type": "unknown",
                        "bbox": {"x": 700.0, "y": 120.0, "w": 220.0, "h": 170.0},
                    },
                    {
                        "block_id": "block-label",
                        "type": "text",
                        "bbox": {"x": 705.0, "y": 320.0, "w": 180.0, "h": 40.0},
                    },
                    {
                        "block_id": "block-body",
                        "type": "list",
                        "bbox": {"x": 60.0, "y": 220.0, "w": 420.0, "h": 60.0},
                    },
                ],
                "title_text": "",
                "bullet_texts": [],
                "figure_regions": [],
            }
        ],
    }

    monkeypatch.setattr(
        "src.slides.layout_service._build_local_llm_wrapper", lambda: object()
    )
    monkeypatch.setattr(
        "src.slides.layout_service.run_step_json",
        lambda *args, **kwargs: [
            {
                "blocks": [
                    {
                        "blockId": "block-title",
                        "type": "title",
                        "readingOrder": 0,
                    },
                    {
                        "blockId": "block-body",
                        "type": "bullet_item",
                        "listLevel": 0,
                        "readingOrder": 1,
                    },
                    {
                        "blockId": "block-metric",
                        "type": "metric",
                        "groupId": "exhibit-1",
                        "renderMode": "group_as_image",
                        "readingOrder": 2,
                    },
                    {
                        "blockId": "block-label",
                        "type": "exhibit_label",
                        "groupId": "exhibit-1",
                        "renderMode": "group_as_image",
                        "readingOrder": 3,
                    },
                ]
            }
        ],
    )

    corrected = apply_semantic_layout_corrections_to_payload(
        deck,
        deck_path,
        layout_payload,
        lang="ita",
    )

    slide_payload = corrected["slides"][0]
    blocks = slide_payload["blocks"]
    assert [block["type"] for block in blocks] == [
        "title",
        "bullet_item",
        "metric",
        "exhibit_label",
    ]
    assert blocks[0]["detected_type"] == "unknown"
    assert blocks[2]["group_id"] == "exhibit-1"
    assert blocks[2]["render_mode"] == "group_as_image"
    assert blocks[3]["group_id"] == "exhibit-1"
    assert slide_payload["figure_regions"] == [
        {"x": 700.0, "y": 120.0, "w": 220.0, "h": 240.0}
    ]


def test_apply_semantic_layout_corrections_to_payload_fails_on_openai_failures(
    monkeypatch,
    tmp_path: Path,
) -> None:
    deck = Deck(
        deck_id="deckSemanticLayoutFailure",
        slides=[
            Slide(
                id="slide0.html",
                title_html="Popolazione totale",
                body_html="<img src='/slides/deck/deckSemanticLayoutFailure/assets/slide.png' />",
            )
        ],
    )
    deck_path = tmp_path / deck.deck_id
    assets_path = deck_path / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 700), "white").save(assets_path / "slide.png")

    layout_payload = {
        "deck_id": deck.deck_id,
        "lang": "ita",
        "slides": [
            {
                "slide_id": "slide0.html",
                "slide_number": 1,
                "page_number": 1,
                "asset_path": "assets/slide.png",
                "blocks": [
                    {
                        "block_id": "block-title",
                        "type": "title",
                        "text": "Popolazione totale",
                        "bbox": {"x": 40.0, "y": 30.0, "w": 520.0, "h": 110.0},
                    },
                    {
                        "block_id": "block-body",
                        "type": "bullet_item",
                        "text": "Recent launches grew",
                        "bbox": {"x": 60.0, "y": 220.0, "w": 420.0, "h": 60.0},
                    },
                ],
                "title_text": "Popolazione totale",
                "bullet_texts": ["Recent launches grew"],
                "figure_regions": [],
            }
        ],
    }

    class SemanticCorrectionConnectionError(layout_service.OpenAIError):
        pass

    monkeypatch.setattr(
        "src.slides.layout_service._build_local_llm_wrapper", lambda: object()
    )

    def _raise_openai_error(*args, **kwargs):
        raise SemanticCorrectionConnectionError("connection failed")

    monkeypatch.setattr("src.slides.layout_service.run_step_json", _raise_openai_error)

    with pytest.raises(
        SlideLayoutOpenAIError,
        match="OpenAI call failed during slide layout semantic correction",
    ):
        apply_semantic_layout_corrections_to_payload(
            deck,
            deck_path,
            layout_payload,
            lang="ita",
        )
