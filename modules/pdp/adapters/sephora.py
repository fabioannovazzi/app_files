from __future__ import annotations

import json
import re
from json import JSONDecodeError
from typing import Mapping, Sequence
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, FeatureNotFound  # type: ignore[import]

from ..models import EvidenceBlob, ParentProduct, Variant
from . import RetailerAdapter

PARENT_REGEX = re.compile(r"(P[0-9]{3,})")


def _parse_json(text: str) -> Mapping[str, object] | None:
    snippet = text.strip()
    if not snippet:
        return None
    try:
        payload = json.loads(snippet)
        if isinstance(payload, Mapping):
            return payload
    except JSONDecodeError:
        pass
    for delimiter in ("{", "["):
        start = snippet.find(delimiter)
        if start == -1:
            continue
        end = snippet.rfind("}" if delimiter == "{" else "]")
        if end == -1 or end <= start:
            continue
        candidate = snippet[start : end + 1]
        try:
            payload = json.loads(candidate)
            if isinstance(payload, Mapping):
                return payload
        except JSONDecodeError:
            continue
    return None


def _find_product(payload: Mapping[str, object]) -> Mapping[str, object] | None:
    data = payload.get("data")
    if isinstance(data, Sequence):
        for entry in data:
            if isinstance(entry, Mapping):
                product = entry.get("product")
                if isinstance(product, Mapping):
                    return product
    if isinstance(payload.get("product"), Mapping):
        return payload["product"]  # type: ignore[return-value]
    return None


