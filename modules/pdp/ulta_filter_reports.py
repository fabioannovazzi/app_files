from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import polars as pl

from .postgres_compat import connect_pdp_database
from .ulta_taxonomy_bridge import (
    ULTA_FILTER_FAMILY_TO_ATTRIBUTE_LABELS,
    attribute_labels_for_filter_family,
    mapped_filter_families_for_category,
)

FILTER_FAMILY_TO_MAPPING_COLUMNS: dict[str, tuple[str, ...]] = dict(
    ULTA_FILTER_FAMILY_TO_ATTRIBUTE_LABELS
)


def latest_ulta_filter_crawl_ts(pdp_store_path: str | Path) -> str | None:
    """Return the latest available Ulta filter crawl timestamp."""

    query = (
        "SELECT MAX(crawl_ts) FROM retailer_filter_observations "
        "WHERE retailer = 'ulta'"
    )
    with connect_pdp_database(Path(pdp_store_path)) as conn:
        try:
            row = conn.execute(query).fetchone()
        except Exception:
            return None
    if not row or row[0] is None:
        return None
    return str(row[0])


def load_ulta_filter_observations(
    pdp_store_path: str | Path,
    *,
    crawl_ts: str | None = None,
    category_keys: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Load Ulta filter observations for one crawl."""

    selected_crawl_ts = crawl_ts or latest_ulta_filter_crawl_ts(pdp_store_path)
    if not selected_crawl_ts:
        return _empty_filter_observation_frame()

    query = """
        SELECT
            crawl_ts,
            retailer,
            category_key,
            filter_family,
            filter_value,
            source_surface,
            pdp_url,
            parent_product_id,
            page,
            position,
            listing_url
        FROM retailer_filter_observations
        WHERE retailer = 'ulta' AND crawl_ts = ?
    """
    params: list[Any] = [selected_crawl_ts]
    if category_keys:
        placeholders = ",".join("?" for _ in category_keys)
        query += f" AND category_key IN ({placeholders})"
        params.extend(category_keys)
    query += " ORDER BY category_key, filter_family, filter_value, page, position"
    return _read_store_to_polars(pdp_store_path, query, tuple(params))


def compute_double_matching_summary(filter_df: pl.DataFrame) -> pl.DataFrame:
    """Measure how often products have multiple Ulta values in the same family."""

    if filter_df.is_empty():
        return _empty_double_matching_summary_frame()

    identity_expr = (
        pl.when(
            pl.col("parent_product_id").is_not_null()
            & (pl.col("parent_product_id") != "")
        )
        .then(pl.col("parent_product_id"))
        .otherwise(pl.col("pdp_url"))
    )

    per_product = (
        filter_df.with_columns(identity_expr.alias("identity"))
        .group_by(["category_key", "filter_family", "identity"])
        .agg(pl.col("filter_value").n_unique().alias("filter_value_count"))
    )

    return (
        per_product.group_by(["category_key", "filter_family"])
        .agg(
            [
                pl.len().alias("product_count"),
                pl.col("filter_value_count").eq(1).sum().alias("single_value_products"),
                pl.col("filter_value_count").gt(1).sum().alias("multi_value_products"),
                pl.col("filter_value_count").max().alias("max_values_per_product"),
            ]
        )
        .with_columns(
            (pl.col("multi_value_products") / pl.col("product_count")).alias(
                "multi_value_share"
            )
        )
        .sort(["category_key", "filter_family"])
    )


def load_parent_mapping_frame(
    parents_parquet_path: str | Path,
    *,
    retailer: str = "ulta",
    brand_contains: str | None = None,
    category_keys: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Load the current parent-level mapped attribute frame."""

    path = Path(parents_parquet_path)
    if not path.exists():
        raise FileNotFoundError(f"Parent mapping parquet not found: {path}")

    df = pl.read_parquet(path)
    filtered = df.filter(pl.col("retailer") == retailer)
    if brand_contains:
        filtered = filtered.filter(
            pl.col("brand")
            .fill_null("")
            .str.to_lowercase()
            .str.contains(brand_contains.lower())
        )
    if category_keys:
        filtered = filtered.filter(pl.col("category_key").is_in(category_keys))
    return filtered


def build_brand_filter_comparison(
    *,
    filter_df: pl.DataFrame,
    parents_df: pl.DataFrame,
) -> pl.DataFrame:
    """Build a parent-level comparison between our mapping and Ulta filter memberships."""

    if parents_df.is_empty():
        return _empty_brand_comparison_frame()

    parent_records = {
        str(row["parent_product_id"]): row
        for row in parents_df.select(
            ["parent_product_id", "brand", "product_name", "category_key", "pdp_url"]
        ).to_dicts()
        if str(row["parent_product_id"] or "").strip()
    }
    allowed_parent_ids = set(parent_records)

    mapped_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in parents_df.to_dicts():
        parent_id = str(row.get("parent_product_id") or "").strip()
        if not parent_id:
            continue
        category_key = str(row.get("category_key") or "").strip()
        for filter_family in mapped_filter_families_for_category(category_key):
            columns = attribute_labels_for_filter_family(
                filter_family,
                category_key=category_key,
            )
            if not columns:
                continue
            chosen_column = None
            chosen_value = None
            for column in columns:
                value = row.get(column)
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    chosen_column = column
                    chosen_value = text
                    break
            mapped_rows[(parent_id, filter_family)] = {
                "our_value": chosen_value,
                "our_source_column": chosen_column,
            }

    ulta_rows: dict[tuple[str, str], dict[str, Any]] = {}
    if not filter_df.is_empty():
        grouped = (
            filter_df.filter(
                pl.col("parent_product_id").is_not_null()
                & (pl.col("parent_product_id") != "")
            )
            .group_by(["parent_product_id", "filter_family"])
            .agg(
                [
                    pl.col("filter_value").sort().unique().alias("ulta_values_list"),
                    pl.col("filter_value")
                    .sort()
                    .unique()
                    .str.join(" | ")
                    .alias("ulta_values"),
                    pl.col("category_key")
                    .sort()
                    .unique()
                    .str.join(" | ")
                    .alias("ulta_category_keys"),
                    pl.col("filter_value").n_unique().alias("ulta_value_count"),
                ]
            )
        )
        for row in grouped.to_dicts():
            parent_id = str(row["parent_product_id"])
            if parent_id not in allowed_parent_ids:
                continue
            ulta_rows[(parent_id, str(row["filter_family"]))] = row

    union_keys = sorted(set(mapped_rows) | set(ulta_rows))
    records: list[dict[str, Any]] = []
    for parent_id, filter_family in union_keys:
        parent_meta = parent_records.get(parent_id, {})
        mapped = mapped_rows.get((parent_id, filter_family), {})
        ulta = ulta_rows.get((parent_id, filter_family), {})
        our_value = mapped.get("our_value")
        ulta_values = ulta.get("ulta_values")
        verdict = compare_mapping_to_ulta(
            filter_family=filter_family,
            our_value=our_value,
            ulta_values=ulta.get("ulta_values_list"),
            category_key=str(parent_meta.get("category_key") or ""),
        )
        records.append(
            {
                "parent_product_id": parent_id,
                "brand": parent_meta.get("brand"),
                "product_name": parent_meta.get("product_name"),
                "mapped_category_key": parent_meta.get("category_key"),
                "pdp_url": parent_meta.get("pdp_url"),
                "filter_family": filter_family,
                "our_value": our_value,
                "our_source_column": mapped.get("our_source_column"),
                "ulta_values": ulta_values,
                "ulta_category_keys": ulta.get("ulta_category_keys"),
                "ulta_value_count": ulta.get("ulta_value_count"),
                "verdict": verdict,
            }
        )

    return pl.DataFrame(records).sort(["product_name", "filter_family"])


def summarize_brand_filter_comparison(comparison_df: pl.DataFrame) -> pl.DataFrame:
    """Summarize comparison verdicts by filter family."""

    if comparison_df.is_empty():
        return _empty_brand_comparison_summary_frame()

    return (
        comparison_df.group_by(["filter_family", "verdict"])
        .agg(pl.len().alias("product_count"))
        .sort(["filter_family", "verdict"])
    )


def compare_mapping_to_ulta(
    *,
    filter_family: str,
    our_value: str | None,
    ulta_values: list[str] | None,
    category_key: str | None = None,
) -> str:
    """Return a coarse verdict for our mapped value versus Ulta memberships."""

    family_is_mapped = bool(
        attribute_labels_for_filter_family(filter_family, category_key=category_key)
    )
    normalized_ulta_values = [
        _normalize_compare_value(value)
        for value in (ulta_values or [])
        if _normalize_compare_value(value)
    ]
    normalized_our = _normalize_compare_value(our_value)

    if not family_is_mapped:
        return "family_unmapped"
    if not normalized_our and not normalized_ulta_values:
        return "both_missing"
    if not normalized_our:
        return "our_missing"
    if not normalized_ulta_values:
        return "ulta_missing"
    if normalized_our in normalized_ulta_values:
        return "exact_match"

    our_candidates = _comparison_candidates(
        normalized_our,
        filter_family=filter_family,
    )
    for candidate in our_candidates:
        for ulta_value in normalized_ulta_values:
            if candidate == ulta_value:
                return "exact_match"
    for candidate in our_candidates:
        for ulta_value in normalized_ulta_values:
            if candidate in ulta_value or ulta_value in candidate:
                return "partial_match"

    return "mismatch"


def _comparison_candidates(
    value: str,
    *,
    filter_family: str | None = None,
) -> set[str]:
    values = {value}
    if filter_family == "spf":
        values.update(_spf_comparison_candidates(value))
    for piece in re.split(r"[|/,;]+", value):
        cleaned = _normalize_compare_value(piece)
        if cleaned:
            values.add(cleaned)
    return values


def _normalize_compare_value(value: str | None) -> str:
    if value is None:
        return ""
    normalized = " ".join(str(value).strip().lower().replace("-", " ").split())
    return normalized


def _spf_comparison_candidates(value: str) -> set[str]:
    parsed = _parse_compare_spf_value(value)
    if parsed is None:
        return set()

    candidates: set[str] = set()
    if parsed < 15:
        candidates.add("under 15")
    else:
        candidates.add("15+")
        if parsed <= 30:
            candidates.add("15 30")
        if parsed >= 30:
            candidates.add("30+")
        if parsed > 30:
            candidates.add("above 30")
        if parsed >= 50:
            candidates.add("50+")
    return candidates


def _parse_compare_spf_value(value: str) -> int | None:
    match = re.search(r"(\d{1,3})", value)
    if not match:
        return None
    parsed = int(match.group(1))
    if parsed <= 0 or parsed > 150:
        return None
    return parsed


def _read_store_to_polars(
    pdp_store_path: str | Path,
    query: str,
    params: tuple[Any, ...] = (),
) -> pl.DataFrame:
    with connect_pdp_database(Path(pdp_store_path)) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description or ()]
    if not columns:
        return pl.DataFrame()
    if not rows:
        return pl.DataFrame(schema={column: pl.Utf8 for column in columns})
    return pl.DataFrame(rows, schema=columns, orient="row")


