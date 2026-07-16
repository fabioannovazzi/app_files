from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import polars as pl

__all__ = ["audit_manifest_against_us_cosmetics", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    REPO_ROOT / "runs" / "chart_selection_manifest_rebuild" / "selection_manifest.json"
)
DEFAULT_DATASET = (
    REPO_ROOT
    / "data"
    / "pdp"
    / "sales_data"
    / "joined_datasets"
    / "us_cosmetics"
    / "joined.parquet"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "runs"
    / "chart_selection_manifest_rebuild"
    / "us_cosmetics_orchestrator_audit.md"
)


ROLE_COVERAGE: dict[str, tuple[str, str]] = {
    "comparison_metric": ("direct", "sales or units"),
    "variance_metric": ("direct", "sales or units"),
    "distribution_metric": (
        "direct",
        "sales, units, sales_share, cumulative_sales_share, pareto_rank, price_raw, avg_price, asp, or product_count",
    ),
    "primary_metric": ("direct", "sales or units"),
    "primary_additive_metric": ("direct", "sales or units"),
    "related_marker_metric": (
        "direct",
        "sales_share, cumulative_sales_share, pareto_rank, price_raw, or price_band",
    ),
    "x_metric": (
        "direct",
        "sales, units, sales_share, cumulative_sales_share, or price_raw",
    ),
    "y_metric": ("direct", "Any second numeric metric, e.g. units or sales_share"),
    "size_metric": ("direct", "Any third numeric metric, e.g. sales or units"),
    "current_period_metric": (
        "derived",
        "sales or units aggregated for the current month window",
    ),
    "baseline_period_metric": (
        "derived",
        "sales or units aggregated for a prior month or previous-year month window",
    ),
    "current_metric": (
        "derived",
        "sales, units, or share aggregated for current month window",
    ),
    "baseline_metric": (
        "derived",
        "sales, units, or share aggregated for baseline month window",
    ),
    "delta_metric": (
        "derived",
        "Current minus baseline after month/category aggregation",
    ),
    "percent_delta_metric": ("derived", "Delta divided by baseline after aggregation"),
    "value_metric": ("direct", "sales"),
    "volume_metric": ("direct", "units"),
    "price_or_rate_metric": ("derived", "sales divided by units, or direct price_raw"),
    "width_metric": ("direct", "sales, units, sales_share, or cumulative_sales_share"),
    "height_metric": (
        "direct",
        "units, price_raw, sales_share, cumulative_sales_share, or pareto_rank",
    ),
    "area_metric": ("derived", "Width metric times height metric"),
    "stage_start_count": ("missing", "No ordered funnel stage count columns"),
    "stage_pass_count": ("missing", "No ordered funnel stage pass columns"),
    "dropoff_count": ("missing", "No ordered funnel dropoff columns"),
    "conversion_rate": ("missing", "No ordered funnel conversion-rate columns"),
    "statement_value": ("missing", "No financial statement line-item table"),
    "focus_share": (
        "derived",
        "Attribute sales share by finish, coverage, benefit, shade, form, or price band",
    ),
    "baseline_share": (
        "derived",
        "Baseline sales share by comparable attribute bundle",
    ),
    "index_metric": ("derived", "Focus share divided by baseline share"),
    "current_signal_metric": (
        "derived",
        "Current-window sales, sales_share, pareto_class, or pareto_rank by product/attribute",
    ),
    "emerging_signal_metric": (
        "derived",
        "Recent-month, new_now, or improving product/attribute signal from sales history",
    ),
    "alignment_metric": (
        "derived",
        "Overlap or distance between current winners and emerging attributes/products",
    ),
    "gross_weight": ("direct", "sales_share or cumulative_sales_share"),
    "incremental_weight": ("direct", "sales_share"),
    "cumulative_weight": ("direct", "cumulative_sales_share"),
    "robustness_metric": (
        "derived",
        "Sales/share consistency across months, retailers, or categories",
    ),
    "product_signal_score": (
        "derived",
        "Product-level score from sales, sales_share, pareto_rank, and attribute presence",
    ),
    "validation_metric": (
        "derived",
        "Validation from holdout months, retailer agreement, or sales/share consistency",
    ),
    "category": (
        "direct",
        "retailer, merchant, category, category_key, brand, finish, coverage, shade family, benefits",
    ),
    "component_category": (
        "direct",
        "retailer, category, brand, finish, coverage, shade family, benefits, or price_band",
    ),
    "component_dimension": (
        "direct",
        "retailer, category, brand, finish, coverage, shade family, benefits, or product",
    ),
    "nested_category": (
        "direct",
        "retailer -> category -> brand -> product, or category -> attribute -> product",
    ),
    "width_category": (
        "direct",
        "retailer, category, brand, price_band, or attribute bundle",
    ),
    "stack_category": (
        "direct",
        "brand, retailer, category, price_band, finish, or coverage",
    ),
    "height_category": (
        "direct",
        "retailer, category, brand, price_band, finish, or coverage",
    ),
    "point_dimension": (
        "direct",
        "canonical_id, variant_id, product_name, brand, or category",
    ),
    "comparison_series": (
        "derived",
        "Current and baseline month windows, or retailer/merchant split",
    ),
    "comparison_item": (
        "direct",
        "retailer, category, brand, product, price_band, or attribute",
    ),
    "comparison_window": ("derived", "Month windows from month"),
    "bridge_component_period": ("derived", "Monthly deltas from month"),
    "stable_population_flag": (
        "derived",
        "canonical_id or variant_id present in both current and baseline month windows",
    ),
    "first_active_cohort": ("derived", "First month by canonical_id or variant_id"),
    "lost_or_last_active_cohort": (
        "derived",
        "Last month by canonical_id or variant_id",
    ),
    "variance_driver": (
        "direct",
        "retailer, category, brand, product, price_band, finish, coverage, shade family, or benefits",
    ),
    "dimension_member": (
        "direct",
        "Members of retailer, category, brand, product, price_band, finish, coverage, or benefits",
    ),
    "parent_driver": ("direct", "retailer, category, brand, or product_collection"),
    "child_driver": (
        "direct",
        "brand, product, canonical_id, variant_id, finish, coverage, shade family, or benefits",
    ),
    "root_cause_driver": (
        "derived",
        "Candidate drivers ranked by period sales or units delta",
    ),
    "component": (
        "direct",
        "retailer, category, brand, price_band, finish, coverage, or benefits",
    ),
    "component_driver": (
        "direct",
        "brand, product, canonical_id, variant_id, finish, coverage, shade family, or benefits",
    ),
    "scenario_or_period_pair": ("derived", "Current and baseline month windows"),
    "set_membership_fields": (
        "derived",
        "Product or brand membership across retailers, categories, price bands, or attributes",
    ),
    "panel_or_segment": (
        "direct",
        "retailer, category, brand, price_band, pareto_class, or attribute",
    ),
    "two_or_three_set_membership_fields": (
        "derived",
        "Product or brand membership across two or three retailers, categories, or attributes",
    ),
    "ordered_stage": ("missing", "No ordered funnel stage column"),
    "statement_line_item": ("missing", "No statement line-item column"),
    "attribute_bundle": (
        "direct",
        "finish, coverage, shade family, benefits, claims, form, product type, or price_band",
    ),
    "signal_bundle": (
        "derived",
        "Product/attribute bundle combining sales/share/pareto fields with attribute columns",
    ),
    "cohort_layer": (
        "derived",
        "new_now, first month, last month, or current/emerging month layer",
    ),
    "rank_or_lane": (
        "direct",
        "pareto_rank, pareto_class, pareto_bucket, or price_band",
    ),
    "product": (
        "direct",
        "product_name, canonical_id, variant_id, sku, or product_description",
    ),
}


