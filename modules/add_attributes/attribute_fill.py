from __future__ import annotations

"""Offline helpers to reconcile cross-retailer attribute values.

This logic is intended to run in batch during the pre-join pipeline (not in the
interactive review endpoints).
"""

import logging
from collections.abc import Sequence

import polars as pl

from modules.add_attributes.pdp_attribute_export import _ATTRIBUTE_PLACEHOLDERS
from modules.utilities.utils import get_row_count, get_schema_and_column_names

__all__ = [
    "fill_missing_attribute_values",
    "fill_unique_attribute_values",
    "map_attribute_conflicts",
    "map_attribute_na_fill_candidates",
    "meaningful_value_expr",
    "resolve_attribute_conflicts",
]

LOGGER = logging.getLogger(__name__)

_TAXONOMY_MISS_PREFIX = "not in taxonomy"

PLACEHOLDER_CANONICAL = {
    str(value).strip().casefold()
    for value in _ATTRIBUTE_PLACEHOLDERS
    if isinstance(value, str)
}
PLACEHOLDER_CANONICAL.discard(_TAXONOMY_MISS_PREFIX.casefold())
PLACEHOLDER_VALUES = sorted(PLACEHOLDER_CANONICAL)

DEFAULT_RETAILER_PRIORITY: list[str] = ["ulta", "kiko", "sephora", "amazon"]

ATTRIBUTE_EXCLUDE_COLUMNS = {
    "retailer",
    "parent_product_id",
    "canonical_id",
    "brand",
    "product_name",
    "pdp_url",
    "brand_norm",
    "product_name_norm",
    "category_key",
    "category_label",
}


def _retailer_rank_expr(retailer_col: str, retailer_priority: Sequence[str]) -> pl.Expr:
    normalized = (
        pl.col(retailer_col).cast(pl.Utf8).str.strip_chars().str.to_lowercase()
    )
    expr: pl.Expr = pl.lit(len(retailer_priority), dtype=pl.Int64)
    for idx, retailer in enumerate(retailer_priority):
        expr = pl.when(normalized == retailer).then(pl.lit(idx, dtype=pl.Int64)).otherwise(expr)
    return expr


def _value_class_expr(column: str) -> tuple[pl.Expr, pl.Expr, pl.Expr, pl.Expr]:
    normalized_text = pl.col(column).cast(pl.Utf8).str.strip_chars()
    lowered = normalized_text.str.to_lowercase()
    is_taxonomy_miss = lowered.str.starts_with(_TAXONOMY_MISS_PREFIX)
    is_na = lowered.is_null() | (lowered == "") | lowered.is_in(PLACEHOLDER_VALUES)
    meaningful_value = pl.when(is_na | is_taxonomy_miss).then(None).otherwise(normalized_text)
    return normalized_text, is_na, is_taxonomy_miss, meaningful_value


def meaningful_value_expr(column: str) -> pl.Expr:
    """Return a Polars expression that keeps only meaningful values.

    N/A placeholders and taxonomy-miss strings are mapped to null so callers can
    derive distinct meaningful values without special-casing placeholders.
    """

    return _value_class_expr(column)[3]


def _group_cols(parents_df: pl.DataFrame) -> list[str]:
    columns, _ = get_schema_and_column_names(parents_df)
    if "canonical_id" not in columns:
        return []
    group_cols = ["canonical_id"]
    if "category_key" in columns:
        group_cols.append("category_key")
    return group_cols


def _candidate_attribute_columns(
    parents_df: pl.DataFrame,
    *,
    group_cols: Sequence[str],
    exclude_columns: set[str] | None = None,
) -> list[str]:
    columns, schema = get_schema_and_column_names(parents_df)
    excluded = exclude_columns or ATTRIBUTE_EXCLUDE_COLUMNS
    candidate_columns: list[str] = []
    for column in columns:
        if column in excluded or column in group_cols:
            continue
        if schema is not None and schema.get(column) == pl.List:
            continue
        candidate_columns.append(column)
    return candidate_columns


