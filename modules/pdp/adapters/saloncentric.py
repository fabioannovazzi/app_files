from __future__ import annotations

import json
import re
from json import JSONDecodeError
from typing import Any, Mapping, Sequence

from bs4 import BeautifulSoup  # type: ignore[import]

from ..models import EvidenceBlob, ParentProduct, Variant
from . import RetailerAdapter

__all__ = ["SaloncentricAdapter"]

_PARENT_FROM_URL = re.compile(r"/([^/?#]+)\.html", re.IGNORECASE)
_SIZE_IN_TITLE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:oz|fl\.?\s*oz|ml|g|kg|lb|lbs)\.?)",
    re.IGNORECASE,
)
_PREVIEW_IMAGE_INDEX = re.compile(r"preview image\s+(\d+)", re.IGNORECASE)
_TWIC_PREFIX = "image:"
_TWIC_MEDIA_BASE = "https://media.saloncentric.com"


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def _parse_json_value(raw: object) -> Any | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except JSONDecodeError:
        return None


def _extract_title(soup: BeautifulSoup, master_tracking: Mapping[str, str]) -> str | None:
    tracked = _clean_text(master_tracking.get("data-product-name"))
    if tracked:
        return tracked
    heading = soup.select_one("h1")
    if heading:
        title = _clean_text(heading.get_text(" ", strip=True))
        if title:
            return title
    og_title = soup.select_one("meta[property='og:title']")
    if og_title:
        title = _clean_text(og_title.get("content"))
        if title:
            return title
    return None


def _extract_brand(soup: BeautifulSoup, master_tracking: Mapping[str, str]) -> str | None:
    tracked_brand = _clean_text(master_tracking.get("data-product-brand"))
    if tracked_brand:
        return tracked_brand
    meta_brand = soup.select_one("meta[itemprop='brand']")
    if meta_brand:
        brand = _clean_text(meta_brand.get("content"))
        if brand:
            return brand
    return None


def _extract_summary(soup: BeautifulSoup) -> str | None:
    description_meta = soup.select_one("meta[name='description']")
    if description_meta:
        description = _clean_text(description_meta.get("content"))
        if description:
            return description
    for candidate in soup.select("[itemprop='description']"):
        description = _clean_text(candidate.get_text(" ", strip=True))
        if description:
            return description
    return None


def _extract_category_path(
    soup: BeautifulSoup,
    master_tracking: Mapping[str, str],
) -> list[str]:
    breakout = _clean_text(master_tracking.get("data-category-breakout"))
    if breakout:
        return [part.strip() for part in breakout.split(">") if part.strip()]

    breadcrumb_items: list[str] = []
    for element in soup.select(".breadcrumb li, .breadcrumbs li, [aria-label='breadcrumb'] li"):
        label = _clean_text(element.get_text(" ", strip=True))
        if label and label.lower() not in {"home"}:
            breadcrumb_items.append(label)
    return breadcrumb_items


def _size_from_title(title: str | None) -> str | None:
    if not title:
        return None
    match = _SIZE_IN_TITLE.search(title)
    if not match:
        return None
    return _clean_text(match.group(1))


def _availability_from_values(
    *,
    class_names: Sequence[str],
    product_status: str | None,
) -> str | None:
    class_values = {str(name).strip().lower() for name in class_names if str(name).strip()}
    if "in_stock" in class_values:
        return "InStock"
    if "out_of_stock" in class_values:
        return "OutOfStock"
    status = str(product_status or "").strip().lower()
    if not status:
        return None
    if "in stock" in status:
        return "InStock"
    if "out of stock" in status:
        return "OutOfStock"
    return None


def _tracking_divs_by_id(soup: BeautifulSoup) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    variant_tracking: dict[str, dict[str, str]] = {}
    master_tracking: dict[str, str] = {}
    for element in soup.select("div[id^='product-dynamic-tracking-']"):
        attrs = {
            str(key): str(value)
            for key, value in element.attrs.items()
            if isinstance(key, str) and key.startswith("data-")
        }
        element_id = str(element.get("id") or "").strip()
        suffix = element_id.removeprefix("product-dynamic-tracking-")
        if suffix.isdigit():
            variant_tracking[suffix] = attrs
        elif attrs and not master_tracking:
            master_tracking = attrs
    return variant_tracking, master_tracking


def _direct_itemprop_text(review: object, itemprop: str) -> str | None:
    if not hasattr(review, "find_all"):
        return None
    elements = review.find_all(attrs={"itemprop": itemprop}, recursive=False)
    for element in elements:
        text = _clean_text(element.get_text(" ", strip=True))
        if text:
            return text
    return None


def _direct_itemprop_attr(review: object, itemprop: str, attr: str) -> str | None:
    if not hasattr(review, "find_all"):
        return None
    elements = review.find_all(attrs={"itemprop": itemprop}, recursive=False)
    for element in elements:
        value = _clean_text(element.get(attr))
        if value:
            return value
    return None


