from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup  # type: ignore[import]
from bs4.element import Tag  # type: ignore[import]

from .guestinresidence_catalog import (
    GUESTINRESIDENCE_BASE_URL,
    GUESTINRESIDENCE_CATEGORY_KEY,
    GUESTINRESIDENCE_RETAILER,
    guestinresidence_color_families,
    guestinresidence_product_option_values,
)
from .models import FilterObservation, FilterSurface

__all__ = [
    "GuestInResidenceSiteFilter",
    "build_guestinresidence_filter_records",
    "extract_guestinresidence_filter_surfaces",
    "guestinresidence_site_filters_for_product",
    "normalize_guestinresidence_filter_family",
]

_FILTER_FAMILY_BY_QUERY_NAME = {
    "filter.v.t.shopify.color-pattern": "color_family",
    "filter.v.option.size": "size",
    "filter.v.availability": "availability",
}
_ALLOWED_DEFAULT_FILTER_FAMILIES = ("color_family", "size", "availability")
_TRAILING_COUNT_RE = re.compile(r"\s*\(?\d+\)?\s*$")
_PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "not stated", "unknown"}


@dataclass(frozen=True, slots=True)
class GuestInResidenceSiteFilter:
    """One product-to-filter membership emitted by the GIR site/data."""

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


def normalize_guestinresidence_filter_family(value: object | None) -> str:
    """Normalize one GIR filter family to the local attribute/filter label."""

    text = _clean_text(value).casefold()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = " ".join(text.split())
    aliases = {
        "availability": "availability",
        "color": "color_family",
        "color family": "color_family",
        "color pattern": "color_family",
        "colour": "color_family",
        "size": "size",
    }
    return aliases.get(text, text.replace(" ", "_"))


def _allowed_filter_families(values: Sequence[str] | None) -> set[str]:
    return {
        normalize_guestinresidence_filter_family(value)
        for value in (values or _ALLOWED_DEFAULT_FILTER_FAMILIES)
        if _clean_text(value)
    }


def _filter_url(base_url: str, query_name: str, query_value: str) -> str:
    parsed = urlparse(base_url)
    query = urlencode({query_name: query_value})
    return urlunparse(parsed._replace(query=query, fragment=""))


def _label_for_input(node: Tag) -> str:
    label = node.find_parent("label")
    if label is not None:
        text = _clean_text(label.get_text(" ", strip=True))
        if text:
            return _TRAILING_COUNT_RE.sub("", text).strip()
    element_id = _clean_text(node.get("id"))
    if element_id:
        root = node.find_parent()
        if root is not None:
            explicit = root.select_one(f"label[for='{element_id}']")
            if explicit is not None:
                text = _clean_text(explicit.get_text(" ", strip=True))
                if text:
                    return _TRAILING_COUNT_RE.sub("", text).strip()
    return _clean_text(node.get("value"))


def _surface_from_input(
    *,
    node: Tag,
    category_url: str,
    category_key: str,
    retailer: str,
) -> FilterSurface | None:
    name = _clean_text(node.get("name"))
    raw_value = _clean_text(node.get("value"))
    family = _FILTER_FAMILY_BY_QUERY_NAME.get(name)
    if not family or not raw_value:
        return None
    label = _label_for_input(node)
    if family == "availability":
        value = "in_stock" if raw_value == "1" else label or raw_value
        label = label or "In Stock Only"
    else:
        value = _normalize_value(label) or _normalize_value(raw_value)
    if not value:
        return None
    return FilterSurface(
        retailer=retailer,
        category_key=category_key,
        filter_family=family,
        filter_value=value,
        filter_url=_filter_url(category_url, name, raw_value),
        filter_label=label or value,
    )


def extract_guestinresidence_filter_surfaces(
    *,
    category_url: str,
    html: str,
    category_key: str = GUESTINRESIDENCE_CATEGORY_KEY,
    retailer: str = GUESTINRESIDENCE_RETAILER,
    allowed_families: Sequence[str] | None = None,
) -> list[FilterSurface]:
    """Return GIR collection filter surfaces from rendered/static HTML."""

    allowed = _allowed_filter_families(allowed_families)
    soup = BeautifulSoup(html, "lxml")
    surfaces: list[FilterSurface] = []
    seen: set[tuple[str, str, str]] = set()
    for node in soup.select("form.filter-group-display__form input[name][value]"):
        if not isinstance(node, Tag):
            continue
        surface = _surface_from_input(
            node=node,
            category_url=category_url,
            category_key=category_key,
            retailer=retailer,
        )
        if surface is None or surface.filter_family not in allowed:
            continue
        key = (
            surface.filter_family,
            surface.filter_value.casefold(),
            surface.filter_url,
        )
        if key in seen:
            continue
        seen.add(key)
        surfaces.append(surface)
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


