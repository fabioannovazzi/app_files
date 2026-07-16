from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from json import JSONDecodeError
from typing import Any, Mapping, Sequence

from bs4 import BeautifulSoup  # type: ignore[import]

from ..models import EvidenceBlob, ParentProduct, Variant
from . import RetailerAdapter

_LOGGER = logging.getLogger(__name__)

ASIN_FROM_URL = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})", re.IGNORECASE)
ASIN_FALLBACK = re.compile(r"\b([A-Z0-9]{10})\b")
ASIN_EXACT = re.compile(r"^[A-Z0-9]{10}$")
VIDEO_PLACEHOLDER_TITLES = {"video_title", "video_description"}
REVIEW_RATING_RE = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s+out of\s+[0-9]+",
    re.IGNORECASE,
)
REVIEW_DATE_RE = re.compile(r"\bon\s+(.+)$", re.IGNORECASE)


def _load_json(raw: str | None) -> Mapping[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
        if isinstance(payload, Mapping):
            return payload
        return None
    except JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        snippet = text[start : end + 1]
        try:
            payload = json.loads(snippet)
            if isinstance(payload, Mapping):
                return payload
        except JSONDecodeError:
            return None
    return None


def _price_to_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        cents = Decimal(value)
        if abs(cents) >= 100:
            cents = cents / Decimal("100")
        return f"{cents:.2f}"
    if isinstance(value, (float, Decimal)):
        amount = Decimal(str(value))
        return f"{amount:.2f}"
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit() or ch == ".")
        return digits or None
    if isinstance(value, Mapping):
        for key in ("amount", "price", "value", "raw"):
            if key in value:
                result = _price_to_string(value[key])
                if result:
                    return result
        for key in ("displayAmount", "formattedPrice", "priceString"):
            if key in value and isinstance(value[key], str):
                result = _price_to_string(value[key])
                if result:
                    return result
    return None


def _availability_label(metadata: Mapping[str, Any]) -> str | None:
    availability = metadata.get("availability")
    if isinstance(availability, str):
        availability = availability.strip().upper()
        if availability in {"NOW", "AVAILABLE", "IN_STOCK"}:
            return "InStock"
        if availability in {"OOS", "OUT_OF_STOCK"}:
            return "OutOfStock"
        if availability in {"LIMITED"}:
            return "Limited"
        if availability:
            return availability
    for key in ("isAvailable", "isBackorderable"):
        flag = metadata.get(key)
        if isinstance(flag, bool):
            return "InStock" if flag else "OutOfStock"
    return None


def _extract_images(metadata: Mapping[str, Any]) -> tuple[str | None, str | None]:
    images = metadata.get("images")
    hero = None
    swatch = None
    if isinstance(images, Mapping):
        hero_candidate = images.get("heroImage") or images.get("main")
        if isinstance(hero_candidate, str):
            hero = hero_candidate
        elif isinstance(hero_candidate, Mapping):
            hero = hero_candidate.get("imageUrl") or hero_candidate.get("large")
        swatch_candidate = images.get("swatchImage") or images.get("swatch")
        if isinstance(swatch_candidate, str):
            swatch = swatch_candidate
        elif isinstance(swatch_candidate, Mapping):
            swatch = (
                swatch_candidate.get("imageUrl")
                or swatch_candidate.get("large")
                or swatch_candidate.get("small")
            )
        if not swatch:
            swatch_images = images.get("swatchImages")
            if isinstance(swatch_images, Sequence) and not isinstance(
                swatch_images, (str, bytes)
            ):
                for item in swatch_images:
                    if isinstance(item, str):
                        swatch = item
                        break
                    if isinstance(item, Mapping):
                        candidate = item.get("imageUrl") or item.get("large")
                        if isinstance(candidate, str):
                            swatch = candidate
                            break
    return hero, swatch