def _parse_review_rating(value: object) -> float | None:
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


def _extract_reviews(soup: BeautifulSoup) -> list[dict[str, object]]:
    reviews: list[dict[str, object]] = []
    seen_review_ids: set[str] = set()
    for review in soup.select("#bvseo-reviewsSection .bvseo-review[itemprop='review']"):
        review_id = _clean_text(review.get("data-reviewid"))
        if review_id and review_id in seen_review_ids:
            continue
        if review_id:
            seen_review_ids.add(review_id)

        review_record: dict[str, object] = {}
        if review_id:
            review_record["review_id"] = review_id

        headline = _direct_itemprop_text(review, "name")
        if headline:
            review_record["headline"] = headline

        comment = _direct_itemprop_text(review, "description")
        if comment:
            review_record["comment"] = comment

        author = None
        author_container = review.find(attrs={"itemprop": "author"})
        if author_container is not None:
            author = _clean_text(author_container.get_text(" ", strip=True))
        if author:
            review_record["author"] = author

        created_date = _direct_itemprop_attr(review, "datePublished", "content")
        if created_date:
            review_record["created_date"] = created_date

        rating_element = review.find(attrs={"itemprop": "ratingValue"})
        rating = _parse_review_rating(
            rating_element.get_text(" ", strip=True) if rating_element is not None else None
        )
        if rating is not None:
            review_record["rating"] = rating

        if review_record:
            reviews.append(review_record)
    return reviews


def _gallery_sort_key(tag: object) -> tuple[int, str]:
    alt = ""
    if tag is not None and hasattr(tag, "get"):
        alt = _clean_text(tag.get("alt")) or _clean_text(tag.get("title")) or ""
    match = _PREVIEW_IMAGE_INDEX.search(alt)
    if match:
        return (int(match.group(1)), alt)
    return (10_000, alt)


def _extract_gallery_image_url(tag: object) -> str | None:
    if tag is None or not hasattr(tag, "get"):
        return None

    raw_payload = _parse_json_value(tag.get("data-large-img"))
    if isinstance(raw_payload, Mapping):
        for key in ("hires", "url"):
            candidate = _clean_text(raw_payload.get(key))
            if candidate and candidate.startswith(("http://", "https://")):
                return candidate
        devices = raw_payload.get("devicesUrls")
        if isinstance(devices, Mapping):
            for key in (
                "desktop",
                "retinadesktop",
                "tablet",
                "retinatablet",
                "mobile",
                "retinamobile",
            ):
                candidate = _clean_text(devices.get(key))
                if candidate and candidate.startswith(("http://", "https://")):
                    return candidate
    return _extract_image_url(tag)


def _extract_gallery_images(soup: BeautifulSoup) -> list[str]:
    images: list[tuple[tuple[int, str], str]] = []
    seen: set[str] = set()
    for tag in soup.select("img[data-large-img], img[data-twic-src*='/large/']"):
        url = _extract_gallery_image_url(tag)
        if not url or url in seen:
            continue
        seen.add(url)
        images.append((_gallery_sort_key(tag), url))
    images.sort(key=lambda item: item[0])
    return [url for _, url in images]


def _extract_image_url(tag: object) -> str | None:
    if tag is None or not hasattr(tag, "get"):
        return None

    def _twic_candidate() -> str | None:
        raw = _clean_text(tag.get("data-twic-src"))
        if not raw or not raw.startswith(_TWIC_PREFIX):
            return None
        path = raw[len(_TWIC_PREFIX) :].strip()
        if not path.startswith("/"):
            path = f"/{path}"
        transform = _clean_text(tag.get("data-twic-transform"))
        if transform and "WxH" not in transform:
            return f"{_TWIC_MEDIA_BASE}{path}?twic=v1/{transform}"
        return f"{_TWIC_MEDIA_BASE}{path}"

    def _valid_candidate(value: object) -> str | None:
        text = _clean_text(value)
        if not text:
            return None
        if text.startswith("data:"):
            return None
        if text.startswith("//"):
            return f"https:{text}"
        if text.startswith("http://") or text.startswith("https://"):
            return text
        return None

    candidate = _twic_candidate()
    if candidate:
        return candidate

    for attr in ("data-src", "data-lazy-src", "data-zoom-image", "src"):
        candidate = _valid_candidate(tag.get(attr))
        if candidate:
            return candidate

    srcset = _clean_text(tag.get("srcset")) or _clean_text(tag.get("data-srcset"))
    if srcset:
        for part in srcset.split(","):
            candidate = _valid_candidate(part.strip().split(" ", 1)[0])
            if candidate:
                return candidate
    return None


