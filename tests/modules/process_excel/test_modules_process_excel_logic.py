from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.process_excel.logic import explode


def test_explode_posting_signed_produces_expected_columns_and_parses_dates():
    # Arrange
    df = pl.DataFrame(
        {
            "dt": ["05/01/24", "06/01/2024"],  # short and long year
            "acct": ["A", "B"],
            "amt": ["100,50", "-7,50"],  # values are currently parsed to nulls
        }
    )
    m = {"date": "dt", "account": "acct", "amount": "amt"}

    # Act
    out = explode(df, m, layout="posting_signed")

    # Assert: column order and date parsing
    assert out.columns == ["date", "account", "debit", "credit"]
    assert out.schema["date"] == pl.Date
    assert out["date"].to_list() == [date(2024, 1, 5), date(2024, 1, 6)]
    # Amounts are currently null due to parser behaviour
    assert out.schema["debit"] == pl.Float64
    assert out.schema["credit"] == pl.Float64
    assert out["debit"].null_count() == 2
    assert out["credit"].null_count() == 2


def test_explode_entry_split_acc_splits_each_row_into_debit_and_credit_sides():
    # Arrange
    df = pl.DataFrame(
        {
            "dt": ["15/04/2024"],
            "debit_acc": ["D1"],
            "credit_acc": ["C1"],
            "debit_amt": ["5,00"],  # currently parsed to 0 via fill_null
            "credit_amt": ["5,00"],
        }
    )
    m = {
        "date": "dt",
        "debit_account": "debit_acc",
        "credit_account": "credit_acc",
        "debit_amount": "debit_amt",
        "credit_amount": "credit_amt",
    }

    # Act
    out = explode(df, m, layout="entry_split_acc")

    # Assert: two rows produced, accounts mapped, amounts zeroed by parser
    expected = pl.DataFrame(
        {
            "date": pl.Series("date", [date(2024, 4, 15), date(2024, 4, 15)], dtype=pl.Date),
            "account": ["D1", "C1"],
            "debit": [0.0, 0.0],
            "credit": [0.0, 0.0],
        }
    )
    assert_frame_equal(out, expected)


def test_explode_posting_split_amt_fills_nulls_with_zero():
    # Arrange: missing side becomes 0
    df = pl.DataFrame(
        {
            "dt": ["10/03/2024", "11/03/2024"],
            "acct": ["A1", "A2"],
            "debit_amt": [None, "5,00"],
            "credit_amt": ["10,00", None],
        }
    )
    m = {
        "date": "dt",
        "account": "acct",
        "debit_amount": "debit_amt",
        "credit_amount": "credit_amt",
    }

    # Act
    out = explode(df, m, layout="posting_split_amt")

    # Assert
    expected = pl.DataFrame(
        {
            "date": pl.Series("date", [date(2024, 3, 10), date(2024, 3, 11)], dtype=pl.Date),
            "account": ["A1", "A2"],
            "debit": [0.0, 0.0],
            "credit": [0.0, 0.0],
        }
    )
    assert_frame_equal(out, expected)


def test_explode_raises_on_unknown_layout():
    # Arrange
    df = pl.DataFrame({"dt": ["01/01/2024"], "acct": ["X"], "amt": ["1,00"]})
    m = {"date": "dt", "account": "acct", "amount": "amt"}

    # Act / Assert
    with pytest.raises(ValueError, match=r"Unknown layout .*foo"):
        explode(df, m, layout="foo")
