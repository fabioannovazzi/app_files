from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag  # type: ignore[import]

from ..lorealparis_catalog import (
    LOREALPARIS_BASE_URL,
    LOREALPARIS_BRAND_NAME,
    LOREALPARIS_RETAILER,
    lorealparis_category_from_url,
    lorealparis_category_path,
    lorealparis_family_slug_from_slug,
    lorealparis_family_url,
    lorealparis_parent_id_from_url,
)
from ..lorealparis_filter_discovery import extract_lorealparis_site_tags
from ..models import EvidenceBlob, ParentProduct, Variant
from ..normalization import normalize_text
from ..profile import FieldNormalizationSpec

__all__ = ["LorealParisAdapter"]

_TITLE_SUFFIX_RE = re.compile(r"\s*[-|]\s*L['O]real Paris.*$", re.IGNORECASE)
_SHADE_NUMBER_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s+[A-Za-z][A-Za-z\s-]*")
_USELESS_SHADE_TEXT = {
    "",
    "view product",
    "try it",
    "live try on",
    "buy online",
    "add to cart",
}


def _clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _meta_content(soup: BeautifulSoup, *selectors: str) -> str | None:
    for selector in selectors:
        element = soup.select_one(selector)
        if element is None:
            continue
        content = _clean_text(element.get("content"))
        if content:
            return content
    return None


def _canonical_url(soup: BeautifulSoup) -> str | None:
    element = soup.select_one("link[rel='canonical']")
    if element is not None:
        href = _clean_text(element.get("href"))
        if href:
            return urljoin(LOREALPARIS_BASE_URL, href)
    return _meta_content(soup, "meta[property='og:url']")


def _extract_jsonld_products(soup: BeautifulSoup) -> list[Mapping[str, object]]:
    products: list[Mapping[str, object]] = []

    def _walk(node: object) -> None:
        if isinstance(node, Mapping):
            raw_type = node.get("@type") or node.get("type")
            type_values = (
                raw_type
                if isinstance(raw_type, Sequence)
                and not isinstance(raw_type, (str, bytes))
                else (raw_type,)
            )
            if any(str(item).lower() == "product" for item in type_values):
                products.append(node)
            for value in node.values():
                _walk(value)
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            for item in node:
                _walk(item)

    for script in soup.select("script[type='application/ld+json']"):
        text = script.string or script.get_text()
        if not text or not text.strip():
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        _walk(payload)
    return products


def _first_product_jsonld(soup: BeautifulSoup) -> Mapping[str, object]:
    products = _extract_jsonld_products(soup)
    return products[0] if products else {}


def _jsonld_offer(product: Mapping[str, object]) -> Mapping[str, object]:
    offer = product.get("offers")
    if isinstance(offer, Mapping):
        return offer
    if isinstance(offer, Sequence) and not isinstance(offer, (str, bytes)):
        for item in offer:
            if isinstance(item, Mapping):
                return item
    return {}


def _first_image_url(value: object) -> str | None:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, Mapping):
        for key in ("url", "contentUrl"):
            url = _clean_text(value.get(key))
            if url:
                return url
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            url = _first_image_url(item)
            if url:
                return url
    return None


def _extract_title(soup: BeautifulSoup, product: Mapping[str, object]) -> str | None:
    for source in (
        lambda: (
            _clean_text(soup.select_one("h1").get_text(" ", strip=True))
            if soup.select_one("h1")
            else None
        ),
        lambda: _clean_text(product.get("name")),
        lambda: _meta_content(soup, "meta[property='og:title']"),
        lambda: _clean_text(soup.title.string if soup.title else None),
    ):
        value = source()
        if value:
            return _TITLE_SUFFIX_RE.sub("", value).strip()
    return None