PROFILE_COLUMNS = (
    "retailer",
    "category",
    "category_key",
    "brand",
    "price_band",
    "pareto_class",
    "finish",
    "coverage",
    "shade family",
    "benefits",
)


def _dataset_profile(dataset_path: Path) -> dict[str, Any]:
    lf = pl.scan_parquet(dataset_path)
    schema = lf.collect_schema()
    columns = schema.names()
    summary = lf.select(
        pl.len().alias("rows"),
        pl.col("month").min().alias("min_month"),
        pl.col("month").max().alias("max_month"),
        pl.col("retailer").n_unique().alias("retailers"),
        pl.col("category").n_unique().alias("categories"),
        pl.col("brand").n_unique().alias("brands"),
        pl.col("canonical_id").n_unique().alias("canonical_products"),
        pl.col("variant_id").n_unique().alias("variants"),
        pl.col("sales").sum().alias("sales_sum"),
        pl.col("units").sum().alias("units_sum"),
    ).collect()
    row = summary.row(0, named=True)
    samples: dict[str, list[Any]] = {}
    for column in PROFILE_COLUMNS:
        if column not in columns:
            continue
        values = (
            lf.group_by(column)
            .len()
            .sort("len", descending=True)
            .limit(8)
            .collect()
            .get_column(column)
            .to_list()
        )
        samples[column] = [value for value in values if value is not None]
    return {
        "path": str(dataset_path),
        "rows": row["rows"],
        "columns": columns,
        "date_range": [str(row["min_month"]), str(row["max_month"])],
        "retailers": row["retailers"],
        "categories": row["categories"],
        "brands": row["brands"],
        "canonical_products": row["canonical_products"],
        "variants": row["variants"],
        "sales_sum": row["sales_sum"],
        "units_sum": row["units_sum"],
        "sample_distinct_values": samples,
    }


def _role_coverage(role: str) -> tuple[str, str]:
    return ROLE_COVERAGE.get(role, ("unknown", "No mapping in this dataset audit."))


