from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from polars.testing import assert_frame_equal

# Ensure 'src' is on sys.path so absolute imports like 'journal_ingest.*' resolve
SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _import_target():
    # Import lazily to avoid side effects during test collection
    from modules.process_pdf_journal import process_pdf_journal as mpj

    return mpj


def test_process_pdf_journal_success_calls_ui_and_returns_df(monkeypatch):
    mpj = _import_target()

    # Arrange
    calls: list[tuple[str, tuple, dict]] = []

    def _rec(name):
        def _fn(*args, **kwargs):
            calls.append((name, args, kwargs))
            # download_button returns a boolean; others return None
            return True if name == "download_button" else None

        return _fn

    # Stub UI hooks used by the function
    monkeypatch.setattr(mpj.ui, "info", _rec("info"), raising=False)
    monkeypatch.setattr(mpj.ui, "success", _rec("success"), raising=False)
    monkeypatch.setattr(mpj.ui, "error", _rec("error"), raising=False)
    monkeypatch.setattr(mpj.ui, "download_button", _rec("download_button"), raising=False)

    # Stub parser and Excel exporter
    expected_df = pl.DataFrame({"a": [1, 2, 3]})
    seen: dict[str, object] = {}

    def fake_parse_journal(pdf_bytes: bytes, *, header_row=None):  # noqa: ANN001
        # capture the header_row pass-through contract
        seen["header_row"] = header_row
        assert isinstance(pdf_bytes, (bytes, bytearray))
        return expected_df

    monkeypatch.setattr(mpj, "parse_journal", fake_parse_journal)
    monkeypatch.setattr(mpj, "to_excel_bytes", lambda df: b"excel-bytes")

    # Minimal file-like with getvalue()
    pdf_file = SimpleNamespace(getvalue=lambda: b"%PDF-1.4\n...")

    # Act
    result = mpj.process_pdf_journal(pdf_file, header_row=2)

    # Assert
    assert_frame_equal(result, expected_df)
    assert seen.get("header_row") == 2  # header_row is passed through

    # Verify UI interactions
    kinds = [k for k, *_ in calls]
    assert "info" in kinds
    assert "success" in kinds
    assert "download_button" in kinds
    # Check the download details
    dl = next(item for item in calls if item[0] == "download_button")
    args, kwargs = dl[1], dl[2]
    assert args[0].startswith("📥 Download")
    assert kwargs["data"] == b"excel-bytes"
    assert kwargs["file_name"] == "journal_with_movements.xlsx"
    assert (
        kwargs["mime"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_process_pdf_journal_value_error_shows_error_and_returns_none(monkeypatch):
    mpj = _import_target()

    # Arrange
    calls: list[str] = []
    monkeypatch.setattr(mpj.ui, "info", lambda *a, **k: calls.append("info"), raising=False)
    monkeypatch.setattr(
        mpj.ui, "error", lambda *a, **k: calls.append("error"), raising=False
    )
    # Avoid touching the real exporter
    monkeypatch.setattr(mpj, "to_excel_bytes", lambda df: b"irrelevant")

    def raise_value_error(*_a, **_k):  # noqa: ANN001
        raise ValueError("bad pdf")

    monkeypatch.setattr(mpj, "parse_journal", raise_value_error)

    pdf_file = SimpleNamespace(getvalue=lambda: b"%PDF")

    # Act
    result = mpj.process_pdf_journal(pdf_file)

    # Assert
    assert result is None
    assert calls.count("info") == 1
    assert calls.count("error") == 1


@pytest.mark.parametrize("exc_factory", [lambda: pl.exceptions.PolarsError("x")])
def test_process_pdf_journal_expected_errors_return_none(monkeypatch, exc_factory):
    mpj = _import_target()

    # Arrange
    flags = {"error": 0}
    monkeypatch.setattr(mpj.ui, "info", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(
        mpj.ui, "error", lambda *a, **k: flags.__setitem__("error", flags["error"] + 1), raising=False
    )
    # Ensure expected exception class exists on pdfplumber for the except clause
    if not hasattr(mpj.pdfplumber, "PDFSyntaxError"):
        monkeypatch.setattr(mpj.pdfplumber, "PDFSyntaxError", Exception, raising=False)
    monkeypatch.setattr(mpj, "to_excel_bytes", lambda df: b"irrelevant")

    def _raise(*_a, **_k):  # noqa: ANN001
        raise exc_factory()

    monkeypatch.setattr(mpj, "parse_journal", _raise)

    pdf_file = SimpleNamespace(getvalue=lambda: b"%PDF")

    # Act
    res = mpj.process_pdf_journal(pdf_file)

    # Assert
    assert res is None
    assert flags["error"] == 1