def _extract_product_details(soup: BeautifulSoup) -> list[str]:
    lines = [
        line.strip()
        for line in soup.get_text("\n", strip=True).splitlines()
        if line.strip()
    ]
    details: list[str] = []
    collecting = False
    stop_markers = {
        "ingredients",
        "how to use",
        "makeup tryon",
        "try before you buy",
        "frequently bought together",
        "questions",
        "reviews",
        "tab component skipped",
    }
    for line in lines:
        normalized = line.strip().lower()
        if normalized == "product details":
            collecting = True
            continue
        if not collecting:
            continue
        if normalized in stop_markers or normalized.startswith("shop this"):
            break
        if line not in details:
            details.append(line)
    return details


def _extract_price_and_currency(
    product: Mapping[str, object],
) -> tuple[str | None, str | None]:
    offer = _jsonld_offer(product)
    price = _clean_text(offer.get("price"))
    if not price:
        price = _clean_text(product.get("price"))
    currency = _clean_text(offer.get("priceCurrency")) or _clean_text(
        product.get("priceCurrency")
    )
    return price, currency


def _availability_from_product(product: Mapping[str, object]) -> str | None:
    offer = _jsonld_offer(product)
    raw = _clean_text(offer.get("availability")) or _clean_text(
        product.get("availability")
    )
    if not raw:
        return None
    lowered = raw.lower()
    if "instock" in lowered or "in stock" in lowered:
        return "in_stock"
    if "outofstock" in lowered or "out of stock" in lowered:
        return "out_of_stock"
    return raw


def _image_from_element(anchor: Tag) -> str | None:
    image = anchor.select_one("img")
    if image is None:
        return None
    for key in ("src", "data-src", "data-original", "data-lazy-src"):
        value = _clean_text(image.get(key))
        if value:
            return urljoin(LOREALPARIS_BASE_URL, value)
    srcset = _clean_text(image.get("srcset"))
    if srcset:
        first = srcset.split(",", 1)[0].strip().split(" ", 1)[0]
        if first:
            return urljoin(LOREALPARIS_BASE_URL, first)
    return None


def _candidate_texts(anchor: Tag) -> list[str]:
    texts: list[str] = []
    for key in (
        "data-color",
        "data-colour",
        "data-color-name",
        "data-shade",
        "aria-label",
        "title",
    ):
        text = _clean_text(anchor.get(key))
        if text:
            texts.append(text)
    text = _clean_text(anchor.get_text(" ", strip=True))
    if text:
        texts.append(text)
    image = anchor.select_one("img")
    if image is not None:
        alt = _clean_text(image.get("alt"))
        if alt:
            texts.append(alt)
    return texts


def _shade_from_slug(parent_id: str, variant_slug: str) -> str | None:
    suffix = variant_slug.removeprefix(parent_id).strip("-")
    if not suffix:
        return None
    return " ".join(part.capitalize() for part in suffix.split("-") if part)


