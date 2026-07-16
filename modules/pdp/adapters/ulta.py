from __future__ import annotations

import json
import re
from collections import deque
from json import JSONDecodeError
from typing import Mapping, Sequence

from bs4 import BeautifulSoup  # type: ignore[import]
from json_repair import repair_json  # type: ignore[import]

from ..models import EvidenceBlob, ParentProduct, Variant
from . import RetailerAdapter

ULTA_PRODUCT_ID_REGEX = re.compile(r"((?:pimprod|mkt|xlsImpprod)[0-9A-Za-z]+)")

def _first_image_value(payload: object) -> str | None:
    """Return the first usable image URL from a parent-level payload."""
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if not isinstance(payload, Mapping):
        return None

    keys = (
        "heroImageUrl",
        "heroImage",
        "imageUrl",
        "primaryImageUrl",
        "defaultImageUrl",
        "primaryImage",
        "defaultImage",
        "productImage",
        "image",
    )
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            nested = value.get("url") or value.get("imageUrl")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()

    media = payload.get("media")
    if isinstance(media, Mapping):
        for candidate in ("mainImage", "heroImage", "defaultImage"):
            entry = media.get(candidate)
            if isinstance(entry, Mapping):
                nested = entry.get("url") or entry.get("imageUrl")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return None


def _parse_json(text: str):
    snippet = text.strip()
    if not snippet:
        return ()
    try:
        return (json.loads(snippet),)
    except JSONDecodeError:
        pass
    for delimiter in ("{", "["):
        start = snippet.find(delimiter)
        if start == -1:
            continue
        end = snippet.rfind("}" if delimiter == "{" else "]")
        if end == -1:
            continue
        candidate = snippet[start : end + 1]
        try:
            return (json.loads(candidate),)
        except JSONDecodeError:
            try:
                repaired = repair_json(candidate)
            except Exception:
                continue
            if repaired:
                try:
                    return (json.loads(repaired),)
                except JSONDecodeError:
                    continue
    return ()


