from __future__ import annotations

import polars as pl

from modules.pdp.ulta_filter_reports import (
    build_brand_filter_comparison,
    compare_mapping_to_ulta,
    compute_double_matching_summary,
    summarize_brand_filter_comparison,
)


def test_compute_double_matching_summary_counts_multi_value_products() -> None:
    filter_df = pl.DataFrame(
        {
            "crawl_ts": ["t1", "t1", "t1", "t1"],
            "retailer": ["ulta", "ulta", "ulta", "ulta"],
            "category_key": ["lipstick", "lipstick", "lipstick", "lipstick"],
            "filter_family": ["finish", "finish", "finish", "finish"],
            "filter_value": ["matte", "high shine", "matte", "matte"],
            "source_surface": ["filter", "filter", "filter", "filter"],
            "pdp_url": ["u1", "u1", "u2", "u3"],
            "parent_product_id": ["p1", "p1", "p2", "p3"],
            "page": [1, 1, 1, 1],
            "position": [1, 2, 1, 1],
            "listing_url": ["l1", "l1", "l2", "l3"],
        }
    )

    summary = compute_double_matching_summary(filter_df)
    row = summary.to_dicts()[0]

    assert row["product_count"] == 3
    assert row["single_value_products"] == 2
    assert row["multi_value_products"] == 1
    assert row["max_values_per_product"] == 2


def test_build_brand_filter_comparison_and_summary() -> None:
    filter_df = pl.DataFrame(
        {
            "crawl_ts": ["t1", "t1", "t1"],
            "retailer": ["ulta", "ulta", "ulta"],
            "category_key": ["lipstick", "lipstick", "lip_gloss"],
            "filter_family": ["finish", "form", "form"],
            "filter_value": ["matte", "liquid", "gloss"],
            "source_surface": ["filter", "filter", "filter"],
            "pdp_url": ["u1", "u1", "u2"],
            "parent_product_id": ["p1", "p1", "p2"],
            "page": [1, 1, 1],
            "position": [1, 1, 1],
            "listing_url": ["l1", "l2", "l3"],
        }
    )
    parents_df = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "parent_product_id": ["p1", "p2"],
            "brand": ["KIKO Milano", "KIKO Milano"],
            "product_name": ["Product One", "Product Two"],
            "category_key": ["lipstick", "lip_gloss"],
            "pdp_url": ["u1", "u2"],
            "finish": ["matte", None],
            "form": ["liquid lipstick", "wand"],
            "product type": [None, "plumping gloss"],
            "coverage": [None, None],
            "benefits": [None, None],
            "key benefits": [None, None],
            "wear claims": [None, None],
            "water resistance": [None, None],
            "spf": [None, None],
            "skin type": [None, None],
            "color family": [None, None],
        }
    )

    comparison = build_brand_filter_comparison(
        filter_df=filter_df,
        parents_df=parents_df,
    )
    rows = {
        (row["parent_product_id"], row["filter_family"]): row
        for row in comparison.to_dicts()
    }

    assert rows[("p1", "finish")]["verdict"] == "exact_match"
    assert rows[("p1", "form")]["verdict"] == "partial_match"
    assert rows[("p2", "form")]["verdict"] == "mismatch"

    summary = summarize_brand_filter_comparison(comparison)
    assert summary.height >= 3


def test_compare_mapping_to_ulta_handles_missing_cases() -> None:
    assert (
        compare_mapping_to_ulta(
            filter_family="finish", our_value=None, ulta_values=["matte"]
        )
        == "our_missing"
    )
    assert (
        compare_mapping_to_ulta(
            filter_family="finish", our_value="matte", ulta_values=None
        )
        == "ulta_missing"
    )
    assert (
        compare_mapping_to_ulta(
            filter_family="unknown_family", our_value="x", ulta_values=["x"]
        )
        == "family_unmapped"
    )


def test_compare_mapping_to_ulta_normalizes_numeric_spf_against_ulta_buckets() -> None:
    assert (
        compare_mapping_to_ulta(
            filter_family="spf",
            our_value="30",
            ulta_values=["15 - 30", "30+"],
            category_key="tinted_moisturizer",
        )
        == "exact_match"
    )
    assert (
        compare_mapping_to_ulta(
            filter_family="spf",
            our_value="50",
            ulta_values=["50+", "above 30"],
            category_key="bb_cc_creams",
        )
        == "exact_match"
    )


def test_build_brand_filter_comparison_uses_bridge_attribute_labels() -> None:
    filter_df = pl.DataFrame(
        {
            "crawl_ts": ["t1", "t1"],
            "retailer": ["ulta", "ulta"],
            "category_key": ["foundation", "foundation"],
            "filter_family": ["skin type", "spf"],
            "filter_value": ["sensitive", "50+"],
            "source_surface": ["filter", "filter"],
            "pdp_url": ["u1", "u1"],
            "parent_product_id": ["p1", "p1"],
            "page": [1, 1],
            "position": [1, 1],
            "listing_url": ["l1", "l1"],
        }
    )
    parents_df = pl.DataFrame(
        {
            "retailer": ["ulta"],
            "parent_product_id": ["p1"],
            "brand": ["Brand"],
            "product_name": ["Foundation One"],
            "category_key": ["foundation"],
            "pdp_url": ["u1"],
            "suitable skin type": ["Sensitive"],
            "SPF": ["50+"],
        }
    )

    comparison = build_brand_filter_comparison(
        filter_df=filter_df,
        parents_df=parents_df,
    )
    rows = {
        (row["parent_product_id"], row["filter_family"]): row
        for row in comparison.to_dicts()
    }

    assert rows[("p1", "skin type")]["our_source_column"] == "suitable skin type"
    assert rows[("p1", "skin type")]["verdict"] == "exact_match"
    assert rows[("p1", "spf")]["our_source_column"] == "SPF"
    assert rows[("p1", "spf")]["verdict"] == "exact_match"
