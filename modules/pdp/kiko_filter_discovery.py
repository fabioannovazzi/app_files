from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlencode, urlparse

import requests
from bs4 import BeautifulSoup  # type: ignore[import]

from .discovery import KIKO_ALGOLIA_API_KEY, KIKO_ALGOLIA_APP_ID
from .models import FilterObservation, FilterSurface

__all__ = [
    "KIKO_SEMANTIC_FACET_TO_ATTRIBUTE",
    "KikoAlgoliaState",
    "crawl_kiko_filter_observations",
    "extract_kiko_filter_surfaces",
    "load_kiko_algolia_state",
    "normalize_kiko_filter_value",
]

LOGGER = logging.getLogger(__name__)

KIKO_SEMANTIC_FACET_TO_ATTRIBUTE: dict[str, str] = {
    "coverage": "coverage",
    "finishEffect": "finish",
    "waterproof": "water resistance",
    "spf": "spf",
}

_IGNORED_FACETS = {
    "averageRating",
    "multicolor",
    "prices.formattedDiscountPerc",
    "prices.value",
}
_PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "not stated", "unknown"}
_ALGOLIA_URL = f"https://{KIKO_ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries"


@dataclass(frozen=True, slots=True)
class KikoAlgoliaState:
    """Rendered Kiko category search state extracted from ``__NEXT_DATA__``."""

    index_name: str
    params: dict[str, str]
    facets: dict[str, dict[str, int]]


def load_kiko_algolia_state(html: str) -> KikoAlgoliaState | None:
    """Extract the first product-search Algolia result from a Kiko PLP."""

    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return None
    try:
        payload = json.loads(script.string)
    except json.JSONDecodeError:
        return None

    page_props = (
        payload.get("props", {}).get("pageProps")
        if isinstance(payload, Mapping)
        else None
    )
    if not isinstance(page_props, Mapping):
        return None
    initial_results = (
        page_props.get("serverState", {}).get("initialResults")
        if isinstance(page_props.get("serverState"), Mapping)
        else None
    )
    if not isinstance(initial_results, Mapping):
        return None

    for result_payload in initial_results.values():
        if not isinstance(result_payload, Mapping):
            continue
        results = result_payload.get("results")
        if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
            continue
        for result in results:
            if not isinstance(result, Mapping):
                continue
            hits = result.get("hits")
            facets = result.get("facets")
            index_name = str(result.get("index") or "").strip()
            params = str(result.get("params") or "").strip()
            if (
                isinstance(hits, Sequence)
                and not isinstance(hits, (str, bytes))
                and isinstance(facets, Mapping)
                and index_name
                and params
            ):
                parsed_facets: dict[str, dict[str, int]] = {}
                for family, values in facets.items():
                    if not isinstance(values, Mapping):
                        continue
                    parsed_values: dict[str, int] = {}
                    for value, count in values.items():
                        value_text = str(value or "").strip()
                        if not value_text:
                            continue
                        try:
                            parsed_values[value_text] = int(count or 0)
                        except (TypeError, ValueError):
                            parsed_values[value_text] = 0
                    if parsed_values:
                        parsed_facets[str(family)] = parsed_values
                return KikoAlgoliaState(
                    index_name=index_name,
                    params=dict(parse_qsl(params, keep_blank_values=True)),
                    facets=parsed_facets,
                )
    return None


def extract_kiko_filter_surfaces(
    *,
    category_url: str,
    html: str,
    category_key: str,
    retailer: str = "kiko",
    allowed_families: Sequence[str] | None = None,
) -> list[FilterSurface]:
    """Return semantic Kiko filter surfaces from the rendered PLP state."""

    state = load_kiko_algolia_state(html)
    if state is None:
        return []
    allowed = (
        {_normalize_family(value) for value in allowed_families if str(value).strip()}
        if allowed_families
        else None
    )

    discovered: list[FilterSurface] = []
    seen: set[tuple[str, str]] = set()
    for facet, values in state.facets.items():
        if facet in _IGNORED_FACETS:
            continue
        attribute = KIKO_SEMANTIC_FACET_TO_ATTRIBUTE.get(facet)
        if attribute is None:
            continue
        if allowed is not None and (
            _normalize_family(attribute) not in allowed
            and _normalize_family(facet) not in allowed
        ):
            continue
        for raw_value in sorted(values):
            normalized_value = normalize_kiko_filter_value(
                facet,
                raw_value,
                category_key=category_key,
            )
            if normalized_value is None:
                continue
            dedupe_key = (attribute, normalized_value.casefold())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            discovered.append(
                FilterSurface(
                    retailer=retailer,
                    category_key=category_key,
                    filter_family=attribute,
                    filter_value=normalized_value,
                    filter_url=_filter_surface_url(category_url, facet, raw_value),
                    filter_label=str(raw_value).strip(),
                )
            )

    return sorted(
        discovered,
        key=lambda item: (item.filter_family, item.filter_value, item.filter_url),
    )