class UltaAdapter(RetailerAdapter):
    retailer = "ulta"

    def __init__(self) -> None:
        self._latest_parent_payload: Mapping[str, object] | None = None
        self._latest_reviews_payload: Mapping[str, object] | None = None
        self._meta_image_url: str | None = None

    def primary_id_from_url(self, url: str) -> str | None:
        match = ULTA_PRODUCT_ID_REGEX.search(url)
        if match:
            return match.group(1)
        return None

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        soup = BeautifulSoup(html, "lxml")
        blobs: list[EvidenceBlob] = []
        self._latest_parent_payload = None
        self._latest_reviews_payload = None
        self._meta_image_url = None

        script_selectors = [
            "script[data-component*='Shade']",
            "script[data-component*='Variant']",
            "script[data-component='ProductShadeSelector']",
        ]
        for selector in script_selectors:
            for script in soup.select(selector):
                text = script.string or script.get_text()
                if not text:
                    continue
                for payload in _parse_json(text):
                    blobs.append(
                        EvidenceBlob(
                            source="dom_adapter_script",
                            selector=selector,
                            index=-(len(blobs) + 1),
                            payload=payload,
                        )
                    )

        variant_elements = soup.select("[data-variant-id], [data-sku], [data-sku-id]")
        variant_payloads: list[dict[str, str]] = []
        for element in variant_elements:
            data: dict[str, str] = {}
            for attr, value in element.attrs.items():
                if not attr.startswith("data-"):
                    continue
                if isinstance(value, list):
                    data[attr[5:]] = " ".join(value)
                else:
                    data[attr[5:]] = str(value)
            if data:
                variant_payloads.append(data)

        if variant_payloads:
            blobs.append(
                EvidenceBlob(
                    source="dom_variant_attributes",
                    selector="[data-variant-id]",
                    index=-(len(blobs) + 1),
                    payload={"variants": variant_payloads},
                )
            )

        apollo = soup.select_one("script#apollo_state")
        if apollo:
            text = apollo.string or apollo.get_text()
            if text:
                for payload in _parse_json(text):
                    normalized_variants, parent_payload, reviews_payload = _normalize_graphql_variants(payload)
                    if normalized_variants:
                        combined_payload: dict[str, object] = {"variants": normalized_variants}
                        if parent_payload:
                            combined_payload["parent"] = parent_payload
                            self._latest_parent_payload = parent_payload
                        else:
                            self._latest_parent_payload = None
                        self._latest_reviews_payload = reviews_payload
                        blobs.append(
                            EvidenceBlob(
                                source="apollo_state_variants",
                                selector="script#apollo_state",
                                index=-(len(blobs) + 1),
                                payload=combined_payload,
                            )
                        )
                        break

        # Capture OpenGraph hero image as a fallback for PDPs with missing variant images.
        og_image = soup.select_one("meta[property='og:image']")
        if og_image:
            content = og_image.get("content") or og_image.get("value")
            if isinstance(content, str) and content.strip():
                self._meta_image_url = content.strip()

        return tuple(blobs)

    def retailer_specific_fixes(
        self,
        parent: ParentProduct | None,
        variants: list[Variant],
        profile_name: str | None = None,
    ) -> None:
        if parent and parent.title_raw:
            lowered = parent.title_raw.lower()
            if any(token in lowered for token in (" kit", " set", " duo", " vault")):
                parent.has_color_selector = False

        seen_ids: dict[str, Variant] = {}
        deduped: list[Variant] = []
        for variant in variants:
            variant_id = variant.variant_id
            if variant_id:
                existing = seen_ids.get(variant_id)
                if existing is not None:
                    _merge_variant_details(existing, variant)
                    continue
                seen_ids[variant_id] = variant
            deduped.append(variant)
        variants.clear()
        variants.extend(deduped)

        # Fallback: try to populate category_path if profile selectors failed.
        if parent and not parent.category_path:
            if self._latest_parent_payload:
                fallback_categories = _extract_category_path(self._latest_parent_payload)
                if fallback_categories:
                    parent.category_path = fallback_categories
            # Last resort: derive from profile name (e.g., ulta_face_primer -> "face primer")
            if not parent.category_path and profile_name:
                suffix = profile_name
                if suffix.startswith("ulta_"):
                    suffix = suffix.split("_", 1)[1]
                suffix = suffix.replace("_", " ").strip()
                if suffix:
                    parent.category_path = (suffix,)

        if parent and self._latest_parent_payload:
            parent_payload = self._latest_parent_payload
            brand = parent_payload.get("brandName")
            if isinstance(brand, str) and brand:
                parent.brand_raw = brand
                parent.brand_normalized = brand.strip() or brand
            parent_image = _first_image_value(parent_payload)

            title = parent_payload.get("name")
            if isinstance(title, str) and title:
                parent.title_raw = title
                parent.title_normalized = title

            details: dict[str, object] = {}
            for key, alias in (
                ("description", "description_markdown"),
                ("usage", "usage"),
                ("ingredients", "ingredients"),
                ("restrictions", "restrictions"),
            ):
                value = parent_payload.get(key)
                if isinstance(value, str) and value:
                    details[alias] = value

            features = parent_payload.get("features")
            if isinstance(features, Sequence) and features:
                details["features"] = [str(item) for item in features if isinstance(item, str)]

            summary_message = parent_payload.get("summary")
            if isinstance(summary_message, str) and summary_message:
                if not parent.extras.get("summary"):
                    parent.extras["summary"] = summary_message

            highlights = parent_payload.get("highlights")
            if isinstance(highlights, Sequence) and highlights:
                cleaned_highlights = []
                for item in highlights:
                    if isinstance(item, Mapping):
                        label = item.get("label")
                        description = item.get("description")
                        if label:
                            entry: dict[str, str] = {"label": str(label)}
                            if isinstance(description, str) and description:
                                entry["description"] = description
                            cleaned_highlights.append(entry)
                if cleaned_highlights:
                    parent.extras["highlights"] = cleaned_highlights

            summary_cards = parent_payload.get("summary_cards")
            if isinstance(summary_cards, Sequence) and summary_cards:
                parent.extras["summary_cards"] = list(summary_cards)

            rating = parent_payload.get("rating")
            if isinstance(rating, (int, float)):
                parent.extras["rating"] = rating

            review_count = parent_payload.get("reviewCount")
            if isinstance(review_count, int):
                parent.extras["review_count"] = review_count

            badges = parent_payload.get("badges")
            if isinstance(badges, Sequence) and badges:
                parent.extras["badges"] = [str(item) for item in badges if isinstance(item, str)]

            brand_url = parent_payload.get("brandUrl")
            if isinstance(brand_url, str) and brand_url:
                parent.extras["brand_url"] = brand_url

            if details:
                parent.extras.setdefault("details", {}).update(details)  # type: ignore[arg-type]

            if self._latest_reviews_payload:
                _attach_reviews(parent, self._latest_reviews_payload)
                self._latest_reviews_payload = None

        # If variants still lack hero images, fall back to the page-level OG image.
        fallback_image = self._meta_image_url or locals().get("parent_image")
        if fallback_image:
            for variant in variants:
                if not variant.hero_image_url:
                    variant.hero_image_url = fallback_image

        self._latest_parent_payload = None
        self._meta_image_url = None


