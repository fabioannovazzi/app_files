from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup  # type: ignore[import]
from bs4.element import Tag  # type: ignore[import]

from .models import FilterObservation, FilterSurface
from .vince_catalog import (
    VINCE_BASE_URL,
    VINCE_CATEGORY_KEY,
    VINCE_CATEGORY_URL,
    VINCE_RETAILER,
    vince_color_families,
)

__all__ = [
    "VinceSiteFilter",
    "build_vince_filter_records",
    "extract_vince_filter_observations_from_html",
    "extract_vince_filter_surfaces",
    "normalize_vince_filter_family",
    "vince_site_filters_from_values",
]

_QUERY_FAMILY_ALIASES = {
    "badge": "new_now",
    "refinementcolor": "color_family",
    "size": "size",
    "stores": "store_availability",
}
_DEFAULT_ALLOWED_SURFACE_FAMILIES = ("new_now", "color_family", "size", "price")
_DEFAULT_ALLOWED_OBSERVATION_FAMILIES = ("new_now", "color_family", "size")
_PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "not stated", "unknown"}
_TRAILING_COUNT_RE = re.compile(r"\s*\(?\d+\)?\s*$")


@dataclass(frozen=True, slots=True)
class VinceSiteFilter:
    """One product-to-filter membership emitted by Vince site/filter data."""

    filter_family: str
    filter_value: str
    filter_label: str
    filter_url: str


def _clean_text(value: object | None) -> str:
    return " ".join(str(value or "").split())


