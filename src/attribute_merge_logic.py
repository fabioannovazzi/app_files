from __future__ import annotations

from typing import Dict, Iterable, Optional
import re

import polars as pl
from polars.exceptions import ColumnNotFoundError

import logging

from modules.utilities.utils import (
    get_row_count,
    get_schema_and_column_names,
    is_valid_lazyframe,
)

__all__ = [
    "merge_attribute_results",
    "try_merge_attribute_results",
    "propagate_attribute_results",
]


logger = logging.getLogger(__name__)


def _raise_if_empty(
    df: pl.DataFrame | pl.LazyFrame | None,
    name: str,
    dataset: str | None,
) -> None:
    """Raise ``ValueError`` if ``df`` has zero rows or columns."""

    if df is None:
        return

    columns, schema = get_schema_and_column_names(df)
    if len(columns) == 0 or get_row_count(df) == 0:
        prefix = f"{dataset}: " if dataset else ""
        raise ValueError(
            f"{prefix}{name} dataframe is empty (rows={get_row_count(df)}, cols={len(columns)})"
        )


# Columns produced by the Add Attributes workflow that should not be merged
# back onto the main dataset. These originate from Pareto ranking or impact
# analysis and are metrics rather than actual attributes.
_METRIC_COLUMNS: set[str] = {
    "rank",
    "cum_share",
    "total_amount",
    "total_units",
    "total_volume",
    "average_price",
    "Sales",
    "Units",
    "Price",
    "period_amount",
    "months_since_launch",
    "avg_month_sales",
    "TopProduct",
}

_NUMERIC_TYPES = {
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
    pl.Float32,
    pl.Float64,
}


def _normalize_attribute_column(name: str) -> str:
    """Return a normalised attribute column name.

    Spaces and punctuation are replaced with underscores and the result is
    converted to title case to align with the app's standard column naming.
    """

    cleaned = re.sub(r"[\.:'\"]", "", str(name).strip())
    cleaned = re.sub(r"[\s\-/]+", "_", cleaned)
    cleaned = re.sub(r"__+", "_", cleaned).strip("_")
    return cleaned.title() if cleaned else str(name)


def _find_column(name: str | None, columns: Iterable[str]) -> str | None:
    """Return ``name`` matched case-insensitively within ``columns``."""
    if not name:
        return None
    if name in columns:
        return name
    lookup = {c.lower(): c for c in columns}
    return lookup.get(name.lower())


def _diagnose_column_mismatch(name: str, columns: Iterable[str]) -> str | None:
    """Return a hint when ``name`` nearly matches one of ``columns``."""
    target = name.strip().lower()
    for col in columns:
        if col.strip().lower() == target and col != name:
            return f"Did you mean '{col}'?"
    return None


