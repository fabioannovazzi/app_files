from __future__ import annotations

import json
import os
import re
from typing import Sequence
from urllib.parse import urlencode, urljoin
from urllib.request import urlopen

from bs4 import BeautifulSoup  # type: ignore[import]

from ..models import EvidenceBlob, ParentProduct, Variant
from . import RetailerAdapter

__all__ = ["CosmoprofbeautyAdapter"]

_PARENT_FROM_URL = re.compile(r"/([^/?#]+)\.html", re.IGNORECASE)
_STYLE_URL = re.compile(r"url\((['\"]?)(.*?)\1\)", re.IGNORECASE)
_BV_BATCH_ENDPOINT = "https://api.bazaarvoice.com/data/batch.json"
_BV_PASSKEY = os.getenv("COSMOPROF_BV_PASSKEY", "").strip()
_BV_DISPLAY_CODE = "37382-en_us"
_BV_API_VERSION = "5.5"


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def _clean_lines(container: object) -> str | None:
    if container is None or not hasattr(container, "get_text"):
        return None
    text = _clean_text(container.get_text("\n", strip=True))
    return text or None


def _extract_style_url(value: object) -> str | None:
    style = _clean_text(value)
    if not style:
        return None
    match = _STYLE_URL.search(style)
    if not match:
        return None
    url = _clean_text(match.group(2))
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    return url


def _extract_bv_product_id(soup: BeautifulSoup) -> str | None:
    node = soup.select_one("[data-bv-product-id]")
    if node is None:
        return None
    return _clean_text(node.get("data-bv-product-id"))


def _extract_title(soup: BeautifulSoup) -> str | None:
    heading = soup.select_one("h1.product-name[itemprop='name'], h1.product-name")
    if heading is not None:
        title = _clean_text(heading.get_text(" ", strip=True))
        if title:
            return title
    return None


def _extract_brand(soup: BeautifulSoup) -> str | None:
    meta = soup.select_one("meta[itemprop='brand']")
    if meta is not None:
        brand = _clean_text(meta.get("content"))
        if brand:
            return brand
    brand_link = soup.select_one(".h5 .pdp-brand:last-of-type")
    if brand_link is not None:
        brand = _clean_text(brand_link.get_text(" ", strip=True))
        if brand:
            return brand
    return None


def _extract_summary(soup: BeautifulSoup) -> str | None:
    meta = soup.select_one("meta[name='description']")
    if meta is not None:
        summary = _clean_text(meta.get("content"))
        if summary:
            return summary
    details = soup.select_one("div[id^='detailstab-'] > div")
    return _clean_lines(details)


def _extract_category_path(soup: BeautifulSoup) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for element in soup.select(".breadcrumb a"):
        label = _clean_text(element.get_text(" ", strip=True))
        key = str(label or "").casefold()
        if not label or key in seen:
            continue
        seen.add(key)
        items.append(label)
    return items


def _extract_gallery_images(soup: BeautifulSoup) -> list[str]:
    images: list[str] = []
    seen: set[str] = set()
    for image in soup.select(".pdp-carousel img[src], .pdp-carousel img[data-src]"):
        candidate = _clean_text(image.get("src")) or _clean_text(image.get("data-src"))
        if not candidate or candidate.startswith("data:"):
            continue
        if candidate.startswith("//"):
            candidate = f"https:{candidate}"
        if candidate in seen:
            continue
        seen.add(candidate)
        images.append(candidate)
    return images


def _extract_details(soup: BeautifulSoup) -> dict[str, object]:
    details: dict[str, object] = {}

    description = _clean_lines(soup.select_one("div[id^='detailstab-'] > div"))
    if description:
        details["description_markdown"] = description

    usage = _clean_lines(soup.select_one("div[id^='directionstab-'] > div"))
    if usage:
        details["usage"] = usage

    features_container = soup.select_one("div[id^='featuresbenefitstab-'] > div")
    if features_container is not None:
        features = [
            text
            for item in features_container.select("li")
            for text in [_clean_text(item.get_text(" ", strip=True))]
            if text
        ]
        if features:
            details["features"] = features
        else:
            feature_text = _clean_lines(features_container)
            if feature_text:
                details["features"] = [feature_text]

    ingredients = _clean_lines(soup.select_one("div[id^='ingredientstab-'] > div"))
    if ingredients:
        details["ingredients"] = ingredients

    return details


