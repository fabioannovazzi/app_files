from __future__ import annotations

from typing import Iterable


def normalize_number(value: str, decimal: str = ".", thousands: str = ",") -> float:
    """Normalize a locale-formatted number string to ``float``."""
    cleaned = value.replace(thousands, "").replace(decimal, ".")
    return float(cleaned)


def infer_number(
    value: str, decimal_candidates: Iterable[str], thousands_candidates: Iterable[str]
) -> float:
    """Infer separators from candidates and parse the number."""
    for dec in decimal_candidates:
        for thou in thousands_candidates:
            try:
                return normalize_number(value, decimal=dec, thousands=thou)
            except ValueError:
                continue
    raise ValueError(f"Unable to parse number: {value}")
