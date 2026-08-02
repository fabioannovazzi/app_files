from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

__all__ = ["FinancialAnalysisScripts", "load_financial_analysis_scripts"]


class FinancialAnalysisScripts(NamedTuple):
    """Exact financial-analysis script modules required by the FDD tests."""

    kernel: ModuleType
    fdd_runner: ModuleType
    pack_runner: ModuleType


_SCRIPT_MODULE_NAMES = (
    "preparation_contract_kernel",
    "validate_case_contracts",
    "prepare_customer_concentration_case",
    "prepare_fdd_case",
    "prepare_monthly_pnl_case",
    "prepare_working_capital_case",
    "run_pack",
)
_MISSING = object()


def load_financial_analysis_scripts(script_root: Path) -> FinancialAnalysisScripts:
    """Load Vera's FDD scripts without leaking their ambiguous module names."""

    original_path = list(sys.path)
    previous_modules = {
        name: sys.modules.get(name, _MISSING) for name in _SCRIPT_MODULE_NAMES
    }
    try:
        sys.path[:] = [
            str(script_root),
            *[p for p in sys.path if p != str(script_root)],
        ]
        for name in _SCRIPT_MODULE_NAMES:
            sys.modules.pop(name, None)
        importlib.invalidate_caches()
        kernel = importlib.import_module("preparation_contract_kernel")
        fdd_runner = importlib.import_module("prepare_fdd_case")
        pack_runner = importlib.import_module("run_pack")
    finally:
        for name in _SCRIPT_MODULE_NAMES:
            sys.modules.pop(name, None)
        for name, module in previous_modules.items():
            if module is not _MISSING:
                sys.modules[name] = module
        sys.path[:] = original_path

    return FinancialAnalysisScripts(
        kernel=kernel,
        fdd_runner=fdd_runner,
        pack_runner=pack_runner,
    )
