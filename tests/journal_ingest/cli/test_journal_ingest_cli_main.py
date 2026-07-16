from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

import pytest

# Ensure the 'src' package root is importable for journal_ingest
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import importlib
from journal_ingest.cli.main import build_router, main
from journal_ingest.router import Router
from journal_ingest.strategies import (
    JournalStrategyExcel,
    JournalStrategyTableArea,
    JournalStrategyTextLayout,
    OcrParser,
    TablePDFParser,
    TextPDFParser,
)


def test_build_router_parsers_and_agent() -> None:
    # Arrange
    sentinel = object()

    # Act
    router = build_router(agent=sentinel)

    # Assert
    assert isinstance(router, Router)
    # expected order and count
    assert [
        type(p) for p in router.parsers
    ] == [
        JournalStrategyExcel,
        TextPDFParser,
        TablePDFParser,
        JournalStrategyTextLayout,
        JournalStrategyTableArea,
        OcrParser,
    ]
    assert router.agent is sentinel


def test_main_auto_writes_csv_when_rows_returned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: stub router + parser to yield two balanced rows
    class StubParser:
        def probe(self, file_bytes: bytes, meta: dict | None = None) -> float:
            return 0.9

        def parse(self, file_bytes: bytes, meta: dict | None = None):
            return [
                {
                    "entry_date": date(2024, 1, 1),
                    "entry_label": "lbl",
                    "unit": "u",
                    "location": "loc",
                    "line_no": 1,
                    "account_code": "100",
                    "account_desc": "Cash",
                    "memo": "",
                    "debit": 10.0,
                    "credit": None,
                },
                {
                    "entry_date": date(2024, 1, 1),
                    "entry_label": "lbl",
                    "unit": "u",
                    "location": "loc",
                    "line_no": 2,
                    "account_code": "200",
                    "account_desc": "Sales",
                    "memo": "",
                    "debit": None,
                    "credit": 10.0,
                },
            ]

    class StubRouter:
        def route(self, file_bytes: bytes, meta: dict | None = None):
            return StubParser()

    cli_main_mod = importlib.import_module("journal_ingest.cli.main")
    monkeypatch.setattr(cli_main_mod, "build_router", lambda *_: StubRouter())

    input_path = tmp_path / "in.bin"
    input_path.write_bytes(b"dummy")
    out_path = tmp_path / "out.csv"

    # Act
    rc = main([str(input_path), "--output", str(out_path)])

    # Assert
    assert rc == 0
    assert out_path.exists()
    with out_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    # sanity-check a couple of fields made it through
    assert {r["account_code"] for r in rows} == {"100", "200"}


def test_main_manual_recipe_returns_zero_and_no_output(tmp_path: Path) -> None:
    # Arrange
    input_path = tmp_path / "in.txt"
    input_path.write_text("irrelevant")
    out_path = tmp_path / "out.csv"

    # Act
    rc = main([str(input_path), "--output", str(out_path), "--recipe", "sample"])

    # Assert: no rows -> no file written, but exit is success
    assert rc == 0
    assert not out_path.exists()


def test_main_auto_no_parser_selected_returns_one(tmp_path: Path) -> None:
    # Arrange: use real router with empty file, no agent allowed
    input_path = tmp_path / "empty.bin"
    input_path.write_bytes(b"")

    # Act
    rc = main([str(input_path)])

    # Assert
    assert rc == 1
