from __future__ import annotations

import re
from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup  # type: ignore[import]

from .models import FilterSurface

__all__ = [
    "extract_cosmoprofbeauty_filter_surfaces",
    "normalize_cosmoprofbeauty_filter_family",
]


_FILTER_FAMILY_ALIASES: dict[str, str] = {
    "brandcustom": "brand",
}
_TRAILING_COUNT_RE = re.compile(r"\s*\(?\d+\)?\s*$")


def extract_cosmoprofbeauty_filter_surfaces(
    *,
    category_url: str,
    html: str,
    category_key: str,
    retailer: str = "cosmoprofbeauty",
    allowed_families: Sequence[str] | None = None,
) -> list[FilterSurface]:
    """Return unique Cosmoprof refinement URLs exposed on a rendered PLP."""

    soup = BeautifulSoup(html, "lxml")
    allowed = (
        {
            normalize_cosmoprofbeauty_filter_family(value)
            for value in allowed_families
            if str(value).strip()
        }
        if allowed_families
        else None
    )
    category_path = urlparse(category_url).path
    discovered: list[FilterSurface] = []
    seen: set[tuple[str, str, str]] = set()

    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        full_url = urljoin(category_url, href)
        if not _looks_like_cosmoprof_filter_url(full_url, category_path):
            continue
        filter_pair = _extract_filter_pair(full_url)
        if filter_pair is None:
            continue
        raw_family, raw_value = filter_pair
        filter_family = normalize_cosmoprofbeauty_filter_family(raw_family)
        if not filter_family:
            continue
        if allowed is not None and filter_family not in allowed:
            continue
        filter_value = _clean_text(raw_value)
        filter_label = _clean_text(anchor.get_text(" ", strip=True)) or filter_value
        if not filter_value or not filter_label:
            continue
        filter_url = _canonicalize_filter_url(full_url)
        dedupe_key = (filter_family, filter_value.casefold(), filter_url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        discovered.append(
            FilterSurface(
                retailer=retailer,
                category_key=category_key,
                filter_family=filter_family,
                filter_value=filter_value,
                filter_url=filter_url,
                filter_label=filter_label,
            )
        )

    return sorted(
        discovered,
        key=lambda item: (item.filter_family, item.filter_value, item.filter_url),
    )


def normalize_cosmoprofbeauty_filter_family(value: str) -> str:
    """Normalize one Cosmoprof filter family to a stable lowercase label."""

    cleaned = " ".join(str(value or "").strip().lower().split())
    cleaned = cleaned.replace("_", " ")
    cleaned = re.sub(r"[^a-z0-9\\s-]+", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    return _FILTER_FAMILY_ALIASES.get(cleaned, cleaned)


def _looks_like_cosmoprof_filter_url(url: str, category_path: str) -> bool:
    parsed = urlparse(url)
    if "cosmoprofbeauty.com" not in parsed.netloc.lower():
        return False
    if parsed.path != category_path:
        return False
    if parsed.path.lower().endswith(".html"):
        return False
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    has_prefn = any(key.lower().startswith("prefn") for key, _ in query_items)
    has_prefv = any(key.lower().startswith("prefv") for key, _ in query_items)
    return has_prefn and has_prefv


def _extract_filter_pair(url: str) -> tuple[str, str] | None:
    query_items = parse_qsl(urlparse(url).query, keep_blank_values=True)
    family_by_index: dict[str, str] = {}
    value_by_index: dict[str, str] = {}

    for key, value in query_items:
        lowered = key.lower()
        if lowered.startswith("prefn"):
            family_by_index[lowered[5:]] = value
        elif lowered.startswith("prefv"):
            value_by_index[lowered[5:]] = value

    shared_indices = [
        index
        for index in family_by_index
        if index in value_by_index
        and str(family_by_index[index]).strip()
        and str(value_by_index[index]).strip()
    ]
    if not shared_indices:
        return None
    selected_index = max(shared_indices, key=_pref_index_sort_key)
    return family_by_index[selected_index], value_by_index[selected_index]


def _pref_index_sort_key(value: str) -> tuple[int, str]:
    cleaned = str(value or "").strip()
    if cleaned.isdigit():
        return (int(cleaned), cleaned)
    return (-1, cleaned)


def _clean_text(value: str) -> str:
    cleaned = " ".join(str(value or "").split())
    return _TRAILING_COUNT_RE.sub("", cleaned).strip()


def _canonicalize_filter_url(url: str) -> str:
    parsed = urlparse(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if str(value).strip()
        and (
            key.lower().startswith("prefn")
            or key.lower().startswith("prefv")
            or key in {"cgid", "issearchresultfilter", "srule"}
        )
    ]
    return urlunparse(
        parsed._replace(
            query=urlencode(query, doseq=True),
            fragment="",
        )
    )
