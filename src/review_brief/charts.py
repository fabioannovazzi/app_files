from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Literal, Sequence

import polars as pl

from modules.utilities.utils import get_schema_and_column_names

from .models import ChartPayload, ChartUniverse, DimensionSpec

__all__ = [
    "ChartBuildError",
    "ChartCandidate",
    "build_brand_attribute_slope",
    "build_total_combo_absolute",
    "build_dimension_stacked_absolute",
    "build_dimension_stacked",
    "build_dimension_stacked_facets",
    "choose_pair_attributes",
    "compute_month_range",
    "make_chart_id",
]


class ChartBuildError(RuntimeError):
    """Raised when chart inputs are missing or invalid."""


@dataclass(frozen=True, slots=True)
class ChartCandidate:
    chart: ChartPayload
    csv_rows: list[dict[str, object]]


def make_chart_id(parts: Sequence[str]) -> str:
    joined = "|".join(str(p).strip() for p in parts if str(p).strip())
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]
    safe_prefix = "_".join(
        "".join(ch for ch in str(p).lower() if ch.isalnum() or ch in {"-", "_"}).strip(
            "_-"
        )
        for p in parts[:3]
        if str(p).strip()
    )
    safe_prefix = safe_prefix[:60] if safe_prefix else "chart"
    return f"{safe_prefix}_{digest}"


def _canonical_csv(values: Iterable[str]) -> str:
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    unique = sorted(set(cleaned), key=str.casefold)
    return ",".join(unique)


def _canonical_placeholders(values: set[str]) -> str:
    return _canonical_csv(sorted(values))


def compute_month_range(joined: pl.DataFrame) -> tuple[date, date]:
    columns, _schema = get_schema_and_column_names(joined)
    if joined.is_empty() or "month" not in columns:
        raise ChartBuildError("Missing sales month data.")
    min_month = joined.select(pl.col("month").min()).item()
    max_month = joined.select(pl.col("month").max()).item()
    if not isinstance(min_month, date) or not isinstance(max_month, date):
        raise ChartBuildError("Month range not available.")
    return min_month, max_month


def _sorted_months(joined: pl.DataFrame) -> list[date]:
    columns, _schema = get_schema_and_column_names(joined)
    if joined.is_empty() or "month" not in columns:
        raise ChartBuildError("Missing sales month data.")
    months = joined.select(pl.col("month").drop_nulls().unique()).to_series().to_list()
    month_values = [m for m in months if isinstance(m, date)]
    if not month_values:
        raise ChartBuildError("Month range not available.")
    month_values.sort()
    return month_values


def _clean_dim(col: str, placeholder_values: set[str]) -> pl.Expr:
    raw = pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars()
    lowered = raw.str.to_lowercase()
    placeholders = list(sorted(placeholder_values))
    return (
        pl.when(raw.is_null() | (raw == "") | lowered.is_in(placeholders))
        .then(pl.lit("N/A"))
        .otherwise(raw)
        .alias(col)
    )


def _compute_monthly_share(
    joined: pl.DataFrame,
    *,
    dims: Sequence[str],
    denom_dims: Sequence[str],
    placeholder_values: set[str],
) -> pl.DataFrame:
    if not dims:
        raise ChartBuildError("At least one dimension is required.")
    if not set(denom_dims).issubset(set(dims)):
        raise ChartBuildError("denom_dims must be a subset of dims.")
    columns, _schema = get_schema_and_column_names(joined)
    missing = [col for col in ("month", "sales", *dims) if col not in columns]
    if missing:
        raise ChartBuildError(f"Missing columns for share computation: {missing}")

    cleaned = joined.select(["month", "sales", *dims]).with_columns(
        [_clean_dim(col, placeholder_values) for col in dims]
    )
    numer = (
        cleaned.group_by(["month", *dims])
        .agg(pl.col("sales").sum().alias("sales"))
        .sort(["month", *dims])
    )

    denom_cols = ["month", *denom_dims]
    denom = (
        cleaned.group_by(denom_cols)
        .agg(pl.col("sales").sum().alias("denom_sales"))
        .sort(denom_cols)
    )
    shared = numer.join(denom, on=denom_cols, how="left")
    return shared.with_columns(
        pl.when(pl.col("denom_sales") > 0)
        .then(pl.col("sales") / pl.col("denom_sales") * 100)
        .otherwise(0.0)
        .alias("share_pct")
    ).drop(["sales", "denom_sales"])


