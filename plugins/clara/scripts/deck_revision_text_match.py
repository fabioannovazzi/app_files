"""Conservative text matching for deck-revision patch targets."""

from __future__ import annotations

import re
import unicodedata

__all__ = ["normalize_patch_target_text", "target_text_matches"]

_WHITESPACE_RE = re.compile(r"\s+")
_ZERO_WIDTH_TRANSLATION = {
    ord("\u200b"): None,
    ord("\u200c"): None,
    ord("\u200d"): None,
    ord("\ufeff"): None,
}


def normalize_patch_target_text(value: str) -> str:
    """Normalize extractor-only text differences without changing meaning."""

    normalized = unicodedata.normalize("NFC", value)
    normalized = normalized.translate(_ZERO_WIDTH_TRANSLATION)
    normalized = normalized.replace("\u00a0", " ")
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def target_text_matches(actual_text: str, expected_text: str) -> bool:
    """Match exact target text, allowing harmless PPTX extractor whitespace drift."""

    actual = str(actual_text or "")
    expected = str(expected_text or "")
    if actual.strip() == expected.strip():
        return True
    return normalize_patch_target_text(actual) == normalize_patch_target_text(expected)
