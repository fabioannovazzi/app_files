from __future__ import annotations

from pathlib import Path
import sys

import polars as pl
import pytest

# Ensure src/ is on sys.path for package imports during tests
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from journal_ingest.core import ValidationError
from journal_ingest.strategies.table_area import (
    JournalStrategyTableArea,
    detect_table_columns,
    parse_table_dataframe,
)


def test_detect_table_columns_happy_path():
    # Arrange: minimal, well-formed journal-like table
    df = pl.DataFrame(
        {
            "line": [1, 2],
            "acct": ["100-200", "100-201"],
            "desc": ["Cash", "Receivables"],
            "debit": [100.0, 0.0],
            "credit": [0.0, 100.0],
            "memo": ["init", "adj"],
        }
    )

    # Act
    mapping = detect_table_columns(df)

    # Assert: detected columns map to expected roles
    assert mapping == {
        "line_no": "line",
        "account_code": "acct",
        "debit": "debit",
        "credit": "credit",
        "account_desc": "desc",
        "memo": "memo",
    }


def test_detect_table_columns_single_amount_and_no_line():
    # Arrange: no explicit line column; only one amount column present
    df = pl.DataFrame(
        {
            "account": ["400/10", "400/20"],
            "description": ["Sales", "Returns"],
            "amount": [50.0, 25.0],
        }
    )

    # Act
    mapping = detect_table_columns(df)

    # Assert: single amount becomes debit; credit stays None; line_no absent
    assert mapping["line_no"] is None
    assert mapping["account_code"] == "account"
    assert mapping["debit"] == "amount"
    assert mapping["credit"] is None
    assert mapping["account_desc"] == "description"
    assert mapping["memo"] is None


def test_parse_table_dataframe_balanced_rows_returns_parsed_records():
    # Arrange: two rows that balance to zero (required by validator)
    df = pl.DataFrame(
        {
            "line": [1, 2],
            "acct": ["100-200", "100-201"],
            "desc": ["Cash", "Receivables"],
            "debit": [100.0, 0.0],
            "credit": [0.0, 100.0],
            "memo": ["init", "adj"],
        }
    )

    # Act
    rows = parse_table_dataframe(df)

    # Assert: shape and key fields; numeric parsing and balance
    assert isinstance(rows, list) and len(rows) == 2
    assert {k for k in rows[0].keys()} == {
        "entry_date",
        "line_no",
        "account_code",
        "account_desc",
        "memo",
        "debit",
        "credit",
    }
    # Debit/Credit parsed as floats and balanced
    total_debit = sum(float(r["debit"] or 0.0) for r in rows)
    total_credit = sum(float(r["credit"] or 0.0) for r in rows)
    assert total_debit == pytest.approx(100.0)
    assert total_credit == pytest.approx(100.0)
    assert rows[0]["line_no"] == 1 and rows[1]["line_no"] == 2
    assert rows[0]["account_code"] == "100-200"


def test_parse_table_dataframe_raises_on_imbalance():
    # Arrange: only a debit column present; validator should fail
    df = pl.DataFrame(
        {
            "account": ["400/10"],
            "description": ["Sales"],
            "amount": [50.0],  # becomes debit; no credit column
        }
    )

    # Act / Assert
    with pytest.raises(ValidationError):
        parse_table_dataframe(df)


@pytest.mark.parametrize(
    "meta,expected",
    [
        (None, 0.0),  # no dataframe provided
        ({"df": pl.DataFrame({"desc": ["x"], "debit": [1.0]})}, 0.4),  # no account
        (
            {
                "frame": pl.DataFrame(
                    {
                        "line": [1],
                        "acct": ["100-200"],
                        "debit": [1.0],
                        "credit": [0.0],
                    }
                )
            },
            0.8,
        ),
    ],
)
def test_journal_strategy_table_area_probe(meta, expected):
    # Arrange
    strat = JournalStrategyTableArea()

    # Act
    score = strat.probe(b"", meta)

    # Assert
    assert score == expected
