from __future__ import annotations

import io
from typing import Any, Iterable, Mapping

import polars as pl

from journal_ingest.core import BaseJournalParser


class CsvExcelParser(BaseJournalParser):
    """Parse CSV or Excel files using Polars."""

    def probe(self, file_bytes: bytes, meta: Mapping[str, Any] | None = None) -> float:
        return 0.0

    def parse(
        self, file_bytes: bytes, meta: Mapping[str, Any] | None = None
    ) -> Iterable[dict[str, Any]]:
        buffer = io.BytesIO(file_bytes)
        if meta and meta.get("format") == "excel":
            df = pl.read_excel(buffer)  # type: ignore[arg-type]
        else:
            df = pl.read_csv(buffer)
        return df.to_dicts()