def _fetch_bazaarvoice_batch(product_id: str) -> dict[str, object] | None:
    if not _BV_PASSKEY:
        return None
    params = [
        ("passkey", _BV_PASSKEY),
        ("apiversion", _BV_API_VERSION),
        ("displaycode", _BV_DISPLAY_CODE),
        ("resource.q0", "products"),
        ("filter.q0", f"id:eq:{product_id}"),
        ("stats.q0", "questions,reviews"),
        ("filteredstats.q0", "questions,reviews"),
        ("filter_questions.q0", "contentlocale:eq:en*,en_US"),
        ("filter_answers.q0", "contentlocale:eq:en*,en_US"),
        ("filter_reviews.q0", "contentlocale:eq:en*,en_US"),
        ("filter_reviewcomments.q0", "contentlocale:eq:en*,en_US"),
        ("resource.q2", "reviews"),
        ("filter.q2", "isratingsonly:eq:false"),
        ("filter.q2", f"productid:eq:{product_id}"),
        ("filter.q2", "contentlocale:eq:en*,en_US"),
        ("sort.q2", "relevancy:a1"),
        ("stats.q2", "reviews"),
        ("filteredstats.q2", "reviews"),
        ("include.q2", "authors,products,comments"),
        ("filter_reviews.q2", "contentlocale:eq:en*,en_US"),
        ("filter_reviewcomments.q2", "contentlocale:eq:en*,en_US"),
        ("filter_comments.q2", "contentlocale:eq:en*,en_US"),
        ("limit.q2", "8"),
        ("offset.q2", "0"),
        ("limit_comments.q2", "3"),
    ]
    request_url = f"{_BV_BATCH_ENDPOINT}?{urlencode(params, doseq=True)}"
    try:
        with urlopen(request_url, timeout=20) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _coerce_float(value: object) -> float | None:
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


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def _normalize_bazaarvoice_reviews(
    results: object,
    authors: object,
) -> list[dict[str, object]]:
    if not isinstance(results, list):
        return []
    author_map = authors if isinstance(authors, dict) else {}
    reviews: list[dict[str, object]] = []
    for entry in results:
        if not isinstance(entry, dict):
            continue
        review: dict[str, object] = {}
        review_id = _clean_text(entry.get("Id"))
        if review_id:
            review["review_id"] = review_id
        headline = _clean_text(entry.get("Title"))
        if headline:
            review["headline"] = headline
        comment = _clean_text(entry.get("ReviewText"))
        if comment:
            review["comment"] = comment
        rating = _coerce_float(entry.get("Rating"))
        if rating is not None:
            review["rating"] = rating
        created_date = _clean_text(entry.get("SubmissionTime"))
        if created_date:
            review["created_date"] = created_date
        author = _clean_text(entry.get("UserNickname"))
        if not author:
            author_id = _clean_text(entry.get("AuthorId"))
            author_payload = author_map.get(author_id) if author_id else None
            if isinstance(author_payload, dict):
                author = _clean_text(author_payload.get("UserNickname"))
        if author:
            review["author"] = author
        if review:
            reviews.append(review)
    return reviews


def _extract_bazaarvoice_reviews(
    product_id: str,
) -> tuple[float | None, int | None, list[dict[str, object]]]:
    payload = _fetch_bazaarvoice_batch(product_id)
    if not payload:
        return None, None, []

    batched = payload.get("BatchedResults")
    if not isinstance(batched, dict):
        return None, None, []

    product_query = batched.get("q0") if isinstance(batched.get("q0"), dict) else {}
    review_query = batched.get("q2") if isinstance(batched.get("q2"), dict) else {}

    rating: float | None = None
    review_count: int | None = None

    product_results = product_query.get("Results")
    if isinstance(product_results, list) and product_results:
        first_product = product_results[0]
        if isinstance(first_product, dict):
            review_stats = first_product.get("ReviewStatistics")
            if isinstance(review_stats, dict):
                rating = _coerce_float(review_stats.get("AverageOverallRating"))
                review_count = _coerce_int(
                    review_stats.get("TotalReviewCount")
                ) or _coerce_int(first_product.get("TotalReviewCount"))
            elif review_count is None:
                review_count = _coerce_int(first_product.get("TotalReviewCount"))

    reviews = _normalize_bazaarvoice_reviews(
        review_query.get("Results"),
        (
            (review_query.get("Includes") or {})
            if isinstance(review_query.get("Includes"), dict)
            else {}
        ).get("Authors"),
    )

    if review_count is None:
        review_count = _coerce_int(review_query.get("TotalResults"))
    if rating is None and reviews:
        rating_values = [
            value
            for value in (_coerce_float(review.get("rating")) for review in reviews)
            if value is not None
        ]
        if rating_values:
            rating = sum(rating_values) / len(rating_values)
    return rating, review_count, reviews


