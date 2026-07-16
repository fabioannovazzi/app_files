import sys
import types
from datetime import datetime

import pytest

from modules.pdf_utils import bank_agent
from modules.pdf_utils.bank_agent import extract_bank_pdf


class _DummyPage:
    def __init__(self, tables):
        self._tables = tables

    def extract_tables(self):
        return self._tables


class _DummyPDF:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_extract_bank_pdf_table_with_importo_trailing_minus(monkeypatch):
    # Arrange: table with headers including Importo and a trailing minus amount
    header = ["Data", "Descrizione", "Importo"]
    row = ["01/02/2024", "Bonifico", "1.234,56-"]
    tables = [[header, row]]  # one table with header+row
    pages = [_DummyPage(tables)]

    monkeypatch.setattr(bank_agent.pdfplumber, "open", lambda _io: _DummyPDF(pages))

    # Act
    txs = extract_bank_pdf(b"%PDF-1.4 dummy")

    # Assert
    assert len(txs) == 1
    tx = txs[0]
    assert isinstance(tx.date, datetime)
    assert tx.date == datetime(2024, 2, 1)
    assert tx.description == "Bonifico"
    assert tx.amount == pytest.approx(-1234.56, rel=1e-9)


def test_extract_bank_pdf_table_with_debit_credit_columns(monkeypatch):
    # Arrange: no Importo column; separate Uscite/Entrate determine sign
    header = ["Data", "Descrizione", "Uscite", "Entrate"]
    row1 = ["02/02/2024", "Pagamento supermercato", "2,00", ""]
    row2 = ["03/02/2024", "Stipendio", "", "3,50"]
    tables = [[header, row1, row2]]
    pages = [_DummyPage(tables)]

    monkeypatch.setattr(bank_agent.pdfplumber, "open", lambda _io: _DummyPDF(pages))

    # Act
    txs = extract_bank_pdf(b"%PDF-1.4 dummy")

    # Assert: amounts carry expected signs and order is preserved
    assert [t.date for t in txs] == [datetime(2024, 2, 2), datetime(2024, 2, 3)]
    assert [t.description for t in txs] == ["Pagamento supermercato", "Stipendio"]
    assert [t.amount for t in txs] == pytest.approx([-2.0, 3.5], rel=1e-9)


def test_extract_bank_pdf_table_with_none_header(monkeypatch):
    """Ensure `extract_bank_pdf` tolerates `None` values in the header row."""
    header = [None, "Data", "Descrizione", "Importo"]
    row = ["", "01/02/2024", "Bonifico", "10,00"]
    tables = [[header, row]]
    pages = [_DummyPage(tables)]

    monkeypatch.setattr(bank_agent.pdfplumber, "open", lambda _io: _DummyPDF(pages))

    txs = extract_bank_pdf(b"%PDF-1.4 dummy")

    assert len(txs) == 1
    tx = txs[0]
    assert tx.date == datetime(2024, 2, 1)
    assert tx.description == "Bonifico"
    assert tx.amount == pytest.approx(10.0, rel=1e-9)


def test_extract_bank_pdf_table_invalid_date_skips_row(monkeypatch):
    # Arrange: date not matching dd/mm/yyyy -> row is skipped
    header = ["Data", "Descrizione", "Importo"]
    bad_row = ["2024-02-01", "Invalid date format", "10,00"]
    tables = [[header, bad_row]]
    pages = [_DummyPage(tables)]

    monkeypatch.setattr(bank_agent.pdfplumber, "open", lambda _io: _DummyPDF(pages))
    # Ensure heuristics (fitz) import does not try to open a real PDF
    stub_fitz = types.SimpleNamespace()

    class _StubPage:
        def get_text(self):
            return "no relevant lines"

    class _StubDoc:
        def __iter__(self):
            return iter([_StubPage()])

    stub_fitz.open = lambda *a, **k: _StubDoc()
    monkeypatch.setitem(sys.modules, "fitz", stub_fitz)
    # Avoid pdf2image calling external binaries in OCR fallback
    monkeypatch.setattr(bank_agent, "convert_from_bytes", lambda *_a, **_k: [])

    # Act
    txs = extract_bank_pdf(b"%PDF-1.4 dummy")

    # Assert: no transactions parsed
    assert txs == []