def map_attribute_conflicts(
    parents_df: pl.DataFrame,
    *,
    retailer_priority: Sequence[str] | None = None,
    retailer_col: str = "retailer",
    group_cols: Sequence[str] | None = None,
    exclude_columns: set[str] | None = None,
    attribute_columns: Sequence[str] | None = None,
) -> pl.DataFrame:
    """Map (product, attribute) groups that have >1 meaningful value across retailers."""
    if parents_df.is_empty() or retailer_col not in parents_df.columns:
        return pl.DataFrame()

    resolved_group_cols = list(group_cols) if group_cols is not None else _group_cols(parents_df)
    if not resolved_group_cols:
        return pl.DataFrame()
    if any(col not in parents_df.columns for col in resolved_group_cols):
        return pl.DataFrame()

    priority = [str(r).strip().lower() for r in (retailer_priority or DEFAULT_RETAILER_PRIORITY) if str(r).strip()]
    excluded = set(exclude_columns) if exclude_columns is not None else ATTRIBUTE_EXCLUDE_COLUMNS
    if attribute_columns is None:
        candidate_columns = _candidate_attribute_columns(
            parents_df, group_cols=resolved_group_cols, exclude_columns=excluded
        )
    else:
        candidate_columns = [
            col
            for col in attribute_columns
            if col in parents_df.columns and col not in resolved_group_cols and col not in excluded
        ]
    if not candidate_columns:
        return pl.DataFrame()

    retailer_norm = (
        pl.col(retailer_col).cast(pl.Utf8).str.strip_chars().str.to_lowercase().alias("__retailer_norm")
    )
    rank = _retailer_rank_expr(retailer_col, priority).alias("__rank")

    frames: list[pl.DataFrame] = []
    for attribute in candidate_columns:
        _, _is_na, _is_taxonomy_miss, meaningful_value = _value_class_expr(attribute)
        meaningful_rows = (
            parents_df.select([*resolved_group_cols, retailer_norm, rank, meaningful_value.alias("__meaningful")])
            .filter(pl.col("__meaningful").is_not_null())
        )
        if meaningful_rows.is_empty():
            continue

        grouped = meaningful_rows.group_by(resolved_group_cols).agg(
            pl.col("__meaningful").unique().alias("values"),
            pl.col("__meaningful").n_unique().alias("distinct_meaningful_values"),
            pl.col("__meaningful").sort_by(["__rank", "__retailer_norm"]).first().alias("chosen_value"),
            pl.col("__retailer_norm").sort_by(["__rank", "__retailer_norm"]).first().alias("chosen_retailer"),
        ).with_columns(
            pl.col("values").list.sort()
        )

        conflicts = (
            grouped.filter(pl.col("distinct_meaningful_values") > 1)
            .with_columns(pl.lit(attribute).alias("attribute"))
            .select(
                [
                    *resolved_group_cols,
                    "attribute",
                    "distinct_meaningful_values",
                    "values",
                    "chosen_retailer",
                    "chosen_value",
                ]
            )
        )
        if not conflicts.is_empty():
            frames.append(conflicts)

    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def resolve_attribute_conflicts(
    parents_df: pl.DataFrame,
    *,
    retailer_priority: Sequence[str] | None = None,
    retailer_col: str = "retailer",
    group_cols: Sequence[str] | None = None,
    exclude_columns: set[str] | None = None,
    attribute_columns: Sequence[str] | None = None,
) -> pl.DataFrame:
    """Resolve conflicts by forcing a single meaningful value per group.

    Rules:
    - Choose among meaningful values only (meaningful beats taxonomy-miss regardless of retailer priority).
    - Overwrite all non-N/A rows (including taxonomy-miss) to the chosen value.
    - Leave N/A rows for the subsequent fill step.
    """
    if parents_df.is_empty() or retailer_col not in parents_df.columns:
        return parents_df

    resolved_group_cols = list(group_cols) if group_cols is not None else _group_cols(parents_df)
    if not resolved_group_cols:
        LOGGER.info("Skipping attribute resolve: grouping columns unavailable.")
        return parents_df
    if any(col not in parents_df.columns for col in resolved_group_cols):
        LOGGER.info("Skipping attribute resolve: grouping columns missing from frame.")
        return parents_df

    priority = [str(r).strip().lower() for r in (retailer_priority or DEFAULT_RETAILER_PRIORITY) if str(r).strip()]
    excluded = set(exclude_columns) if exclude_columns is not None else ATTRIBUTE_EXCLUDE_COLUMNS
    if attribute_columns is None:
        candidate_columns = _candidate_attribute_columns(
            parents_df, group_cols=resolved_group_cols, exclude_columns=excluded
        )
    else:
        candidate_columns = [
            col
            for col in attribute_columns
            if col in parents_df.columns and col not in resolved_group_cols and col not in excluded
        ]
    if not candidate_columns:
        LOGGER.info("No attribute columns found for cross-retailer resolution.")
        return parents_df

    retailer_norm = (
        pl.col(retailer_col).cast(pl.Utf8).str.strip_chars().str.to_lowercase().alias("__retailer_norm")
    )
    rank = _retailer_rank_expr(retailer_col, priority).alias("__rank")

    result = parents_df
    for attribute in candidate_columns:
        _, is_na, _is_taxonomy_miss, meaningful_value = _value_class_expr(attribute)
        meaningful_rows = (
            result.select([*resolved_group_cols, retailer_norm, rank, meaningful_value.alias("__meaningful")])
            .filter(pl.col("__meaningful").is_not_null())
        )
        if meaningful_rows.is_empty():
            continue

        chosen = meaningful_rows.group_by(resolved_group_cols).agg(
            pl.col("__meaningful")
            .sort_by(["__rank", "__retailer_norm"])
            .first()
            .alias("__chosen_value")
        )
        result = result.join(chosen, on=resolved_group_cols, how="left")
        result = result.with_columns(is_na.alias("__is_na"))

        overwritten = get_row_count(
            result.filter(pl.col("__chosen_value").is_not_null() & (~pl.col("__is_na")))
        )
        result = result.with_columns(
            pl.when(pl.col("__chosen_value").is_not_null() & (~pl.col("__is_na")))
            .then(pl.col("__chosen_value"))
            .otherwise(pl.col(attribute))
            .alias(attribute)
        ).drop(["__chosen_value", "__is_na"])

        if overwritten:
            LOGGER.info("Resolved %s %s values using preferred retailers.", overwritten, attribute)

    return result


