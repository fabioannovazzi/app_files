from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from src.check_statements import (
    Transaction,
    detect_bank_accounts,
    reconcile_transactions,
)


def test_f24_matches_tax_only() -> None:
    bank = [
        Transaction(
            date=date(2024, 2, 1), amount=-220.0, description="F24 TELEMATICO DELEGA"
        )
    ]
    ledger = [
        Transaction(
            date=date(2024, 2, 1),
            amount=-220.0,
            description="Versamento erario",
            metadata={"account_desc": "Erario c/IVA"},
        ),
        Transaction(
            date=date(2024, 2, 1),
            amount=-220.0,
            description="Pagamento fornitore",
            metadata={"account_desc": "Fornitori"},
        ),
    ]
    matched, ub, ul = reconcile_transactions(bank, ledger, date_window=0)
    assert matched == [(0, 0, "exact")]
    assert ub == []
    assert ul == [1]


def test_split_payment_separate_matches_no_grouping() -> None:
    bank = [
        Transaction(
            date=date(2024, 3, 5),
            amount=-1000.0,
            description="Bonifico fornitore X",
            beneficiary="fornitore x",
        ),
        Transaction(date=date(2024, 3, 5), amount=-220.0, description="F24 IVA"),
    ]
    ledger = [
        Transaction(
            date=date(2024, 3, 5),
            amount=-1000.0,
            description="Pagamento fattura",
            beneficiary="fornitore x",
            metadata={"account_desc": "Fornitori"},
        ),
        Transaction(
            date=date(2024, 3, 5),
            amount=-220.0,
            description="Liquidazione IVA",
            metadata={"account_desc": "Erario c/IVA"},
        ),
    ]
    matched, ub, ul = reconcile_transactions(bank, ledger, date_window=0)
    # Two separate matches; no grouping
    assert len(matched) == 2
    assert ub == []
    assert ul == []


def test_grouping_supplier_batch_unique() -> None:
    bank = [
        Transaction(
            date=date(2024, 4, 1),
            amount=-3000.0,
            description="Bonifico fornitori",
            beneficiary="alpha srl",
        )
    ]
    ledger = [
        Transaction(
            date=date(2024, 4, 1),
            amount=-1200.0,
            description="Pagamento A",
            beneficiary="alpha srl",
        ),
        Transaction(
            date=date(2024, 4, 1),
            amount=-1800.0,
            description="Pagamento B",
            beneficiary="alpha srl",
        ),
    ]
    matched, ub, ul = reconcile_transactions(bank, ledger, group_limit=2, date_window=0)
    assert matched == [(0, (0, 1), "group")]
    assert ub == []
    assert ul == []


def test_dense_day_threshold_bump_effect_via_threshold_param() -> None:
    # Simulate UI bump by setting fuzzy_threshold=90.0 in the core call
    bank = [
        Transaction(
            date=date(2024, 5, 10),
            amount=-500.0,
            description="Bonifico a favore di Alpha",
            beneficiary="alpha srl",
        )
    ]
    # One candidate with different counterparty should not pass at 90
    ledger = [
        Transaction(
            date=date(2024, 5, 10),
            amount=-500.0,
            description="Bonifico a favore di Beta",
            beneficiary="beta srl",
        )
    ]
    matched, ub, ul = reconcile_transactions(
        bank, ledger, fuzzy_threshold=90.0, date_window=0
    )
    assert matched == []
    assert ub == [0]
    assert ul == [0]


def test_auto_detect_bank_accounts_prefers_bankish() -> None:
    ledger = [
        Transaction(
            date=date(2024, 1, 1),
            amount=10.0,
            description="",
            metadata={"account_id": "A", "account_desc": "Example Bank"},
        ),
        Transaction(
            date=date(2024, 1, 2),
            amount=20.0,
            description="",
            metadata={"account_id": "A", "account_desc": "Example Bank"},
        ),
        Transaction(
            date=date(2024, 1, 3),
            amount=30.0,
            description="",
            metadata={"account_id": "B", "account_desc": "Vendite"},
        ),
    ]
    out = detect_bank_accounts(ledger)
    assert out and out[0]["account_id"] == "A"
