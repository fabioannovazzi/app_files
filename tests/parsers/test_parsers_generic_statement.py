from __future__ import annotations

# Ensure 'src' is on sys.path so absolute imports like 'parsers.*' resolve
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import pdfplumber
import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from parsers.generic_statement import (
    GenericStatementParser,
    LLMRowRepair,
    StatementRow,
    extract_statement_rows,
)

# --- Test helpers ------------------------------------------------------------


@dataclass
class _StubPage:
    text: Optional[str] = None
    tables: Optional[List[List[List[str]]]] = None

    def extract_text(self) -> Optional[str]:
        return self.text

    def extract_tables(self):  # type: ignore[override]
        return self.tables or []


class _StubPDF:
    def __init__(self, pages: List[_StubPage]):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _patch_pdf_open(monkeypatch: pytest.MonkeyPatch, pages: List[_StubPage]) -> None:
    def _open_stub(_path: Path):
        return _StubPDF(pages)

    monkeypatch.setattr(pdfplumber, "open", _open_stub)


# --- Tests -------------------------------------------------------------------


def test_parse_raises_for_non_pdf_extension(tmp_path: Path):
    parser = GenericStatementParser()
    non_pdf = tmp_path / "statement.txt"
    non_pdf.write_text("dummy")
    with pytest.raises(ValueError, match="Only PDF files are supported"):
        parser.parse(str(non_pdf))


def test_parse_parses_text_pages_and_invokes_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Arrange: two pages with one line-based transaction each
    page1 = _StubPage(text="01/02/2024 100.50 To John Doe, invoice 123")
    page2 = _StubPage(text="03/02/2024 20.00 fees paid to SuperMart invoice 55")
    _patch_pdf_open(monkeypatch, [page1, page2])

    calls: list[tuple[float, int, tuple[Optional[date], Optional[date]]]] = []

    def progress_cb(progress: float, rows: int, drange):
        calls.append((progress, rows, drange))

    # Act
    parser = GenericStatementParser()
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%stub")
    rows = parser.parse(str(pdf_path), locale_hint="eng", progress_callback=progress_cb)

    # Assert: rows content
    assert len(rows) == 2
    r1, r2 = rows
    assert r1.booking_date == date(2024, 2, 1)
    assert r1.amount == Decimal("100.50") and r1.direction == "credit"
    assert r1.beneficiary == "john doe"  # extracted from "To John Doe"

    assert r2.booking_date == date(2024, 2, 3)
    assert r2.amount == Decimal("20.00") and r2.direction == "debit"

    # Assert: progress callback invoked per page with correct progress and date range
    assert [round(c[0], 2) for c in calls] == [0.5, 1.0]
    assert [c[1] for c in calls] == [1, 2]  # rows_so_far
    # date range evolves from first row to min/max across both pages
    assert calls[0][2] == (date(2024, 2, 1), date(2024, 2, 1))
    assert calls[1][2] == (date(2024, 2, 1), date(2024, 2, 3))


def test_parse_uses_table_when_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Arrange: single page with a simple table (header + one row)
    table = [
        ["Data", "Descrizione", "Importo"],
        ["02/02/2024", "Bonifico a favore di Example Client, CRO 999", "EUR 1.234,56"],
    ]
    page = _StubPage(text=None, tables=[table])
    _patch_pdf_open(monkeypatch, [page])

    parser = GenericStatementParser()
    pdf_path = tmp_path / "table.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%stub")

    # Act
    rows = parser.parse(str(pdf_path))

    # Assert: parsed via table path
    assert len(rows) == 1
    row = rows[0]
    assert row.booking_date == date(2024, 2, 2)
    assert row.amount == Decimal("1234.56") and row.direction == "credit"
    assert row.beneficiary == "example client"  # extracted from description
    assert row.reference_ids == ["999"]  # CRO ID extracted


