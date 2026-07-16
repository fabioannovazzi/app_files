from __future__ import annotations

import polars as pl
import pytest

from modules.pdp.web_shelf_discovery import (
    discover_web_shelves,
    refine_shelf_with_third_attribute,
)


def _toy_category() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "product_id": [f"p{i}" for i in range(1, 11)],
            "rank": list(range(1, 11)),
            "brand": [
                "Alpha",
                "Beta",
                "Gamma",
                "Delta",
                "Alpha",
                "Beta",
                "Gamma",
                "Delta",
                "Alpha",
                "Beta",
            ],
            "product_name": [f"Product {i}" for i in range(1, 11)],
            "attributes": [
                [
                    "color=black",
                    "color=white",
                    "material=leather",
                    "claim=vegan",
                    "price_tier=premium",
                ],
                [
                    "color=black",
                    "material=leather",
                    "claim=vegan",
                    "price_tier=premium",
                ],
                [
                    "color=black",
                    "material=leather",
                    "claim=natural",
                    "price_tier=premium",
                ],
                [
                    "color=black",
                    "material=leather",
                    "claim=vegan",
                    "price_tier=value",
                ],
                [
                    "color=black",
                    "material=canvas",
                    "claim=vegan",
                    "price_tier=premium",
                ],
                [
                    "color=white",
                    "material=leather",
                    "claim=natural",
                    "price_tier=premium",
                ],
                [
                    "color=white",
                    "material=canvas",
                    "claim=natural",
                    "price_tier=value",
                ],
                [
                    "color=red",
                    "material=canvas",
                    "claim=vegan",
                    "price_tier=value",
                ],
                [
                    "color=red",
                    "material=leather",
                    "claim=vegan",
                    "price_tier=premium",
                ],
                [
                    "color=red",
                    "material=canvas",
                    "claim=natural",
                    "price_tier=value",
                ],
            ],
        }
    )


def _discover() -> dict[str, pl.DataFrame]:
    return discover_web_shelves(
        _toy_category(),
        alphas=(0.0, 1.0, 1.2),
        min_skus=2,
        min_brands=1,
        max_selected_shelves=20,
    )


def _bundle_has_duplicate_dimensions(bundle_key: str) -> bool:
    dimensions = [part.split("=", 1)[0] for part in bundle_key.split(" + ")]
    return len(dimensions) != len(set(dimensions))


def test_product_weights_sum_to_one_for_each_alpha() -> None:
    assignments = _discover()["product_shelf_assignments"]

    for row in (
        assignments.group_by("alpha")
        .agg(pl.col("product_weight").sum().alias("weight_sum"))
        .to_dicts()
    ):
        assert row["weight_sum"] == pytest.approx(1.0)


def test_alpha_zero_gives_equal_product_weights() -> None:
    assignments = _discover()["product_shelf_assignments"].filter(
        pl.col("alpha") == 0.0
    )

    weights = sorted(
        round(float(value), 10)
        for value in assignments.get_column("product_weight").to_list()
    )

    assert weights == [0.1] * 10


def test_candidate_bundles_do_not_contain_two_values_from_same_dimension() -> None:
    candidates = _discover()["candidate_shelves"]

    invalid = [
        bundle_key
        for bundle_key in candidates.get_column("bundle_key").to_list()
        if _bundle_has_duplicate_dimensions(bundle_key)
    ]

    assert invalid == []


def test_package_style_attribute_columns_are_supported() -> None:
    df = pl.DataFrame(
        {
            "product_id": ["p1", "p2", "p3", "p4"],
            "rank": [1, 2, 3, 4],
            "brand": ["Alpha", "Beta", "Gamma", "Delta"],
            "product_name": ["One", "Two", "Three", "Four"],
            "color": ["black", "black", "white", "white"],
            "material": ["leather", "leather", "canvas", "canvas"],
            "claim": ["vegan", "vegan", "natural", "natural"],
        }
    )

    outputs = discover_web_shelves(
        df,
        attributes_col=None,
        attribute_columns=("color", "material", "claim"),
        alphas=(1.0,),
        min_skus=2,
        min_brands=1,
    )

    assert (
        "color=black + material=leather"
        in outputs["candidate_shelves"].get_column("bundle_key").to_list()
    )


def test_gross_shelf_weights_can_overlap() -> None:
    candidates = _discover()["candidate_shelves"].filter(pl.col("alpha") == 1.0)

    gross_weight_sum = candidates.get_column("gross_weight_share").sum()

    assert gross_weight_sum > 1.0


def test_incremental_weights_plus_residual_sum_to_one() -> None:
    selected = _discover()["selected_shelves"]

    for row in (
        selected.group_by("alpha")
        .agg(pl.col("incremental_weight_share").sum().alias("weight_sum"))
        .to_dicts()
    ):
        assert row["weight_sum"] == pytest.approx(1.0)


def test_each_product_is_assigned_to_one_shelf_per_alpha() -> None:
    assignments = _discover()["product_shelf_assignments"]

    max_assignments = (
        assignments.group_by(["alpha", "product_id"])
        .agg(pl.len().alias("assignment_count"))
        .get_column("assignment_count")
        .max()
    )

    assert max_assignments == 1


def test_density_index_is_weight_share_divided_by_sku_share() -> None:
    candidate = (
        _discover()["candidate_shelves"]
        .filter(pl.col("alpha") == 1.0)
        .row(
            0,
            named=True,
        )
    )

    expected = candidate["gross_weight_share"] / candidate["gross_sku_share"]

    assert candidate["density_index"] == pytest.approx(expected)


def test_robustness_summary_records_alpha_selection_flags() -> None:
    robustness = _discover()["robustness_summary"]

    assert {
        "selected_under_alpha_0",
        "selected_under_alpha_1",
        "selected_under_alpha_1_2",
    } <= set(robustness.columns)
    assert robustness.get_column("times_selected").max() >= 1


def test_third_attribute_refinement_adds_valid_third_dimension() -> None:
    selected = _discover()["selected_shelves"].filter(
        (pl.col("alpha") == 1.0) & (pl.col("bundle_key") != "__residual__")
    )
    base_bundle = str(selected.row(0, named=True)["bundle_key"])

    refinements = refine_shelf_with_third_attribute(
        _toy_category(),
        base_bundle,
        alpha=1.0,
        min_skus=2,
        min_brands=1,
    )

    assert refinements.height > 0
    refinement = refinements.row(0, named=True)
    base_dimensions = {part.split("=", 1)[0] for part in base_bundle.split(" + ")}
    refinement_dimensions = {
        part.split("=", 1)[0]
        for part in str(refinement["refinement_bundle_key"]).split(" + ")
    }
    assert len(refinement_dimensions) == 3
    assert base_dimensions < refinement_dimensions


def test_invalid_nonpositive_rank_raises() -> None:
    df = _toy_category().with_columns(
        pl.when(pl.col("product_id") == "p1")
        .then(0)
        .otherwise(pl.col("rank"))
        .alias("rank")
    )

    with pytest.raises(ValueError, match="positive numeric ranks"):
        discover_web_shelves(df, min_skus=2, min_brands=1)