def _compute_yearly_share(
    joined: pl.DataFrame,
    *,
    dims: Sequence[str],
    denom_dims: Sequence[str],
    placeholder_values: set[str],
) -> pl.DataFrame:
    if not dims:
        raise ChartBuildError("At least one dimension is required.")
    if not set(denom_dims).issubset(set(dims)):
        raise ChartBuildError("denom_dims must be a subset of dims.")
    columns, _schema = get_schema_and_column_names(joined)
    missing = [col for col in ("month", "sales", *dims) if col not in columns]
    if missing:
        raise ChartBuildError(f"Missing columns for share computation: {missing}")

    cleaned = joined.select(["month", "sales", *dims]).with_columns(
        [_clean_dim(col, placeholder_values) for col in dims]
    )
    cleaned = cleaned.with_columns(pl.col("month").dt.year().alias("year"))
    numer = (
        cleaned.group_by(["year", *dims])
        .agg(pl.col("sales").sum().alias("sales"))
        .sort(["year", *dims])
    )

    denom_cols = ["year", *denom_dims]
    denom = (
        cleaned.group_by(denom_cols)
        .agg(pl.col("sales").sum().alias("denom_sales"))
        .sort(denom_cols)
    )
    shared = numer.join(denom, on=denom_cols, how="left")
    return shared.with_columns(
        pl.when(pl.col("denom_sales") > 0)
        .then(pl.col("sales") / pl.col("denom_sales") * 100)
        .otherwise(0.0)
        .alias("share_pct")
    ).drop(["sales", "denom_sales"])


def _reduce_top_values(
    share_df: pl.DataFrame,
    *,
    value_col: str,
    top_n: int,
    other_label: str = "Other",
) -> tuple[pl.DataFrame, list[str]]:
    if top_n <= 0:
        return share_df, sorted(share_df.get_column(value_col).unique().to_list())

    ranked = (
        share_df.group_by(value_col)
        .agg(pl.col("share_pct").mean().alias("avg_share"))
        .sort("avg_share", descending=True)
    )
    top_values = [
        str(v)
        for v in ranked.select(value_col).head(top_n).to_series().to_list()
        if isinstance(v, str) and v.strip()
    ]
    reduced = share_df.with_columns(
        pl.when(pl.col(value_col).is_in(top_values))
        .then(pl.col(value_col))
        .otherwise(pl.lit(other_label))
        .alias(value_col)
    )
    return reduced, top_values


def _iso_month(value: date) -> str:
    return value.isoformat()


def _month_to_iso_expr() -> pl.Expr:
    return pl.col("month").dt.strftime("%Y-%m-%d").alias("month")


def _label_window_month(
    joined: pl.DataFrame, months: Sequence[date], label: date
) -> pl.DataFrame:
    return joined.filter(pl.col("month").is_in(months)).with_columns(
        pl.lit(label).cast(pl.Date).alias("month")
    )


def _compute_monthly_absolute(
    joined: pl.DataFrame,
    *,
    dims: Sequence[str],
    metric_column: str,
    placeholder_values: set[str],
) -> pl.DataFrame:
    if not dims:
        raise ChartBuildError("At least one dimension is required.")
    columns, _schema = get_schema_and_column_names(joined)
    missing = [col for col in ("month", metric_column, *dims) if col not in columns]
    if missing:
        raise ChartBuildError(f"Missing columns for absolute computation: {missing}")

    cleaned = joined.select(["month", metric_column, *dims]).with_columns(
        [
            pl.col(metric_column).cast(pl.Float64).fill_null(0.0).alias(metric_column),
            *[_clean_dim(col, placeholder_values) for col in dims],
        ]
    )
    return (
        cleaned.group_by(["month", *dims])
        .agg(pl.col(metric_column).sum().alias(metric_column))
        .sort(["month", *dims])
    )