def _norm(s: str) -> str:
    """Normalise a column name for fuzzy matching.

    Lowercase and strip all non-alphanumeric characters so that
    'Formula Base', 'formula_base' and 'FORMULA-BASE' match.
    """
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def merge_attribute_results(
    df: pl.DataFrame | pl.LazyFrame | None,
    mapping: Dict[str, Optional[str]],
    scores: pl.DataFrame | pl.LazyFrame | None = None,
    classification: pl.DataFrame | pl.LazyFrame | None = None,
    *,
    group_col: str | None = None,
    include_scores: bool = False,
    allow_numeric_attributes: bool = False,
) -> pl.DataFrame | pl.LazyFrame | None:
    """Return ``df`` joined with attribute results.

    Parameters
    ----------
    df:
        Main dataset to augment.
    mapping:
        Mapping dictionary containing the product column name.
    scores:
        Optional score data to join.
    classification:
        Optional classification data to join.
    group_col:
        When provided, joins are performed on ``product_col`` and ``group_col``.
    include_scores:
        When ``True``, numeric columns ending with ``_score`` are merged.
    allow_numeric_attributes:
        When ``True``, allows non-score numeric attribute columns to merge.
    """
    if df is None:
        return None

    columns, schema = get_schema_and_column_names(df)
    if len(columns) == 0 or get_row_count(df) == 0:
        raise ValueError(
            f"Empty DataFrame: no columns to merge (rows={get_row_count(df)}, cols={len(columns)})"
        )

    product_key = mapping.get("product_column")
    if not product_key:
        return df
    columns, schema = get_schema_and_column_names(df)
    product_col = _find_column(product_key, columns)
    if product_col is None:
        columns, schema = get_schema_and_column_names(df)
        hint = _diagnose_column_mismatch(product_key, columns)
        extras = f" {hint}" if hint else f" Available columns: {columns}"
        raise ColumnNotFoundError(
            f"Product column '{product_key}' not found in provided DataFrame.{extras}"
        )

    original_rows = get_row_count(df)
    original_columns = set(columns)
    base_columns = set(original_columns)
    columns, schema = get_schema_and_column_names(df)
    group_col_df = _find_column(group_col, columns) if group_col else None

    join_cols = [product_col]
    if group_col_df:
        join_cols.append(group_col_df)

    def _to_same_type(
        other: pl.DataFrame | pl.LazyFrame | None,
    ) -> pl.DataFrame | pl.LazyFrame | None:
        if other is None:
            return None
        if isinstance(df, pl.DataFrame) and isinstance(other, pl.LazyFrame):
            return other.collect()
        if isinstance(df, pl.LazyFrame) and isinstance(other, pl.DataFrame):
            return other.lazy()
        return other

    scores_conv = _to_same_type(scores)
    classification_conv = _to_same_type(classification)

    is_numeric_dtype = getattr(pl.datatypes, "is_numeric_dtype", None)

    def _select_attrs(
        tbl: pl.DataFrame | pl.LazyFrame | None,
        join_cols_local: list[str],
        *,
        allow_numeric_scores: bool = False,
        allow_numeric_columns: bool = False,
    ) -> tuple[list[str] | None, int]:
        """Return attribute columns eligible for joining and count."""

        if tbl is None:
            return None, 0
        columns, schema = get_schema_and_column_names(df)
        existing = {c.lower() for c in columns}
        existing_norm = {_norm(c) for c in columns}
        eligible: list[str] = []
        columns, schema = get_schema_and_column_names(tbl)
        for name, dtype in schema.items():
            if name in join_cols_local or name in _METRIC_COLUMNS:
                continue
            # Avoid adding near-duplicate columns that differ only by case/spacing/underscores
            if name.lower() in existing or _norm(name) in existing_norm:
                continue
            if dtype in (pl.Categorical, pl.Utf8):
                eligible.append(name)
            else:
                is_numeric = (
                    is_numeric_dtype(dtype)
                    if is_numeric_dtype
                    else dtype in _NUMERIC_TYPES
                )
                if (
                    allow_numeric_scores
                    and is_numeric
                    and name.lower().endswith("_score")
                ):
                    eligible.append(name)
                elif allow_numeric_columns and is_numeric:
                    eligible.append(name)

        return ([*join_cols_local, *eligible] if eligible else None, len(eligible))

    if isinstance(scores_conv, (pl.DataFrame, pl.LazyFrame)):
        columns, schema = get_schema_and_column_names(scores_conv)
        prod_score_col = _find_column(product_col, columns)
        group_score_col = _find_column(group_col_df, columns) if group_col_df else None
        if prod_score_col is None:
            hint = _diagnose_column_mismatch(product_col, columns)
            extras = f" {hint}" if hint else f" Available columns: {columns}"
            raise ColumnNotFoundError(
                f"Product column '{product_col}' not found in scores DataFrame.{extras}"
            )
        if group_col_df and group_score_col is None:
            hint = _diagnose_column_mismatch(group_col_df, columns)
            extras = f" {hint}" if hint else f" Available columns: {columns}"
            raise ColumnNotFoundError(
                f"Group column '{group_col_df}' not found in scores DataFrame.{extras}"
            )
        if prod_score_col:
            rename_map: dict[str, str] = {}
            if prod_score_col != product_col:
                rename_map[prod_score_col] = product_col
            if group_col_df and group_score_col and group_score_col != group_col_df:
                rename_map[group_score_col] = group_col_df
            if rename_map:
                scores_conv = scores_conv.rename(rename_map)
            join_cols_scores = [product_col]
            if group_col_df and group_score_col:
                join_cols_scores.append(group_col_df)
            cols, n = _select_attrs(
                scores_conv,
                join_cols_scores,
                allow_numeric_scores=include_scores,
                allow_numeric_columns=False,
            )
            if cols:
                df = df.join(scores_conv.select(cols), on=join_cols_scores, how="left")

    if isinstance(classification_conv, (pl.DataFrame, pl.LazyFrame)):
        columns, schema = get_schema_and_column_names(classification_conv)
        prod_class_col = _find_column(product_col, columns)
        group_class_col = _find_column(group_col_df, columns) if group_col_df else None
        if prod_class_col is None:
            hint = _diagnose_column_mismatch(product_col, columns)
            extras = f" {hint}" if hint else f" Available columns: {columns}"
            raise ColumnNotFoundError(
                f"Product column '{product_col}' not found in classification DataFrame.{extras}"
            )
        if group_col_df and group_class_col is None:
            hint = _diagnose_column_mismatch(group_col_df, columns)
            extras = f" {hint}" if hint else f" Available columns: {columns}"
            raise ColumnNotFoundError(
                f"Group column '{group_col_df}' not found in classification DataFrame.{extras}"
            )
        if prod_class_col:
            rename_map: dict[str, str] = {}
            if prod_class_col != product_col:
                rename_map[prod_class_col] = product_col
            if group_col_df and group_class_col and group_class_col != group_col_df:
                rename_map[group_class_col] = group_col_df
            if rename_map:
                classification_conv = classification_conv.rename(rename_map)
            join_cols_class = [product_col]
            if group_col_df and group_class_col:
                join_cols_class.append(group_col_df)

            columns_df, _ = get_schema_and_column_names(df)
            existing_map = {c.lower(): c for c in columns_df}
            existing_norm_map = {_norm(c): c for c in columns_df}
            columns_cls, _ = get_schema_and_column_names(classification_conv)
            attr_cols = [
                c
                for c in columns_cls
                if c not in join_cols_class and c not in _METRIC_COLUMNS
            ]
            # Prefer exact (case-insensitive) matches; fall back to normalised mapping
            override_map: dict[str, str] = {}
            for c in attr_cols:
                cl = c.lower()
                if cl in existing_map:
                    override_map[c] = existing_map[cl]
                else:
                    cn = _norm(c)
                    if cn in existing_norm_map:
                        override_map[c] = existing_norm_map[cn]

            # Ensure existing columns that will be overridden use normalised naming.
            override_updates: dict[str, str] = {}
            join_col_set = set(join_cols_class)
            for src_name, target_name in list(override_map.items()):
                if target_name in join_col_set:
                    continue
                normalised = _normalize_attribute_column(target_name)
                if normalised != target_name and normalised not in original_columns:
                    logger.info(
                        "merge-attrs: normalising existing column '%s' -> '%s'",
                        target_name,
                        normalised,
                    )
                    df = df.rename({target_name: normalised})
                    original_columns.remove(target_name)
                    original_columns.add(normalised)
                    override_updates[src_name] = normalised
                elif normalised != target_name and normalised in original_columns:
                    logger.info(
                        "merge-attrs: skipped normalising '%s' -> '%s' due to existing column",
                        target_name,
                        normalised,
                    )
            if override_updates:
                override_map.update(override_updates)
                columns, schema = get_schema_and_column_names(df)
                existing_map = {c.lower(): c for c in columns}
                existing_norm_map = {_norm(c): c for c in columns}

            classification_new = (
                classification_conv.drop(list(override_map))
                if override_map
                else classification_conv
            )
            cols, n = _select_attrs(
                classification_new,
                join_cols_class,
                allow_numeric_scores=False,
                allow_numeric_columns=allow_numeric_attributes,
            )
            if cols:
                cols_filtered: list[str] = list(join_cols_class)
                rename_new: dict[str, str] = {}
                for col in cols:
                    if col in join_cols_class:
                        continue
                    normalized = _normalize_attribute_column(col)
                    target_name = normalized if normalized else col
                    target_in_original = target_name in original_columns
                    if target_in_original:
                        logger.info(
                            "merge-attrs: skipped new column '%s' due to duplicate target '%s'",
                            col,
                            target_name,
                        )
                        continue
                    cols_filtered.append(col)
                    if normalized and normalized != col:
                        rename_new[col] = normalized
                if len(cols_filtered) > len(join_cols_class):
                    frame_new = classification_new.select(cols_filtered)
                    if rename_new:
                        frame_new = frame_new.rename(rename_new)
                        original_columns.update(rename_new.values())
                    else:
                        original_columns.update([c for c in cols_filtered if c not in join_cols_class])
                    df = df.join(frame_new, on=join_cols_class, how="left")

            if override_map:
                renamed = classification_conv.rename(
                    {k: v for k, v in override_map.items() if k != v}
                )
                cols_override = list(override_map.values())
                df = df.join(
                    renamed.select(join_cols_class + cols_override),
                    on=join_cols_class,
                    how="left",
                    suffix="_new",
                )
                df = df.with_columns(
                    [
                        pl.when(pl.col(f"{c}_new").is_not_null())
                        .then(pl.col(f"{c}_new"))
                        .otherwise(pl.col(c))
                        .alias(c)
                        for c in cols_override
                    ]
                ).drop([f"{c}_new" for c in cols_override])

    new_rows = get_row_count(df)
    if new_rows != original_rows:
        raise ValueError(
            (
                "Row count changed after merging attribute results: "
                f"expected {original_rows} rows, got {new_rows}. "
                "Ensure attribute tables have one row per product."
            )
        )

    columns, schema = get_schema_and_column_names(df)
    added_raw = [c for c in columns if c not in base_columns]
    rename_map: dict[str, str] = {}
    taken: set[str] = set(columns)
    for col in added_raw:
        normalized = _normalize_attribute_column(col)
        if (
            normalized
            and normalized != col
            and normalized not in original_columns
            and normalized not in taken
        ):
            rename_map[col] = normalized
            taken.add(normalized)
    if rename_map:
        logger.debug(
            "merge-attrs: renaming columns (before=%s, rename_map=%s)",
            added_raw,
            rename_map,
        )
        df = df.rename(rename_map)
        columns, schema = get_schema_and_column_names(df)
    else:
        logger.debug("merge-attrs: no column renames applied (added=%s)", added_raw)

    # Replace nulls in newly added product attribute columns with "N/A"
    added_columns = [c for c in columns if c not in base_columns]
    fill_cols: list[str] = []
    for col in added_columns:
        dtype = schema.get(col) if schema else None
        lower = col.lower()
        is_text = dtype in (pl.Utf8, pl.Categorical)
        is_score_metric = lower.endswith("_score")
        is_narrative = lower.endswith(("_explanation", "_confidence"))
        if is_text or is_narrative or is_score_metric:
            fill_cols.append(col)

    if fill_cols:
        df = df.with_columns(
            [pl.col(c).cast(pl.Utf8).fill_null("N/A").alias(c) for c in fill_cols]
        )

    return df