def _sanitize_text(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return None


def _clean_html(value: object) -> str | None:
    text = _sanitize_text(value)
    if not text:
        return None
    fragment = BeautifulSoup(text, "lxml")
    cleaned = fragment.get_text(" ", strip=True)
    return cleaned or None


def _extract_image_url(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, Mapping):
        for key in ("imageUrl", "url", "image250"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                cleaned = candidate.strip()
                if cleaned:
                    return cleaned
    return None


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


class SephoraAdapter(RetailerAdapter):
    retailer = "sephora"

    def __init__(self) -> None:
        self._latest_product: Mapping[str, object] | None = None
        self._jsonld_product: Mapping[str, object] | None = None

    @staticmethod
    def _sku_id_from_url(url: str) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for key in ("skuId", "sku"):
            values = query.get(key)
            if values and values[0]:
                sku_value = str(values[0]).strip()
                if sku_value:
                    return sku_value
        return None

    def primary_id_from_url(self, url: str) -> str | None:
        match = PARENT_REGEX.search(url)
        if match:
            return match.group(1)
        return None

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        try:
            soup = BeautifulSoup(html, "lxml")
        except FeatureNotFound:
            soup = BeautifulSoup(html, "html.parser")
        link_store_script = soup.select_one("script#linkStore")
        script = soup.select_one("script#__NUXT__")
        self._latest_product = None
        self._jsonld_product = None

        blobs: list[EvidenceBlob] = []

        if link_store_script:
            text = link_store_script.string or link_store_script.get_text()
            if text:
                payload = _parse_json(text)
                product = None
                if payload and isinstance(payload.get("page"), Mapping):
                    page = payload.get("page")
                    candidate = page.get("product") if isinstance(page, Mapping) else None
                    if isinstance(candidate, Mapping):
                        product = candidate

                if product:
                    product_payload = dict(product)
                    current_sku = product_payload.get("currentSku")
                    if isinstance(current_sku, Mapping):
                        brand_name = _sanitize_text(current_sku.get("brandName"))
                        if brand_name and "brand" not in product_payload:
                            product_payload["brand"] = {"displayName": brand_name}
                        display_name = _sanitize_text(current_sku.get("displayName"))
                        if display_name and "displayName" not in product_payload:
                            product_payload["displayName"] = display_name
                        if "mainSku" not in product_payload:
                            sku_id = _sanitize_text(current_sku.get("skuId") or current_sku.get("sku"))
                            if sku_id:
                                product_payload["mainSku"] = {"skuId": sku_id}

                    if "skus" not in product_payload:
                        regular_child_skus = product_payload.get("regularChildSkus")
                        ancillary_skus = product_payload.get("ancillarySkus")
                        if isinstance(regular_child_skus, list):
                            product_payload["skus"] = regular_child_skus
                        elif isinstance(ancillary_skus, list):
                            product_payload["skus"] = ancillary_skus

                    self._latest_product = product_payload
                    blobs.append(
                        EvidenceBlob(
                            source="sephora_link_store",
                            selector="script#linkStore",
                            index=-2,
                            payload=product_payload,
                        )
                    )

        if script:
            text = script.string or script.get_text()
            if text:
                payload = _parse_json(text)
                if payload:
                    product = _find_product(payload)
                    if product:
                        self._latest_product = product
                        blobs.append(
                            EvidenceBlob(
                                source="sephora_nuxt_product",
                                selector="script#__NUXT__",
                                index=-1,
                                payload=dict(product),
                            )
                        )

        jsonld_payload = self._extract_jsonld_product(soup)
        if jsonld_payload:
            self._jsonld_product = jsonld_payload
            if not self._latest_product:
                self._latest_product = jsonld_payload

        return tuple(blobs)

    def _extract_jsonld_product(self, soup: BeautifulSoup) -> Mapping[str, object] | None:
        for script in soup.select("script[type='application/ld+json']"):
            text = script.string or script.get_text()
            if not text:
                continue
            candidate = _parse_json(text)
            if candidate and isinstance(candidate, Mapping) and candidate.get("productGroupID"):
                return candidate
        return None

    def retailer_specific_fixes(
        self,
        parent: ParentProduct | None,
        variants: list[Variant],
        profile_name: str | None = None,
    ) -> None:
        if not parent:
            return

        if not variants:
            sku_id = self._sku_id_from_url(parent.pdp_url)
            if sku_id:
                variants.append(
                    Variant(
                        retailer=self.retailer,
                        parent_product_id=parent.parent_product_id,
                        variant_id=sku_id,
                        shade_name_raw=None,
                        shade_name_normalized=None,
                        size_text_raw=None,
                        price_raw=None,
                        price=None,
                        currency=None,
                        barcode=None,
                        swatch_image_url=None,
                        hero_image_url=None,
                        availability=None,
                        source_index=None,
                        qa_flags=(),
                        extras={},
                    )
                )

        product = self._latest_product if isinstance(self._latest_product, Mapping) else None
        jsonld = self._jsonld_product if isinstance(self._jsonld_product, Mapping) else None
        if not product and not jsonld:
            return
        product_details = None
        if product:
            details_candidate = product.get("productDetails")
            if isinstance(details_candidate, Mapping):
                product_details = details_candidate

        title_source = jsonld or product
        title = _sanitize_text((title_source or {}).get("name") or (product or {}).get("displayName"))
        if not title and product_details:
            title = _sanitize_text(product_details.get("displayName"))
        if title:
            parent.title_raw = title
            parent.title_normalized = title

        brand_obj = (jsonld or product or {}).get("brand")
        if isinstance(brand_obj, Mapping):
            brand = _sanitize_text(brand_obj.get("name"))
        else:
            brand = _sanitize_text(brand_obj)
        if not brand and product_details:
            detail_brand = product_details.get("brand")
            if isinstance(detail_brand, Mapping):
                brand = _sanitize_text(detail_brand.get("displayName") or detail_brand.get("name"))
            else:
                brand = _sanitize_text(detail_brand)
        if brand:
            parent.brand_raw = brand
            parent.brand_normalized = brand.strip() or brand

        aggregate = None
        if jsonld and isinstance(jsonld.get("aggregateRating"), Mapping):
            aggregate = jsonld.get("aggregateRating")
        elif product and isinstance(product.get("aggregateRating"), Mapping):
            aggregate = product.get("aggregateRating")
        if isinstance(aggregate, Mapping):
            rating = _coerce_float(aggregate.get("ratingValue"))
            if rating is not None:
                parent.extras["rating"] = rating
            review_count = aggregate.get("reviewCount")
            if isinstance(review_count, (int, float)):
                parent.extras["review_count"] = int(review_count)
            elif isinstance(review_count, str) and review_count.isdigit():
                parent.extras["review_count"] = int(review_count)
        else:
            rating = _coerce_float(product.get("rating"))
            if rating is not None:
                parent.extras["rating"] = rating
        if "rating" not in parent.extras and product_details:
            rating = _coerce_float(product_details.get("rating"))
            if rating is not None:
                parent.extras["rating"] = rating

        review_count = (product or {}).get("reviewsCount")
        if isinstance(review_count, (int, float)):
            parent.extras["review_count"] = int(review_count)
        elif isinstance(review_count, str) and review_count.strip().isdigit():
            parent.extras["review_count"] = int(review_count.strip())
        if "review_count" not in parent.extras and product_details:
            review_count = product_details.get("reviews")
            if isinstance(review_count, (int, float)):
                parent.extras["review_count"] = int(review_count)
            elif isinstance(review_count, str) and review_count.strip().isdigit():
                parent.extras["review_count"] = int(review_count.strip())

        ratings_summary = (product or {}).get("ratingsAndReviews")
        if isinstance(ratings_summary, Mapping):
            positive = ratings_summary.get("topPositive")
            if isinstance(positive, Mapping):
                headline = _sanitize_text(positive.get("title"))
                quote = _sanitize_text(positive.get("quote"))
                if headline or quote:
                    summary: dict[str, str] = {}
                    if headline:
                        summary["headline"] = headline
                    if quote:
                        summary["comment"] = quote
                    parent.extras["reviews_positive"] = summary
            negative = ratings_summary.get("topCritical")
            if isinstance(negative, Mapping):
                headline = _sanitize_text(negative.get("title"))
                quote = _sanitize_text(negative.get("quote"))
                if headline or quote:
                    summary = {}
                    if headline:
                        summary["headline"] = headline
                    if quote:
                        summary["comment"] = quote
                    parent.extras["reviews_negative"] = summary

        reviews = None
        if jsonld and isinstance(jsonld.get("reviews"), Sequence):
            reviews = jsonld.get("reviews")
        elif product and isinstance(product.get("reviews"), Sequence):
            reviews = product.get("reviews")
        if isinstance(reviews, Sequence):
            cleaned_reviews: list[dict[str, object]] = []
            for entry in reviews:
                if not isinstance(entry, Mapping):
                    continue
                review_record: dict[str, object] = {}
                headline = _sanitize_text(entry.get("title"))
                if headline:
                    review_record["headline"] = headline
                detail = _sanitize_text(entry.get("detail"))
                if detail:
                    review_record["comment"] = detail
                author = _sanitize_text(entry.get("author"))
                if author:
                    review_record["author"] = author
                submitted = _sanitize_text(entry.get("submittedAt"))
                if submitted:
                    review_record["created_date"] = submitted
                location = _sanitize_text(entry.get("location"))
                if location:
                    review_record["location"] = location
                rating_value = _coerce_float(entry.get("rating"))
                if rating_value is not None:
                    review_record["rating"] = rating_value
                if review_record:
                    cleaned_reviews.append(review_record)
            if cleaned_reviews:
                parent.extras["reviews"] = cleaned_reviews

        details: dict[str, object] = parent.extras.setdefault("details", {})  # type: ignore[assignment]
        description_source = jsonld or product or {}
        description = _clean_html(description_source.get("description"))
        if not description and product_details:
            description = _clean_html(
                product_details.get("longDescription") or product_details.get("shortDescription")
            )
        if description:
            details.setdefault("description_markdown", description)
        usage = _clean_html((product or {}).get("howToUse"))
        if not usage and product_details:
            usage = _clean_html(product_details.get("suggestedUsage"))
        if usage:
            details.setdefault("usage", usage)
        ingredients = _clean_html((product or {}).get("ingredients"))
        if not ingredients and product_details:
            ingredients = _clean_html(product_details.get("ingredients"))
        if ingredients:
            details.setdefault("ingredients", ingredients)
        benefits = (product or {}).get("benefits")
        if isinstance(benefits, Sequence):
            cleaned_benefits = [_sanitize_text(item) for item in benefits if _sanitize_text(item)]
            if cleaned_benefits:
                details.setdefault("features", [benefit for benefit in cleaned_benefits if benefit])
        if "summary" not in parent.extras and product_details:
            summary = _clean_html(product_details.get("shortDescription"))
            if summary:
                parent.extras["summary"] = summary

        sku_map: dict[str, Mapping[str, object]] = {}
        skus = (product or {}).get("skus")
        if isinstance(skus, Sequence):
            for sku in skus:
                if isinstance(sku, Mapping):
                    sku_id = _sanitize_text(sku.get("skuId") or sku.get("sku"))
                    if sku_id:
                        sku_map[sku_id] = sku

        # Normalize variant IDs to use the retailer SKU (skuId) so joins to sales data work.
        if sku_map and variants:
            sku_keys = list(sku_map.keys())
            default_sku = _sanitize_text((product or {}).get("mainSku", {}).get("skuId")) if isinstance((product or {}).get("mainSku"), Mapping) else None
            for idx, variant in enumerate(variants):
                if variant.variant_id in sku_map:
                    continue
                # Prefer the default sku from the PDP if available.
                if default_sku and default_sku in sku_map:
                    variant.variant_id = default_sku
                # Else, if there is only one SKU, use it.
                elif len(sku_keys) == 1:
                    variant.variant_id = sku_keys[0]
                # Else, try to align by position if available; fall back to first.
                else:
                    candidate = sku_keys[variant.source_index] if variant.source_index is not None and 0 <= variant.source_index < len(sku_keys) else sku_keys[0]
                    variant.variant_id = candidate

        for variant in variants:
            payload = sku_map.get(variant.variant_id)
            if not payload:
                continue

            if not variant.availability:
                availability = payload.get("inventoryStatus")
                if isinstance(availability, str) and availability:
                    variant.availability = availability

            marketing_tags = payload.get("promotionTags")
            if isinstance(marketing_tags, Sequence):
                tags = [str(tag).strip() for tag in marketing_tags if tag not in (None, "")]
                if tags:
                    variant.extras.setdefault("promotion_tags", tags)

            attributes = payload.get("attributes")
            if isinstance(attributes, Mapping):
                existing = variant.extras.get("attributes")
                if isinstance(existing, Mapping):
                    merged = dict(existing)
                    for key, value in attributes.items():
                        if key not in merged and isinstance(value, str):
                            merged[key] = value
                    variant.extras["attributes"] = merged
                else:
                    variant.extras["attributes"] = dict(attributes)

            variation_value = _sanitize_text(payload.get("variationValue"))
            variation_desc = _sanitize_text(payload.get("variationDesc"))
            if not variant.shade_name_raw:
                candidate = variation_value or variation_desc
                if candidate:
                    variant.shade_name_raw = candidate
                    variant.shade_name_normalized = candidate
            else:
                raw_sku = payload.get("skuId") or payload.get("sku")
                sku_id = None
                if isinstance(raw_sku, (str, int)):
                    sku_id = str(raw_sku)
                if sku_id and variant.shade_name_raw:
                    if variant.shade_name_raw.strip().startswith(sku_id) and (variation_value or variation_desc):
                        candidate = variation_value or variation_desc
                        if candidate:
                            variant.shade_name_raw = candidate
                            variant.shade_name_normalized = candidate
            if variation_desc and "shade_description" not in variant.extras:
                variant.extras["shade_description"] = variation_desc

            if not variant.size_text_raw:
                size_text = _sanitize_text(payload.get("size"))
                if size_text:
                    variant.size_text_raw = size_text

            if not variant.swatch_image_url:
                swatch = _sanitize_text(payload.get("smallImage"))
                if not swatch:
                    swatch = _extract_image_url(payload.get("swatchImage"))
                if swatch:
                    variant.swatch_image_url = swatch

            if not variant.hero_image_url:
                hero = _extract_image_url(payload.get("skuImages"))
                if not hero:
                    hero = _extract_image_url(payload.get("primaryImage"))
                if not hero:
                    alt_images = payload.get("alternateImages")
                    if isinstance(alt_images, Sequence) and not isinstance(alt_images, (str, bytes, bytearray)) and alt_images:
                        hero = _extract_image_url(alt_images[0])
                if hero:
                    variant.hero_image_url = hero

            if "ingredients" not in details:
                ingredient_desc = _sanitize_text(payload.get("ingredientDesc"))
                if ingredient_desc:
                    details["ingredients"] = ingredient_desc

        if "features" not in details:
            highlight_items: list[str] = []
            for payload in sku_map.values():
                highlights = payload.get("highlights")
                if isinstance(highlights, Sequence) and not isinstance(highlights, (str, bytes, bytearray)):
                    for item in highlights:
                        if isinstance(item, Mapping):
                            name = _sanitize_text(item.get("name") or item.get("altText"))
                            if name:
                                highlight_items.append(name)
                        elif isinstance(item, str):
                            cleaned = item.strip()
                            if cleaned:
                                highlight_items.append(cleaned)
            if highlight_items:
                details["features"] = list(dict.fromkeys(highlight_items))

        for variant in variants:
            if isinstance(variant.availability, str) and "schema.org" in variant.availability:
                variant.availability = variant.availability.rsplit("/", 1)[-1]

        if len(variants) == 1:
            variant = variants[0]
            if variant.variant_id and variant.variant_id.upper().startswith("P"):
                sku_id = self._sku_id_from_url(parent.pdp_url)
                if sku_id:
                    variant.variant_id = sku_id

        self._latest_product = None
        self._jsonld_product = None


__all__ = ["SephoraAdapter"]