def map_attribute_na_fill_candidates(
    parents_df: pl.DataFrame,
    *,
    retailer_priority: Sequence[str] | None = None,
    retailer_col: str = "retailer",
    group_cols: Sequence[str] | None = None,
    exclude_columns: set[str] | None = None,
    attribute_columns: Sequence[str] | None = None,
) -> pl.DataFrame:
    """Map (product, attribute) groups where at least one row is N/A and a meaningful value exists."""
    if parents_df.is_empty() or retailer_col not in parents_df.columns:
        return pl.DataFrame()

    resolved_group_cols = list(group_cols) if group_cols is not None else _group_cols(parents_df)
    if not resolved_group_cols:
        return pl.DataFrame()
    if any(col not in parents_df.columns for col in resolved_group_cols):
        return pl.DataFrame()

    priority = [str(r).strip().lower() for r in (retailer_priority or DEFAULT_RETAILER_PRIORITY) if str(r).strip()]
    excluded = set(exclude_columns) if exclude_columns is not None else ATTRIBUTE_EXCLUDE_COLUMNS
    if attribute_columns is None:
        candidate_columns = _candidate_attribute_columns(
            parents_df, group_cols=resolved_group_cols, exclude_columns=excluded
        )
    else:
        candidate_columns = [
            col
            for col in attribute_columns
            if col in parents_df.columns and col not in resolved_group_cols and col not in excluded
        ]
    if not candidate_columns:
        return pl.DataFrame()

    retailer_norm = (
        pl.col(retailer_col).cast(pl.Utf8).str.strip_chars().str.to_lowercase().alias("__retailer_norm")
    )
    rank = _retailer_rank_expr(retailer_col, priority).alias("__rank")

    frames: list[pl.DataFrame] = []
    for attribute in candidate_columns:
        _, is_na, _is_taxonomy_miss, meaningful_value = _value_class_expr(attribute)
        meaningful_rows = (
            parents_df.select([*resolved_group_cols, retailer_norm, rank, meaningful_value.alias("__meaningful")])
            .filter(pl.col("__meaningful").is_not_null())
        )
        if meaningful_rows.is_empty():
            continue

        chosen = meaningful_rows.group_by(resolved_group_cols).agg(
            pl.col("__meaningful")
            .sort_by(["__rank", "__retailer_norm"])
            .first()
            .alias("chosen_value")
        )
        with_choice = parents_df.join(chosen, on=resolved_group_cols, how="left").with_columns(
            is_na.alias("__is_na")
        )
        candidates = with_choice.filter(pl.col("chosen_value").is_not_null() & pl.col("__is_na"))
        if candidates.is_empty():
            continue

        summary = candidates.group_by(resolved_group_cols).agg(
            pl.len().alias("na_rows"),
            pl.col(retailer_col)
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .unique()
            .alias("retailers_na"),
            pl.col("chosen_value").first(),
        ).with_columns(
            pl.col("retailers_na").list.sort()
        )
        summary = summary.with_columns(pl.lit(attribute).alias("attribute")).select(
            [*resolved_group_cols, "attribute", "na_rows", "retailers_na", "chosen_value"]
        )
        frames.append(summary)

    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def fill_missing_attribute_values(
    parents_df: pl.DataFrame,
    *,
    retailer_priority: Sequence[str] | None = None,
    retailer_col: str = "retailer",
    group_cols: Sequence[str] | None = None,
    exclude_columns: set[str] | None = None,
    attribute_columns: Sequence[str] | None = None,
) -> pl.DataFrame:
    """Fill N/A rows from the resolved meaningful value (does not propagate taxonomy-miss)."""
    if parents_df.is_empty() or retailer_col not in parents_df.columns:
        return parents_df

    resolved_group_cols = list(group_cols) if group_cols is not None else _group_cols(parents_df)
    if not resolved_group_cols:
        LOGGER.info("Skipping attribute fill: grouping columns unavailable.")
        return parents_df
    if any(col not in parents_df.columns for col in resolved_group_cols):
        LOGGER.info("Skipping attribute fill: grouping columns missing from frame.")
        return parents_df

    priority = [str(r).strip().lower() for r in (retailer_priority or DEFAULT_RETAILER_PRIORITY) if str(r).strip()]
    excluded = set(exclude_columns) if exclude_columns is not None else ATTRIBUTE_EXCLUDE_COLUMNS
    if attribute_columns is None:
        candidate_columns = _candidate_attribute_columns(
            parents_df, group_cols=resolved_group_cols, exclude_columns=excluded
        )
    else:
        candidate_columns = [
            col
            for col in attribute_columns
            if col in parents_df.columns and col not in resolved_group_cols and col not in excluded
        ]
    if not candidate_columns:
        LOGGER.info("No attribute columns found for cross-retailer fill.")
        return parents_df

    retailer_norm = (
        pl.col(retailer_col).cast(pl.Utf8).str.strip_chars().str.to_lowercase().alias("__retailer_norm")
    )
    rank = _retailer_rank_expr(retailer_col, priority).alias("__rank")

    result = parents_df
    for attribute in candidate_columns:
        _, is_na, _is_taxonomy_miss, meaningful_value = _value_class_expr(attribute)
        meaningful_rows = (
            result.select([*resolved_group_cols, retailer_norm, rank, meaningful_value.alias("__meaningful")])
            .filter(pl.col("__meaningful").is_not_null())
        )
        if meaningful_rows.is_empty():
            continue

        chosen = meaningful_rows.group_by(resolved_group_cols).agg(
            pl.col("__meaningful")
            .sort_by(["__rank", "__retailer_norm"])
            .first()
            .alias("__chosen_value")
        )
        result = result.join(chosen, on=resolved_group_cols, how="left")
        result = result.with_columns(is_na.alias("__is_na"))

        filled = get_row_count(
            result.filter(pl.col("__chosen_value").is_not_null() & pl.col("__is_na"))
        )
        result = result.with_columns(
            pl.when(pl.col("__chosen_value").is_not_null() & pl.col("__is_na"))
            .then(pl.col("__chosen_value"))
            .otherwise(pl.col(attribute))
            .alias(attribute)
        ).drop(["__chosen_value", "__is_na"])

        if filled:
            LOGGER.info("Filled %s %s N/A values from resolved value.", filled, attribute)

    return result


def fill_unique_attribute_values(parents_df: pl.DataFrame) -> pl.DataFrame:
    """Backwards-compatible wrapper used by the pre-join pipeline."""

    if parents_df.is_empty():
        return parents_df

    columns, schema = get_schema_and_column_names(parents_df)
    if "canonical_id" not in columns:
        LOGGER.info("Skipping attribute fill: canonical_id missing from parent cache.")
        return parents_df

    resolved = resolve_attribute_conflicts(parents_df)
    return fill_missing_attribute_values(resolved)
