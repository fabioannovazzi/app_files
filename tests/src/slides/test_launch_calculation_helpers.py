from __future__ import annotations

import polars as pl

from src.slides.launch_calculation_helpers import calculate_package_frames


def test_calculate_package_frames_recomputes_launch_bundle_metrics() -> None:
    product_matrix = pl.DataFrame(
        [
            {
                "product_name": "A Clear Balm",
                "brand": "A",
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "resolved_color": "clear",
                "resolved_form": "balm",
                "pareto_bucket": "A",
            },
            {
                "product_name": "B Red Balm",
                "brand": "B",
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "resolved_color": "red",
                "resolved_form": "balm",
                "pareto_bucket": "A",
            },
            {
                "product_name": "C Clear Balm",
                "brand": "C",
                "listing_status": "rest",
                "top_seller_status": "other",
                "resolved_color": "clear",
                "resolved_form": "balm",
                "pareto_bucket": "B",
            },
            {
                "product_name": "D Clear Stick",
                "brand": "D",
                "listing_status": "rest",
                "top_seller_status": "other",
                "resolved_color": "clear",
                "resolved_form": "stick",
                "pareto_bucket": "C",
            },
        ]
    )
    frames = {
        "product_filter_matrix.csv": product_matrix,
        "top_seller_pairs.csv": pl.DataFrame(
            [
                {
                    "bundle_key": "color=clear + form=balm",
                    "bundle_label": "clear + balm",
                    "count_top_seller": 999,
                    "count_other": 999,
                    "top_seller_base": 999,
                    "other_base": 999,
                    "pct_top_seller": 9.99,
                    "pct_other": 9.99,
                }
            ]
        ),
    }

    result = calculate_package_frames("launch", frames)

    row = result.frames["top_seller_pairs.csv"].to_dicts()[0]
    assert row["count_top_seller"] == 1
    assert row["count_other"] == 1
    assert row["top_seller_base"] == 2
    assert row["other_base"] == 2
    assert row["pct_top_seller"] == 0.5
    assert row["pct_other"] == 0.5
    assert row["top_seller_brand_count"] == 1
    assert row["calculation_helper_id"] == "launch.bundle_incidence.v1"
    assert row["calculation_source"] == "product_filter_matrix.csv"


def test_calculate_package_frames_respects_explicit_bundle_source_column() -> None:
    product_matrix = pl.DataFrame(
        [
            {
                "product_name": "Exact Top Balm",
                "brand": "A",
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "resolved_form": "gloss",
                "form": "balm",
            },
            {
                "product_name": "Exact Other Balm",
                "brand": "B",
                "listing_status": "rest",
                "top_seller_status": "other",
                "resolved_form": "gloss",
                "form": "balm",
            },
            {
                "product_name": "Resolved Top Balm",
                "brand": "C",
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "resolved_form": "gloss",
                "form": "stick",
            },
            {
                "product_name": "Resolved Only Balm",
                "brand": "D",
                "listing_status": "rest",
                "top_seller_status": "other",
                "resolved_form": "balm",
                "form": "stick",
            },
        ]
    )
    frames = {
        "product_filter_matrix.csv": product_matrix,
        "top_seller_pairs.csv": pl.DataFrame(
            [
                {
                    "bundle_key": "form=balm",
                    "bundle_label": "balm",
                    "count_top_seller": 999,
                    "count_other": 999,
                    "top_seller_base": 999,
                    "other_base": 999,
                    "pct_top_seller": 9.99,
                    "pct_other": 9.99,
                }
            ]
        ),
    }

    result = calculate_package_frames("launch", frames)

    row = result.frames["top_seller_pairs.csv"].to_dicts()[0]
    assert row["count_top_seller"] == 1
    assert row["count_other"] == 1
    assert row["pct_top_seller"] == 0.5
    assert row["pct_other"] == 0.5


def test_calculate_package_frames_prefers_populated_duplicate_bundle_column() -> None:
    product_matrix = pl.DataFrame(
        [
            {
                "product_name": "Paraben Free Longwear",
                "brand": "A",
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "free from": "paraben-free",
                "free_from": None,
                "wear claims": "longwear",
            },
            {
                "product_name": "Paraben Free Only",
                "brand": "B",
                "listing_status": "rest",
                "top_seller_status": "other",
                "free from": "paraben-free",
                "free_from": None,
                "wear claims": None,
            },
        ]
    )
    frames = {
        "product_filter_matrix.csv": product_matrix,
        "innovation_pairs.csv": pl.DataFrame(
            [
                {
                    "bundle_key": "free from=paraben-free + wear claims=longwear",
                    "bundle_label": "paraben-free + longwear",
                    "count_recent": 999,
                    "count_rest": 999,
                    "recent_base": 999,
                    "rest_base": 999,
                    "pct_recent": 9.99,
                    "pct_rest": 9.99,
                }
            ]
        ),
    }

    result = calculate_package_frames("launch", frames)

    row = result.frames["innovation_pairs.csv"].to_dicts()[0]
    assert row["count_recent"] == 1
    assert row["count_rest"] == 0
    assert row["pct_recent"] == 1.0
    assert row["pct_rest"] == 0.0


