from __future__ import annotations

import re
from typing import List, Optional

from .page_classifier import AMOUNT_RE, DATE_RE

SUMMARY_ROW_PREFIXES = [
    r"^total\b",
    r"^totale\b",
    r"^subtotal\b",
    r"^summary\b",
    r"^riepilogo\b",
    r"^récapitulatif\b",
    r"^resumen\b",
    r"^zusammenfassung\b",
]

SUMMARY_PREFIX_RE = [re.compile(pat, re.IGNORECASE) for pat in SUMMARY_ROW_PREFIXES]


def looks_like_summary_row(text: str, lang: str | None) -> bool:
    norm = text.strip().lower()
    if any(pat.search(norm) for pat in SUMMARY_PREFIX_RE):
        if not DATE_RE.search(norm):
            return True
    return False


def has_any_amount(text: str) -> bool:
    return bool(AMOUNT_RE.search(text))


def has_any_date(text: str) -> bool:
    return bool(DATE_RE.search(text))


def filter_rows(rows: List[str], lang_hint: Optional[str] = None) -> List[str]:
    filtered: List[str] = []
    carry_date = False
    for row in rows:
        row_str = row.strip()
        if not row_str:
            continue
        if looks_like_summary_row(row_str, lang_hint):
            continue
        has_date = has_any_date(row_str)
        has_amt = has_any_amount(row_str)
        if not has_amt:
            continue
        if not (has_date or carry_date):
            continue
        filtered.append(row_str)
        carry_date = has_date
    return filtered
