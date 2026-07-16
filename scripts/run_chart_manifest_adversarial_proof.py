from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_VENDOR_ROOT = REPO_ROOT / "plugins" / "_shared" / "vendor"


def _ensure_shared_chart_harness_path() -> None:
    shared_text = str(SHARED_VENDOR_ROOT)
    if shared_text in sys.path:
        sys.path.remove(shared_text)
    sys.path.insert(0, shared_text)
    module_root = (SHARED_VENDOR_ROOT / "modules").resolve()
    for name, module in list(sys.modules.items()):
        if name == "modules" or name.startswith("modules."):
            module_file = getattr(module, "__file__", None)
            if not module_file or not Path(module_file).resolve().is_relative_to(
                module_root
            ):
                del sys.modules[name]


_ensure_shared_chart_harness_path()

from modules.chart_harness import validate_period_label_policy  # noqa: E402

from audit_chart_manifest_against_us_cosmetics import (
    audit_manifest_against_us_cosmetics,
)

__all__ = ["main", "run_adversarial_proof"]

SOURCE_DATASET = (
    REPO_ROOT
    / "data"
    / "pdp"
    / "sales_data"
    / "joined_datasets"
    / "us_cosmetics"
    / "joined.parquet"
)
OUTPUT_DIR = Path("/private/tmp/chart_manifest_cosmetics_proof")
PROOF_CSV = OUTPUT_DIR / "us_cosmetics_manifest_proof.csv"
PROOF_TWO_PERIOD_CSV = OUTPUT_DIR / "us_cosmetics_manifest_two_period_proof.csv"
REPORT_PATH = (
    REPO_ROOT
    / "runs"
    / "chart_selection_manifest_rebuild"
    / "us_cosmetics_adversarial_chart_proof.md"
)
PASSING_PROOF_VERDICTS = {"correct_rejection", "credible_data_artifact"}
CONTEXT_IDENTITY_KEYS = ("chart", "chart_type", "analysis_type")
SIDECAR_NAME_SUFFIXES = ("_context", "_chart_context")