def _normalize_brand_text(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    text = re.sub(r"^Visit the\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+Store$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^Brand:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip(" :-")
    return text or None


def _clean_review_text(raw: str | None) -> str | None:
    if not raw:
        return None
    text = " ".join(raw.split())
    return text or None


def _rating_from_text(raw: str | None) -> float | None:
    if not raw:
        return None
    match = REVIEW_RATING_RE.search(raw)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _created_date_from_text(raw: str | None) -> str | None:
    text = _clean_review_text(raw)
    if not text:
        return None
    match = REVIEW_DATE_RE.search(text)
    if match:
        return match.group(1).strip() or text
    return text


def _availability_from_dimension_state(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    state = value.strip().upper()
    if state in {"SELECTED", "AVAILABLE"}:
        return "InStock"
    if state in {"UNAVAILABLE", "OOS", "OUT_OF_STOCK"}:
        return "OutOfStock"
    if state in {"LIMITED"}:
        return "Limited"
    return None


class AmazonAdapter(RetailerAdapter):
    retailer = "amazon"

    def __init__(self) -> None:
        self._latest_parent_payload: Mapping[str, Any] | None = None
        self._product_ldjson: Mapping[str, Any] | None = None
        self._feature_bullets: list[str] = []
        self._dom_title: str | None = None
        self._dom_brand: str | None = None
        self._dom_hero_image: str | None = None
        self._embedded_reviews: list[dict[str, Any]] = []

    def primary_id_from_url(self, url: str) -> str | None:
        match = ASIN_FROM_URL.search(url)
        if match:
            return match.group(1).upper()
        fallback = ASIN_FALLBACK.search(url)
        if fallback:
            return fallback.group(1).upper()
        return None

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        soup = BeautifulSoup(html, "lxml")
        blobs: list[EvidenceBlob] = []
        self._latest_parent_payload = None
        self._product_ldjson = self._extract_product_ldjson(soup)
        self._feature_bullets = self._extract_feature_bullets(soup)
        self._dom_title = self._extract_dom_title(soup)
        self._dom_brand = self._extract_dom_brand(soup)
        self._dom_hero_image = self._extract_dom_hero_image(soup)
        self._embedded_reviews = self._extract_embedded_reviews(soup)

        state_payload = self._extract_twister_state(soup)
        if state_payload:
            normalized = self._normalize_twister_payload(state_payload)
            if normalized:
                payload: dict[str, Any] = {}
                variants = normalized.get("variants")
                if variants:
                    payload["variants"] = variants
                parent_payload = normalized.get("parent")
                if parent_payload:
                    payload["parent"] = parent_payload
                    self._latest_parent_payload = parent_payload
                if payload:
                    blobs.append(
                        EvidenceBlob(
                            source="amazon_variants",
                            selector="script[type='a-state']",
                            index=-(len(blobs) + 1),
                            payload=payload,
                        )
                    )

        return tuple(blobs)

    def retailer_specific_fixes(
        self,
        parent: ParentProduct | None,
        variants: list[Variant],
        profile_name: str | None = None,
    ) -> None:
        if parent is None:
            return

        canonical_parent_asin: str | None = None
        if self._dom_title:
            current = (parent.title_raw or "").strip().lower()
            if not current or current in VIDEO_PLACEHOLDER_TITLES:
                parent.title_raw = self._dom_title
                parent.title_normalized = self._dom_title
        if self._dom_brand and not (parent.brand_raw or "").strip():
            parent.brand_raw = self._dom_brand
            parent.brand_normalized = self._dom_brand

        if self._product_ldjson:
            rating_info = self._product_ldjson.get("aggregateRating")
            if isinstance(rating_info, Mapping):
                rating_value = rating_info.get("ratingValue")
                review_count = rating_info.get("reviewCount") or rating_info.get(
                    "ratingCount"
                )
                if isinstance(rating_value, (int, float, str)):
                    try:
                        parent.extras["rating"] = float(rating_value)
                    except (ValueError, TypeError):
                        pass
                if isinstance(review_count, (int, float, str)):
                    try:
                        parent.extras["review_count"] = int(float(review_count))
                    except (ValueError, TypeError):
                        pass

        if self._latest_parent_payload:
            parent_brand = self._latest_parent_payload.get("brand")
            if isinstance(parent_brand, str) and parent_brand.strip():
                parent.brand_raw = parent_brand
                parent.brand_normalized = parent_brand.strip() or parent_brand
            parent_title = self._latest_parent_payload.get("title")
            if isinstance(parent_title, str) and parent_title.strip():
                parent.title_raw = parent_title
                parent.title_normalized = parent_title.strip() or parent_title
            summary = self._latest_parent_payload.get("summary")
            if isinstance(summary, str) and summary.strip():
                parent.extras["summary"] = summary
            rating = self._latest_parent_payload.get("rating")
            if isinstance(rating, (int, float)):
                parent.extras.setdefault("rating", float(rating))
            review_count = self._latest_parent_payload.get("review_count")
            if isinstance(review_count, (int, float)):
                parent.extras.setdefault("review_count", int(review_count))

            parent_asin = self._latest_parent_payload.get("parent_asin")
            if isinstance(parent_asin, str):
                normalized_parent_asin = parent_asin.strip().upper()
                if ASIN_EXACT.match(normalized_parent_asin):
                    canonical_parent_asin = normalized_parent_asin
                    parent.extras["parent_asin"] = normalized_parent_asin

            details = parent.extras.setdefault("details", {})
            description = self._latest_parent_payload.get("description_markdown")
            if isinstance(description, str) and description.strip():
                details["description_markdown"] = description
            usage = self._latest_parent_payload.get("usage")
            if isinstance(usage, str) and usage.strip():
                details["usage"] = usage
            ingredients = self._latest_parent_payload.get("ingredients")
            if isinstance(ingredients, str) and ingredients.strip():
                details["ingredients"] = ingredients

        if self._feature_bullets:
            details = parent.extras.setdefault("details", {})
            existing = details.get("features")
            if not existing:
                details["features"] = self._feature_bullets

        if self._embedded_reviews and "reviews" not in parent.extras:
            parent.extras["reviews"] = self._embedded_reviews
            parent.extras["reviews_meta"] = {
                "provider": "amazon_pdp_embedded",
                "count": len(self._embedded_reviews),
            }

        # Fallback: if no category was parsed, derive it from the profile name
        # (e.g., amazon_lipstick -> ["lipstick"]) so downstream consumers can
        # group results by category.
        if (
            not parent.category_path or not tuple(parent.category_path)
        ) and profile_name:
            suffix = (
                profile_name.split("_", 1)[1] if "_" in profile_name else profile_name
            )
            category = suffix.strip()
            if category:
                parent.category_path = (category,)

        if canonical_parent_asin and canonical_parent_asin != parent.parent_product_id:
            parent.extras["source_parent_id_from_url"] = parent.parent_product_id
            parent.parent_product_id = canonical_parent_asin

        if not variants:
            variants.append(
                Variant(
                    retailer=parent.retailer,
                    parent_product_id=parent.parent_product_id,
                    variant_id=parent.parent_product_id,
                    shade_name_raw=None,
                    shade_name_normalized=None,
                    size_text_raw=None,
                    price_raw=None,
                    price=None,
                    currency="USD",
                    barcode=parent.parent_product_id,
                    swatch_image_url=None,
                    hero_image_url=self._dom_hero_image,
                    availability=None,
                    source_index=None,
                    qa_flags=(),
                    extras={},
                )
            )

        for variant in variants:
            if canonical_parent_asin:
                variant.parent_product_id = canonical_parent_asin
            if variant.price_raw:
                normalized = _price_to_string(variant.price_raw)
                if normalized:
                    variant.price_raw = normalized
                    try:
                        variant.price = Decimal(normalized)
                    except Exception:  # noqa: BLE001 - defensive conversion
                        pass
            if not variant.currency:
                variant.currency = "USD"
            if not variant.hero_image_url and self._dom_hero_image:
                variant.hero_image_url = self._dom_hero_image

    def _extract_product_ldjson(self, soup: BeautifulSoup) -> Mapping[str, Any] | None:
        for script in soup.select("script[type='application/ld+json']"):
            raw = script.string or script.get_text()
            if not raw:
                continue
            payload_obj: Any = None
            try:
                payload_obj = json.loads(raw)
            except JSONDecodeError:
                payload_obj = _load_json(raw)
            if isinstance(payload_obj, Mapping):
                if payload_obj.get("@type") == "Product":
                    return payload_obj
                graph = payload_obj.get("@graph")
                if isinstance(graph, Sequence) and not isinstance(graph, (str, bytes)):
                    for item in graph:
                        if isinstance(item, Mapping) and item.get("@type") == "Product":
                            return item
            elif isinstance(payload_obj, Sequence) and not isinstance(
                payload_obj, (str, bytes)
            ):
                for item in payload_obj:
                    if isinstance(item, Mapping) and item.get("@type") == "Product":
                        return item
        return None

    def _extract_feature_bullets(self, soup: BeautifulSoup) -> list[str]:
        bullets: list[str] = []
        bullet_section = soup.select("#feature-bullets ul li span")
        for span in bullet_section:
            text = span.get_text(strip=True)
            if text:
                bullets.append(text)
        return bullets

    def _extract_twister_state(self, soup: BeautifulSoup) -> Mapping[str, Any] | None:
        for script in soup.select("script[type='a-state']"):
            candidates = (
                script.string or script.get_text(),
                script.get("data-a-state"),
            )
            for candidate in candidates:
                payload = _load_json(candidate)
                state = self._unwrap_state_payload(payload)
                if state:
                    return state
        for element in soup.select("[data-a-state]"):
            payload = _load_json(element.get("data-a-state"))
            state = self._unwrap_state_payload(payload)
            if state:
                return state
        for script in soup.select("script"):
            text = script.string or ""
            if not text or "twister" not in text.lower():
                continue
            payload = _load_json(text)
            state = self._unwrap_state_payload(payload)
            if state:
                return state
        return None

    @staticmethod
    def _unwrap_state_payload(
        payload: Mapping[str, Any] | None,
    ) -> Mapping[str, Any] | None:
        if not payload:
            return None
        if "value" in payload and isinstance(payload["value"], Mapping):
            return payload["value"]
        if "dimensionValuesDisplayData" in payload and "asinMetadata" in payload:
            return payload
        if "sortedDimValuesForAllDims" in payload:
            return payload
        if "twisterState" in payload and isinstance(payload["twisterState"], Mapping):
            return payload["twisterState"]
        return None

    def _normalize_twister_payload(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        asin_metadata = payload.get("asinMetadata")
        if isinstance(asin_metadata, Mapping):
            normalized = self._normalize_asin_metadata_payload(payload, asin_metadata)
            if normalized:
                return normalized

        sorted_dims = payload.get("sortedDimValuesForAllDims")
        if isinstance(sorted_dims, Mapping):
            return self._normalize_sorted_dimensions_payload(payload, sorted_dims)

        return None

    def _normalize_asin_metadata_payload(
        self,
        payload: Mapping[str, Any],
        asin_metadata: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        color_labels: dict[str, str] = {}
        dimension_values = payload.get("dimensionValuesDisplayData")
        if isinstance(dimension_values, Mapping):
            for mapping in dimension_values.values():
                if not isinstance(mapping, Mapping):
                    continue
                for asin, label in mapping.items():
                    if isinstance(asin, str) and isinstance(label, str):
                        color_labels[asin] = label

        variants: list[dict[str, Any]] = []
        for asin, metadata in asin_metadata.items():
            if not isinstance(asin, str) or not isinstance(metadata, Mapping):
                continue
            normalized_variant: dict[str, Any] = {"asin": asin, "variantId": asin}

            color_name = color_labels.get(asin)
            if not color_name:
                variation_values = metadata.get("variationValues")
                if isinstance(variation_values, Mapping):
                    color_value = variation_values.get(
                        "color_name"
                    ) or variation_values.get("shade_name")
                    if isinstance(color_value, str):
                        color_name = color_value
            title = metadata.get("title")
            if isinstance(title, str) and title:
                normalized_variant.setdefault("shadeDescription", title)
            if color_name:
                normalized_variant["colorName"] = color_name
                if "shadeDescription" not in normalized_variant:
                    normalized_variant["shadeDescription"] = color_name

            size_name = None
            dimension_map = metadata.get("dimensionValues")
            if isinstance(dimension_map, Mapping):
                for key in ("size_name", "size", "item_volume"):
                    value = dimension_map.get(key)
                    if isinstance(value, str) and value:
                        size_name = value
                        break
            if size_name:
                normalized_variant["sizeText"] = size_name

            list_price = _price_to_string(metadata.get("listPrice"))
            if list_price:
                normalized_variant["list_price"] = list_price

            price = (
                _price_to_string(metadata.get("price"))
                or _price_to_string(metadata.get("priceAmount"))
                or _price_to_string(metadata.get("priceRaw"))
                or _price_to_string(metadata.get("displayPrice"))
            )
            if price:
                normalized_variant["price"] = price
            if list_price and not price:
                normalized_variant["price"] = list_price

            currency = metadata.get("currency") or metadata.get("currencyCode")
            if isinstance(currency, str):
                normalized_variant["currency"] = currency
            else:
                normalized_variant["currency"] = "USD"

            hero, swatch = _extract_images(metadata)
            if hero:
                normalized_variant["heroImage"] = hero
            if swatch:
                normalized_variant["swatchImage"] = swatch

            availability = _availability_label(metadata)
            if availability:
                normalized_variant["availability"] = availability

            badges = metadata.get("badges")
            if isinstance(badges, Sequence) and not isinstance(badges, (str, bytes)):
                normalized_variant["badges"] = [
                    str(item) for item in badges if isinstance(item, str)
                ]

            promotions = metadata.get("promotions")
            if isinstance(promotions, Sequence) and not isinstance(
                promotions, (str, bytes)
            ):
                normalized_variant["promotionTags"] = [
                    str(item) for item in promotions if isinstance(item, str)
                ]

            variants.append(normalized_variant)

        parent_payload = self._build_parent_payload(payload)
        normalized: dict[str, Any] = {}
        if parent_payload:
            normalized["parent"] = parent_payload
        if variants:
            normalized["variants"] = variants
        return normalized or None

    def _normalize_sorted_dimensions_payload(
        self,
        payload: Mapping[str, Any],
        sorted_dims: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        variants_by_asin: dict[str, dict[str, Any]] = {}

        def ensure_variant(asin: str) -> dict[str, Any]:
            entry = variants_by_asin.get(asin)
            if entry is None:
                entry = {"asin": asin, "variantId": asin, "currency": "USD"}
                variants_by_asin[asin] = entry
            return entry

        for dimension_name, values in sorted_dims.items():
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                continue
            for item in values:
                if not isinstance(item, Mapping):
                    continue
                asin_value = item.get("defaultAsin") or item.get("asin")
                if not isinstance(asin_value, str):
                    continue
                asin = asin_value.upper()
                variant = ensure_variant(asin)

                display_text = item.get("dimensionValueDisplayText")
                if isinstance(display_text, str) and display_text.strip():
                    text = display_text.strip()
                    if dimension_name in {"color_name", "shade_name", "color"}:
                        variant.setdefault("colorName", text)
                        variant.setdefault("shadeDescription", text)
                    elif dimension_name in {"size_name", "size", "item_volume"}:
                        variant.setdefault("sizeText", text)

                image_attribute = item.get("imageAttribute")
                if isinstance(image_attribute, Mapping):
                    image_url = image_attribute.get("url") or image_attribute.get(
                        "large"
                    )
                    if isinstance(image_url, str) and image_url:
                        variant.setdefault("heroImage", image_url)
                        variant.setdefault("swatchImage", image_url)

                availability = _availability_from_dimension_state(
                    item.get("dimensionValueState")
                )
                if availability:
                    variant["availability"] = availability

        parent_payload = self._build_parent_payload(payload)
        normalized: dict[str, Any] = {}
        if parent_payload:
            normalized["parent"] = parent_payload
        variants = list(variants_by_asin.values())
        if variants:
            normalized["variants"] = variants
        return normalized or None

    def _build_parent_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        parent_payload: dict[str, Any] = {}
        parent_asin = payload.get("parentAsin")
        if isinstance(parent_asin, str):
            parent_payload["parent_asin"] = parent_asin
        parent_title = payload.get("title") or payload.get("parentTitle")
        if isinstance(parent_title, str):
            parent_payload["title"] = parent_title
        brand_name = payload.get("brand") or payload.get("brandName")
        if isinstance(brand_name, str):
            parent_payload["brand"] = brand_name
        description = payload.get("description") or payload.get("productDescription")
        if isinstance(description, str):
            parent_payload["summary"] = description
            parent_payload["description_markdown"] = description

        category_path = payload.get("categoryPath")
        if isinstance(category_path, Sequence) and not isinstance(
            category_path, (str, bytes)
        ):
            parent_payload["category_path"] = [
                str(item) for item in category_path if isinstance(item, str)
            ]

        rating = payload.get("rating")
        if isinstance(rating, (int, float)):
            parent_payload["rating"] = float(rating)
        review_count = payload.get("reviewCount")
        if isinstance(review_count, (int, float)):
            parent_payload["review_count"] = int(review_count)
        return parent_payload

    def _extract_dom_title(self, soup: BeautifulSoup) -> str | None:
        title_element = soup.select_one("#productTitle")
        if title_element:
            title = title_element.get_text(" ", strip=True)
            if title:
                return title
        if self._product_ldjson:
            ld_name = self._product_ldjson.get("name")
            if isinstance(ld_name, str) and ld_name.strip():
                return ld_name.strip()
        return None

    def _extract_dom_brand(self, soup: BeautifulSoup) -> str | None:
        byline = soup.select_one("#bylineInfo")
        if byline:
            brand = _normalize_brand_text(byline.get_text(" ", strip=True))
            if brand:
                return brand
        if self._product_ldjson:
            brand_value = self._product_ldjson.get("brand")
            if isinstance(brand_value, Mapping):
                brand_name = brand_value.get("name")
                if isinstance(brand_name, str) and brand_name.strip():
                    return brand_name.strip()
            elif isinstance(brand_value, str) and brand_value.strip():
                return brand_value.strip()
        canonical = soup.select_one("link[rel='canonical']")
        if canonical:
            href = canonical.get("href")
            if isinstance(href, str) and href:
                match = re.search(r"amazon\.com/([^/]+)/dp/", href, flags=re.IGNORECASE)
                if match:
                    slug = match.group(1).replace("%20", "-")
                    slug_head = slug.split("-", 1)[0]
                    brand = _normalize_brand_text(slug_head)
                    if brand:
                        return brand
        title = self._extract_dom_title(soup)
        if title:
            title_head = (
                title.split(" - ", 1)[0] if " - " in title else title.split(" ", 1)[0]
            )
            brand = _normalize_brand_text(title_head)
            if brand:
                return brand
        return None

    def _extract_dom_hero_image(self, soup: BeautifulSoup) -> str | None:
        image = soup.select_one("#landingImage, #imgBlkFront")
        if image:
            dynamic = image.get("data-a-dynamic-image")
            if isinstance(dynamic, str):
                try:
                    parsed = json.loads(dynamic)
                    if isinstance(parsed, Mapping):
                        for url in parsed:
                            if isinstance(url, str) and url.strip():
                                return url
                except JSONDecodeError:
                    pass
            for attr in ("data-old-hires", "src"):
                value = image.get(attr)
                if (
                    isinstance(value, str)
                    and value.strip()
                    and "data:image" not in value
                ):
                    return value
        og_image = soup.select_one("meta[property='og:image']")
        if og_image:
            content = og_image.get("content")
            if isinstance(content, str) and content.strip():
                return content
        return None

    def _extract_embedded_reviews(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        review_nodes = list(soup.select('[data-hook="review"]'))
        if not review_nodes:
            review_nodes = list(soup.select('[data-hook="reviewContainer"]'))

        reviews: list[dict[str, Any]] = []
        seen: set[str] = set()
        for node in review_nodes:
            review_id = _clean_review_text(
                str(node.get("data-reviewid") or node.get("id") or "")
            )
            if not review_id:
                parent = node.find_parent(attrs={"data-reviewid": True})
                if parent is not None:
                    review_id = _clean_review_text(
                        str(parent.get("data-reviewid") or "")
                    )

            rating_node = node.select_one(
                '[data-hook="review-star-rating"] .a-icon-alt, '
                '[data-hook="cmps-review-star-rating"] .a-icon-alt'
            )
            rating = _rating_from_text(
                rating_node.get_text(" ", strip=True) if rating_node else None
            )

            title_node = node.select_one(
                '[data-hook="review-title"], [data-hook="reviewTitle"]'
            )
            headline = _clean_review_text(
                title_node.get_text(" ", strip=True) if title_node else None
            )

            text_node = node.select_one(
                '[data-hook="review-body"], [data-hook="reviewRichContentContainer"], '
                '[data-hook="reviewText"]'
            )
            comment = _clean_review_text(
                text_node.get_text(" ", strip=True) if text_node else None
            )

            if not any((review_id, headline, comment, rating is not None)):
                continue

            author_node = node.select_one(".a-profile-name")
            date_node = node.select_one('[data-hook="review-date"]')
            variant_node = node.select_one('[data-hook="format-strip"]')
            review: dict[str, Any] = {}
            if review_id:
                review["review_id"] = review_id
            if headline:
                review["headline"] = headline
            if comment:
                review["comment"] = comment
            author = _clean_review_text(
                author_node.get_text(" ", strip=True) if author_node else None
            )
            if author:
                review["author"] = author
            created_date = _created_date_from_text(
                date_node.get_text(" ", strip=True) if date_node else None
            )
            if created_date:
                review["created_date"] = created_date
            if rating is not None:
                review["rating"] = rating
            if node.select_one('[data-hook="avp-badge"]') is not None:
                review["verified_purchase"] = True
            variant_text = _clean_review_text(
                variant_node.get_text(" ", strip=True) if variant_node else None
            )
            if variant_text:
                review["variant_text"] = variant_text
            asin = _clean_review_text(str(node.get("data-asin") or ""))
            if asin:
                review["asin"] = asin
            locale = _clean_review_text(str(node.get("data-locale") or ""))
            if locale:
                review["locale"] = locale
            source_language = _clean_review_text(
                str(node.get("data-sourcelanguage") or "")
            )
            if source_language:
                review["source_language"] = source_language

            dedupe_key = review_id or f"{headline}|{comment}|{author}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            reviews.append(review)

        return reviews


__all__ = ["AmazonAdapter"]
