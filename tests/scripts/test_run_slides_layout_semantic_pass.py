from __future__ import annotations

import importlib
import sys

from src.slides.models import Deck, Slide


def _load_runner_module(monkeypatch):
    monkeypatch.setenv("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    sys.modules.pop("scripts.run_slides_layout_semantic_pass", None)
    return importlib.import_module("scripts.run_slides_layout_semantic_pass")


def test_select_unknown_slide_ids_uses_existing_layout_payload(monkeypatch) -> None:
    runner = _load_runner_module(monkeypatch)
    deck = Deck(
        deck_id="deckUnknownSelection",
        slides=[
            Slide(id="slide0.html", title_html="", body_html=""),
            Slide(id="slide1.html", title_html="", body_html=""),
            Slide(id="slide2.html", title_html="", body_html=""),
        ],
    )
    existing_layout = {
        "deckId": deck.deck_id,
        "lang": "ita",
        "slides": [
            {
                "slideId": "slide0.html",
                "blocks": [{"blockId": "block-0", "type": "title"}],
            },
            {
                "slideId": "slide1.html",
                "blocks": [{"blockId": "block-1", "type": "unknown"}],
            },
            {
                "slideId": "slide2.html",
                "blocks": [
                    {"blockId": "block-2", "type": "figure"},
                    {"blockId": "block-3", "type": "unknown"},
                ],
            },
        ],
    }

    selected = runner._resolve_selected_slide_ids(
        deck,
        existing_layout=existing_layout,
        page_numbers=[],
        slide_ids=[],
    )

    assert selected == ["slide1.html", "slide2.html"]


def test_merge_ocr_payload_keeps_order_and_updates_selected_slide(monkeypatch) -> None:
    runner = _load_runner_module(monkeypatch)
    deck = Deck(
        deck_id="deckMergeSubset",
        slides=[
            Slide(id="slide0.html", title_html="", body_html=""),
            Slide(id="slide1.html", title_html="", body_html=""),
        ],
    )
    existing_payload = {
        "deck_id": deck.deck_id,
        "lang": "ita",
        "ocr_strategy": "layout_guided_text_region_assignment_v7",
        "prompt_style": "uniform",
        "style_hint": {"title_to_body_ratio": 1.6},
        "generated_at": "2026-03-19T10:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide0.html",
                "slide_number": 1,
                "page_number": 1,
                "ocr_text": "Alpha",
                "lines": [],
                "blocks": [
                    {
                        "block_id": "block-0",
                        "type": "list",
                        "text": "Alpha",
                        "items": ["Alpha"],
                    }
                ],
                "title_text": "Alpha",
                "bullet_texts": ["Alpha"],
                "figure_regions": [],
            },
            {
                "slide_id": "slide1.html",
                "slide_number": 2,
                "page_number": 2,
                "ocr_text": "Old Beta",
                "lines": [],
                "blocks": [
                    {
                        "block_id": "block-1",
                        "type": "text",
                        "text": "Old Beta",
                        "items": [],
                    }
                ],
                "title_text": "",
                "bullet_texts": [],
                "figure_regions": [],
            },
        ],
    }
    updated_payload = {
        "deck_id": deck.deck_id,
        "lang": "ita",
        "ocr_strategy": "layout_guided_text_region_assignment_v7",
        "prompt_style": "uniform",
        "style_hint": {"title_to_body_ratio": 1.6},
        "generated_at": "2026-03-19T11:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide1.html",
                "slide_number": 2,
                "page_number": 2,
                "ocr_text": "New Beta",
                "lines": [],
                "blocks": [
                    {
                        "block_id": "block-1",
                        "type": "bullet_item",
                        "text": "New Beta",
                        "items": ["New Beta"],
                    }
                ],
                "title_text": "",
                "bullet_texts": ["New Beta"],
                "figure_regions": [],
            }
        ],
    }

    merged = runner._merge_ocr_payload(
        deck=deck,
        existing_payload=existing_payload,
        updated_payload=updated_payload,
        lang="ita",
    )

    assert [slide["slide_id"] for slide in merged["slides"]] == [
        "slide0.html",
        "slide1.html",
    ]
    assert merged["slides"][0]["ocr_text"] == "Alpha"
    assert merged["slides"][1]["ocr_text"] == "New Beta"
    assert merged["slides"][1]["blocks"][0]["type"] == "bullet_item"
    assert merged["prompt_style"] == "uniform"
