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


def test_never_match_on_amount_and_date_alone() -> None:
    """Amount+date alone must not produce an auto-match (Jack vs. Caritas guard)."""
    bank = [Transaction(date=date(2024, 1, 1), amount=170.0, description="generic movement")]
    ledger = [
        Transaction(date=date(2024, 1, 1), amount=170.0, description="bonifico a favore di JACK"),
        Transaction(date=date(2024, 1, 1), amount=170.0, description="bonifico a favore di CARITAS"),
    ]
    matched, unmatched_bank, unmatched_ledger = reconcile_transactions(
        bank, ledger, use_absolute_amounts=False
    )
    # With no hard ID, IBAN, or beneficiary on the bank side, this is ambiguous
    assert matched == []
    assert unmatched_bank == [0]
    assert unmatched_ledger == [0, 1]


def test_jack_vs_caritas_prefers_true_counterparty() -> None:
    bank = [
        Transaction(date=date(2024, 1, 10), amount=170.0, description="bonifico a favore di Jack the Ripper", beneficiary="jack the ripper"),
    ]
    ledger = [
        Transaction(date=date(2024, 1, 10), amount=170.0, description="bonifico a favore di CARITAS", beneficiary="caritas"),
        Transaction(date=date(2024, 1, 10), amount=170.0, description="bonifico a favore di Jack the Ripper", beneficiary="jack the ripper"),
    ]
    matched, ub, ul = reconcile_transactions(bank, ledger, date_window=0)
    assert matched and matched[0][1] == 1
    assert ub == []


def test_jack_vs_caritas_no_autos_when_only_wrong_counterparty_exists() -> None:
    bank = [
        Transaction(date=date(2024, 1, 10), amount=170.0, description="bonifico a favore di Jack the Ripper", beneficiary="jack the ripper"),
    ]
    ledger = [
        Transaction(date=date(2024, 1, 10), amount=170.0, description="bonifico a favore di CARITAS", beneficiary="caritas"),
    ]
    matched, ub, ul = reconcile_transactions(bank, ledger, date_window=0)
    assert matched == []
    assert ub == [0]
