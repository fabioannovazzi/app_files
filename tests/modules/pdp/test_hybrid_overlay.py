from __future__ import annotations

import polars as pl

from modules.pdp.hybrid_overlay import (
    annotate_bronzer_blush_hybrid,
    annotate_market_hybrid_claims,
)


def test_annotate_bronzer_blush_hybrid_marks_explicit_parent_claims() -> None:
    frame = pl.DataFrame(
        [
            {
                "category_key": "bronzer",
                "product_name": "Beach Blonzer Duo",
                "description": "A blush + bronzer stick.",
            },
            {
                "category_key": "bronzer",
                "product_name": "Matte Bronzer",
                "description": "Warm matte finish.",
            },
            {
                "category_key": "blush",
                "product_name": "Blush Bronzer Duo",
                "description": "Dual shade compact.",
            },
        ]
    )

    out = annotate_bronzer_blush_hybrid(frame, record_type="parent")
    rows = out.select(
        [
            "also_blush",
            "brand_claims_blush_hybrid",
            "inferred_blush_hybrid",
            "also_blush_source",
            "also_blush_secondary_category",
            "also_blush_evidence",
        ]
    ).to_dicts()

    assert rows[0]["also_blush"] is True
    assert rows[0]["brand_claims_blush_hybrid"] is True
    assert rows[0]["inferred_blush_hybrid"] is False
    assert rows[0]["also_blush_source"] == "brand_claim"
    assert rows[0]["also_blush_secondary_category"] == "blush"
    assert isinstance(rows[0]["also_blush_evidence"], str)
    assert rows[0]["also_blush_evidence"]

    assert rows[1]["also_blush"] is False
    assert rows[2]["also_blush"] is False
    assert rows[2]["also_blush_evidence"] is None


def test_annotate_bronzer_blush_hybrid_uses_variant_fields() -> None:
    frame = pl.DataFrame(
        [
            {
                "category_label": "Bronzer",
                "variant_description": "2 in 1 blush and bronzer stick",
            }
        ]
    )

    out = annotate_bronzer_blush_hybrid(frame, record_type="variant")
    row = out.select(
        ["also_blush", "brand_claims_blush_hybrid", "also_blush_evidence"]
    ).row(0)

    assert row[0] is True
    assert row[1] is True
    assert isinstance(row[2], str)
    assert row[2]


def test_annotate_market_hybrid_claims_marks_supported_secondary_categories() -> None:
    frame = pl.DataFrame(
        [
            {
                "category_key": "blush",
                "product_name": "Ambient Blushlighter",
                "description": "A blush + highlighter duo.",
            },
            {
                "category_key": "bronzer",
                "product_name": "Sun Bronzer + Highlighter",
                "description": "Two-tone bronzer/highlighter compact.",
            },
            {
                "category_key": "lipstick",
                "product_name": "Lip and Cheek Tint",
                "description": "A lip and cheek color stick.",
            },
            {
                "category_key": "eyeshadow",
                "product_name": "Velvet Eyeshadow",
                "description": "Can be used as an eyeliner when wet.",
            },
        ]
    )

    out = annotate_market_hybrid_claims(frame, record_type="parent").select(
        [
            "also_highlighter",
            "also_cheek",
            "also_eyeliner",
            "also_highlighter_evidence",
            "also_cheek_evidence",
            "also_eyeliner_evidence",
        ]
    )
    rows = out.to_dicts()

    assert rows[0]["also_highlighter"] is True
    assert isinstance(rows[0]["also_highlighter_evidence"], str)
    assert rows[0]["also_highlighter_evidence"]

    assert rows[1]["also_highlighter"] is True
    assert isinstance(rows[1]["also_highlighter_evidence"], str)
    assert rows[1]["also_highlighter_evidence"]

    assert rows[2]["also_cheek"] is True
    assert isinstance(rows[2]["also_cheek_evidence"], str)
    assert rows[2]["also_cheek_evidence"]

    assert rows[3]["also_eyeliner"] is True
    assert isinstance(rows[3]["also_eyeliner_evidence"], str)
    assert rows[3]["also_eyeliner_evidence"]


def test_annotate_bronzer_blush_hybrid_adds_columns_for_empty_frames() -> None:
    frame = pl.DataFrame()
    out = annotate_bronzer_blush_hybrid(frame, record_type="parent")
    assert {
        "brand_claims_blush_hybrid",
        "inferred_blush_hybrid",
        "also_blush",
        "also_blush_secondary_category",
        "also_blush_source",
        "also_blush_evidence",
        "brand_claims_highlighter_hybrid",
        "also_highlighter",
        "also_cheek",
        "also_eyeliner",
    }.issubset(set(out.columns))
