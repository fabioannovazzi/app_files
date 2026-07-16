"""Helpers to join uploaded attribute Excel files."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import polars as pl

from modules.utilities.utils import get_schema_and_column_names
from src.attribute_merge_logic import merge_attribute_results

__all__ = [
    "merge_attributes_from_excel",
    "merge_or_classify_attributes_from_excel",
    "shared_columns",
]


DEFAULT_NUMERIC_SUFFIXES: tuple[str, ...] = (
    "_total",
    "_amount",
    "_units",
    "_price",
    "_volume",
    "_qty",
    "_quantity",
)


def _looks_numeric_metric(name: str, suffixes: set[str] | tuple[str, ...]) -> bool:
    lower = name.lower()
    if any(lower.endswith(suf) for suf in suffixes):
        return True
    if lower in {
        "total_amount",
        "total_units",
        "price",
        "rank",
        "cum_pct",
        "cumulative_percent",
    }:
        return True
    if "cumulative" in lower and ("pct" in lower or "%" in lower):
        return True
    return False


def _allowed_attributes(category: str) -> set[str]:
    """Return attribute IDs allowed for ``category``."""
    from modules.add_attributes.attribute_taxonomy import get_attribute_taxonomy

    taxonomy = get_attribute_taxonomy() or {}
    categories = taxonomy.get("categories") or []
    cat_id = str(category).lower()
    for cat in categories:
        if str(cat.get("id", "")).lower() == cat_id:
            attrs = cat.get("attributes") or []
            return {str(a.get("id")) for a in attrs if a.get("id")}
    return set()


def _collect_leaves(nodes: list[dict] | None) -> set[str]:
    """Return leaf ``id`` values from ``nodes``."""
    leaves: set[str] = set()
    for node in nodes or []:
        node_id = node.get("id")
        children = node.get("children") or node.get("nodes")
        if children:
            leaves.update(_collect_leaves(children))
        elif node_id:
            leaves.add(str(node_id))
    return leaves


def _allowed_leaves(category: str) -> set[str]:
    """Return all leaf IDs allowed for ``category``."""
    from modules.add_attributes.attribute_taxonomy import get_attribute_taxonomy

    taxonomy = get_attribute_taxonomy() or {}
    categories = taxonomy.get("categories") or []
    cat_id = str(category).lower()
    for cat in categories:
        if str(cat.get("id", "")).lower() == cat_id:
            leaves: set[str] = set()
            for attr in cat.get("attributes") or []:
                leaves.update(_collect_leaves(attr.get("nodes")))
            return leaves
    return set()


def _read_excel(file: str | Path | bytes | BytesIO) -> pl.DataFrame:
    """Return a DataFrame loaded from the given Excel file."""
    if isinstance(file, (str, Path)):
        return pl.read_excel(file, engine="openpyxl")
    if isinstance(file, (bytes, bytearray)):
        return pl.read_excel(BytesIO(file), engine="openpyxl")
    return pl.read_excel(file, engine="openpyxl")


def shared_columns(
    df: pl.DataFrame | pl.LazyFrame, file: str | Path | bytes | BytesIO
) -> list[str]:
    """Return sorted list of columns present in both ``df`` and ``file``."""
    excel_cols = get_schema_and_column_names(_read_excel(file))[0]
    df_cols, _ = get_schema_and_column_names(df)
    return sorted(set(df_cols) & set(excel_cols))


def merge_attributes_from_excel(
    df: pl.DataFrame | pl.LazyFrame,
    file: str | Path | bytes | BytesIO,
    *,
    product_col: str,
    category_col: str,
    return_debug: bool = False,
    enforce_taxonomy: bool = True,
    exclude_numeric: bool = False,
    excluded_columns: set[str] | None = None,
) -> pl.DataFrame | pl.LazyFrame | tuple[pl.DataFrame | pl.LazyFrame, dict]:
    """Merge attribute leaves from ``file`` into ``df``.

    The merge is performed on ``product_col`` and respects allowed attributes per
    category defined in the taxonomy. Rows whose category is unknown are skipped.
    """

    attrs = _read_excel(file)
    cols, _ = get_schema_and_column_names(attrs)
    df_cols, _ = get_schema_and_column_names(df)

    diagnostics: dict[str, Any] = {
        "dataset_columns": df_cols,
        "excel_columns": cols,
        "shared_columns": sorted(set(df_cols) & set(cols)),
        "matched_columns": set(),
        "allowed_leaves_by_category": {},
        "categories_without_allowed": [],
        "categories_missing_columns": {},
        "enforce_taxonomy": enforce_taxonomy,
        "numeric_columns_skipped": set(),
        "duplicate_products": [],
        "row_count_changed": False,
        "original_row_count": None,
        "joined_row_count": None,
    }

    merged_attribute_columns: set[str] = set()
    used_target_columns: set[str] = set()
    df_cols_lower: dict[str, str] = {}
    for col in df_cols:
        df_cols_lower.setdefault(col.lower(), col)

    for col_name in (product_col, category_col):
        if col_name not in cols:
            raise KeyError(f"Column {col_name!r} not found in Excel file")
        if col_name not in df_cols:
            raise KeyError(f"Column {col_name!r} not found in dataset")

    results: list[pl.DataFrame] = []

    excluded = set(excluded_columns or [])
    numeric_suffixes = set(DEFAULT_NUMERIC_SUFFIXES)

    numeric_skipped: set[str] = set()

    if not enforce_taxonomy:
        attr_cols = []
        for col in cols:
            if col in {product_col, category_col}:
                continue
            if col in excluded:
                continue
            if exclude_numeric and _looks_numeric_metric(col, numeric_suffixes):
                numeric_skipped.add(col)
                continue
            attr_cols.append(col)
        rename_map: dict[str, str] = {}
        for col in attr_cols:
            target = df_cols_lower.get(col.lower(), col)
            if exclude_numeric and _looks_numeric_metric(target, numeric_suffixes):
                numeric_skipped.add(target)
                continue
            if target in excluded or target in used_target_columns:
                continue
            rename_map[col] = target
            used_target_columns.add(target)
        diagnostics["matched_columns"].update(rename_map.values())
        merged_attribute_columns.update(rename_map.values())
        if rename_map:
            subset = attrs.select([product_col] + list(rename_map.keys())).rename(
                rename_map
            )
            results.append(subset)
        else:
            diagnostics["categories_missing_columns"]["__all__"] = []
    else:
        for cat in attrs.get_column(category_col).unique().to_list():
            cat_key = str(cat)
            allowed = _allowed_leaves(cat_key)
            diagnostics["allowed_leaves_by_category"][cat_key] = sorted(allowed)
            if not allowed:
                diagnostics["categories_without_allowed"].append(cat_key)
                continue
            rows = attrs.filter(pl.col(category_col) == cat)
            allowed_lower = {a.lower(): a for a in allowed}
            attr_cols = [col for col in cols if col.lower() in allowed_lower]
            if not attr_cols:
                diagnostics["categories_missing_columns"][cat_key] = sorted(
                    allowed
                )
                continue
            rename_map: dict[str, str] = {}
            for col in attr_cols:
                resolved = allowed_lower[col.lower()]
                if resolved in excluded:
                    continue
                if exclude_numeric and _looks_numeric_metric(resolved, numeric_suffixes):
                    numeric_skipped.add(resolved)
                    continue
                target = df_cols_lower.get(resolved.lower(), resolved)
                if exclude_numeric and _looks_numeric_metric(target, numeric_suffixes):
                    numeric_skipped.add(target)
                    continue
                if target in excluded or target in used_target_columns:
                    continue
                rename_map[col] = target
                used_target_columns.add(target)
            if not rename_map:
                continue
            resolved_cols = list(rename_map.values())
            diagnostics["matched_columns"].update(resolved_cols)
            merged_attribute_columns.update(resolved_cols)
            subset = rows.select([product_col] + list(rename_map.keys())).rename(
                rename_map
            )
            results.append(subset)

    if not results:
        return (df, diagnostics) if return_debug else df

    merged_attrs = pl.concat(results, how="diagonal")

    if merged_attrs.height > 0:
        value_counts_df = merged_attrs.group_by(product_col).agg(
            pl.len().alias("__count")
        )
        dup_products = (
            value_counts_df.filter(pl.col("__count") > 1)
            .get_column(product_col)
            .to_list()
        )
        if dup_products:
            diagnostics["duplicate_products"] = dup_products
            merged_attrs = merged_attrs.unique(subset=[product_col], keep="first")

    original_count = (
        df.select(pl.len()).collect().item()
        if isinstance(df, pl.LazyFrame)
        else df.height
    )

    ordered_attrs = sorted(merged_attribute_columns)
    merged_attrs = merged_attrs.select([product_col, *ordered_attrs])

    merged_df = merge_attribute_results(
        df,
        {"product_column": product_col},
        classification=merged_attrs,
        allow_numeric_attributes=not exclude_numeric,
    )

    joined_count = (
        merged_df.select(pl.len()).collect().item()
        if isinstance(merged_df, pl.LazyFrame)
        else merged_df.height
    )
    diagnostics["original_row_count"] = int(original_count)
    diagnostics["joined_row_count"] = int(joined_count)
    if joined_count != original_count:
        diagnostics["row_count_changed"] = True

    out = merged_df
    if return_debug:
        diagnostics["matched_columns"] = sorted(diagnostics["matched_columns"])
        diagnostics["merged_columns"] = ordered_attrs
        diagnostics["numeric_columns_skipped"] = sorted(numeric_skipped)
        diagnostics["duplicate_products"] = sorted(diagnostics["duplicate_products"])
        return out, diagnostics
    return out


def merge_or_classify_attributes_from_excel(
    df: pl.DataFrame | pl.LazyFrame,
    file: str | Path | bytes | BytesIO,
    category: str,
    *,
    line_col: str = "Line",
    classify_fn: callable | None = None,
    llm_wrapper=None,
) -> pl.DataFrame | pl.LazyFrame:
    """Merge Excel attributes or classify via an LLM when none provided."""

    attrs = _read_excel(file)
    allowed = _allowed_attributes(category)
    attr_cols = [c for c in get_schema_and_column_names(attrs)[0] if c in allowed]
    if attr_cols:
        return merge_attributes_from_excel(
            df, file, product_col=line_col, category_col="Category"
        )

    if classify_fn is None:
        from modules.add_attributes import classify_attributes_for_products

        classify_fn = classify_attributes_for_products

    products = attrs.get_column(line_col).to_list()
    attr_map = {"All products": list(allowed)}
    base_df = df.collect() if isinstance(df, pl.LazyFrame) else df
    classification = classify_fn(
        llm_wrapper,
        base_df,
        line_col,
        products,
        attr_map,
        group_col=None,
    )
    merged = merge_attribute_results(
        base_df if isinstance(base_df, pl.DataFrame) else base_df.collect(),
        {"product_column": line_col},
        classification=classification,
    )
    return merged.lazy() if isinstance(df, pl.LazyFrame) else merged
