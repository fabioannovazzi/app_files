from __future__ import annotations

import pytest

from src.slides.launch_report_ast import validate_launch_report_payload


def test_validate_launch_report_payload_accepts_rich_valid_payload() -> None:
    payload = {
        "deckName": "Ulta launch experiment",
        "slides": [
            {
                "slideId": "s01",
                "title": "Launch thesis",
                "body": [
                    "Launches are the cleanest place to test whether signal survives audit."
                ],
                "footerText": "Ulta new-arrivals scrape",
            },
            {
                "slideId": "s02",
                "title": "What survived vs what failed",
                "comparisonColumns": [
                    {"title": "Survived", "items": ["Hydrating over-indexes"]},
                    {"title": "Failed", "items": ["Refillable collapsed after audit"]},
                ],
                "calloutBody": "The signal is modest but inspectable.",
            },
            {
                "slideId": "s03",
                "title": "Included launches",
                "layoutVariant": "text_visual_bottom",
                "nativeVisual": {
                    "kind": "launch_product_tiles",
                    "tiles": [
                        {
                            "brand": "Brand A",
                            "product": "Matte Lip Color",
                            "body": "Counterexample",
                            "tags": ["matte"],
                        },
                        {
                            "brand": "Brand B",
                            "product": "Hydrating Lip Color",
                            "body": "Care-led",
                            "tags": ["hydrating"],
                        },
                    ],
                },
            },
        ],
    }

    validated = validate_launch_report_payload(payload)

    assert validated["deckName"] == "Ulta launch experiment"
    assert len(validated["slides"]) == 3


def test_validate_launch_report_payload_rejects_unsupported_layout_variant() -> None:
    payload = {
        "slides": [
            {
                "title": "Launch thesis",
                "layoutVariant": "cinematic_freeform",
            }
        ]
    }

    with pytest.raises(ValueError, match="unsupported layoutVariant"):
        validate_launch_report_payload(payload)


def test_validate_launch_report_payload_rejects_absolute_visual_path() -> None:
    payload = {
        "slides": [
            {
                "title": "Included launches",
                "visualPath": "/tmp/launches.png",
            }
        ]
    }

    with pytest.raises(ValueError, match="must be relative"):
        validate_launch_report_payload(payload)


def test_validate_launch_report_payload_rejects_incomplete_comparison_columns() -> None:
    payload = {
        "slides": [
            {
                "title": "What survived vs what failed",
                "comparisonColumns": [
                    {"title": "Survived", "items": ["Hydrating over-indexes"]}
                ],
            }
        ]
    }

    with pytest.raises(ValueError, match="at least two columns"):
        validate_launch_report_payload(payload)


def test_validate_launch_report_payload_rejects_cards_without_titles() -> None:
    payload = {
        "slides": [
            {
                "title": "Included launches",
                "nativeVisual": {
                    "kind": "cards_row",
                    "cards": [{"body": "Counterexample", "items": ["matte"]}],
                },
            }
        ]
    }

    with pytest.raises(ValueError, match="missing a title"):
        validate_launch_report_payload(payload)


def test_validate_launch_report_payload_rejects_product_tiles_without_product() -> None:
    payload = {
        "slides": [
            {
                "title": "Included launches",
                "nativeVisual": {
                    "kind": "launch_product_tiles",
                    "tiles": [
                        {"brand": "Brand B", "body": "Care-led", "tags": ["hydrating"]},
                        {
                            "brand": "Brand A",
                            "product": "Matte Lip Color",
                            "body": "Counterexample",
                        },
                    ],
                },
            }
        ]
    }

    with pytest.raises(ValueError, match="missing a product/title"):
        validate_launch_report_payload(payload)
