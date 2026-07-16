from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from reportlab.pdfgen import canvas

# Import the parser from the src layout
from src.finance.bank_statements.agentic_parser import (
    AgenticStatementParser,
    ParserConfig,
)
from src.finance.bank_statements.model import BankTransaction, ParseReport


def _make_minimal_pdf(path: Path) -> None:
    """Create a one-page PDF file for pdfplumber to open."""
    with path.open("wb") as fh:
        c = canvas.Canvas(fh)
        # Draw at least one string so a page is present
        c.drawString(10, 10, "test page")
        c.save()


def test_parse_raises_on_non_pdf(tmp_path: Path) -> None:
    # Arrange
    p = tmp_path / "not_a_pdf.txt"
    p.write_text("hello")
    parser = AgenticStatementParser()

    # Act / Assert
    with pytest.raises(ValueError, match="Only PDF files are supported"):
        parser.parse(p)


def test_parse_builds_report_and_dedupes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Arrange: minimal PDF and a stub strategy returning duplicate-like rows
    pdf_path = tmp_path / "sample.pdf"
    _make_minimal_pdf(pdf_path)

    kept = BankTransaction(
        posted_date=date(2024, 7, 12),
        value_date=None,
        description="Payment A longer",
        amount=Decimal("10.50"),
        source_page=1,
        confidence=0.9,
        currency=None,
    )
    duplicate = BankTransaction(
        posted_date=date(2024, 7, 12),
        value_date=None,
        description="Payment A",
        amount=Decimal("10.50"),
        source_page=1,
        confidence=0.5,
        currency=None,
    )

    class DummyStrategy:
        name = "dummy"

        def parse(self, doc):  # type: ignore[no-untyped-def]
            # Expose debug_rows to simulate strategy debugging payload
            self.debug_rows = [{"row": "r1"}]  # noqa: B018
            return [duplicate, kept]

    dummy = DummyStrategy()

    def fake_choose_strategy(doc):  # type: ignore[no-untyped-def]
        return dummy

    from src.finance.bank_statements import agentic_parser as ap_mod

    monkeypatch.setattr(ap_mod, "choose_strategy", fake_choose_strategy)

    parser = AgenticStatementParser(ParserConfig(debug_dump_dir=str(tmp_path / "dump")))

    # Act
    txs, report = parser.parse(pdf_path)

    # Assert: types and deduplication (only the best/longer survives)
    assert isinstance(report, ParseReport)
    assert all(isinstance(t, BankTransaction) for t in txs)
    assert len(txs) == 1 and txs[0].description == kept.description

    # Report invariants
    assert report.pages_total == 1
    assert report.pages_parsed == 1
    assert report.transactions_extracted == 1
    assert report.by_strategy.get("dummy") == 1
    assert len(report.decisions) == 1
    assert report.decisions[0].page_number == 1
    assert len(report.decisions[0].transactions) == 1

    # Debug dump files created
    dump_dir = Path(parser.config.debug_dump_dir)  # type: ignore[arg-type]
    assert (dump_dir / "page-001.txt").exists()
    assert (dump_dir / "transactions.json").exists()
    assert (dump_dir / "rows.jsonl").exists()  # because strategy exposed debug_rows


def test_parse_no_rows_sets_pages_parsed_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Arrange: PDF with a strategy that returns no rows
    pdf_path = tmp_path / "empty.pdf"
    _make_minimal_pdf(pdf_path)

    class NoopStrategy:
        name = "noop"

        def parse(self, doc):  # type: ignore[no-untyped-def]
            return []

    def fake_choose_strategy(doc):  # type: ignore[no-untyped-def]
        return NoopStrategy()

    from src.finance.bank_statements import agentic_parser as ap_mod

    monkeypatch.setattr(ap_mod, "choose_strategy", fake_choose_strategy)
    parser = AgenticStatementParser()

    # Act
    txs, report = parser.parse(pdf_path)

    # Assert
    assert txs == []
    assert report.pages_total == 1
    assert report.pages_parsed == 0  # no candidate rows were produced
    assert report.transactions_extracted == 0
    assert report.by_strategy.get("noop") == 0
    assert len(report.decisions) == 1 and len(report.decisions[0].transactions) == 0
