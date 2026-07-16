from __future__ import annotations

import re
from datetime import date

import src.check_statements as logic
from src.check_statements import Transaction, reconcile_transactions


def test_reconcile_transactions_marks_synthetic_fee(monkeypatch):
    bank = [Transaction(date=date(2024, 1, 1), amount=5.0, description="fee charge")]
    ledger: list[Transaction] = []
    monkeypatch.setattr(logic, "load_fee_patterns", lambda: [re.compile("fee", re.I)])

    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank,
        ledger,
        exclude_fees=True,
        fee_mode="match",
    )

    assert matched == [(0, None, "exact")]
    assert unmatched_bank == []
    assert unmatched_ledger == []