def crawl_kiko_filter_observations(
    *,
    category_url: str,
    html: str,
    category_key: str,
    variant_parent_lookup: Mapping[str, Sequence[str]],
    session: requests.Session | None = None,
    max_pages: int = 20,
    timeout: float = 15.0,
    allowed_families: Sequence[str] | None = None,
) -> list[FilterObservation]:
    """Query Kiko Algolia filtered facets and return parent-product memberships."""

    if not KIKO_ALGOLIA_APP_ID or not KIKO_ALGOLIA_API_KEY:
        return []

    state = load_kiko_algolia_state(html)
    if state is None:
        return []
    surfaces = extract_kiko_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key=category_key,
        allowed_families=allowed_families,
    )
    if not surfaces:
        return []

    client = session or requests.Session()
    observations: list[FilterObservation] = []
    seen: set[tuple[str, str, str]] = set()

    for surface in surfaces:
        raw_facet, raw_value = _raw_facet_pair_from_surface(surface.filter_url)
        if raw_facet is None or raw_value is None:
            continue
        hits = _query_filtered_hits(
            client,
            state=state,
            facet=raw_facet,
            value=raw_value,
            max_pages=max_pages,
            timeout=timeout,
        )
        position = 0
        for hit in hits:
            parent_ids = _parent_ids_for_hit(hit, variant_parent_lookup)
            for parent_id in parent_ids:
                dedupe_key = (
                    parent_id,
                    surface.filter_family,
                    surface.filter_value,
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                position += 1
                observations.append(
                    FilterObservation(
                        retailer="kiko",
                        category_key=category_key,
                        filter_family=surface.filter_family,
                        filter_value=surface.filter_value,
                        source_surface=(
                            f"filter:{surface.filter_family}={surface.filter_value}"
                        ),
                        pdp_url=_hit_pdp_url(category_url, hit),
                        parent_product_id=parent_id,
                        page=1,
                        position=position,
                        listing_url=category_url,
                    )
                )
    return observations


def normalize_kiko_filter_value(
    facet: str,
    raw_value: object,
    *,
    category_key: str,
) -> str | None:
    """Normalize one Kiko facet value into the project attribute vocabulary."""

    text = " ".join(str(raw_value or "").strip().split())
    if not text or text.casefold() in _PLACEHOLDER_VALUES:
        return None
    upper = text.upper()

    if facet == "coverage":
        return {
            "FULL COLOR": "full",
            "HIGH": "full",
            "LIGHT": "light",
            "MEDIUM": "medium",
            "SHEER": "sheer",
        }.get(upper)

    if facet == "finishEffect":
        category = _normalize_family(category_key).replace(" ", "_")
        if upper == "GLOSSY" and category == "lip_gloss":
            return "high shine/glossy"
        if upper == "LUMINOUS" and category == "foundation":
            return "radiant/luminous"
        return {
            "GLOSSY": "glossy",
            "LUMINOUS": "luminous",
            "MATTE": "matte",
            "METALLIC": "metallic",
            "NATURAL": "natural",
            "PEARLY": "pearlescent",
            "SATIN": "satin",
            "SHEER": "sheer",
            "SHIMMER": "shimmer",
        }.get(upper)

    if facet == "waterproof":
        return "waterproof" if upper == "YES" else None

    if facet == "spf":
        return text if re.search(r"\d", text) else None

    return None


def _query_filtered_hits(
    session: requests.Session,
    *,
    state: KikoAlgoliaState,
    facet: str,
    value: str,
    max_pages: int,
    timeout: float,
) -> list[Mapping[str, object]]:
    query_params = dict(state.params)
    query_params["hitsPerPage"] = "100"
    query_params["page"] = "0"
    query_params["facetFilters"] = json.dumps(
        _append_facet_filter(query_params.get("facetFilters"), facet, value),
        separators=(",", ":"),
    )

    hits: list[Mapping[str, object]] = []
    total_pages = 1
    for page in range(max(1, max_pages)):
        query_params["page"] = str(page)
        body = {
            "requests": [
                {
                    "indexName": state.index_name,
                    "params": urlencode(query_params, doseq=True),
                }
            ]
        }
        response = session.post(
            _ALGOLIA_URL,
            headers={
                "X-Algolia-Application-Id": KIKO_ALGOLIA_APP_ID,
                "X-Algolia-API-Key": KIKO_ALGOLIA_API_KEY,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=timeout,
        )
        if response.status_code != 200:
            LOGGER.warning(
                "Kiko Algolia filter request failed for %s=%s: %s",
                facet,
                value,
                response.status_code,
            )
            break
        result = (response.json().get("results") or [{}])[0]
        if not isinstance(result, Mapping):
            break
        page_hits = result.get("hits") or []
        if isinstance(page_hits, Sequence) and not isinstance(page_hits, (str, bytes)):
            hits.extend(hit for hit in page_hits if isinstance(hit, Mapping))
        try:
            total_pages = int(result.get("nbPages") or 1)
        except (TypeError, ValueError):
            total_pages = 1
        if page + 1 >= total_pages:
            break
    return hits


def _append_facet_filter(
    facet_filters_raw: str | None,
    facet: str,
    value: str,
) -> list[object]:
    try:
        parsed = json.loads(facet_filters_raw or "[]")
    except json.JSONDecodeError:
        parsed = []
    filters = parsed if isinstance(parsed, list) else []
    filters.append([f"{facet}:{value}"])
    return filters


def _parent_ids_for_hit(
    hit: Mapping[str, object],
    variant_parent_lookup: Mapping[str, Sequence[str]],
) -> tuple[str, ...]:
    candidate_keys = (
        hit.get("objectID"),
        hit.get("code"),
        hit.get("baseBackendId"),
    )
    parent_ids: list[str] = []
    for key in candidate_keys:
        cleaned = str(key or "").strip()
        if not cleaned:
            continue
        for parent_id in variant_parent_lookup.get(cleaned, ()):
            if parent_id not in parent_ids:
                parent_ids.append(parent_id)
    return tuple(parent_ids)


def _hit_pdp_url(category_url: str, hit: Mapping[str, object]) -> str | None:
    slug = str(hit.get("slug") or "").strip().strip("/")
    if not slug:
        return None
    product_id = str(hit.get("objectID") or "").strip()
    if product_id.isdigit() and not slug.endswith(product_id):
        slug = f"{slug.rstrip('-')}-{product_id}"
    locale = _locale_from_url(category_url)
    return f"https://www.kikocosmetics.com/{locale}/p/{slug}/"


def _locale_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.strip("/").split("/") if part]
    return parts[0] if parts else "en-us"


def _filter_surface_url(category_url: str, facet: str, value: str) -> str:
    return (
        f"{category_url.rstrip('/')}#kiko-filter={quote(f'{facet}:{value}', safe='')}"
    )


def _raw_facet_pair_from_surface(filter_url: str) -> tuple[str | None, str | None]:
    marker = "#kiko-filter="
    if marker not in filter_url:
        return None, None
    raw = filter_url.split(marker, 1)[1]
    try:
        from urllib.parse import unquote

        decoded = unquote(raw)
    except Exception:
        decoded = raw
    if ":" not in decoded:
        return None, None
    facet, value = decoded.split(":", 1)
    facet = facet.strip()
    value = value.strip()
    return (facet or None, value or None)


def _normalize_family(value: object) -> str:
    cleaned = " ".join(str(value or "").strip().lower().replace("_", " ").split())
    return cleaned