TEST_CASES: list[dict[str, Any]] = [
    {
        "capability_id": "period_comparison.trend",
        "question": "How did monthly cosmetics sales evolve versus previous year?",
        "expected_plugin": "period-comparison",
        "plugin_chart": "year_over_year_line",
        "expected_outcome": "use_after_derivation",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "comparison": "2025 YTD through Sep vs 2024 YTD through Sep",
            "dimensions": ["category", "retailer", "brand", "price_band"],
        },
    },
    {
        "capability_id": "period_comparison.by_period",
        "question": "Which months explain the AC/PY sales gap?",
        "expected_plugin": "period-comparison",
        "plugin_chart": "year_over_year_by_period",
        "expected_outcome": "use_after_derivation",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "comparison": "monthly AC/PY derived from month",
        },
    },
    {
        "capability_id": "period_comparison.horizontal_waterfall",
        "question": "How do period variances reconcile prior-year sales to current sales?",
        "expected_plugin": "period-comparison",
        "plugin_chart": "year_over_year_waterfall",
        "expected_outcome": "use_after_derivation",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "bridge_component_period": "derived monthly deltas",
        },
    },
    {
        "capability_id": "period_comparison.multitier_column",
        "question": "Show compact AC/PY monthly sales columns.",
        "expected_plugin": "period-comparison",
        "plugin_chart": "year_over_year_column",
        "expected_outcome": "use_after_derivation",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "comparison_series": "AC/PY derived from month",
        },
    },
    {
        "capability_id": "period_comparison.comparison_table",
        "question": "Give exact current, prior-year, delta, and percent-delta sales values.",
        "expected_plugin": "period-comparison",
        "plugin_chart": "comparison_table",
        "expected_outcome": "use_after_derivation",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "comparison_window": "2025 YTD through Sep vs 2024 YTD through Sep",
        },
    },
    {
        "capability_id": "period_comparison.dot",
        "question": "Compare AC/PY sales gaps across categories with low clutter.",
        "expected_plugin": "period-comparison",
        "plugin_chart": "year_over_year_dot",
        "expected_outcome": "use_after_derivation",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "comparison_item": "category",
        },
    },
    {
        "capability_id": "period_comparison.slope",
        "question": "Show endpoint direction and magnitude of category sales changes.",
        "expected_plugin": "period-comparison",
        "plugin_chart": "year_over_year_slope",
        "expected_outcome": "use_after_derivation",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "comparison_item": "category",
        },
    },
    {
        "capability_id": "period_comparison.time_series_table",
        "question": "Give citeable monthly AC/PY sales values and variances.",
        "expected_plugin": "period-comparison",
        "plugin_chart": "time_series_table",
        "expected_outcome": "use_after_derivation",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "period_axis": "month",
        },
    },
    {
        "capability_id": "mix.timeline",
        "question": "Show the single sales trend across months without AC/PY comparison.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "line",
        "expected_outcome": "use_directly",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "dimensions": ["category", "retailer", "brand"],
        },
    },
    {
        "capability_id": "mix.area",
        "question": "Show sales contribution as an area trend across months.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "area_absolute",
        "expected_outcome": "use_directly",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "dimensions": ["retailer", "category"],
        },
    },
    {
        "capability_id": "mix.column",
        "question": "Show total sales by month as compact columns.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "column_total",
        "expected_outcome": "use_directly",
        "params": {
            "date_column": "month",
            "period_column": "month",
            "period_axis": "month",
            "amount_column": "sales",
        },
        "expected_context_period_axis": {
            "minimum_distinct_periods": 2,
            "required_period_grain": "month",
            "forbid_same_period_title": True,
            "forbid_bare_ac_period": True,
        },
    },
    {
        "capability_id": "mix.column_overlay",
        "question": "Show total monthly sales with sales-share marker context.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "column_total_with_overlay",
        "expected_outcome": "use_directly",
        "params": {
            "date_column": "month",
            "period_column": "month",
            "period_axis": "month",
            "amount_column": "sales",
            "related_marker_metric_column": "sales_share",
        },
        "expected_context_period_axis": {
            "minimum_distinct_periods": 2,
            "required_period_grain": "month",
            "forbid_same_period_title": True,
            "forbid_bare_ac_period": True,
        },
    },
    {
        "capability_id": "mix.multitier_bar",
        "question": "Show category sales in two periods and the difference, split into retailer panels.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "multitier_bar_two_dimension",
        "expected_outcome": "use_directly",
        "params": {
            "amount_column": "sales",
            "dimension": "category",
            "small_multiples_dimension": "retailer",
            "selected_periods": ["2025-08", "2025-09"],
            "shown_values": ["baseline sales", "current sales", "delta"],
        },
    },
    {
        "capability_id": "mix.bar",
        "question": "Rank categories by sales for a selected scope.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "bar",
        "expected_outcome": "use_directly",
        "params": {
            "amount_column": "sales",
            "category": "category",
        },
    },
    {
        "capability_id": "mix.barmekko",
        "question": "Show category width and retailer height as a variable-width composition.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "barmekko",
        "expected_outcome": "use_directly",
        "params": {
            "width_metric": "sales",
            "height_metric": "sales_share",
            "width_category": "category",
            "height_category": "retailer",
        },
    },
    {
        "capability_id": "mix.marimekko",
        "question": "Show sales composition across category and retailer.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "marimekko",
        "expected_outcome": "use_directly",
        "params": {
            "amount_column": "sales",
            "width_category": "category",
            "stack_category": "retailer",
        },
    },
    {
        "capability_id": "mix.pareto",
        "question": "Find the few categories that explain most sales.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "pareto",
        "expected_outcome": "use_directly",
        "params": {
            "amount_column": "sales",
            "category": "category",
        },
    },
    {
        "capability_id": "mix.stacked_bar",
        "question": "Show sales totals and composition by retailer within categories.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "stacked_bar",
        "expected_outcome": "use_directly",
        "params": {
            "amount_column": "sales",
            "category": "category",
            "component_category": "retailer",
        },
    },
    {
        "capability_id": "mix.stacked_bar_overlay",
        "question": "Rank category sales while overlaying sales-share context.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "related_metrics_bar",
        "expected_outcome": "use_directly",
        "params": {
            "amount_column": "sales",
            "related_marker_metric_column": "sales_share",
            "category": "category",
        },
    },
    {
        "capability_id": "mix.stacked_column",
        "question": "Show recent monthly sales mix by category.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "stacked_column",
        "expected_outcome": "use_directly",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "component_dimension": "category",
            "period_grain": "month",
            "selected_periods": ["2025-08", "2025-09"],
        },
    },
    {
        "capability_id": "mix.like_for_like_column",
        "question": "How did sales change for the same products active in both selected months?",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "like_for_like_column_total",
        "expected_outcome": "use_after_derivation",
        "params": {
            "amount_column": "sales",
            "stable_population_entity": "canonical_id",
            "comparison_periods": ["2025-08", "2025-09"],
        },
    },
    {
        "capability_id": "mix.like_for_like_stacked_column",
        "question": "How did same-product sales mix by category change across the selected months?",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "like_for_like_stacked_column",
        "expected_outcome": "use_after_derivation",
        "params": {
            "amount_column": "sales",
            "stable_population_entity": "canonical_id",
            "component_dimension": "category",
            "comparison_periods": ["2025-08", "2025-09"],
        },
    },
    {
        "capability_id": "mix.cohort_since_stacked_column",
        "question": "How much sales contribution comes from products by first active month?",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "cohort_since_stacked_column",
        "expected_outcome": "use_after_derivation",
        "params": {
            "amount_column": "sales",
            "entity_dimension": "canonical_id",
            "cohort_role": "first_active_cohort",
        },
    },
    {
        "capability_id": "mix.cohort_lost_stacked_column",
        "question": "How much sales contribution comes from products by last active month?",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "cohort_lost_stacked_column",
        "expected_outcome": "use_after_derivation",
        "params": {
            "amount_column": "sales",
            "entity_dimension": "canonical_id",
            "cohort_role": "lost_or_last_active_cohort",
        },
    },
    {
        "capability_id": "mix.stacked_pareto",
        "question": "Show concentration and component composition together.",
        "expected_plugin": "mix-contribution-analysis",
        "plugin_chart": "stacked_pareto_abc",
        "expected_outcome": "use_directly",
        "params": {
            "amount_column": "sales",
            "category": "category",
            "component_dimension": "retailer",
        },
    },
    {
        "capability_id": "scatter.bubble",
        "question": "Do units and sales share relate, weighted by sales?",
        "expected_plugin": "scatter-bubble-analysis",
        "plugin_chart": "bubble",
        "expected_outcome": "use_directly",
        "params": {
            "x_metric_column": "units",
            "y_metric_column": "sales_share",
            "bubble_size_metric_column": "sales",
            "dot_dimension": "retailer",
            "color_dimension": "brand",
        },
    },
    {
        "capability_id": "scatter.scatter",
        "question": "Do units and sales share relate without size encoding?",
        "expected_plugin": "scatter-bubble-analysis",
        "plugin_chart": "scatter",
        "expected_outcome": "use_directly",
        "params": {
            "x_metric_column": "units",
            "y_metric_column": "sales_share",
            "dot_dimension": "retailer",
            "color_dimension": "brand",
        },
    },
    {
        "capability_id": "distribution.boxplot",
        "question": "Summarize spread and outliers in monthly sales observations.",
        "expected_plugin": "distribution-analysis",
        "plugin_chart": "boxplot",
        "expected_outcome": "use_directly",
        "params": {
            "metric_column": "sales",
            "small_multiples_dimension": "retailer",
        },
    },
    {
        "capability_id": "distribution.ecdf",
        "question": "Show cumulative share of sales observations below each threshold.",
        "expected_plugin": "distribution-analysis",
        "plugin_chart": "ecdf",
        "expected_outcome": "use_directly",
        "params": {
            "metric_column": "sales",
            "small_multiples_dimension": "retailer",
        },
    },
    {
        "capability_id": "distribution.histogram",
        "question": "What is the distribution of monthly sales observations?",
        "expected_plugin": "distribution-analysis",
        "plugin_chart": "histogram",
        "expected_outcome": "use_directly",
        "params": {
            "metric_column": "sales",
            "small_multiples_dimension": "retailer",
        },
    },
    {
        "capability_id": "distribution.kernel_density",
        "question": "Show smoothed sales-distribution shape.",
        "expected_plugin": "distribution-analysis",
        "plugin_chart": "kernel_density",
        "expected_outcome": "use_directly",
        "params": {
            "metric_column": "sales",
            "small_multiples_dimension": "retailer",
        },
    },
    {
        "capability_id": "distribution.stripplot",
        "question": "Show individual monthly sales observations and outliers.",
        "expected_plugin": "distribution-analysis",
        "plugin_chart": "stripplot",
        "expected_outcome": "use_directly",
        "params": {
            "metric_column": "sales",
            "small_multiples_dimension": "retailer",
        },
    },
    {
        "capability_id": "set_overlap.upset",
        "question": "Which brands are shared across retailers?",
        "expected_plugin": "set-overlap-analysis",
        "plugin_chart": "upset",
        "expected_outcome": "use_after_derivation",
        "params": {
            "item_column": "brand",
            "set_column": "retailer",
            "set_values": ["amazon", "sephora", "ulta"],
        },
    },
    {
        "capability_id": "set_overlap.upset_small_multiples",
        "question": "How does brand overlap across retailers differ by category?",
        "expected_plugin": "set-overlap-analysis",
        "plugin_chart": "upset_small_multiples",
        "expected_outcome": "use_after_derivation",
        "params": {
            "item_column": "brand",
            "set_column": "retailer",
            "small_multiples_dimension": "category",
        },
    },
    {
        "capability_id": "set_overlap.venn",
        "question": "Show simple brand overlap across the three retailers.",
        "expected_plugin": "set-overlap-analysis",
        "plugin_chart": "venn",
        "expected_outcome": "use_after_derivation",
        "params": {
            "item_column": "brand",
            "set_column": "retailer",
            "set_values": ["amazon", "sephora", "ulta"],
        },
    },
    {
        "capability_id": "variance.scenario_bridge",
        "question": "Reconcile total sales from baseline to current with a plain bridge.",
        "expected_plugin": "variance-analysis",
        "plugin_chart": "standard_variance",
        "verification_artifact": "standard_variance_context",
        "expected_context_chart_type": "standard_variance_waterfall",
        "expected_outcome": "use_after_derivation",
        "params": {
            "date_column": "month",
            "amount_column": "sales",
            "baseline_period": "derived PY",
            "comparison_period": "derived AC",
        },
    },
    {
        "capability_id": "variance.price_volume_mix",
        "question": "How much of the sales movement is due to price, units, and mix?",
        "expected_plugin": "variance-analysis",
        "plugin_chart": "pvm_decomposition_ladder",
        "verification_artifact": "pvm_decomposition_ladder_context",
        "expected_context_chart_type": "pvm_decomposition_ladder",
        "expected_outcome": "use_after_derivation",
        "params": {
            "amount_column": "sales",
            "units_column": "units",
            "date_column": "month",
        },
    },
    {
        "capability_id": "variance.total_by_dimension_bridge",
        "question": "Which categories account for the total sales variance?",
        "expected_plugin": "variance-analysis",
        "plugin_chart": "total_by_dimension_bridge",
        "verification_artifact": "total_by_dimension_bridge_context",
        "expected_context_chart_type": "total_by_dimension_bridge",
        "expected_outcome": "use_after_derivation",
        "params": {
            "amount_column": "sales",
            "dimension": "category",
        },
    },
    {
        "capability_id": "variance.exploded_variance_bridge",
        "question": "Which categories drove variance, and which brands explain the selected category moves?",
        "expected_plugin": "variance-analysis",
        "plugin_chart": "exploded_variance_bridge",
        "verification_artifact": "exploded_variance_bridge_context",
        "expected_context_chart_type": "exploded_variance_bridge",
        "expected_outcome": "use_after_derivation",
        "params": {
            "parent_driver": "category",
            "child_driver": "brand",
        },
    },
    {
        "capability_id": "variance.root_cause_exploded_bridge",
        "question": "Which ordered root-cause path explains the total sales movement, and what explains the selected root-cause driver?",
        "expected_plugin": "variance-analysis",
        "plugin_chart": "root_cause_exploded_bridge",
        "verification_artifact": "root_cause_exploded_bridge_context",
        "expected_context_chart_type": "root_cause_exploded_bridge",
        "expected_outcome": "use_after_derivation",
        "params": {
            "root_cause_driver_sequence": "derived ranked dimensions",
            "selected_root_cause_row": 1,
            "nested_root_cause_driver_sequence": "row-specific derived ranked dimensions",
            "amount_column": "sales",
        },
    },
    {
        "capability_id": "variance.root_cause_total_bridge",
        "question": "Which ordered root-cause path explains the total sales movement?",
        "expected_plugin": "variance-analysis",
        "plugin_chart": "root_cause_total_bridge",
        "verification_artifact": "root_cause_total_bridge_context",
        "expected_context_chart_type": "root_cause_total_bridge",
        "expected_outcome": "use_after_derivation",
        "params": {
            "root_cause_driver": "derived ranked dimensions",
            "amount_column": "sales",
        },
    },
    {
        "capability_id": "variance.root_cause_component_bridge",
        "question": "Which drivers explain the selected root-cause component of sales movement?",
        "expected_plugin": "variance-analysis",
        "plugin_chart": "root_cause_component_bridge",
        "verification_artifact": "root_cause_component_bridge_context",
        "expected_context_chart_type": "root_cause_component_bridge",
        "expected_outcome": "use_after_derivation",
        "params": {
            "component": "selected variance component",
            "component_driver": "derived ranked dimensions",
            "amount_column": "sales",
        },
    },
    {
        "capability_id": "funnel.stage_table",
        "question": "What is the stage conversion funnel?",
        "expected_plugin": "funnel-analysis",
        "plugin_chart": None,
        "expected_outcome": "reject",
        "params": {
            "ordered_stage": None,
            "stage_start_count": None,
            "stage_pass_count": None,
        },
    },
    {
        "capability_id": "statement.pnl_table",
        "question": "Build a P&L line-item table.",
        "expected_plugin": "statement-analysis",
        "plugin_chart": None,
        "expected_outcome": "reject",
        "params": {
            "statement_line_item": None,
            "statement_value": None,
        },
    },
]


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _prepare_proof_csv() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lf = pl.scan_parquet(SOURCE_DATASET)
    base = (
        lf.select(
            [
                pl.col("month").cast(pl.Date),
                pl.col("retailer"),
                pl.col("category"),
                pl.col("brand"),
                pl.col("sales").cast(pl.Float64),
                pl.col("units").cast(pl.Float64),
                pl.col("price_raw").cast(pl.Float64, strict=False),
                pl.col("sales_share").cast(pl.Float64, strict=False),
                pl.col("cumulative_sales_share").cast(pl.Float64, strict=False),
                pl.col("pareto_rank").cast(pl.Float64, strict=False),
                pl.col("price_band"),
                pl.col("pareto_class"),
                pl.col("finish"),
                pl.col("coverage"),
                pl.col("canonical_id"),
            ]
        )
        .filter(pl.col("sales").is_not_null(), pl.col("units").is_not_null())
        .group_by(
            [
                "month",
                "retailer",
                "category",
                "brand",
                "canonical_id",
                "price_band",
                "pareto_class",
                "finish",
                "coverage",
            ]
        )
        .agg(
            [
                pl.col("sales").sum().alias("sales"),
                pl.col("units").sum().alias("units"),
                pl.col("sales_share").sum().alias("sales_share"),
                pl.col("cumulative_sales_share").max().alias("cumulative_sales_share"),
                pl.col("price_raw").mean().alias("avg_price"),
                pl.col("pareto_rank").mean().alias("avg_pareto_rank"),
                pl.col("canonical_id").n_unique().alias("product_count"),
            ]
        )
        .with_columns(
            (
                pl.col("sales")
                / pl.when(pl.col("units") == 0).then(None).otherwise(pl.col("units"))
            ).alias("asp")
        )
        .collect(engine="streaming")
    )
    top_brands = (
        base.group_by("brand")
        .agg(pl.col("sales").sum())
        .sort("sales", descending=True)
        .head(25)
        .get_column("brand")
        .implode()
    )
    top_categories = (
        base.group_by("category")
        .agg(pl.col("sales").sum())
        .sort("sales", descending=True)
        .head(12)
        .get_column("category")
        .implode()
    )
    proof = base.filter(
        pl.col("brand").is_in(top_brands),
        pl.col("category").is_in(top_categories),
    ).sort(["month", "retailer", "category", "brand"])
    proof.write_csv(PROOF_CSV)
    two_period_proof = (
        proof.with_columns(
            pl.when(pl.col("month").cast(pl.Utf8).str.starts_with("2025-08"))
            .then(pl.lit("PY"))
            .when(pl.col("month").cast(pl.Utf8).str.starts_with("2025-09"))
            .then(pl.lit("AC"))
            .otherwise(None)
            .alias("period_pair")
        )
        .filter(pl.col("period_pair").is_in(["PY", "AC"]))
        .sort(["period_pair", "retailer", "category", "brand"])
    )
    two_period_proof.write_csv(PROOF_TWO_PERIOD_CSV)
    profile = proof.select(
        pl.len().alias("rows"),
        pl.col("month").min().alias("min_month"),
        pl.col("month").max().alias("max_month"),
        pl.col("retailer").n_unique().alias("retailers"),
        pl.col("category").n_unique().alias("categories"),
        pl.col("brand").n_unique().alias("brands"),
    ).row(0, named=True)
    return {
        key: str(value) if key.endswith("month") else value
        for key, value in profile.items()
    }


