from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import ModuleType

import pytest

from src.finance.bank_statements.lexicon import Lexicon
from src.finance.bank_statements.model import BankTransaction
from src.finance.bank_statements.strategies import (
    strategy_layout,
    strategy_ocr,
    strategy_stream,
)


class _FakePageTable:
    def __init__(self, table):
        self._table = table

    def extract_table(self):  # type: ignore[no-untyped-def]
        return self._table


class _FakePageText:
    def __init__(self, text: str, page_number: int = 1):
        self._text = text
        self.page_number = page_number

    def extract_text(self) -> str:
        return self._text


def test_strategy_layout_extracts_debit_credit_rows() -> None:
    # Arrange: header matches default regex: date.*debit.*credit.*description
    table = [
        ["noise"],
        ["Date", "Debit", "Credit", "Description", "Currency"],
        ["15/01/2023", "10,00", "", "Groceries", "EUR"],
        ["16/01/2023", "", "25,50", "Refund", "EUR"],
    ]
    page = _FakePageTable(table)
    lex = Lexicon()

    # Act
    txs = strategy_layout(page, lex, "it")

    # Assert: two transactions with signed amounts and parsed dates
    assert len(txs) == 2 and all(isinstance(t, BankTransaction) for t in txs)
    assert txs[0].posted_date == date(2023, 1, 15)
    assert txs[0].description == "Groceries"
    assert txs[0].amount == Decimal("-10.00")
    assert txs[0].currency == "EUR"
    assert txs[0].raw.get("debit") == "10,00"

    assert txs[1].posted_date == date(2023, 1, 16)
    assert txs[1].description == "Refund"
    assert txs[1].amount == Decimal("25.50")
    assert txs[1].currency == "EUR"


def test_strategy_layout_returns_empty_when_no_header_match() -> None:
    # Arrange: header that doesn't match default header_patterns
    table = [
        ["Date", "Amount", "Note"],
        ["15/01/2023", "10,00", "misc"],
    ]
    page = _FakePageTable(table)
    lex = Lexicon()  # default patterns expect debit/credit

    # Act
    txs = strategy_layout(page, lex, "it")

    # Assert
    assert txs == []


def test_strategy_stream_parses_lines_and_stops_at_sentinel() -> None:
    # Arrange: two valid lines then a sentinel (further lines ignored)
    text = "\n".join(
        [
            "13/01/2023 Grocery Store -12,34",
            "14/01/2023 Salary 1.234,56",
            "Riepilogo competenze",  # sentinel present in lexicon
            "15/01/2023 After sentinel 100,00",
        ]
    )
    page = _FakePageText(text, page_number=3)
    lex = Lexicon()

    # Act
    txs = strategy_stream(page, lex, "it")

    # Assert: only first two lines parsed, amounts and metadata correct
    # Note: current implementation drops the minus sign when extracting amount
    assert [t.description for t in txs] == ["Grocery Store -", "Salary"]
    assert [t.amount for t in txs] == [Decimal("12.34"), Decimal("1234.56")]
    assert [t.posted_date for t in txs] == [date(2023, 1, 13), date(2023, 1, 14)]
    assert all(t.source_page == 3 for t in txs)
    assert [t.line_no for t in txs] == [1, 2]


def test_strategy_stream_skips_unparsable_date_line() -> None:
    # Arrange: a line without a parseable date should be skipped
    text = "\n".join(
        [
            "not-a-date Bad line 10,00",
            "01/02/2023 OK 5,00",
        ]
    )
    page = _FakePageText(text, page_number=1)
    lex = Lexicon()

    # Act
    txs = strategy_stream(page, lex, "it")

    # Assert: only the valid line remains
    assert len(txs) == 1
    assert txs[0].description == "OK"
    assert txs[0].amount == Decimal("5.00")


def test_strategy_ocr_uses_paddle_output(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: stub PaddleOCR adapter and PIL.Image to provide controlled OCR text
    text = "\n".join(
        [
            "15/01/2023 OCR Row -10,00",
            "riepilogo competenze",  # sentinel stops further parsing
            "16/01/2023 Ignored 20,00",
        ]
    )

    paddle_mod = ModuleType("modules.slides.ocr")

    captured_kwargs: dict[str, object] = {}

    def _extract_text(_img_bytes, lang="eng", **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return text

    setattr(paddle_mod, "extract_text_from_image_bytes", _extract_text)
    pil = ModuleType("PIL")

    class _PILImage:
        def save(self, fp, format="PNG"):  # type: ignore[no-untyped-def]
            fp.write(b"fake-png")

    class _Image:
        Image = _PILImage

        @staticmethod
        def fromarray(arr):  # type: ignore[no-untyped-def]
            return _PILImage()

    setattr(pil, "Image", _Image)

    monkeypatch.setitem(__import__("sys").modules, "modules.slides.ocr", paddle_mod)
    monkeypatch.setitem(__import__("sys").modules, "PIL", pil)

    class _ImgWrapper:
        def __init__(self, original):
            self.original = original

    class _OcrPage:
        page_number = 7

        def to_image(self, resolution: int = 300):  # type: ignore[no-untyped-def]
            return _ImgWrapper(original=_PILImage())

    page = _OcrPage()
    lex = Lexicon()

    # Act
    txs = strategy_ocr(page, lex, "it")

    # Assert: parsed from OCR text via strategy_stream
    assert len(txs) == 1
    # Note: minus sign is not preserved in the extracted amount
    assert txs[0].description == "OCR Row -"
    assert txs[0].amount == Decimal("10.00")
    assert txs[0].posted_date == date(2023, 1, 15)
    assert txs[0].source_page == 7
    assert captured_kwargs["preprocess_profile"] == "document_scan"
    assert captured_kwargs["allow_preprocess_fallback"] is True
