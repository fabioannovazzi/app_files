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


def test_reconcile_transactions_requires_same_sign_by_default() -> None:
    """Opposite-signed amounts should not match unless absolute mode is enabled."""
    bank = [Transaction(date=date(2024, 1, 1), amount=-100.0, description="a", beneficiary="Same Co")]
    ledger = [Transaction(date=date(2024, 1, 1), amount=100.0, description="a", beneficiary="Same Co")]

    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(bank, ledger)

    assert matched == []
    assert unmatched_bank == [0]
    assert unmatched_ledger == [0]


def test_reconcile_transactions_matches_on_absolute_amounts() -> None:
    """Enabling absolute amounts allows opposite-signed entries to match."""
    bank = [Transaction(date=date(2024, 1, 1), amount=-100.0, description="a", beneficiary="Same Co")]
    ledger = [Transaction(date=date(2024, 1, 1), amount=100.0, description="a", beneficiary="Same Co")]

    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank,
        ledger,
        use_absolute_amounts=True,
    )

    assert matched and matched[0][:2] == (0, 0)
    assert unmatched_bank == []
    assert unmatched_ledger == []


def test_reconcile_transactions_group_match_with_absolute_amounts() -> None:
    """Group matching also respects absolute amount comparison."""
    bank = [Transaction(date=date(2024, 1, 1), amount=-150.0, description="a", beneficiary="Same Co")]
    ledger = [
        Transaction(date=date(2024, 1, 1), amount=100.0, description="a", beneficiary="Same Co"),
        Transaction(date=date(2024, 1, 1), amount=50.0, description="a", beneficiary="Same Co"),
    ]

    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank,
        ledger,
        group_limit=2,
        use_absolute_amounts=True,
    )

    assert matched == [(0, (0, 1), "group")]
    assert unmatched_bank == []
    assert unmatched_ledger == []
