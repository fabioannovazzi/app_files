from __future__ import annotations

from typing import Any, MutableMapping

import polars as pl

from modules.layout.memoization import check_collect
from modules.utilities.session_context import SessionContext

__all__ = ["parse_date_column"]


def parse_date_column(
    df: pl.DataFrame | pl.LazyFrame,
    date_col: str,
    session_context: SessionContext | MutableMapping[str, Any] | None = None,
    drop_invalid: bool = True,
) -> pl.LazyFrame:
    """Return ``df`` with ``date_col`` parsed into ``pl.Date`` as a lazy frame.

    Parameters
    ----------
    df:
        Input dataset.
    date_col:
        Name of the date column.
    session_context:
        Optional session state mapping or :class:`SessionContext` for
        :func:`check_collect`.
    drop_invalid:
        When ``True``, rows that cannot be parsed are removed. Otherwise they are
        replaced with ``null``.

    Returns
    -------
    pl.LazyFrame
        LazyFrame with the parsed date column.

    Examples
    --------
    Eager DataFrame::

        >>> df = pl.DataFrame({"date": ["2024-01-01", "2024-01-02"]})
        >>> parse_date_column(df, "date")
        shape: (2, 1)
        ┌────────────┐
        │ date       │
        │ ---        │
        │ date       │
        ╞════════════╡
        │ 2024-01-01 │
        │ 2024-01-02 │
        └────────────┘

    LazyFrame::

        >>> lf = df.lazy()
        >>> res = parse_date_column(lf, "date")
        >>> res.collect().dtypes
        {'date': pl.Date}
    """

    original_is_lazy = isinstance(df, pl.LazyFrame)
    lf = df if original_is_lazy else df.lazy()

    schema = lf.collect_schema()
    if schema.get(date_col) == pl.Null:
        lf = lf.with_columns(pl.lit(None, dtype=pl.Date).alias(date_col))
        if drop_invalid:
            lf = lf.filter(pl.col(date_col).is_not_null())
        return lf

    date_str = pl.col(date_col).cast(pl.Utf8, strict=False)
    lf = lf.with_columns(
        pl.when(date_str.is_in(["N/A", "NaN", ""]))
        .then(None)
        .otherwise(date_str)
        .alias(date_col)
    )

    unique_dates = (
        lf.select(pl.col(date_col).drop_nulls().unique())
        .collect()
        .get_column(date_col)
        .to_list()
    )
    check_collect("NAA", "unique_dates", unique_dates, session_context=session_context)

    parsed_base = pl.col(date_col).cast(pl.Utf8, strict=False)
    parse_expr = (
        parsed_base
        .str.to_datetime(strict=False)
        .dt.date()
        .fill_null(parsed_base.str.strptime(pl.Date, "%Y-%m-%d", strict=False))
        .fill_null(parsed_base.str.strptime(pl.Date, "%Y/%m/%d", strict=False))
        .fill_null(parsed_base.str.strptime(pl.Date, "%d-%m-%Y", strict=False))
        .fill_null(parsed_base.str.strptime(pl.Date, "%b %d %Y", strict=False))
    )

    lf = lf.with_columns(parse_expr.alias(date_col))
    if drop_invalid:
        lf = lf.filter(pl.col(date_col).is_not_null())

    return lf
