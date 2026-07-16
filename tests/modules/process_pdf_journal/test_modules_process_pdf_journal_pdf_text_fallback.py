from __future__ import annotations

import io
from typing import Iterable, List
import types
from datetime import date, datetime

import polars as pl
from polars.testing import assert_frame_equal

from modules.process_pdf_journal.pdf_text_fallback import (
    infer_dare_avere_x_positions,
    parse_pdf_group_lines,
    parse_pdf_text_mode,
)


class _FakePage:
    def __init__(self, text: str = "", words: Iterable[dict] | None = None) -> None:
        self._text = text
        self._words = list(words or [])

    def extract_text(self) -> str:
        return self._text

    def extract_words(self, x_tolerance: int = 1, y_tolerance: int = 3) -> List[dict]:
        return list(self._words)


class _FakePDF:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def __enter__(self):  # context manager API used by the code under test
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_fake_open(page_texts: list[str]):
    def _open(_file_like):
        return _FakePDF([_FakePage(text=t) for t in page_texts])

    return _open


def _install_fake_logic(monkeypatch):
    """Install a lightweight stub for modules.process_pdf_journal.logic.

    The production module has external dependencies not needed here; we only
    provide the two functions imported by the code under test.
    """
    mod = types.ModuleType("modules.process_pdf_journal.logic")

    def parse_amount(s: str) -> float | None:
        s = (s or "").strip().replace("\u00a0", "").replace("€", "")
        if s in {"", "-", "—"}:
            return None
        s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None

    def parse_date_str(s: str):
        try:
            return datetime.strptime(s.strip(), "%d/%m/%Y").date()
        except Exception:
            return None

    mod.parse_amount = parse_amount  # type: ignore[attr-defined]
    mod.parse_date_str = parse_date_str  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "modules.process_pdf_journal.logic", mod)


def test_infer_dare_avere_x_positions_two_clusters():
    # Arrange: two clear clusters of monetary amounts (left and right columns)
    words = [
        {"x0": 90, "x1": 110, "text": "123,45"},  # mid 100 (left)
        {"x0": 110, "x1": 130, "text": "67,89"},   # mid 120 (left)
        {"x0": 290, "x1": 310, "text": "1.234,56"},  # mid 300 (right)
        {"x0": 310, "x1": 330, "text": "10,00"},  # mid 320 (right)
        {"x0": 0, "x1": 0, "text": "NOTE"},  # ignored non-amount
    ]
    page = _FakePage(words=words)

    # Act
    left_x, right_x = infer_dare_avere_x_positions(page)  # type: ignore[arg-type]

    # Assert
    assert left_x == 110.0
    assert right_x == 310.0


def test_infer_dare_avere_x_positions_missing_amounts_returns_zeros():
    page = _FakePage(words=[{"x0": 0, "x1": 0, "text": "foo"}])

    left_x, right_x = infer_dare_avere_x_positions(page)  # type: ignore[arg-type]

    assert (left_x, right_x) == (0.0, 0.0)


def test_infer_dare_avere_x_positions_single_value_returns_same_for_both():
    page = _FakePage(words=[{"x0": 195, "x1": 205, "text": "100,00"}])  # mid 200

    left_x, right_x = infer_dare_avere_x_positions(page)  # type: ignore[arg-type]

    assert left_x == right_x == 200.0


def test_parse_pdf_text_mode_parses_row_with_headers(monkeypatch):
    # Arrange: header (date + causale, then attivita and filiale), then a row
    lines = [
        "01/02/2024 Vendite",
        "Attivita A",
        "Filiale X",
        "1  12345  Conto Merci  Operazione di vendita   1.234,56",
    ]
    monkeypatch.setattr(
        "modules.process_pdf_journal.pdf_text_fallback.pdfplumber.open",
        _make_fake_open(["\n".join(lines)]),
    )

    # Act
    _install_fake_logic(monkeypatch)
    df = parse_pdf_text_mode(b"%PDF stub bytes%")

    # Assert
    expected = pl.DataFrame(
        [
            {
                "data": date(2024, 2, 1),
                "causale": "Vendite",
                "attivita": "Attivita A",
                "filiale": "Filiale X",
                "riga": "1",
                "conto": "12345",
                "descrizione_conto": "Conto Merci",
                "descrizione_operazione": "Operazione di vendita",
                "amount": 1234.56,
            }
        ]
    )
    assert df.height == 1
    assert_frame_equal(df, expected, check_dtype=False)


def test_parse_pdf_text_mode_ignores_non_matching_lines(monkeypatch):
    # Arrange: lines that do not match the ROW_RE pattern
    text = "\n".join([
        "header that should be ignored",
        "foo bar baz",  # no riga/amount structure
        "conto 12345 123,45",  # does not start with riga
    ])
    monkeypatch.setattr(
        "modules.process_pdf_journal.pdf_text_fallback.pdfplumber.open",
        _make_fake_open([text]),
    )

    # Act
    _install_fake_logic(monkeypatch)
    df = parse_pdf_text_mode(b"irrelevant")

    # Assert
    assert df.is_empty()
    assert df.width == 0


def test_parse_pdf_group_lines_parses_multiline_with_header_fields(monkeypatch):
    # Arrange: header with two fields (causale + field2), then a multi-line row
    lines = [
        "01/02/2024 Causale AAA   Extra Field",
        "12   987654   Conto AAA  Descrizione op",
        "continua qui   €1.234,56",
    ]
    monkeypatch.setattr(
        "modules.process_pdf_journal.pdf_text_fallback.pdfplumber.open",
        _make_fake_open(["\n".join(lines)]),
    )

    # Act
    _install_fake_logic(monkeypatch)
    df = parse_pdf_group_lines(b"binary")

    # Assert
    expected = pl.DataFrame(
        [
            {
                "data": date(2024, 2, 1),
                "causale": "Causale AAA",
                "field2": "Extra Field",
                "riga": "12",
                "conto": "987654",
                "descrizione_conto": "Conto AAA",
                "descrizione_operazione": "Descrizione op continua qui",
                "amount": 1234.56,
            }
        ]
    )
    assert df.height == 1
    assert_frame_equal(df, expected, check_dtype=False)


def test_parse_pdf_group_lines_ignores_non_matching_candidate(monkeypatch):
    # Arrange: buffer starts with a number but the candidate won't match ROW_RE
    # because there is no valid account code segment after riga.
    lines = [
        "01/02/2024 Causale",
        "66 not-an-account",
        "still not valid  10,00",
    ]
    monkeypatch.setattr(
        "modules.process_pdf_journal.pdf_text_fallback.pdfplumber.open",
        _make_fake_open(["\n".join(lines)]),
    )

    # Act
    _install_fake_logic(monkeypatch)
    df = parse_pdf_group_lines(b"binary")

    # Assert
    assert df.is_empty()
    assert df.width == 0
