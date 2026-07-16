from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.finance.bank_statements.dedupe import dedupe_transactions
from src.finance.bank_statements.model import BankTransaction


def _tx(
    posted: date,
    desc: str,
    amount: str,
    *,
    value: date | None = None,
    conf: float = 1.0,
) -> BankTransaction:
    return BankTransaction(
        posted_date=posted,
        value_date=value,
        description=desc,
        amount=Decimal(amount),
        confidence=conf,
        currency=None,
    )


def test_dedupe_keeps_highest_confidence_for_similar_descriptions() -> None:
    # Arrange: same dates/amount; descriptions are substrings (treated as similar)
    d = date(2024, 7, 12)
    rows = [
        _tx(d, "ACME SHOP LONDON", "10.50", conf=0.6),
        _tx(d, "ACME SHOP", "10.50", conf=0.9),
    ]

    # Act
    result = dedupe_transactions(rows)

    # Assert: only one remains and it's the higher-confidence transaction
    assert len(result) == 1
    assert result[0].description == "ACME SHOP"
    assert result[0].confidence == 0.9


def test_dedupe_retains_both_when_descriptions_dissimilar() -> None:
    # Arrange: same key by date/amount but very different descriptions (not similar)
    d = date(2024, 7, 13)
    rows = [
        _tx(d, "GROCERY STORE", "25.00", conf=0.8),
        _tx(d, "UTILITY BILL", "25.00", conf=0.7),
    ]

    # Act
    result = dedupe_transactions(rows)

    # Assert: both are kept under distinct keys due to dissimilar descriptions
    assert len(result) == 2
    assert {t.description for t in result} == {"GROCERY STORE", "UTILITY BILL"}


def test_dedupe_prefers_longer_description_on_tie_confidence() -> None:
    # Arrange: equal confidence; similar descriptions -> prefer longer description
    d = date(2024, 7, 14)
    rows = [
        _tx(d, "Payment A", "10.00", conf=0.8),
        _tx(d, "Payment A longer", "10.00", conf=0.8),
    ]

    # Act
    result = dedupe_transactions(rows)

    # Assert
    assert len(result) == 1
    assert result[0].description == "Payment A longer"
