from __future__ import annotations

import re

from .profile import FieldNormalizationSpec

SPACE_RE = re.compile(r"\s+")
SYMBOL_DEDUPE_RE = re.compile(r"([^\w\s])\1+")
PACK_COUNT_RE = re.compile(r"\s*\((?:\d+[\s-]*(?:pc|pcs|piece|pieces|pack|packs|set))\)\s*$", re.IGNORECASE)


def _collapse_spaces(text: str) -> str:
    return SPACE_RE.sub(" ", text)


def _dedupe_symbols(text: str) -> str:
    return SYMBOL_DEDUPE_RE.sub(r"\1", text)


def _normalize_number_position(text: str) -> str:
    match = re.match(r"^(?P<num>(?:\d+[A-Za-z]{0,2}|#[0-9A-Za-z]+))\s+(?P<rest>.+)$", text)
    if match:
        rest = match.group("rest").strip()
        num = match.group("num").strip()
        if rest:
            return f"{rest} {num}".strip()
    return text


def _looks_like_shade_token(token: str) -> bool:
    lowered = token.lower()
    if any(keyword in lowered for keyword in ("shade", "color", "colour", "tonal", "tone", "hue")):
        return True
    digits = any(char.isdigit() for char in token)
    if digits and len(token) <= 16:
        return True
    if len(token.split()) <= 3 and token.isupper():
        return True
    return False


def _strip_trailing_shade_tokens(text: str) -> str:
    candidates = [" | ", " - ", " – ", " — ", "|", "-", "–", "—", ":"]
    for separator in candidates:
        if separator in text:
            head, tail = text.rsplit(separator, 1)
            tail_clean = tail.strip()
            if tail_clean and _looks_like_shade_token(tail_clean):
                return head.strip()
    return text


def _strip_pack_counts(text: str) -> str:
    return PACK_COUNT_RE.sub("", text).strip()


def normalize_text(value: str | None, spec: FieldNormalizationSpec) -> str | None:
    if value is None:
        return None

    text = value
    if spec.trim:
        text = text.strip()
    if spec.collapse_spaces:
        text = _collapse_spaces(text)
    if spec.dedupe_symbols:
        text = _dedupe_symbols(text)
    if spec.normalize_number_position:
        text = _normalize_number_position(text)
    if spec.strip_trailing_shade_tokens:
        text = _strip_trailing_shade_tokens(text)
    if spec.strip_pack_counts:
        text = _strip_pack_counts(text)
    return text


__all__ = ["normalize_text"]