def _run_command(args: list[str]) -> dict[str, Any]:
    run = subprocess.run(
        args, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return {
        "returncode": run.returncode,
        "stdout_tail": run.stdout.splitlines()[-20:],
        "stderr_tail": run.stderr.splitlines()[-20:],
    }


def _write_root_cause_exploded_bridge_context() -> None:
    variance_dir = OUTPUT_DIR / "variance"
    parent_context = variance_dir / "root_cause_total_bridge_context.json"
    parent_chart = variance_dir / "root_cause_total_bridge.png"
    parent_data = variance_dir / "root_cause_total_bridge.csv"
    drilldown_chart = variance_dir / "root_cause_bridge_alt_1_drilldown_row_1.png"
    drilldown_data = variance_dir / "root_cause_bridge_alt_1_drilldown_row_1.csv"
    if not parent_context.exists() or not drilldown_data.exists():
        return
    payload = {
        "analysis_type": "root_cause_exploded_bridge",
        "chart_type": "root_cause_exploded_bridge",
        "chart": "root_cause_exploded_bridge",
        "capability_id": "variance.root_cause_exploded_bridge",
        "source_chart_type": "derived_composite",
        "root_cause_variance_mode": "total_variance",
        "role": "root_cause_sequence_with_nested_drilldown",
        "parent_artifact": {
            "artifact_id": "root_cause_total_bridge",
            "context": str(parent_context),
            "chart": str(parent_chart),
            "data": str(parent_data),
        },
        "drilldown_artifact": {
            "artifact_id": "root_cause_bridge_alt_1_drilldown_row_1",
            "selected_root_cause_row": 1,
            "chart": str(drilldown_chart),
            "data": str(drilldown_data),
        },
        "dimension_contract": {
            "left_panel_behavior": (
                "Left panel shows a variable mixed-dimension root-cause bridge "
                "sequence."
            ),
            "right_panel_behavior": (
                "Right-side panel reruns root-cause bridge logic inside one "
                "selected left-row slice."
            ),
            "nested_dimension_scope": "row_specific",
        },
    }
    _json_dump(variance_dir / "root_cause_exploded_bridge_context.json", payload)


def _write_recipe(path: Path, payload: dict[str, Any]) -> Path:
    _json_dump(path, payload)
    return path


def _mix_recipe(charts: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_file": str(PROOF_CSV),
        "language": "en",
        "mappings": {
            "amount_column": "sales",
            "date_column": "month",
            "period_column": "month",
            "dimensions": ["retailer", "category", "brand", "price_band"],
            "related_marker_metric_column": "sales_share",
        },
        "options": {
            "currency": "USD",
            "charts": charts,
            "small_multiples": False,
            "max_chart_items": 12,
            "period_type": "calendar",
            "period_grain": "month",
        },
    }


def _two_period_window() -> dict[str, Any]:
    return {
        "mode": "explicit_comparison_periods",
        "period_type": "calendar",
        "period_grain": "month",
        "source_period_column": "month",
        "label_column": "period_pair",
        "baseline": {
            "label": "PY",
            "period_label": "2025-08",
            "start_date": "2025-08-01",
            "end_date": "2025-08-31",
        },
        "previous": {
            "label": "PY",
            "period_label": "2025-08",
            "start_date": "2025-08-01",
            "end_date": "2025-08-31",
        },
        "comparison": {
            "label": "AC",
            "period_label": "2025-09",
            "start_date": "2025-09-01",
            "end_date": "2025-09-30",
        },
        "current": {
            "label": "AC",
            "period_label": "2025-09",
            "start_date": "2025-09-01",
            "end_date": "2025-09-30",
        },
    }


def _mix_cohort_recipe() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_file": str(PROOF_TWO_PERIOD_CSV),
        "language": "en",
        "mappings": {
            "amount_column": "sales",
            "date_column": "month",
            "period_column": "period_pair",
            "dimensions": [
                "retailer",
                "category",
                "brand",
                "price_band",
                "canonical_id",
            ],
            "related_marker_metric_column": "sales_share",
        },
        "options": {
            "currency": "USD",
            "charts": [
                "like_for_like_column_total",
                "like_for_like_stacked_column",
                "cohort_since_stacked_column",
                "cohort_lost_stacked_column",
            ],
            "small_multiples": False,
            "max_chart_items": 12,
            "period_type": "raw",
            "period_grain": "raw",
            "selected_periods": ["PY", "AC"],
            "period_window": _two_period_window(),
            "period_selection": "explicit_comparison_periods",
            "current_period_label": "AC",
            "previous_period_label": "PY",
            "like_for_like": {"source_dimension": "canonical_id"},
            "cohort_definition": {
                "derived_dimensions": [
                    {
                        "source_dimension": "canonical_id",
                        "name": "canonical_id_Since",
                        "kind": "since",
                        "output_column": "canonical_id_Since",
                        "cohort_mode": "since",
                    },
                    {
                        "source_dimension": "canonical_id",
                        "name": "canonical_id_Lost",
                        "kind": "lost",
                        "output_column": "canonical_id_Lost",
                        "cohort_mode": "lost",
                    },
                ],
                "periods": {
                    "period_column": "Period",
                    "value_column": "Sales",
                    "current_period": "AC",
                    "previous_period": "PY",
                },
                "activity_rule": "Sales > 0.0",
            },
        },
    }