class SaloncentricAdapter(RetailerAdapter):
    """Parse SalonCentric PDPs from DOM state and data attributes."""

    retailer = "saloncentric"

    def __init__(self) -> None:
        self._review_count: int | None = None
        self._review_rating: float | None = None
        self._reviews: list[dict[str, object]] = []
        self._parent_hero_image: str | None = None
        self._gallery_images: list[str] = []

    def primary_id_from_url(self, url: str) -> str | None:
        match = _PARENT_FROM_URL.search(url)
        if not match:
            return None
        return _clean_text(match.group(1))

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        self._review_count = None
        self._review_rating = None
        self._reviews = []
        self._parent_hero_image = None
        self._gallery_images = []
        soup = BeautifulSoup(html, "lxml")
        tracking_by_variant, master_tracking = _tracking_divs_by_id(soup)

        title = _extract_title(soup, master_tracking)
        brand = _extract_brand(soup, master_tracking)
        summary = _extract_summary(soup)
        category_path = _extract_category_path(soup, master_tracking)
        size_text = _size_from_title(title)

        review_count_raw = _clean_text(master_tracking.get("data-product-number-reviews"))
        self._review_count = int(review_count_raw) if review_count_raw and review_count_raw.isdigit() else None
        review_rating_raw = _clean_text(master_tracking.get("data-product-number-stars"))
        try:
            self._review_rating = float(review_rating_raw) if review_rating_raw else None
        except ValueError:
            self._review_rating = None
        self._reviews = _extract_reviews(soup)
        self._gallery_images = _extract_gallery_images(soup)
        self._parent_hero_image = self._gallery_images[0] if self._gallery_images else None

        variants: list[dict[str, object]] = []
        seen_variant_ids: set[str] = set()
        for element in soup.select("li.product_shade_item[data-product-id]"):
            variant_id = _clean_text(element.get("data-product-id"))
            if not variant_id or variant_id in seen_variant_ids:
                continue
            seen_variant_ids.add(variant_id)

            search_payload = _parse_json_value(element.get("data-product-search-query"))
            info_payload = _parse_json_value(element.get("data-product-information"))
            search_values = search_payload if isinstance(search_payload, list) else []
            info_values = info_payload if isinstance(info_payload, Mapping) else {}
            tracking = tracking_by_variant.get(variant_id, {})

            shade = None
            product_code = None
            if len(search_values) >= 3:
                shade = _clean_text(search_values[2])
            if len(search_values) >= 5:
                product_code = _clean_text(search_values[4])

            image = None
            image_tag = element.select_one("img")
            if image_tag:
                image = _extract_image_url(image_tag)

            price = _clean_text(tracking.get("data-fromated-price"))
            currency = "USD" if price else None
            status = _clean_text(tracking.get("data-product-status"))
            availability = _availability_from_values(
                class_names=element.get("class", []),
                product_status=status,
            )

            attributes: dict[str, object] = {}
            level = _clean_text(element.get("data-product-level"))
            if level:
                attributes["level"] = level
            collection = _clean_text(element.get("data-product-collection"))
            if collection:
                attributes["collection"] = collection
            if product_code:
                attributes["product_code"] = product_code

            variant_payload: dict[str, object] = {
                "id": variant_id,
                "shade": shade,
                "size": size_text,
                "price": price,
                "currency": currency,
                "image": image,
                "swatchImage": image,
                "availability": availability,
                "attributes": attributes or None,
                "variantLabel": _clean_text(element.get_text(" ", strip=True)),
                "itemId": variant_id,
            }
            if isinstance(info_values, Mapping):
                master_id = _clean_text(info_values.get("masterProductID"))
                if master_id:
                    variant_payload["masterProductID"] = master_id
            variants.append(variant_payload)

        payload: dict[str, object] = {}
        if brand:
            payload["brand"] = brand
        if title:
            payload["name"] = title
        if summary:
            payload["description"] = summary
        if category_path:
            payload["categoryPath"] = category_path
        if variants:
            payload["variants"] = variants

        if not payload:
            return ()
        return (
            EvidenceBlob(
                source="saloncentric_dom_state",
                selector="li.product_shade_item[data-product-id]",
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
        if parent is not None:
            if self._review_count is not None:
                parent.extras["review_count"] = self._review_count
            if self._review_rating is not None:
                parent.extras["review_rating"] = self._review_rating
            if self._reviews:
                parent.extras["reviews"] = self._reviews
                parent.extras["reviews_meta"] = {"provider": "bazaarvoice"}
            if self._parent_hero_image:
                parent.extras["hero_image_url"] = self._parent_hero_image
            if self._gallery_images:
                parent.extras["gallery_images"] = list(self._gallery_images)

        deduped: list[Variant] = []
        seen_variant_ids: set[str] = set()
        for variant in variants:
            variant_id = _clean_text(variant.variant_id)
            if not variant_id or variant_id in seen_variant_ids:
                continue
            seen_variant_ids.add(variant_id)
            deduped.append(variant)
        variants.clear()
        variants.extend(deduped)
