from __future__ import annotations

import io
from pathlib import Path
import sys

import pytest

# Ensure src/ is on sys.path for package imports during tests
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from journal_ingest.strategies.csv_excel import CsvExcelParser


def test_probe_returns_zero_float() -> None:
    # Arrange
    parser = CsvExcelParser()

    # Act
    score = parser.probe(b"anything")

    # Assert
    assert isinstance(score, float)
    assert score == 0.0


def test_parse_csv_basic_returns_dicts() -> None:
    # Arrange
    parser = CsvExcelParser()
    csv_bytes = b"a,b\n1,2\n3,4\n"

    # Act
    rows = list(parser.parse(csv_bytes))

    # Assert
    assert rows == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]


def test_parse_csv_header_only_returns_empty_list() -> None:
    # Arrange
    parser = CsvExcelParser()
    csv_bytes = b"a,b\n"

    # Act
    rows = list(parser.parse(csv_bytes))

    # Assert
    assert rows == []


def test_parse_excel_basic_returns_dicts() -> None:
    # Arrange
    parser = CsvExcelParser()
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "a"
    ws["B1"] = "b"
    ws["A2"] = 1
    ws["B2"] = 2
    buf = io.BytesIO()
    wb.save(buf)
    excel_bytes = buf.getvalue()

    # Act
    rows = list(parser.parse(excel_bytes, meta={"format": "excel"}))

    # Assert
    assert rows == [{"a": 1, "b": 2}]


def test_parse_excel_with_invalid_bytes_raises() -> None:
    # Arrange
    parser = CsvExcelParser()
    bad_bytes = b"not an excel file"

    # Act / Assert
    with pytest.raises(Exception):
        list(parser.parse(bad_bytes, meta={"format": "excel"}))
