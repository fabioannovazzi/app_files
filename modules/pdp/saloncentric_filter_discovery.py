from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup  # type: ignore[import]

from modules.add_attributes.attribute_taxonomy import TAXONOMY_PATH

from .discovery import discover_listing_observations
from .fetcher import HTMLFetcher
from .models import FilterObservation, FilterSurface

__all__ = [
    "SALONCENTRIC_CORE_DESCRIPTOR_FAMILIES",
    "SALONCENTRIC_SECONDARY_DESCRIPTOR_FAMILIES",
    "SALONCENTRIC_DESCRIPTOR_FAMILIES",
    "SALONCENTRIC_FAMILY_ALIASES",
    "default_filter_families_for_category",
    "discover_saloncentric_filter_families",
    "extract_saloncentric_filter_surfaces",
    "crawl_saloncentric_filter_observations",
    "map_saloncentric_families_to_taxonomy",
    "normalize_saloncentric_filter_value",
]

SALONCENTRIC_CORE_DESCRIPTOR_FAMILIES: tuple[str, ...] = (
    "product type",
    "product benefit",
    "product form",
    "ingredient preference",
    "haircolor tone",
    "haircolor level",
)

SALONCENTRIC_SECONDARY_DESCRIPTOR_FAMILIES: tuple[str, ...] = ("hair condition",)

SALONCENTRIC_DESCRIPTOR_FAMILIES: tuple[str, ...] = (
    *SALONCENTRIC_CORE_DESCRIPTOR_FAMILIES,
    *SALONCENTRIC_SECONDARY_DESCRIPTOR_FAMILIES,
)

SALONCENTRIC_FAMILY_ALIASES: dict[str, str] = {
    "product type": "category",
    "producttypesc": "category",
    "product benefit": "benefit",
    "productbenefithairsc": "benefit",
    "product form": "form",
    "productformsc": "form",
    "ingredient preference": "ingredient_preference",
    "ingredientpreferencebeautysc": "ingredient_preference",
    "haircolor tone": "haircolor_tone",
    "hair color tone": "haircolor_tone",
    "haircolortonesc": "haircolor_tone",
    "haircolor level": "haircolor_level",
    "hair color level": "haircolor_level",
    "level": "haircolor_level",
    "haircolorlevelsc": "haircolor_level",
    "hair condition": "hair_condition",
    "hairconditionsc": "hair_condition",
}

SALONCENTRIC_DISCOVERY_FAMILY_LABELS: dict[str, str] = {
    "producttypesc": "product type",
    "productbenefithairsc": "product benefit",
    "productformsc": "product form",
    "ingredientpreferencebeautysc": "ingredient preference",
    "haircolortonesc": "haircolor tone",
    "haircolorlevelsc": "haircolor level",
    "level": "haircolor level",
    "hairconditionsc": "hair condition",
}


@lru_cache(maxsize=None)
def default_filter_families_for_category(category_key: str) -> tuple[str, ...]:
    """Return the default SalonCentric filter families for one tracked category."""

    normalized = " ".join(str(category_key or "").strip().lower().split())
    if not normalized:
        return SALONCENTRIC_DESCRIPTOR_FAMILIES

    path = Path(TAXONOMY_PATH) / "categories" / f"{normalized}.json"
    if not path.is_file():
        return SALONCENTRIC_DESCRIPTOR_FAMILIES

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return SALONCENTRIC_DESCRIPTOR_FAMILIES

    raw_attributes = payload.get("attributes", []) if isinstance(payload, Mapping) else []
    families: list[str] = []
    seen: set[str] = set()
    for attribute in raw_attributes:
        if not isinstance(attribute, Mapping):
            continue
        label = _clean_label(attribute.get("label"))
        if not label:
            continue
        normalized_label = _normalize_family(label)
        if not normalized_label or normalized_label in seen:
            continue
        seen.add(normalized_label)
        families.append(label)
    if families:
        return tuple(families)
    return SALONCENTRIC_DESCRIPTOR_FAMILIES


