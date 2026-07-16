from __future__ import annotations

import datetime as dt

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.utilities.date_utils import parse_date_column


def test_parse_date_column_parses_common_formats_and_returns_lazyframe():
    # Arrange
    df = pl.DataFrame(
        {
            "date": [
                "2024-01-01",  # ISO
                "2024/01/02",  # slashes
                "03-01-2024",  # day-month-year
                "Jan 05 2024",  # month name
            ]
        }
    )

    # Act
    lf = parse_date_column(df, "date")
    out = lf.collect()

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    assert out.schema["date"] == pl.Date
    expected = pl.DataFrame(
        {
            "date": [
                dt.date(2024, 1, 1),
                dt.date(2024, 1, 2),
                dt.date(2024, 1, 3),
                dt.date(2024, 1, 5),
            ]
        }
    )
    assert_frame_equal(out, expected)


def test_parse_date_column_drops_invalid_and_placeholders_by_default():
    # Arrange
    df = pl.DataFrame(
        {
            "date": [
                "2024-01-01",
                "N/A",  # placeholder mapped to null
                "NaN",  # placeholder mapped to null
                "",  # placeholder mapped to null
                "not a date",  # unparsable -> null
                "2024/02/02",
            ]
        }
    )

    # Act
    out = parse_date_column(df, "date").collect()

    # Assert
    assert out.schema["date"] == pl.Date
    expected = pl.DataFrame({"date": [dt.date(2024, 1, 1), dt.date(2024, 2, 2)]})
    assert_frame_equal(out, expected)


def test_parse_date_column_keeps_nulls_when_drop_invalid_false():
    # Arrange
    df = pl.DataFrame(
        {
            "date": [
                "2024-01-01",
                "not a date",
                "",
                "2024/01/02",
            ]
        }
    )

    # Act
    out = parse_date_column(df, "date", drop_invalid=False).collect()

    # Assert
    assert out.schema["date"] == pl.Date
    expected = pl.DataFrame(
        {
            "date": [
                dt.date(2024, 1, 1),
                None,  # unparsable remains null
                None,  # placeholder becomes null
                dt.date(2024, 1, 2),
            ]
        }
    )
    assert_frame_equal(out, expected)


def test_parse_date_column_handles_null_dtypes():
    # Arrange: explicit null-typed column should not raise during parsing
    df = pl.DataFrame(
        schema={"date": pl.Null},
        data=[(None,), (None,)],
        orient="row",
    )

    # Act
    out = parse_date_column(df, "date", drop_invalid=False).collect()

    # Assert
    expected = pl.DataFrame(
        schema={"date": pl.Date},
        data=[(None,), (None,)],
        orient="row",
    )
    assert out.schema["date"] == pl.Date
    assert_frame_equal(out, expected)


def test_parse_date_column_missing_column_raises_on_collect():
    # Arrange
    df = pl.DataFrame({"other": ["2024-01-01"]})

    # Act / Assert
    from polars.exceptions import ColumnNotFoundError

    with pytest.raises(ColumnNotFoundError):
        parse_date_column(df, "date").collect()
