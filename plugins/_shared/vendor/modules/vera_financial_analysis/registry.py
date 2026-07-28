"""Fixed financial due-diligence recipe registry."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

__all__ = [
    "FDD_ENGINE_VERSION",
    "FDD_OUTPUT_ROLES",
    "FDD_PACK_RECIPES",
]

FDD_ENGINE_VERSION = "1.1.0"
FDD_OUTPUT_ROLES = (
    "fdd_line_items",
    "fdd_metrics",
    "fdd_result",
    "reconciliation",
)
FDD_PACK_RECIPES: Mapping[str, str] = MappingProxyType(
    {
        "quality_of_earnings": "adjusted_ebitda_from_reviewed_adjustments.v1",
        "net_debt": "net_debt_from_reviewed_classification.v1",
        "normalized_working_capital": (
            "normalized_working_capital_from_reviewed_policy.v1"
        ),
        "capex": "capex_from_reviewed_classification.v1",
        "deal_bridges": "deal_bridges_from_reviewed_inputs.v1",
    }
)