__all__ = ["UltaAdapter"]


def _find_product_reviews_module(payload: object) -> Mapping[str, object] | None:
    """Locate the ``ProductReviews`` module within an Apollo payload."""

    queue: deque[object] = deque([payload])
    while queue:
        node = queue.popleft()
        if isinstance(node, Mapping):
            module_name = node.get("moduleName")
            if isinstance(module_name, str) and module_name == "ProductReviews":
                return dict(node)
            for value in node.values():
                if isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes)):
                    queue.append(value)
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            queue.extend(node)
    return None


def _normalize_graphql_variants(
    payload: object,
) -> tuple[list[Mapping[str, object]], Mapping[str, object] | None, Mapping[str, object] | None]:
    """Traverse a parsed Apollo payload and extract variant dictionaries plus parent context."""

    def image_url(value: object) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, Mapping):
            url = value.get("imageUrl") or value.get("url")
            if isinstance(url, str) and url:
                return url
        return None

    def coerce_price(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return None

    variants: list[dict[str, object]] = []
    seen: set[str] = set()
    queue: deque[object] = deque([payload])
    while queue:
        node = queue.popleft()
        if isinstance(node, Mapping):
            candidates = node.get("variants")
            if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
                for candidate in candidates:
                    if not isinstance(candidate, Mapping):
                        continue
                    raw_sku = candidate.get("skuId") or candidate.get("sku")
                    if not raw_sku:
                        continue
                    sku = str(raw_sku)
                    if not sku or sku in seen:
                        continue
                    seen.add(sku)

                    sale_price = coerce_price(candidate.get("salePrice"))
                    list_price = coerce_price(candidate.get("listPrice"))
                    price = sale_price or coerce_price(candidate.get("price")) or list_price
                    availability = None
                    if candidate.get("unavailable") is True:
                        availability = "OutOfStock"
                    elif candidate.get("unavailable") is False:
                        availability = "InStock"

                    main_image = image_url(candidate.get("mainImage") or candidate.get("image"))
                    swatch_image = image_url(candidate.get("swatchImage") or candidate.get("swatch"))

                    normalized: dict[str, object] = {"skuId": sku}
                    name = candidate.get("name")
                    shade_description = candidate.get("shadeDescription")
                    attributes: dict[str, object] = {}
                    if isinstance(name, str) and name:
                        normalized["name"] = name
                        normalized["shadeName"] = name
                        normalized["colorName"] = name
                        attributes["color"] = name
                    if isinstance(shade_description, str) and shade_description:
                        normalized["shadeDescription"] = shade_description
                        attributes["shade"] = shade_description
                    if price:
                        normalized["price"] = price
                        normalized["currentPrice"] = price
                    if list_price and list_price != price:
                        normalized["listPrice"] = list_price
                    normalized["priceCurrency"] = candidate.get("priceCurrency") or "USD"
                    if availability:
                        normalized["availability"] = availability
                    if main_image:
                        normalized["image"] = main_image
                    if swatch_image:
                        normalized["swatchImage"] = swatch_image
                    if attributes:
                        normalized["attributes"] = attributes

                    barcode = candidate.get("skuUPC") or candidate.get("upc") or candidate.get("barcode")
                    if isinstance(barcode, str) and barcode:
                        normalized["barcode"] = barcode

                    product_id = candidate.get("productId") or candidate.get("commerceId")
                    if isinstance(product_id, str) and product_id:
                        normalized["productId"] = product_id

                    badges = candidate.get("badges")
                    if isinstance(badges, Sequence) and badges:
                        normalized["badges"] = [
                            badge["label"] if isinstance(badge, Mapping) and "label" in badge else str(badge)
                            for badge in badges
                            if badge not in (None, "")
                        ]

                    promotion_tags = candidate.get("promotionTags")
                    if isinstance(promotion_tags, Sequence) and promotion_tags:
                        normalized["promotionTags"] = [
                            str(tag) for tag in promotion_tags if tag not in (None, "")
                        ]

                    variant_label = candidate.get("variantLabel")
                    if isinstance(variant_label, str) and variant_label:
                        normalized["variantLabel"] = variant_label

                    variants.append(normalized)

            queue.extend(node.values())
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            queue.extend(node)

    parent_payload = _extract_parent_payload(payload)
    reviews_payload = _find_product_reviews_module(payload)
    return variants, parent_payload, reviews_payload


def _extract_category_path(payload: object) -> tuple[str, ...]:
    """
    Traverse a payload to extract a breadcrumb/category trail when profile selectors miss.
    """
    if not isinstance(payload, Mapping):
        return tuple()

    queue: deque[object] = deque([payload])
    categories: list[str] = []
    seen: set[str] = set()

    def _maybe_add(value: object) -> None:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned and cleaned not in seen:
                categories.append(cleaned)
                seen.add(cleaned)

    while queue:
        node = queue.popleft()
        if isinstance(node, Mapping):
            for key, value in node.items():
                lowered = key.lower()
                if any(token in lowered for token in ("breadcrumb", "categorypath", "category_path", "category")):
                    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                        for item in value:
                            if isinstance(item, Mapping):
                                for field in ("name", "label", "title"):
                                    _maybe_add(item.get(field))
                            else:
                                _maybe_add(item)
                    else:
                        _maybe_add(value)
                if isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes, bytearray)):
                    queue.append(value)
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            for item in node:
                if isinstance(item, (Mapping, Sequence)) and not isinstance(item, (str, bytes, bytearray)):
                    queue.append(item)

    return tuple(categories)


