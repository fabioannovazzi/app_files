from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

# Ensure top-level packages under src resolve without replacing shared modules.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.check_statements.classify import classify_op
from src.check_statements.models import Transaction
from src.check_statements.stages.cash_card import _stage3_cash, _stage4_card


def _tx(d: date, amount: float, desc: str, meta: dict | None = None) -> Transaction:
    """Helper to build transactions."""
    return Transaction(date=d, amount=amount, description=desc, metadata=meta or {})


def test_cash_and_card_matches_update_ui_counters() -> None:
    bank = [
        _tx(date(2024, 1, 1), -50.0, "prelievo ATM", {"op_type": "ATM"}),
        _tx(date(2024, 1, 2), -20.0, "pagamento carta"),
        _tx(date(2024, 1, 3), 40.0, "versamento ATM", {"op_type": "ATM"}),
    ]
    ledger = [
        _tx(date(2024, 1, 1), -50.0, "prelievo ATM", {"op_type": "ATM"}),
        _tx(date(2024, 1, 1), -50.0, "altro"),  # create ambiguity for Stage 1
        _tx(date(2024, 1, 2), -20.0, "pagamento carta"),
        _tx(date(2024, 1, 2), -20.0, "altro"),  # create ambiguity for Stage 1
        _tx(date(2024, 1, 3), 40.0, "versamento ATM", {"op_type": "ATM"}),
        _tx(date(2024, 1, 3), 40.0, "altro"),
    ]

    bank_candidates = [[] for _ in bank]
    matched_pairs: list[tuple[int, int | None, str]] = []
    matched_bank_indices: set[int] = set()
    matched_ledger_indices: set[int] = set()

    def tol(a: Transaction, b: Transaction) -> bool:
        return abs(a.amount - b.amount) <= 0.01

    def date_ok(a: Transaction, b: Transaction) -> bool:
        return abs((a.date - b.date).days) <= 0

    c_cash = _stage3_cash(
        bank,
        ledger,
        bank_candidates,
        matched_pairs,
        matched_bank_indices,
        matched_ledger_indices,
        within_tolerance=tol,
        within_date=date_ok,
    )
    c_card = _stage4_card(
        bank,
        ledger,
        bank_candidates,
        matched_pairs,
        matched_bank_indices,
        matched_ledger_indices,
        within_tolerance=tol,
        within_date=date_ok,
    )

    assert len(c_cash["accepted_indices"]) == 2
    assert len(c_card["accepted_indices"]) == 1


@pytest.mark.parametrize(
    "desc",
    [
        "prelievo contanti bancomat",
        "withdrawal cash atm",
        "versamento sportello",
        "deposito bancomat",
        "prelevamento allo sportello",
        "prelievi bancomat",
        "versamenti sportello",
        "depositi atm",
    ],
)
def test_classify_op_atm_synonyms(desc: str) -> None:
    """ATM classification recognises common withdrawal/deposit synonyms."""
    assert classify_op(desc)


def test_stage3_cash_uses_extra_description_metadata() -> None:
    """Ledger extra description should enable ATM classification for matches."""
    bank = [
        _tx(
            date(2024, 6, 10),
            -800.0,
            "PRELEVAMENTO ALLO SPORTELLO CON APPLICAZIONE DI 2,50 EURO DI COMMISSIONE.",
        )
    ]
    ledger = [
        _tx(
            date(2024, 6, 10),
            -800.0,
            "PRELEVAMENTO DA CONTO",
            {
                "extra_desc": "PRELEVAMENTO ALLO SPORTELLO CON APPLICAZIONE DI 2,50 EURO DI COMMISSIONE."
            },
        )
    ]
    bank_candidates = [[]]
    matched_pairs: list[tuple[int, int | None, str]] = []
    matched_bank_indices: set[int] = set()
    matched_ledger_indices: set[int] = set()

    def tol(a: Transaction, b: Transaction) -> bool:
        return abs(a.amount - b.amount) <= 0.01

    def date_ok(a: Transaction, b: Transaction) -> bool:
        return abs((a.date - b.date).days) <= 0

    c_cash = _stage3_cash(
        bank,
        ledger,
        bank_candidates,
        matched_pairs,
        matched_bank_indices,
        matched_ledger_indices,
        within_tolerance=tol,
        within_date=date_ok,
    )

    assert c_cash["cash"] == 1
    assert matched_pairs and matched_pairs[0][:2] == (0, 0)
    assert 0 in c_cash["accepted_indices"]
