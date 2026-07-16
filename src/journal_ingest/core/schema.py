from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(slots=True)
class JournalLine:
    """Canonical flat representation of a journal detail line."""

    entry_date: date
    entry_label: str
    unit: str
    location: str
    line_no: str
    account_code: str
    account_desc: str
    memo: str
    debit: Optional[float]
    credit: Optional[float]
    src_page: str
    beneficiary: Optional[str] = None
