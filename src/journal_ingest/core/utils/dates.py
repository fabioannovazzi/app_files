from __future__ import annotations

from datetime import date, datetime
from typing import Iterable


def parse_date(value: str, formats: Iterable[str]) -> date:
    """Parse a date string using the provided formats."""
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date: {value}")
