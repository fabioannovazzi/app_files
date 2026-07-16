from __future__ import annotations

import re
from typing import Any

__all__ = ["normalize_product_key"]

_WHITESPACE_RE = re.compile(r"\s+")
_DIGIT_LETTER_GAP_RE = re.compile(r"(?:(?<=\d)\s+(?=[a-z])|(?<=[a-z])\s+(?=\d))")


def normalize_product_key(value: Any) -> str:
    """Return a canonical key for product identifiers used in caching.

    The normalizer keeps alphanumeric characters, lowercases them, and
    collapses punctuation/whitespace boundaries so variations like
    ``"Widget-100 mL"`` and ``"widget 100ml"`` map to the same key.
    ``None`` or empty-ish inputs return an empty string so callers can skip
    missing products easily.
    """

    if value is None:
        return ""

    try:
        text = str(value)
    except Exception:
        return ""

    lowered = text.lower()
    if not lowered.strip():
        return ""

    # Replace any non-alphanumeric character with a space so punctuation and
    # separators do not create distinct keys.
    cleaned_chars = [ch if ch.isalnum() else " " for ch in lowered]
    interim = "".join(cleaned_chars)
    collapsed = _WHITESPACE_RE.sub(" ", interim).strip()
    if not collapsed:
        return ""

    # Remove spaces introduced between digits and letters so measurements like
    # "100 mL" and "100ml" collapse to the same representation.
    compact = _DIGIT_LETTER_GAP_RE.sub("", collapsed)
    return compact
