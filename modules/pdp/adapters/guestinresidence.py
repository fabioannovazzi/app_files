from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import TypeGuard
from urllib.parse import urljoin

from bs4 import BeautifulSoup  # type: ignore[import]

from ..guestinresidence_catalog import (
    GUESTINRESIDENCE_BASE_URL,
    GUESTINRESIDENCE_BRAND_NAME,
    GUESTINRESIDENCE_CATEGORY_KEY,
    GUESTINRESIDENCE_RETAILER,
    guestinresidence_cashmere_scope_decision,
    guestinresidence_category_path,
    guestinresidence_feature_lines,
    guestinresidence_parent_id_from_url,
    guestinresidence_product_option_values,
    guestinresidence_product_text,
    guestinresidence_product_url,
    guestinresidence_semantic_attribute_hints,
)
from ..guestinresidence_filter_discovery import (
    guestinresidence_site_filters_for_product,
)
from ..models import EvidenceBlob, ParentProduct, Variant
from . import RetailerAdapter

__all__ = ["GuestInResidenceAdapter"]

_PRODUCT_JSON_MARKERS = (
    "_BISConfig.product =",
    "afterpay_product =",
    "window.measmerizeProduct =",
)
_TITLE_SUFFIX_RE = re.compile(r"\s*[|–-]\s*Guest\s+in\s+Residence.*$", re.IGNORECASE)


