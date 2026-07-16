from __future__ import annotations

import re
from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup  # type: ignore[import]

from .models import FilterSurface

__all__ = [
    "AMAZON_FILTER_PARAM_HINTS",
    "extract_amazon_filter_surfaces",
    "normalize_amazon_filter_family",
]

AMAZON_FILTER_PARAM_HINTS: dict[str, str] = {
    "p_89": "brand",
    "p_n_feature_browse-bin": "feature",
    "p_n_feature_four_browse-bin": "feature",
    "p_n_feature_eight_browse-bin": "feature",
    "p_n_feature_nine_browse-bin": "feature",
    "p_n_feature_thirty-four_browse-bin": "feature",
    "p_n_condition-type": "condition",
    "p_n_size_browse-vebin": "size",
    "p_n_material_browse": "material",
    "p_n_format_browse-bin": "form",
    "p_n_is_free_shipping": "shipping",
    "p_n_deal_type": "deal",
    "p_n_availability": "availability",
}

_HEADING_SELECTORS: tuple[str, ...] = (
    "[role='heading']",
    "h2",
    "h3",
    "span.a-size-base.a-color-base.puis-bold-weight-text",
    "span.a-size-medium.a-color-base.a-text-bold",
    "span.a-size-base-plus.a-color-base.a-text-bold",
)
_TEXT_JUNK_RE = re.compile(r"\b(?:see more|see all|clear|results?|items?)\b", re.I)
_FILTER_FAMILY_ALIASES: dict[str, str] = {
    "age range description": "life stage",
    "allergen information": "special diet",
    "animal food diet type": "special diet",
    "brands": "brand",
    "brand": "brand",
    "container type": "packaging type",
    "count": "package count",
    "flavors": "flavor",
    "flavor": "flavor",
    "lifestage": "life stage",
    "life stage": "life stage",
    "life stages": "life stage",
    "diet type": "special diet",
    "special diets": "special diet",
    "special diet": "special diet",
    "item form": "food texture",
    "food texture": "food texture",
    "nutrient claims": "health feature",
    "package count": "package count",
    "packaging type": "packaging type",
    "pet type": "pet type",
}
_FILTER_FAMILY_PRIORITY: tuple[str, ...] = (
    "flavor",
    "packaging type",
    "food texture",
    "package count",
    "special diet",
    "life stage",
    "health feature",
    "brand",
)
_FILTER_VALUE_PRIORITY: dict[str, tuple[str, ...]] = {
    "flavor": (
        "chicken",
        "beef",
        "turkey",
        "salmon",
        "tuna",
        "seafood",
        "duck",
    ),
    "packaging type": ("can", "carton", "bag"),
    "food texture": ("pate", "paté", "chunk", "shreds", "cuts", "gravy"),
}
_WET_CAT_FOOD_EXCLUDED_FILTER_VALUES = (
    "dry",
    "kibble",
    "pellet",
    "freeze dried",
)
_FOOD_TEXTURE_FILTER_VALUES = {
    "chunk",
    "chunks",
    "cuts",
    "gravy",
    "pate",
    "paté",
    "shreds",
}


def extract_amazon_filter_surfaces(
    *,
    category_url: str,
    html: str,
    category_key: str,
    retailer: str = "amazon",
    allowed_families: Sequence[str] | None = None,
) -> list[FilterSurface]:
    """Return unique Amazon refinement/filter URLs exposed on a rendered PLP."""

    soup = BeautifulSoup(html, "lxml")
    allowed = (
        {
            normalize_amazon_filter_family(value)
            for value in allowed_families
            if str(value).strip()
        }
        if allowed_families
        else None
    )
    discovered: list[FilterSurface] = []
    seen: set[tuple[str, str, str]] = set()

    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        full_url = urljoin(category_url, href)
        if not _looks_like_amazon_filter_url(full_url):
            continue
        filter_value = _clean_value(anchor.get_text(" ", strip=True))
        if not filter_value:
            continue
        filter_family = _infer_filter_family(anchor, full_url)
        if not filter_family:
            continue
        normalized_family = normalize_amazon_filter_family(filter_family)
        normalized_family = _reclassify_filter_family(
            normalized_family,
            filter_value,
        )
        if not _is_relevant_filter_value(
            category_key=category_key,
            filter_value=filter_value,
        ):
            continue
        if allowed is not None and normalized_family not in allowed:
            continue
        cleaned_url = _canonicalize_filter_url(full_url)
        dedupe_key = (normalized_family, filter_value.casefold(), cleaned_url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        discovered.append(
            FilterSurface(
                retailer=retailer,
                category_key=category_key,
                filter_family=normalized_family,
                filter_value=filter_value,
                filter_url=cleaned_url,
                filter_label=filter_value,
            )
        )

    return sorted(
        discovered,
        key=_surface_sort_key,
    )


def normalize_amazon_filter_family(value: str) -> str:
    """Normalize one Amazon filter family to a stable lowercase label."""

    cleaned = " ".join(str(value or "").strip().lower().split())
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9\s_-]+", " ", cleaned)
    normalized = " ".join(cleaned.split())
    return _FILTER_FAMILY_ALIASES.get(normalized, normalized)