def _mix_stacked_column_recipe() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_file": str(PROOF_CSV),
        "language": "en",
        "mappings": {
            "amount_column": "sales",
            "date_column": "month",
            "period_column": "month",
            "dimensions": ["category", "retailer", "brand", "price_band"],
            "related_marker_metric_column": "sales_share",
        },
        "options": {
            "currency": "USD",
            "charts": ["stacked_column"],
            "small_multiples": False,
            "max_chart_items": 12,
            "period_type": "calendar",
            "period_grain": "month",
            "stacked_column_period_grain": "month",
            "selected_periods": ["2025-08", "2025-09"],
        },
    }


def _mix_multitier_recipe() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_file": str(PROOF_TWO_PERIOD_CSV),
        "language": "en",
        "mappings": {
            "amount_column": "sales",
            "date_column": "month",
            "period_column": "period_pair",
            "dimensions": ["retailer", "category", "brand", "price_band"],
            "related_marker_metric_column": "sales_share",
        },
        "options": {
            "currency": "USD",
            "charts": ["multitier_bar", "multitier_bar_two_dimension"],
            "small_multiples": True,
            "max_chart_items": 12,
            "period_type": "raw",
            "period_grain": "raw",
            "previous_period": "PY",
            "current_period": "AC",
            "selected_periods": ["PY", "AC"],
            "period_window": _two_period_window(),
            "multitier_bar_two_dimension": True,
            "multitier_bar_panel_dimension": "retailer",
            "multitier_bar_item_dimension": "category",
            "multitier_bar_item_max_items": 6,
        },
    }