def extract_saloncentric_filter_surfaces(
    *,
    category_url: str,
    html: str,
    category_key: str,
    retailer: str = "saloncentric",
    allowed_families: Sequence[str] | None = None,
) -> list[FilterSurface]:
    """Return unique filter URLs exposed on a SalonCentric category page."""

    soup = BeautifulSoup(html, "lxml")
    discovered_families = set(discover_saloncentric_filter_families(html))
    base_query_pairs = {
        (family, value.casefold())
        for family, value in _extract_query_pref_pairs(urlparse(category_url).query)
        if family and value
    }
    allowed_values = (
        allowed_families
        if allowed_families is not None
        else default_filter_families_for_category(category_key)
    )
    allowed = {
        _normalize_family(value)
        for value in allowed_values
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
        query_pairs = _extract_query_pref_pairs(parsed.query)
        if not query_pairs:
            continue
        for raw_family, raw_value in query_pairs:
            if not raw_family or not raw_value:
                continue
            if (raw_family, raw_value.casefold()) in base_query_pairs:
                continue
            family = _display_family(raw_family)
            if allowed and family not in allowed and raw_family not in allowed:
                continue
            if (
                not allowed
                and discovered_families
                and raw_family not in discovered_families
                and family not in discovered_families
            ):
                continue
            value = normalize_saloncentric_filter_value(family, raw_value)
            cleaned_url = _canonicalize_filter_url(full_url, raw_family, raw_value)
            dedupe_key = (family, value.casefold(), cleaned_url)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            discovered.append(
                FilterSurface(
                    retailer=retailer,
                    category_key=category_key,
                    filter_family=family,
                    filter_value=value,
                    filter_url=cleaned_url,
                    filter_label=_clean_label(anchor.get_text(" ", strip=True)),
                )
            )
    return sorted(
        discovered,
        key=lambda item: (item.filter_family, item.filter_value, item.filter_url),
    )


def crawl_saloncentric_filter_observations(
    surfaces: Iterable[FilterSurface],
    *,
    fetcher: HTMLFetcher,
    max_pages: int,
    delay_seconds: float,
    allowed_patterns,
    parent_id_pattern,
    canonical_base_url: str | None,
) -> list[FilterObservation]:
    """Crawl discovered SalonCentric filter surfaces and return memberships."""

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


def discover_saloncentric_filter_families(html: str) -> tuple[str, ...]:
    """Infer exposed SalonCentric filter families from HTML anchors, attrs, and JSON blobs."""

    soup = BeautifulSoup(html, "lxml")
    families: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if not href or "?" not in href:
            continue
        parsed = urlparse(href)
        for family, _ in _extract_query_pref_pairs(parsed.query):
            if family:
                families.add(family)
    for attr_name in ("data-filter-family", "data-refinement-attribute", "data-refinement-name"):
        for node in soup.select(f"[{attr_name}]"):
            value = _normalize_family(str(node.get(attr_name) or ""))
            if value:
                families.add(value)
    for script in soup.select("script"):
        script_text = str(script.string or script.get_text(" ", strip=False) or "")
        if not script_text:
            continue
        for match in re.findall(r'"prefn\d*"\s*:\s*"([^"]+)"', script_text, flags=re.IGNORECASE):
            value = _normalize_family(match)
            if value:
                families.add(value)
    return tuple(sorted(families))


def map_saloncentric_families_to_taxonomy(
    families: Sequence[str],
    *,
    category_meta: Mapping[str, object],
    aliases: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Map discovered filter families to taxonomy attribute IDs for one category."""

    raw_attributes = category_meta.get("attributes", []) if category_meta else []
    attributes = [attr for attr in raw_attributes if isinstance(attr, Mapping)]
    taxonomy_lookup: dict[str, str] = {}
    for attr in attributes:
        attr_id = str(attr.get("id") or "").strip()
        if not attr_id:
            continue
        label = str(attr.get("label") or "").strip()
        taxonomy_lookup[_normalize_family(attr_id)] = attr_id
        if label:
            taxonomy_lookup[_normalize_family(label)] = attr_id

    default_aliases = dict(SALONCENTRIC_FAMILY_ALIASES)
    if aliases:
        for key, value in aliases.items():
            if str(key).strip() and str(value).strip():
                default_aliases[str(key)] = str(value)

    normalized_aliases = {
        _normalize_family(key): str(value).strip()
        for key, value in default_aliases.items()
        if str(key).strip() and str(value).strip()
    }

    resolved: dict[str, str] = {}
    for family in families:
        raw = str(family or "").strip()
        if not raw:
            continue
        normalized = _normalize_family(raw)
        alias_target = normalized_aliases.get(normalized, normalized)
        attr_id = taxonomy_lookup.get(alias_target)
        if attr_id:
            resolved[raw] = attr_id
    return resolved


def normalize_saloncentric_filter_value(family: str, value: str) -> str:
    """Normalize noisy SalonCentric filter values for known families."""

    family_norm = _normalize_family(family)
    raw = str(value or "").replace("\ufffd", " ").strip()
    if not raw:
        return ""
    if family_norm == "haircolor level":
        lowered = raw.casefold().replace(" ", "")
        if lowered in {"nolevel", "none", "unknown"}:
            return "No Level"
        match = re.search(r"(\d{1,2})", lowered)
        if match:
            return f"Level {int(match.group(1)):02d}"
    return " ".join(raw.split())


def _normalize_family(value: str) -> str:
    cleaned = str(value or "").replace("\ufffd", " ").strip().lower()
    cleaned = re.sub(r"[^a-z0-9\s_-]+", " ", cleaned)
    return " ".join(cleaned.split())


def _display_family(value: str) -> str:
    normalized = _normalize_family(value)
    return SALONCENTRIC_DISCOVERY_FAMILY_LABELS.get(normalized, normalized)


def _clean_label(raw: str | None) -> str | None:
    text = str(raw or "").strip()
    return text or None


def _canonicalize_filter_url(url: str, family: str, value: str) -> str:
    parsed = urlparse(url)
    cleaned = [
        (key, raw)
        for key, raw in parse_qsl(parsed.query, keep_blank_values=True)
        if str(raw).strip()
    ]
    return urlunparse(parsed._replace(query=urlencode(cleaned, doseq=True)))


def _extract_query_pref_pairs(query: str) -> list[tuple[str, str]]:
    query_items = parse_qsl(query, keep_blank_values=True)
    families_by_index: dict[str, str] = {}
    values_by_index: dict[str, str] = {}
    for key, raw in query_items:
        key_norm = key.strip().lower()
        if key_norm.startswith("prefn") and raw.strip():
            index = key_norm[5:] or "1"
            families_by_index[index] = _normalize_family(raw)
        elif key_norm.startswith("prefv") and raw.strip():
            index = key_norm[5:] or "1"
            values_by_index[index] = raw.strip()
    pairs: list[tuple[str, str]] = []
    for index, family in families_by_index.items():
        value = values_by_index.get(index, "")
        if family and value:
            pairs.append((family, value))
    return pairs
