from __future__ import annotations

from modules.pdp.deck_layout_grammar import (
    DECK_LAYOUT_GRAMMAR_VERSION,
    apply_layout_grammar_to_deck,
    select_slide_layout,
)


def test_select_slide_layout_returns_hero_thesis_for_visual_lead_slide() -> None:
    slide = {
        "kind": "text",
        "title": "Testing whether launch attributes are signal, not noise",
        "bullets": [
            "Launches are the best stress test for attribute value.",
            "The point is to see what survives after audit.",
        ],
        "visual": {
            "kind": "product_collage",
            "asset_ids": ["img_1", "img_2", "img_3"],
        },
    }

    decision = select_slide_layout(slide)

    assert decision.family == "hero_thesis"
    assert decision.split_recommended is False


def test_select_slide_layout_returns_cards_3up_for_three_cards() -> None:
    slide = {
        "title": "Why launches are the best place to test attribute value",
        "cards": [
            {"title": "Best-case use case", "body": "Attributes are easiest to read on launches."},
            {"title": "Cleaner unit", "body": "Each launch is counted once."},
            {"title": "Still hard enough", "body": "Small cohorts are easy to over-read."},
        ],
    }

    decision = select_slide_layout(slide)

    assert decision.family == "cards_3up"


def test_select_slide_layout_prefers_chart_focus_for_light_chart_slide() -> None:
    slide = {
        "title": "Hydrating launches over-index",
        "bullets": ["Hydrating launches over-index versus the older base."],
        "chart_id": "chart-01",
    }

    decision = select_slide_layout(slide)

    assert decision.family == "chart_focus"
    assert decision.split_recommended is False


def test_select_slide_layout_flags_dense_chart_sidebar_for_split() -> None:
    slide = {
        "title": "After audit, one clear signal remains",
        "subtitle": "Attribute mix",
        "bullets": [
            "Hydrating launches over-index versus the older base.",
            "Long-wear also over-indexes.",
            "Matte finish remains common.",
            "Full coverage does not separate the cohort.",
            "The result is directionally useful but small-sample.",
        ],
        "chart_id": "chart-02",
    }

    decision = select_slide_layout(slide)

    assert decision.family == "chart_sidebar"
    assert decision.split_recommended is True


def test_apply_layout_grammar_to_deck_enriches_each_slide() -> None:
    payload = {
        "title": "Lipstick launch signal test",
        "slides": [
            {
                "kind": "summary",
                "title": "Executive summary",
                "bullets": [
                    "Launches are the best stress test for attribute value.",
                    "The audit removed false positives.",
                    "The surviving signal is modest but real.",
                ],
            },
            {
                "title": "Hydrating launches over-index",
                "chart_id": "chart-01",
                "bullets": ["Hydrating launches over-index versus the older base."],
            },
        ],
    }

    enriched = apply_layout_grammar_to_deck(payload)

    assert enriched["layout_grammar_version"] == DECK_LAYOUT_GRAMMAR_VERSION
    assert enriched["slides"][0]["layout_family"] == "summary_bullets"
    assert enriched["slides"][1]["layout_family"] == "chart_focus"
    assert enriched["slides"][1]["layout_reasons"] == [
        "Chart is primary and supporting copy is light."
    ]