def _empty_filter_observation_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "crawl_ts": pl.Utf8,
            "retailer": pl.Utf8,
            "category_key": pl.Utf8,
            "filter_family": pl.Utf8,
            "filter_value": pl.Utf8,
            "source_surface": pl.Utf8,
            "pdp_url": pl.Utf8,
            "parent_product_id": pl.Utf8,
            "page": pl.Int64,
            "position": pl.Int64,
            "listing_url": pl.Utf8,
        }
    )


def _empty_double_matching_summary_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "category_key": pl.Utf8,
            "filter_family": pl.Utf8,
            "product_count": pl.Int64,
            "single_value_products": pl.Int64,
            "multi_value_products": pl.Int64,
            "max_values_per_product": pl.Int64,
            "multi_value_share": pl.Float64,
        }
    )


def _empty_brand_comparison_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "parent_product_id": pl.Utf8,
            "brand": pl.Utf8,
            "product_name": pl.Utf8,
            "mapped_category_key": pl.Utf8,
            "pdp_url": pl.Utf8,
            "filter_family": pl.Utf8,
            "our_value": pl.Utf8,
            "our_source_column": pl.Utf8,
            "ulta_values": pl.Utf8,
            "ulta_category_keys": pl.Utf8,
            "ulta_value_count": pl.Int64,
            "verdict": pl.Utf8,
        }
    )


def _empty_brand_comparison_summary_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "filter_family": pl.Utf8,
            "verdict": pl.Utf8,
            "product_count": pl.Int64,
        }
    )


__all__ = [
    "FILTER_FAMILY_TO_MAPPING_COLUMNS",
    "build_brand_filter_comparison",
    "compare_mapping_to_ulta",
    "compute_double_matching_summary",
    "latest_ulta_filter_crawl_ts",
    "load_parent_mapping_frame",
    "load_ulta_filter_observations",
    "summarize_brand_filter_comparison",
]
