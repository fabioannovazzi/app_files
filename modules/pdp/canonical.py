from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Tuple

__all__ = [
    "normalize_brand",
    "normalize_product_name",
    "compute_canonical_values",
]


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_brand(value: str | None) -> str:
    return _normalize_text(value)


def normalize_product_name(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    # Drop obvious variant suffixes separated by dashes (e.g., "Shade Name")
    for sep in (" - ", " – ", " — "):
        if sep in cleaned:
            candidate, remainder = cleaned.split(sep, 1)
            if remainder and len(remainder.split()) <= 4:
                cleaned = candidate
                break
    return _normalize_text(cleaned)


def compute_canonical_values(brand: str | None, product_name: str | None) -> Tuple[str, str, str]:
    brand_norm = normalize_brand(brand)
    name_norm = normalize_product_name(product_name)
    slug = f"{brand_norm}::{name_norm}".encode("utf-8")
    canonical_id = hashlib.sha1(slug).hexdigest()
    return canonical_id, brand_norm, name_norm
