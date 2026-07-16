import datetime as dt

import pytest

from src.date_helpers import start_of_month, start_of_quarter


def test_start_of_quarter_mid_quarter_preserves_time_and_tz():
    # Arrange
    d = dt.datetime(2024, 5, 15, 13, 45, 30, tzinfo=dt.timezone.utc)

    # Act
    result = start_of_quarter(d)

    # Assert
    assert result == dt.datetime(2024, 4, 1, 13, 45, 30, tzinfo=dt.timezone.utc)
    assert isinstance(result, dt.datetime)
    assert result.tzinfo is d.tzinfo


@pytest.mark.parametrize(
    "given, expected",
    [
        (dt.datetime(2023, 3, 31, 23, 59, 59), dt.datetime(2023, 1, 1, 23, 59, 59)),
        (dt.datetime(2023, 4, 1, 0, 0, 0), dt.datetime(2023, 4, 1, 0, 0, 0)),
    ],
)
def test_start_of_quarter_boundary_cases(given: dt.datetime, expected: dt.datetime):
    # Act
    result = start_of_quarter(given)

    # Assert
    assert result == expected


def test_start_of_quarter_invalid_type_raises_attribute_error():
    with pytest.raises(AttributeError):
        _ = start_of_quarter("2024-01-01")  # type: ignore[arg-type]


def test_start_of_month_preserves_time_and_microseconds():
    # Arrange
    d = dt.datetime(2023, 2, 14, 7, 8, 9, 123456)

    # Act
    result = start_of_month(d)

    # Assert
    assert result == dt.datetime(2023, 2, 1, 7, 8, 9, 123456)
    assert isinstance(result, dt.datetime)


def test_start_of_month_boundary_end_of_month():
    # Act
    result = start_of_month(dt.datetime(2023, 1, 31, 18, 0, 0))

    # Assert
    assert result == dt.datetime(2023, 1, 1, 18, 0, 0)


def test_start_of_month_invalid_type_raises_attribute_error():
    with pytest.raises(AttributeError):
        _ = start_of_month(123)  # type: ignore[arg-type]
