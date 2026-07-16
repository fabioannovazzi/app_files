from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
from modules.process_excel.logic import (
    _as_dict,
    _merge_header_rows,
    _suggest_header_row,
    _unique_column_names,
    explode,
)
from modules.process_pdf_journal.logic import parse_journal_any


def test_parse_journal_any_returns_polars_dataframe():
    pdf_path = Path(__file__).resolve().parents[3] / "tmp_test.pdf"
    df = parse_journal_any(pdf_path.read_bytes(), header_row=0)
    assert isinstance(df, pl.DataFrame)
    assert df.height >= 0 and df.width >= 0


def test_merge_header_rows_prefers_second_row_values():
    # Arrange
    row_one = ["Account", "", "Date"]
    row_two = ["", "Amount", ""]

    # Act
    merged = _merge_header_rows(row_one, row_two)

    # Assert
    assert merged == ["Account", "Amount", "Date"]


def test_unique_column_names_fills_blanks_and_handles_duplicates():
    # Arrange
    columns = ["amount", "amount", "", "None", "date"]

    # Act
    unique = _unique_column_names(columns)

    # Assert
    assert unique == ["amount", "amount_2", "column_2", "column_3", "date"]


def test_suggest_header_row_picks_row_with_most_labels():
    # Arrange
    data = pl.DataFrame(
        [
            ["", "", ""],
            ["Date", "Account", "Amount"],
            ["1/1/24", "Cash", "10.00"],
        ]
    )

    # Act
    idx = _suggest_header_row(data)

    # Assert
    assert idx == 1


def test_explode_posting_signed_builds_expected_shape():
    # Arrange
    df = pl.DataFrame(
        {
            "date": ["01/01/24", "02/01/24"],
            "account": ["Cash", "Fees"],
            "amount": ["10,00", "-2,50"],
        }
    )
    mapping = {"date": "date", "account": "account", "amount": "amount"}

    # Act
    exploded = explode(df, mapping, "posting_signed")

    # Assert
    assert exploded.columns == ["date", "account", "debit", "credit"]
    assert exploded.get_column("date").to_list() == [
        date(2024, 1, 1),
        date(2024, 1, 2),
    ]
    assert exploded.get_column("account").to_list() == ["Cash", "Fees"]
    assert exploded.schema["debit"] == pl.Float64
    assert exploded.schema["credit"] == pl.Float64


def test_as_dict_returns_mapping_from_sequence():
    # Arrange
    payload = [{"key": "value"}]

    # Act
    result = _as_dict(payload)

    # Assert
    assert result == {"key": "value"}
