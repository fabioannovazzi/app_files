"""Headless plan-dataset stubs used by vendored variance code."""

from __future__ import annotations

from typing import Any

import polars as pl

__all__ = ["modify_dataframe_for_Plan", "prepare_plan_dataset"]


def prepare_plan_dataset(*_args: Any, **_kwargs: Any) -> None:
    """No-op replacement for the legacy UI plan dataset side effect."""

    return None


def modify_dataframe_for_Plan(
    dfCopy: pl.DataFrame | pl.LazyFrame, _chartDict: dict[str, Any]
) -> pl.DataFrame | pl.LazyFrame:
    """Return ``dfCopy`` unchanged in the headless period-comparison runtime."""

    return dfCopy