def _looks_like_amazon_filter_url(url: str) -> bool:
    parsed = urlparse(url)
    if "amazon." not in parsed.netloc.lower():
        return False
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    rh = str(query.get("rh") or "").strip()
    if not rh:
        return False
    return True


def _infer_filter_family(anchor, full_url: str) -> str | None:
    for node in _context_nodes(anchor):
        heading = _extract_heading(node, anchor)
        if heading:
            return heading

    query = dict(parse_qsl(urlparse(full_url).query, keep_blank_values=True))
    rh = str(query.get("rh") or "").strip()
    for token in rh.split(","):
        key = token.split(":", 1)[0].strip()
        if key in AMAZON_FILTER_PARAM_HINTS:
            return AMAZON_FILTER_PARAM_HINTS[key]
    if query.get("bbn"):
        return "department"
    return None


def _context_nodes(anchor):
    current = anchor
    seen: set[int] = set()
    for _ in range(8):
        if current is None:
            break
        node_id = id(current)
        if node_id not in seen:
            seen.add(node_id)
            yield current
        sibling = getattr(current, "find_previous_sibling", lambda: None)()
        if sibling is not None:
            sibling_id = id(sibling)
            if sibling_id not in seen:
                seen.add(sibling_id)
                yield sibling
        current = getattr(current, "parent", None)


def _extract_heading(node, anchor) -> str | None:
    aria_label = str(
        getattr(node, "get", lambda _key, _default=None: None)("aria-label") or ""
    ).strip()
    if (
        aria_label
        and aria_label.casefold()
        != _clean_value(anchor.get_text(" ", strip=True)).casefold()
    ):
        cleaned = _clean_heading(aria_label)
        if cleaned:
            return cleaned
    if not hasattr(node, "select"):
        return None
    for selector in _HEADING_SELECTORS:
        for heading in node.select(selector):
            if heading is anchor:
                continue
            text = _clean_heading(heading.get_text(" ", strip=True))
            if text:
                return text
    return None


def _clean_heading(text: str) -> str | None:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return None
    if len(cleaned) > 60:
        return None
    if _TEXT_JUNK_RE.search(cleaned):
        return None
    return cleaned


def _clean_value(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    cleaned = re.sub(r"\(\d+\)$", "", cleaned).strip()
    cleaned = re.sub(r"\b\d+\s+results?$", "", cleaned, flags=re.I).strip()
    return cleaned


def _canonicalize_filter_url(url: str) -> str:
    parsed = urlparse(url)
    allowed_keys = {"k", "i", "rh", "s", "bbn", "dc", "rnid"}
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key in allowed_keys and str(value).strip()
    ]
    return urlunparse(
        parsed._replace(
            query=urlencode(query, doseq=True),
            fragment="",
        )
    )


def _reclassify_filter_family(filter_family: str, filter_value: str) -> str:
    normalized_value = _value_key(filter_value)
    if filter_family == "flavor" and normalized_value in _FOOD_TEXTURE_FILTER_VALUES:
        return "food texture"
    return filter_family


def _is_relevant_filter_value(*, category_key: str, filter_value: str) -> bool:
    normalized_category = str(category_key or "").strip().lower()
    if normalized_category != "wet_cat_food":
        return True
    normalized_value = _value_key(filter_value)
    return not any(
        term in normalized_value for term in _WET_CAT_FOOD_EXCLUDED_FILTER_VALUES
    )


def _surface_sort_key(surface: FilterSurface) -> tuple[int, int, str, str, str]:
    family = normalize_amazon_filter_family(surface.filter_family)
    value = _value_key(surface.filter_value)
    family_rank = (
        _FILTER_FAMILY_PRIORITY.index(family)
        if family in _FILTER_FAMILY_PRIORITY
        else len(_FILTER_FAMILY_PRIORITY)
    )
    value_priority = _FILTER_VALUE_PRIORITY.get(family, ())
    value_rank = (
        value_priority.index(value) if value in value_priority else len(value_priority)
    )
    return (
        family_rank,
        value_rank,
        family,
        value,
        surface.filter_url,
    )


def _value_key(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())