def _reduce_top_values_absolute(
    absolute_df: pl.DataFrame,
    *,
    value_col: str,
    metric_col: str,
    top_n: int,
    other_label: str = "Other",
) -> tuple[pl.DataFrame, list[str]]:
    if top_n <= 0:
        return absolute_df, sorted(absolute_df.get_column(value_col).unique().to_list())

    ranked = (
        absolute_df.group_by(value_col)
        .agg(pl.col(metric_col).sum().alias("__total"))
        .sort("__total", descending=True)
    )
    top_values = [
        str(v)
        for v in ranked.select(value_col).head(top_n).to_series().to_list()
        if isinstance(v, str) and v.strip()
    ]
    reduced = absolute_df.with_columns(
        pl.when(pl.col(value_col).is_in(top_values))
        .then(pl.col(value_col))
        .otherwise(pl.lit(other_label))
        .alias(value_col)
    )
    return reduced, top_values


def build_dimension_stacked_absolute(
    *,
    joined: pl.DataFrame,
    category_key: str,
    category_label: str,
    retailers: Sequence[str],
    brands: Sequence[str],
    universe: ChartUniverse,
    segment: DimensionSpec,
    placeholder_values: set[str],
    metric_column: Literal["sales", "units"] = "sales",
    top_n: int = 8,
) -> ChartCandidate:
    start_month, end_month = compute_month_range(joined)
    absolute_df = _compute_monthly_absolute(
        joined,
        dims=[segment.column],
        metric_column=metric_column,
        placeholder_values=placeholder_values,
    )
    absolute_df, kept = _reduce_top_values_absolute(
        absolute_df,
        value_col=segment.column,
        metric_col=metric_column,
        top_n=top_n,
    )
    absolute_df = (
        absolute_df.group_by(["month", segment.column])
        .agg(pl.col(metric_column).sum().alias(metric_column))
        .sort(["month", segment.column])
    )
    csv_rows = (
        absolute_df.with_columns(_month_to_iso_expr())
        .rename({segment.column: "segment"})
        .select(["month", "segment", metric_column])
        .to_dicts()
    )
    spec_version = "v1"
    definition_id = make_chart_id(
        ["stacked_abs", segment.id, category_key, metric_column]
    )
    chart_id = make_chart_id(
        [
            "stacked_abs",
            segment.id,
            category_key,
            metric_column,
            f"retailers={_canonical_csv(retailers)}",
            f"brands={_canonical_csv(brands)}",
            f"universe={universe}",
            f"start_month={_iso_month(start_month)}",
            f"end_month={_iso_month(end_month)}",
            f"top_n={top_n}",
            f"placeholders={_canonical_placeholders(placeholder_values)}",
            f"spec={spec_version}",
        ]
    )
    metric_label = "Sales" if metric_column == "sales" else "Units"
    title = f"{segment.label} monthly stacked values"
    subtitle = (
        f"{metric_label} in absolute value (monthly). "
        f"Segments: {', '.join(kept[:5])}{'…' if len(kept) > 5 else ''}."
    )
    chart = ChartPayload(
        chart_id=chart_id,
        definition_id=definition_id,
        chart_type="stacked_column",
        title=title,
        subtitle=subtitle,
        normalization=f"absolute_{metric_column}",
        category_key=category_key,
        category_label=category_label,
        retailers=list(retailers),
        brands=list(brands),
        universe=universe,
        start_month=_iso_month(start_month),
        end_month=_iso_month(end_month),
        dimensions=[segment],
        facet=None,
        payload={
            "rows": csv_rows,
            "instance_id": chart_id,
            "definition_id": definition_id,
            "segment_label": segment.label,
            "metric": metric_column,
            "aggregation": "monthly",
        },
    )
    return ChartCandidate(chart=chart, csv_rows=csv_rows)


