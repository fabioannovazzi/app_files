from __future__ import annotations

import polars as pl

from src.identify_columns_logic import cogs_col_found, indirect_costs_col_found
from src.identify_columns_logic import show_input_data as core_show_input_data

__all__ = [
    "cogs_col_found",
    "indirect_costs_col_found",
    "show_input_data",
]


def show_input_data(
    df: pl.LazyFrame, param_dict: dict
) -> tuple[pl.LazyFrame, dict, list[tuple[str, str, str | None]]]:
    """Return detected column messages without rendering UI."""

    return core_show_input_data(df, param_dict)