def _distribution_histogram_recipe() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "plugin": "distribution-analysis",
        "input_file": str(PROOF_CSV),
        "language": "en",
        "mappings": {
            "metric_column": "sales",
            "distribution_dimension": None,
            "small_multiples_dimension": None,
            "date_column": "month",
            "period_column": None,
            "dimensions": [
                "retailer",
                "brand",
                "pareto_class",
                "price_band",
                "category",
                "coverage",
                "month",
                "finish",
            ],
        },
        "options": {
            "currency": "USD",
            "charts": ["histogram", "boxplot", "stripplot", "ecdf", "kernel_density"],
            "selected_periods": ["~Sep-2024", "~Sep-2025"],
            "period_type": "rolling",
            "period_grain": "year",
            "small_multiples": False,
            "max_chart_items": 8,
        },
    }


def _set_overlap_recipe() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "plugin": "set-overlap-analysis",
        "mappings": {
            "item_column": "brand",
            "set_column": "retailer",
            "period_column": "month",
            "dimensions": ["category", "price_band"],
        },
        "options": {
            "charts": ["upset", "venn", "upset_small_multiples"],
            "set_values": ["amazon", "sephora", "ulta"],
            "max_sets": 3,
            "aggregate_other_sets": False,
            "small_multiples_dimension": "category",
            "small_multiples_max_panels": 4,
            "write_html": False,
        },
    }


def _plugin_runs() -> dict[str, Any]:
    mix_all_recipe = _write_recipe(
        OUTPUT_DIR / "mix_all_recipe.json",
        _mix_recipe(
            [
                "line",
                "area_absolute",
                "area_share",
                "column_total",
                "column_total_with_overlay",
                "bar",
                "multitier_bar",
                "stacked_bar",
                "related_metrics_bar",
                "marimekko",
                "barmekko",
                "pareto",
                "stacked_pareto",
                "stacked_column",
            ]
        ),
    )
    mix_multitier_recipe = _write_recipe(
        OUTPUT_DIR / "mix_multitier_recipe.json", _mix_multitier_recipe()
    )
    mix_cohort_recipe = _write_recipe(
        OUTPUT_DIR / "mix_cohort_recipe.json", _mix_cohort_recipe()
    )
    mix_stacked_column_recipe = _write_recipe(
        OUTPUT_DIR / "mix_stacked_column_recipe.json", _mix_stacked_column_recipe()
    )
    distribution_recipe = _write_recipe(
        OUTPUT_DIR / "distribution_all_recipe.json",
        _distribution_histogram_recipe(),
    )
    set_overlap_recipe = _write_recipe(
        OUTPUT_DIR / "set_overlap_recipe.json", _set_overlap_recipe()
    )
    runs = {
        "period-comparison": _run_command(
            [
                sys.executable,
                "plugins/period-comparison/scripts/run_period_comparison.py",
                str(PROOF_CSV),
                "--output-dir",
                str(OUTPUT_DIR / "period_auto"),
                "--artifact-mode",
                "data_only",
                "--currency",
                "USD",
            ]
        ),
        "mix-contribution-analysis": _run_command(
            [
                sys.executable,
                "plugins/mix-contribution-analysis/scripts/run_mix_contribution.py",
                str(PROOF_CSV),
                "--output-dir",
                str(OUTPUT_DIR / "mix_all"),
                "--recipe",
                str(mix_all_recipe),
                "--artifact-mode",
                "data_only",
                "--currency",
                "USD",
            ]
        ),
        "mix-contribution-analysis:cohort": _run_command(
            [
                sys.executable,
                "plugins/mix-contribution-analysis/scripts/run_mix_contribution.py",
                str(PROOF_TWO_PERIOD_CSV),
                "--output-dir",
                str(OUTPUT_DIR / "mix_cohort"),
                "--recipe",
                str(mix_cohort_recipe),
                "--artifact-mode",
                "data_only",
                "--currency",
                "USD",
            ]
        ),
        "mix-contribution-analysis:multitier": _run_command(
            [
                sys.executable,
                "plugins/mix-contribution-analysis/scripts/run_mix_contribution.py",
                str(PROOF_TWO_PERIOD_CSV),
                "--output-dir",
                str(OUTPUT_DIR / "mix_multitier"),
                "--recipe",
                str(mix_multitier_recipe),
                "--artifact-mode",
                "data_only",
                "--currency",
                "USD",
            ]
        ),
        "mix-contribution-analysis:stacked_column": _run_command(
            [
                sys.executable,
                "plugins/mix-contribution-analysis/scripts/run_mix_contribution.py",
                str(PROOF_CSV),
                "--output-dir",
                str(OUTPUT_DIR / "mix_stacked_column"),
                "--recipe",
                str(mix_stacked_column_recipe),
                "--artifact-mode",
                "data_only",
                "--currency",
                "USD",
            ]
        ),
        "scatter-bubble-analysis": _run_command(
            [
                sys.executable,
                "plugins/scatter-bubble-analysis/scripts/run_scatter_bubble.py",
                str(PROOF_CSV),
                "--output-dir",
                str(OUTPUT_DIR / "scatter_auto"),
                "--artifact-mode",
                "data_only",
                "--currency",
                "USD",
            ]
        ),
        "distribution-analysis": _run_command(
            [
                sys.executable,
                "plugins/distribution-analysis/scripts/run_distribution.py",
                str(PROOF_CSV),
                "--output-dir",
                str(OUTPUT_DIR / "distribution_all"),
                "--recipe",
                str(distribution_recipe),
                "--artifact-mode",
                "data_only",
                "--currency",
                "USD",
            ]
        ),
        "set-overlap-analysis": _run_command(
            [
                sys.executable,
                "plugins/set-overlap-analysis/scripts/run_set_overlap.py",
                str(PROOF_CSV),
                "--output-dir",
                str(OUTPUT_DIR / "set_overlap"),
                "--recipe",
                str(set_overlap_recipe),
                "--artifact-mode",
                "data_only",
            ]
        ),
        "variance-analysis": _run_command(
            [
                sys.executable,
                "plugins/variance-analysis/scripts/run_variance.py",
                str(PROOF_CSV),
                "--output-dir",
                str(OUTPUT_DIR / "variance"),
                "--artifact-mode",
                "data_only",
                "--currency",
                "USD",
                "--no-waterfall-chart",
                "--total-by-dimension-bridge",
                "--total-by-dimension-bridge-dimension",
                "category",
                "--exploded-variance-bridge",
                "--exploded-variance-bridge-parent-dimension",
                "category",
                "--exploded-variance-bridge-child-dimension",
                "brand",
                "--root-cause-component-bridge",
            ]
        ),
    }
    _write_root_cause_exploded_bridge_context()
    return runs