def _merge_variant_details(primary: Variant, secondary: Variant) -> None:
    """Fill missing fields on ``primary`` using values from ``secondary``."""

    if not primary.shade_name_raw and secondary.shade_name_raw:
        primary.shade_name_raw = secondary.shade_name_raw
    if not primary.shade_name_normalized and secondary.shade_name_normalized:
        primary.shade_name_normalized = secondary.shade_name_normalized
    if not primary.size_text_raw and secondary.size_text_raw:
        primary.size_text_raw = secondary.size_text_raw
    if primary.price is None and secondary.price is not None:
        primary.price = secondary.price
    if not primary.price_raw and secondary.price_raw:
        primary.price_raw = secondary.price_raw
    if not primary.currency and secondary.currency:
        primary.currency = secondary.currency
    if not primary.barcode and secondary.barcode:
        primary.barcode = secondary.barcode
    if not primary.swatch_image_url and secondary.swatch_image_url:
        primary.swatch_image_url = secondary.swatch_image_url
    if not primary.hero_image_url and secondary.hero_image_url:
        primary.hero_image_url = secondary.hero_image_url
    if not primary.availability and secondary.availability:
        primary.availability = secondary.availability
    if secondary.qa_flags:
        combined = tuple(dict.fromkeys((*primary.qa_flags, *secondary.qa_flags)))
        primary.qa_flags = combined
    if secondary.extras:
        for key, value in secondary.extras.items():
            if key not in primary.extras:
                primary.extras[key] = value


def _extract_parent_payload(payload: object) -> Mapping[str, object]:
    """Extract product-level metadata needed for attributes."""

    modules = _find_modules(payload, {"ProductInformation", "ProductDetail", "ProductSummary"})
    info = modules.get("ProductInformation")
    detail = modules.get("ProductDetail")
    summary_module = modules.get("ProductSummary")

    result: dict[str, object] = {}
    if isinstance(info, Mapping):
        name = info.get("productName")
        normalized_name = _sanitize_text(name)
        if normalized_name:
            result["name"] = normalized_name
        brand_action = info.get("brandAction", {})
        if isinstance(brand_action, Mapping):
            label = _sanitize_text(brand_action.get("label"))
            if label:
                result["brandName"] = label
            brand_url = brand_action.get("url")
            if isinstance(brand_url, str) and brand_url:
                result["brandUrl"] = brand_url
        rating = info.get("rating")
        if isinstance(rating, (int, float)):
            result["rating"] = rating
        review_count = info.get("reviewCount")
        if isinstance(review_count, int):
            result["reviewCount"] = review_count
        badges = info.get("badges")
        if isinstance(badges, Sequence):
            result["badges"] = [str(item) for item in badges if isinstance(item, str)]

    if isinstance(detail, Mapping):
        for key in ("description", "usage", "ingredients", "restrictions"):
            value = _sanitize_text(detail.get(key))
            if value:
                result[key] = value

    description = result.get("description")
    if isinstance(description, str):
        features = [
            line.strip()[1:].strip()
            for line in description.splitlines()
            if line.strip().startswith("- ")
        ]
        if features:
            result["features"] = features

    if isinstance(summary_module, Mapping):
        message = _sanitize_text(summary_module.get("message"))
        if message and "summary" not in result:
            result["summary"] = message

        highlights: list[dict[str, str]] = []
        for summary_entry in summary_module.get("summaries", []) or []:
            title = (_sanitize_text(summary_entry.get("title")) or "").lower()
            if title == "highlights":
                for item in summary_entry.get("items", []) or []:
                    label = _sanitize_text(item.get("label"))
                    detail_card = item.get("itemDetailCard") if isinstance(item, Mapping) else None
                    description_text = _sanitize_text(detail_card.get("description") if isinstance(detail_card, Mapping) else None)
                    if label:
                        entry: dict[str, str] = {"label": label}
                        if description_text:
                            entry["description"] = description_text
                        highlights.append(entry)
        if highlights:
            result["highlights"] = highlights

        summary_cards_output: list[dict[str, object]] = []
        for card in summary_module.get("summaryCards", []) or []:
            if not isinstance(card, Mapping):
                continue
            card_title = _sanitize_text(card.get("title"))
            items = card.get("items")
            cleaned_items = []
            if isinstance(items, list):
                for entry in items:
                    if isinstance(entry, Mapping):
                        item_title = _sanitize_text(entry.get("title"))
                        item_text = _sanitize_text(entry.get("text"))
                        combined = item_text or item_title
                        if combined:
                            cleaned_items.append(combined)
                    elif isinstance(entry, str):
                        cleaned_items.append(entry.strip())
            if card_title or cleaned_items:
                summary_cards_output.append(
                    {
                        "title": card_title,
                        "items": cleaned_items,
                    }
                )
        if summary_cards_output:
            result["summary_cards"] = summary_cards_output

    return result


