from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

import polars as pl

from modules.pdp.attribute_review_logic import ReviewTables, repair_text_encoding
from modules.pdp.sales_dataset_paths import (
    BASE_SALES_DIR,
    get_sales_dataset_csv_dir,
    get_sales_dataset_dir,
    get_sales_dataset_join_dir,
    get_sales_dataset_name,
)

DEFAULT_SALES_DIR = BASE_SALES_DIR
LOGGER = logging.getLogger(__name__)
_DEFAULT_DATASET_METADATA: dict[str, str] = {
    "industry": "Cosmetics in USA",
    "currency": "USD",
}


@dataclass(frozen=True)
class SalesCacheEntry:
    path: Path
    mtime: float
    frame: pl.DataFrame


_SALES_CACHE: Dict[str, SalesCacheEntry] = {}


def _resolve_sales_dirs(dataset: str | None = None) -> list[Path]:
    """Return candidate directories for sales outputs, preferring the new layout."""

    ordered = [
        get_sales_dataset_join_dir(dataset),
        get_sales_dataset_dir(dataset),  # legacy fallback
    ]
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in ordered:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _dataset_metadata_defaults(dataset_name: str) -> dict[str, str]:
    if dataset_name.startswith("kiko"):
        return {
            "industry": "Cosmetics in Europe",
            "currency": "EUR",
        }
    return dict(_DEFAULT_DATASET_METADATA)


def _read_dataset_metadata_file(dataset_dir: Path) -> dict[str, str]:
    metadata_path = dataset_dir / "metadata.json"
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.warning("Could not parse dataset metadata file: %s", metadata_path)
        return {}
    if not isinstance(payload, Mapping):
        LOGGER.warning("Dataset metadata must be a JSON object: %s", metadata_path)
        return {}

    resolved: dict[str, str] = {}
    industry_obj = payload.get("industry")
    if industry_obj is not None:
        industry = str(industry_obj).strip()
        if industry:
            resolved["industry"] = industry
    currency_obj = payload.get("currency")
    if currency_obj is not None:
        currency = str(currency_obj).strip().upper()
        if currency:
            resolved["currency"] = currency
    return resolved


def _resolve_sales_path(
    retailer: str | None, dataset: str | None = None
) -> Path | None:
    for sales_dir in _resolve_sales_dirs(dataset):
        joined = sales_dir / "joined.parquet"
        if joined.exists():
            return joined
        merged_csv = sales_dir / "data.csv"
        if merged_csv.exists():
            return merged_csv
        if retailer:
            candidate = sales_dir / f"{retailer.lower()}.csv"
            if candidate.exists():
                return candidate
    if retailer:
        csv_dir = get_sales_dataset_csv_dir(dataset)
        candidate = csv_dir / f"{retailer.lower()}.csv"
        if candidate.exists():
            return candidate
    return None


def _resolve_full_sales_path(
    retailer: str | None, dataset: str | None = None
) -> Path | None:
    """Resolve the *full* sales dataset (not the PDP-joined like-for-like parquet)."""
    for sales_dir in _resolve_sales_dirs(dataset):
        full_sales = sales_dir / "full_sales.parquet"
        if full_sales.exists():
            return full_sales
        if retailer:
            candidate = sales_dir / f"{retailer.lower()}.csv"
            if candidate.exists():
                return candidate
        # Fallback: if only the joined parquet exists, return it so the app still functions.
        joined = sales_dir / "joined.parquet"
        if joined.exists():
            return joined
    if retailer:
        csv_dir = get_sales_dataset_csv_dir(dataset)
        candidate = csv_dir / f"{retailer.lower()}.csv"
        if candidate.exists():
            return candidate
    return None


