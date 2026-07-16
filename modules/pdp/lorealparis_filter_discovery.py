from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import parse_qsl, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup  # type: ignore[import]

from .lorealparis_catalog import LOREALPARIS_BASE_URL, LOREALPARIS_RETAILER
from .models import FilterObservation, FilterSurface

__all__ = [
    "LorealParisSiteTag",
    "build_lorealparis_filter_records",
    "extract_lorealparis_filter_surfaces",
    "extract_lorealparis_site_tags",
    "map_lorealparis_site_tag_to_attribute",
    "normalize_lorealparis_filter_value",
]

_FACE_FILTER_PATH = "/makeup/face"
_FILTER_QUERY_KEYS = {
    "benefit",
    "color",
    "content-type",
    "coverage",
    "finish",
    "formula",
    "formulated-without",
    "ingredient",
    "look",
    "preference",
    "product-status",
    "product-type",
    "skin-type",
    "texture",
    "topic",
}
_PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "not stated", "unknown"}

_BLUSH_COLORS = {
    "berry",
    "bronze",
    "brown",
    "coral",
    "mauve",
    "nude",
    "peach",
    "pink",
    "plum",
    "purple",
    "red",
    "rose",
}
_FORM_VALUES = {
    "cream": "cream",
    "liquid": "liquid",
    "powder": "powder",
    "stick": "stick",
}
_FINISH_VALUES = {
    "dewy": "dewy",
    "glitter": "glitter",
    "luminous": "luminous",
    "matte": "matte",
    "natural": "natural",
    "radiant": "luminous",
    "satin": "satin",
    "shimmer": "shimmer",
    "soft matte": "soft-matte",
}
_PIGMENT_VALUES = {
    "bold": "full",
    "buildable": "buildable",
    "highly pigmented": "full",
    "intense color": "full",
    "light": "light",
    "medium": "medium",
    "sheer": "sheer",
}
_RESISTANCE_VALUES = {
    "sweat proof": "sweat resistant",
    "sweat resistant": "sweat resistant",
    "sweatproof": "sweat resistant",
    "transfer proof": "transfer resistant",
    "transfer resistant": "transfer resistant",
    "water resistant": "water resistant",
    "waterproof": "waterproof",
}
_DERMATOLOGY_VALUES = {
    "dermatologist recommended": "dermatologist-tested",
    "dermatologist tested": "dermatologist-tested",
    "non comedogenic": "non-comedogenic",
    "non-comedogenic": "non-comedogenic",
    "suitable for sensitive skin": "suitable for sensitive skin",
}
_SKIN_BENEFIT_VALUES = {
    "anti-shine": "oil control",
    "blurring": "blurring",
    "brightening": "brightening",
    "hydrating": "hydrating",
    "mattifying": "oil control",
    "moisturizing": "hydrating",
    "oil control": "oil control",
    "smooths": "blurring",
}
_ETHICS_VALUES = {
    "clean": "clean",
    "cruelty free": "cruelty-free",
    "no animal derived ingredients": "vegan",
    "organic": "organic",
    "vegan": "vegan",
}
_BRONZER_BENEFIT_VALUES = {
    "buildable": "layerable benefit",
    "bronzing": "glow-enhancing",
    "hydrating": "hydrating",
    "long lasting": "long-wearing",
    "long wearing": "long-wearing",
    "long-lasting": "long-wearing",
    "long-wearing": "long-wearing",
    "sweat resistant": "sweatproof/water-resistant",
    "transfer resistant": "transfer-resistant",
    "water resistant": "sweatproof/water-resistant",
    "waterproof": "sweatproof/water-resistant",
}
_BRONZER_SKIN_TYPES = {
    "combination": "combination",
    "dry": "dry",
    "oily": "oily",
    "normal": "normal",
    "sensitive skin": "sensitive",
}
_BRONZER_FREE_FROM = {
    "fragrance free": "fragrance-free",
    "oil free": "oil-free",
    "paraben free": "paraben-free",
    "sulfate free": "sulfate-free",
}
_BRONZER_INGREDIENTS = {
    "hyaluronic acid": "hyaluronic acid",
    "niacinamide": "niacinamide",
    "vitamin c": "vitamin c",
    "vitamin e": "vitamin e",
}


@dataclass(frozen=True, slots=True)
class LorealParisSiteTag:
    """One product tag/filter link emitted by the L'Oreal Paris site."""

    query_key: str
    query_value: str
    label: str
    url: str


def _clean_text(value: object | None) -> str:
    return " ".join(str(value or "").split())


def _normalize_value(value: object) -> str:
    text = _clean_text(value).replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def _title_from_slug(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split("-") if part)


