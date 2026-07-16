from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse, urlunparse

import requests

from .models import FilterObservation, FilterSurface
from .purina_catalog import (
    PURINA_CATEGORY_KEY,
    PURINA_RETAILER,
    PURINA_WET_CAT_FOOD_URL,
    fetch_purina_products_for_api_url,
    purina_parent_id_from_url,
)

__all__ = [
    "PurinaSiteFilter",
    "build_purina_filter_records",
    "fetch_purina_filter_memberships",
    "normalize_purina_filter_family",
    "normalize_purina_filter_value",
    "purina_api_filters_from_search_payload",
    "purina_site_filters_from_values",
]

_PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "not stated", "unknown"}
_DEFAULT_ALLOWED_FILTER_FAMILIES = (
    "animal_protein_source",
    "brand",
    "flavor",
    "food_texture",
    "health_feature",
    "lifestage",
    "product_assortment",
    "special_diet",
)
_FIELD_ID_TO_FAMILY = {
    "brand": "brand",
    "field_brand": "brand",
    "field_flavors": "flavor",
    "field_food_form": "food_texture",
    "field_health_benefits": "health_feature",
    "field_ingredients": "animal_protein_source",
    "field_life_stage": "lifestage",
    "field_special_formula": "special_diet",
    "flavors": "flavor",
    "food_form": "food_texture",
    "food form": "food_texture",
    "health_benefits": "health_feature",
    "health benefit": "health_feature",
    "ingredients": "animal_protein_source",
    "life_stage": "lifestage",
    "life stage": "lifestage",
    "lifestage": "lifestage",
    "package type": "product_assortment",
    "package_type": "product_assortment",
    "products_brand": "brand",
    "products_flavors": "flavor",
    "products_food_form": "food_texture",
    "products_health_benefits": "health_feature",
    "products_ingredients": "animal_protein_source",
    "products_life_stage": "lifestage",
    "products_package_type": "product_assortment",
    "products_special_diet": "special_diet",
    "special_diet": "special_diet",
    "special formula": "special_diet",
}
_VALUE_ALIASES = {
    ("food_texture", "paté"): "Pate",
    ("food_texture", "pate"): "Pate",
    ("health_feature", "digestive support"): "Digestive Health",
    ("health_feature", "dental care/health"): "Dental Care",
    ("health_feature", "sensitive system"): "Sensitive Digestion",
    ("health_feature", "skin & coat"): "Skin & Coat Health",
    ("product_assortment", "single flavor"): "Single Recipe",
    ("special_diet", "grain free"): "Grain-Free",
    ("special_diet", "high protein"): "High-Protein",
    ("special_diet", "no artificial flavors/preservatives"): (
        "No Artificial Flavors or Preservatives"
    ),
    ("special_diet", "no corn, wheat, soy"): "No Corn No Wheat No Soy",
}


@dataclass(frozen=True, slots=True)
class PurinaSiteFilter:
    """One product-to-filter membership emitted by Purina API data."""

    filter_family: str
    filter_value: str
    filter_label: str
    filter_url: str
    raw_value: str | None = None
    count: int | None = None


def _clean_text(value: object | None) -> str:
    return " ".join(str(value or "").split())