def try_merge_attribute_results(
    df: pl.DataFrame | pl.LazyFrame | None,
    mapping: Dict[str, Optional[str]],
    scores: pl.DataFrame | pl.LazyFrame | None = None,
    classification: pl.DataFrame | pl.LazyFrame | None = None,
    *,
    group_col: str | None = None,
    include_scores: bool = False,
    dataset_name: str | None = None,
    allow_numeric_attributes: bool = False,
) -> tuple[pl.DataFrame | pl.LazyFrame | None, str | None]:
    """Return merged data and raise on failure.

    This wrapper catches ``ValueError`` from :func:`merge_attribute_results`
    and re-raises it with additional context such as the ``dataset_name``
    and shape information. The previous behaviour of returning a warning
    string is replaced with raising a ``ValueError`` so that callers can
    handle the error explicitly.

    Parameters
    ----------
    allow_numeric_attributes:
        When ``True``, allows non-score numeric attribute columns to merge.
    """

    if df is None:
        return None, None

    _raise_if_empty(df, "main", dataset_name)
    _raise_if_empty(scores, "scores", dataset_name)
    _raise_if_empty(classification, "classification", dataset_name)

    try:
        merged = merge_attribute_results(
            df,
            mapping,
            scores,
            classification,
            group_col=group_col,
            include_scores=include_scores,
            allow_numeric_attributes=allow_numeric_attributes,
        )
        return merged, None
    except ValueError as exc:  # pragma: no cover - defensive branch
        columns, schema = get_schema_and_column_names(df)
        prefix = f"{dataset_name}: " if dataset_name else ""
        msg = (
            f"{prefix}Failed to merge attributes - {exc} "
            f"(rows={get_row_count(df)}, cols={len(columns)})"
        )
        raise ValueError(msg) from exc


