from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from .errors import ValidationError


def validate_double_entry(lines: Iterable[Mapping[str, float]]) -> None:
    """Ensure per-entry debit and credit totals balance."""
    totals: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"debit": 0.0, "credit": 0.0}
    )
    for line in lines:
        key = (str(line.get("entry_date")), str(line.get("entry_label")))
        totals[key]["debit"] += float(line.get("debit") or 0.0)
        totals[key]["credit"] += float(line.get("credit") or 0.0)

    for key, sums in totals.items():
        if round(sums["debit"] - sums["credit"], 2) != 0:
            raise ValidationError(f"Double-entry imbalance for {key}")
