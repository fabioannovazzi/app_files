from __future__ import annotations

from src.slides.analysis_payload import build_slide_analysis_payload

__all__: list[str] = []


def test_build_slide_analysis_payload_preserves_visual_ocr_fields() -> None:
    layout_payload = {
        "deckId": "deckVisualFields",
        "lang": "eng",
        "generatedAt": "2026-03-18T00:00:00+00:00",
        "slides": [
            {
                "slideId": "slide0.html",
                "slideNumber": 1,
                "pageNumber": 1,
                "assetPath": "assets/slide0.png",
                "blocks": [
                    {
                        "blockId": "figure-0",
                        "type": "figure",
                        "text": "",
                        "items": [],
                        "bbox": {"x": 20.0, "y": 40.0, "w": 300.0, "h": 180.0},
                    }
                ],
                "titleText": "",
                "bulletTexts": [],
                "figureRegions": [{"x": 20.0, "y": 40.0, "w": 300.0, "h": 180.0}],
            }
        ],
    }
    ocr_payload = {
        "deck_id": "deckVisualFields",
        "lang": "eng",
        "generated_at": "2026-03-18T00:00:00+00:00",
        "slides": [
            {
                "slide_id": "slide0.html",
                "slide_number": 1,
                "page_number": 1,
                "ocr_text": "",
                "lines": [],
                "blocks": [
                    {
                        "block_id": "figure-0",
                        "type": "figure",
                        "text": "",
                        "items": [],
                        "visual_text": "Phase 1: Italy",
                        "visual_items": ["Phase 1: Italy", "Pilot fleets"],
                        "visual_lines": [
                            {
                                "text": "Phase 1: Italy",
                                "bbox": {
                                    "x": 42.0,
                                    "y": 62.0,
                                    "w": 110.0,
                                    "h": 18.0,
                                },
                            }
                        ],
                        "bbox": {"x": 20.0, "y": 40.0, "w": 300.0, "h": 180.0},
                    }
                ],
                "title_text": "",
                "bullet_texts": [],
                "figure_regions": [{"x": 20.0, "y": 40.0, "w": 300.0, "h": 180.0}],
            }
        ],
    }

    merged = build_slide_analysis_payload(
        layout_payload,
        ocr_payload,
        deck_id="deckVisualFields",
        lang="eng",
    )

    assert merged is not None
    blocks = merged["slides"][0]["blocks"]
    assert blocks[0]["visualText"] == "Phase 1: Italy"
    assert blocks[0]["visualItems"] == ["Phase 1: Italy", "Pilot fleets"]
    assert blocks[0]["visualLines"][0]["text"] == "Phase 1: Italy"
