from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from urllib.parse import urlparse

from bs4 import BeautifulSoup  # type: ignore[import]

from ..models import EvidenceBlob, ParentProduct, Variant
from ..tikicat_catalog import (
    TIKICAT_BRAND_NAME,
    TIKICAT_CATEGORY_KEY,
    TIKICAT_RETAILER,
    tikicat_available_sizes_from_text,
    tikicat_category_path,
    tikicat_lifestage_from_text,
    tikicat_parent_id_from_url,
    tikicat_product_url,
    tikicat_semantic_attribute_hints,
)
from ..tikicat_filter_discovery import tikicat_site_filters_from_values
from . import RetailerAdapter

__all__ = ["TikiCatAdapter"]

_WHITESPACE_RE = re.compile(r"\s+")
_TEXTURE_BY_PATH = {
    "lean-gelee": "Gelee",
    "liquid": "Liquid",
    "mousse-cat": "Mousse",
    "mousse-shreds": "Mousse & Shreds",
    "pate-cat": "Pate",
    "shredded-cat": "Minced",
}
_TITLE_OVERRIDES = {
    "after-dark": "After Dark",
    "after-dark-pate": "After Dark Pate",
    "after-dark-velvet-mousse": "After Dark",
    "aloha-friends": "Friends",
    "comfort-liquid": "Comfort",
    "friends-mousse": "Friends",
    "grill": "Grill",
    "grill-pate": "Grill Pate",
    "kitten": "Baby",
    "lean-gelee": "Gelee",
    "liquid-meal-replacer": "Liquid Meal Replacer",
    "luau": "Luau",
    "luau-pate": "Luau Pate",
    "mega-packs": "Mega Packs",
    "senior-cat": "Silver",
    "solution-mousse": "Solutions",
    "velvet-mousse": "Velvet Mousse",
}


def _clean_text(value: object | None) -> str | None:
    text = _WHITESPACE_RE.sub(" ", str(value or "")).strip()
    return text or None


def _slug(value: object | None) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "default"


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _canonical_url(soup: BeautifulSoup) -> str | None:
    for selector, attribute in (
        ("link[rel='canonical']", "href"),
        ("meta[property='og:url']", "content"),
    ):
        node = soup.select_one(selector)
        if node is not None:
            text = _clean_text(node.get(attribute))
            if text:
                return text
    return None


def _meta_content(soup: BeautifulSoup, selector: str) -> str | None:
    node = soup.select_one(selector)
    if node is None:
        return None
    return _clean_text(node.get("content"))


def _hero_image(soup: BeautifulSoup) -> str | None:
    for selector in (
        "meta[property='og:image']",
        "meta[name='twitter:image']",
    ):
        url = _meta_content(soup, selector)
        if url:
            return url
    node = soup.select_one("img.wp-post-image, .woocommerce-product-gallery img")
    if node is not None:
        return _clean_text(node.get("src") or node.get("data-src"))
    return None


def _title(soup: BeautifulSoup) -> str | None:
    node = soup.select_one("h1")
    if node is not None:
        text = _clean_text(node.get_text(" ", strip=True))
        if text:
            return text
    return _meta_content(soup, "meta[property='og:title']")


def _series(soup: BeautifulSoup) -> str | None:
    for selector in ("h6", ".product-line", ".subtitle"):
        node = soup.select_one(selector)
        if node is None:
            continue
        text = _clean_text(node.get_text(" ", strip=True))
        if text and "tiki" in text.casefold():
            return text
    return None


def _body_text(soup: BeautifulSoup) -> str:
    main = soup.select_one("main") or soup.select_one("body") or soup
    return "\n".join(
        line
        for raw_line in main.get_text("\n", strip=True).splitlines()
        if (line := _clean_text(raw_line)) is not None
    )


def _feature_lines(soup: BeautifulSoup) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for node in soup.select("main li, .entry-summary li, .product li"):
        line = _clean_text(node.get_text(" ", strip=True))
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def _path_terms(url: str) -> tuple[str | None, list[str]]:
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    try:
        wet_index = segments.index("tiki-cat-wet-food")
    except ValueError:
        return None, []
    between = segments[wet_index + 1 : -1]
    texture: str | None = None
    lines: list[str] = []
    for segment in between:
        if texture is None and segment in _TEXTURE_BY_PATH:
            texture = _TEXTURE_BY_PATH[segment]
            continue
        label = _TITLE_OVERRIDES.get(
            segment,
            " ".join(part.capitalize() for part in segment.split("-") if part),
        )
        if label and label not in lines and label != texture:
            lines.append(label)
    return texture, lines


def _summary(title: str | None, body_text: str) -> str | None:
    if not body_text:
        return None
    if title and title in body_text:
        _, _, trailing = body_text.partition(title)
        text = trailing.strip()
    else:
        text = body_text
    stop_words = ("Nutritional Facts", "Where to Buy", "REVIEWS")
    for stop in stop_words:
        if stop in text:
            text = text.split(stop, 1)[0].strip()
    return _clean_text(text)


def _variant_payloads(
    *,
    parent_id: str,
    title: str,
    sizes: Sequence[str],
    hero_image_url: str | None,
) -> list[dict[str, object]]:
    raw_sizes = list(sizes) or ["one size"]
    variants: list[dict[str, object]] = []
    for index, size in enumerate(raw_sizes, start=1):
        size_text = _clean_text(size) or "one size"
        variant_id = parent_id if len(raw_sizes) == 1 else f"{parent_id}--{_slug(size_text)}"
        variants.append(
            {
                "id": variant_id,
                "sku": variant_id,
                "name": title,
                "size": None if size_text == "one size" else size_text,
                "availability": "in_stock",
                "image": hero_image_url,
                "attributes": {
                    "size": size_text,
                },
            }
        )
    return variants


