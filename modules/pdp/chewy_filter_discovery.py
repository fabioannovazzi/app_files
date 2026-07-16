from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup  # type: ignore[import]
from bs4.element import Tag  # type: ignore[import]

from .discovery import discover_listing_observations
from .fetcher import HTMLFetcher
from .models import FilterObservation, FilterSurface

__all__ = [
    "CHEWY_DEFAULT_FILTER_FAMILIES",
    "crawl_chewy_filter_observations",
    "extract_chewy_filter_surfaces",
    "normalize_chewy_filter_family",
]


CHEWY_DEFAULT_FILTER_FAMILIES: tuple[str, ...] = (
    "lifestage",
    "food texture",
    "flavor",
    "special diet",
    "health feature",
    "package count",
    "packaging type",
)

_FILTER_FAMILY_ALIASES: dict[str, str] = {
    "life stage": "lifestage",
    "life-stage": "lifestage",
    "texture": "food texture",
    "food textures": "food texture",
    "flavour": "flavor",
    "diet": "special diet",
    "health features": "health feature",
    "health consideration": "health feature",
    "packaging": "package count",
    "package": "package count",
    "count": "package count",
    "package type": "packaging type",
    "package types": "packaging type",
    "packaging types": "packaging type",
}
_TRAILING_COUNT_RE = re.compile(r"\s*\(?[\d,]+\)?\s*$")
_REFINE_TEXT_RE = re.compile(r"refine\s+by\s+([^:]+):\s*([^|]+)", re.IGNORECASE)
_SLUG_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def extract_chewy_filter_surfaces(
    *,
    category_url: str,
    html: str,
    category_key: str,
    retailer: str = "chewy",
    allowed_families: Sequence[str] | None = None,
) -> list[FilterSurface]:
    """Return unique Chewy filter URLs for the requested attribute families."""

    soup = BeautifulSoup(html, "lxml")
    allowed = _expand_allowed_families(
        allowed_families or CHEWY_DEFAULT_FILTER_FAMILIES
    )
    tracked_surfaces = _extract_tracked_facet_surfaces(
        soup=soup,
        category_url=category_url,
        category_key=category_key,
        retailer=retailer,
        allowed=allowed,
    )
    if tracked_surfaces:
        return tracked_surfaces

    return _extract_link_filter_surfaces(
        soup=soup,
        category_url=category_url,
        category_key=category_key,
        retailer=retailer,
        allowed=allowed,
    )


def _extract_tracked_facet_surfaces(
    *,
    soup: BeautifulSoup,
    category_url: str,
    category_key: str,
    retailer: str,
    allowed: set[str],
) -> list[FilterSurface]:
    discovered: list[FilterSurface] = []
    seen: set[tuple[str, str, str]] = set()

    for facet in soup.select(".js-tracked-facet[data-facet-category]"):
        if not isinstance(facet, Tag):
            continue
        raw_family = str(facet.get("data-facet-category") or "").strip()
        filter_family = normalize_chewy_filter_family(raw_family)
        if filter_family not in allowed:
            continue
        group_id = str(facet.get("data-facet-group-id") or "").strip()
        for value_node in facet.select("input[data-facet-id][aria-label]"):
            if not isinstance(value_node, Tag):
                continue
            filter_value = _clean_filter_value(str(value_node.get("aria-label") or ""))
            if not filter_value or _is_non_value_label(filter_value):
                continue
            href = _facet_value_href(value_node)
            filter_url = (
                _canonicalize_filter_url(urljoin(category_url, href))
                if href
                else _synthesize_chewy_facet_url(
                    category_url=category_url,
                    group_id=group_id,
                    facet_id=str(value_node.get("data-facet-id") or "").strip(),
                    filter_value=filter_value,
                )
            )
            if not filter_url or not _looks_like_chewy_filter_url(filter_url):
                continue
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
                    filter_label=filter_value,
                )
            )

    return sorted(
        discovered,
        key=lambda item: (item.filter_family, item.filter_value, item.filter_url),
    )


def _extract_link_filter_surfaces(
    *,
    soup: BeautifulSoup,
    category_url: str,
    category_key: str,
    retailer: str,
    allowed: set[str],
) -> list[FilterSurface]:
    discovered: list[FilterSurface] = []
    seen: set[tuple[str, str, str]] = set()

    current_family: str | None = None
    for node in soup.find_all(["h2", "h3", "h4", "summary", "button", "a"]):
        if not isinstance(node, Tag):
            continue
        node_text = _clean_text(node.get_text(" ", strip=True))
        node_family = _family_from_text(node_text, allowed=allowed)
        if node.name in {"h2", "h3", "h4", "summary"}:
            current_family = node_family
            continue
        if node_family is not None and node.name != "a":
            current_family = node_family

        href = _node_filter_href(node)
        if not href:
            continue

        filter_pair = _extract_family_value_from_text(node_text)
        if filter_pair is None:
            filter_pair = _extract_query_filter_pair(href)
        if filter_pair is None and current_family:
            filter_pair = (current_family, node_text)
        if filter_pair is None:
            continue

        raw_family, raw_value = filter_pair
        filter_family = normalize_chewy_filter_family(raw_family)
        if filter_family not in allowed:
            continue

        filter_url = _canonicalize_filter_url(urljoin(category_url, href))
        if not _looks_like_chewy_filter_url(filter_url):
            continue
        filter_value = _clean_filter_value(raw_value)
        if not filter_value or _is_non_value_label(filter_value):
            continue

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
                filter_label=filter_value,
            )
        )

    return sorted(
        discovered,
        key=lambda item: (item.filter_family, item.filter_value, item.filter_url),
    )


