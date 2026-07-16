from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

import polars as pl
import pytest

# Ensure src and ui packages resolve correctly
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_package(name: str, path: Path) -> None:
    if name in sys.modules:
        return
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = pkg


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive guard
        raise ImportError(f"Cannot load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ensure_package("src", SRC)
_ensure_package("src.check_statements", SRC / "check_statements")
_ensure_package("src.check_statements.stages", SRC / "check_statements" / "stages")

classify_mod = _load_module(
    "src.check_statements.classify", SRC / "check_statements" / "classify.py"
)
models_mod = _load_module(
    "src.check_statements.models", SRC / "check_statements" / "models.py"
)
cash_card_mod = _load_module(
    "src.check_statements.stages.cash_card",
    SRC / "check_statements" / "stages" / "cash_card.py",
)

classify_op = classify_mod.classify_op
Transaction = models_mod.Transaction
_stage3_cash = cash_card_mod._stage3_cash
_stage4_card = cash_card_mod._stage4_card
from modules.check_statements.helpers import (
    build_bank_funnel,
    build_ledger_funnel,
    build_stage_summary_table,
)


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

    counters = {
        "stage1_assign": len(bank),
        "stage3_cash": len(c_cash["accepted_indices"]),
        "stage4_card": len(c_card["accepted_indices"]),
        "stage3_evidence": len(c_cash["accepted_indices"]),
        "stage4_evidence": len(c_card["accepted_indices"]),
        "stage3_cash_indices": c_cash["accepted_indices"],
        "stage4_card_indices": c_card["accepted_indices"],
        "stage3_at_least": len(set(c_cash["accepted_indices"]) | set(c_card["accepted_indices"])),
        "stage4_at_least": len(c_card["accepted_indices"]),
    }

    assert len(counters["stage3_cash_indices"]) == 2
    assert len(counters["stage4_card_indices"]) == 1

    summary = build_stage_summary_table(counters)
    funnel = build_bank_funnel(bank, counters, dropped_rows=0)
    ledger_funnel = build_ledger_funnel(bank, counters)

    assert (
        summary.filter(pl.col("stage") == "3 Cash Withdrawals/Deposits")["accepted"][0]
        == 2
    )
    assert summary.filter(pl.col("stage") == "4 Card Payments")["accepted"][0] == 1
    assert (
        funnel.filter(pl.col("step") == "3 Cash Withdrawals/Deposits")["matched"][0]
        == 3
    )
    assert funnel.filter(pl.col("step") == "4 Card Payments")["matched"][0] == 1
    assert (
        funnel.filter(pl.col("step") == "3 Cash Withdrawals/Deposits")["at_least"][0]
        == 3
    )
    assert funnel.filter(pl.col("step") == "4 Card Payments")["at_least"][0] == 1


def test_bank_funnel_uses_stage_origin_counts_for_sequential_view() -> None:
    bank = [
        _tx(date(2024, 1, 1), 10.0, "row1"),
        _tx(date(2024, 1, 2), 20.0, "row2"),
        _tx(date(2024, 1, 3), 30.0, "row3"),
        _tx(date(2024, 1, 4), 40.0, "row4"),
        _tx(date(2024, 1, 5), 50.0, "row5"),
    ]

    counters = {
        "stage1_assign": 2,
        "stage2_fix_fee": 1,
        "stage3_at_least": 1,
        "stage4_at_least": 0,
        "stage5_at_least": 0,
        "stage6_at_least": 0,
        "stage7_at_least": 0,
        "stage8_at_least": 0,
        "stage_origin_counts": {1: 2, 2: 1, 3: 1},
        "unmatched_bank_after_filter": 1,
    }

    summary = build_stage_summary_table(counters)
    funnel = build_bank_funnel(bank, counters, dropped_rows=0)

    assert summary.filter(pl.col("stage") == "1 Amount and Date Window")["accepted"][0] == 2
    assert summary.filter(pl.col("stage") == "2 Bank Fees and Charges")["accepted"][0] == 1
    assert summary.filter(pl.col("stage") == "3 Cash Withdrawals/Deposits")["accepted"][0] == 1

    stage1_row = funnel.filter(pl.col("step") == "1 Amount and Date Window").row(0)
    stage2_row = funnel.filter(pl.col("step") == "2 Bank Fees and Charges").row(0)
    stage3_row = funnel.filter(pl.col("step") == "3 Cash Withdrawals/Deposits").row(0)
    assert stage1_row == ("1 Amount and Date Window", 4, 2, 2, 2)
    assert stage2_row == ("2 Bank Fees and Charges", 1, 1, 0, None)
    assert stage3_row == ("3 Cash Withdrawals/Deposits", 2, 1, 1, 1)
    assert (
        funnel.filter(pl.col("step") == "Unmatched bank after all stages").height == 0
    )

    ledger_funnel = build_ledger_funnel(bank, counters)
    ledger_stage1 = ledger_funnel.filter(pl.col("step") == "1 Amount and Date Window").row(0)
    ledger_stage2 = ledger_funnel.filter(pl.col("step") == "2 Bank Fees and Charges").row(0)
    assert ledger_stage1 == ("1 Amount and Date Window", 4, 2, 2, 2)
    assert ledger_stage2 == ("2 Bank Fees and Charges", 1, 1, 0, None)


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
            {"extra_desc": "PRELEVAMENTO ALLO SPORTELLO CON APPLICAZIONE DI 2,50 EURO DI COMMISSIONE."},
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