class TikiCatAdapter(RetailerAdapter):
    """Parse Tiki Cat PDPs from the Tiki Pets official site."""

    retailer = TIKICAT_RETAILER

    def __init__(self) -> None:
        self._payload: Mapping[str, object] | None = None

    def primary_id_from_url(self, url: str) -> str | None:
        return tikicat_parent_id_from_url(url)

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        soup = BeautifulSoup(html, "lxml")
        canonical_url = _canonical_url(soup) or ""
        parent_id = tikicat_parent_id_from_url(canonical_url)
        if not parent_id:
            self._payload = None
            return ()

        title = _title(soup) or parent_id.replace("-", " ").title()
        body = _body_text(soup)
        summary = _summary(title, body) or body
        features = _feature_lines(soup)
        sizes = tikicat_available_sizes_from_text(body)
        texture, product_lines = _path_terms(canonical_url)
        lifestage = tikicat_lifestage_from_text(
            " ".join([title, summary, " ".join(product_lines)])
        )
        hero_image_url = _hero_image(soup)
        semantic_hints = tikicat_semantic_attribute_hints(
            body_text=body,
            title=title,
            sizes=sizes,
            texture=texture,
            product_lines=product_lines,
        )
        site_filters = tikicat_site_filters_from_values(
            texture=texture,
            lifestage=lifestage,
            product_assortment=(semantic_hints.get("product_assortment") or [None])[0],
            health_features=semantic_hints.get("health_feature"),
        )
        product_url = tikicat_product_url(parent_id, canonical_url)
        payload: dict[str, object] = {
            "id": parent_id,
            "brand": TIKICAT_BRAND_NAME,
            "name": title,
            "description": summary,
            "collection": _series(soup) or (product_lines[0] if product_lines else None),
            "categoryPath": list(
                tikicat_category_path(texture=texture, product_lines=product_lines)
            ),
            "variants": _variant_payloads(
                parent_id=parent_id,
                title=title,
                sizes=sizes,
                hero_image_url=hero_image_url,
            ),
            "parent": {
                "parent_product_id": parent_id,
                "canonical_url": product_url,
                "category_key": TIKICAT_CATEGORY_KEY,
                "features": features,
                "summary": summary,
                "description_markdown": body,
                "available_sizes": list(sizes),
                "texture": texture,
                "product_lines": list(product_lines),
                "site_filters": site_filters,
                "site_attributes": semantic_hints,
                "hero_image_url": hero_image_url,
            },
        }
        self._payload = payload
        return (
            EvidenceBlob(
                source="tikicat_dom_product",
                selector="main",
                index=-1,
                payload=payload,
            ),
        )

    def retailer_specific_fixes(
        self,
        parent: ParentProduct | None,
        variants: list[Variant],
        profile_name: str | None = None,
    ) -> None:
        if parent is None or not self._payload:
            return
        raw_parent = self._payload.get("parent")
        if not isinstance(raw_parent, Mapping):
            return

        parent_id = _clean_text(raw_parent.get("parent_product_id"))
        if parent_id:
            parent.parent_product_id = parent_id
        parent.brand_raw = TIKICAT_BRAND_NAME
        parent.brand_normalized = TIKICAT_BRAND_NAME

        title = _clean_text(self._payload.get("name"))
        if title:
            parent.title_raw = title
            parent.title_normalized = title
        product_url = _clean_text(raw_parent.get("canonical_url"))
        if product_url:
            parent.pdp_url = product_url

        category_path = self._payload.get("categoryPath")
        if _is_sequence(category_path):
            parent.category_path = tuple(
                text
                for item in category_path
                if (text := _clean_text(item)) is not None
            )

        for key in (
            "available_sizes",
            "category_key",
            "description_markdown",
            "hero_image_url",
            "product_lines",
            "summary",
            "texture",
        ):
            value = raw_parent.get(key)
            if _is_sequence(value):
                parent.extras[key] = [
                    item for item in value if item not in (None, "")
                ]
            elif (text := _clean_text(value)) is not None:
                parent.extras[key] = text

        for key in ("features", "site_filters"):
            value = raw_parent.get(key)
            if _is_sequence(value):
                parent.extras[key] = [
                    dict(item) if isinstance(item, Mapping) else item
                    for item in value
                    if item not in (None, "")
                ]

        site_attributes = raw_parent.get("site_attributes")
        if isinstance(site_attributes, Mapping):
            parent.extras["site_attributes"] = {
                str(key): list(value)
                for key, value in site_attributes.items()
                if _is_sequence(value)
            }
            hint_lines = [
                f"{key}: {', '.join(str(item) for item in values)}"
                for key, values in parent.extras["site_attributes"].items()
                if _is_sequence(values)
            ]
            if hint_lines:
                parent.extras.setdefault("features", [])
                if isinstance(parent.extras["features"], list):
                    parent.extras["features"].extend(hint_lines)

        hero_image_url = _clean_text(raw_parent.get("hero_image_url"))
        for variant in variants:
            if hero_image_url and not variant.hero_image_url:
                variant.hero_image_url = hero_image_url
            variant.extras.setdefault("category_key", TIKICAT_CATEGORY_KEY)
