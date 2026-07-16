from __future__ import annotations

from io import BytesIO, StringIO
from typing import Any, Mapping

import polars as pl

from modules.utilities.utils import (
    get_schema_and_column_names as _get_schema_and_column_names,
)
from modules.utils.polars_excel_writer import write_polars_excel

__all__ = [
    "convert_df_csv",
    "convert_df_parquet",
    "convert_df_excel",
    "convert_book_excel",
    "collect_streaming",
    "get_schema_and_column_names",
]


def collect_streaming(df: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
    """Return a materialized DataFrame using Polars streaming."""
    return df if isinstance(df, pl.DataFrame) else df.collect(engine="streaming")


def convert_df_csv(df: pl.DataFrame | pl.LazyFrame) -> bytes:
    """Return CSV bytes for ``df``.

    Any invalid UTF-8 sequences in string or binary columns are
    replaced to avoid ``OSError`` when writing.
    """
    buffer = StringIO()
    collected = collect_streaming(df)
    cols, schema = get_schema_and_column_names(collected)
    assert schema is not None  # nosec B101
    str_cols: list[pl.Expr] = []
    for name, dtype in schema.items():
        if dtype == pl.Binary:
            str_cols.append(
                pl.col(name).map_elements(
                    lambda b: b.decode("utf-8", "replace"), return_dtype=pl.Utf8
                )
            )
        elif dtype == pl.Utf8:
            str_cols.append(pl.col(name).cast(pl.Utf8, strict=False))
    collected.with_columns(str_cols).write_csv(buffer)
    return buffer.getvalue().encode("utf-8")


def convert_df_parquet(df: pl.DataFrame | pl.LazyFrame) -> bytes:
    """Return Parquet bytes for ``df``."""
    buffer = BytesIO()
    collect_streaming(df).write_parquet(buffer)
    return buffer.getvalue()


def convert_df_excel(df: pl.DataFrame | pl.LazyFrame) -> bytes:
    """Return Excel bytes for ``df``."""
    buffer = BytesIO()
    write_polars_excel(collect_streaming(df), buffer)
    return buffer.getvalue()


def convert_book_excel(book: Mapping[str, pl.DataFrame]) -> bytes:
    """Return an Excel workbook with multiple sheets.

    ``book`` maps sheet names to Polars DataFrames. DataFrames are collected
    if they are LazyFrames. Sheet order follows the mapping's iteration order.
    """
    materialized: dict[str, pl.DataFrame] = {}
    for name, df in book.items():
        materialized[name] = collect_streaming(df)
    buffer = BytesIO()
    write_polars_excel(materialized, buffer)
    return buffer.getvalue()


def get_schema_and_column_names(
    df: pl.DataFrame | pl.LazyFrame | Any,
) -> tuple[list[str], dict[str, pl.DataType] | None]:
    """Return column names and schema for ``df``."""

    return _get_schema_and_column_names(df)
