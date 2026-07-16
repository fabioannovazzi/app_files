from __future__ import annotations

from collections.abc import Iterable, Sequence
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup  # type: ignore[import]

from .discovery import discover_listing_observations
from .fetcher import HTMLFetcher
from .models import FilterObservation, FilterSurface
from .ulta_taxonomy_bridge import (
    ULTA_CATEGORY_FILTER_FAMILIES,
    ULTA_DEFAULT_ATTRIBUTE_FILTER_FAMILIES,
    mapped_filter_families_for_category,
)


def default_filter_families_for_category(category_key: str) -> tuple[str, ...]:
    """Return the default Ulta filter families for one tracked category."""

    normalized = " ".join(str(category_key or "").strip().lower().split())
    if not normalized:
        return ULTA_DEFAULT_ATTRIBUTE_FILTER_FAMILIES
    return mapped_filter_families_for_category(normalized.replace(" ", "_"))


def extract_ulta_filter_surfaces(
    *,
    category_url: str,
    html: str,
    category_key: str,
    retailer: str = "ulta",
    allowed_families: Sequence[str] | None = None,
) -> list[FilterSurface]:
    """Return unique attribute-like filter URLs exposed on a live Ulta category page."""

    soup = BeautifulSoup(html, "lxml")
    allowed = {
        normalize_filter_family(value)
        for value in (
            allowed_families or default_filter_families_for_category(category_key)
        )
        if str(value).strip()
    }
    discovered: list[FilterSurface] = []
    seen: set[tuple[str, str, str]] = set()

    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if not href or "?" not in href:
            continue
        full_url = urljoin(category_url, href)
        parsed = urlparse(full_url)
        query_items = parse_qsl(parsed.query, keep_blank_values=True)
        filter_pairs = [
            (normalize_filter_family(key), value.strip())
            for key, value in query_items
            if normalize_filter_family(key) in allowed and str(value).strip()
        ]
        if len(filter_pairs) != 1:
            continue
        filter_family, filter_value = filter_pairs[0]
        cleaned_url = _canonicalize_filter_url(full_url, filter_family, filter_value)
        dedupe_key = (filter_family, filter_value, cleaned_url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        label = _clean_filter_label(anchor.get_text(" ", strip=True))
        discovered.append(
            FilterSurface(
                retailer=retailer,
                category_key=category_key,
                filter_family=filter_family,
                filter_value=filter_value,
                filter_url=cleaned_url,
                filter_label=label,
            )
        )

    return sorted(
        discovered,
        key=lambda item: (item.filter_family, item.filter_value, item.filter_url),
    )


def crawl_ulta_filter_observations(
    surfaces: Iterable[FilterSurface],
    *,
    fetcher: HTMLFetcher,
    max_pages: int,
    delay_seconds: float,
    allowed_patterns,
    parent_id_pattern,
    canonical_base_url: str | None,
) -> list[FilterObservation]:
    """Crawl filtered Ulta listing surfaces and return product memberships."""

    observations: list[FilterObservation] = []
    for surface in surfaces:
        listing_rows = discover_listing_observations(
            [surface.filter_url],
            category_key=surface.category_key,
            max_pages=max_pages,
            fetcher=fetcher,
            delay_seconds=delay_seconds,
            allowed_patterns=allowed_patterns,
            retailer=surface.retailer,
            sort_modes=("default",),
            source_surface="filter",
            parent_id_pattern=parent_id_pattern,
            canonical_base_url=canonical_base_url,
        )
        for row in listing_rows:
            observations.append(
                FilterObservation(
                    retailer=surface.retailer,
                    category_key=surface.category_key,
                    filter_family=surface.filter_family,
                    filter_value=surface.filter_value,
                    source_surface="filter",
                    pdp_url=row.pdp_url,
                    parent_product_id=row.parent_product_id,
                    page=row.page,
                    position=row.position,
                    listing_url=row.listing_url,
                )
            )
    return observations


def normalize_filter_family(value: str) -> str:
    """Normalize one Ulta filter-family key to a stable lowercase label."""

    return " ".join(str(value or "").strip().lower().split())


def _canonicalize_filter_url(url: str, filter_family: str, filter_value: str) -> str:
    parsed = urlparse(url)
    allowed_query = [(filter_family, filter_value)]
    return urlunparse(parsed._replace(query=urlencode(allowed_query, doseq=True)))


def _clean_filter_label(text: str) -> str | None:
    cleaned = " ".join(text.split())
    if not cleaned:
        return None
    cleaned = re.sub(r"\s+\d+\s+Products Available\s+\d+$", "", cleaned).strip()
    return cleaned or None


__all__ = [
    "ULTA_CATEGORY_FILTER_FAMILIES",
    "ULTA_DEFAULT_ATTRIBUTE_FILTER_FAMILIES",
    "crawl_ulta_filter_observations",
    "default_filter_families_for_category",
    "extract_ulta_filter_surfaces",
    "normalize_filter_family",
]