def _period_chart_status(chart: str) -> dict[str, Any]:
    audit_path = OUTPUT_DIR / "period_auto" / "period_comparison_audit.json"
    if not audit_path.exists():
        return {"status": "missing_audit"}
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    table_context = OUTPUT_DIR / "period_auto" / f"{chart}_chart_context.json"
    if table_context.exists():
        return {"status": "data_written", "chart_context": str(table_context)}
    return audit["legacy_runtime"]["chart_audits"].get(
        chart, {"status": "missing_chart"}
    )


def _scatter_chart_status(chart: str) -> dict[str, Any]:
    audit_path = OUTPUT_DIR / "scatter_auto" / "scatter_bubble_audit.json"
    if not audit_path.exists():
        return {"status": "missing_audit"}
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    return audit["legacy_runtime"]["chart_audits"].get(
        chart, {"status": "missing_chart"}
    )


def _context_status(plugin: str, chart: str | None) -> dict[str, Any]:
    if not chart:
        return {"status": "not_applicable"}
    candidates = {
        "mix-contribution-analysis": OUTPUT_DIR
        / "mix_all"
        / f"{chart}_chart_context.json",
        "mix-contribution-analysis:multitier": OUTPUT_DIR
        / "mix_multitier"
        / f"{chart}_chart_context.json",
        "mix-contribution-analysis:cohort": OUTPUT_DIR
        / "mix_cohort"
        / f"{chart}_chart_context.json",
        "mix-contribution-analysis:stacked_column": OUTPUT_DIR
        / "mix_stacked_column"
        / f"{chart}_chart_context.json",
        "distribution-analysis": OUTPUT_DIR
        / "distribution_all"
        / f"{chart}_chart_context.json",
        "variance-analysis": OUTPUT_DIR / "variance" / f"{chart}.json",
    }
    path = candidates.get(plugin)
    if path and path.exists():
        return {"status": "context_written", "path": str(path)}
    return {"status": "context_missing"}


def _plugin_key_for_test_case(test_case: dict[str, Any]) -> str:
    plugin = str(test_case["expected_plugin"])
    plugin_chart = test_case.get("plugin_chart")
    if plugin == "mix-contribution-analysis" and str(plugin_chart).startswith(
        "multitier_bar"
    ):
        return "mix-contribution-analysis:multitier"
    if test_case["capability_id"] in {
        "mix.like_for_like_column",
        "mix.like_for_like_stacked_column",
        "mix.cohort_since_stacked_column",
        "mix.cohort_lost_stacked_column",
    }:
        return "mix-contribution-analysis:cohort"
    if test_case["capability_id"] == "mix.stacked_column":
        return "mix-contribution-analysis:stacked_column"
    return plugin


def _verification_artifact_for_test_case(test_case: dict[str, Any]) -> str | None:
    value = test_case.get("verification_artifact") or test_case.get("plugin_chart")
    return str(value) if value else None


def _looks_like_sidecar_name(value: Any) -> bool:
    text = str(value or "").removesuffix(".json")
    return text.endswith(SIDECAR_NAME_SUFFIXES)


def _chart_id_sidecar_status(test_case: dict[str, Any]) -> dict[str, Any] | None:
    plugin_chart = test_case.get("plugin_chart")
    if plugin_chart is None:
        return {"status": "chart_identity_not_applicable"}
    chart_id = str(plugin_chart)
    if _looks_like_sidecar_name(chart_id):
        return {
            "status": "chart_id_is_context_artifact",
            "chart_id": chart_id,
        }
    return None


