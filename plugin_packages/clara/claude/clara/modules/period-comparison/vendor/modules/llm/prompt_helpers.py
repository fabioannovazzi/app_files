"""Prompt helper stubs for the headless period-comparison chart runtime."""

from __future__ import annotations

from typing import Any

import polars as pl

__all__ = ["clean_df_for_prompt"]


def clean_df_for_prompt(
    dfCopy: pl.DataFrame | pl.LazyFrame, _chartDict: dict[str, Any]
) -> pl.DataFrame:
    """Return a bounded eager frame without importing the app LLM stack."""

    if isinstance(dfCopy, pl.LazyFrame):
        return dfCopy.head(30000).collect()
    return dfCopy.head(30000)
