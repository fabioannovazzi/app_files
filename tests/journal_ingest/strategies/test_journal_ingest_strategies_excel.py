from __future__ import annotations

from pathlib import Path
import sys
import pytest

# Ensure src/ is on sys.path for package imports during tests
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from journal_ingest.strategies.excel import JournalStrategyExcel


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def test_probe_high_confidence_when_account_and_debit_detected():
    # Arrange: CSV with detectable line, account code, debit/credit columns
    csv = (
        "line,account,desc,debit,credit,memo\n"
        "1,100/200,Assets,10.00,0.00,Opening\n"
        "2,100/200,Assets,0.00,10.00,Reversal\n"
    )
    strategy = JournalStrategyExcel()

    # Act
    score = strategy.probe(_csv_bytes(csv))

    # Assert
    assert score == 0.8


def test_probe_low_confidence_when_missing_account_column():
    # Arrange: Only one numeric column; no account-like column present
    csv = (
        "line,desc,amount\n"
        "1,Note,10\n"
        "2,Note,5\n"
    )
    strategy = JournalStrategyExcel()

    # Act
    score = strategy.probe(_csv_bytes(csv))

    # Assert
    assert score == 0.4


def test_probe_returns_zero_on_read_error(monkeypatch):
    # Arrange: Force _read_dataframe to raise, exercising error handling
    strategy = JournalStrategyExcel()

    def boom(*args, **kwargs):  # noqa: ARG001
        raise ValueError("cannot read")

    monkeypatch.setattr(JournalStrategyExcel, "_read_dataframe", boom)

    # Act
    score = strategy.probe(b"irrelevant")

    # Assert
    assert score == 0.0


def test_parse_returns_canonical_rows_balanced_totals():
    # Arrange: Two rows that balance to satisfy validation
    csv = (
        "line,account,desc,debit,credit,memo\n"
        "1,100/200,Assets,10.00,0.00,Opening\n"
        "2,100/200,Assets,0.00,10.00,Reversal\n"
    )
    strategy = JournalStrategyExcel()

    # Act
    rows = list(strategy.parse(_csv_bytes(csv)))

    # Assert: shape and key fields
    assert isinstance(rows, list)
    assert len(rows) == 2
    assert rows[0] == {
        "entry_date": None,
        "line_no": 1,
        "account_code": "100/200",
        "account_desc": "Assets",
        "memo": "Opening",
        "debit": 10.0,
        "credit": 0.0,
    }
    assert rows[1] == {
        "entry_date": None,
        "line_no": 2,
        "account_code": "100/200",
        "account_desc": "Assets",
        "memo": "Reversal",
        "debit": 0.0,
        "credit": 10.0,
    }