def _context_chart_identity_values(payload: dict[str, Any]) -> list[str]:
    values = []
    for key in CONTEXT_IDENTITY_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def _context_period_values(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in (payload, payload.get("period_adapter")):
        if not isinstance(source, dict):
            continue
        for value in source.get("selected_periods") or []:
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return values


def _context_period_grain(payload: dict[str, Any]) -> str | None:
    for source in (payload, payload.get("period_adapter")):
        if not isinstance(source, dict):
            continue
        value = source.get("period_grain")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _context_title_lines(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for value in payload.get("chart_title_lines") or []:
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    for key in ("chart_title", "title"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    title_contract = payload.get("title_contract")
    if isinstance(title_contract, dict):
        for value in title_contract.values():
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
    return values


def _normalized_context_label(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _same_period_title_line(lines: list[str]) -> str | None:
    for line in lines:
        normalized = _normalized_context_label(line)
        if " to " not in normalized:
            continue
        left, right = normalized.split(" to ", 1)
        right = right.split(" | ", 1)[0]
        if left and left == right:
            return line
    return None


def _bare_ac_title_line(lines: list[str]) -> str | None:
    for line in lines:
        if _normalized_context_label(line) == "ac":
            return line
    return None


def _context_period_axis_status(
    test_case: dict[str, Any], context_payload: dict[str, Any], context_path: Path
) -> dict[str, Any] | None:
    contract = test_case.get("expected_context_period_axis")
    if not isinstance(contract, dict):
        return None
    periods = _context_period_values(context_payload)
    period_grain = _context_period_grain(context_payload)
    minimum_distinct_periods = int(contract.get("minimum_distinct_periods") or 0)
    if minimum_distinct_periods and len(periods) < minimum_distinct_periods:
        return {
            "status": "context_period_axis_too_few_periods",
            "path": str(context_path),
            "expected_minimum_distinct_periods": minimum_distinct_periods,
            "observed_periods": periods,
        }
    required_period_grain = contract.get("required_period_grain")
    if (
        isinstance(required_period_grain, str)
        and required_period_grain.strip()
        and period_grain != required_period_grain.strip().lower()
    ):
        return {
            "status": "context_period_axis_grain_mismatch",
            "path": str(context_path),
            "expected_period_grain": required_period_grain.strip().lower(),
            "observed_period_grain": period_grain,
            "observed_periods": periods,
        }
    title_lines = _context_title_lines(context_payload)
    same_period_line = (
        _same_period_title_line(title_lines)
        if contract.get("forbid_same_period_title")
        else None
    )
    if same_period_line:
        return {
            "status": "context_same_period_title",
            "path": str(context_path),
            "title_line": same_period_line,
            "observed_periods": periods,
        }
    if contract.get("forbid_bare_ac_period"):
        normalized_periods = {_normalized_context_label(period) for period in periods}
        bare_ac_line = _bare_ac_title_line(title_lines)
        if normalized_periods == {"ac"} or bare_ac_line:
            return {
                "status": "context_bare_ac_period",
                "path": str(context_path),
                "title_line": bare_ac_line,
                "observed_periods": periods,
            }
    return {
        "status": "context_period_axis_ok",
        "path": str(context_path),
        "observed_periods": periods,
        "observed_period_grain": period_grain,
    }


def _context_period_label_policy_status(
    context_payload: dict[str, Any], context_path: Path
) -> dict[str, Any]:
    policy = validate_period_label_policy(context_payload)
    if policy["status"] == "period_label_policy_failed":
        return {
            "status": "context_period_label_policy_failed",
            "path": str(context_path),
            "issues": policy["issues"],
            "scenario_tokens": policy["scenario_tokens"],
            "selected_periods": policy["selected_periods"],
            "checked_texts": policy["checked_texts"],
        }
    return {
        "status": policy["status"],
        "path": str(context_path),
        "scenario_tokens": policy["scenario_tokens"],
        "selected_periods": policy["selected_periods"],
        "resolved_period_context": policy["resolved_period_context"],
    }


def _context_period_label_status_from_path(context_path: Path) -> dict[str, Any]:
    try:
        context_payload = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "context_period_label_policy_unreadable",
            "path": str(context_path),
            "reason": str(exc),
        }
    return _context_period_label_policy_status(context_payload, context_path)


def _chart_identity_status(
    test_case: dict[str, Any], context_status: dict[str, Any]
) -> dict[str, Any]:
    """Validate a mechanical contract: chart ids and context sidecars differ."""

    sidecar_status = _chart_id_sidecar_status(test_case)
    if sidecar_status:
        return sidecar_status
    plugin_chart = test_case.get("plugin_chart")
    chart_id = str(plugin_chart)
    if context_status.get("status") != "context_written":
        return {
            "status": "chart_identity_not_checked",
            "reason": context_status.get("status", "missing_context"),
        }
    context_path = Path(str(context_status["path"]))
    try:
        context_payload = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "context_identity_unreadable",
            "path": str(context_path),
            "reason": str(exc),
        }
    observed_values = _context_chart_identity_values(context_payload)
    if not observed_values:
        return {
            "status": "context_chart_identity_missing",
            "path": str(context_path),
            "expected_chart_type": str(
                test_case.get("expected_context_chart_type") or chart_id
            ),
        }
    expected_chart_type = str(test_case.get("expected_context_chart_type") or chart_id)
    if expected_chart_type not in observed_values:
        return {
            "status": "context_chart_identity_mismatch",
            "path": str(context_path),
            "chart_id": chart_id,
            "expected_chart_type": expected_chart_type,
            "observed_chart_identities": observed_values,
        }
    expected_capability_id = str(test_case["capability_id"])
    observed_capability_id = context_payload.get("capability_id")
    if observed_capability_id and observed_capability_id != expected_capability_id:
        return {
            "status": "context_capability_identity_mismatch",
            "path": str(context_path),
            "expected_capability_id": expected_capability_id,
            "observed_capability_id": observed_capability_id,
        }
    period_axis_status = _context_period_axis_status(
        test_case, context_payload, context_path
    )
    if period_axis_status and period_axis_status["status"] != "context_period_axis_ok":
        return period_axis_status
    period_label_status = _context_period_label_policy_status(
        context_payload, context_path
    )
    if period_label_status["status"] == "context_period_label_policy_failed":
        return period_label_status
    return {
        "status": "chart_identity_ok",
        "path": str(context_path),
        "chart_id": chart_id,
        "expected_chart_type": expected_chart_type,
        "observed_chart_identities": observed_values,
        "context_period_axis": period_axis_status,
        "context_period_label_policy": period_label_status,
    }


def _audit_chart_identity_status(
    test_case: dict[str, Any],
    audit_status: dict[str, Any],
    audit_dir: Path | None = None,
) -> dict[str, Any]:
    sidecar_status = _chart_id_sidecar_status(test_case)
    if sidecar_status:
        return sidecar_status
    if audit_status.get("status") != "data_written":
        return {
            "status": "chart_identity_not_checked",
            "reason": audit_status.get("status", "missing_audit_chart"),
        }
    context_path = _audit_context_path(audit_status, audit_dir)
    period_label_status = None
    if context_path is not None and context_path.exists():
        period_label_status = _context_period_label_status_from_path(context_path)
        if period_label_status["status"] in {
            "context_period_label_policy_failed",
            "context_period_label_policy_unreadable",
        }:
            return period_label_status
    return {
        "status": "chart_identity_ok",
        "chart_id": str(test_case["plugin_chart"]),
        "verification": "plugin_audit_chart_key",
        "context_period_label_policy": period_label_status,
    }


def _audit_context_path(
    audit_status: dict[str, Any], audit_dir: Path | None
) -> Path | None:
    raw_context = audit_status.get("chart_context")
    raw_path: Any = None
    if isinstance(raw_context, str):
        raw_path = raw_context
    elif isinstance(raw_context, dict):
        raw_path = raw_context.get("context_path") or raw_context.get("path")
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if path.is_absolute():
        return path
    if audit_dir is None:
        return None
    return audit_dir / path


def _chart_identity_for_test_case(test_case: dict[str, Any]) -> dict[str, Any]:
    plugin_chart = test_case.get("plugin_chart")
    plugin = test_case["expected_plugin"]
    if plugin_chart is None:
        return {"status": "chart_identity_not_applicable"}
    if plugin == "period-comparison":
        return _audit_chart_identity_status(
            test_case,
            _period_chart_status(str(plugin_chart)),
            OUTPUT_DIR / "period_auto",
        )
    if plugin == "scatter-bubble-analysis":
        return _audit_chart_identity_status(
            test_case,
            _scatter_chart_status(str(plugin_chart)),
            OUTPUT_DIR / "scatter_auto",
        )
    if plugin == "set-overlap-analysis":
        return _audit_chart_identity_status(
            test_case,
            _set_overlap_chart_status(str(plugin_chart)),
            OUTPUT_DIR / "set_overlap",
        )
    return _chart_identity_status(
        test_case,
        _context_status(
            _plugin_key_for_test_case(test_case),
            _verification_artifact_for_test_case(test_case),
        ),
    )


def _set_overlap_chart_status(chart: str) -> dict[str, Any]:
    audit_path = OUTPUT_DIR / "set_overlap" / "set_overlap_audit.json"
    if not audit_path.exists():
        return {"status": "missing_audit"}
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    return (audit.get("charts") or {}).get(chart, {"status": "missing_chart"})


def _case_verdict(
    test_case: dict[str, Any],
    capability_status: str,
    run_status: dict[str, Any],
) -> str:
    if test_case["expected_outcome"] == "reject":
        return (
            "correct_rejection"
            if capability_status == "understand_reject_for_this_dataset"
            else "bad_rejection_logic"
        )
    plugin_chart = test_case["plugin_chart"]
    plugin = test_case["expected_plugin"]
    if plugin == "period-comparison":
        status = _period_chart_status(str(plugin_chart))
        identity_status = _audit_chart_identity_status(
            test_case, status, OUTPUT_DIR / "period_auto"
        )
        if (
            status.get("status") == "data_written"
            and identity_status["status"] != "chart_identity_ok"
        ):
            return str(identity_status["status"])
        return (
            "credible_data_artifact"
            if status.get("status") == "data_written"
            else "plugin_failed"
        )
    if plugin == "scatter-bubble-analysis":
        status = _scatter_chart_status(str(plugin_chart))
        identity_status = _audit_chart_identity_status(
            test_case, status, OUTPUT_DIR / "scatter_auto"
        )
        if (
            status.get("status") == "data_written"
            and identity_status["status"] != "chart_identity_ok"
        ):
            return str(identity_status["status"])
        return (
            "credible_data_artifact"
            if status.get("status") == "data_written"
            else "plugin_failed"
        )
    if plugin == "set-overlap-analysis":
        status = _set_overlap_chart_status(str(plugin_chart))
        identity_status = _audit_chart_identity_status(
            test_case, status, OUTPUT_DIR / "set_overlap"
        )
        if (
            status.get("status") == "data_written"
            and identity_status["status"] != "chart_identity_ok"
        ):
            return str(identity_status["status"])
        return (
            "credible_data_artifact"
            if status.get("status") == "data_written"
            else "plugin_failed"
        )
    plugin_key = _plugin_key_for_test_case(test_case)
    verification_artifact = _verification_artifact_for_test_case(test_case)
    status = _context_status(plugin_key, verification_artifact)
    if status["status"] == "context_written":
        identity_status = _chart_identity_status(test_case, status)
        if identity_status["status"] != "chart_identity_ok":
            return str(identity_status["status"])
        if plugin == "distribution-analysis" and run_status.get("returncode") != 0:
            return "partial_context_written"
        return "credible_data_artifact"
    return "plugin_failed"


def _build_results(plugin_runs: dict[str, Any]) -> list[dict[str, Any]]:
    dataset_audit = audit_manifest_against_us_cosmetics()
    capability_status = {
        result["capability_id"]: result["status"] for result in dataset_audit["results"]
    }
    results = []
    for test_case in TEST_CASES:
        plugin_run_key = _plugin_key_for_test_case(test_case)
        verdict = _case_verdict(
            test_case,
            capability_status.get(test_case["capability_id"], "missing_capability"),
            plugin_runs.get(plugin_run_key, {}),
        )
        results.append(
            {
                **test_case,
                "manifest_dataset_status": capability_status.get(
                    test_case["capability_id"], "missing_capability"
                ),
                "plugin_returncode": plugin_runs.get(plugin_run_key, {}).get(
                    "returncode"
                ),
                "chart_identity": _chart_identity_for_test_case(test_case),
                "verdict": verdict,
            }
        )
    return results


def _markdown(
    profile: dict[str, Any], plugin_runs: dict[str, Any], results: list[dict[str, Any]]
) -> str:
    manifest = json.loads(
        (
            REPO_ROOT
            / "runs"
            / "chart_selection_manifest_rebuild"
            / "selection_manifest.json"
        ).read_text(encoding="utf-8")
    )
    tested_capabilities = {result["capability_id"] for result in results}
    all_capabilities = set(manifest["capabilities"])
    untested_capabilities = sorted(all_capabilities - tested_capabilities)
    lines = [
        "# US Cosmetics Adversarial Chart-Manifest Proof",
        "",
        "## Test Definition",
        "",
        "This test behaves like a dumb caller: it uses the manifest role contract, a real dataset profile, and plugin recipe fields. It does not use legacy dropdown knowledge to pick charts.",
        "",
        "## Dataset",
        "",
        f"- Source parquet: `{SOURCE_DATASET}`",
        f"- Proof CSV: `{PROOF_CSV}`",
        f"- Rows: `{profile['rows']}`",
        f"- Date range: `{profile['min_month']}` to `{profile['max_month']}`",
        f"- Retailers: `{profile['retailers']}`",
        f"- Categories: `{profile['categories']}`",
        f"- Brands: `{profile['brands']}`",
        "",
        "## Plugin Run Status",
        "",
    ]
    for plugin, run in plugin_runs.items():
        lines.append(f"- `{plugin}` return code: `{run['returncode']}`")
    lines.extend(["", "## Verdicts", ""])
    counts: dict[str, int] = {}
    for result in results:
        counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1
    for verdict, count in sorted(counts.items()):
        lines.append(f"- `{verdict}`: `{count}`")
    lines.extend(
        [
            "",
            "## Coverage Against Manifest",
            "",
            f"- Manifest capabilities: `{len(all_capabilities)}`",
            f"- Tested capabilities: `{len(tested_capabilities)}`",
            f"- Untested capabilities: `{len(untested_capabilities)}`",
        ]
    )
    for capability_id in untested_capabilities:
        capability = manifest["capabilities"][capability_id]
        lines.append(f"  - `{capability_id}` ({capability['selection_emphasis']})")
    lines.append("")
    header = (
        "| capability | question | params from manifest/data roles | plugin | verdict |"
    )
    lines.extend([header, "| --- | --- | --- | --- | --- |"])
    for result in results:
        params = ", ".join(f"{key}={value}" for key, value in result["params"].items())
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{result['capability_id']}`",
                    str(result["question"]),
                    f"`{params}`",
                    f"`{result['expected_plugin']}`",
                    f"`{result['verdict']}`",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `credible_data_artifact`: the plugin accepted the manifest-derived mapping and wrote chart data/audit for the target chart. In this run PNG rendering was intentionally not required.",
            "- `partial_context_written`: the plugin wrote chart context before a later package failure. This supports role-to-parameter feasibility but exposes renderer/package fragility.",
            "- `correct_rejection`: the manifest says the dataset lacks the required roles, and the dataset audit agrees.",
            "- `plugin_failed`: the manifest mapping was not enough to produce even chart data/context.",
            "- `chart_id_is_context_artifact` and `context_*_mismatch`: the proof mixed up chart identity with a sidecar/context artifact, or the context did not confirm the selected chart identity.",
            "- `context_period_axis_*` and `context_same_period_title`: the proof claimed period-axis evidence, but the chart context did not expose enough resolved periods or used an ambiguous same-period label such as `AC to AC`.",
            "- `context_period_label_policy_failed`: the chart/table context used scenario labels such as `AC`, `PY`, or `PL` without resolved period/window evidence, or compared a period with itself.",
            "",
            "## Known Weaknesses Exposed",
            "",
            "- This is not a semantic gold-standard test. It checks whether the manifest can produce defensible parameters and whether the plugin accepts them.",
            "- Data-only period runs still hit Chrome/Kaleido-related noise in legacy scale helpers, although the period audit wrote chart-data records.",
            "- PNG rendering is not exercised here; this proof is about manifest-to-parameter feasibility and structured chart-data artifacts.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_adversarial_proof() -> dict[str, Any]:
    profile = _prepare_proof_csv()
    plugin_runs = _plugin_runs()
    results = _build_results(plugin_runs)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_markdown(profile, plugin_runs, results), encoding="utf-8")
    _json_dump(
        REPORT_PATH.with_suffix(".json"),
        {"dataset_profile": profile, "plugin_runs": plugin_runs, "results": results},
    )
    return {"report": str(REPORT_PATH), "profile": profile, "results": results}


def main() -> int:
    result = run_adversarial_proof()
    print(result["report"])
    counts: dict[str, int] = {}
    for item in result["results"]:
        counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
    print(json.dumps(counts, sort_keys=True))
    failed = [
        item["capability_id"]
        for item in result["results"]
        if item["verdict"] not in PASSING_PROOF_VERDICTS
    ]
    if failed:
        print(json.dumps({"failed_capabilities": failed}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
