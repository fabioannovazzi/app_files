"""Utilities for loading bank statement documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pdfplumber
import polars as pl


@dataclass
class Document:
    """In-memory representation of an input document."""

    path: Path
    kind: str
    pages: List[str] = field(default_factory=list)
    tables: List[pl.DataFrame] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class DocumentIngestor:
    """Load various statement formats into :class:`Document` objects."""

    def ingest(self, file_path: str) -> Document:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix in {".csv"}:
            return self._load_csv(path)
        if suffix in {".xlsx", ".xls"}:
            return self._load_xlsx(path)
        if suffix == ".pdf":
            return self._load_pdf(path)
        raise ValueError(f"Unsupported file type: {suffix}")

    def _load_csv(self, path: Path) -> Document:
        df = pl.read_csv(path)
        return Document(path=path, kind="csv", tables=[df])

    def _load_xlsx(self, path: Path) -> Document:
        df = pl.read_excel(path)
        return Document(path=path, kind="xlsx", tables=[df])

    def _load_pdf(self, path: Path) -> Document:
        pages: List[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
        return Document(path=path, kind="pdf", pages=pages)
