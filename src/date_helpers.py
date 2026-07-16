"""Helper functions for date calculations."""

from __future__ import annotations

import datetime as dt

__all__ = ["start_of_quarter", "start_of_month"]


def start_of_quarter(d: dt.datetime) -> dt.datetime:
    """Return the first day of the quarter that ``d`` belongs to."""
    quarter_index = (d.month - 1) // 3
    start_month = 3 * quarter_index + 1
    return d.replace(month=start_month, day=1)


def start_of_month(d: dt.datetime) -> dt.datetime:
    """Return the first day of the month that ``d`` belongs to."""
    return d.replace(day=1)