def _normalize_sales_columns(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    rename_map = {}
    seen: dict[str, int] = {}
    for name in frame.columns:
        base = name.strip().lower().replace(" ", "_")
        count = seen.get(base, 0)
        seen[base] = count + 1
        unique = base if count == 0 else f"{base}_{count}"
        rename_map[name] = unique
    df = frame.rename(rename_map)

    def _clean(col: str) -> pl.Expr:
        return (
            pl.col(col)
            .cast(pl.Utf8)
            .str.strip_chars()
            .map_elements(repair_text_encoding)
        )

    month_raw = pl.col("month").cast(pl.Utf8).str.strip_chars()
    df = df.with_columns(
        [
            pl.coalesce(
                [
                    month_raw.str.strptime(pl.Date, format="%Y-%m-%d", strict=False),
                    month_raw.str.strptime(pl.Date, format="%m/%d/%Y", strict=False),
                    month_raw.str.strptime(pl.Date, format="%m/%d/%y", strict=False),
                    month_raw.str.strptime(pl.Date, format="%Y", strict=False),
                ]
            ).alias("month"),
            _clean("merchant").str.to_lowercase().alias("merchant"),
            _clean("category").alias("category"),
            _clean("brand").alias("brand"),
            pl.col("sku").cast(pl.Utf8).str.strip_chars().alias("sku"),
            pl.col("sales").cast(pl.Float64).alias("sales"),
            pl.col("units").cast(pl.Float64).alias("units"),
        ]
    )
    return df


def load_sales_data(
    retailer: str | Sequence[str] | None = None,
    dataset: str | None = None,
) -> pl.DataFrame:
    path = _resolve_sales_path(
        None if isinstance(retailer, (list, tuple, set)) else retailer,
        dataset,
    )
    if path is None:
        return pl.DataFrame()
    mtime = path.stat().st_mtime
    key = str(path)
    cached = _SALES_CACHE.get(key)
    if cached and cached.mtime == mtime:
        return cached.frame.clone()
    if path.suffix == ".parquet":
        df = pl.read_parquet(path)
        if "month" in df.columns:
            try:
                month_raw = pl.col("month").cast(pl.Utf8).str.strip_chars()
                df = df.with_columns(
                    pl.coalesce(
                        [
                            month_raw.str.strptime(
                                pl.Date, format="%Y-%m-%d", strict=False
                            ),
                            month_raw.str.strptime(
                                pl.Date, format="%m/%d/%Y", strict=False
                            ),
                            month_raw.str.strptime(
                                pl.Date, format="%m/%d/%y", strict=False
                            ),
                            month_raw.str.strptime(pl.Date, format="%Y", strict=False),
                        ]
                    ).alias("month")
                )
            except Exception:
                df = df
    else:
        df = pl.read_csv(path)
        df = _normalize_sales_columns(df)
    _SALES_CACHE[key] = SalesCacheEntry(path=path, mtime=mtime, frame=df)
    return df.clone()


def load_full_sales_data(
    retailer: str | Sequence[str] | None = None,
    dataset: str | None = None,
) -> pl.DataFrame:
    """Load the full sales dataset (unfiltered by PDP coverage)."""
    path = _resolve_full_sales_path(
        None if isinstance(retailer, (list, tuple, set)) else retailer,
        dataset,
    )
    if path is None:
        return pl.DataFrame()
    mtime = path.stat().st_mtime
    key = f"full::{path}"
    cached = _SALES_CACHE.get(key)
    if cached and cached.mtime == mtime:
        return cached.frame.clone()
    if path.suffix == ".parquet":
        df = pl.read_parquet(path)
        if "month" in df.columns:
            try:
                month_raw = pl.col("month").cast(pl.Utf8).str.strip_chars()
                df = df.with_columns(
                    pl.coalesce(
                        [
                            month_raw.str.strptime(
                                pl.Date, format="%Y-%m-%d", strict=False
                            ),
                            month_raw.str.strptime(
                                pl.Date, format="%m/%d/%Y", strict=False
                            ),
                            month_raw.str.strptime(
                                pl.Date, format="%m/%d/%y", strict=False
                            ),
                            month_raw.str.strptime(pl.Date, format="%Y", strict=False),
                        ]
                    ).alias("month")
                )
            except Exception:
                df = df
    else:
        df = pl.read_csv(path)
        df = _normalize_sales_columns(df)
    _SALES_CACHE[key] = SalesCacheEntry(path=path, mtime=mtime, frame=df)
    return df.clone()


def sales_categories(
    frame: pl.DataFrame, retailers: Sequence[str] | str | None = None
) -> list[str]:
    if frame.is_empty():
        return []
    df = frame
    if retailers:
        if isinstance(retailers, str):
            targets = {retailers.lower()}
        else:
            targets = {str(r).lower() for r in retailers if isinstance(r, str)}
        if targets:
            df = df.filter(pl.col("merchant").is_in(list(targets)))
    cats = df.select(pl.col("category").drop_nulls().unique()).to_series().to_list()
    return sorted({str(c).strip() for c in cats if isinstance(c, str)})


def _prepare_sales(
    frame: pl.DataFrame,
    retailers: Sequence[str],
    categories: Sequence[str],
    brands: Sequence[str],
) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    targets = {r.lower() for r in retailers if isinstance(r, str)}
    df = frame.filter(pl.col("merchant").is_in(list(targets))) if targets else frame
    if categories:
        lowered = {c.strip().lower() for c in categories if c}
        df = df.filter(pl.col("category").str.to_lowercase().is_in(list(lowered)))
    if brands:
        bnorm = {str(b).strip().lower() for b in brands if str(b).strip()}
        df = df.filter(pl.col("brand").str.to_lowercase().is_in(list(bnorm)))
    return df


def _prepare_variants(
    tables: ReviewTables,
    retailers: Sequence[str],
    categories: Sequence[str],
    brands: Sequence[str],
) -> pl.DataFrame:
    variants = tables.variants
    if variants.is_empty():
        return variants
    df = variants.with_columns(
        [
            pl.col("retailer")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("retailer"),
            pl.col("variant_id").cast(pl.Utf8).str.strip_chars().alias("variant_id"),
            pl.col("category_label")
            .cast(pl.Utf8)
            .str.strip_chars()
            .alias("category_label"),
            pl.col("brand")
            .cast(pl.Utf8)
            .map_elements(repair_text_encoding)
            .str.strip_chars()
            .alias("brand"),
        ]
    )
    targets = {r.lower() for r in retailers if isinstance(r, str)}
    if targets:
        df = df.filter(pl.col("retailer").is_in(list(targets)))
    if categories:
        lowered = {c.strip().lower() for c in categories if c}
        df = df.filter(pl.col("category_label").str.to_lowercase().is_in(list(lowered)))
    if brands:
        bnorm = {str(b).strip().lower() for b in brands if str(b).strip()}
        df = df.filter(pl.col("brand").str.to_lowercase().is_in(list(bnorm)))
    return df


def _month_span(min_month: date, max_month: date) -> list[date]:
    months: list[date] = []
    cursor = date(min_month.year, min_month.month, 1)
    end = date(max_month.year, max_month.month, 1)
    while cursor <= end:
        months.append(cursor)
        year = cursor.year + (1 if cursor.month == 12 else 0)
        month = 1 if cursor.month == 12 else cursor.month + 1
        cursor = date(year, month, 1)
    return months


def build_sales_calendar_and_join(
    tables: ReviewTables,
    sales_frame: pl.DataFrame,
    retailers: Sequence[str],
    category_labels: Sequence[str],
    brands: Sequence[str],
    dimensions: Sequence[str],
    attr_column_lookup: Mapping[str, str],
    attr_labels: Mapping[str, str],
    price_bands: pl.DataFrame | None = None,
    required_columns: Sequence[str] | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, list[str], list[str]]:
    empty_result = (pl.DataFrame(), pl.DataFrame(), [], [])
    if sales_frame.is_empty():
        return empty_result
    required_columns_set = {
        str(column_name).strip()
        for column_name in (required_columns or [])
        if str(column_name).strip()
    }
    required_columns_set.update(
        {
            column_name
            for column_name in (
                attr_column_lookup.get(dim_key) for dim_key in dimensions
            )
            if column_name
        }
    )
    parts: list[pl.DataFrame] = []
    for retailer in retailers:
        sales_df = _prepare_sales(sales_frame, [retailer], category_labels, brands)
        if sales_df.is_empty():
            continue
        variants_df = _prepare_variants(tables, [retailer], category_labels, brands)
        sales_columns = set(sales_df.columns)
        prejoined = {
            "variant_id",
            "parent_product_id",
            "category_label",
        }.issubset(sales_columns)
        missing_required = sorted(
            column_name
            for column_name in required_columns_set
            if column_name not in sales_columns
        )
        if price_bands is not None and "price_band" in missing_required:
            # Prefer computed full-sales price bands over sparse PDP variant coverage.
            missing_required = [
                column_name
                for column_name in missing_required
                if column_name != "price_band"
            ]
        if prejoined:
            joined_slice = sales_df
            if missing_required:
                if variants_df.is_empty() or "variant_id" not in variants_df.columns:
                    continue
                lookup_columns = [
                    "variant_id",
                    *[
                        column_name
                        for column_name in missing_required
                        if column_name in variants_df.columns
                    ],
                ]
                if len(lookup_columns) > 1:
                    variants_lookup = variants_df.select(lookup_columns).unique(
                        subset=["variant_id"], keep="first"
                    )
                    joined_slice = joined_slice.join(
                        variants_lookup,
                        on="variant_id",
                        how="left",
                    )
        else:
            if variants_df.is_empty():
                continue
            if "sku" in sales_df.columns:
                joined_slice = sales_df.join(
                    variants_df,
                    left_on="sku",
                    right_on="variant_id",
                    how="inner",
                )
            elif "variant_id" in sales_df.columns:
                joined_slice = sales_df.join(
                    variants_df,
                    on="variant_id",
                    how="inner",
                )
            else:
                continue
        if not joined_slice.is_empty():
            joined_slice = joined_slice.with_columns(pl.lit(retailer).alias("retailer"))
            parts.append(joined_slice)
    joined = pl.concat(parts, how="diagonal_relaxed") if parts else pl.DataFrame()
    if joined.is_empty() or "month" not in joined.columns:
        return empty_result

    joined = joined.with_columns(pl.col("month").cast(pl.Date).alias("month"))
    min_month = joined.select(pl.col("month").min()).item()
    max_month = joined.select(pl.col("month").max()).item()
    if min_month is None or max_month is None:
        return empty_result

    requested_columns = required_columns_set

    if (
        "price_band" in requested_columns
        and "price_band" not in joined.columns
        and price_bands is not None
    ):
        if not price_bands.is_empty():
            joined = joined.with_columns(
                pl.col("variant_id")
                .cast(pl.Utf8)
                .str.strip_chars()
                .alias("variant_id_norm")
            )
            joined = joined.join(price_bands, on="variant_id_norm", how="left")
            joined = joined.drop("variant_id_norm")

    if "pareto_class" in requested_columns and "pareto_class" not in joined.columns:
        if "parent_product_id" in joined.columns and "sales" in joined.columns:
            parent_sales = (
                joined.select(["parent_product_id", "sales"])
                .group_by("parent_product_id")
                .agg(pl.col("sales").sum().alias("sales_total"))
                .sort(pl.col("sales_total"), descending=True)
            )
            if not parent_sales.is_empty():
                total_sales_all = float(parent_sales.get_column("sales_total").sum())
                cumulative = 0.0
                pareto_map: dict[str, str] = {}
                for pid, sales_val in parent_sales.iter_rows():
                    val = float(sales_val or 0.0)
                    share = (val / total_sales_all) if total_sales_all > 0 else 0.0
                    cumulative += share
                    if cumulative <= 0.80 + 1e-9:
                        bucket = "A"
                    elif cumulative <= 0.95 + 1e-9:
                        bucket = "B"
                    else:
                        bucket = "C"
                    pareto_map[str(pid)] = bucket
                if pareto_map:
                    pareto_df = pl.DataFrame(
                        {
                            "parent_product_id": list(pareto_map.keys()),
                            "pareto_class": list(pareto_map.values()),
                        }
                    )
                    joined = joined.join(pareto_df, on="parent_product_id", how="left")

    group_cols: list[str] = []
    headers: list[str] = []
    hybrid_group_cols: set[str] = set()
    schema = joined.schema
    for dim in dimensions:
        col = attr_column_lookup.get(dim)
        if not col or col not in joined.columns:
            continue
        dtype = schema.get(col)
        if (
            dtype is None
            or str(dtype).startswith("struct")
            or str(dtype).startswith("list")
        ):
            continue
        group_cols.append(col)
        headers.append(attr_labels.get(dim, col))
        normalized_dim = str(dim).strip().lower()
        if normalized_dim.startswith("also_"):
            hybrid_group_cols.add(col)

    if not group_cols:
        joined = joined.with_columns(pl.lit("All").alias("__all__"))
        group_cols = ["__all__"]
        headers = []

    normalized_group_exprs: list[pl.Expr] = []
    for col in group_cols:
        if col in hybrid_group_cols:
            lowered = pl.col(col).cast(pl.Utf8, strict=False).str.to_lowercase()
            normalized_group_exprs.append(
                pl.when(lowered.is_in(["yes", "true", "1", "on"]))
                .then(pl.lit("yes"))
                .when(lowered.is_in(["no", "false", "0", "off"]))
                .then(pl.lit("no"))
                .when(pl.col(col).cast(pl.Boolean, strict=False).fill_null(False))
                .then(pl.lit("yes"))
                .otherwise(pl.lit("no"))
                .alias(col)
            )
            continue
        text_expr = pl.col(col).cast(pl.Utf8, strict=False)
        normalized_group_exprs.append(
            pl.when(pl.col(col).is_null() | (text_expr.str.strip_chars() == ""))
            .then(pl.lit("N/A"))
            .otherwise(text_expr)
            .alias(col)
        )
    joined = joined.with_columns(normalized_group_exprs)

    months = _month_span(min_month, max_month)
    calendar = pl.DataFrame({"month": months})

    return joined, calendar, group_cols, headers


def get_sales_dataset_metadata(dataset: str | None = None) -> dict[str, str]:
    """Return metadata for the requested sales dataset."""

    dataset_name = get_sales_dataset_name(dataset)
    dataset_dir = get_sales_dataset_dir(dataset_name)
    metadata = _dataset_metadata_defaults(dataset_name)
    metadata.update(_read_dataset_metadata_file(dataset_dir))
    metadata["dataset"] = dataset_name
    metadata["dataset_dir"] = str(dataset_dir)
    return metadata


def _format_retailer_label(retailer: str) -> str:
    if retailer is None:
        return ""
    cleaned = str(retailer).strip()
    if not cleaned:
        return ""
    lower = cleaned.lower()
    mapping = {
        "ulta": "Ulta",
        "sephora": "Sephora",
        "amazon": "Amazon",
        "kiko": "Kiko",
        "walmart": "Walmart",
        "target": "Target",
    }
    if lower in mapping:
        return mapping[lower]
    parts = [p for p in re.split(r"[\\s_-]+", cleaned) if p]
    if not parts:
        return cleaned
    return " ".join(part.capitalize() for part in parts)


def _format_retailer_list(retailers: Sequence[str] | None) -> str:
    if not retailers:
        return ""
    labels: list[str] = []
    seen: set[str] = set()
    for item in retailers:
        if item is None:
            continue
        for part in str(item).split(","):
            label = _format_retailer_label(part)
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            labels.append(label)
    return " + ".join(labels)


def _format_category_label(category_label: str) -> str:
    if category_label is None:
        return ""
    cleaned = str(category_label).strip()
    if not cleaned:
        return ""
    if any(ch.isupper() for ch in cleaned):
        return cleaned
    return cleaned.title()


def _build_mekko_title(
    category_label: str,
    headers: Sequence[str],
    metric: str,
    *,
    window_months: int,
    period: date | str | None = None,
    metric_prefix: str = "",
    currency: str | None = None,
    industry: str | None = None,
    retailers: Sequence[str] | None = None,
) -> str:
    """Compose the Mekko chart title with metric and rolling window context."""
    line1_parts: list[str] = []
    if industry:
        line1_parts.append(str(industry).strip())
    retailer_text = _format_retailer_list(retailers)
    if retailer_text:
        line1_parts.append(retailer_text)
    category_text = _format_category_label(category_label)
    if category_text:
        line1_parts.append(f"Category: {category_text}")
    line1 = " / ".join([p for p in line1_parts if p])

    metric_label = "Sales" if metric == "sales" else "Units"
    suffix = ""
    prefix = metric_prefix or ""
    if metric_label == "Sales":
        if prefix and currency:
            suffix = f"{prefix}{currency}"
        elif currency:
            suffix = currency
        elif prefix:
            suffix = prefix
    else:
        if prefix:
            suffix = prefix

    if suffix:
        metric_text = f"{metric_label} in {suffix}"
    else:
        metric_text = metric_label

    if len(headers) >= 2:
        dimension_text = f"by {headers[0]} and {headers[1]}"
    elif len(headers) == 1:
        dimension_text = f"by {headers[0]}"
    else:
        dimension_text = ""

    line2_parts = [metric_text, dimension_text] if dimension_text else [metric_text]
    line2 = " ".join([p for p in line2_parts if p]).strip()

    period_text = ""
    if period:
        if isinstance(period, str):
            try:
                period = date.fromisoformat(period)
            except Exception:
                period = None
        if isinstance(period, date):
            period_label = period.strftime("%Y %m")
        else:
            period_label = str(period)
        if window_months > 1:
            period_text = f"Rolling {window_months} months ending {period_label}"
        else:
            period_text = period_label

    parts = [p for p in (line1, line2, period_text) if p]
    return "<BR>".join(parts)


def compute_category_rollup(
    joined: pl.DataFrame,
    calendar: pl.DataFrame,
    window_months: int,
) -> pl.DataFrame:
    """Compute category monthly totals and rolling sums on the provided calendar."""
    if joined.is_empty() or calendar.is_empty():
        return pl.DataFrame()

    category_monthly = (
        joined.group_by("month")
        .agg(
            pl.col("sales").sum().alias("category_sales"),
            pl.col("units").sum().alias("category_units"),
        )
        .sort("month")
    )

    filled = calendar.join(category_monthly, on="month", how="left")
    filled = filled.with_columns(
        [
            pl.col("category_sales").fill_null(0.0),
            pl.col("category_units").fill_null(0.0),
        ]
    ).with_columns(
        [
            pl.col("category_sales")
            .rolling_sum(window_size=window_months, min_periods=1)
            .alias("category_sales_rolling"),
            pl.col("category_units")
            .rolling_sum(window_size=window_months, min_periods=1)
            .alias("category_units_rolling"),
        ]
    )
    return filled


def compute_dimension_shares(
    joined: pl.DataFrame,
    calendar: pl.DataFrame,
    category_rollup: pl.DataFrame,
    window_months: int,
    group_cols: Sequence[str],
    headers: Sequence[str],
) -> pl.DataFrame:
    """Compute rolling sales/units and shares for each dimension combo."""
    if joined.is_empty() or calendar.is_empty() or category_rollup.is_empty():
        return pl.DataFrame()

    combos = joined.select(group_cols).unique().to_dicts() if group_cols else [{}]
    parts: list[pl.DataFrame] = []

    for combo in combos:
        base = calendar.clone()
        for col in group_cols:
            base = base.with_columns(pl.lit(combo.get(col, "N/A")).alias(col))

        subset = joined
        for col in group_cols:
            subset = subset.filter(pl.col(col) == combo.get(col, "N/A"))

        monthly = (
            subset.group_by(["month"])
            .agg(
                pl.col("sales").sum().alias("sales"),
                pl.col("units").sum().alias("units"),
            )
            .sort("month")
        )

        combo_df = (
            base.join(monthly, on="month", how="left")
            .with_columns(
                [
                    pl.col("sales").fill_null(0.0),
                    pl.col("units").fill_null(0.0),
                ]
            )
            .with_columns(
                [
                    pl.col("sales")
                    .rolling_sum(window_size=window_months, min_periods=1)
                    .alias("sales_rolling"),
                    pl.col("units")
                    .rolling_sum(window_size=window_months, min_periods=1)
                    .alias("units_rolling"),
                ]
            )
            .join(category_rollup, on="month", how="left")
            .with_columns(
                [
                    pl.when(pl.col("category_sales_rolling") > 0)
                    .then(pl.col("sales_rolling") / pl.col("category_sales_rolling"))
                    .otherwise(0.0)
                    .alias("sales_share"),
                    pl.when(pl.col("category_units_rolling") > 0)
                    .then(pl.col("units_rolling") / pl.col("category_units_rolling"))
                    .otherwise(0.0)
                    .alias("units_share"),
                ]
            )
        )
        parts.append(combo_df)

    result = pl.concat(parts, how="vertical") if parts else pl.DataFrame()
    if result.is_empty():
        return result

    for col, header in zip(group_cols, headers):
        result = result.rename({col: header})

    return result.sort(["month", "sales_share"] + list(headers))


def join_sales_with_attributes(
    tables: ReviewTables,
    sales_frame: pl.DataFrame,
    retailers: Sequence[str],
    category_labels: Sequence[str],
    brands: Sequence[str],
    window_months: int,
    dimensions: Sequence[str],
    attr_column_lookup: Mapping[str, str],
    attr_labels: Mapping[str, str],
) -> pl.DataFrame:
    sales_df = _prepare_sales(sales_frame, retailers, category_labels, brands)
    if sales_df.is_empty():
        return pl.DataFrame()

    variants_df = _prepare_variants(tables, retailers, category_labels, brands)
    prejoined = {"variant_id", "parent_product_id", "category_label"}.issubset(
        set(sales_df.columns)
    )

    if prejoined:
        joined = sales_df
    else:
        if variants_df.is_empty():
            return pl.DataFrame()
        joined = sales_df.join(
            variants_df,
            left_on="sku",
            right_on="variant_id",
            how="inner",
        )
    if joined.is_empty():
        return joined

    group_cols: list[str] = []
    for dim in dimensions:
        col = attr_column_lookup.get(dim)
        if col and col in joined.columns:
            group_cols.append(col)

    agg_exprs = [
        pl.col("sales").sum().alias("sales"),
        pl.col("units").sum().alias("units"),
        pl.col("sku").n_unique().alias("sku_count"),
    ]
    if not group_cols:
        aggregated = joined.select(agg_exprs)
    else:
        aggregated = (
            joined.group_by(group_cols)
            .agg(agg_exprs)
            .sort(pl.col("sales"), descending=True)
        )

    if aggregated.is_empty():
        return aggregated

    for col in group_cols:
        attr_id = next((k for k, v in attr_column_lookup.items() if v == col), None)
        label = attr_labels.get(attr_id, col) if attr_id else col
        aggregated = aggregated.rename({col: label})

    return aggregated


__all__ = [
    "load_sales_data",
    "load_full_sales_data",
    "sales_categories",
    "build_sales_calendar_and_join",
    "compute_category_rollup",
    "compute_dimension_shares",
    "join_sales_with_attributes",
]