def build_total_combo_absolute(
    *,
    joined: pl.DataFrame,
    category_key: str,
    category_label: str,
    retailers: Sequence[str],
    brands: Sequence[str],
    universe: ChartUniverse,
    bar_metric: Literal["sales", "units"] = "sales",
    line_metric: Literal["sales", "units", "price"] = "units",
) -> ChartCandidate:
    start_month, end_month = compute_month_range(joined)
    columns, _schema = get_schema_and_column_names(joined)
    missing = [col for col in ("month", "sales", "units") if col not in columns]
    if missing:
        raise ChartBuildError(f"Missing columns for combo chart: {missing}")

    grouped = (
        joined.select(["month", "sales", "units"])
        .with_columns(
            [
                pl.col("sales").cast(pl.Float64).fill_null(0.0).alias("sales"),
                pl.col("units").cast(pl.Float64).fill_null(0.0).alias("units"),
            ]
        )
        .group_by("month")
        .agg(
            [
                pl.col("sales").sum().alias("sales"),
                pl.col("units").sum().alias("units"),
            ]
        )
        .with_columns(
            pl.when(pl.col("units") > 0)
            .then(pl.col("sales") / pl.col("units"))
            .otherwise(None)
            .alias("price")
        )
        .sort("month")
    )
    if grouped.is_empty():
        raise ChartBuildError("No data available for combo chart.")
    csv_rows = (
        grouped.with_columns(_month_to_iso_expr())
        .select(["month", "sales", "units", "price"])
        .to_dicts()
    )

    spec_version = "v1"
    definition_id = make_chart_id(
        ["combo_total_abs", category_key, bar_metric, line_metric]
    )
    chart_id = make_chart_id(
        [
            "combo_total_abs",
            category_key,
            bar_metric,
            line_metric,
            f"retailers={_canonical_csv(retailers)}",
            f"brands={_canonical_csv(brands)}",
            f"universe={universe}",
            f"start_month={_iso_month(start_month)}",
            f"end_month={_iso_month(end_month)}",
            f"spec={spec_version}",
        ]
    )
    title = "Total monthly values (bar + line)"
    subtitle = (
        f"Bar: {bar_metric}. Line: {line_metric}. "
        f"{_iso_month(start_month)} → {_iso_month(end_month)}."
    )
    chart = ChartPayload(
        chart_id=chart_id,
        definition_id=definition_id,
        chart_type="stacked_column",
        title=title,
        subtitle=subtitle,
        normalization="absolute_totals",
        category_key=category_key,
        category_label=category_label,
        retailers=list(retailers),
        brands=list(brands),
        universe=universe,
        start_month=_iso_month(start_month),
        end_month=_iso_month(end_month),
        dimensions=[],
        facet=None,
        payload={
            "rows": csv_rows,
            "instance_id": chart_id,
            "definition_id": definition_id,
            "bar_metric": bar_metric,
            "line_metric": line_metric,
            "aggregation": "monthly",
        },
    )
    return ChartCandidate(chart=chart, csv_rows=csv_rows)


