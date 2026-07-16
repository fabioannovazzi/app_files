from __future__ import annotations

import importlib
import sys
import types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _ensure_package(name: str, path: Path) -> None:
    if name in sys.modules:
        return
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = pkg


_ensure_package("src", SRC)
_ensure_package("src.check_statements", SRC / "check_statements")

models_mod = importlib.import_module("src.check_statements.models")
pipeline_mod = importlib.import_module("src.check_statements.reconcile_pipeline")
beneficiary_mod = importlib.import_module("src.check_statements.stages.beneficiary")

Transaction = models_mod.Transaction
staged_reconcile = pipeline_mod.staged_reconcile
_stage6_beneficiary_invoice = beneficiary_mod._stage6_beneficiary_invoice
_stage8_reference = importlib.import_module(
    "src.check_statements.stages.iban_reference"
)._stage8_reference


def _txn(amount: float) -> Transaction:
    return Transaction(
        date=date(2024, 5, 1),
        amount=amount,
        description="sample",
        reference_ids=[],
        metadata={"op_type": "BONIFICO"},
    )


def test_stage1_candidate_graph_flag_keeps_legacy_results() -> None:
    bank = [_txn(-100.0), _txn(-200.0)]
    ledger = [_txn(-100.0), _txn(-200.0)]

    legacy_matches, _, _, legacy_counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.5,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=1,
        dense_day=False,
    )

    flagged_matches, _, _, flagged_counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.5,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=1,
        dense_day=False,
    )

    assert legacy_matches == flagged_matches
    assert legacy_counts["stage1_assign"] == flagged_counts["stage1_assign"] == 2
    assert legacy_counts["stage1_candidate_edges"] == 2
    assert flagged_counts["stage1_candidate_edges"] == 2


def test_stage3_with_graph_matches_legacy_behaviour() -> None:
    bank = [_txn(-50.0), _txn(-75.0)]
    bank[0].metadata["op_type"] = "ATM"
    bank[1].metadata["op_type"] = "ATM"
    ledger = [_txn(-50.0), _txn(-75.0)]
    ledger[0].metadata["op_type"] = "ATM"
    ledger[1].metadata["op_type"] = "ATM"

    legacy_matches, _, _, legacy_counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.5,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=3,
        dense_day=False,
    )

    flagged_matches, _, _, flagged_counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.5,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=3,
        dense_day=False,
    )

    assert legacy_matches == flagged_matches
    assert legacy_counts["stage3_cash"] == flagged_counts["stage3_cash"]


def test_preview_keys_absent_when_flag_enabled() -> None:
    bank = [_txn(-60.0), _txn(-80.0)]
    bank[0].metadata["op_type"] = "ATM"
    bank[1].metadata["op_type"] = "ATM"
    ledger = [_txn(-60.0), _txn(-80.0)]
    ledger[0].metadata["op_type"] = "ATM"
    ledger[1].metadata["op_type"] = "ATM"

    _, _, _, flagged_counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.5,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=3,
        dense_day=False,
    )


def test_stage5_with_graph_matches_legacy_behaviour() -> None:
    bank = [
        _txn(-150.0),
        _txn(-200.0),
    ]
    bank[0].description = "Payroll May"
    bank[1].metadata["op_type"] = "F24"
    ledger = [
        _txn(-150.0),
        _txn(-200.0),
    ]
    ledger[0].metadata["account_desc"] = "PAYROLL COSTS"
    ledger[1].metadata["tax_flag"] = True

    flagged_matches, _, _, flagged_counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.5,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=5,
        dense_day=False,
    )

    # Under the single-graph mode, salary/tax gate is still computed
    # and exposed in counters
    assert flagged_counts["stage5_salary_gate"] >= 1
    assert "stage5_payroll_hits" in flagged_counts
    assert "stage5_tax_hits" in flagged_counts


def test_stage6_with_graph_matches_legacy_behaviour() -> None:
    bank = [
        _txn(-90.0),
        _txn(-120.0),
    ]
    bank[0].beneficiary = "ACME LTD"
    bank[1].beneficiary = "BETA SPA"
    ledger = [
        _txn(-90.0),
        _txn(-120.0),
    ]
    ledger[0].beneficiary = "ACME LTD"
    ledger[1].beneficiary = "BETA SPA"

    flagged_matches, _, _, flagged_counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.5,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=6,
        dense_day=False,
    )
    assert "stage6_beneficiary_hits" in flagged_counts


def test_stage7_with_graph_matches_legacy_behaviour() -> None:
    bank = [_txn(-70.0), _txn(-85.0)]
    bank[0].metadata["iban"] = "IT00A"
    bank[1].metadata["iban"] = "IT00B"
    ledger = [_txn(-70.0), _txn(-85.0)]
    ledger[0].metadata["iban"] = "IT00A"
    ledger[1].metadata["iban"] = "IT00B"

    flagged_matches, _, _, flagged_counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.5,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=7,
        dense_day=False,
    )
    assert flagged_counts["stage7_iban"] == 2