def _canonical_filter_url(url: str, query_key: str, query_value: str) -> str:
    parsed = urlparse(url)
    return urlunparse(
        parsed._replace(
            path=_FACE_FILTER_PATH,
            query=f"{query_key}={query_value}",
            fragment="",
        )
    )


def extract_lorealparis_site_tags(
    html: str,
    *,
    base_url: str = LOREALPARIS_BASE_URL,
) -> list[dict[str, str]]:
    """Extract raw L'Oreal Paris product tag/filter links from rendered HTML."""

    soup = BeautifulSoup(html, "lxml")
    tags: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for anchor in soup.select("a[href]"):
        href = _clean_text(anchor.get("href"))
        if not href:
            continue
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if not parsed.netloc.endswith("lorealparisusa.com"):
            continue
        if parsed.path.rstrip("/") != _FACE_FILTER_PATH:
            continue
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        for query_key, query_value in query_pairs:
            normalized_key = query_key.strip().lower()
            normalized_value = query_value.strip().lower()
            if normalized_key not in _FILTER_QUERY_KEYS or not normalized_value:
                continue
            label = _clean_text(anchor.get_text(" ", strip=True)) or _title_from_slug(
                normalized_value
            )
            if not label:
                continue
            key = (normalized_key, normalized_value, label.casefold())
            if key in seen:
                continue
            seen.add(key)
            tags.append(
                {
                    "query_key": normalized_key,
                    "query_value": normalized_value,
                    "label": label,
                    "url": _canonical_filter_url(url, normalized_key, normalized_value),
                }
            )
    return sorted(
        tags,
        key=lambda item: (
            item["query_key"],
            item["query_value"],
            item["label"].casefold(),
        ),
    )


def normalize_lorealparis_filter_value(raw_value: object) -> str | None:
    """Normalize a L'Oreal Paris site filter value for attribute storage."""

    normalized = _normalize_value(raw_value)
    if normalized in _PLACEHOLDER_VALUES:
        return None
    return normalized


def _tag_from_mapping(payload: Mapping[str, object]) -> LorealParisSiteTag | None:
    query_key = _clean_text(payload.get("query_key")).lower()
    query_value = _clean_text(payload.get("query_value")).lower()
    label = _clean_text(payload.get("label"))
    url = _clean_text(payload.get("url"))
    if not query_key or not query_value or not label:
        return None
    return LorealParisSiteTag(
        query_key=query_key,
        query_value=query_value,
        label=label,
        url=url,
    )


def _is_allowed_family(family: str, allowed_families: Sequence[str] | None) -> bool:
    if not allowed_families:
        return True
    normalized = _normalize_value(family)
    allowed = {_normalize_value(item) for item in allowed_families}
    return normalized in allowed


def extract_lorealparis_filter_surfaces(
    *,
    category_url: str,
    html: str,
    category_key: str,
    retailer: str = LOREALPARIS_RETAILER,
    allowed_families: Sequence[str] | None = None,
) -> list[FilterSurface]:
    """Return semantic filter surfaces found in L'Oreal Paris rendered HTML."""

    surfaces: list[FilterSurface] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_tag in extract_lorealparis_site_tags(html):
        tag = _tag_from_mapping(raw_tag)
        if tag is None:
            continue
        mapped = map_lorealparis_site_tag_to_attribute(tag, category_key=category_key)
        if mapped is None:
            continue
        family, value = mapped
        if not _is_allowed_family(family, allowed_families):
            continue
        key = (family, value, tag.url)
        if key in seen:
            continue
        seen.add(key)
        surfaces.append(
            FilterSurface(
                retailer=retailer,
                category_key=category_key,
                filter_family=family,
                filter_value=value,
                filter_url=tag.url or category_url,
                filter_label=tag.label,
            )
        )
    return sorted(
        surfaces,
        key=lambda item: (item.filter_family, item.filter_value, item.filter_url),
    )