def build_dimension_stacked(
    *,
    joined: pl.DataFrame,
    category_key: str,
    category_label: str,
    retailers: Sequence[str],
    brands: Sequence[str],
    universe: ChartUniverse,
    segment: DimensionSpec,
    placeholder_values: set[str],
    top_n: int = 8,
    aggregation: Literal["monthly", "annual"] = "monthly",
) -> ChartCandidate:
    start_month, end_month = compute_month_range(joined)
    if aggregation == "annual":
        share_df = _compute_yearly_share(
            joined,
            dims=[segment.column],
            denom_dims=[],
            placeholder_values=placeholder_values,
        )
        period_col = "year"
    else:
        share_df = _compute_monthly_share(
            joined,
            dims=[segment.column],
            denom_dims=[],
            placeholder_values=placeholder_values,
        )
        period_col = "month"
    share_df, kept = _reduce_top_values(share_df, value_col=segment.column, top_n=top_n)
    share_df = (
        share_df.group_by([period_col, segment.column])
        .agg(pl.col("share_pct").sum().alias("share_pct"))
        .sort([period_col, segment.column])
    )
    share_df = share_df.with_columns(
        pl.when(pl.col("share_pct") < 1.0)
        .then(pl.col("share_pct"))
        .otherwise(pl.col("share_pct").round(1))
        .alias("share_pct")
    )
    if aggregation == "annual":
        csv_rows = (
            share_df.with_columns(pl.col("year").cast(pl.Utf8).alias("year"))
            .rename({segment.column: "segment"})
            .select(["year", "segment", "share_pct"])
            .to_dicts()
        )
    else:
        csv_rows = (
            share_df.with_columns(_month_to_iso_expr())
            .rename({segment.column: "segment"})
            .select(["month", "segment", "share_pct"])
            .to_dicts()
        )
    spec_version = "v1"
    definition_id = make_chart_id(["stacked", segment.id, category_key])
    chart_id = make_chart_id(
        [
            "stacked",
            segment.id,
            category_key,
            f"retailers={_canonical_csv(retailers)}",
            f"brands={_canonical_csv(brands)}",
            f"universe={universe}",
            f"start_month={_iso_month(start_month)}",
            f"end_month={_iso_month(end_month)}",
            f"top_n={top_n}",
            f"agg={aggregation}",
            f"placeholders={_canonical_placeholders(placeholder_values)}",
            f"spec={spec_version}",
        ]
    )
    title = f"{segment.label} share over time"
    granularity_note = (
        "Annual share snapshot" if aggregation == "annual" else "Monthly share trend"
    )
    subtitle = (
        f"{granularity_note}. Sales share % of category (all selected retailers). "
        f"Segments: {', '.join(kept[:5])}{'…' if len(kept) > 5 else ''}."
    )
    chart = ChartPayload(
        chart_id=chart_id,
        definition_id=definition_id,
        chart_type="area",
        title=title,
        subtitle=subtitle,
        normalization="share_of_category_total",
        category_key=category_key,
        category_label=category_label,
        retailers=list(retailers),
        brands=list(brands),
        universe=universe,
        start_month=_iso_month(start_month),
        end_month=_iso_month(end_month),
        dimensions=[segment],
        facet=None,
        payload={
            "rows": csv_rows,
            "instance_id": chart_id,
            "definition_id": definition_id,
            "segment_label": segment.label,
            "start_month": _iso_month(start_month),
            "end_month": _iso_month(end_month),
            "aggregation": aggregation,
        },
    )
    return ChartCandidate(chart=chart, csv_rows=csv_rows)


