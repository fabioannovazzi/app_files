from __future__ import annotations

import re
from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup  # type: ignore[import]
from bs4.element import Tag  # type: ignore[import]

from .models import FilterSurface

__all__ = [
    "extract_saksfifthavenue_filter_surfaces",
    "normalize_saksfifthavenue_filter_family",
]


_FILTER_FAMILY_ALIASES: dict[str, str] = {
    "colour": "color",
    "colors": "color",
    "ref lifestyle": "lifestyle",
    "reflifestyle": "lifestyle",
    "ref sleeve length": "sleeve length",
    "refsleevelength": "sleeve length",
    "material type": "material",
    "materials": "material",
    "sleeve": "sleeve length",
    "sleeve lenght": "sleeve length",
    "sleeve lengths": "sleeve length",
}
_FILTER_FAMILY_QUERY_KEYS: dict[str, str] = {
    "lifestyle": "refLifestyle",
    "sleeve length": "refSleeveLength",
}
_DEFAULT_FILTER_FAMILIES = (
    "color",
    "material",
    "style",
    "sleeve length",
    "lifestyle",
)
_PLAIN_BUTTON_FILTER_FAMILIES = frozenset({"sleeve length", "lifestyle"})
_NON_FILTER_VALUE_LABELS = {
    "allow all",
    "apply",
    "back button advertising cookies",
    "clear",
    "clear all",
    "clear filters",
    "close",
    "confirm my choices",
    "customer care",
    "done",
    "filter",
    "filter button",
    "filters",
    "next",
    "next page",
    "ok",
    "previous",
    "previous page",
    "saksfirst card",
    "show less",
    "show items",
    "show more",
    "services",
    "stores corporate",
    "stores & corporate",
    "update",
    "view all",
    "view less",
    "view more",
}
_FILTER_CONTEXT_RESET_LABELS = {
    "brand",
    "category",
    "designer",
    "featured type",
    "new",
    "price",
    "runway & exclusives",
    "sale",
    "size",
}
_CATEGORY_FALLBACK_FILTER_VALUES = {
    "cashmere_sweaters": {
        "sleeve length": (
            "refSleeveLength",
            ("Long Sleeve", "Short Sleeve", "Sleeveless"),
        ),
    },
}
_TRAILING_COUNT_RE = re.compile(r"\s*\(?\d+\)?\s*$")
_REFINE_TEXT_RE = re.compile(r"refine\s+by\s+([^:]+):\s*([^|]+)", re.IGNORECASE)


def extract_saksfifthavenue_filter_surfaces(
    *,
    category_url: str,
    html: str,
    category_key: str,
    retailer: str = "saksfifthavenue",
    allowed_families: Sequence[str] | None = None,
) -> list[FilterSurface]:
    """Return unique Saks filter URLs exposed on a rendered category page."""

    soup = BeautifulSoup(html, "lxml")
    allowed = {
        normalize_saksfifthavenue_filter_family(value)
        for value in (allowed_families or _DEFAULT_FILTER_FAMILIES)
        if str(value).strip()
    }
    category_path = urlparse(category_url).path.rstrip("/")
    discovered: list[FilterSurface] = []
    seen: set[tuple[str, str, str]] = set()

    current_family: str | None = None
    for node in soup.find_all(["h2", "h3", "h4", "button", "summary", "a"]):
        if not isinstance(node, Tag):
            continue
        node_text = _clean_text(node.get_text(" ", strip=True))
        node_family = _family_from_text(node_text, allowed=allowed)
        href = _node_filter_href(node)
        if not href:
            filter_pair = _extract_family_value_from_text(node_text)
            if filter_pair is None:
                if node_family is not None:
                    current_family = node_family
                    continue
                if _should_reset_filter_context(node_text):
                    current_family = None
                    continue
                filter_pair = _extract_current_family_value_pair(
                    node_text,
                    current_family=current_family,
                    node=node,
                )
                if filter_pair is None:
                    continue
            full_url = _build_query_filter_url(category_url, *filter_pair)
        else:
            full_url = urljoin(category_url, href)
            filter_pair = _extract_query_filter_pair(full_url)
            if filter_pair is None:
                filter_pair = _extract_path_filter_pair(
                    full_url,
                    category_path=category_path,
                    label=node_text,
                    current_family=current_family,
                    node=node,
                    allowed=allowed,
                )
        if node.name != "a" and node_family is not None:
            current_family = node_family
        if filter_pair is None:
            continue

        raw_family, raw_value = filter_pair
        filter_family = normalize_saksfifthavenue_filter_family(raw_family)
        if filter_family not in allowed:
            continue
        if not _looks_like_saks_filter_url(full_url, category_path):
            continue

        filter_value = _clean_filter_value(raw_value)
        filter_label = _clean_filter_value(node_text) or filter_value
        if not filter_value:
            continue
        filter_url = _canonicalize_filter_url(full_url)
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
                filter_label=filter_label,
            )
        )

    _append_category_fallback_surfaces(
        discovered=discovered,
        seen=seen,
        category_url=category_url,
        category_key=category_key,
        retailer=retailer,
        allowed=allowed,
    )

    return sorted(
        discovered,
        key=lambda item: (item.filter_family, item.filter_value, item.filter_url),
    )


