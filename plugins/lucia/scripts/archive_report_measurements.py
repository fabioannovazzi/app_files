"""Measure supported local sources and exact read selections without LLM estimates."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from contextlib import contextmanager
from itertools import islice
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from archive_report_store import canonical, file_digest

__all__ = ["measure_source", "read_selection", "direct_read_selection"]


@contextmanager
def _table(path: Path):
    """Stream physical source units; a small inspection never loads a whole table."""
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(65536)
            handle.seek(0)
            dialect = csv.excel_tab if suffix == ".tsv" else csv.excel
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                pass
            reader = csv.reader(handle, dialect=dialect, strict=True)
            header = next(reader, [])
            yield header, reader, "rows"
        return
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            width = max((sheet.max_column or 0 for sheet in workbook), default=0)

            def rows():
                for sheet in workbook:
                    for row in sheet.iter_rows(values_only=True):
                        if any(value is not None for value in row):
                            yield [_scalar(value) for value in row] + [None] * (
                                width - len(row)
                            )

            yield [str(i) for i in range(width)], rows(), "worksheet_rows"
        finally:
            workbook.close()
        return
    if suffix == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import DependencyError, PdfReadError

        try:
            with path.open("rb") as handle:
                reader = PdfReader(handle)

                def text_pages():
                    for page in reader.pages:
                        text = page.extract_text()
                        if not text or not text.strip():
                            raise ValueError(
                                "PDF page has no measurable extracted text"
                            )
                        yield [text]

                yield ["text"], text_pages(), "text_pages"
        except (PdfReadError, DependencyError) as exc:
            raise ValueError("PDF text could not be measured") from exc
        return
    if suffix in {".xml", ".json"}:
        with path.open(encoding="utf-8-sig") as handle:
            yield ["document"], ([handle.read()],), "documents"
        return
    if suffix in {".txt", ".md", ".jsonl"}:
        with path.open(encoding="utf-8-sig") as handle:
            yield ["text"], ([line.rstrip("\r\n")] for line in handle), "lines"
        return
    raise ValueError("No source measurement adapter for this format")


def _file_hash(path: Path) -> str:
    return file_digest(path)


def _scalar(value: Any) -> Any:
    if value is None or type(value) in {str, int, bool, float}:
        return value
    return str(value)


def measure_source(
    path: Path, *, source_id: str, role: str = "input"
) -> dict[str, Any]:
    """Count physical data units; never infer accounting or legal row relevance."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("Reporting source must be an ordinary file")
    file_hash = _file_hash(path)
    byte_count = path.stat().st_size
    result = {
        "source_id": source_id,
        "path": str(path.resolve()),
        "role": role,
        "sha256": file_hash,
        "bytes": byte_count,
        "unit": "files",
        "quantity": 1,
        "columns": None,
        "cells": None,
        "measurement_error": None,
    }
    try:
        with _table(path) as (header, rows, unit):
            quantity = 0
            cells = 0
            for row in rows:
                if len(row) != len(header):
                    raise ValueError("Source has inconsistent physical row widths")
                quantity += 1
                cells += len(row)
        if _file_hash(path) != file_hash:
            raise ValueError("Source changed during measurement")
    except (
        ValueError,
        UnicodeError,
        csv.Error,
        ImportError,
        OSError,
        BadZipFile,
        ParseError,
    ) as exc:
        result["measurement_error"] = type(exc).__name__
        return result
    result.update(unit=unit, quantity=quantity, columns=len(header), cells=cells)
    return result


def read_selection(
    source: dict[str, Any],
    *,
    offset: int = 0,
    limit: int | None = None,
    columns: list[int] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return actual selected data with exact source coordinates for the observer."""
    path = Path(source["path"])
    if source["measurement_error"]:
        raise ValueError("This source has no complete measurement adapter")
    if path.is_symlink() or _file_hash(path) != source["sha256"]:
        raise ValueError("Read source no longer matches its Archive measurement")
    if (
        type(offset) is not int
        or offset < 0
        or (limit is not None and (type(limit) is not int or limit < 0))
    ):
        raise ValueError("Read offset and limit must be non-negative integers")
    start = min(offset, source["quantity"])
    stop = (
        source["quantity"] if limit is None else min(source["quantity"], start + limit)
    )
    with _table(path) as (header, rows, unit):
        selected_columns = list(range(len(header))) if columns is None else columns
        if not selected_columns:
            raise ValueError("Read must select at least one source column")
        if any(
            type(index) is not int or not 0 <= index < len(header)
            for index in selected_columns
        ) or len(set(selected_columns)) != len(selected_columns):
            raise ValueError("Read columns must be distinct source column indices")
        selected_rows = []
        size = 0
        for row in islice(rows, start, stop):
            if len(row) != len(header):
                raise ValueError("Source row width changed")
            selected = [row[index] for index in selected_columns]
            size += len(canonical(selected))
            if size > 6_000_000:
                raise ValueError(
                    "Selected data exceeds the host output limit; select fewer units or columns"
                )
            selected_rows.append(selected)
    data = {
        "columns": [header[index] for index in selected_columns],
        "rows": selected_rows,
    }
    evidence = {
        "source_id": source["source_id"],
        "source_sha256": source["sha256"],
        "unit": unit,
        "start": start,
        "stop": start + len(selected_rows),
        "columns": selected_columns,
        "data_sha256": hashlib.sha256(canonical(data)).hexdigest(),
    }
    return data, evidence


def direct_read_selection(
    source: dict[str, Any], request: Any, response: Any
) -> dict[str, Any] | None:
    """Match a Vera payload against the complete bytes of an immutable source.

    Source selection depends on exact content equality, never host commands,
    transcript syntax or a model's statement that it read something.
    """
    path = Path(source["path"])
    if isinstance(response, str):
        if len(response.encode("utf-8")) not in {source["bytes"], source["bytes"] - 3}:
            return None
    elif path.suffix.lower() != ".json":
        return None
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != source["sha256"]:
        return None
    try:
        original = content.decode("utf-8-sig")
    except UnicodeError:
        return None
    matched = isinstance(response, str) and response == original
    if path.suffix.lower() == ".json":
        try:
            matched = matched or json.loads(original) == response
        except ValueError:
            return None
    if not matched:
        return None
    return {
        "source_id": source["source_id"],
        "source_sha256": source["sha256"],
        "unit": source["unit"],
        "start": 0,
        "stop": source["quantity"],
        "columns": list(range(source["columns"] or 1)),
        "basis": "exact_vera_payload",
    }