def _clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _is_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _absolute_url(value: object | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if text.startswith("//"):
        return f"https:{text}"
    return urljoin(GUESTINRESIDENCE_BASE_URL, text)


def _price_to_decimal_text(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return f"{Decimal(value) / Decimal(100):.2f}"
    if isinstance(value, float):
        return f"{Decimal(str(value)) / Decimal(100):.2f}"
    text = _clean_text(value)
    if not text:
        return None
    try:
        amount = Decimal(text.replace("$", "").replace(",", ""))
    except InvalidOperation:
        return text
    if amount >= 1000 and "." not in text:
        amount = amount / Decimal(100)
    return f"{amount:.2f}"


def _parse_decimal(value: object | None) -> Decimal | None:
    text = _price_to_decimal_text(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _extract_meta(soup: BeautifulSoup, *selectors: str) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        value = _clean_text(node.get("content"))
        if value:
            return value
    return None


def _canonical_url(soup: BeautifulSoup) -> str | None:
    node = soup.select_one("link[rel='canonical']")
    if node is not None:
        href = _absolute_url(node.get("href"))
        if href:
            return href
    return _absolute_url(_extract_meta(soup, "meta[property='og:url']"))


def _json_after_marker(text: str, marker: str) -> Mapping[str, object] | None:
    index = text.find(marker)
    if index < 0:
        return None
    fragment = text[index + len(marker) :].lstrip()
    try:
        payload, _end = json.JSONDecoder().raw_decode(fragment)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, Mapping) else None


def _extract_product_json(soup: BeautifulSoup) -> Mapping[str, object]:
    for script in soup.select("script"):
        text = script.string or script.get_text()
        if not text:
            continue
        for marker in _PRODUCT_JSON_MARKERS:
            payload = _json_after_marker(text, marker)
            if payload is not None and payload.get("handle"):
                return payload

    for script in soup.select("script[type='application/ld+json']"):
        text = script.string or script.get_text()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        for item in _iter_json_objects(payload):
            raw_type = item.get("@type")
            type_values = raw_type if _is_sequence(raw_type) else (raw_type,)
            if any(str(value).casefold() == "product" for value in type_values):
                return item
    return {}


def _iter_json_objects(value: object) -> Sequence[Mapping[str, object]]:
    objects: list[Mapping[str, object]] = []

    def walk(node: object) -> None:
        if isinstance(node, Mapping):
            objects.append(node)
            for child in node.values():
                walk(child)
        elif _is_sequence(node):
            for child in node:
                walk(child)

    walk(value)
    return objects


def _title_from_product(
    soup: BeautifulSoup,
    product: Mapping[str, object],
) -> str | None:
    for value in (
        _clean_text(product.get("title") or product.get("name")),
        (
            _clean_text(soup.select_one("h1").get_text(" ", strip=True))
            if soup.select_one("h1")
            else None
        ),
        _extract_meta(soup, "meta[property='og:title']", "meta[name='title']"),
    ):
        if value:
            return _TITLE_SUFFIX_RE.sub("", value).strip()
    return None


def _series_from_product(
    product: Mapping[str, object], title: str | None
) -> str | None:
    tags = product.get("tags")
    if _is_sequence(tags):
        for tag in tags:
            text = _clean_text(tag)
            if text and text.lower().startswith("nvgroup_"):
                return text.removeprefix("nvgroup_").replace("_", " ").strip().title()
    if not title:
        return None
    return title.split(" - ", 1)[0].strip() or None


def _first_image(product: Mapping[str, object]) -> str | None:
    for key in ("featured_image", "image"):
        url = _absolute_url(product.get(key))
        if url:
            return url
    images = product.get("images")
    if _is_sequence(images):
        for image in images:
            url = _absolute_url(image)
            if url:
                return url
    media = product.get("media")
    if _is_sequence(media):
        for item in media:
            if not isinstance(item, Mapping):
                continue
            url = _absolute_url(item.get("src"))
            if url:
                return url
            preview = item.get("preview_image")
            if isinstance(preview, Mapping):
                url = _absolute_url(preview.get("src"))
                if url:
                    return url
    return None


def _variant_color(
    variant: Mapping[str, object], product: Mapping[str, object]
) -> str | None:
    option_names = product.get("options")
    if _is_sequence(option_names):
        for index, raw_name in enumerate(option_names, start=1):
            if isinstance(raw_name, Mapping):
                name = _clean_text(raw_name.get("name"))
            else:
                name = _clean_text(raw_name)
            if str(name or "").casefold() == "color":
                return _clean_text(variant.get(f"option{index}"))
    return _clean_text(variant.get("option1"))


def _variant_size(
    variant: Mapping[str, object], product: Mapping[str, object]
) -> str | None:
    option_names = product.get("options")
    if _is_sequence(option_names):
        for index, raw_name in enumerate(option_names, start=1):
            if isinstance(raw_name, Mapping):
                name = _clean_text(raw_name.get("name"))
            else:
                name = _clean_text(raw_name)
            if str(name or "").casefold() == "size":
                return _clean_text(variant.get(f"option{index}"))
    return _clean_text(variant.get("option2"))


def _variant_image_url(
    variant: Mapping[str, object],
    default_image: str | None,
) -> str | None:
    featured = variant.get("featured_image")
    if isinstance(featured, Mapping):
        image = _absolute_url(featured.get("src"))
        if image:
            return image
    return default_image


def _variant_payloads(product: Mapping[str, object]) -> list[dict[str, object]]:
    variants = product.get("variants")
    default_image = _first_image(product)
    if not _is_sequence(variants):
        return [
            {
                "id": _clean_text(product.get("handle") or product.get("id"))
                or "default",
                "color": next(
                    iter(guestinresidence_product_option_values(product, "Color")),
                    None,
                ),
                "size": None,
                "price": _price_to_decimal_text(product.get("price")),
                "currency": "USD",
                "barcode": None,
                "image": default_image,
                "availability": (
                    "in_stock" if product.get("available") else "out_of_stock"
                ),
                "attributes": {},
            }
        ]

    payloads: list[dict[str, object]] = []
    for variant in variants:
        if not isinstance(variant, Mapping):
            continue
        variant_id = _clean_text(variant.get("id"))
        if not variant_id:
            continue
        color = _variant_color(variant, product)
        size = _variant_size(variant, product)
        image = _variant_image_url(variant, default_image)
        payloads.append(
            {
                "id": variant_id,
                "sku": _clean_text(variant.get("sku")),
                "color": color,
                "shade": color,
                "size": size,
                "price": _price_to_decimal_text(variant.get("price")),
                "currency": "USD",
                "barcode": _clean_text(variant.get("barcode")),
                "image": image,
                "availability": (
                    "in_stock" if bool(variant.get("available")) else "out_of_stock"
                ),
                "attributes": {
                    "color": color,
                    "size": size,
                    "public_title": _clean_text(variant.get("public_title")),
                },
            }
        )
    return payloads


class GuestInResidenceAdapter(RetailerAdapter):
    """Parse Guest in Residence Shopify PDPs."""

    retailer = GUESTINRESIDENCE_RETAILER

    def __init__(self) -> None:
        self._payload: Mapping[str, object] | None = None

    def primary_id_from_url(self, url: str) -> str | None:
        return guestinresidence_parent_id_from_url(url)

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        soup = BeautifulSoup(html, "lxml")
        product = _extract_product_json(soup)
        canonical_url = _canonical_url(soup)
        parent_id = guestinresidence_parent_id_from_url(canonical_url or "")
        handle = _clean_text(product.get("handle"))
        if not parent_id and handle:
            parent_id = handle.lower()
        if not parent_id:
            self._payload = None
            return ()

        title = _title_from_product(soup, product)
        body_text = guestinresidence_product_text(product)
        features = guestinresidence_feature_lines(product)
        include, include_reason = guestinresidence_cashmere_scope_decision(product)
        product_url = guestinresidence_product_url(parent_id)
        site_filters = guestinresidence_site_filters_for_product(product)
        semantic_hints = guestinresidence_semantic_attribute_hints(product)
        variants = _variant_payloads(product)
        payload: dict[str, object] = {
            "id": parent_id,
            "handle": parent_id,
            "brand": _clean_text(product.get("vendor")) or GUESTINRESIDENCE_BRAND_NAME,
            "name": title,
            "description": body_text,
            "collection": _series_from_product(product, title),
            "categoryPath": list(
                guestinresidence_category_path(GUESTINRESIDENCE_CATEGORY_KEY)
            ),
            "variants": variants,
            "parent": {
                "parent_product_id": parent_id,
                "canonical_url": product_url,
                "category_key": GUESTINRESIDENCE_CATEGORY_KEY,
                "product_type": _clean_text(
                    product.get("product_type") or product.get("type")
                ),
                "tags": [
                    text
                    for tag in (
                        product.get("tags") if _is_sequence(product.get("tags")) else []
                    )
                    if (text := _clean_text(tag)) is not None
                ],
                "features": features,
                "summary": features[0] if features else body_text,
                "description_markdown": body_text,
                "site_filters": site_filters,
                "site_attributes": semantic_hints,
                "scope_included": include,
                "scope_reason": include_reason,
                "hero_image_url": _first_image(product),
            },
        }
        self._payload = payload
        return (
            EvidenceBlob(
                source="guestinresidence_shopify_product",
                selector="script",
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
        parent.brand_raw = GUESTINRESIDENCE_BRAND_NAME
        parent.brand_normalized = GUESTINRESIDENCE_BRAND_NAME

        title = _clean_text(self._payload.get("name"))
        if title:
            parent.title_raw = title
            parent.title_normalized = title

        category_path = self._payload.get("categoryPath")
        if _is_sequence(category_path):
            parent.category_path = tuple(
                text
                for item in category_path
                if (text := _clean_text(item)) is not None
            )

        canonical_url = _clean_text(raw_parent.get("canonical_url"))
        if canonical_url:
            parent.pdp_url = canonical_url
            parent.extras["canonical_url"] = canonical_url

        for key in (
            "category_key",
            "description_markdown",
            "hero_image_url",
            "product_type",
            "scope_reason",
            "summary",
        ):
            value = raw_parent.get(key)
            if (text := _clean_text(value)) is not None:
                parent.extras[key] = text
        scope_included = raw_parent.get("scope_included")
        if isinstance(scope_included, bool):
            parent.extras["scope_included"] = scope_included

        for key in ("features", "site_filters", "tags"):
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

        variant_payloads = self._payload.get("variants")
        payload_by_id: dict[str, Mapping[str, object]] = {}
        if _is_sequence(variant_payloads):
            payload_by_id = {
                str(item.get("id")): item
                for item in variant_payloads
                if isinstance(item, Mapping) and item.get("id")
            }

        hero_image = _clean_text(raw_parent.get("hero_image_url"))
        for index, variant in enumerate(variants):
            variant.retailer = self.retailer
            variant.parent_product_id = parent.parent_product_id
            variant.source_index = index
            payload = payload_by_id.get(str(variant.variant_id))
            if payload is None:
                if hero_image and not variant.hero_image_url:
                    variant.hero_image_url = hero_image
                continue
            color = _clean_text(payload.get("color") or payload.get("shade"))
            if color:
                variant.shade_name_raw = color
                variant.shade_name_normalized = color
            size = _clean_text(payload.get("size"))
            if size:
                variant.size_text_raw = size
            price = _clean_text(payload.get("price"))
            if price:
                variant.price_raw = price
                variant.price = _parse_decimal(price)
            currency = _clean_text(payload.get("currency"))
            if currency:
                variant.currency = currency
            barcode = _clean_text(payload.get("barcode"))
            if barcode:
                variant.barcode = barcode
            image = _clean_text(payload.get("image")) or hero_image
            if image:
                variant.swatch_image_url = image
                variant.hero_image_url = image
            availability = _clean_text(payload.get("availability"))
            if availability:
                variant.availability = availability
            attributes = payload.get("attributes")
            if isinstance(attributes, Mapping):
                variant.extras["attributes"] = dict(attributes)
