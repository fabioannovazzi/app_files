from __future__ import annotations

from typing import Any, Iterable, Mapping

from journal_ingest.core import BaseJournalParser


class OcrParser(BaseJournalParser):
    """Placeholder parser for OCR-based extraction."""

    def probe(self, file_bytes: bytes, meta: Mapping[str, Any] | None = None) -> float:
        return 0.0

    def parse(
        self, file_bytes: bytes, meta: Mapping[str, Any] | None = None
    ) -> Iterable[dict[str, Any]]:
        return []