def _capability_result(capability: dict[str, Any]) -> dict[str, Any]:
    contract = capability["selection_contract"]
    requirements = contract["dataset_requirements"]
    metric_requirements = requirements["metrics"]
    source_metric_roles = [
        role["role"]
        for role in metric_requirements["source_metric_roles"]
        if role.get("required", True)
    ]
    derived_metric_roles = [
        role["role"] for role in metric_requirements["derived_metric_roles"]
    ]
    roles = source_metric_roles + list(requirements["dimensions"]["required_roles"])
    covered = [_role_coverage(role) for role in roles]
    states = {state for state, _detail in covered}
    if "unknown" in states:
        status = "manifest_role_unmapped_in_audit"
    elif "missing" in states:
        status = "understand_reject_for_this_dataset"
    elif "derived" in states:
        status = "understand_use_after_aggregation_or_derivation"
    else:
        status = "understand_use_directly_after_role_mapping"
    return {
        "capability_id": capability["capability_id"],
        "selection_emphasis": capability["selection_emphasis"],
        "status": status,
        "required_roles": roles,
        "source_metric_roles": source_metric_roles,
        "derived_metric_roles": derived_metric_roles,
        "role_coverage": [
            {"role": role, "status": state, "evidence": detail}
            for role, (state, detail) in zip(roles, covered)
        ],
        "period": requirements["period"],
        "accept_when": contract["accept_when"],
        "reject_when": contract["reject_when"],
    }


def audit_manifest_against_us_cosmetics(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    dataset_path: Path = DEFAULT_DATASET,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = [
        _capability_result(capability)
        for capability in manifest["capabilities"].values()
    ]
    results_by_capability = {result["capability_id"]: result for result in results}
    artifact_results = []
    for artifact in manifest["artifacts"]:
        capability_id = artifact["capability_id"]
        capability_result = results_by_capability[capability_id]
        artifact_results.append(
            {
                "label": artifact["label"],
                "capability_id": capability_id,
                "status": capability_result["status"],
                "selection_emphasis": capability_result["selection_emphasis"],
                "output": artifact["output"],
                "role_coverage": capability_result["role_coverage"],
                "period": capability_result["period"],
            }
        )
    return {
        "dataset": _dataset_profile(dataset_path),
        "summary": dict(Counter(result["status"] for result in results)),
        "artifact_summary": dict(
            Counter(result["status"] for result in artifact_results)
        ),
        "results": sorted(results, key=lambda item: item["capability_id"]),
        "artifact_results": sorted(
            artifact_results,
            key=lambda item: (item["status"], item["label"]),
        ),
    }


def _markdown(audit: dict[str, Any]) -> str:
    dataset = audit["dataset"]
    lines = [
        "# US Cosmetics Orchestrator Manifest Audit",
        "",
        "## Dataset",
        "",
        f"- Path: `{dataset['path']}`",
        f"- Rows: `{dataset['rows']}`",
        f"- Date range: `{dataset['date_range'][0]}` to `{dataset['date_range'][1]}`",
        f"- Columns: `{len(dataset['columns'])}`",
        f"- Retailers: `{dataset['retailers']}`",
        f"- Categories: `{dataset['categories']}`",
        f"- Brands: `{dataset['brands']}`",
        f"- Canonical products: `{dataset['canonical_products']}`",
        f"- Variants: `{dataset['variants']}`",
        f"- Sales sum: `{dataset['sales_sum']}`",
        f"- Units sum: `{dataset['units_sum']}`",
        "",
        "## Sample Distinct Values",
        "",
    ]
    for column, values in sorted(dataset["sample_distinct_values"].items()):
        value_text = ", ".join(f"`{value}`" for value in values)
        lines.append(f"- `{column}`: {value_text}")
    lines.extend(["", "## Summary", ""])
    for status, count in sorted(audit["summary"].items()):
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Artifact Summary", ""])
    for status, count in sorted(audit["artifact_summary"].items()):
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Capability Results", ""])
    for result in audit["results"]:
        lines.append(
            f"- `{result['capability_id']}` -> `{result['status']}` "
            f"({result['selection_emphasis']})"
        )
        lines.append(f"  - Period: `{result['period']['role']}`")
        if result["required_roles"]:
            role_text = ", ".join(
                f"`{entry['role']}`={entry['status']}"
                for entry in result["role_coverage"]
            )
            lines.append(f"  - Required roles: {role_text}")
        else:
            lines.append("  - Required roles: none")
        lines.append(f"  - Use: {result['accept_when']}")
        lines.append(f"  - Reject: {result['reject_when']}")
    lines.extend(["", "## Artifact Results", ""])
    for result in audit["artifact_results"]:
        lines.append(
            f"- `{result['label']}` -> `{result['status']}` "
            f"via `{result['capability_id']}` ({result['selection_emphasis']})"
        )
        lines.append(f"  - Output: `{result['output']}`")
        lines.append(f"  - Period: `{result['period']['role']}`")
        if result["role_coverage"]:
            role_text = ", ".join(
                f"`{entry['role']}`={entry['status']}"
                for entry in result["role_coverage"]
            )
            lines.append(f"  - Required roles: {role_text}")
        else:
            lines.append("  - Required roles: none")
    return "\n".join(lines) + "\n"


def main() -> int:
    audit = audit_manifest_against_us_cosmetics()
    DEFAULT_OUTPUT.write_text(_markdown(audit), encoding="utf-8")
    print(DEFAULT_OUTPUT)
    print(json.dumps(audit["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
