from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

__all__ = [
    "LOREALPARIS_BASE_URL",
    "LOREALPARIS_BRAND_NAME",
    "LOREALPARIS_KNOWN_FAMILY_SLUGS",
    "LOREALPARIS_RETAILER",
    "lorealparis_category_from_url",
    "lorealparis_category_path",
    "lorealparis_family_slug_from_slug",
    "lorealparis_family_url",
    "lorealparis_parent_id_from_url",
]

LOREALPARIS_BASE_URL = "https://www.lorealparisusa.com"
LOREALPARIS_BRAND_NAME = "L'Oreal Paris"
LOREALPARIS_RETAILER = "lorealparis"

LOREALPARIS_KNOWN_FAMILY_SLUGS = frozenset(
    {
        "infallible-fresh-wear-blush",
        "lumi-le-liquid-blush",
        "true-match-blush",
        "lumi-bronze-le-stick-soleil",
        "infallible-up-to-24h-fresh-wear-soft-matte-bronzer",
    }
)

_PDP_PATH_RE = re.compile(
    r"/makeup/face/(?P<category>blush|bronzer)/(?P<slug>[a-z0-9-]+)",
    re.IGNORECASE,
)


def lorealparis_family_slug_from_slug(slug: str) -> str:
    """Return the canonical family slug for a L'Oreal Paris product URL slug."""

    normalized = str(slug or "").strip().strip("/").lower()
    if not normalized:
        return ""
    for family_slug in sorted(LOREALPARIS_KNOWN_FAMILY_SLUGS, key=len, reverse=True):
        if normalized == family_slug or normalized.startswith(f"{family_slug}-"):
            return family_slug
    return normalized


def lorealparis_parent_id_from_url(url: str) -> str | None:
    """Extract a stable parent product id from a L'Oreal Paris PDP URL."""

    parsed = urlparse(str(url or ""))
    match = _PDP_PATH_RE.search(parsed.path)
    if not match:
        return None
    parent_id = lorealparis_family_slug_from_slug(match.group("slug"))
    return parent_id or None


def lorealparis_category_from_url(url: str) -> str | None:
    """Extract the face category key from a L'Oreal Paris category or PDP URL."""

    parsed = urlparse(str(url or ""))
    match = _PDP_PATH_RE.search(parsed.path)
    if match:
        return match.group("category").lower()
    parts = [part for part in parsed.path.lower().split("/") if part]
    if len(parts) >= 3 and parts[:3] == ["makeup", "face", "blush"]:
        return "blush"
    if len(parts) >= 3 and parts[:3] == ["makeup", "face", "bronzer"]:
        return "bronzer"
    return None


def lorealparis_family_url(category_key: str, family_slug: str) -> str:
    """Build the canonical family PDP URL."""

    category = str(category_key or "").strip().lower()
    slug = lorealparis_family_slug_from_slug(family_slug)
    return urljoin(
        LOREALPARIS_BASE_URL,
        f"/makeup/face/{category}/{slug}",
    )


def lorealparis_category_path(category_key: str | None) -> tuple[str, ...]:
    """Return the normalized category path stored on parsed parent products."""

    normalized = str(category_key or "").strip().lower()
    if normalized == "blush":
        return ("Makeup", "Face Makeup", "Blush")
    if normalized == "bronzer":
        return ("Makeup", "Face Makeup", "Bronzer")
    return ("Makeup", "Face Makeup")
