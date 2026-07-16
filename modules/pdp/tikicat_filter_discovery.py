from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse, urlunparse

from .models import FilterObservation, FilterSurface
from .tikicat_catalog import (
    TIKICAT_CATEGORY_KEY,
    TIKICAT_RETAILER,
    TIKICAT_WET_CAT_FOOD_URL,
    tikicat_semantic_attribute_hints,
    tikicat_term_values_for_product,
)

__all__ = [
    "TikicatSiteFilter",
    "build_tikicat_filter_records",
    "normalize_tikicat_filter_family",
    "tikicat_site_filters_for_product",
    "tikicat_site_filters_from_values",
]

_PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "not stated", "unknown"}
_DEFAULT_ALLOWED_FILTER_FAMILIES = (
    "food_texture",
    "lifestage",
    "product_assortment",
    "health_feature",
)


@dataclass(frozen=True, slots=True)
class TikicatSiteFilter:
    """One product-to-filter membership emitted by Tiki Pets site data."""

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


def normalize_tikicat_filter_family(value: object | None) -> str:
    """Normalize one Tiki site filter family to an attribute/filter id."""

    text = _clean_text(value).casefold()
    text = re.sub(r"[^a-z0-9\s_]+", " ", text.replace("-", " "))
    text = " ".join(text.split())
    aliases = {
        "assortment": "product_assortment",
        "food form": "food_texture",
        "food texture": "food_texture",
        "health feature": "health_feature",
        "line": "brand_line",
        "life stage": "lifestage",
        "lifestage": "lifestage",
        "product assortment": "product_assortment",
        "texture": "food_texture",
    }
    return aliases.get(text, text.replace(" ", "_"))


def _allowed_filter_families(values: Sequence[str] | None) -> set[str]:
    return {
        normalize_tikicat_filter_family(value)
        for value in (values or _DEFAULT_ALLOWED_FILTER_FAMILIES)
        if _clean_text(value)
    }


def _filter_url(
    family: str, value: str, base_url: str = TIKICAT_WET_CAT_FOOD_URL
) -> str:
    parsed = urlparse(base_url)
    query = urlencode({family: value})
    return urlunparse(parsed._replace(query=query, fragment=""))


def _site_filter_payload(
    *,
    family: str,
    value: str,
    label: str | None = None,
    url: str | None = None,
) -> dict[str, str]:
    label_text = _normalize_value(label) or value
    return {
        "filter_family": family,
        "filter_value": value,
        "filter_label": label_text,
        "filter_url": url or _filter_url(family, value),
    }


def tikicat_site_filters_from_values(
    *,
    texture: object | None = None,
    lifestage: object | None = None,
    product_assortment: object | None = None,
    health_features: Sequence[object] | None = None,
) -> list[dict[str, str]]:
    """Build Tiki product-level site filters from parsed values."""

    filters: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(family: str, value: object | None) -> None:
        normalized_family = normalize_tikicat_filter_family(family)
        normalized_value = _normalize_value(value)
        if not normalized_family or not normalized_value:
            return
        key = (normalized_family, normalized_value.casefold())
        if key in seen:
            return
        seen.add(key)
        filters.append(
            _site_filter_payload(family=normalized_family, value=normalized_value)
        )

    add("food_texture", texture)
    add("lifestage", lifestage)
    add("product_assortment", product_assortment)
    for value in health_features or ():
        add("health_feature", value)
    return filters


def tikicat_site_filters_for_product(
    product: Mapping[str, object],
    *,
    term_lookup: Mapping[int, Mapping[str, object]] | None = None,
) -> list[dict[str, str]]:
    """Build product-level Tiki site filter memberships from WP terms/copy."""

    term_values = tikicat_term_values_for_product(product, term_lookup=term_lookup)
    hints = tikicat_semantic_attribute_hints(product, term_lookup=term_lookup)
    return tikicat_site_filters_from_values(
        texture=term_values.get("texture"),
        lifestage=(hints.get("lifestage") or [None])[0],
        product_assortment=term_values.get("product_assortment"),
        health_features=hints.get("health_feature"),
    )