def build_dimension_stacked_facets(
    *,
    joined: pl.DataFrame,
    category_key: str,
    category_label: str,
    retailers: Sequence[str],
    brands: Sequence[str],
    universe: ChartUniverse,
    segment: DimensionSpec,
    facet: DimensionSpec,
    placeholder_values: set[str],
    top_n: int = 6,
    aggregation: Literal["monthly", "annual"] = "monthly",
) -> ChartCandidate:
    start_month, end_month = compute_month_range(joined)
    if aggregation == "annual":
        share_df = _compute_yearly_share(
            joined,
            dims=[facet.column, segment.column],
            denom_dims=[facet.column],
            placeholder_values=placeholder_values,
        )
        period_col = "year"
    else:
        share_df = _compute_monthly_share(
            joined,
            dims=[facet.column, segment.column],
            denom_dims=[facet.column],
            placeholder_values=placeholder_values,
        )
        period_col = "month"
    share_df, kept = _reduce_top_values(share_df, value_col=segment.column, top_n=top_n)
    share_df = (
        share_df.group_by([period_col, facet.column, segment.column])
        .agg(pl.col("share_pct").sum().alias("share_pct"))
        .sort([period_col, facet.column, segment.column])
    )
    share_df = share_df.with_columns(
        pl.when(pl.col("share_pct") < 1.0)
        .then(pl.col("share_pct"))
        .otherwise(pl.col("share_pct").round(1))
        .alias("share_pct")
    )
    if aggregation == "annual":
        csv_rows = (
            share_df.with_columns(pl.col("year").cast(pl.Utf8).alias("year"))
            .rename({facet.column: "facet", segment.column: "segment"})
            .select(["facet", "year", "segment", "share_pct"])
            .to_dicts()
        )
    else:
        csv_rows = (
            share_df.with_columns(_month_to_iso_expr())
            .rename({facet.column: "facet", segment.column: "segment"})
            .select(["facet", "month", "segment", "share_pct"])
            .to_dicts()
        )
    spec_version = "v1"
    definition_id = make_chart_id(
        ["stacked_facets", segment.id, category_key, facet.id]
    )
    chart_id = make_chart_id(
        [
            "stacked_facets",
            segment.id,
            category_key,
            f"facet={facet.id}",
            f"retailers={_canonical_csv(retailers)}",
            f"brands={_canonical_csv(brands)}",
            f"universe={universe}",
            f"start_month={_iso_month(start_month)}",
            f"end_month={_iso_month(end_month)}",
            f"top_n={top_n}",
            f"agg={aggregation}",
            f"placeholders={_canonical_placeholders(placeholder_values)}",
            f"spec={spec_version}",
        ]
    )
    title = f"{segment.label} share over time (faceted by {facet.label})"
    granularity_note = (
        "Annual share snapshot" if aggregation == "annual" else "Monthly share trend"
    )
    subtitle = (
        f"{granularity_note}. Sales share % within each {facet.label}. "
        f"Segments: {', '.join(kept[:5])}{'…' if len(kept) > 5 else ''}."
    )
    chart = ChartPayload(
        chart_id=chart_id,
        definition_id=definition_id,
        chart_type="area",
        title=title,
        subtitle=subtitle,
        normalization=f"share_within_{facet.id}",
        category_key=category_key,
        category_label=category_label,
        retailers=list(retailers),
        brands=list(brands),
        universe=universe,
        start_month=_iso_month(start_month),
        end_month=_iso_month(end_month),
        dimensions=[segment],
        facet=facet,
        payload={
            "rows": csv_rows,
            "instance_id": chart_id,
            "definition_id": definition_id,
            "segment_label": segment.label,
            "facet_label": facet.label,
            "start_month": _iso_month(start_month),
            "end_month": _iso_month(end_month),
            "aggregation": aggregation,
        },
    )
    return ChartCandidate(chart=chart, csv_rows=csv_rows)


