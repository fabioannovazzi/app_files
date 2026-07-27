from __future__ import annotations

import json
from datetime import date, datetime
from typing import IO, Any, Mapping

import polars as pl
from polars.exceptions import PolarsError
from xlsxwriter import Workbook
from xlsxwriter.exceptions import XlsxWriterException

from modules.utilities.utils import get_schema_and_column_names


def _to_plain_python(value: Any) -> Any:
    """Recursively convert Polars objects to plain Python types."""
    if isinstance(value, pl.Series):
        return [_to_plain_python(v) for v in value.to_list()]
    if isinstance(value, dict):
        if {"mismatch_type", "explanation"}.issubset(value):
            return {
                "type": value.get("mismatch_type"),
                "message": value.get("explanation"),
                "severity": value.get("severity"),
            }
        return {k: _to_plain_python(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_python(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _prepare_df_for_excel(df: pl.DataFrame) -> pl.DataFrame:
    """Return a copy of ``df`` safe for Excel export."""

    def _to_excel(value: Any) -> str | Any:
        plain = _to_plain_python(value)
        if isinstance(plain, (list, dict)):
            return json.dumps(plain, ensure_ascii=False)
        return plain

    df = df.drop("line_numbers", strict=False)

    # Use centralised helper to retrieve schema/columns
    _, schema = get_schema_and_column_names(df)
    problematic = [
        name
        for name, dtype in schema.items()
        if dtype in (pl.Object, pl.Struct, pl.Date, pl.Datetime)
        or isinstance(dtype, pl.List)
    ]
    if problematic:
        df = df.with_columns(
            pl.col(col).map_elements(_to_excel, return_dtype=pl.Utf8)
            for col in problematic
        )
    return df


def write_polars_excel(
    data: pl.DataFrame | Mapping[str, pl.DataFrame],
    buffer: IO[bytes],
) -> None:
    """Write ``data`` to an Excel ``buffer``."""
    try:
        if isinstance(data, pl.DataFrame):
            _prepare_df_for_excel(data).write_excel(buffer)
        else:
            workbook = Workbook(buffer, {"in_memory": True})
            try:
                for sheet_name, df in data.items():
                    _prepare_df_for_excel(df).write_excel(
                        workbook, worksheet=sheet_name
                    )
            finally:
                workbook.close()
        return
    except (PolarsError, XlsxWriterException, NotImplementedError) as exc:
        raise RuntimeError("Polars Excel export failed") from exc