def _node_filter_href(node: Tag) -> str:
    for attr_name in ("href", "data-href", "data-url"):
        value = str(node.get(attr_name) or "").strip()
        if not value or value.startswith("javascript:"):
            continue
        return value
    return ""


def _append_category_fallback_surfaces(
    *,
    discovered: list[FilterSurface],
    seen: set[tuple[str, str, str]],
    category_url: str,
    category_key: str,
    retailer: str,
    allowed: set[str],
) -> None:
    fallback_values = _CATEGORY_FALLBACK_FILTER_VALUES.get(category_key, {})
    if not fallback_values:
        return
    discovered_families = {surface.filter_family for surface in discovered}
    for family, fallback in fallback_values.items():
        family_key, values = fallback
        filter_family = normalize_saksfifthavenue_filter_family(family)
        if filter_family not in allowed or filter_family in discovered_families:
            continue
        for value in values:
            filter_value = _clean_filter_value(value)
            filter_url = _canonicalize_filter_url(
                _build_query_filter_url(category_url, family_key, filter_value)
            )
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


def normalize_saksfifthavenue_filter_family(value: str) -> str:
    """Normalize one Saks filter family to a stable lowercase label."""

    cleaned = " ".join(str(value or "").strip().lower().split())
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    return _FILTER_FAMILY_ALIASES.get(cleaned, cleaned)


def _looks_like_saks_filter_url(url: str, category_path: str) -> bool:
    parsed = urlparse(url)
    if "saksfifthavenue.com" not in parsed.netloc.lower():
        return False
    path = parsed.path.rstrip("/")
    if "/product/" in path.lower():
        return False
    if path == category_path:
        return bool(_extract_query_filter_pair(url))
    return path.startswith(f"{category_path}/")


def _extract_query_filter_pair(url: str) -> tuple[str, str] | None:
    query_items = parse_qsl(urlparse(url).query, keep_blank_values=True)
    family_by_index: dict[str, str] = {}
    value_by_index: dict[str, str] = {}

    for key, value in query_items:
        lowered = key.lower()
        direct_family = normalize_saksfifthavenue_filter_family(lowered)
        if direct_family in _DEFAULT_FILTER_FAMILIES and str(value).strip():
            return lowered, value
        if lowered.startswith("prefn"):
            family_by_index[lowered[5:]] = value
        elif lowered.startswith("prefv"):
            value_by_index[lowered[5:]] = value

    shared_indices = [
        index
        for index in family_by_index
        if index in value_by_index
        and str(family_by_index[index]).strip()
        and str(value_by_index[index]).strip()
    ]
    if not shared_indices:
        return None
    selected_index = max(shared_indices, key=_pref_index_sort_key)
    return family_by_index[selected_index], value_by_index[selected_index]