def _normalize_value(value: object | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    normalized = text.replace("_", " ").replace("-", " ").strip()
    normalized = " ".join(normalized.split())
    if normalized.casefold() in _PLACEHOLDER_VALUES:
        return None
    return normalized


def normalize_vince_filter_family(value: object | None) -> str:
    """Normalize a Vince filter label/query name to the local family id."""

    text = _clean_text(value).casefold()
    text = re.sub(r"[^a-z0-9\s]+", " ", text.replace("_", " "))
    text = " ".join(text.split())
    aliases = {
        "badge": "new_now",
        "color": "color_family",
        "color family": "color_family",
        "new": "new_now",
        "new now": "new_now",
        "new plus now": "new_now",
        "price": "price",
        "refinementcolor": "color_family",
        "size": "size",
        "store availability": "store_availability",
        "stores": "store_availability",
    }
    return aliases.get(text, text.replace(" ", "_"))


def _allowed(values: Sequence[str] | None, defaults: Sequence[str]) -> set[str]:
    return {
        normalize_vince_filter_family(value)
        for value in (values or defaults)
        if _clean_text(value)
    }


def _filter_url(base_url: str, query_name: str, query_value: str) -> str:
    parsed = urlparse(base_url)
    if query_name == "price":
        query = query_value
    else:
        query = urlencode({"prefn1": query_name, "prefv1": query_value})
    return urlunparse(parsed._replace(query=query, fragment=""))


def _family_value_from_url(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query_name = _clean_text(next(iter(query.get("prefn1", ())), ""))
    query_value = _clean_text(next(iter(query.get("prefv1", ())), ""))
    if query_name and query_value:
        family = _QUERY_FAMILY_ALIASES.get(
            query_name.replace("-", "").casefold(),
            normalize_vince_filter_family(query_name),
        )
        return family, query_value
    if "pmin" in query or "pmax" in query:
        minimum = _clean_text(next(iter(query.get("pmin", ())), ""))
        maximum = _clean_text(next(iter(query.get("pmax", ())), ""))
        value = f"{minimum}-{maximum}".strip("-")
        return ("price", value) if value else None
    stores = _clean_text(next(iter(query.get("stores", ())), ""))
    if stores:
        return ("store_availability", stores)
    return None


def _label_from_button(node: Tag) -> str:
    text = _clean_text(node.get_text(" ", strip=True))
    text = re.sub(r"\bRefine by .*$", "", text).strip()
    if text:
        return _TRAILING_COUNT_RE.sub("", text).strip()
    for key in ("aria-label", "title", "data-attr-value"):
        text = _clean_text(node.get(key))
        if text:
            text = re.sub(r"^Refine by [^:]+:\s*", "", text).strip()
            return _TRAILING_COUNT_RE.sub("", text).strip()
    return ""


def _price_range_from_node(node: Tag) -> tuple[str, str] | None:
    root = node.find_parent(class_="js-price-ref-slider")
    if root is None:
        root = node.parent
    if root is None:
        return None
    min_node = root.select_one(".js-price-ref-min")
    max_node = root.select_one(".js-price-ref-max")
    minimum = _clean_text(
        (min_node.get("data-full-min") if min_node else None)
        or (min_node.get("value") if min_node else None)
        or node.get("data-full-min")
        or node.get("min")
    )
    maximum = _clean_text(
        (max_node.get("data-full-max") if max_node else None)
        or (max_node.get("value") if max_node else None)
        or node.get("data-full-max")
        or node.get("max")
    )
    if not minimum or not maximum:
        return None
    return minimum, maximum


def extract_vince_filter_surfaces(
    *,
    category_url: str,
    html: str,
    category_key: str = VINCE_CATEGORY_KEY,
    retailer: str = VINCE_RETAILER,
    allowed_families: Sequence[str] | None = None,
) -> list[FilterSurface]:
    """Return filter surfaces found on the Vince sneaker category page."""

    allowed_families_set = _allowed(
        allowed_families,
        _DEFAULT_ALLOWED_SURFACE_FAMILIES,
    )
    soup = BeautifulSoup(html, "lxml")
    surfaces: list[FilterSurface] = []
    seen: set[tuple[str, str, str]] = set()

    for node in soup.select("[data-url], [data-href]"):
        if not isinstance(node, Tag):
            continue
        raw_url = _clean_text(node.get("data-url") or node.get("data-href"))
        if not raw_url:
            continue
        url = urljoin(VINCE_BASE_URL, raw_url)
        parsed = _family_value_from_url(url)
        if parsed is None:
            continue
        family, raw_value = parsed
        family = normalize_vince_filter_family(family)
        if family not in allowed_families_set:
            continue
        label = _label_from_button(node) or raw_value
        if family == "price":
            price_range = _price_range_from_node(node)
            if price_range is None:
                continue
            minimum, maximum = price_range
            raw_value = f"{minimum}-{maximum}"
            label = f"${minimum}-${maximum}"
            url = _filter_url(
                category_url, "price", urlencode({"pmin": minimum, "pmax": maximum})
            )
        value = raw_value if family == "price" else _normalize_value(label)
        if not value:
            continue
        key = (family, value.casefold(), url)
        if key in seen:
            continue
        seen.add(key)
        surfaces.append(
            FilterSurface(
                retailer=retailer,
                category_key=category_key,
                filter_family=family,
                filter_value=value,
                filter_url=url,
                filter_label=label,
            )
        )

    return sorted(
        surfaces,
        key=lambda item: (item.filter_family, item.filter_value, item.filter_url),
    )


def _site_filter_payload(
    *,
    family: str,
    value: str,
    label: str,
    url: str,
) -> dict[str, str]:
    return {
        "filter_family": family,
        "filter_value": value,
        "filter_label": label,
        "filter_url": url,
    }


def vince_site_filters_from_values(
    *,
    color: object | None = None,
    sizes: Sequence[object] | None = None,
    is_new: bool = False,
    category_url: str = VINCE_CATEGORY_URL,
) -> list[dict[str, str]]:
    """Build product-level Vince site filter memberships from PDP values."""

    filters: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(family: str, value: object, label: object | None = None) -> None:
        normalized_family = normalize_vince_filter_family(family)
        normalized_value = _normalize_value(value)
        if not normalized_family or not normalized_value:
            return
        key = (normalized_family, normalized_value.casefold())
        if key in seen:
            return
        seen.add(key)
        query_name = {
            "color_family": "refinementColor",
            "new_now": "badge",
            "size": "size",
        }.get(normalized_family, normalized_family)
        filters.append(
            _site_filter_payload(
                family=normalized_family,
                value=normalized_value,
                label=_clean_text(label) or normalized_value,
                url=_filter_url(category_url, query_name, normalized_value),
            )
        )

    if is_new:
        add("new_now", "New", "New")
    for family in vince_color_families(color):
        add("color_family", family, family)
    for size in sizes or ():
        add("size", size, size)

    return sorted(
        filters,
        key=lambda item: (item["filter_family"], item["filter_value"]),
    )


def _site_filters_from_extras(extras: Mapping[str, object]) -> list[VinceSiteFilter]:
    raw_filters = extras.get("site_filters")
    if isinstance(raw_filters, str):
        try:
            parsed = json.loads(raw_filters)
        except json.JSONDecodeError:
            return []
        raw_filters = parsed
    if not isinstance(raw_filters, Sequence) or isinstance(raw_filters, (str, bytes)):
        return []
    filters: list[VinceSiteFilter] = []
    for raw_item in raw_filters:
        if not isinstance(raw_item, Mapping):
            continue
        family = normalize_vince_filter_family(raw_item.get("filter_family"))
        value = _normalize_value(raw_item.get("filter_value"))
        label = _clean_text(raw_item.get("filter_label")) or str(value or "")
        url = _clean_text(raw_item.get("filter_url"))
        if not family or not value:
            continue
        filters.append(
            VinceSiteFilter(
                filter_family=family,
                filter_value=value,
                filter_label=label,
                filter_url=url,
            )
        )
    return filters


def build_vince_filter_records(
    parents: Iterable[Mapping[str, object]],
    *,
    allowed_categories: Sequence[str] | None = None,
    allowed_families: Sequence[str] | None = None,
    retailer: str = VINCE_RETAILER,
) -> tuple[list[FilterSurface], list[FilterObservation]]:
    """Build filter surfaces and memberships from parsed Vince parent extras."""

    category_scope = {
        _clean_text(category).casefold()
        for category in allowed_categories or ()
        if _clean_text(category)
    }
    allowed_families_set = _allowed(
        allowed_families,
        _DEFAULT_ALLOWED_OBSERVATION_FAMILIES,
    )
    surfaces: list[FilterSurface] = []
    observations: list[FilterObservation] = []
    seen_surfaces: set[tuple[str, str, str, str]] = set()
    seen_observations: set[tuple[str, str, str, str]] = set()

    for parent_index, parent in enumerate(parents, start=1):
        parent_id = _clean_text(parent.get("parent_product_id"))
        pdp_url = _clean_text(parent.get("pdp_url"))
        category_key = _clean_text(parent.get("category_key") or VINCE_CATEGORY_KEY)
        category_key = category_key.casefold()
        if category_scope and category_key not in category_scope:
            continue
        extras = parent.get("extras")
        if not isinstance(extras, Mapping):
            continue
        position = 0
        for site_filter in _site_filters_from_extras(extras):
            if site_filter.filter_family not in allowed_families_set:
                continue
            filter_url = site_filter.filter_url or pdp_url
            surface_key = (
                category_key,
                site_filter.filter_family,
                site_filter.filter_value,
                filter_url,
            )
            if surface_key not in seen_surfaces:
                seen_surfaces.add(surface_key)
                surfaces.append(
                    FilterSurface(
                        retailer=retailer,
                        category_key=category_key,
                        filter_family=site_filter.filter_family,
                        filter_value=site_filter.filter_value,
                        filter_url=filter_url,
                        filter_label=site_filter.filter_label,
                    )
                )
            observation_key = (
                parent_id,
                category_key,
                site_filter.filter_family,
                site_filter.filter_value,
            )
            if not parent_id or observation_key in seen_observations:
                continue
            seen_observations.add(observation_key)
            position += 1
            observations.append(
                FilterObservation(
                    retailer=retailer,
                    category_key=category_key,
                    filter_family=site_filter.filter_family,
                    filter_value=site_filter.filter_value,
                    source_surface=f"site_filter:{site_filter.filter_family}",
                    pdp_url=pdp_url,
                    parent_product_id=parent_id,
                    page=1,
                    position=position or parent_index,
                    listing_url=filter_url,
                )
            )

    return (
        sorted(
            surfaces,
            key=lambda item: (item.category_key, item.filter_family, item.filter_value),
        ),
        sorted(
            observations,
            key=lambda item: (
                item.category_key,
                item.parent_product_id or "",
                item.filter_family,
                item.filter_value,
            ),
        ),
    )


def extract_vince_filter_observations_from_html(
    *,
    filter_surface: FilterSurface,
    html: str,
    parent_id_from_url: Callable[[str], str | None],
) -> list[FilterObservation]:
    """Return product memberships from one rendered Vince filter result page."""

    family = normalize_vince_filter_family(filter_surface.filter_family)
    if family not in _DEFAULT_ALLOWED_OBSERVATION_FAMILIES:
        return []
    soup = BeautifulSoup(html, "lxml")
    observations: list[FilterObservation] = []
    seen_urls: set[str] = set()
    for position, anchor in enumerate(soup.select("a[href*='/product/']"), start=1):
        if not isinstance(anchor, Tag):
            continue
        url = urljoin(VINCE_BASE_URL, _clean_text(anchor.get("href")))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        parent_id = parent_id_from_url(url)
        if not parent_id:
            continue
        observations.append(
            FilterObservation(
                retailer=filter_surface.retailer,
                category_key=filter_surface.category_key,
                filter_family=family,
                filter_value=filter_surface.filter_value,
                source_surface=f"site_filter:{family}",
                pdp_url=url,
                parent_product_id=parent_id,
                page=1,
                position=position,
                listing_url=filter_surface.filter_url,
            )
        )
    return observations