def _site_filters_from_extras(extras: Mapping[str, object]) -> list[TikicatSiteFilter]:
    raw_filters = extras.get("site_filters")
    if not isinstance(raw_filters, Sequence) or isinstance(raw_filters, (str, bytes)):
        return []
    filters: list[TikicatSiteFilter] = []
    seen: set[tuple[str, str]] = set()
    for raw_item in raw_filters:
        if not isinstance(raw_item, Mapping):
            continue
        family = normalize_tikicat_filter_family(raw_item.get("filter_family"))
        value = _normalize_value(raw_item.get("filter_value"))
        if not family or not value:
            continue
        key = (family, value.casefold())
        if key in seen:
            continue
        seen.add(key)
        label = _normalize_value(raw_item.get("filter_label")) or value
        url = _clean_text(raw_item.get("filter_url")) or _filter_url(family, value)
        filters.append(
            TikicatSiteFilter(
                filter_family=family,
                filter_value=value,
                filter_label=label,
                filter_url=url,
            )
        )
    return filters


def build_tikicat_filter_records(
    parent_rows: Sequence[Mapping[str, object]],
    *,
    allowed_categories: Sequence[str] | None = None,
    allowed_families: Sequence[str] | None = None,
) -> tuple[list[FilterSurface], list[FilterObservation]]:
    """Build filter surfaces and memberships from parsed Tiki parent extras."""

    allowed_category_set = {
        str(category).strip().lower()
        for category in (allowed_categories or (TIKICAT_CATEGORY_KEY,))
        if _clean_text(category)
    }
    allowed_family_set = _allowed_filter_families(allowed_families)
    surfaces_by_key: dict[tuple[str, str, str], FilterSurface] = {}
    observations: list[FilterObservation] = []
    seen_observations: set[tuple[str, str, str]] = set()

    for row in parent_rows:
        category_key = (
            str(row.get("category_key") or TIKICAT_CATEGORY_KEY).strip().lower()
        )
        if allowed_category_set and category_key not in allowed_category_set:
            continue
        parent_id = _clean_text(row.get("parent_product_id"))
        pdp_url = _clean_text(row.get("pdp_url"))
        extras = row.get("extras")
        if not isinstance(extras, Mapping):
            extras = {}
        for site_filter in _site_filters_from_extras(extras):
            if site_filter.filter_family not in allowed_family_set:
                continue
            surface_key = (
                category_key,
                site_filter.filter_family,
                site_filter.filter_value.casefold(),
            )
            surfaces_by_key.setdefault(
                surface_key,
                FilterSurface(
                    retailer=TIKICAT_RETAILER,
                    category_key=category_key,
                    filter_family=site_filter.filter_family,
                    filter_value=site_filter.filter_value,
                    filter_url=site_filter.filter_url,
                    filter_label=site_filter.filter_label,
                ),
            )
            observation_key = (
                parent_id,
                site_filter.filter_family,
                site_filter.filter_value.casefold(),
            )
            if observation_key in seen_observations:
                continue
            seen_observations.add(observation_key)
            observations.append(
                FilterObservation(
                    retailer=TIKICAT_RETAILER,
                    category_key=category_key,
                    filter_family=site_filter.filter_family,
                    filter_value=site_filter.filter_value,
                    source_surface="brand_site_filter",
                    pdp_url=pdp_url,
                    parent_product_id=parent_id,
                    page=1,
                    position=len(observations) + 1,
                    listing_url=site_filter.filter_url,
                )
            )

    surfaces = sorted(
        surfaces_by_key.values(),
        key=lambda item: (item.filter_family, item.filter_value.casefold()),
    )
    observations.sort(
        key=lambda item: (
            item.filter_family,
            item.filter_value.casefold(),
            item.parent_product_id or "",
        )
    )
    return surfaces, observations