def _extract_path_filter_pair(
    url: str,
    *,
    category_path: str,
    label: str,
    current_family: str | None,
    node: Tag,
    allowed: set[str],
) -> tuple[str, str] | None:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path.startswith(f"{category_path}/"):
        return None

    text_pair = _extract_family_value_from_text(label)
    if text_pair is not None:
        return text_pair

    family = current_family or _family_from_node_attributes(node, allowed=allowed)
    if not family:
        return None

    suffix = path[len(category_path) :].strip("/")
    if not suffix:
        return None
    value = label or suffix.rsplit("/", 1)[-1].replace("-", " ")
    return family, value


def _extract_family_value_from_text(text: str) -> tuple[str, str] | None:
    match = _REFINE_TEXT_RE.search(text)
    if not match:
        return None
    return match.group(1), match.group(2)


def _extract_current_family_value_pair(
    text: str,
    *,
    current_family: str | None,
    node: Tag,
) -> tuple[str, str] | None:
    if current_family is None or node.name not in {"button", "summary"}:
        return None
    if current_family not in _PLAIN_BUTTON_FILTER_FAMILIES:
        return None
    value = _clean_filter_value(text)
    if not _looks_like_filter_value_label(value):
        return None
    return current_family, value


def _should_reset_filter_context(text: str) -> bool:
    normalized = _clean_filter_value(text).casefold()
    return normalized in _FILTER_CONTEXT_RESET_LABELS


def _looks_like_filter_value_label(value: str) -> bool:
    normalized = _clean_text(value).casefold()
    if not normalized or normalized in _NON_FILTER_VALUE_LABELS:
        return False
    if normalized.isdigit():
        return False
    return True


def _family_from_text(text: str, *, allowed: set[str]) -> str | None:
    normalized = normalize_saksfifthavenue_filter_family(text)
    if normalized in allowed:
        return normalized
    pair = _extract_family_value_from_text(text)
    if pair is None:
        return None
    family = normalize_saksfifthavenue_filter_family(pair[0])
    return family if family in allowed else None


def _family_from_node_attributes(node: Tag, *, allowed: set[str]) -> str | None:
    for attr_name in ("aria-label", "title", "data-testid", "data-filter-name"):
        raw = str(node.get(attr_name) or "")
        family = _family_from_text(raw, allowed=allowed)
        if family:
            return family
    return None


def _pref_index_sort_key(value: str) -> tuple[int, str]:
    cleaned = str(value or "").strip()
    if cleaned.isdigit():
        return (int(cleaned), cleaned)
    return (-1, cleaned)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _clean_filter_value(value: str) -> str:
    cleaned = _clean_text(value)
    text_pair = _extract_family_value_from_text(cleaned)
    if text_pair is not None:
        cleaned = text_pair[1]
    cleaned = _TRAILING_COUNT_RE.sub("", cleaned).strip()
    return cleaned.replace("+", " ")


def _build_query_filter_url(category_url: str, family: str, value: str) -> str:
    parsed = urlparse(category_url)
    filter_family = normalize_saksfifthavenue_filter_family(family)
    family_key = _FILTER_FAMILY_QUERY_KEYS.get(filter_family, filter_family)
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() == "srule" and str(item).strip()
    ]
    query.extend(
        [
            ("prefn1", family_key),
            ("prefv1", _clean_filter_value(value)),
        ]
    )
    return urlunparse(
        parsed._replace(
            query=urlencode(query, doseq=True),
            fragment="",
        )
    )


def _canonicalize_filter_url(url: str) -> str:
    parsed = urlparse(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if str(value).strip()
        and (
            key.lower().startswith("prefn")
            or key.lower().startswith("prefv")
            or normalize_saksfifthavenue_filter_family(key)
            in _DEFAULT_FILTER_FAMILIES
            or key.lower() == "srule"
        )
    ]
    return urlunparse(
        parsed._replace(
            query=urlencode(query, doseq=True),
            fragment="",
        )
    )
