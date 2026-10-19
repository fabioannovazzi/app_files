"""Measure supported local sources and exact read selections without LLM estimates."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shlex
from contextlib import contextmanager
from itertools import islice
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from archive_report_store import canonical, file_digest

__all__ = ["measure_source", "read_selection", "direct_read_selection", "model_texts"]


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


def model_texts(response: Any) -> list[str]:
    """Extract displayed strings once, avoiding duplicated MCP structured content."""
    if isinstance(response, str):
        return [response]
    if isinstance(response, list):
        return [text for item in response for text in model_texts(item)]
    if not isinstance(response, dict):
        return []
    if response.get("type") in {"image", "audio", "resource_link"}:
        return []
    if isinstance(response.get("content"), list):
        return model_texts(response["content"])
    for field in ("text", "stdout", "output", "content"):
        if isinstance(response.get(field), str):
            return [response[field]]
    return [canonical(response).decode()]


def direct_read_selection(
    source: dict[str, Any], tool_input: Any, response: Any
) -> dict[str, Any] | None:
    """Recognize exact whole-file and prefix reads by comparing returned bytes.

    Command recognition only resolves an explicit file operand. It never decides
    semantic relevance or treats a requested read as proof that data was returned.
    Other commands remain unmeasured rather than fabricating a row count.
    """
    path = Path(source["path"])
    if isinstance(tool_input, str):
        # Code-mode transcripts contain the outer JavaScript source. Require an
        # explicit file operand plus exact returned bytes, not command execution.
        if str(path) not in tool_input:
            return None
        tool_input = {"path": str(path)}
    if not isinstance(tool_input, dict):
        return None
    named = tool_input.get("file_path") or tool_input.get("path")
    command = tool_input.get("command") or tool_input.get("cmd")
    tokens: list[str] = []
    if isinstance(command, str):
        try:
            tokens = shlex.split(command)
        except ValueError:
            return None
    if str(path) != named and str(path) not in tokens:
        return None
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != source["sha256"]:
        return None
    try:
        original = content.decode("utf-8-sig")
    except UnicodeError:
        return None
    displayed = model_texts(response)
    if original and any(original.strip() == text.strip() for text in displayed):
        return {
            "source_id": source["source_id"],
            "source_sha256": source["sha256"],
            "unit": source["unit"],
            "start": 0,
            "stop": source["quantity"],
            "columns": list(range(source["columns"] or 1)),
            "basis": "exact_returned_file",
        }
    if path.suffix.lower() not in {".csv", ".tsv"}:
        return None
    if not tokens or Path(tokens[0]).name != "head":
        return None
    try:
        count = (
            10
            if tokens == [tokens[0], str(path)]
            else int(tokens[tokens.index("-n") + 1])
        )
    except (ValueError, IndexError):
        return None
    if count < 1:
        return None
    prefix = "".join(original.splitlines(keepends=True)[:count])
    if not prefix or not any(prefix.strip() == text.strip() for text in displayed):
        return None
    # Multiline CSV fields must close in the returned prefix before counting.
    try:
        dialect = csv.Sniffer().sniff(original[:65536], delimiters=",;\t|")
        rows = list(csv.reader(io.StringIO(prefix), dialect=dialect, strict=True))
    except csv.Error:
        return None
    if any(len(row) != source["columns"] for row in rows):
        return None
    return {
        "source_id": source["source_id"],
        "source_sha256": source["sha256"],
        "unit": source["unit"],
        "start": 0,
        "stop": max(0, len(rows) - 1),
        "columns": list(range(source["columns"] or 1)),
        "basis": "exact_returned_prefix",
    }