def test_stage8_with_graph_matches_legacy_behaviour() -> None:
    bank = [_txn(-95.0), _txn(-110.0)]
    ledger = [_txn(-95.0), _txn(-110.0)]
    bank[0].reference_ids = ["INV-100"]
    bank[1].reference_ids = ["INV-200"]
    ledger[0].reference_ids = ["INV-100"]
    ledger[1].reference_ids = ["INV-200"]

    flagged_matches, _, _, flagged_counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.5,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=8,
        dense_day=False,
    )
    assert flagged_counts["stage8_reference"] == 2


def test_candidate_graph_prefers_iban_match() -> None:
    bank = [
        Transaction(
            date=date(2024, 5, 10),
            amount=-170.0,
            description="bonifico stipendio",
            metadata={"op_type": "BONIFICO", "iban": "IT60X0542811101000000123456"},
        )
    ]
    ledger = [
        Transaction(
            date=date(2024, 5, 10),
            amount=-170.0,
            description="bonifico generico",
            metadata={"op_type": "BONIFICO", "iban": "IT60X0542811101000000999999"},
        ),
        Transaction(
            date=date(2024, 5, 10),
            amount=-170.0,
            description="bonifico stipendio",
            metadata={"op_type": "BONIFICO", "iban": "IT60X0542811101000000123456"},
        ),
    ]

    flagged_matches, _, _, flagged_counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.5,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=8,
        dense_day=False,
    )
    assert flagged_matches == [(0, 1, "iban")]
    stage_flags = flagged_counts.get("stage_flags", {})
    assert stage_flags.get(0, {}).get("s7") is True
    assert flagged_counts["stage1_candidate_edges"] == 2


def test_stage6_uses_extra_desc_for_beneficiary_match() -> None:
    bank = [
        Transaction(
            date=date(2024, 1, 2),
            amount=-3746.55,
            description="Addebito SDD Example Leasing",
            beneficiary="Example Leasing S.P.A.",
        )
    ]
    ledger = [
        Transaction(
            date=date(2024, 1, 2),
            amount=-3746.55,
            description="PAGATA FATTURA",
            metadata={"extra_desc": "N.911 del 02012024 EXAMPLE LEASING S.P.A."},
        )
    ]
    candidates = [[0]]
    matched_pairs: list[tuple[int, int | None, str]] = []
    matched_bank: set[int] = set()
    matched_ledger: set[int] = set()

    def tol(a, b):
        return abs(a.amount - b.amount) < 0.01

    def within(a, b):
        return abs((a.date - b.date).days) <= 0

    result = _stage6_beneficiary_invoice(
        bank,
        ledger,
        candidates,
        matched_pairs,
        matched_bank,
        matched_ledger,
        within_tolerance=tol,
        within_date=within,
        beneficiary_similarity_fn=lambda a, b: (
            1.0 if (a and b and (a in b or b in a)) else 0.0
        ),
    )
    assert result["stage6_beneficiary"] == 1
    assert matched_pairs == [(0, 0, "beneficiary")]


def test_stage2_fix_fee_matches_fee_ledger() -> None:
    bank = [
        Transaction(
            date=date(2024, 3, 5),
            amount=-5.0,
            description="Commissioni bancarie",
        )
    ]
    ledger = [
        Transaction(
            date=date(2024, 3, 5),
            amount=-5.0,
            description="Commissioni bancarie",
            metadata={"account_desc": "Commissioni bancarie"},
        ),
        Transaction(
            date=date(2024, 3, 5),
            amount=-5.0,
            description="Altre spese",
            metadata={"account_desc": "Spese generiche"},
        ),
    ]

    matches, _, _, counts = staged_reconcile(
        bank,
        ledger,
        tolerance=0.01,
        date_window=0,
        use_absolute_amounts=False,
        up_to_stage=2,
        dense_day=False,
    )

    assert matches == [(0, 0, "fix_fee")]
    assert counts["stage2_fix_fee"] == 1


def test_stage8_uses_extra_desc_for_reference_match() -> None:
    bank = [
        Transaction(
            date=date(2024, 1, 2),
            amount=-3746.55,
            description="Pagamento fattura",
            metadata={"extra_desc": "N.911 del 02012024 EXAMPLE LEASING S.P.A."},
        )
    ]
    ledger = [
        Transaction(
            date=date(2024, 1, 2),
            amount=-3746.55,
            description="PAGATA FATTURA",
            metadata={"extra_desc": "N.911 del 02012024 Example Leasing S.p.A."},
        )
    ]
    matched_pairs: list[tuple[int, int | None, str]] = []
    matched_bank: set[int] = set()
    matched_ledger: set[int] = set()

    def tol(a, b):
        return abs(a.amount - b.amount) < 0.01

    def within(a, b):
        return abs((a.date - b.date).days) <= 0

    result = _stage8_reference(
        bank,
        ledger,
        matched_pairs,
        matched_bank,
        matched_ledger,
        within_tolerance=tol,
        within_date=within,
    )
    assert result["stage8_reference"] == 1
    assert matched_pairs == [(0, 0, "reference")]
