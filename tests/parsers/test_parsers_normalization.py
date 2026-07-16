
import logging
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

# Ensure 'src' is on sys.path so absolute imports like 'parsers.*' resolve
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from parsers.normalization import (
    extract_dates,
    parse_amount,
    parse_amount_any,
    parse_date_token,
)


# parse_amount
@pytest.mark.parametrize(
    "token, expected",
    [
        ("€ 1.234,56", Decimal("1234.56")),
        ("$1,234.56", Decimal("1234.56")),
        ("1234,56", Decimal("1234.56")),  # no thousands separator
    ],
)
def test_parse_amount_supported_formats(token: str, expected: Decimal) -> None:
    # Act
    result = parse_amount(token)

    # Assert
    assert isinstance(result, Decimal)
    assert result == expected


def test_parse_amount_strips_nbsp_and_currency() -> None:
    # Arrange
    token = "EUR\u00a01.234,56"

    # Act
    result = parse_amount(token)

    # Assert
    assert result == Decimal("1234.56")


def test_parse_amount_raises_on_currency_only() -> None:
    # Arrange
    token = "EUR"

    # Act / Assert
    with pytest.raises(InvalidOperation):
        parse_amount(token)


# parse_amount_any
@pytest.mark.parametrize(
    "text, expected",
    [
        ("Total: € 1.234,56 due", Decimal("1234.56")),
        ("Pay $12.34 now", Decimal("12.34")),  # simple US format
        ("foo 1234,56 bar", Decimal("1234.56")),
    ],
)
def test_parse_amount_any_finds_first_amount(text: str, expected: Decimal) -> None:
    # Act
    result = parse_amount_any(text)

    # Assert
    assert isinstance(result, Decimal)
    assert result == expected


def test_parse_amount_any_long_unpunctuated_integer_returns_none() -> None:
    # Arrange
    text = "Ref 12345678 ok"  # 8 digits, no separators

    # Act
    result = parse_amount_any(text)

    # Assert
    assert result is None


def test_parse_amount_any_accepts_up_to_seven_digits_unpunctuated() -> None:
    # Arrange
    text = "Ref 1234567 ok"  # 7 digits

    # Act
    result = parse_amount_any(text)

    # Assert
    assert result == Decimal("1234567")


def test_parse_amount_any_no_number_returns_none() -> None:
    # Act
    result = parse_amount_any("No amount here")

    # Assert
    assert result is None


# parse_date_token
def test_parse_date_token_iso() -> None:
    # Act
    dt = parse_date_token("2023-08-15")

    # Assert
    assert dt == date(2023, 8, 15)


@pytest.mark.parametrize(
    "token, expected",
    [
        ("15/08/2023", date(2023, 8, 15)),
        ("15.08.2023", date(2023, 8, 15)),
        ("15-08-2023", date(2023, 8, 15)),
    ],
)
def test_parse_date_token_dmy_variants(token: str, expected: date) -> None:
    # Act
    dt = parse_date_token(token)

    # Assert
    assert dt == expected


@pytest.mark.parametrize(
    "token, expected",
    [
        ("31/12/69", date(2069, 12, 31)),  # <70 maps to 2000-2069
        ("31-12-69", date(2069, 12, 31)),
        ("01/01/70", date(1970, 1, 1)),  # >=70 maps to 1900s
        ("01.01.70", date(1970, 1, 1)),
        ("02/01/00", date(2000, 1, 2)),
        ("02.01.00", date(2000, 1, 2)),
    ],
)
def test_parse_date_token_two_digit_year_rules(token: str, expected: date) -> None:
    # Act
    dt = parse_date_token(token)

    # Assert
    assert dt == expected


def test_parse_date_token_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_date_token("32/13/2023")


def test_extract_dates_invalid_token_logs_debug_not_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Arrange
    tokens = ["32/13/2023"]

    # Act
    with caplog.at_level(logging.DEBUG):
        result = extract_dates(tokens)

    # Assert
    assert result == []
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno < logging.ERROR

