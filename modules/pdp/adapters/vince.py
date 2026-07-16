from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import TypeGuard
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup  # type: ignore[import]

from ..models import EvidenceBlob, ParentProduct, Variant
from ..vince_catalog import (
    VINCE_BASE_URL,
    VINCE_BRAND_NAME,
    VINCE_CATEGORY_KEY,
    VINCE_RETAILER,
    vince_category_path,
    vince_parent_id_from_url,
    vince_product_url,
    vince_semantic_attribute_hints,
    vince_style_id_from_parent_id,
)
from ..vince_filter_discovery import vince_site_filters_from_values
from . import RetailerAdapter

__all__ = ["VinceAdapter"]

_TITLE_SUFFIX_RE = re.compile(
    r"\s+(?:in\s+Sneakers\s+)?[|–-]\s*Vince.*$", re.IGNORECASE
)


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
    return urljoin(VINCE_BASE_URL, text)


def _parse_decimal(value: object | None) -> Decimal | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return Decimal(text.replace("$", "").replace(",", ""))
    except InvalidOperation:
        return None


def _meta_content(soup: BeautifulSoup, *selectors: str) -> str | None:
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
            return href.split("?", 1)[0]
    url = _meta_content(soup, "meta[property='og:url']")
    if url:
        return _absolute_url(url.split("?", 1)[0])
    return None


def _iter_json_objects(value: object) -> list[Mapping[str, object]]:
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


def _extract_jsonld_product(soup: BeautifulSoup) -> Mapping[str, object]:
    for script in soup.select("script[type='application/ld+json']"):
        text = script.string or script.get_text()
        if not text or not text.strip():
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


def _title_from_sources(
    soup: BeautifulSoup,
    product: Mapping[str, object],
) -> str | None:
    for value in (
        _clean_text(product.get("name")),
        (
            _clean_text(soup.select_one("h1.product-name").get_text(" ", strip=True))
            if soup.select_one("h1.product-name")
            else None
        ),
        _meta_content(soup, "meta[property='og:title']", "meta[name='twitter:title']"),
        _clean_text(soup.title.string if soup.title else None),
    ):
        if value:
            value = re.sub(r"^Buy\s+", "", value, flags=re.IGNORECASE)
            value = re.sub(r"\s+for\s+[A-Z]{3}\s+[0-9,.]+.*$", "", value)
            return _TITLE_SUFFIX_RE.sub("", value).strip()
    return None


def _first_image_url(value: object) -> str | None:
    if isinstance(value, str):
        return _absolute_url(value)
    if isinstance(value, Mapping):
        for key in ("url", "contentUrl"):
            if url := _absolute_url(value.get(key)):
                return url
    if _is_sequence(value):
        for item in value:
            if url := _first_image_url(item):
                return url
    return None


def _offer(product: Mapping[str, object]) -> Mapping[str, object]:
    raw_offer = product.get("offers")
    if isinstance(raw_offer, Mapping):
        return raw_offer
    if _is_sequence(raw_offer):
        for item in raw_offer:
            if isinstance(item, Mapping):
                return item
    return {}


def _price_and_currency(
    soup: BeautifulSoup,
    product: Mapping[str, object],
) -> tuple[str | None, str | None]:
    price = _meta_content(soup, "meta[property='product:price.amount']")
    currency = _meta_content(soup, "meta[property='product:price.currency']")
    offer = _offer(product)
    if not price:
        price = _clean_text(offer.get("price")) or _clean_text(product.get("price"))
    if not currency:
        currency = _clean_text(offer.get("priceCurrency")) or _clean_text(
            product.get("priceCurrency")
        )
    return price, currency


def _availability(product: Mapping[str, object]) -> str | None:
    raw = _clean_text(_offer(product).get("availability")) or _clean_text(
        product.get("availability")
    )
    if not raw:
        return None
    lowered = raw.casefold()
    if "instock" in lowered or "in stock" in lowered:
        return "in_stock"
    if "outofstock" in lowered or "out of stock" in lowered:
        return "out_of_stock"
    return raw


