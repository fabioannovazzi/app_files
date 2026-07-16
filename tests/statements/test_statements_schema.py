import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

import pytest

# Ensure 'src' is on sys.path so 'statements' resolves from the real package
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from statements.schema import (
    Transaction,
    normalise_transaction,
    normalise_whitespace,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  foo   bar  ", "foo bar"),
        ("foo\tbar", "foo bar"),
        ("\nfoo  \n bar\tbaz  ", "foo bar baz"),
        ("", ""),
        ("    ", ""),
        ("already normalised", "already normalised"),
    ],
)
def test_normalise_whitespace_various(raw: str, expected: str) -> None:
    # Act
    result = normalise_whitespace(raw)

    # Assert
    assert result == expected


def test_normalise_transaction_normalises_all_text_fields() -> None:
    # Arrange
    tx = Transaction(
        booking_date=date(2024, 1, 2),
        value_date=None,
        description="  Payment   to\tABC\nLtd  ",
        amount=Decimal("-12.34"),
        currency="EUR",
        balance_after=None,
        reference="  INV   123  ",
        counterparty="  ABC   LTD ",
        reference_ids=["  REF1 ", "\t REF2  "],
        beneficiary="  John   Doe  ",
    )

    # Act
    result = normalise_transaction(tx)

    # Assert: textual fields normalised, non-text fields preserved
    assert isinstance(result, Transaction)
    assert result.description == "Payment to ABC Ltd"
    assert result.reference == "INV 123"
    assert result.counterparty == "ABC LTD"
    assert result.beneficiary == "John Doe"
    assert result.reference_ids == ["REF1", "REF2"]
    assert result.amount == Decimal("-12.34")
    assert result.currency == "EUR"


def test_normalise_transaction_preserves_none_and_empty_values() -> None:
    # Arrange: None and empty strings/lists should remain safe
    tx = Transaction(
        booking_date=date(2024, 2, 3),
        value_date=None,
        description="   ",  # collapses to empty string
        amount=Decimal("0"),
        currency="USD",
        balance_after=None,
        reference=None,  # stays None (guarded by truthiness check)
        counterparty=None,  # stays None
        reference_ids=[],  # stays empty list
        beneficiary=None,  # stays None
    )

    # Act
    result = normalise_transaction(tx)

    # Assert
    assert result.description == ""
    assert result.reference is None
    assert result.counterparty is None
    assert result.reference_ids == []
    assert result.beneficiary is None
