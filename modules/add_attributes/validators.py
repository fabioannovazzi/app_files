from __future__ import annotations

"""Utility validators for the add_attributes module."""

__all__ = ["is_valid_product_name"]

_INVALID_NAMES = {"n/a", "na"}


def is_valid_product_name(name: str) -> bool:
    """Return ``True`` when ``name`` is a meaningful product identifier.

    Blank strings or case-insensitive placeholders like ``"N/A"`` are treated as
    invalid.
    """
    if not isinstance(name, str):
        return False
    cleaned = name.strip()
    if not cleaned:
        return False
    return cleaned.lower() not in _INVALID_NAMES