def _parse_review_rating(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _attach_reviews(parent: ParentProduct, payload: Mapping[str, object]) -> None:
    reviews_data = payload.get("reviews")
    if isinstance(reviews_data, Sequence):
        cleaned_reviews: list[dict[str, object]] = []
        for entry in reviews_data:
            if not isinstance(entry, Mapping):
                continue
            review_record: dict[str, object] = {}
            headline = _sanitize_text(entry.get("headline"))
            if headline:
                review_record["headline"] = headline
            comment = _sanitize_text(entry.get("comment"))
            if comment:
                review_record["comment"] = comment
            created = _sanitize_text(entry.get("createdDate"))
            if created:
                review_record["created_date"] = created
            nickname = _sanitize_text(entry.get("nickname"))
            if nickname:
                review_record["author"] = nickname
            location = _sanitize_text(entry.get("location"))
            if location:
                review_record["location"] = location
            rating_value = _parse_review_rating(entry.get("rating"))
            if rating_value is not None:
                review_record["rating"] = rating_value
            if review_record:
                cleaned_reviews.append(review_record)
        if cleaned_reviews:
            parent.extras["reviews"] = cleaned_reviews

    positive_headline = _sanitize_text(payload.get("positiveHeadline"))
    positive_comment = _sanitize_text(payload.get("positiveComments"))
    if positive_headline or positive_comment:
        summary: dict[str, str] = {}
        if positive_headline:
            summary["headline"] = positive_headline
        if positive_comment:
            summary["comment"] = positive_comment
        parent.extras["reviews_positive"] = summary

    negative_headline = _sanitize_text(payload.get("negativeHeadline"))
    negative_comment = _sanitize_text(payload.get("negativeComments"))
    if negative_headline or negative_comment:
        summary: dict[str, str] = {}
        if negative_headline:
            summary["headline"] = negative_headline
        if negative_comment:
            summary["comment"] = negative_comment
        parent.extras["reviews_negative"] = summary

    metadata: dict[str, str] = {}
    api_key = _sanitize_text(payload.get("prApiKey"))
    if api_key:
        metadata["api_key"] = api_key
    group_id = _sanitize_text(payload.get("prMerchantGroupId"))
    if group_id:
        metadata["merchant_group_id"] = group_id
    merchant_id = _sanitize_text(payload.get("prMerchantId"))
    if merchant_id:
        metadata["merchant_id"] = merchant_id
    locale = _sanitize_text(payload.get("locale"))
    if locale:
        metadata["locale"] = locale
    if metadata:
        metadata["provider"] = "powerreviews"
        parent.extras["reviews_meta"] = metadata


def _find_modules(payload: object, names: set[str]) -> dict[str, Mapping[str, object]]:
    results: dict[str, Mapping[str, object]] = {}
    queue: deque[object] = deque([payload])
    while queue:
        node = queue.popleft()
        if isinstance(node, Mapping):
            module_name = node.get("moduleName")
            if isinstance(module_name, str) and module_name in names and module_name not in results:
                results[module_name] = node  # type: ignore[assignment]
            queue.extend(node.values())
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            queue.extend(node)
        if len(results) == len(names):
            break
    return results


def _sanitize_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.replace("\\n", "\n")
    sanitized = text.strip()
    return sanitized or None
