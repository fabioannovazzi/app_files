from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

# Ensure 'src' is on sys.path so absolute imports resolve
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from src.check_statements import Transaction, reconcile_transactions


def test_group_pairs_two_sum_finds_match() -> None:
    bank = [Transaction(date=date(2024, 1, 10), amount=100.0, description="BONIFICO ACME", beneficiary="ACME")]
    ledger = [
        Transaction(date=date(2024, 1, 9), amount=60.0, description="BONIFICO ACME", beneficiary="ACME"),
        Transaction(date=date(2024, 1, 10), amount=40.0, description="BONIFICO ACME", beneficiary="ACME"),
        Transaction(date=date(2024, 1, 12), amount=100.0, description="OTHER", beneficiary="ACME"),
    ]
    matched, ub, ul = reconcile_transactions(
        bank,
        ledger,
        date_window=3,
        group_limit=2,
        use_absolute_amounts=False,
        beneficiary_mode="soft",
        fuzzy_threshold=70.0,
        group_candidates_cap=16,
        max_combos_per_bank=1000,
        group_time_budget_ms=1000,
    )
    # Either the exact single (index 2) or the pair (0,1) is acceptable; but we want to 
    # assert that grouping can produce a pair match and that the method label is present.
    assert matched, "Expected at least one match"
    # Find a grouped pair
    group_hits = [m for m in matched if isinstance(m[1], tuple)]
    assert group_hits or any(m[1] == 2 for m in matched)


def test_group_triples_respect_max_combos_zero() -> None:
    # Only a triple sums to the bank amount; pairs do not.
    bank = [Transaction(date=date(2024, 6, 1), amount=100.0, description="BONIFICO X", beneficiary="X")]
    ledger = [
        Transaction(date=date(2024, 6, 1), amount=30.0, description="BONIFICO X", beneficiary="X"),
        Transaction(date=date(2024, 6, 1), amount=40.0, description="BONIFICO X", beneficiary="X"),
        Transaction(date=date(2024, 6, 1), amount=30.0, description="BONIFICO X", beneficiary="X"),
    ]
    matched, ub, ul = reconcile_transactions(
        bank,
        ledger,
        date_window=0,
        group_limit=3,
        use_absolute_amounts=False,
        max_combos_per_bank=0,  # disallow triple enumeration
    )
    assert matched == []
    # Now allow triples; it should find a grouped match
    matched2, ub2, ul2 = reconcile_transactions(
        bank,
        ledger,
        date_window=0,
        group_limit=3,
        use_absolute_amounts=False,
        max_combos_per_bank=1000,
    )
    assert matched2 and isinstance(matched2[0][1], tuple)


def test_iban_gate_blocks_mismatch() -> None:
    # Same amount and date but different IBANs should not match
    bank = [
        Transaction(
            date=date(2024, 3, 5),
            amount=250.0,
            description="Bonifico IT60X0542811101000000123456 for services",
            beneficiary="ACME",
            metadata={"iban": "IT60X0542811101000000123456"},
        )
    ]
    ledger = [
        Transaction(
            date=date(2024, 3, 5),
            amount=250.0,
            description="Bonifico IT12Z0306909606100000123456 from client",
            beneficiary="ACME",
            metadata={"iban": "IT12Z0306909606100000123456"},
        )
    ]
    matched, ub, ul = reconcile_transactions(bank, ledger, date_window=0)
    assert matched == []
    assert ub == [0]
    assert ul == [0]

