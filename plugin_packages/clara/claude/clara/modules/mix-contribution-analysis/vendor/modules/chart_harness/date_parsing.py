"""Shared date parsing for monthly and full-date chart inputs."""

from __future__ import annotations

import polars as pl

__all__ = ["parse_date_expression"]


def parse_date_expression(column: str) -> pl.Expr:
    """Represent year-month labels by the first day before date inference.

    Polars cannot infer a date format from a column containing only YYYY-MM.
    Normalizing that documented monthly grain also keeps eager fallback
    expressions from raising even when another parse branch succeeds.
    """
    expression = pl.col(column)
    text = expression.cast(pl.Utf8)
    normalized = (
        pl.when(text.str.contains(r"^\d{4}[-/]\d{2}$"))
        .then(text.str.replace_all("/", "-") + pl.lit("-01"))
        .otherwise(text)
    )
    return expression.cast(pl.Date, strict=False).fill_null(
        normalized.str.strptime(pl.Date, strict=False).fill_null(
            normalized.str.strptime(pl.Datetime, strict=False).cast(pl.Date)
        )
    )
