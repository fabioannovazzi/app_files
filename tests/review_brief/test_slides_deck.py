from __future__ import annotations

from src.review_brief.slides_deck import (
    build_review_brief_deck,
    build_review_brief_deck_spec,
)


def test_build_review_brief_deck_creates_summary_and_chart_slides() -> None:
    payload = {
        "category": "Blush",
        "retailers": ["ulta", "sephora"],
        "prompt_style": "uniform",
        "start_month": "2024-01-01",
        "end_month": "2024-12-01",
        "charts": [
            {
                "chart_id": "chart_demo_1",
                "title": "Category mix by form",
                "subtitle": "Monthly values",
                "normalization": "share_of_category_total",
            },
            {
                "chart_id": "chart_demo_2",
                "title": "Brand share by retailer",
                "subtitle": "Trailing twelve months",
                "normalization": "share_of_category_total",
            },
        ],
        "interpretations": {
            "chart_demo_1": {
                "chart_id": "chart_demo_1",
                "headline": "Cream outpaces powder",
                "bullets": ["Cream gains 12 pp.", "Powder loses 7 pp."],
                "relevance": 88,
            },
            "chart_demo_2": {
                "chart_id": "chart_demo_2",
                "headline": "Retailer mix stays fragmented",
                "bullets": ["No single brand dominates both retailers."],
                "relevance": 75,
            },
        },
        "selected": ["chart_demo_1", "chart_demo_2"],
        "narrative": {
            "executive_narrative": "The category is shifting toward cream formats.",
            "key_takeaways": ["Cream is the main winner.", "Powder is retreating."],
            "suggested_flow": [
                {"title": "Format mix shift", "chart_ids": ["chart_demo_1"]}
            ],
        },
        "requested_scope": {},
    }

    spec = build_review_brief_deck_spec(payload)
    deck = build_review_brief_deck(
        "deckUniform",
        spec,
        chart_image_urls={
            "chart_demo_1": "/slides/deck/deckUniform/assets/chart_demo_1.png",
            "chart_demo_2": "/slides/deck/deckUniform/assets/chart_demo_2.png",
        },
    )

    assert deck.prompt_style == "uniform"
    assert len(deck.slides) == 3
    assert deck.slides[0].title_html == "Blush review: ulta, sephora"
    assert "Cream is the main winner." in deck.slides[0].body_html
    assert deck.slides[1].title_html == "Format mix shift"
    assert "Cream outpaces powder" in deck.slides[1].body_html
    assert (
        "/slides/deck/deckUniform/assets/chart_demo_1.png" in deck.slides[1].body_html
    )
