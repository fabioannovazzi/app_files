from __future__ import annotations

import logging

import polars as pl
from modules.utilities.ui_notifier import ui
from polars.exceptions import ComputeError

try:  # pragma: no cover - optional dependency during testing
    from modules.utilities.utils import (
        ensure_lazyframe,
        get_schema_and_column_names,
    )
except Exception as e:  # pragma: no cover - provide fallbacks
    logging.exception(e)
    ui.error(f"polars_helpers import error: {e}")

    def get_schema_and_column_names(df: pl.DataFrame | pl.LazyFrame):
        # Fallback implementation without using DataFrame/LazyFrame `.columns`/`.schema`.
        # Handle LazyFrame via `collect_schema` when available; otherwise, derive
        # names and dtypes by iterating eager columns.
        if isinstance(df, pl.LazyFrame):
            try:
                schema_obj = df.collect_schema()
                schema = dict(schema_obj)
                cols = list(schema.keys())
                return cols, schema
            except Exception as e:
                logging.exception(e)
                return [], {}

        # Eager DataFrame path
        cols = [s.name for s in df.iter_columns()]
        try:
            schema = {s.name: s.dtype for s in df.iter_columns()}
        except Exception as e:
            logging.exception(e)
            schema = {}
        return cols, schema

    def ensure_lazyframe(obj: pl.DataFrame | pl.LazyFrame) -> pl.LazyFrame:
        return obj.lazy() if isinstance(obj, pl.DataFrame) else obj

    def ensure_lazyframe(obj: pl.DataFrame | pl.LazyFrame) -> pl.LazyFrame:
        return obj.lazy() if isinstance(obj, pl.DataFrame) else obj


__all__ = [
    "unique_values_lazy",
    "collect_tail",
    "get_unique_categories",
    "n_unique_lazy",
    "to_lists",
    "share_of_row",
    "extract_top_categories",
    "get_max_value",
    "get_min_value",
]


def unique_values_lazy(column: str, df: pl.DataFrame | pl.LazyFrame) -> list[str]:
    """Return unique values from ``column`` for both DataFrame and LazyFrame.

    The order of first appearance is preserved for both input types.
    """

    if isinstance(df, pl.LazyFrame):
        return (
            df.select(pl.col(column).unique(maintain_order=True))
            .collect(engine="streaming")
            .get_column(column)
            .to_list()
        )
    return df.get_column(column).unique(maintain_order=True).to_list()


def collect_tail(
    lf: pl.LazyFrame, n: int, *, engine: str = "streaming"
) -> pl.DataFrame:
    """Return the last ``n`` rows of ``lf`` collected as a ``DataFrame``.

    Parameters
    ----------
    lf:
        LazyFrame to sample from.
    n:
        Number of rows to return from the end of the frame.
    engine:
        Engine to use when collecting the data. Defaults to ``"streaming"``.
    """

    return lf.tail(n).collect(engine=engine)


def n_unique_lazy(column: str, lf: pl.LazyFrame | pl.DataFrame) -> int:
    """Return number of unique values in ``column`` of ``lf``."""

    if isinstance(lf, pl.DataFrame):
        return lf.get_column(column).n_unique()

    if hasattr(lf, "_already_collected_df"):
        return lf._already_collected_df.get_column(column).n_unique()

    lf = ensure_lazyframe(lf)
    try:
        return lf.select(pl.col(column).n_unique()).collect(engine="streaming").item()
    except ComputeError as e:
        logging.exception(e)
        ui.error(f"n_unique_lazy error: {e}")
        try:
            return lf.select(pl.col(column).n_unique()).collect().item()
        except ComputeError as e:
            logging.exception(e)
            ui.error(f"n_unique_lazy error: {e}")
            return lf.select(pl.col(column)).unique().select(pl.len()).collect().item()


def get_unique_categories(df: pl.DataFrame | pl.LazyFrame) -> list[str]:
    """Return unique values from the first column of ``df``."""

    columns, _ = get_schema_and_column_names(df)
    first_col = columns[0]
    lf = ensure_lazyframe(df)
    return (
        lf.select(pl.col(first_col).drop_nulls().unique(maintain_order=True))
        .collect(engine="streaming")
        .get_column(first_col)
        .to_list()
    )


def get_unique_categories_ok_nulls(df: pl.DataFrame | pl.LazyFrame) -> list[str]:
    """Return unique values from the first column of ``df``."""

    columns, _ = get_schema_and_column_names(df)
    first_col = columns[0]
    lf = ensure_lazyframe(df)
    return (
        lf.select(pl.col(first_col).unique(maintain_order=True))
        .collect(engine="streaming")
        .get_column(first_col)
        .to_list()
    )


def share_of_row(
    df: pl.DataFrame | pl.LazyFrame,
    value_col: str,
) -> pl.DataFrame | pl.LazyFrame:
    """Return frame with ``value_col`` as share of its column total."""

    return df.with_columns(
        (pl.col(value_col) / pl.col(value_col).sum()).alias(value_col)
    )


def extract_top_categories(
    df: pl.DataFrame | pl.LazyFrame,
    column: str,
    *,
    top_n: int = 5,
) -> list[str]:
    """Return the most frequent ``column`` values up to ``top_n`` entries.

    Always returns a list of categories.
    """

    lf = ensure_lazyframe(df)
    result = (
        lf.group_by(column)
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
        .head(top_n)
        .select(column)
        .collect(engine="streaming")
    )
    return result.get_column(column).to_list()


def get_max_value(lf: pl.DataFrame | pl.LazyFrame, col: str) -> float:
    """Return the maximum value of ``col`` from ``lf``.

    The function reuses previously collected data when available to avoid
    redundant streaming collections. It works with both
    :class:`~polars.DataFrame` and :class:`~polars.LazyFrame` inputs.
    """

    if isinstance(lf, pl.DataFrame):
        return lf.get_column(col).max()

    if hasattr(lf, "_already_collected_df"):
        return lf._already_collected_df.get_column(col).max()

    return (
        ensure_lazyframe(lf)
        .select(pl.col(col).max())
        .collect(engine="streaming")
        .item()
    )


def get_min_value(lf: pl.DataFrame | pl.LazyFrame, col: str) -> float:
    """Return the minimum value of ``col`` from ``lf``.

    Mirrors :func:`get_max_value` and avoids extra streaming collections when
    possible.
    """

    if isinstance(lf, pl.DataFrame):
        return lf.get_column(col).min()

    if hasattr(lf, "_already_collected_df"):
        return lf._already_collected_df.get_column(col).min()

    return (
        ensure_lazyframe(lf)
        .select(pl.col(col).min())
        .collect(engine="streaming")
        .item()
    )


def to_lists(lf: pl.LazyFrame | pl.DataFrame, cols: list[str]) -> dict[str, list]:
    """Collect ``cols`` from ``lf`` and return them as Python lists.

    The collected :class:`~polars.DataFrame` is cached on the ``LazyFrame`` via
    the ``_already_collected_df`` attribute so that subsequent helper calls can
    reuse it without triggering additional collects.
    """

    if isinstance(lf, pl.DataFrame):
        return {col: lf.get_column(col).to_list() for col in cols}

    collected = lf.select(pl.col(cols)).collect(engine="streaming")
    setattr(lf, "_already_collected_df", collected)
    return {col: collected.get_column(col).to_list() for col in cols}


def column_to_list(lf: pl.LazyFrame, col: str) -> list:
    """Collect ``col`` from ``lf`` and return it as a Python list."""

    return lf.select(pl.col(col)).collect(engine="streaming").get_column(col).to_list()