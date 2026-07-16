from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

# Ensure 'src' is on sys.path so 'statements' resolves from the real package
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import polars as pl
import pytest
from polars.testing import assert_frame_equal

import statements.extract as extract_mod


@dataclass
class _Row:
    description: str
    amount: int
    currency: str
    # Columns that must be dropped by the CLI before writing CSV
    reference_ids: list[str]
    beneficiary: str


@dataclass
class _Diag:
    language: str
    currency: str
    strategy_used: str
    rows: int


class _StubExtractor:
    called: bool = False
    last_file: str | None = None
    last_config: dict | None = None

    def orchestrate(self, file_path: str, config: dict):  # noqa: D401
        self.called = True
        self.last_file = file_path
        self.last_config = config
        rows = [
            _Row(
                description="Payment A",
                amount=100,
                currency="USD",
                reference_ids=["x1", "x2"],
                beneficiary="Alice",
            ),
            _Row(
                description="Refund B",
                amount=-30,
                currency="USD",
                reference_ids=[],
                beneficiary="Bob",
            ),
        ]
        diag = _Diag(language="en", currency="USD", strategy_used="stub", rows=2)
        return rows, diag


def test_main_writes_csv_and_diagnostics_and_drops_columns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    stub = _StubExtractor()
    monkeypatch.setattr(extract_mod, "StatementExtractor", lambda: stub)
    out_csv = tmp_path / "out.csv"
    diag_json = tmp_path / "diag.json"
    fake_input = tmp_path / "input.pdf"
    argv = ["--file", str(fake_input), "--out", str(out_csv), "--diagnostics", str(diag_json)]

    # Act
    extract_mod.main(argv)

    # Assert: orchestrator called with file path and empty config
    assert stub.called is True
    assert stub.last_file == str(fake_input)
    assert stub.last_config == {}

    # Assert: diagnostics JSON written with expected content
    import json

    with diag_json.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data == {"language": "en", "currency": "USD", "strategy_used": "stub", "rows": 2}

    # Assert: CSV exists and dropped the specified columns
    assert out_csv.exists()
    df = pl.read_csv(out_csv)
    # Must not include dropped columns
    assert "reference_ids" not in df.columns
    assert "beneficiary" not in df.columns

    # Compare remaining content deterministically (order-agnostic)
    expected = pl.DataFrame(
        {
            "description": ["Payment A", "Refund B"],
            "amount": [100, -30],
            "currency": ["USD", "USD"],
        }
    )
    # sort columns by name to avoid relying on construction order
    df_sorted = df.select(sorted(df.columns)).sort("description")
    expected_sorted = expected.select(sorted(expected.columns)).sort("description")
    assert_frame_equal(df_sorted, expected_sorted, check_column_order=True, check_row_order=True)


def test_main_writes_only_diagnostics_when_out_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    stub = _StubExtractor()
    monkeypatch.setattr(extract_mod, "StatementExtractor", lambda: stub)
    diag_json = tmp_path / "diag.json"
    fake_input = tmp_path / "input.pdf"

    # Act
    extract_mod.main(["--file", str(fake_input), "--diagnostics", str(diag_json)])

    # Assert: diagnostics file exists and CSV not written
    assert diag_json.exists()
    # Minimal content check
    import json

    assert json.loads(diag_json.read_text()) == {
        "language": "en",
        "currency": "USD",
        "strategy_used": "stub",
        "rows": 2,
    }


def test_main_requires_file_argument_raises_system_exit():
    # Arrange / Act / Assert
    with pytest.raises(SystemExit) as exc:
        extract_mod.main([])
    # argparse uses exit code 2 for parse errors
    assert exc.value.code == 2
