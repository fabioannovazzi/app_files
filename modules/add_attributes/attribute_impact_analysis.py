from __future__ import annotations

import polars as pl
from modules.utilities.utils import get_schema_and_column_names

__all__ = ["merge_scores_with_metrics"]


def merge_scores_with_metrics(
    scores_df: pl.DataFrame,
    metrics_df: pl.DataFrame,
    *,
    on: str = "Product",
) -> pl.DataFrame:
    """Return ``scores_df`` joined with ``metrics_df`` and standard metrics names."""
    df = scores_df.join(metrics_df, on=on, how="inner")
    rename_map = {}
    cols, _ = get_schema_and_column_names(df)
    if "total_amount" in cols:
        rename_map["total_amount"] = "Sales"
    if "total_units" in cols:
        rename_map["total_units"] = "Units"
    if "average_price" in cols:
        rename_map["average_price"] = "Price"
    return df.rename(rename_map) if rename_map else df