def _clean_shade_name(text: str, *, parent_id: str, variant_slug: str) -> str | None:
    cleaned = text.replace(variant_slug, " ")
    cleaned = cleaned.replace(parent_id, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|:")
    if not cleaned or cleaned.lower() in _USELESS_SHADE_TEXT:
        return None
    match = _SHADE_NUMBER_RE.search(cleaned)
    if match:
        return match.group(0).strip()
    if len(cleaned) <= 60 and any(char.isalpha() for char in cleaned):
        return cleaned
    return None


def _variant_from_anchor(
    anchor: Tag,
    *,
    parent_id: str,
    category_key: str,
    default_price: str | None,
    default_currency: str | None,
    default_image: str | None,
    default_availability: str | None,
) -> dict[str, object] | None:
    href = _clean_text(anchor.get("href"))
    if not href:
        return None
    url = urljoin(LOREALPARIS_BASE_URL, href)
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 4 or path_parts[:3] != ["makeup", "face", category_key]:
        return None
    variant_slug = path_parts[3].lower()
    if lorealparis_family_slug_from_slug(variant_slug) != parent_id:
        return None

    shade_name = None
    for text in _candidate_texts(anchor):
        shade_name = _clean_shade_name(
            text,
            parent_id=parent_id,
            variant_slug=variant_slug,
        )
        if shade_name:
            break
    if not shade_name:
        shade_name = _shade_from_slug(parent_id, variant_slug)

    image_url = _image_from_element(anchor)
    return {
        "variant_id": variant_slug,
        "shade_name": shade_name,
        "price": default_price,
        "currency": default_currency,
        "swatch_image": image_url,
        "hero_image": image_url or default_image,
        "availability": default_availability,
        "url": url,
    }


def _extract_variants(
    soup: BeautifulSoup,
    *,
    canonical_url: str | None,
    parent_id: str,
    category_key: str,
    product: Mapping[str, object],
) -> list[dict[str, object]]:
    default_price, default_currency = _extract_price_and_currency(product)
    default_image = _first_image_url(product.get("image"))
    if default_image:
        default_image = urljoin(LOREALPARIS_BASE_URL, default_image)
    default_availability = _availability_from_product(product)

    variants_by_id: dict[str, dict[str, object]] = {}
    for anchor in soup.select("a[href]"):
        variant = _variant_from_anchor(
            anchor,
            parent_id=parent_id,
            category_key=category_key,
            default_price=default_price,
            default_currency=default_currency,
            default_image=default_image,
            default_availability=default_availability,
        )
        if variant is None:
            continue
        variant_id = str(variant["variant_id"])
        existing = variants_by_id.get(variant_id)
        if existing is None:
            variants_by_id[variant_id] = variant
            continue
        for key, value in variant.items():
            if existing.get(key) in (None, "", [], {}) and value not in (
                None,
                "",
                [],
                {},
            ):
                existing[key] = value

    canonical_parent = lorealparis_parent_id_from_url(canonical_url or "")
    if canonical_parent == parent_id and canonical_url:
        canonical_slug = urlparse(canonical_url).path.rstrip("/").split("/")[-1]
        variants_by_id.setdefault(
            canonical_slug,
            {
                "variant_id": canonical_slug,
                "shade_name": _shade_from_slug(parent_id, canonical_slug),
                "price": default_price,
                "currency": default_currency,
                "swatch_image": default_image,
                "hero_image": default_image,
                "availability": default_availability,
                "url": canonical_url,
            },
        )

    if not variants_by_id:
        variants_by_id[parent_id] = {
            "variant_id": parent_id,
            "shade_name": None,
            "price": default_price,
            "currency": default_currency,
            "swatch_image": default_image,
            "hero_image": default_image,
            "availability": default_availability,
            "url": canonical_url,
        }
    return sorted(variants_by_id.values(), key=lambda item: str(item["variant_id"]))


def _series_from_title(title: str | None) -> str | None:
    if not title:
        return None
    for prefix in ("Infallible", "True Match", "Lumi"):
        if title.lower().startswith(prefix.lower()):
            return prefix
    return None


def _parse_decimal(value: object | None) -> Decimal | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return Decimal(text.replace("$", "").replace(",", ""))
    except InvalidOperation:
        return None


class LorealParisAdapter:
    """Adapter for L'Oreal Paris USA face PDPs."""

    retailer = LOREALPARIS_RETAILER

    def __init__(self) -> None:
        self._payload: Mapping[str, object] | None = None

    def primary_id_from_url(self, url: str) -> str | None:
        return lorealparis_parent_id_from_url(url)

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        soup = BeautifulSoup(html, "lxml")
        canonical_url = _canonical_url(soup)
        category_key = lorealparis_category_from_url(canonical_url or "")
        product = _first_product_jsonld(soup)
        parent_id = lorealparis_parent_id_from_url(canonical_url or "")

        if not category_key:
            category_key = "bronzer" if "/bronzer/" in html.lower() else "blush"
        if not parent_id:
            title = _extract_title(soup, product)
            parent_id = lorealparis_family_slug_from_slug(
                normalize_text(
                    title,
                    FieldNormalizationSpec(trim=True, collapse_spaces=True),
                )
                or ""
            )
        if not parent_id:
            self._payload = None
            return ()

        title = _extract_title(soup, product)
        description = _clean_text(product.get("description")) or _meta_content(
            soup,
            "meta[name='description']",
            "meta[property='og:description']",
        )
        detail_lines = _extract_product_details(soup)
        summary = detail_lines[0] if detail_lines else description
        canonical_family_url = lorealparis_family_url(category_key, parent_id)
        variants = _extract_variants(
            soup,
            canonical_url=canonical_url,
            parent_id=parent_id,
            category_key=category_key,
            product=product,
        )
        payload: dict[str, object] = {
            "parent": {
                "parent_product_id": parent_id,
                "brand": LOREALPARIS_BRAND_NAME,
                "title": title,
                "summary": summary,
                "description": description,
                "series_label": _series_from_title(title),
                "category_key": category_key,
                "category_path": list(lorealparis_category_path(category_key)),
                "canonical_url": canonical_family_url,
                "site_tags": extract_lorealparis_site_tags(html),
                "features": detail_lines,
            },
            "variants": variants,
        }
        self._payload = payload
        return (
            EvidenceBlob(
                source="lorealparis_dom",
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

        parent_id = _clean_text(raw_parent.get("parent_product_id"))
        if parent_id:
            parent.parent_product_id = parent_id
        parent.brand_raw = LOREALPARIS_BRAND_NAME
        parent.brand_normalized = LOREALPARIS_BRAND_NAME

        title = _clean_text(raw_parent.get("title"))
        if title:
            parent.title_raw = title
            parent.title_normalized = title

        series = _clean_text(raw_parent.get("series_label"))
        if series:
            parent.series_label_raw = series

        category_path = raw_parent.get("category_path")
        if isinstance(category_path, Sequence) and not isinstance(
            category_path, (str, bytes)
        ):
            parent.category_path = tuple(
                text
                for item in category_path
                if (text := _clean_text(item)) is not None
            )
        canonical_url = _clean_text(raw_parent.get("canonical_url"))
        if canonical_url:
            parent.pdp_url = canonical_url
            parent.extras["canonical_url"] = canonical_url

        for key in ("summary", "description", "category_key"):
            value = _clean_text(raw_parent.get(key))
            if value:
                parent.extras[key] = value
        features = raw_parent.get("features")
        if isinstance(features, Sequence) and not isinstance(features, (str, bytes)):
            parent.extras["features"] = [
                text for item in features if (text := _clean_text(item)) is not None
            ]
        site_tags = raw_parent.get("site_tags")
        if isinstance(site_tags, Sequence) and not isinstance(site_tags, (str, bytes)):
            parent.extras["site_tags"] = [
                dict(item) for item in site_tags if isinstance(item, Mapping)
            ]

        variant_payloads = self._payload.get("variants")
        payload_by_id: dict[str, Mapping[str, object]] = {}
        if isinstance(variant_payloads, Sequence) and not isinstance(
            variant_payloads, (str, bytes)
        ):
            payload_by_id = {
                str(item.get("variant_id")): item
                for item in variant_payloads
                if isinstance(item, Mapping) and item.get("variant_id")
            }
        for index, variant in enumerate(variants):
            variant.retailer = self.retailer
            variant.parent_product_id = parent.parent_product_id
            payload = payload_by_id.get(variant.variant_id)
            if payload is None:
                continue
            shade = _clean_text(payload.get("shade_name"))
            if shade:
                variant.shade_name_raw = shade
            price = _clean_text(payload.get("price"))
            if price:
                variant.price_raw = price
                variant.price = _parse_decimal(price)
            currency = _clean_text(payload.get("currency"))
            if currency:
                variant.currency = currency
            swatch = _clean_text(payload.get("swatch_image"))
            if swatch:
                variant.swatch_image_url = swatch
            hero = _clean_text(payload.get("hero_image"))
            if hero:
                variant.hero_image_url = hero
            availability = _clean_text(payload.get("availability"))
            if availability:
                variant.availability = availability
            variant.source_index = index
            url = _clean_text(payload.get("url"))
            if url:
                variant.extras["url"] = url
