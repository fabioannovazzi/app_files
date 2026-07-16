from __future__ import annotations

from pathlib import Path
import sys

import pytest

# Ensure src/ is on sys.path for package imports during tests
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from journal_ingest.strategies.text_pdf import TextPDFParser


@pytest.mark.parametrize(
    "file_bytes",
    [b"", b"random-bytes", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"],  # typical PDF header
)
def test_probe_always_returns_zero_float(file_bytes: bytes) -> None:
    # Arrange
    parser = TextPDFParser()

    # Act
    score = parser.probe(file_bytes)

    # Assert
    assert isinstance(score, float)
    assert score == 0.0


def test_parse_returns_empty_list_when_no_helper() -> None:
    # Arrange
    parser = TextPDFParser()  # helper defaults to None

    # Act
    rows = list(parser.parse(b""))

    # Assert
    assert isinstance(rows, list)
    assert rows == []


def test_parse_ignores_helper_and_meta_and_is_empty() -> None:
    # Arrange
    parser = TextPDFParser(helper=object())
    meta = {"note": "ignored"}

    # Act
    rows = list(parser.parse(b"%PDF-1.4\n", meta=meta))

    # Assert
    assert rows == []