def _text_lines_from_nodes(soup: BeautifulSoup, selectors: Sequence[str]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        for node in soup.select(selector):
            text = _clean_text(node.get_text(" ", strip=True))
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            lines.append(text)
    return lines


def _description_from_soup(
    soup: BeautifulSoup,
    product: Mapping[str, object],
) -> str | None:
    detail = _text_lines_from_nodes(soup, (".product-info-details",))
    if detail:
        return detail[0]
    return _clean_text(product.get("description")) or _meta_content(
        soup,
        "meta[name='description']",
        "meta[property='og:description']",
    )


def _feature_lines(soup: BeautifulSoup) -> list[str]:
    return _text_lines_from_nodes(
        soup,
        (
            "#collapsible-product-details li",
            "#collapsible-product-details p",
            "#collapsible-product-fabric-care p",
        ),
    )


def _selected_color(
    soup: BeautifulSoup,
    product: Mapping[str, object],
    *,
    requested_parent_id: str | None = None,
) -> str | None:
    requested_color = _color_from_requested_parent_id(soup, requested_parent_id)
    if requested_color:
        return requested_color
    for value in (
        _clean_text(product.get("color")),
        (
            _clean_text(
                soup.select_one(".color-selected-value").get_text(" ", strip=True)
            )
            if soup.select_one(".color-selected-value")
            else None
        ),
    ):
        if value:
            return value.upper()
    return None


def _compact_color(value: object | None) -> str:
    return re.sub(r"[^A-Z0-9]+", "", _clean_text(value) or "").upper()


def _color_from_requested_parent_id(
    soup: BeautifulSoup,
    requested_parent_id: str | None,
) -> str | None:
    style_id = vince_style_id_from_parent_id(requested_parent_id)
    if not requested_parent_id or not style_id:
        return None
    suffix = str(requested_parent_id).upper().removeprefix(style_id)
    if not suffix:
        return None
    for node in soup.select(".color-swatch[title], .color-attribute[aria-label]"):
        candidates = (
            _clean_text(node.get("title")),
            re.sub(
                r"^Select\s+(?:Color|[^A-Z]+)\s+",
                "",
                _clean_text(node.get("aria-label")) or "",
                flags=re.IGNORECASE,
            ),
        )
        for candidate in candidates:
            if candidate and _compact_color(candidate) == suffix:
                return candidate.upper()
    return None


def _color_options_by_suffix(soup: BeautifulSoup) -> dict[str, str]:
    options: dict[str, str] = {}
    for node in soup.select(".color-swatch[title], .color-attribute[aria-label]"):
        for value in (
            _clean_text(node.get("title")),
            re.sub(
                r"^Select\s+(?:Color\s+)?",
                "",
                _clean_text(node.get("aria-label")) or "",
                flags=re.IGNORECASE,
            ),
        ):
            compact = _compact_color(value)
            if compact and value:
                options.setdefault(compact, value.upper())
    return options


def _color_from_parent_suffix(
    *,
    color_options: Mapping[str, object],
    parent_id: str | None,
    fallback: str | None,
) -> str | None:
    style_id = vince_style_id_from_parent_id(parent_id)
    if parent_id and style_id:
        suffix = str(parent_id).upper().removeprefix(style_id)
        if suffix:
            value = _clean_text(color_options.get(suffix))
            if value:
                return value
    return fallback


def _slug_from_url(url: str | None) -> str | None:
    parsed = urlparse(str(url or ""))
    match = re.search(r"/product/(?P<slug>.+)-[A-Z0-9]+\.html$", parsed.path)
    if not match:
        return None
    return match.group("slug")


def _available_sizes(
    soup: BeautifulSoup,
    product: Mapping[str, object],
) -> tuple[str, ...]:
    values: list[str] = []
    raw_size = product.get("size")
    if isinstance(raw_size, str):
        values.append(raw_size)
    elif _is_sequence(raw_size):
        values.extend(str(item) for item in raw_size if _clean_text(item))

    if not values:
        for node in soup.select(
            ".attribute-container[data-attr='size'] .size-value.selectable"
        ):
            value = _clean_text(node.get("data-attr-value") or node.get("title"))
            if value:
                values.append(value)

    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return tuple(out)


def _is_new(soup: BeautifulSoup) -> bool:
    badge_text = " ".join(
        text
        for node in soup.select(".product-badges, .product-badge")
        if (text := _clean_text(node.get_text(" ", strip=True)))
    )
    return "new" in badge_text.casefold().split()


def _product_id_from_dom(soup: BeautifulSoup) -> str | None:
    for value in (
        (
            _clean_text(soup.select_one(".product-detail[data-pid]").get("data-pid"))
            if soup.select_one(".product-detail[data-pid]")
            else None
        ),
        (
            _clean_text(soup.select_one(".product-id").get_text(" ", strip=True))
            if soup.select_one(".product-id")
            else None
        ),
    ):
        if value:
            return value.upper()
    return None


def _variant_payloads(
    *,
    parent_id: str,
    color: str | None,
    sizes: Sequence[str],
    price: str | None,
    currency: str | None,
    image: str | None,
    availability: str | None,
) -> list[dict[str, object]]:
    if not sizes:
        return [
            {
                "variant_id": parent_id,
                "color": color,
                "size": None,
                "price": price,
                "currency": currency,
                "image": image,
                "availability": availability,
            }
        ]
    return [
        {
            "variant_id": f"{parent_id}-{str(size).replace(' ', '')}",
            "color": color,
            "size": size,
            "price": price,
            "currency": currency,
            "image": image,
            "availability": availability,
        }
        for size in sizes
    ]


class VinceAdapter(RetailerAdapter):
    """Parse Vince Salesforce Commerce Cloud sneaker PDPs."""

    retailer = VINCE_RETAILER

    def __init__(self) -> None:
        self._payload: Mapping[str, object] | None = None
        self._requested_parent_id: str | None = None

    def primary_id_from_url(self, url: str) -> str | None:
        self._requested_parent_id = vince_parent_id_from_url(url)
        return self._requested_parent_id

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        soup = BeautifulSoup(html, "lxml")
        product = _extract_jsonld_product(soup)
        canonical_url = _canonical_url(soup)
        parent_id = (
            self._requested_parent_id
            or vince_parent_id_from_url(canonical_url or "")
            or _clean_text(product.get("sku") or product.get("mpn"))
        )
        parent_id = (parent_id or _product_id_from_dom(soup) or "").upper()
        if not parent_id:
            self._payload = None
            return ()

        title = _title_from_sources(soup, product)
        description = _description_from_soup(soup, product)
        features = _feature_lines(soup)
        color = _selected_color(
            soup,
            product,
            requested_parent_id=parent_id,
        )
        sizes = _available_sizes(soup, product)
        price, currency = _price_and_currency(soup, product)
        image = _first_image_url(product.get("image")) or _meta_content(
            soup,
            "meta[property='og:image']",
            "meta[name='twitter:image']",
        )
        image = _absolute_url(image)
        availability = _availability(product)
        material = _clean_text(product.get("material"))
        site_filters = vince_site_filters_from_values(
            color=color,
            sizes=sizes,
            is_new=_is_new(soup),
        )
        site_attributes = vince_semantic_attribute_hints(
            title=title,
            description=description,
            material=material,
            detail_lines=tuple(features),
        )
        canonical_product_url = vince_product_url(
            parent_id, _slug_from_url(canonical_url)
        )
        payload: dict[str, object] = {
            "parent": {
                "parent_product_id": parent_id,
                "style_id": vince_style_id_from_parent_id(parent_id),
                "brand": VINCE_BRAND_NAME,
                "title": title,
                "summary": description,
                "description": description,
                "material": material,
                "category_key": VINCE_CATEGORY_KEY,
                "category_path": list(vince_category_path(VINCE_CATEGORY_KEY)),
                "canonical_url": canonical_product_url,
                "features": features,
                "color_options": _color_options_by_suffix(soup),
                "site_filters": site_filters,
                "site_attributes": site_attributes,
                "hero_image_url": image,
                "is_new": _is_new(soup),
            },
            "variants": _variant_payloads(
                parent_id=parent_id,
                color=color,
                sizes=sizes,
                price=price,
                currency=currency,
                image=image,
                availability=availability,
            ),
        }
        self._payload = payload
        return (
            EvidenceBlob(
                source="vince_dom",
                selector="body",
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

        requested_parent_id = parent.parent_product_id
        raw_parent_id = _clean_text(raw_parent.get("parent_product_id"))
        parent_id = requested_parent_id or raw_parent_id
        if parent_id:
            parent.parent_product_id = parent_id
        parent.brand_raw = VINCE_BRAND_NAME
        parent.brand_normalized = VINCE_BRAND_NAME

        title = _clean_text(raw_parent.get("title"))
        if title:
            parent.title_raw = title
            parent.title_normalized = title

        category_path = raw_parent.get("category_path")
        if _is_sequence(category_path):
            parent.category_path = tuple(
                text
                for item in category_path
                if (text := _clean_text(item)) is not None
            )
        canonical_url = _clean_text(raw_parent.get("canonical_url"))
        if canonical_url and parent_id:
            parent.pdp_url = vince_product_url(parent_id, _slug_from_url(canonical_url))
            parent.extras["canonical_url"] = parent.pdp_url

        for key in (
            "category_key",
            "description",
            "hero_image_url",
            "material",
            "style_id",
            "summary",
        ):
            value = _clean_text(raw_parent.get(key))
            if value:
                parent.extras[key] = value
        is_new = raw_parent.get("is_new")
        if isinstance(is_new, bool):
            parent.extras["is_new"] = is_new

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

        variant_payloads = self._payload.get("variants")
        payload_list: list[Mapping[str, object]] = []
        payload_by_id: dict[str, Mapping[str, object]] = {}
        if _is_sequence(variant_payloads):
            payload_list = [
                item for item in variant_payloads if isinstance(item, Mapping)
            ]
            payload_by_id = {
                str(item.get("variant_id")): item
                for item in payload_list
                if item.get("variant_id")
            }
        color_options = raw_parent.get("color_options")
        if not isinstance(color_options, Mapping):
            color_options = {}
        requested_color = _color_from_parent_suffix(
            color_options=color_options,
            parent_id=parent.parent_product_id,
            fallback=None,
        )
        if parent_id and payload_list:
            parent.extras["site_filters"] = vince_site_filters_from_values(
                color=requested_color or payload_list[0].get("color"),
                sizes=[payload.get("size") for payload in payload_list],
                is_new=bool(raw_parent.get("is_new")),
            )
        hero_image = _clean_text(raw_parent.get("hero_image_url"))
        for index, variant in enumerate(variants):
            variant.retailer = self.retailer
            variant.parent_product_id = parent.parent_product_id
            variant.source_index = index
            payload = payload_by_id.get(variant.variant_id)
            if payload is None and index < len(payload_list):
                payload = payload_list[index]
            if payload is None:
                if hero_image and not variant.hero_image_url:
                    variant.hero_image_url = hero_image
                continue
            size = _clean_text(payload.get("size"))
            if parent_id:
                variant.variant_id = (
                    f"{parent.parent_product_id}-{size.replace(' ', '')}"
                    if size
                    else parent.parent_product_id
                )
            color = requested_color or _clean_text(payload.get("color"))
            if color:
                variant.shade_name_raw = color
                variant.shade_name_normalized = color
            if size:
                variant.size_text_raw = size
            price = _clean_text(payload.get("price"))
            if price:
                variant.price_raw = price
                variant.price = _parse_decimal(price)
            currency = _clean_text(payload.get("currency"))
            if currency:
                variant.currency = currency
            image = _clean_text(payload.get("image")) or hero_image
            if image:
                variant.swatch_image_url = image
                variant.hero_image_url = image
            availability = _clean_text(payload.get("availability"))
            if availability:
                variant.availability = availability
