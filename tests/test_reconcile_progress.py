from __future__ import annotations

from datetime import date
from typing import List

import pytest

from src.check_statements import Transaction, reconcile_transactions


def test_reconcile_progress_callback_reports_executed_passes():
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

    assert progresses == sorted(progresses)
    assert progresses[-1] == pytest.approx(1.0)
    assert 1.0 not in progresses[:-1]


def test_reconcile_progress_is_monotonic_without_adaptive_group_retry():
    bank = [
        Transaction(date=date(2024, 1, 1), amount=100.0, description="foo"),
        Transaction(date=date(2024, 1, 2), amount=200.0, description="bar"),
    ]
    progresses: List[float] = []

    reconcile_transactions(
        bank,
        [],
        progress_callback=lambda progress, _matches, _idx: progresses.append(progress),
        group_limit=3,
    )

    assert progresses == sorted(progresses)
    assert progresses[-1] == pytest.approx(1.0)
    assert 1.0 not in progresses[:-1]


def test_reconcile_progress_completes_when_adaptive_retry_is_not_needed():
    bank = [
        Transaction(
            date=date(2024, 1, 1),
            amount=100.0,
            description="bank",
            reference_ids=["REF-100"],
        )
    ]
    ledger = [
        Transaction(
            date=date(2024, 1, 1),
            amount=100.0,
            description="ledger",
            reference_ids=["REF-100"],
        )
    ]
    progresses: List[float] = []

    reconcile_transactions(
        bank,
        ledger,
        progress_callback=lambda progress, _matches, _idx: progresses.append(progress),
        group_limit=2,
    )

    assert progresses == sorted(progresses)
    assert progresses[-1] == pytest.approx(1.0)
    assert 1.0 not in progresses[:-1]


def test_reconcile_progress_completes_empty_input():
    progresses: List[float] = []

    reconcile_transactions(
        [],
        [],
        progress_callback=lambda progress, _matches, _idx: progresses.append(progress),
        group_limit=2,
    )

    assert progresses == [pytest.approx(1.0)]