def test_parse_handles_none_header_cells(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ensure tables with missing header cells are processed without errors."""
    table = [
        [None, "Data", "Descrizione", "Importo"],
        [None, "02/02/2024", "Bonifico a Example Client", "EUR 1.234,56"],
    ]
    page = _StubPage(text=None, tables=[table])
    _patch_pdf_open(monkeypatch, [page])

    parser = GenericStatementParser()
    pdf_path = tmp_path / "none_header.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%stub")

    rows = parser.parse(str(pdf_path))

    assert len(rows) == 1
    row = rows[0]
    assert row.booking_date == date(2024, 2, 2)
    assert row.amount == Decimal("1234.56") and row.direction == "credit"


def test_parse_skips_balance_and_closing_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    text = (
        "31/03/2024 8.009,90 SALDO INIZIALE\n"
        "01/04/2024 100,00 Bonifico da Example Client\n"
        "30/04/2024 8.109,90 SALDO FINALE\n"
        "30/04/2024 -50,00 CHIUSURA CONTABILE\n"
    )
    page = _StubPage(text=text)
    _patch_pdf_open(monkeypatch, [page])

    parser = GenericStatementParser()
    pdf_path = tmp_path / "balance.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%stub")

    rows = parser.parse(str(pdf_path))

    assert len(rows) == 1
    row = rows[0]
    assert row.booking_date == date(2024, 4, 1)
    assert row.amount == Decimal("100.00") and row.direction == "credit"


def test_parse_preserves_lines_with_saldo_or_chiusura_in_description(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    text = (
        "01/04/2024 100,00 Bonifico saldo fattura\n"
        "02/04/2024 -30,00 Pagamento chiusura carta\n"
    )
    page = _StubPage(text=text)
    _patch_pdf_open(monkeypatch, [page])

    parser = GenericStatementParser()
    pdf_path = tmp_path / "contains_words.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%stub")

    rows = parser.parse(str(pdf_path))

    assert len(rows) == 2
    r1, r2 = rows
    assert r1.booking_date == date(2024, 4, 1)
    assert r1.amount == Decimal("100.00")
    assert r2.booking_date == date(2024, 4, 2)
    assert r2.amount == Decimal("30.00")


def test_parse_skips_additional_non_transaction_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ensure narrative or internal bookkeeping rows are ignored."""

    text = (
        "01/04/2024 100,00 Bonifico da Example Client\n"
        "02/04/2024 0,00 SALDI PER VALUTA\n"
        "03/04/2024 -5,00 RILEVAZIONE COSTI\n"
        "04/04/2024 -10,00 RILEVAZIONI VARIE\n"
        "05/04/2024 -20,00 Pagamento supermercato\n"
        "06/04/2024 0,00 NUOVI ORARI FILIALE\n"
    )
    page = _StubPage(text=text)
    _patch_pdf_open(monkeypatch, [page])

    parser = GenericStatementParser()
    pdf_path = tmp_path / "non_txn.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%stub")

    rows = parser.parse(str(pdf_path))

    assert [r.booking_date for r in rows] == [date(2024, 4, 1), date(2024, 4, 5)]


def test_extract_statement_rows_wrapper_basic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Arrange: simple single-page, line-based transaction
    page = _StubPage(text="05/02/2024 10.00 To Alice")
    _patch_pdf_open(monkeypatch, [page])

    pdf_path = tmp_path / "wrapper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%stub")

    # Act
    rows = extract_statement_rows(str(pdf_path), locale="eng", deterministic_only=True)

    # Assert
    assert len(rows) == 1
    assert rows[0].booking_date == date(2024, 2, 5)
    assert rows[0].amount == Decimal("10.00") and rows[0].direction == "credit"


def test_llm_row_repair_uses_wrapper(monkeypatch: pytest.MonkeyPatch):
    row = StatementRow(
        booking_date=date(2024, 1, 1),
        value_date=None,
        amount=Decimal("0"),
        direction="debit",
        currency=None,
        description="",
        counterparty=None,
        beneficiary=None,
        method=None,
        raw_lines=["raw"],
    )

    def _fake_llm(wrapper, step, system_prompt, user_prompt, tools=None):
        assert wrapper == "stub-wrapper"
        assert step == "generic-statement-row"
        assert tools is None
        return {
            "booking_date": "2024-02-01",
            "amount": 5,
            "direction": "credit",
            "currency": "USD",
        }

    repairer = LLMRowRepair(deterministic_only=False, llm_wrapper="stub-wrapper")
    monkeypatch.setattr(repairer, "_llm", _fake_llm)
    repaired = repairer.repair(row)

    assert repaired.booking_date == date(2024, 2, 1)
    assert repaired.amount == Decimal("5")
    assert repaired.direction == "credit"
    assert repaired.currency == "USD"
