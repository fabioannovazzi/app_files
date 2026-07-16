"""Hierarchy resolution utilities using polars."""

from __future__ import annotations

from typing import Sequence

import polars as pl

from modules.utilities.utils import ensure_lazyframe

__all__ = ["resolve_hierarchies"]


def _choose_parent(
    lf: pl.LazyFrame, child_col: str, parent_col: str, weight_col: str | None
) -> pl.LazyFrame:
    """Return mapping of each child to its most likely parent."""
    weight_expr = (
        pl.col(weight_col).sum().alias("_weight")
        if weight_col
        else pl.lit(0).alias("_weight")
    )
    agg = lf.group_by([child_col, parent_col]).agg(
        pl.len().alias("_count"),
        weight_expr,
    )
    sorted_lf = agg.sort(
        [child_col, "_count", "_weight", parent_col],
        descending=[False, True, True, False],
    )
    best = sorted_lf.group_by(child_col).first()
    return best.select(child_col, parent_col)


def _apply_mapping(
    lf: pl.LazyFrame, child_col: str, parent_col: str, mapping: pl.LazyFrame
) -> pl.LazyFrame:
    """Overwrite ``parent_col`` with the chosen parent for each child lazily."""
    return (
        lf.join(mapping, on=child_col, how="left", suffix="_new")
        .with_columns(
            pl.col(f"{parent_col}_new").fill_null(pl.col(parent_col)).alias(parent_col)
        )
        .drop(f"{parent_col}_new")
    )


def _assert_unique(lf: pl.LazyFrame, child_col: str, parent_col: str) -> None:
    """Raise ``ValueError`` if a child maps to multiple parents."""
    conflicts = (
        lf.group_by(child_col)
        .agg(pl.col(parent_col).n_unique().alias("n"))
        .filter(pl.col("n") > 1)
        .collect()
    )
    if conflicts.select(pl.len()).item() > 0:
        raise ValueError(f"Non-unique mapping detected for {parent_col}")


def resolve_hierarchies(
    df: pl.DataFrame | pl.LazyFrame,
    child_col: str,
    parent_cols: Sequence[str],
    *,
    weight_col: str | None = None,
) -> pl.LazyFrame:
    """Ensure a single parent per ``child_col`` for each hierarchy column.

    Accepts both :class:`polars.DataFrame` and :class:`polars.LazyFrame`. Any
    lazy input is collected before processing.
    """

    result = ensure_lazyframe(df)
    for parent in parent_cols:
        mapping = _choose_parent(result, child_col, parent, weight_col)
        result = _apply_mapping(result, child_col, parent, mapping)
        _assert_unique(result, child_col, parent)
    return result