def _variant_payloads(soup: BeautifulSoup) -> list[dict[str, object]]:
    variants: list[dict[str, object]] = []
    seen_variant_ids: set[str] = set()

    for line in soup.select("div.swatch-line[data-pid]"):
        variant_id = _clean_text(line.get("data-pid"))
        if not variant_id or variant_id in seen_variant_ids:
            continue
        seen_variant_ids.add(variant_id)

        shade = _clean_text(
            (line.select_one(".variation-name") or line).get_text(" ", strip=True)
        )
        barcode = None
        filter_name = _clean_text(line.get("data-filter-name"))
        if filter_name:
            parts = [part.strip() for part in filter_name.split("|")]
            if len(parts) >= 3 and parts[2]:
                barcode = parts[2]

        swatch = line.select_one("[data-attr-value]")
        swatch_image = (
            _extract_style_url(swatch.get("style")) if swatch is not None else None
        )

        quantity_input = line.select_one(f"input[data-pid='{variant_id}']")
        attr_link = line.select_one(f"a[data-pid='{variant_id}']")
        extras: dict[str, object] = {}
        attr_value = (
            _clean_text(swatch.get("data-attr-value")) if swatch is not None else None
        )
        if attr_value:
            extras["attr_value"] = attr_value
        attr_url = (
            _clean_text(attr_link.get("data-attrurl"))
            if attr_link is not None
            else None
        )
        if attr_url:
            extras["attr_url"] = urljoin("https://www.cosmoprofbeauty.com", attr_url)
        if filter_name:
            extras["filter_name"] = filter_name
        quantity_url = (
            _clean_text(quantity_input.get("data-url"))
            if quantity_input is not None
            else None
        )
        if quantity_url:
            extras["availability_url"] = urljoin(
                "https://www.cosmoprofbeauty.com", quantity_url
            )

        variants.append(
            {
                "id": variant_id,
                "itemId": variant_id,
                "shade": shade,
                "barcode": barcode,
                "image": swatch_image,
                "swatchImage": swatch_image,
                "availability": None,
                "attributes": extras or None,
            }
        )

    return variants


class CosmoprofbeautyAdapter(RetailerAdapter):
    """Parse CosmoProf Beauty PDPs from server-rendered DOM state."""

    retailer = "cosmoprofbeauty"

    def __init__(self) -> None:
        self._gallery_images: list[str] = []
        self._details: dict[str, object] = {}
        self._reviews: list[dict[str, object]] = []
        self._review_count: int | None = None
        self._review_rating: float | None = None
        self._bv_product_id: str | None = None
        self._dom_title: str | None = None
        self._dom_brand: str | None = None
        self._dom_summary: str | None = None
        self._dom_category_path: tuple[str, ...] = ()

    def primary_id_from_url(self, url: str) -> str | None:
        match = _PARENT_FROM_URL.search(url)
        if not match:
            return None
        return _clean_text(match.group(1))

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        self._gallery_images = []
        self._details = {}
        self._reviews = []
        self._review_count = None
        self._review_rating = None
        self._bv_product_id = None
        self._dom_title = None
        self._dom_brand = None
        self._dom_summary = None
        self._dom_category_path = ()

        soup = BeautifulSoup(html, "lxml")
        title = _extract_title(soup)
        brand = _extract_brand(soup)
        summary = _extract_summary(soup)
        category_path = _extract_category_path(soup)
        self._dom_title = title
        self._dom_brand = brand
        self._dom_summary = summary
        self._dom_category_path = tuple(category_path)
        variants = _variant_payloads(soup)
        self._gallery_images = _extract_gallery_images(soup)
        self._details = _extract_details(soup)
        self._bv_product_id = _extract_bv_product_id(soup)
        if self._bv_product_id:
            (
                self._review_rating,
                self._review_count,
                self._reviews,
            ) = _extract_bazaarvoice_reviews(self._bv_product_id)

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
                source="cosmoprofbeauty_dom_state",
                selector="div.swatch-line[data-pid]",
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
            current_title = (parent.title_raw or "").strip().casefold()
            if self._dom_title and (not current_title or current_title == "cosmoprof"):
                parent.title_raw = self._dom_title
                parent.title_normalized = self._dom_title
            if self._dom_brand and not (parent.brand_raw or "").strip():
                parent.brand_raw = self._dom_brand
                parent.brand_normalized = self._dom_brand
            if self._dom_summary and not parent.extras.get("summary"):
                parent.extras["summary"] = self._dom_summary
            if self._dom_category_path and not tuple(parent.category_path):
                parent.category_path = self._dom_category_path
            if self._gallery_images:
                parent.extras["gallery_images"] = list(self._gallery_images)
                parent.extras["hero_image_url"] = self._gallery_images[0]
            if self._details:
                parent.extras["details"] = dict(self._details)
            if self._review_rating is not None:
                parent.extras["rating"] = self._review_rating
            if self._review_count is not None:
                parent.extras["review_count"] = self._review_count
            if self._reviews:
                parent.extras["reviews"] = list(self._reviews)
            if self._bv_product_id:
                parent.extras["reviews_meta"] = {
                    "provider": "bazaarvoice",
                    "product_id": self._bv_product_id,
                }
