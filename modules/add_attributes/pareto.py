"""Pareto ranking utilities for Add Attributes."""

from __future__ import annotations

from importlib import import_module
from typing import Iterable

import polars as pl
from dateutil.relativedelta import relativedelta

from modules.llm.batch_runner import run_step_json
from modules.utilities.config import get_naming_params

__all__ = [
    "infer_amount_column",
    "compute_pareto_ranking",
    "compute_top_launches",
]


def _get_schema_and_column_names(df: pl.DataFrame | pl.LazyFrame):
    """Return column names and schema via dynamic import."""
    utils = import_module("modules.utilities.utils")
    return utils.get_schema_and_column_names(df)


def infer_amount_column(llm_wrapper, lf: pl.LazyFrame) -> str | None:
    """Return the most likely amount column in ``lf``.

    If an ``Amount`` column exists (case-insensitive) it is returned.
    Otherwise the function inspects numeric columns and uses a quick LLM call
    to guess the best candidate. Returns ``None`` if no numeric columns exist
    or the LLM result is invalid.
    """
    # ``LazyFrame`` and ``DataFrame`` expose a ``schema`` attribute in recent
    # Polars versions. Fallback to ``collect().schema`` for compatibility.
    columns, schema = _get_schema_and_column_names(lf)
    if schema is None:
        # Fallback: derive schema from a collected frame via the shared helper
        _, schema = _get_schema_and_column_names(lf.collect())
    amount_like = [c for c in schema if c.lower() in {"amount", "sales", "revenue"}]
    if amount_like:
        return amount_like[0]

    numeric = [
        c for c, dt in schema.items() if hasattr(dt, "is_numeric") and dt.is_numeric()
    ]
    if not numeric:
        return None

    if llm_wrapper is None:
        if len(numeric) == 1:
            return numeric[0]
        return None

    sample_df = lf.select(numeric).head(3).collect()
    col_samples: dict[str, list[str]] = {}
    for c in numeric:
        vals = sample_df.get_column(c).drop_nulls().cast(str).to_list()[:3]
        col_samples[c] = vals

    lines = ["Numeric columns and example values:"]
    for col, vals in col_samples.items():
        lines.append(f"- {col}: {', '.join(vals)}")
    user_prompt = (
        "\n".join(lines)
        + '\nWhich column represents sales amount? Return JSON {"amount_column": <name>}'
    )
    namingParams = get_naming_params()
    inferColumnQuery = namingParams["inferColumnQuery"]
    resp = run_step_json(
        llm_wrapper,
        inferColumnQuery,
        "You are a helpful assistant. Return JSON only.",
        user_prompt,
    )[0]
    if isinstance(resp, dict):
        col = resp.get("amount_column")
        if col in numeric:
            return col
    return None


