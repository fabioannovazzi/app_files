from __future__ import annotations

from pathlib import Path
import sys

# Ensure src/ is on sys.path for package imports during tests
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from journal_ingest.strategies.ocr import OcrParser


def test_probe_returns_zero_float() -> None:
    # Arrange
    parser = OcrParser()

    # Act
    score = parser.probe(b"some bytes")

    # Assert
    assert isinstance(score, float)
    assert score == 0.0


def test_parse_returns_empty_list_for_empty_bytes() -> None:
    # Arrange
    parser = OcrParser()

    # Act
    rows = list(parser.parse(b""))

    # Assert
    assert isinstance(rows, list)
    assert rows == []


def test_parse_ignores_meta_and_is_empty() -> None:
    # Arrange
    parser = OcrParser()

    # Act
    rows = list(parser.parse(b"irrelevant", meta={"unexpected": "value"}))

    # Assert
    assert rows == []
