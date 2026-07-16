from __future__ import annotations

"""Retailer scoping helpers for PDP attribute mapping runs."""

from typing import Sequence

import polars as pl

__all__ = [
    "filter_frame_by_retailers",
    "normalize_retailer_scope",
    "replace_retailer_scope_rows",
]


def normalize_retailer_scope(
    retailers: Sequence[str] | str | None,
) -> tuple[str, ...]:
    """Return normalized retailer names for scoped mapping runs."""

    if retailers is None:
        return ()
    raw_values = [retailers] if isinstance(retailers, str) else list(retailers)
    normalized: list[str] = []
    for value in raw_values:
        text = str(value or "").strip().lower()
        if text and text not in normalized:
            normalized.append(text)
    return tuple(normalized)


def filter_frame_by_retailers(
    df: pl.DataFrame,
    retailer_scope: Sequence[str],
) -> pl.DataFrame:
    """Return rows whose retailer is in ``retailer_scope``."""

    if df.is_empty() or not retailer_scope or "retailer" not in df.columns:
        return df
    return df.filter(
        pl.col("retailer")
        .cast(pl.Utf8, strict=False)
        .str.strip_chars()
        .str.to_lowercase()
        .is_in(list(retailer_scope))
    )


def replace_retailer_scope_rows(
    full_df: pl.DataFrame,
    scoped_df: pl.DataFrame,
    retailer_scope: Sequence[str],
) -> pl.DataFrame:
    """Merge processed scoped rows back into an otherwise full cache frame."""

    if not retailer_scope or full_df.is_empty() or "retailer" not in full_df.columns:
        return scoped_df
    if scoped_df.is_empty():
        return full_df
    scoped_retailer = (
        pl.col("retailer")
        .cast(pl.Utf8, strict=False)
        .str.strip_chars()
        .str.to_lowercase()
        .is_in(list(retailer_scope))
    )
    non_scoped_df = full_df.filter(~scoped_retailer)
    if non_scoped_df.is_empty():
        return scoped_df
    return pl.concat([non_scoped_df, scoped_df], how="diagonal_relaxed")
