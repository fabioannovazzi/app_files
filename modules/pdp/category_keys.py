from __future__ import annotations

import re
from collections.abc import Iterable


def normalize_category_key(value: object) -> str:
    """Return a lowercase slug-style category key."""

    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def canonical_category_key(retailer: str, category_key: object) -> str:
    """Return the canonical category key for a retailer/category pair."""

    _ = retailer
    normalized_key = normalize_category_key(category_key)
    return normalized_key


def canonical_category_keys(
    retailer: str,
    category_keys: Iterable[object] | None,
) -> set[str] | None:
    """Return canonical category filters, preserving ``None`` for all categories."""

    if not category_keys:
        return None
    normalized = {
        canonical_category_key(retailer, category_key)
        for category_key in category_keys
        if normalize_category_key(category_key)
    }
    return normalized or None


def profile_category_key(retailer: str, profile_name: str) -> str:
    """Return the canonical category key implied by a retailer PDP profile."""

    retailer_key = normalize_category_key(retailer)
    profile_key = str(profile_name or "").strip()
    prefix = f"{retailer_key}_"
    suffix = (
        profile_key[len(prefix) :]
        if profile_key.lower().startswith(prefix)
        else profile_key
    )
    return canonical_category_key(retailer_key, suffix)


__all__ = [
    "canonical_category_key",
    "canonical_category_keys",
    "normalize_category_key",
    "profile_category_key",
]