def compute_pareto_ranking(
    df: pl.DataFrame | pl.LazyFrame,
    product_col: str,
    amount_col: str,
    *,
    group_col: str | None = None,
    groups: Iterable[str] | None = None,
    period_col: str | None = None,
    periods: Iterable[str] | None = None,
) -> pl.DataFrame:
    """Return a DataFrame with Pareto ranking information.

    The result contains ``product_col``, ``total_amount`` and, when available,
    ``total_units`` and the price column specified in the naming parameters.
    These are provided alongside cumulative share ``cum_share`` and ``rank``
    (starting at 1). Optionally filters by ``group_col``/``groups`` and
    ``period_col``/``periods`` before ranking. Products with ``None`` or zero
    ``amount_col`` values are dropped to avoid meaningless rankings.
    """
    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    columns, _ = _get_schema_and_column_names(lf)

    def _resolve(col: str) -> str:
        if col in columns:
            return col
        lower_map = {c.lower(): c for c in columns}
        return lower_map.get(col.lower(), col)

    product_col = _resolve(product_col)
    amount_col = _resolve(amount_col)
    if group_col:
        group_col = _resolve(group_col)

    missing = [c for c in (product_col, amount_col) if c not in columns]
    if missing:
        raise pl.exceptions.ColumnNotFoundError(
            f"Missing column(s): {', '.join(missing)}"
        )

    if group_col and groups:
        lf = lf.filter(pl.col(group_col).is_in(list(groups)))
    if period_col and periods:
        period_col = _resolve(period_col)
        lf = lf.filter(pl.col(period_col).is_in(list(periods)))

    naming = get_naming_params()
    units_col_name = naming["unitsName"]
    volume_col_name = naming["volumeName"]
    price_col_name = naming["priceName"]
    units_col = _resolve(units_col_name) if units_col_name else None
    volume_col = _resolve(volume_col_name) if volume_col_name else None

    agg_exprs = [pl.col(amount_col).sum().alias("total_amount")]
    if units_col and units_col in columns:
        agg_exprs.append(pl.col(units_col).sum().alias("total_units"))
    if volume_col and volume_col in columns:
        agg_exprs.append(pl.col(volume_col).sum().alias("total_volume"))

    agg = (
        lf.group_by(product_col)
        .agg(agg_exprs)
        .filter(pl.col("total_amount").is_not_null() & (pl.col("total_amount") > 0))
        .sort("total_amount", descending=True)
        .collect()
    )

    cols, _ = _get_schema_and_column_names(agg)
    if "total_units" in cols:
        agg = agg.with_columns(
            pl.when(pl.col("total_units") != 0)
            .then(pl.col("total_amount") / pl.col("total_units"))
            .otherwise(None)
            .alias(price_col_name)
        )
    elif "total_volume" in cols:
        agg = agg.with_columns(
            pl.when(pl.col("total_volume") != 0)
            .then(pl.col("total_amount") / pl.col("total_volume"))
            .otherwise(None)
            .alias(price_col_name)
        )
    else:
        agg = agg.with_columns(pl.lit(None).alias(price_col_name))

    total_amount_sum = agg["total_amount"].sum()
    total_units_sum = agg["total_units"].sum() if "total_units" in agg.columns else None
    price_sum = (
        agg[price_col_name].sum()
        if price_col_name in agg.columns and agg[price_col_name].dtype != pl.Null
        else None
    )

    agg = agg.with_columns(pl.cum_sum("total_amount").alias("cum_amount"))
    if "total_units" in agg.columns:
        agg = agg.with_columns(pl.cum_sum("total_units").alias("cum_units"))
    if price_col_name in agg.columns and agg[price_col_name].dtype != pl.Null:
        agg = agg.with_columns(pl.cum_sum(price_col_name).alias("cum_price"))

    agg = agg.with_columns(
        (pl.col("cum_amount") / pl.lit(total_amount_sum) * 100).alias("cum_amount_pct")
    )
    if total_units_sum:
        agg = agg.with_columns(
            (pl.col("cum_units") / pl.lit(total_units_sum) * 100).alias("cum_units_pct")
        )
    if price_sum:
        agg = agg.with_columns(
            (pl.col("cum_price") / pl.lit(price_sum) * 100).alias("cum_price_pct")
        )

    agg = agg.drop(["cum_amount", "cum_units", "cum_price"], strict=False)
    agg = agg.with_columns(pl.col("cum_amount_pct").alias("cum_share"))
    agg = agg.with_row_index("rank", offset=1).with_columns(
        pl.col("rank").cast(pl.Int64)
    )

    select_cols = [product_col, "total_amount"]
    if "total_units" in agg.columns:
        select_cols.append("total_units")
    select_cols.append(price_col_name)
    if "cum_amount_pct" in agg.columns:
        select_cols.append("cum_amount_pct")
    if "cum_units_pct" in agg.columns:
        select_cols.append("cum_units_pct")
    if "cum_price_pct" in agg.columns:
        select_cols.append("cum_price_pct")
    select_cols.extend(["cum_share", "rank"])

    return agg.select(select_cols)


def compute_top_launches(
    df: pl.DataFrame | pl.LazyFrame,
    product_col: str,
    amount_col: str,
    date_col: str,
    *,
    months: int = 3,
    top_n: int = 3,
    group_col: str | None = None,
    groups: Iterable[str] | None = None,
    period_col: str | None = None,
    periods: Iterable[str] | None = None,
) -> pl.DataFrame:
    """Return high-performing launches within the given period.

    Optionally filters by ``group_col``/``groups`` and ``period_col``/``periods``
    before computing the ranking.
    """

    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    columns, schema = _get_schema_and_column_names(lf)

    def _resolve(col: str) -> str:
        if col in columns:
            return col
        lower_map = {c.lower(): c for c in columns}
        return lower_map.get(col.lower(), col)

    product_col = _resolve(product_col)
    amount_col = _resolve(amount_col)
    date_col = _resolve(date_col)
    if group_col:
        group_col = _resolve(group_col)

    missing = [c for c in (product_col, amount_col, date_col) if c not in columns]
    if missing:
        raise pl.exceptions.ColumnNotFoundError(
            f"Missing column(s): {', '.join(missing)}"
        )

    if group_col and groups:
        lf = lf.filter(pl.col(group_col).is_in(list(groups)))
    if period_col and periods:
        period_col = _resolve(period_col)
        lf = lf.filter(pl.col(period_col).is_in(list(periods)))

    if schema[date_col] not in (pl.Date, pl.Datetime):
        lf = lf.with_columns(
            pl.col(date_col).str.strptime(pl.Date, strict=False).alias(date_col)
        )

    max_date = lf.select(pl.col(date_col).max()).collect()[0, 0]
    cutoff = max_date - relativedelta(months=months)

    launches = (
        lf.group_by(product_col)
        .agg(pl.col(date_col).min().alias("launch_date"))
        .filter(pl.col("launch_date") >= pl.lit(cutoff))
    )

    sales = (
        lf.filter(pl.col(date_col) >= pl.lit(cutoff))
        .group_by(product_col)
        .agg(pl.col(amount_col).sum().alias("period_amount"))
    )

    result = (
        launches.join(sales, on=product_col, how="inner")
        .with_columns(
            ((pl.lit(max_date) - pl.col("launch_date")).dt.total_days() / 30 + 1).alias(
                "months_since_launch"
            )
        )
        .with_columns(
            (pl.col("period_amount") / pl.col("months_since_launch")).alias(
                "avg_month_sales"
            )
        )
        .sort("avg_month_sales", descending=True)
        .head(top_n)
        .collect()
    )

    if result.height == 0:
        return pl.DataFrame(schema=[(product_col, pl.Utf8)])

    return result
