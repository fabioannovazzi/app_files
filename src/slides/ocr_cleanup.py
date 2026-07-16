from __future__ import annotations

import re

__all__ = ["clean_ocr_items", "clean_ocr_text"]

_SMART_APOSTROPHE_PATTERN = re.compile(r"[\u2018\u2019\u2032\u00b4`]")
_UPPERCASE_TOKEN_TRAILING_LOWERCASE_PATTERN = re.compile(
    r"\b([A-ZÀ-ÖØ-Þ]{2,})([a-zà-öø-ÿ])\b"
)
_LEADING_I_APOSTROPHE_PATTERN = re.compile(r"\bI'(?=[A-ZÀ-ÖØ-Þ])")
_POTENZA_COMPARATOR_PATTERN = re.compile(r"\b([Pp]otenza)\s+a\s+(?=[≤<>])")
_SPACE_BEFORE_PUNCTUATION_PATTERN = re.compile(r"\s+([,.;:!?])")
_MISSING_SPACE_AFTER_PUNCTUATION_PATTERN = re.compile(
    r"([,.;:!?])(?=[A-Za-zÀ-ÖØ-öø-ÿ])"
)
_LOWER_TO_UPPER_BOUNDARY_PATTERN = re.compile(r"(?<=[a-zà-öø-ÿ])(?=[A-ZÀ-ÖØ-Þ])")
_LOWER_TO_DIGIT_BOUNDARY_PATTERN = re.compile(r"(?<=[a-zà-öø-ÿ])(?=\d)")
_DIGIT_TO_KMH_BOUNDARY_PATTERN = re.compile(r"(?<=\d)(?=km/h\b)", re.IGNORECASE)
_WATT_UNIT_PATTERN = re.compile(r"(?<=\d)\s*[wW]\b")
_MULTISPACE_PATTERN = re.compile(r"[ \t]{2,}")


def _clean_ocr_line(text: str) -> str:
    cleaned = str(text or "").replace("\xa0", " ")
    cleaned = _SMART_APOSTROPHE_PATTERN.sub("'", cleaned)
    cleaned = _LEADING_I_APOSTROPHE_PATTERN.sub("l'", cleaned)
    cleaned = _POTENZA_COMPARATOR_PATTERN.sub(r"\1 ", cleaned)
    cleaned = _SPACE_BEFORE_PUNCTUATION_PATTERN.sub(r"\1", cleaned)
    cleaned = _MISSING_SPACE_AFTER_PUNCTUATION_PATTERN.sub(r"\1 ", cleaned)
    cleaned = _LOWER_TO_UPPER_BOUNDARY_PATTERN.sub(" ", cleaned)
    cleaned = _LOWER_TO_DIGIT_BOUNDARY_PATTERN.sub(" ", cleaned)
    cleaned = _DIGIT_TO_KMH_BOUNDARY_PATTERN.sub(" ", cleaned)
    cleaned = _UPPERCASE_TOKEN_TRAILING_LOWERCASE_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2).upper()}",
        cleaned,
    )
    cleaned = _WATT_UNIT_PATTERN.sub("W", cleaned)
    cleaned = _MULTISPACE_PATTERN.sub(" ", cleaned)
    return cleaned.strip()


def clean_ocr_text(text: str) -> str:
    """Apply narrow deterministic OCR cleanup while preserving line breaks."""

    if not str(text or "").strip():
        return ""
    cleaned_lines = [
        cleaned
        for cleaned in (_clean_ocr_line(segment) for segment in str(text).splitlines())
        if cleaned
    ]
    return "\n".join(cleaned_lines).strip()


def clean_ocr_items(items: list[str]) -> list[str]:
    """Clean and deduplicate OCR text items while preserving order."""

    cleaned_items: list[str] = []
    seen: set[str] = set()
    for raw_item in items:
        cleaned = clean_ocr_text(str(raw_item or ""))
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_items.append(cleaned)
    return cleaned_items
