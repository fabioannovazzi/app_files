from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Tuple, Optional


@dataclass
class MatchOptions:
    amount_tolerance_abs: float = 1.0
    date_window_days: int = 7
    use_absolute_amounts: bool = True
    beneficiary_mode: Literal["off", "soft", "hard"] = "soft"
    beneficiary_threshold: float = 0.85
    group_limit: int = 3
    # Grouping guardrails (None preserves legacy behaviour)
    group_candidates_cap: Optional[int] = None
    max_combos_per_bank: Optional[int] = None
    group_time_budget_ms: Optional[int] = None
    fee_mode: Literal["exclude", "match"] = "exclude"
    strictness: Literal["normal", "strict"] = "normal"
    # LLM gating (None preserves current logic)
    llm_enabled: Optional[bool] = None
    llm_auto_threshold_abs: Optional[int] = None
    llm_auto_threshold_pct: Optional[float] = None


@dataclass
class RecoResult:
    matched_pairs: List[Tuple[int, Tuple[int, ...], Dict]]
    unmatched_bank: List[int]
    unmatched_ledger: List[int]
    diagnostics: Dict


__all__ = ["MatchOptions", "RecoResult"]
