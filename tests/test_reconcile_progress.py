from __future__ import annotations

from datetime import date
from typing import List

import pytest

from src.check_statements import Transaction, reconcile_transactions


def test_reconcile_progress_callback_runs_for_all_passes():
    bank: List[Transaction] = [
        Transaction(date=date(2024, 1, 1), amount=100.0, description="foo"),
        Transaction(date=date(2024, 1, 2), amount=200.0, description="bar"),
    ]
    ledger: List[Transaction] = []
    progresses: List[float] = []

    def progress_cb(progress: float, matches: int, idx: int) -> None:  # noqa: ARG001
        progresses.append(progress)

    reconcile_transactions(
        bank,
        ledger,
        progress_callback=progress_cb,
        group_limit=2,
    )

    total_passes = 3
    expected = [
        (p + (i + 1) / len(bank)) / total_passes
        for p in range(total_passes)
        for i in range(len(bank))
    ]
    assert progresses == pytest.approx(expected)
