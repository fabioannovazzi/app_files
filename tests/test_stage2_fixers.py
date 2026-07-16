from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (SRC, ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


# Provide lightweight stubs for modules imported during pipeline load
utils_mod = types.ModuleType("modules.utilities.utils")
utils_mod.get_schema_and_column_names = (
    lambda df: (getattr(df, "columns", []), getattr(df, "schema", {}))
)
utils_mod.get_row_count = lambda df: 0
utils_mod.ensure_polars_df = lambda df: df
utils_mod.ensure_lazyframe = lambda df: df
utils_mod.get_column_sum = lambda obj, column: 0.0
sys.modules.setdefault("modules.utilities.utils", utils_mod)

config_mod = types.ModuleType("modules.utilities.config")
config_mod.get_config_params = lambda: {}
config_mod.get_naming_params = lambda: {}
sys.modules.setdefault("modules.utilities.config", config_mod)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mod_models = _load_module("cs_models_stage2", SRC / "check_statements" / "models.py")
mod_pipeline = _load_module("cs_pipeline_stage2", SRC / "check_statements" / "reconcile_pipeline.py")

Transaction = mod_models.Transaction
_stage2_fixers_and_routing = mod_pipeline._stage2_fixers_and_routing


def _tx(amount: float, desc: str) -> Transaction:
    return Transaction(date=date(2024, 1, 1), amount=amount, description=desc, metadata={})


def test_stage2_fixers_accept_small_fee_batch() -> None:
    bank = [_tx(-1.0, "commissione bancaria") for _ in range(10)]
    ledger: list[Transaction] = []
    matched_pairs: list[tuple[int, int | None, str]] = []
    matched_bank_indices: set[int] = set()
    matched_ledger_indices: set[int] = set()

    counters = _stage2_fixers_and_routing(
        bank,
        ledger,
        [[] for _ in bank],
        matched_pairs,
        matched_bank_indices,
        matched_ledger_indices,
        within_tolerance=lambda _bank, _ledger: True,
        within_date=lambda _bank, _ledger: True,
    )

    assert counters["fix_fee"] == 10
    assert len(matched_pairs) == 10


def test_stage2_fixers_gated_when_batch_is_massive() -> None:
    bank = [_tx(-1.0, "commissione bancaria") for _ in range(300)]
    ledger: list[Transaction] = []
    matched_pairs: list[tuple[int, int | None, str]] = []
    matched_bank_indices: set[int] = set()
    matched_ledger_indices: set[int] = set()

    counters = _stage2_fixers_and_routing(
        bank,
        ledger,
        [[] for _ in bank],
        matched_pairs,
        matched_bank_indices,
        matched_ledger_indices,
        within_tolerance=lambda _bank, _ledger: True,
        within_date=lambda _bank, _ledger: True,
    )

    assert counters["fix_fee"] == 0
    assert not matched_pairs
