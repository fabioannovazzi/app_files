"""Helpers to filter out non-transaction lines."""

from __future__ import annotations

from typing import Iterable

SUMMARY_KEYWORDS = {
    "it": ["riepilogo", "interessi", "spese", "comunicazione"],
    "de": ["zusammenfassung", "zinsen", "geb\u00fchren", "mitteilung"],
    "fr": ["r\u00e9capitulatif", "int\u00e9r\u00eats", "frais", "communication"],
    "en": ["summary", "interest", "fees", "notice"],
    "es": [
        "resumen",
        "intereses",
        "comisiones",
        "comunicación",
        "comunicacion",
        "aviso",
    ],
}


def is_summary_or_notice(line_text: str, lang: str) -> bool:
    """Return True if text looks like a summary/notice header."""
    text = line_text.lower()
    for key in SUMMARY_KEYWORDS.get(lang, []):
        if key in text:
            return True
    return False


def is_header_footer(y_pos: float, page_height: float) -> bool:
    """Detect if a line falls in header or footer band."""
    band = 0.07 * page_height
    return y_pos < band or y_pos > (page_height - band)


def is_total_or_balance_only(line_text: str) -> bool:
    """Check if line contains only total/balance words without dates."""
    text = line_text.lower().strip()
    keywords = ["total", "saldo", "balance", "sum", "totale"]
    return any(text.startswith(k) for k in keywords)
