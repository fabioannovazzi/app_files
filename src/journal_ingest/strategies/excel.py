from __future__ import annotations

import io
import logging
from typing import Any, Iterable, Mapping

import polars as pl

from journal_ingest.core import BaseJournalParser

from .table_area import _is_filled, detect_table_columns, parse_table_dataframe


class JournalStrategyExcel(BaseJournalParser):
    """Parse CSV or Excel files by inferring column roles."""

    def _read_dataframe(
        self, file_bytes: bytes, meta: Mapping[str, Any] | None
    ) -> pl.DataFrame:
        buffer = io.BytesIO(file_bytes)
        fmt = (meta or {}).get("format")
        if fmt == "excel" or file_bytes[:2] == b"PK":
            return pl.read_excel(buffer)  # type: ignore[arg-type]
        return pl.read_csv(buffer)

    def probe(self, file_bytes: bytes, meta: Mapping[str, Any] | None = None) -> float:
        try:
            df = self._read_dataframe(file_bytes, meta)
        except Exception as e:
            logging.exception(e)
            return 0.0
        mapping = detect_table_columns(df)
        if _is_filled(mapping.get("account_code")) and _is_filled(mapping.get("debit")):
            return 0.8
        return 0.4

    def parse(
        self, file_bytes: bytes, meta: Mapping[str, Any] | None = None
    ) -> Iterable[dict[str, Any]]:
        df = self._read_dataframe(file_bytes, meta)
        return parse_table_dataframe(df)