def map_lorealparis_site_tag_to_attribute(
    tag: LorealParisSiteTag,
    *,
    category_key: str,
) -> tuple[str, str] | None:
    """Map a L'Oreal Paris site tag to the local attribute taxonomy."""

    category = str(category_key or "").strip().lower()
    label = normalize_lorealparis_filter_value(tag.label)
    query_value = normalize_lorealparis_filter_value(tag.query_value)
    value = label or query_value
    if not value:
        return None

    if tag.query_key in {"texture", "formula"} and value in _FORM_VALUES:
        return ("form", _FORM_VALUES[value])
    if tag.query_key in {"look", "finish"} and value in _FINISH_VALUES:
        return ("finish", _FINISH_VALUES[value])

    if category == "blush":
        if tag.query_key == "color" and value in _BLUSH_COLORS:
            return ("shade_family", value)
        if tag.query_key == "coverage" and value in _PIGMENT_VALUES:
            return ("coverage", _PIGMENT_VALUES[value])
        if value in _PIGMENT_VALUES:
            return ("coverage", _PIGMENT_VALUES[value])
        if value in _RESISTANCE_VALUES:
            return ("resistance_claims", _RESISTANCE_VALUES[value])
        if value in _DERMATOLOGY_VALUES:
            return ("dermatology_claims", _DERMATOLOGY_VALUES[value])
        if value in _SKIN_BENEFIT_VALUES:
            return ("skin_benefits", _SKIN_BENEFIT_VALUES[value])
        if value in _ETHICS_VALUES:
            return ("ethics_claims", _ETHICS_VALUES[value])
        if value == "fragrance free":
            return ("fragrance", "fragrance-free")
        return None

    if category == "bronzer":
        if tag.query_key == "coverage" and value in _PIGMENT_VALUES:
            return ("pigment_level", _PIGMENT_VALUES[value])
        if value in _PIGMENT_VALUES:
            return ("pigment_level", _PIGMENT_VALUES[value])
        if value in _BRONZER_BENEFIT_VALUES:
            return ("benefits", _BRONZER_BENEFIT_VALUES[value])
        if value in _BRONZER_SKIN_TYPES:
            return ("skin_type", _BRONZER_SKIN_TYPES[value])
        if value in _BRONZER_FREE_FROM:
            return ("free_from", _BRONZER_FREE_FROM[value])
        if value in _BRONZER_INGREDIENTS:
            return ("key_ingredients", _BRONZER_INGREDIENTS[value])
        return None

    return None


def _site_tags_from_extras(extras: Mapping[str, object]) -> list[LorealParisSiteTag]:
    raw_tags = extras.get("site_tags")
    if isinstance(raw_tags, str):
        try:
            parsed = json.loads(raw_tags)
        except json.JSONDecodeError:
            return []
        raw_tags = parsed
    if not isinstance(raw_tags, Sequence) or isinstance(raw_tags, (str, bytes)):
        return []
    tags: list[LorealParisSiteTag] = []
    for item in raw_tags:
        if isinstance(item, Mapping) and (tag := _tag_from_mapping(item)) is not None:
            tags.append(tag)
    return tags


def build_lorealparis_filter_records(
    parents: Iterable[Mapping[str, object]],
    *,
    allowed_categories: Sequence[str] | None = None,
    allowed_families: Sequence[str] | None = None,
    retailer: str = LOREALPARIS_RETAILER,
) -> tuple[list[FilterSurface], list[FilterObservation]]:
    """Build filter surfaces and memberships from parsed L'Oreal Paris parents."""

    category_scope = {
        _normalize_value(category)
        for category in allowed_categories or ()
        if _normalize_value(category)
    }
    surfaces: list[FilterSurface] = []
    observations: list[FilterObservation] = []
    seen_surfaces: set[tuple[str, str, str, str]] = set()
    seen_observations: set[tuple[str, str, str, str]] = set()

    for parent_index, parent in enumerate(parents, start=1):
        parent_id = _clean_text(parent.get("parent_product_id"))
        pdp_url = _clean_text(parent.get("pdp_url"))
        category_key = _normalize_value(parent.get("category_key"))
        if category_scope and category_key not in category_scope:
            continue
        extras = parent.get("extras")
        if not isinstance(extras, Mapping):
            continue
        position = 0
        for tag in _site_tags_from_extras(extras):
            mapped = map_lorealparis_site_tag_to_attribute(
                tag,
                category_key=category_key,
            )
            if mapped is None:
                continue
            family, value = mapped
            if not _is_allowed_family(family, allowed_families):
                continue
            surface_key = (category_key, family, value, tag.url)
            if surface_key not in seen_surfaces:
                seen_surfaces.add(surface_key)
                surfaces.append(
                    FilterSurface(
                        retailer=retailer,
                        category_key=category_key,
                        filter_family=family,
                        filter_value=value,
                        filter_url=tag.url,
                        filter_label=tag.label,
                    )
                )
            observation_key = (parent_id, category_key, family, value)
            if not parent_id or observation_key in seen_observations:
                continue
            seen_observations.add(observation_key)
            position += 1
            observations.append(
                FilterObservation(
                    retailer=retailer,
                    category_key=category_key,
                    filter_family=family,
                    filter_value=value,
                    source_surface=f"site_tag:{tag.query_key}={tag.query_value}",
                    pdp_url=pdp_url,
                    parent_product_id=parent_id,
                    page=1,
                    position=position or parent_index,
                    listing_url=tag.url,
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