def test_calculate_package_frames_recomputes_launch_attribute_subset_bases() -> None:
    product_matrix = pl.DataFrame(
        [
            {
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "benefits": "vegan",
            },
            {
                "listing_status": "recent",
                "top_seller_status": "other",
                "benefits": None,
            },
            {
                "listing_status": "rest",
                "top_seller_status": "other",
                "benefits": "vegan",
            },
            {
                "listing_status": "rest",
                "top_seller_status": "other",
                "benefits": "hydrating",
            },
            {
                "listing_status": "rest",
                "top_seller_status": "other",
                "benefits": None,
            },
        ]
    )
    frames = {
        "product_filter_matrix.csv": product_matrix,
        "mapped_attribute_comparison.csv": pl.DataFrame(
            [
                {
                    "attribute_name": "benefits",
                    "attribute_value": "vegan",
                    "count_recent": 999,
                    "count_rest": 999,
                    "recent_base": 999,
                    "rest_base": 999,
                    "pct_recent": 9.99,
                    "pct_rest": 9.99,
                }
            ]
        ),
    }

    result = calculate_package_frames("launch", frames)

    row = result.frames["mapped_attribute_comparison.csv"].to_dicts()[0]
    assert row["count_recent"] == 1
    assert row["count_rest"] == 1
    assert row["recent_base"] == 1
    assert row["rest_base"] == 2
    assert row["pct_recent"] == 1.0
    assert row["pct_rest"] == 0.5
    assert row["calculation_column"] == "benefits"
    assert row["calculation_helper_id"] == "launch.attribute_incidence.v1"


def test_calculate_package_frames_uses_exact_mapped_attribute_values() -> None:
    product_matrix = pl.DataFrame(
        [
            {
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "product form": "cream",
            },
            {
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "product form": "brushOn | cream | liquid",
            },
            {
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "product form": "not in taxonomy",
            },
            {
                "listing_status": "rest",
                "top_seller_status": "other",
                "product form": "cream",
            },
        ]
    )
    frames = {
        "product_filter_matrix.csv": product_matrix,
        "top_seller_mapped_attribute_comparison.csv": pl.DataFrame(
            [
                {
                    "attribute_name": "product form",
                    "attribute_value": "cream",
                    "count_top_seller": 999,
                    "count_other": 999,
                    "top_seller_base": 999,
                    "other_base": 999,
                    "pct_top_seller": 9.99,
                    "pct_other": 9.99,
                }
            ]
        ),
    }

    result = calculate_package_frames("launch", frames)

    row = result.frames["top_seller_mapped_attribute_comparison.csv"].to_dicts()[0]
    assert row["count_top_seller"] == 1
    assert row["top_seller_base"] == 2
    assert row["count_other"] == 1
    assert row["other_base"] == 1
    assert row["pct_top_seller"] == 0.5
    assert row["pct_other"] == 1.0


def test_calculate_package_frames_uses_atom_filter_values() -> None:
    product_matrix = pl.DataFrame(
        [
            {
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "product form": "cream",
            },
            {
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "product form": "brushOn | cream | liquid",
            },
            {
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "product form": "not in taxonomy",
            },
            {
                "listing_status": "rest",
                "top_seller_status": "other",
                "product form": "liquid",
            },
        ]
    )
    frames = {
        "product_filter_matrix.csv": product_matrix,
        "filter_comparison.csv": pl.DataFrame(
            [
                {
                    "filter_family": "product form",
                    "filter_value": "cream",
                    "count_recent": 999,
                    "count_rest": 999,
                    "recent_family_base": 999,
                    "rest_family_base": 999,
                    "pct_recent": 9.99,
                    "pct_rest": 9.99,
                }
            ]
        ),
    }

    result = calculate_package_frames("launch", frames)

    row = result.frames["filter_comparison.csv"].to_dicts()[0]
    assert row["count_recent"] == 2
    assert row["recent_family_base"] == 2
    assert row["count_rest"] == 0
    assert row["rest_family_base"] == 1
    assert row["pct_recent"] == 1.0
    assert row["pct_rest"] == 0.0


def test_calculate_package_frames_recomputes_launch_brand_share() -> None:
    product_matrix = pl.DataFrame(
        [
            {"brand": "A", "top_seller_status": "top_seller"},
            {"brand": "A", "top_seller_status": "other"},
            {"brand": "B", "top_seller_status": "top_seller"},
            {"brand": None, "top_seller_status": "top_seller"},
        ]
    )
    frames = {
        "product_filter_matrix.csv": product_matrix,
        "top_seller_brand_comparison.csv": pl.DataFrame(
            [
                {
                    "brand": "A",
                    "catalog_count": 999,
                    "top_seller_count": 999,
                    "other_count": 999,
                    "catalog_share": 9.99,
                    "top_seller_share_of_brand": 9.99,
                    "top_seller_share_of_cohort": 9.99,
                    "over_index_vs_catalog_share": 9.99,
                }
            ]
        ),
    }

    result = calculate_package_frames("launch", frames)

    row = result.frames["top_seller_brand_comparison.csv"].to_dicts()[0]
    assert row["catalog_count"] == 2
    assert row["top_seller_count"] == 1
    assert row["other_count"] == 1
    assert row["catalog_share"] == 2 / 3
    assert row["top_seller_share_of_brand"] == 0.5
    assert row["top_seller_share_of_cohort"] == 0.5
    assert row["over_index_vs_catalog_share"] == 0.75
    assert row["calculation_helper_id"] == "launch.brand_share.v1"
