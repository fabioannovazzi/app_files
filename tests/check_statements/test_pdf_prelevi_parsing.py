from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "pdf_name, expected",
    [
        ("30_03_2024.pdf", (date(2024, 1, 23), -500.0)),
        ("30_12_2024.pdf", (date(2024, 12, 24), -1300.0)),
    ],
)
def test_parse_pdf_prepare_extracts_prelevi(pdf_name: str, expected: tuple[date, float]) -> None:
    root = Path(__file__).resolve().parents[2]
    for p in (root, root / "src"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    loaders_mod = _load_module(
        "cs_loaders",
        root / "src" / "check_statements" / "loaders.py",
    )
    content = Path(__file__).resolve().parents[2] / "test_data" / pdf_name
    try:
        rows = loaders_mod.parse_pdf_prepare(
            content.read_bytes(),
            pdf_name,
            language="it",
            deterministic_only=True,
        )
    except ImportError as exc:
        pytest.skip(f"PDF parsing dependencies unavailable: {exc}")

    match = None
    target_date, target_amount = expected
    for row in rows:
        if row.get("date") == target_date and pytest.approx(row.get("amount"), abs=0.01) == target_amount:
            match = row
            break

    assert match is not None, f"Expected transaction {expected} not parsed"