def _normalize_value(value: object | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    normalized = text.replace("_", " ").strip()
    normalized = " ".join(normalized.split())
    if normalized.casefold() in _PLACEHOLDER_VALUES:
        return None
    return normalized


def normalize_purina_filter_family(value: object | None) -> str:
    """Normalize one Purina filter family to an attribute/filter id."""

    text = _clean_text(value).casefold()
    text = re.sub(r"[^a-z0-9\s_]+", " ", text.replace("-", " "))
    text = " ".join(text.split())
    return _FIELD_ID_TO_FAMILY.get(text, text.replace(" ", "_"))


def normalize_purina_filter_value(
    family: object | None, value: object | None
) -> str | None:
    """Normalize official Purina filter labels to package-facing taxonomy values."""

    normalized_family = normalize_purina_filter_family(family)
    normalized_value = _normalize_value(value)
    if not normalized_value:
        return None
    alias = _VALUE_ALIASES.get((normalized_family, normalized_value.casefold()))
    return alias or normalized_value


def _allowed_filter_families(values: Sequence[str] | None) -> set[str]:
    return {
        normalize_purina_filter_family(value)
        for value in (values or _DEFAULT_ALLOWED_FILTER_FAMILIES)
        if _clean_text(value)
    }


def _filter_url(
    family: str,
    value: str,
    base_url: str = PURINA_WET_CAT_FOOD_URL,
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
    raw_value: str | None = None,
    count: int | None = None,
) -> dict[str, object]:
    label_text = _normalize_value(label) or value
    return {
        "count": count,
        "filter_family": family,
        "filter_label": label_text,
        "filter_url": url or _filter_url(family, value),
        "filter_value": value,
        "raw_value": raw_value,
    }


def purina_site_filters_from_values(
    *,
    brand: object | None = None,
    flavors: Sequence[object] | None = None,
    food_textures: Sequence[object] | None = None,
    health_features: Sequence[object] | None = None,
    ingredients: Sequence[object] | None = None,
    lifestages: Sequence[object] | None = None,
    product_assortment: object | None = None,
    special_diets: Sequence[object] | None = None,
) -> list[dict[str, object]]:
    """Build Purina product-level site filters from parsed values."""

    filters: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    def add(family: str, value: object | None) -> None:
        normalized_family = normalize_purina_filter_family(family)
        normalized_value = normalize_purina_filter_value(normalized_family, value)
        if not normalized_family or not normalized_value:
            return
        key = (normalized_family, normalized_value.casefold())
        if key in seen:
            return
        seen.add(key)
        filters.append(
            _site_filter_payload(
                family=normalized_family,
                value=normalized_value,
                label=_normalize_value(value),
            )
        )

    add("brand", brand)
    for value in flavors or ():
        add("flavor", value)
    for value in food_textures or ():
        add("food_texture", value)
    for value in health_features or ():
        add("health_feature", value)
    for value in ingredients or ():
        add("animal_protein_source", value)
    for value in lifestages or ():
        add("lifestage", value)
    add("product_assortment", product_assortment)
    for value in special_diets or ():
        add("special_diet", value)
    return filters


def _metadata_by_field_id(
    payload: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    raw_metadata = payload.get("facets_metadata")
    if not isinstance(raw_metadata, Mapping):
        return {}
    metadata: dict[str, Mapping[str, object]] = {}
    for key, value in raw_metadata.items():
        if not isinstance(value, Mapping):
            continue
        field_id = _clean_text(value.get("field_id"))
        if field_id:
            metadata[field_id] = value
        metadata[str(key)] = value
    return metadata


def _iter_api_facet_items(
    payload: Mapping[str, object],
) -> Iterable[tuple[str, Mapping[str, object], Mapping[str, object]]]:
    metadata = _metadata_by_field_id(payload)
    raw_facets = payload.get("facets")
    if not isinstance(raw_facets, Sequence) or isinstance(raw_facets, (str, bytes)):
        return ()
    rows: list[tuple[str, Mapping[str, object], Mapping[str, object]]] = []
    for group in raw_facets:
        if not isinstance(group, Sequence) or isinstance(group, (str, bytes)):
            continue
        for obj in group:
            if not isinstance(obj, Mapping):
                continue
            for field_id, raw_items in obj.items():
                if not isinstance(raw_items, Sequence) or isinstance(
                    raw_items, (str, bytes)
                ):
                    continue
                field_metadata = metadata.get(str(field_id), {})
                for raw_item in raw_items:
                    if isinstance(raw_item, Mapping):
                        rows.append((str(field_id), field_metadata, raw_item))
    return rows


def purina_api_filters_from_search_payload(
    payload: Mapping[str, object],
    *,
    allowed_families: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Return official Purina API filter surfaces as normalized payloads."""

    allowed = _allowed_filter_families(allowed_families)
    filters: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for field_id, metadata, raw_item in _iter_api_facet_items(payload):
        family = normalize_purina_filter_family(
            metadata.get("url_alias") or metadata.get("label") or field_id
        )
        if family not in allowed:
            continue
        values = raw_item.get("values")
        if not isinstance(values, Mapping):
            continue
        label = _normalize_value(values.get("value"))
        value = normalize_purina_filter_value(family, label)
        if not value:
            continue
        raw_count = values.get("count")
        try:
            count = int(raw_count)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            count = None
        url = _clean_text(raw_item.get("url")) or _filter_url(family, value)
        raw_value = _clean_text(raw_item.get("raw_value")) or None
        key = (family, value.casefold(), url)
        if key in seen:
            continue
        seen.add(key)
        filters.append(
            _site_filter_payload(
                family=family,
                value=value,
                label=label,
                url=url,
                raw_value=raw_value,
                count=count,
            )
        )
    filters.sort(
        key=lambda item: (
            str(item["filter_family"]),
            str(item["filter_value"]).casefold(),
        )
    )
    return filters


def fetch_purina_filter_memberships(
    session: requests.Session,
    api_filters: Sequence[Mapping[str, object]],
    *,
    timeout: float | tuple[float, float] = 30.0,
) -> dict[str, list[dict[str, object]]]:
    """Fetch product memberships for each official Purina API filter."""

    filters_by_parent: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for api_filter in api_filters:
        url = _clean_text(api_filter.get("filter_url"))
        family = normalize_purina_filter_family(api_filter.get("filter_family"))
        value = normalize_purina_filter_value(family, api_filter.get("filter_value"))
        if not url or not family or not value:
            continue
        products = fetch_purina_products_for_api_url(
            session,
            url,
            timeout=timeout,
        )
        for product in products:
            parent_id = purina_parent_id_from_url(str(product.get("url") or ""))
            if not parent_id:
                continue
            key = (parent_id, family, value.casefold())
            if key in seen:
                continue
            seen.add(key)
            filters_by_parent[parent_id].append(dict(api_filter))
    for filters in filters_by_parent.values():
        filters.sort(
            key=lambda item: (
                str(item.get("filter_family") or ""),
                str(item.get("filter_value") or "").casefold(),
            )
        )
    return dict(filters_by_parent)


def _site_filters_from_extras(extras: Mapping[str, object]) -> list[PurinaSiteFilter]:
    raw_filters = extras.get("site_filters")
    if not isinstance(raw_filters, Sequence) or isinstance(raw_filters, (str, bytes)):
        return []
    filters: list[PurinaSiteFilter] = []
    seen: set[tuple[str, str]] = set()
    for raw_item in raw_filters:
        if not isinstance(raw_item, Mapping):
            continue
        family = normalize_purina_filter_family(raw_item.get("filter_family"))
        value = normalize_purina_filter_value(family, raw_item.get("filter_value"))
        if not family or not value:
            continue
        key = (family, value.casefold())
        if key in seen:
            continue
        seen.add(key)
        label = _normalize_value(raw_item.get("filter_label")) or value
        url = _clean_text(raw_item.get("filter_url")) or _filter_url(family, value)
        raw_count = raw_item.get("count")
        try:
            count = int(raw_count)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            count = None
        raw_value = _clean_text(raw_item.get("raw_value")) or None
        filters.append(
            PurinaSiteFilter(
                count=count,
                filter_family=family,
                filter_label=label,
                filter_url=url,
                filter_value=value,
                raw_value=raw_value,
            )
        )
    return filters


def build_purina_filter_records(
    parent_rows: Sequence[Mapping[str, object]],
    *,
    allowed_categories: Sequence[str] | None = None,
    allowed_families: Sequence[str] | None = None,
) -> tuple[list[FilterSurface], list[FilterObservation]]:
    """Build filter surfaces and memberships from parsed Purina parent extras."""

    allowed_category_set = {
        str(category).strip().lower()
        for category in (allowed_categories or (PURINA_CATEGORY_KEY,))
        if _clean_text(category)
    }
    allowed_family_set = _allowed_filter_families(allowed_families)
    surfaces_by_key: dict[tuple[str, str, str], FilterSurface] = {}
    observations: list[FilterObservation] = []
    seen_observations: set[tuple[str, str, str]] = set()

    for row in parent_rows:
        category_key = (
            str(row.get("category_key") or PURINA_CATEGORY_KEY).strip().lower()
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
                    retailer=PURINA_RETAILER,
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
                    retailer=PURINA_RETAILER,
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
