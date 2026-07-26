from __future__ import annotations

import re
from datetime import date

from src.check_statements import Transaction, reconcile_transactions


def test_reconcile_transactions_marks_synthetic_fee(monkeypatch):
    bank = [Transaction(date=date(2024, 1, 1), amount=5.0, description="fee charge")]
    ledger: list[Transaction] = []
    monkeypatch.setitem(
        reconcile_transactions.__globals__,
        "load_fee_patterns",
        lambda: [re.compile("fee", re.I)],
    )

    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank,
        ledger,
        exclude_fees=True,
        fee_mode="match",
    )

    assert matched == [(0, None, "exact")]
    assert unmatched_bank == []
    assert unmatched_ledger == []


def test_reconcile_transactions_links_duplicate_fees_to_distinct_synthetic_rows(
    monkeypatch,
):
    bank = [
        Transaction(date=date(2024, 1, 1), amount=5.0, description="fee charge"),
        Transaction(date=date(2024, 1, 1), amount=5.0, description="fee charge"),
    ]
    monkeypatch.setitem(
        reconcile_transactions.__globals__,
        "load_fee_patterns",
        lambda: [re.compile("fee", re.I)],
    )
    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank,
        [],
        exclude_fees=True,
        fee_mode="match",
    )

    assert matched == [(0, None, "exact"), (1, None, "exact")]
    assert unmatched_bank == []
    assert unmatched_ledger == []


def test_reconcile_transactions_does_not_consume_unrelated_same_value_fee_entry(
    monkeypatch,
):
    bank = [Transaction(date=date(2024, 1, 1), amount=5.0, description="fee charge")]
    ledger = [
        Transaction(
            date=date(2024, 1, 1),
            amount=5.0,
            description="unrelated ledger row",
        )
    ]
    monkeypatch.setitem(
        reconcile_transactions.__globals__,
        "load_fee_patterns",
        lambda: [re.compile("fee", re.I)],
    )

    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank,
        ledger,
        exclude_fees=True,
        fee_mode="match",
    )

    assert matched == [(0, None, "exact")]
    assert unmatched_bank == []
    assert unmatched_ledger == [0]


def test_reconcile_transactions_does_not_trust_caller_synthetic_fee_metadata():
    bank = [Transaction(date=date(2024, 1, 1), amount=5.0, description="fee charge")]
    ledger = [
        Transaction(
            date=date(2024, 1, 1),
            amount=5.0,
            description="Bank fee",
            metadata={
                "source": {"name": "synthetic_fee"},
                "synthetic_fee_bank_index": 0,
            },
        )
    ]

    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank,
        ledger,
        exclude_fees=False,
    )

    assert matched == []
    assert unmatched_bank == [0]
    assert unmatched_ledger == [0]


def test_reconcile_transactions_does_not_treat_fee_words_as_exact_authority():
    bank = [Transaction(date=date(2024, 1, 1), amount=5.0, description="fee charge")]
    ledger = [Transaction(date=date(2024, 1, 1), amount=5.0, description="fee charge")]

    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank,
        ledger,
        exclude_fees=False,
        fuzzy_threshold=101.0,
    )

    assert matched == []
    assert unmatched_bank == [0]
    assert unmatched_ledger == [0]


def test_reconcile_transactions_links_each_recurring_amount_to_its_origin(
    monkeypatch,
):
    recurring_count = 20
    bank = [
        Transaction(
            date=date(2024, 1, 1),
            amount=5.0,
            description=f"small recurring row {index}",
        )
        for index in range(recurring_count)
    ]
    monkeypatch.setitem(
        reconcile_transactions.__globals__,
        "load_fee_patterns",
        lambda: [re.compile(r"does-not-match")],
    )

    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank,
        [],
        exclude_fees=True,
        fee_mode="match",
    )

    assert matched == [(index, None, "exact") for index in range(recurring_count)]
    assert unmatched_bank == []
    assert unmatched_ledger == []