def crawl_chewy_filter_observations(
    surfaces: Iterable[FilterSurface],
    *,
    fetcher: HTMLFetcher,
    max_pages: int,
    delay_seconds: float,
    allowed_patterns,
    parent_id_pattern,
    canonical_base_url: str | None,
) -> list[FilterObservation]:
    """Crawl Chewy filter surfaces and return product memberships."""

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
            sort_modes=("newest",),
            source_surface=f"filter:{surface.filter_family}={surface.filter_value}",
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
                    source_surface=row.source_surface,
                    pdp_url=row.pdp_url,
                    parent_product_id=row.parent_product_id,
                    page=row.page,
                    position=row.position,
                    listing_url=row.listing_url,
                )
            )
    return observations


def normalize_chewy_filter_family(value: str) -> str:
    """Normalize a Chewy filter family to a stable lowercase label."""

    cleaned = " ".join(str(value or "").strip().lower().split())
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    return _FILTER_FAMILY_ALIASES.get(cleaned, cleaned)


def _expand_allowed_families(values: Sequence[str]) -> set[str]:
    allowed: set[str] = set()
    for value in values:
        family = normalize_chewy_filter_family(value)
        if not family:
            continue
        allowed.add(family)
    return allowed


def _node_filter_href(node: Tag) -> str:
    for attr_name in ("href", "data-href", "data-url"):
        value = str(node.get(attr_name) or "").strip()
        if value and not value.startswith("javascript:"):
            return value
    return ""


def _facet_value_href(node: Tag) -> str:
    if not isinstance(node.parent, Tag):
        return ""
    anchor = node.parent.find("a", href=True)
    if not isinstance(anchor, Tag):
        return ""
    href = _node_filter_href(anchor)
    if href:
        return href
    return ""


def _synthesize_chewy_facet_url(
    *,
    category_url: str,
    group_id: str,
    facet_id: str,
    filter_value: str,
) -> str | None:
    if not group_id or not facet_id:
        return None
    parsed = urlparse(category_url)
    slug = _slugify_chewy_filter_value(filter_value)
    if not slug:
        return None
    path = f"/f/{slug}-wet-cat-food_c389_f{group_id}v{facet_id}"
    return urlunparse((parsed.scheme or "https", parsed.netloc, path, "", "", ""))


def _slugify_chewy_filter_value(value: str) -> str:
    cleaned = _SLUG_TOKEN_RE.sub("-", str(value or "").strip().lower())
    return cleaned.strip("-")


def _family_from_text(text: str, *, allowed: set[str]) -> str | None:
    family = normalize_chewy_filter_family(text)
    if family in allowed:
        return family
    pair = _extract_family_value_from_text(text)
    if pair is None:
        return None
    family = normalize_chewy_filter_family(pair[0])
    return family if family in allowed else None


def _extract_family_value_from_text(text: str) -> tuple[str, str] | None:
    match = _REFINE_TEXT_RE.search(text)
    if not match:
        return None
    return match.group(1), match.group(2)


def _extract_query_filter_pair(url: str) -> tuple[str, str] | None:
    for key, value in parse_qsl(urlparse(url).query, keep_blank_values=True):
        family = normalize_chewy_filter_family(key)
        if family in CHEWY_DEFAULT_FILTER_FAMILIES and str(value).strip():
            return family, value
    return None


def _looks_like_chewy_filter_url(url: str) -> bool:
    parsed = urlparse(url)
    if "chewy.com" not in parsed.netloc.lower():
        return False
    path = parsed.path.lower()
    return "/dp/" not in path and (path.startswith("/b/") or path.startswith("/f/"))


def _canonicalize_filter_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True), fragment=""))


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _clean_filter_value(value: str) -> str:
    cleaned = _clean_text(value)
    pair = _extract_family_value_from_text(cleaned)
    if pair is not None:
        cleaned = pair[1]
    cleaned = _TRAILING_COUNT_RE.sub("", cleaned).strip()
    return cleaned


def _is_non_value_label(value: str) -> bool:
    normalized = value.casefold()
    return (
        normalized.startswith("+ ")
        or normalized.endswith("more")
        or normalized.startswith("find a ")
        or "brands are shown" in normalized
    )
