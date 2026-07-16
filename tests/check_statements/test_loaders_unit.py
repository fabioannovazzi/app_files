from __future__ import annotations

import io
from datetime import date
import re

import polars as pl

import os
import sys
import importlib.util
from pathlib import Path
import types

# Load loaders module directly to avoid heavy package __init__ side-effects
ROOT = Path(os.getcwd()).resolve()
sys.path.insert(0, str(ROOT))
LOADERS_PATH = ROOT / "src" / "check_statements" / "loaders.py"
spec = importlib.util.spec_from_file_location("cs_loaders", str(LOADERS_PATH))
assert spec and spec.loader, "Failed to locate loaders module"
cs_loaders = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs_loaders)  # type: ignore[arg-type]

parse_spreadsheet_prepare = cs_loaders.parse_spreadsheet_prepare
parse_spreadsheet_prepare_with_keywords = cs_loaders.parse_spreadsheet_prepare_with_keywords
load_ledger_rows = cs_loaders.load_ledger_rows
parse_pdf_prepare = cs_loaders.parse_pdf_prepare
_parse_amount_local = cs_loaders._parse_amount_local  # type: ignore[attr-defined]


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def test_parse_spreadsheet_prepare_csv_basic() -> None:
    # Arrange
    content = _csv_bytes("Date,Description,Amount\n2024-09-01,Payment,100.50\n")

    # Act
    df, mapping = parse_spreadsheet_prepare(content, "test.csv")

    # Assert
    assert isinstance(df, pl.DataFrame)
    assert df.height == 1
    # Ensure core fields are inferred
    assert mapping.get("date") == 0
    assert mapping.get("description") == 1
    assert mapping.get("amount") == 2


def test_parse_spreadsheet_prepare_with_keywords_overrides() -> None:
    # Arrange
    content = _csv_bytes("Booking Date,Desc.,Value\n2024-08-05,Wire,250.00\n")
    keywords = {
        "date": ["booking date"],
        "description": ["desc."],
        "amount": ["value"],
    }

    # Act
    df, mapping = parse_spreadsheet_prepare_with_keywords(content, "dummy.csv", keywords)

    # Assert
    assert df.height == 1
    assert mapping.get("date") == 0
    assert mapping.get("description") == 1
    assert mapping.get("amount") == 2


def test_load_ledger_rows_csv_minimal() -> None:
    # Arrange: minimal ledger-like CSV using standard headers
    rows = [
        "data,descrizione,importo",
        "2024-08-12,Acquisto materiali,123.45",
    ]
    content = _csv_bytes("\n".join(rows) + "\n")

    # Act
    out = load_ledger_rows([("ledger.csv", content)], language="ita")

    # Assert
    assert len(out) == 1
    row = out[0]
    assert isinstance(row.get("date"), date)
    assert abs(float(row.get("amount", 0.0)) - 123.45) < 1e-6
    assert isinstance(row.get("description"), str)
    meta = row.get("metadata") or {}
    assert meta.get("source") == "ledger.csv"
    assert meta.get("language") == "ita"


def test_parse_pdf_prepare_returns_empty_without_parsers() -> None:
    # Arrange: invalid PDF bytes should be handled gracefully, returning []
    bogus_pdf = b"not a pdf"

    # Act
    rows = parse_pdf_prepare(bogus_pdf, "sample.pdf", language="ita", deterministic_only=True)

    # Assert
    assert isinstance(rows, list)
    assert rows == []


def test_parse_amount_local_handles_mixed_separators() -> None:
    assert _parse_amount_local("1,300.00") == 1300.0
    assert _parse_amount_local("1.300,00") == 1300.0
    assert _parse_amount_local("-1,300.00") == -1300.0


def test_load_ledger_rows_retains_pattern_matches_when_extra_desc_present() -> None:
    """Rows with ignore-pattern descriptions must survive when extra details exist."""

    finance_mod = types.ModuleType("finance")
    ledger_pkg = types.ModuleType("finance.ledger")
    ignore_mod = types.ModuleType("finance.ledger.ignore_patterns")

    def load_ignore_patterns(_path):
        return [re.compile("RILEVAZIONI VARIE")]

    ignore_mod.load_ignore_patterns = load_ignore_patterns  # type: ignore[attr-defined]
    ledger_pkg.ignore_patterns = ignore_mod  # type: ignore[attr-defined]
    finance_mod.ledger = ledger_pkg  # type: ignore[attr-defined]

    sys.modules["finance"] = finance_mod
    sys.modules["finance.ledger"] = ledger_pkg
    sys.modules["finance.ledger.ignore_patterns"] = ignore_mod

    try:
        rows = [
            "Data reg.,Descr. causale,Codice conto,Descr. conto,Dare,Avere,Descr. agg.",
            '24/12/2024,RILEVAZIONI VARIE,15 / 15 / 1,Cassa Euro,"1,300.00",,PRELEVAMENTO ALLO SPORTELLO',
        ]
        content = _csv_bytes("\n".join(rows) + "\n")

        out = load_ledger_rows([("ledger.csv", content)], language="ita")

        assert len(out) == 1
        assert out[0]["metadata"].get("extra_desc") == "PRELEVAMENTO ALLO SPORTELLO"
    finally:
        sys.modules.pop("finance", None)
        sys.modules.pop("finance.ledger", None)
        sys.modules.pop("finance.ledger.ignore_patterns", None)