def propagate_attribute_results(
    df_dates: pl.DataFrame | pl.LazyFrame | None,
    df_periods: pl.DataFrame | pl.LazyFrame | None,
    df_all_periods: pl.DataFrame | pl.LazyFrame | None,
    df_plan: pl.DataFrame | pl.LazyFrame | None,
    mapping: Dict[str, Optional[str]],
    scores: pl.DataFrame | pl.LazyFrame | None = None,
    classification: pl.DataFrame | pl.LazyFrame | None = None,
    *,
    group_col: str | None = None,
    include_scores: bool = False,
) -> tuple[
    pl.DataFrame | pl.LazyFrame | None,
    pl.DataFrame | pl.LazyFrame | None,
    pl.DataFrame | pl.LazyFrame | None,
    pl.DataFrame | pl.LazyFrame | None,
]:
    """Merge attribute results into additional datasets when valid."""

    if is_valid_lazyframe(df_dates):
        df_dates, _ = try_merge_attribute_results(
            df_dates,
            mapping,
            scores,
            classification,
            group_col=group_col,
            include_scores=include_scores,
            dataset_name="dates",
        )

    if is_valid_lazyframe(df_periods):
        df_periods, _ = try_merge_attribute_results(
            df_periods,
            mapping,
            scores,
            classification,
            group_col=group_col,
            include_scores=include_scores,
            dataset_name="periods",
        )

    if is_valid_lazyframe(df_all_periods):
        df_all_periods, _ = try_merge_attribute_results(
            df_all_periods,
            mapping,
            scores,
            classification,
            group_col=group_col,
            include_scores=include_scores,
            dataset_name="all_periods",
        )

    if is_valid_lazyframe(df_plan):
        df_plan, _ = try_merge_attribute_results(
            df_plan,
            mapping,
            scores,
            classification,
            group_col=group_col,
            include_scores=include_scores,
            dataset_name="plan",
        )

    return df_dates, df_periods, df_all_periods, df_plan