def guestinresidence_site_filters_for_product(
    product: Mapping[str, object],
    *,
    category_url: str = GUESTINRESIDENCE_BASE_URL + "/collections/womens-sweaters",
) -> list[dict[str, str]]:
    """Build product-level GIR site filter memberships from Shopify payloads."""

    filters: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(family: str, value: object, label: object | None = None) -> None:
        normalized_family = normalize_guestinresidence_filter_family(family)
        normalized_value = (
            "in_stock"
            if normalized_family == "availability" and _clean_text(value) == "in_stock"
            else _normalize_value(value)
        )
        if not normalized_family or not normalized_value:
            return
        key = (normalized_family, normalized_value.casefold())
        if key in seen:
            return
        seen.add(key)
        query_name = {
            "availability": "filter.v.availability",
            "color_family": "filter.v.t.shopify.color-pattern",
            "size": "filter.v.option.size",
        }.get(normalized_family, normalized_family)
        raw_value = "1" if normalized_family == "availability" else normalized_value
        filters.append(
            _site_filter_payload(
                family=normalized_family,
                value=normalized_value,
                label=_clean_text(label) or normalized_value,
                url=_filter_url(category_url, query_name, raw_value),
            )
        )

    for color in guestinresidence_product_option_values(product, "Color"):
        for family in guestinresidence_color_families(color):
            add("color_family", family, family)

    for size in guestinresidence_product_option_values(product, "Size"):
        add("size", size, size)

    variants = product.get("variants")
    if isinstance(variants, Sequence) and any(
        isinstance(variant, Mapping) and bool(variant.get("available"))
        for variant in variants
    ):
        add("availability", "in_stock", "In Stock Only")

    return sorted(
        filters, key=lambda item: (item["filter_family"], item["filter_value"])
    )


def _site_filters_from_extras(
    extras: Mapping[str, object],
) -> list[GuestInResidenceSiteFilter]:
    raw_filters = extras.get("site_filters")
    if isinstance(raw_filters, str):
        try:
            parsed = json.loads(raw_filters)
        except json.JSONDecodeError:
            return []
        raw_filters = parsed
    if not isinstance(raw_filters, Sequence) or isinstance(raw_filters, (str, bytes)):
        return []
    filters: list[GuestInResidenceSiteFilter] = []
    for raw_item in raw_filters:
        if not isinstance(raw_item, Mapping):
            continue
        family = normalize_guestinresidence_filter_family(raw_item.get("filter_family"))
        raw_value = _clean_text(raw_item.get("filter_value"))
        value = (
            "in_stock"
            if family == "availability"
            and raw_value.casefold() in {"in_stock", "in stock"}
            else _normalize_value(raw_value)
        )
        label = _clean_text(raw_item.get("filter_label")) or str(value or "")
        url = _clean_text(raw_item.get("filter_url"))
        if not family or not value:
            continue
        filters.append(
            GuestInResidenceSiteFilter(
                filter_family=family,
                filter_value=value,
                filter_label=label,
                filter_url=url,
            )
        )
    return filters


def build_guestinresidence_filter_records(
    parents: Iterable[Mapping[str, object]],
    *,
    allowed_categories: Sequence[str] | None = None,
    allowed_families: Sequence[str] | None = None,
    retailer: str = GUESTINRESIDENCE_RETAILER,
) -> tuple[list[FilterSurface], list[FilterObservation]]:
    """Build filter surfaces and memberships from parsed GIR parent extras."""

    category_scope = {
        _clean_text(category).casefold()
        for category in allowed_categories or ()
        if _clean_text(category)
    }
    allowed = _allowed_filter_families(allowed_families)
    surfaces: list[FilterSurface] = []
    observations: list[FilterObservation] = []
    seen_surfaces: set[tuple[str, str, str, str]] = set()
    seen_observations: set[tuple[str, str, str, str]] = set()

    for parent_index, parent in enumerate(parents, start=1):
        parent_id = _clean_text(parent.get("parent_product_id"))
        pdp_url = _clean_text(parent.get("pdp_url"))
        category_key = _clean_text(
            parent.get("category_key") or GUESTINRESIDENCE_CATEGORY_KEY
        ).casefold()
        if category_scope and category_key not in category_scope:
            continue
        extras = parent.get("extras")
        if not isinstance(extras, Mapping):
            continue
        position = 0
        for site_filter in _site_filters_from_extras(extras):
            if site_filter.filter_family not in allowed:
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
