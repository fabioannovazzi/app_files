from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.finance.bank_statements.bank_statement_strategies import (
    LayoutAwareTextStrategy,
    StatementParsingStrategy,
)


class _FakePage:
    def __init__(self, text: str, text_layout: str | None = None, page_number: int = 1):
        self._text = text
        self._text_layout = text_layout if text_layout is not None else text
        self.page_number = page_number

    # Accept both no-arg and layout=True calls
    def extract_text(self, *_, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("layout"):
            return self._text_layout
        return self._text


class _FakeDoc:
    def __init__(self, pages):
        self.pages = pages


def test_statement_parsing_strategy_docstrings_present() -> None:
    # Assert: protocol methods define helpful, non-empty docstrings (contract clarity)
    assert StatementParsingStrategy.can_handle.__doc__
    assert "confidence" in StatementParsingStrategy.can_handle.__doc__
    assert StatementParsingStrategy.parse.__doc__
    assert "transactions" in StatementParsingStrategy.parse.__doc__


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Date Debit Credit Description", 0.9),  # header pattern present
        ("Some random first-page text", 0.6),  # non-empty but no header
        ("", 0.0),  # empty first page
    ],
)
def test_layoutaware_can_handle_scoring(text: str, expected: float) -> None:
    doc = _FakeDoc([_FakePage(text)])
    score = LayoutAwareTextStrategy().can_handle(doc)  # type: ignore[arg-type]
    # Assert: returns a float and matches the expected heuristic branch
    assert isinstance(score, float)
    assert score == pytest.approx(expected, rel=0, abs=1e-9)


def test_layoutaware_parse_debit_credit_line_produces_transaction() -> None:
    # Arrange: a single page with one row starting with a date and two numbers
    # Format: posted_date value_date debit credit description
    layout_text = "15/01/2023 16/01/2023 10,00 0,00 Grocery store"
    page = _FakePage(text="Date Debit Credit Description", text_layout=layout_text, page_number=3)
    doc = _FakeDoc([page])

    # Act
    txs = LayoutAwareTextStrategy().parse(doc)  # type: ignore[arg-type]

    # Assert: one transaction with parsed dates, signed amount, and metadata
    assert len(txs) == 1
    tx = txs[0]
    assert tx.posted_date == date(2023, 1, 15)
    assert tx.value_date == date(2023, 1, 16)
    assert tx.description == "Grocery store"
    assert isinstance(tx.amount, Decimal) and tx.amount == Decimal("-10.00")
    assert tx.source_page == 3
    assert isinstance(tx.raw, dict) and "row" in tx.raw
