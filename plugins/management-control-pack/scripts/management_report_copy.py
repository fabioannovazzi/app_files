"""Localize fixed report labels while preserving source and authored text."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

__all__ = ["localize_number", "report_label", "report_language"]

LANGUAGES = frozenset({"en", "it", "fr", "de", "es"})


def report_language(value: object) -> str:
    """Resolve a supported language without silently replacing it with English."""
    language = value.strip().lower().split("-", 1)[0] if isinstance(value, str) else ""
    if language not in LANGUAGES:
        raise ValueError("Report language must be en, it, fr, de or es.")
    return language


@lru_cache(maxsize=1)
def _copy() -> dict[str, dict[str, str]]:
    path = Path(__file__).resolve().parent.parent / "assets/management-report-copy.json"
    return json.loads(path.read_text(encoding="utf-8"))


def report_label(value: str, language: str) -> str:
    """Translate only registered display copy, never unknown source content."""
    return _copy()[report_language(language)].get(value, value)


def localize_number(text: str, language: str) -> str:
    """Format an already calculated numeric string without changing its value."""
    if language == "fr":
        return text.translate(str.maketrans({",": "\u202f", ".": ","}))
    if language in {"it", "de", "es"}:
        return text.translate(str.maketrans({",": ".", ".": ","}))
    return text
