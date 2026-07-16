from __future__ import annotations

from pathlib import Path
import sys

import pytest

# Ensure src/ is on sys.path for package imports during tests
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from journal_ingest.strategies.table_pdf import TablePDFParser


@pytest.mark.parametrize("file_bytes", [b"", b"random-bytes", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"])  # typical header
def test_probe_always_returns_zero_float(file_bytes: bytes) -> None:
    # Arrange
    parser = TablePDFParser()

    # Act
    score = parser.probe(file_bytes)

    # Assert
    assert isinstance(score, float)
    assert score == 0.0


def test_parse_returns_empty_list_for_empty_bytes() -> None:
    # Arrange
    parser = TablePDFParser()

    # Act
    rows = list(parser.parse(b""))

    # Assert
    assert isinstance(rows, list)
    assert rows == []


def test_parse_ignores_meta_and_is_empty() -> None:
    # Arrange
    parser = TablePDFParser()
    meta = {"any": "thing", "page": 1}

    # Act
    rows = list(parser.parse(b"%PDF-1.4\n", meta=meta))

    # Assert
    assert rows == []
