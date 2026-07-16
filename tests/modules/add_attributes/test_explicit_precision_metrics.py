from __future__ import annotations

import polars as pl

from modules.add_attributes.explicit_precision_metrics import (
    compute_explicit_precision_metrics,
)


def test_compute_explicit_precision_metrics_counts_parent_and_variant_matches() -> None:
    explicit_parent_stage = pl.DataFrame(
        {
            "retailer": ["sephora", "sephora"],
            "parent_product_id": ["P1", "P2"],
            "category_key": ["lipstick", "lipstick"],
            "finish": ["matte", "satin"],
        }
    )
    explicit_variant_stage = pl.DataFrame(
        {
            "retailer": ["sephora"],
            "variant_id": ["V1"],
            "category_key": ["lipstick"],
            "finish": ["matte"],
        }
    )

    deterministic_parent_stage = pl.DataFrame(
        {
            "retailer": ["sephora", "sephora"],
            "parent_product_id": ["P1", "P2"],
            "category_key": ["lipstick", "lipstick"],
            "finish": ["matte", "luminous"],
        }
    )
    deterministic_variant_stage = pl.DataFrame(
        {
            "retailer": ["sephora"],
            "variant_id": ["V1"],
            "category_key": ["lipstick"],
            "finish": ["matte"],
        }
    )

    llm_parent_stage = pl.DataFrame(
        {
            "retailer": ["sephora", "sephora"],
            "parent_product_id": ["P1", "P2"],
            "category_key": ["lipstick", "lipstick"],
            "finish": ["matte", "N/A"],
        }
    )
    llm_variant_stage = pl.DataFrame(
        {
            "retailer": ["sephora"],
            "variant_id": ["V1"],
            "category_key": ["lipstick"],
            "finish": ["N/A"],
        }
    )

    metrics = compute_explicit_precision_metrics(
        run_id="run_001",
        explicit_parent_stage=explicit_parent_stage,
        explicit_variant_stage=explicit_variant_stage,
        explicit_parent_attributes=["finish"],
        explicit_variant_attributes=["finish"],
        deterministic_parent_stage=deterministic_parent_stage,
        deterministic_variant_stage=deterministic_variant_stage,
        deterministic_parent_attributes=["finish"],
        deterministic_variant_attributes=["finish"],
        llm_parent_stage=llm_parent_stage,
        llm_variant_stage=llm_variant_stage,
        llm_parent_attributes=["finish"],
        llm_variant_attributes=["finish"],
    )

    assert len(metrics) == 1
    metric = metrics[0]
    assert metric.run_id == "run_001"
    assert metric.category_key == "lipstick"
    assert metric.attribute_id == "finish"
    assert metric.explicit_positive_count == 3
    assert metric.deterministic_match_on_explicit == 2
    assert metric.llm_match_on_explicit == 1
    assert metric.deterministic_precision_proxy == (2 / 3)
    assert metric.llm_precision_proxy == (1 / 3)


def test_compute_explicit_precision_metrics_ignores_placeholder_explicit_values() -> (
    None
):
    explicit_parent_stage = pl.DataFrame(
        {
            "retailer": ["sephora"],
            "parent_product_id": ["P1"],
            "category_key": ["lipstick"],
            "finish": ["N/A"],
        }
    )

    metrics = compute_explicit_precision_metrics(
        run_id="run_002",
        explicit_parent_stage=explicit_parent_stage,
        explicit_variant_stage=pl.DataFrame(),
        explicit_parent_attributes=["finish"],
        explicit_variant_attributes=[],
        deterministic_parent_stage=pl.DataFrame(),
        deterministic_variant_stage=pl.DataFrame(),
        deterministic_parent_attributes=[],
        deterministic_variant_attributes=[],
        llm_parent_stage=pl.DataFrame(),
        llm_variant_stage=pl.DataFrame(),
        llm_parent_attributes=[],
        llm_variant_attributes=[],
    )

    assert metrics == []
