from __future__ import annotations

from typing import Callable, Dict

from .cash_card import _stage3_cash, _stage4_card
from .payroll_tax import _stage5_category_gate
from .beneficiary import _stage6_beneficiary_invoice
from .iban_reference import _stage7_iban, _stage8_reference


def get_stage_funcs() -> Dict[int, Callable[..., dict]]:
    """Return a mapping of stage number -> implementation function.

    This registry centralizes where each stage is defined so the orchestrator
    can reference a single source-of-truth for the stage entry points.
    """
    return {
        3: _stage3_cash,
        4: _stage4_card,
        5: _stage5_category_gate,
        6: _stage6_beneficiary_invoice,
        7: _stage7_iban,
        8: _stage8_reference,
    }

