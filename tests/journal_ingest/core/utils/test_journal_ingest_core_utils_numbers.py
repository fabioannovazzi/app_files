import sys
from pathlib import Path

import pytest

# Ensure the 'src' package root is importable for journal_ingest
ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from journal_ingest.core.utils.numbers import infer_number, normalize_number


@pytest.mark.parametrize(
    "value,decimal,thousands,expected",
    [
        ("1,234.56", ".", ",", 1234.56),  # US style
        ("1.234,56", ",", ".", 1234.56),  # EU style
        ("-1,234.56", ".", ",", -1234.56),  # negative number
    ],
)
def test_normalize_number_locales_and_sign(value: str, decimal: str, thousands: str, expected: float) -> None:
    # Act
    result = normalize_number(value, decimal=decimal, thousands=thousands)

    # Assert
    assert result == pytest.approx(expected)


def test_normalize_number_invalid_value_raises() -> None:
    # Act / Assert
    with pytest.raises(ValueError):
        normalize_number("not_a_number")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1,234.56", 1234.56),  # unambiguous with candidates order below
        ("1234", 1234.0),  # no separators
    ],
)
def test_infer_number_from_candidates(value: str, expected: float) -> None:
    # Arrange
    decimal_candidates = [".", ","]
    thousands_candidates = [",", ".", ""]

    # Act
    result = infer_number(value, decimal_candidates, thousands_candidates)

    # Assert
    assert result == pytest.approx(expected)


def test_infer_number_raises_when_unparseable() -> None:
    # Arrange
    value = "1x2"
    decimal_candidates = [".", ","]
    thousands_candidates = [",", ".", ""]

    # Act / Assert
    with pytest.raises(ValueError) as exc:
        infer_number(value, decimal_candidates, thousands_candidates)
    assert str(exc.value) == f"Unable to parse number: {value}"


@pytest.mark.parametrize(
    "decimal_candidates,thousands_candidates,expected",
    [
        ([".", ","], [",", ".", ""], 1.23456),  # first viable combo wins
        ([",", "."], [".", ",", ""], 1234.56),  # order flipped -> correct EU parse
    ],
)
def test_infer_number_respects_candidate_order(
    decimal_candidates, thousands_candidates, expected
) -> None:
    # Arrange
    value = "1.234,56"

    # Act
    result = infer_number(value, decimal_candidates, thousands_candidates)

    # Assert
    assert result == pytest.approx(expected)