def build_brand_attribute_slope(
    *,
    joined: pl.DataFrame,
    category_key: str,
    category_label: str,
    retailers: Sequence[str],
    brands: Sequence[str],
    universe: ChartUniverse,
    brand: DimensionSpec,
    attribute: DimensionSpec,
    placeholder_values: set[str],
    top_n: int = 14,
    facet: DimensionSpec | None = None,
    rolling_window: bool = False,
    window_months: int = 12,
) -> ChartCandidate:
    start_month, end_month = compute_month_range(joined)
    dims = [brand.column, attribute.column]
    denom_dims: list[str] = []
    normalization = "share_of_category_total"
    if facet is not None:
        dims = [facet.column, *dims]
        denom_dims = [facet.column]
        normalization = f"share_within_{facet.id}"

    window_meta: dict[str, object] | None = None
    if rolling_window:
        months = _sorted_months(joined)
        window_span = window_months * 2
        if len(months) < window_span:
            raise ChartBuildError("Not enough months for rolling slope windows.")
        start_window = months[-window_span:-window_months]
        end_window = months[-window_months:]
        start_window_start = start_window[0]
        start_window_end = start_window[-1]
        end_window_start = end_window[0]
        end_window_end = end_window[-1]
        window_meta = {
            "mode": "rolling",
            "months": window_months,
            "start_window_start": start_window_start.isoformat(),
            "start_window_end": start_window_end.isoformat(),
            "end_window_start": end_window_start.isoformat(),
            "end_window_end": end_window_end.isoformat(),
        }
        start_joined = _label_window_month(joined, start_window, start_window_end)
        end_joined = _label_window_month(joined, end_window, end_window_end)
        start_share = _compute_monthly_share(
            start_joined,
            dims=dims,
            denom_dims=denom_dims,
            placeholder_values=placeholder_values,
        )
        end_share = _compute_monthly_share(
            end_joined,
            dims=dims,
            denom_dims=denom_dims,
            placeholder_values=placeholder_values,
        )
        start = (
            start_share.filter(pl.col("month") == start_window_end)
            .drop("month")
            .rename({"share_pct": "start_share_pct"})
        )
        end = (
            end_share.filter(pl.col("month") == end_window_end)
            .drop("month")
            .rename({"share_pct": "end_share_pct"})
        )
        start_month = start_window_start
        end_month = end_window_end
    else:
        share_df = _compute_monthly_share(
            joined,
            dims=dims,
            denom_dims=denom_dims,
            placeholder_values=placeholder_values,
        )
        start = (
            share_df.filter(pl.col("month") == start_month)
            .drop("month")
            .rename({"share_pct": "start_share_pct"})
        )
        end = (
            share_df.filter(pl.col("month") == end_month)
            .drop("month")
            .rename({"share_pct": "end_share_pct"})
        )
    merged = start.join(end, on=dims, how="full")
    coalesce_dims: list[pl.Expr] = []
    right_dim_columns: list[str] = []
    for dim_col in dims:
        right_col = f"{dim_col}_right"
        if right_col in merged.columns:
            coalesce_dims.append(
                pl.coalesce([pl.col(dim_col), pl.col(right_col)]).alias(dim_col)
            )
            right_dim_columns.append(right_col)
    if coalesce_dims:
        merged = merged.with_columns(coalesce_dims)
    if right_dim_columns:
        merged = merged.drop(right_dim_columns)
    merged = merged.with_columns(
        [
            pl.col("start_share_pct").fill_null(0.0),
            pl.col("end_share_pct").fill_null(0.0),
        ]
    )
    merged = merged.with_columns(
        [
            pl.when(pl.col("start_share_pct") < 1.0)
            .then(pl.col("start_share_pct"))
            .otherwise(pl.col("start_share_pct").round(1))
            .alias("start_share_pct"),
            pl.when(pl.col("end_share_pct") < 1.0)
            .then(pl.col("end_share_pct"))
            .otherwise(pl.col("end_share_pct").round(1))
            .alias("end_share_pct"),
        ]
    )
    merged = merged.with_columns(
        (pl.col("end_share_pct") - pl.col("start_share_pct")).alias("delta_pp")
    )
    merged = merged.with_columns(
        pl.col("delta_pp").round(0).cast(pl.Int64).alias("delta_pp")
    )
    merged = merged.with_columns(
        (pl.col("end_share_pct").abs() + pl.col("delta_pp").abs() * 1.25).alias("score")
    )
    merged = merged.sort("score", descending=True).drop("score")
    if merged.height > top_n:
        other_start = float(merged.slice(top_n).get_column("start_share_pct").sum())
        other_end = float(merged.slice(top_n).get_column("end_share_pct").sum())
        other_row: dict[str, object] = {
            brand.column: "Other (remaining)",
            attribute.column: "Other (remaining)",
            "start_share_pct": (
                round(other_start, 1) if other_start >= 1.0 else other_start
            ),
            "end_share_pct": round(other_end, 1) if other_end >= 1.0 else other_end,
            "delta_pp": int(round(other_end - other_start)),
        }
        if facet is not None:
            # For faceted slopes, collapse "other" per facet to preserve within-facet sums.
            rows: list[dict[str, object]] = []
            for facet_key, group in merged.group_by(facet.column, maintain_order=True):  # type: ignore[misc]
                facet_val = (
                    facet_key[0]
                    if isinstance(facet_key, tuple) and len(facet_key) == 1
                    else facet_key
                )
                group_sorted = group.sort("end_share_pct", descending=True)
                if group_sorted.height <= top_n:
                    rows.extend(group_sorted.to_dicts())
                    continue
                kept = group_sorted.head(top_n)
                omitted = group_sorted.slice(top_n)
                o_start = float(omitted.get_column("start_share_pct").sum())
                o_end = float(omitted.get_column("end_share_pct").sum())
                o_row = dict(other_row)
                o_row[facet.column] = facet_val
                o_row["start_share_pct"] = (
                    round(o_start, 1) if o_start >= 1.0 else o_start
                )
                o_row["end_share_pct"] = round(o_end, 1) if o_end >= 1.0 else o_end
                o_row["delta_pp"] = int(round(o_end - o_start))
                rows.extend(kept.to_dicts())
                rows.append(o_row)
            merged_rows = rows
        else:
            merged_rows = merged.head(top_n).to_dicts() + [other_row]
    else:
        merged_rows = merged.to_dicts()

    csv_rows: list[dict[str, object]] = []
    for row in merged_rows:
        record = dict(row)
        record["brand"] = record.pop(brand.column)
        record["attribute"] = record.pop(attribute.column)
        if facet is not None:
            record["facet"] = record.pop(facet.column)
        csv_rows.append(record)

    kind = "slope_facets" if facet is not None else "slope"
    spec_version = "v1"
    definition_parts = [kind, attribute.id, category_key, brand.id]
    if facet is not None:
        definition_parts.append(facet.id)
    definition_id = make_chart_id(definition_parts)
    instance_parts = [
        kind,
        attribute.id,
        category_key,
        brand.id,
        f"retailers={_canonical_csv(retailers)}",
        f"brands={_canonical_csv(brands)}",
        f"universe={universe}",
        f"top_n={top_n}",
        f"placeholders={_canonical_placeholders(placeholder_values)}",
        f"spec={spec_version}",
    ]
    if rolling_window and window_meta is not None:
        instance_parts.extend(
            [
                f"window=rolling_{window_months}m",
                f"start_window_start={window_meta['start_window_start']}",
                f"start_window_end={window_meta['start_window_end']}",
                f"end_window_start={window_meta['end_window_start']}",
                f"end_window_end={window_meta['end_window_end']}",
            ]
        )
    else:
        instance_parts.extend(
            [
                f"start_month={start_month.isoformat()}",
                f"end_month={end_month.isoformat()}",
            ]
        )
    if facet is not None:
        instance_parts.append(f"facet={facet.id}")
    chart_id = make_chart_id(instance_parts)
    if rolling_window and window_meta is not None:
        title = f"{brand.label} × {attribute.label} (rolling {window_months}-month)"
        subtitle = (
            "Sales share % "
            f"({normalization.replace('_', ' ')}). "
            f"Rolling windows: {window_meta['start_window_start']} → {window_meta['start_window_end']} "
            f"vs {window_meta['end_window_start']} → {window_meta['end_window_end']}."
        )
    else:
        title = f"{brand.label} × {attribute.label} (start → end)"
        subtitle = (
            f"Sales share % ({normalization.replace('_', ' ')}). "
            f"{start_month.isoformat()} → {end_month.isoformat()}."
        )
    chart = ChartPayload(
        chart_id=chart_id,
        definition_id=definition_id,
        chart_type="slope",
        title=title,
        subtitle=subtitle,
        normalization=normalization,
        category_key=category_key,
        category_label=category_label,
        retailers=list(retailers),
        brands=list(brands),
        universe=universe,
        start_month=start_month.isoformat(),
        end_month=end_month.isoformat(),
        dimensions=[brand, attribute],
        facet=facet,
        payload={
            "rows": csv_rows,
            "instance_id": chart_id,
            "definition_id": definition_id,
            "start_month": start_month.isoformat(),
            "end_month": end_month.isoformat(),
            "brand_dim": brand.label,
            "attribute_dim": attribute.label,
            "facet_dim": facet.label if facet is not None else None,
            "window": window_meta,
        },
    )
    return ChartCandidate(chart=chart, csv_rows=csv_rows)


def choose_pair_attributes(
    attributes: Iterable[DimensionSpec],
    attribute_meta: dict[str, int],
    *,
    max_count: int = 6,
) -> list[DimensionSpec]:
    """Pick a small set of attributes for pair charts using value cardinality heuristics."""
    candidates: list[tuple[int, str, DimensionSpec]] = []
    for attr in attributes:
        count = int(attribute_meta.get(attr.id, 0))
        if count < 2:
            continue
        candidates.append((count, attr.label.lower(), attr))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in candidates[:max_count]]
