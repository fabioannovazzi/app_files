from __future__ import annotations

import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

import polars as pl
import pytest

# Ensure 'src' is on sys.path so 'statements' resolves from the real package
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from statements.ingest import Document
from statements.schema import Transaction
from statements.strategies import (
    strategy_table_layout,
    strategy_line_heuristics,
    strategy_llm_blocks,
)


def _make_document_with_table(df: pl.DataFrame, kind: str = "csv") -> Document:
    return Document(path=Path("dummy.ext"), kind=kind, tables=[df])


def test_strategy_table_layout_parses_valid_rows_and_skips_invalid() -> None:
    # Arrange: one valid and one invalid row (bad date)
    df = pl.DataFrame(
        {
            "Booking Date": ["2023-08-10", "not a date"],
            "Description": ["Groceries", "Bad"],
            "Amount": ["123.45", "999.99"],
            "Currency": ["EUR", "EUR"],
        }
    )
    doc = _make_document_with_table(df, kind="csv")

    # Act
    out = strategy_table_layout(doc, locale="en")

    # Assert
    assert isinstance(out, list) and len(out) == 1
    tx = out[0]
    assert isinstance(tx, Transaction)
    assert tx.booking_date == date(2023, 8, 10)
    assert tx.description == "Groceries"
    assert tx.amount == Decimal("123.45")
    assert tx.currency == "EUR"
    assert tx.raw_source == "csv"


def test_strategy_table_layout_missing_optional_fields_defaults_blank() -> None:
    # Arrange: no description/currency columns present
    df = pl.DataFrame({"Booking Date": ["31/12/2023"], "Amount": ["1,234.50"]})
    doc = _make_document_with_table(df, kind="xlsx")

    # Act
    out = strategy_table_layout(doc, locale="en")

    # Assert
    assert len(out) == 1
    tx = out[0]
    assert tx.booking_date == date(2023, 12, 31)
    assert tx.amount == Decimal("1234.50")
    assert tx.description == ""
    assert tx.currency == ""
    assert tx.raw_source == "xlsx"


def test_strategy_table_layout_no_tables_returns_empty() -> None:
    # Arrange
    doc = Document(path=Path("no.pdf"), kind="pdf", tables=[])

    # Act / Assert
    assert strategy_table_layout(doc, locale="en") == []


def test_strategy_line_heuristics_parses_lines_and_updates_diagnostics() -> None:
    # Arrange: two pages; include a summary-like row that should be dropped
    page1 = "\n".join(
        [
            "01/02/2023 Grocery Store 12.34",
            "Summary total 500",  # dropped by filter_rows
        ]
    )
    page2 = "\n".join(
        [
            "05/02/2023 Payment 200.00",
            "32/13/2023 Wrong 100.00",  # invalid date -> skipped during parsing
        ]
    )
    metadata = {"page_diagnostics": [{}, {}]}
    doc = Document(path=Path("x.pdf"), kind="pdf", pages=[page1, page2], metadata=metadata)

    # Act
    out = strategy_line_heuristics(doc, locale="en")

    # Assert transactions
    assert len(out) == 2
    assert [t.booking_date for t in out] == [date(2023, 2, 1), date(2023, 2, 5)]
    assert [t.description for t in out] == ["Grocery Store", "Payment"]
    assert [t.raw_page for t in out] == [1, 2]
    assert all(t.currency == "" and t.raw_source == "pdf" for t in out)

    # Assert diagnostics updated with kept/dropped counts
    diag = doc.metadata["page_diagnostics"]
    assert diag[0]["kept_rows"] == 1 and diag[0]["dropped_rows"] == 1
    # Second page keeps both rows at filter stage; parsing drops the invalid one later
    assert diag[1]["kept_rows"] == 2 and diag[1]["dropped_rows"] == 0


def test_strategy_llm_blocks_uses_llm_and_aggregates_pages(monkeypatch) -> None:
    # Arrange: stub the LLM extractor to return one transaction per call
    calls: list[tuple[str, str]] = []

    def _stub_extract(text: str, locale: str) -> list[Transaction]:  # noqa: ANN001
        calls.append((text, locale))
        return [
            Transaction(
                booking_date=date(2023, 1, 1),
                value_date=None,
                description=f"tx from {text}",
                amount=Decimal("1.00"),
                currency="EUR",
            )
        ]

    import statements.llm as llm_mod

    monkeypatch.setattr(llm_mod, "extract_transactions_llm", _stub_extract)

    doc = Document(path=Path("y.pdf"), kind="pdf", pages=["A", "B"])

    # Act
    out = strategy_llm_blocks(doc, locale="en")

    # Assert
    assert len(out) == 2
    assert [t.description for t in out] == ["tx from A", "tx from B"]
    assert calls == [("A", "en"), ("B", "en")]


def test_strategy_llm_blocks_returns_empty_when_llm_returns_nothing() -> None:
    # Arrange: default implementation returns [] when API key missing
    doc = Document(path=Path("z.pdf"), kind="pdf", pages=["some text"])

    # Act / Assert
    assert strategy_llm_blocks(doc, locale="en") == []
