from __future__ import annotations

import polars as pl

__all__ = ["build_upset_matrix"]


def build_upset_matrix(lf: pl.LazyFrame, sets: list[str]) -> pl.LazyFrame:
    """Return a LazyFrame with boolean membership columns for each set."""

    exprs = [(pl.col("set") == s).any().alias(s) for s in sets]
    return lf.group_by("Name").agg(exprs).sort("Name")
