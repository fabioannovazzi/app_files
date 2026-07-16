from __future__ import annotations

import json
import re
from json import JSONDecodeError
from typing import Mapping, Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup  # type: ignore[import]

from ..models import EvidenceBlob, ParentProduct, Variant
from . import RetailerAdapter

__all__ = ["ChewyAdapter"]

_MAX_REVIEWS = 5
_PARENT_FROM_URL = re.compile(r"/dp/(\d+)", re.IGNORECASE)
_MONEY = re.compile(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)")
_SIZE_IN_TITLE = re.compile(
    r",\s*((?:\d+(?:\.\d+)?\s*[- ]?\s*)?(?:oz|fl\.?\s*oz|lb|lbs|g|kg|ml)"
    r"(?:[^,]*)(?:,\s*(?:case|pack|bundle|tray|box|bag|can|count)\b[^,]*)?)$",
    re.IGNORECASE,
)


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def _extract_title(soup: BeautifulSoup) -> str | None:
    heading = soup.select_one("h1")
    if heading is not None:
        title = _clean_text(heading.get_text(" ", strip=True))
        if title:
            return title
    for selector in ("meta[property='og:title']", "title"):
        element = soup.select_one(selector)
        if element is None:
            continue
        title = _clean_text(
            element.get("content")
            if element.name == "meta"
            else element.get_text(" ", strip=True)
        )
        if title:
            return title.replace(" - Chewy.com", "").strip()
    return None


def _extract_brand(soup: BeautifulSoup) -> str | None:
    for selector in (
        "[data-testid*='brand' i] a",
        ".product-brand a",
        "[itemprop='brand']",
        "meta[itemprop='brand']",
        "meta[property='product:brand']",
    ):
        element = soup.select_one(selector)
        if element is None:
            continue
        brand = _clean_text(
            element.get("content")
            if element.name == "meta"
            else element.get_text(" ", strip=True)
        )
        if brand:
            return brand.removeprefix("By ").strip()

    heading = soup.select_one("h1")
    brand_link = heading.find_next("a", href=True) if heading is not None else None
    if brand_link is not None:
        brand = _clean_text(brand_link.get_text(" ", strip=True))
        if brand and not brand.lower().startswith(("image:", "rated ")):
            return brand

    body_text = _clean_text(soup.get_text("\n", strip=True)) or ""
    match = re.search(r"\bBy\s+(.+?)\s+Rated\s+\d", body_text, re.IGNORECASE)
    if match:
        return _clean_text(match.group(1))
    return None


def _extract_category_path(soup: BeautifulSoup) -> list[str]:
    selectors = (
        "nav[aria-label*='breadcrumb' i] a",
        "[data-testid*='breadcrumb' i] a",
        ".breadcrumb a",
        "ol[itemscope] a",
    )
    items: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        for element in soup.select(selector):
            label = _clean_text(element.get_text(" ", strip=True))
            key = str(label or "").casefold()
            if not label or key in {"home", "chewy"} or key in seen:
                continue
            seen.add(key)
            items.append(label)
        if items:
            return items
    return items


def _valid_url(value: object) -> str | None:
    text = _clean_text(value)
    if not text or text.startswith("data:"):
        return None
    if text.startswith("//"):
        return f"https:{text}"
    if text.startswith(("http://", "https://")):
        return text
    if text.startswith("/"):
        return urljoin("https://www.chewy.com", text)
    return None


def _extract_srcset_url(value: object) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    candidates = [part.strip().split(" ", 1)[0] for part in text.split(",")]
    for candidate in reversed(candidates):
        url = _valid_url(candidate)
        if url:
            return url
    return None


def _extract_image_url(tag: object) -> str | None:
    if tag is None or not hasattr(tag, "get"):
        return None
    for attr in ("src", "data-src", "data-lazy-src", "data-zoom-image"):
        url = _valid_url(tag.get(attr))
        if url:
            return url
    for attr in ("srcset", "data-srcset"):
        url = _extract_srcset_url(tag.get(attr))
        if url:
            return url
    return None


def _extract_gallery_images(soup: BeautifulSoup, title: str | None) -> list[str]:
    title_key = str(title or "").casefold()
    images: list[str] = []
    seen: set[str] = set()
    for image in soup.select("img[src], img[data-src], img[srcset], img[data-srcset]"):
        alt = _clean_text(image.get("alt")) or _clean_text(image.get("title")) or ""
        if (
            title_key
            and title_key not in alt.casefold()
            and "slide" not in alt.casefold()
        ):
            continue
        url = _extract_image_url(image)
        if not url or url in seen:
            continue
        seen.add(url)
        images.append(url)
    return images


def _price_from_text(text: str, label: str) -> str | None:
    pattern = re.compile(
        rf"\$([0-9][0-9,]*(?:\.[0-9]{{2}})?)\s*{re.escape(label)}", re.IGNORECASE
    )
    match = pattern.search(text)
    if match:
        return match.group(1).replace(",", "")
    return None


def _first_money_from_selector(
    soup: BeautifulSoup, selectors: Sequence[str]
) -> str | None:
    for selector in selectors:
        element = soup.select_one(selector)
        if element is None:
            continue
        text = _clean_text(element.get_text(" ", strip=True))
        if not text:
            continue
        match = _MONEY.search(text)
        if match:
            return match.group(1).replace(",", "")
    return None


def _extract_price(soup: BeautifulSoup, body_text: str) -> str | None:
    return _price_from_text(body_text, "Chewy Price") or _first_money_from_selector(
        soup,
        (
            "[data-testid*='chewy-price' i]",
            "[data-testid*='price' i]",
            ".product-pricing",
        ),
    )


def _extract_list_price(soup: BeautifulSoup, body_text: str) -> str | None:
    return _price_from_text(body_text, "List Price") or _first_money_from_selector(
        soup,
        (
            "[data-testid*='list-price' i]",
            ".list-price",
        ),
    )


def _extract_availability(soup: BeautifulSoup, body_text: str) -> str | None:
    for selector in (
        "[data-testid*='availability' i]",
        "[data-testid*='stock' i]",
        ".availability",
    ):
        element = soup.select_one(selector)
        text = (
            _clean_text(element.get_text(" ", strip=True))
            if element is not None
            else None
        )
        if text:
            return _availability_label(text)
    if re.search(r"\bIn Stock\b", body_text, re.IGNORECASE):
        return "InStock"
    if re.search(r"\bOut of Stock\b", body_text, re.IGNORECASE):
        return "OutOfStock"
    return None


def _availability_label(value: str) -> str | None:
    normalized = value.casefold()
    if "in stock" in normalized:
        return "InStock"
    if "out of stock" in normalized or "unavailable" in normalized:
        return "OutOfStock"
    return _clean_text(value)


def _extract_selected_option(soup: BeautifulSoup, group_label: str) -> str | None:
    label_key = group_label.casefold()
    for container in soup.select(
        "[data-testid*='variation' i], fieldset, section, div"
    ):
        text = _clean_text(container.get_text(" ", strip=True)) or ""
        if label_key not in text.casefold():
            continue
        for selector in (
            "[aria-pressed='true']",
            "[aria-checked='true']",
            "[data-selected='true']",
            ".selected",
        ):
            selected = container.select_one(selector)
            if selected is None:
                continue
            value = _clean_text(selected.get("aria-label")) or _clean_text(
                selected.get_text(" ", strip=True)
            )
            if value:
                value = re.sub(
                    rf"^{re.escape(group_label)}:\s*", "", value, flags=re.IGNORECASE
                )
                return value
    return None


def _size_from_title(title: str | None) -> str | None:
    if not title:
        return None
    match = _SIZE_IN_TITLE.search(title)
    if not match:
        return None
    return _clean_text(match.group(1))


def _deduped_text_lines(container: object) -> list[str]:
    if container is None or not hasattr(container, "select"):
        return []
    lines: list[str] = []
    seen: set[str] = set()
    for item in container.select("li, p"):
        text = _clean_text(item.get_text(" ", strip=True))
        key = str(text or "").casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        lines.append(text)
    return lines


def _normalize_detail_value(lines: list[str]) -> str | list[str] | None:
    if not lines:
        return None
    if len(lines) == 1:
        return lines[0]
    return lines


def _section_by_id(soup: BeautifulSoup, section_id: str) -> object | None:
    return soup.select_one(f"section#{section_id}")


def _accordion_content_by_title(soup: BeautifulSoup, title: str) -> object | None:
    title_key = str(title or "").strip().casefold()
    if not title_key:
        return None
    for heading in soup.select("h2, h3, h4, div"):
        text = _clean_text(heading.get_text(" ", strip=True))
        if str(text or "").casefold() != title_key:
            continue
        accordion = heading.find_parent(class_=re.compile(r"\bkib-accordion-new-item\b"))
        if accordion is None:
            continue
        content = accordion.select_one(".kib-accordion-new-item__content")
        if content is not None:
            return content
    return None


def _legacy_section_lines(
    soup: BeautifulSoup, heading_pattern: re.Pattern[str]
) -> list[str]:
    heading = soup.find(string=heading_pattern)
    if heading is None:
        return []
    container = heading.find_parent(["section", "div", "article"])
    if container is None:
        return []
    return _deduped_text_lines(container)


def _extract_details(soup: BeautifulSoup) -> dict[str, object]:
    details: dict[str, object] = {}
    details_content = _accordion_content_by_title(soup, "Details")
    lines = _deduped_text_lines(details_content)
    if not lines:
        lines = _legacy_section_lines(soup, re.compile(r"^Details$", re.IGNORECASE))
    value = _normalize_detail_value(lines)
    if value is not None:
        details["details"] = value

    ingredients_section = _section_by_id(soup, "INGREDIENTS-section")
    lines = _deduped_text_lines(ingredients_section)
    if not lines:
        lines = _legacy_section_lines(soup, re.compile(r"^Ingredients$", re.IGNORECASE))
    value = _normalize_detail_value(lines)
    if value is not None:
        details["ingredients"] = value

    feeding_section = _section_by_id(soup, "FEEDING_INSTRUCTIONS-section")
    lines = _deduped_text_lines(feeding_section)
    if not lines:
        lines = _legacy_section_lines(
            soup, re.compile(r"^Feeding Instructions$", re.IGNORECASE)
        )
    value = _normalize_detail_value(lines)
    if value is not None:
        details["feeding_instructions"] = value

    transition_section = _section_by_id(soup, "TRANSITION_INSTRUCTIONS-section")
    transition_lines = _deduped_text_lines(transition_section)
    value = _normalize_detail_value(transition_lines)
    if value is not None:
        details["transition_instructions"] = value
    return details


def _extract_rating(body_text: str) -> float | None:
    match = re.search(r"Rated\s+([0-9.]+)\s+out of 5 stars", body_text, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_review_count(body_text: str) -> int | None:
    match = re.search(
        r"([0-9][0-9,]*)\s+(?:Ratings|Reviews)\b", body_text, re.IGNORECASE
    )
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


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


def _json_script_payloads(soup: BeautifulSoup) -> list[object]:
    payloads: list[object] = []
    selectors = (
        "script#__NEXT_DATA__",
        "script[type='application/json'][data-state]",
        "script[type='application/json'][data-apollo-state]",
        "script[id*='apollo'][type='application/json']",
        "script[id*='state'][type='application/json']",
    )
    for script in soup.select(", ".join(selectors)):
        text = script.string or script.get_text()
        if not text:
            continue
        try:
            payloads.append(json.loads(text))
        except JSONDecodeError:
            continue
    return payloads


def _nested_mapping(
    payload: object, path: Sequence[str]
) -> Mapping[str, object] | None:
    current = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current if isinstance(current, Mapping) else None


def _review_photo_count(value: object) -> int | None:
    if not isinstance(value, Mapping):
        return None
    results = value.get("results")
    if isinstance(results, Sequence) and not isinstance(results, (str, bytes)):
        return len(results)
    return None


def _clean_review(entry: Mapping[str, object]) -> dict[str, object] | None:
    review_record: dict[str, object] = {}
    review_id = _clean_text(entry.get("id")) or _clean_text(entry.get("contentId"))
    if review_id:
        review_record["review_id"] = review_id
    headline = _clean_text(entry.get("title"))
    if headline:
        review_record["headline"] = headline
    comment = _clean_text(entry.get("reviewText"))
    if comment:
        review_record["comment"] = comment
    created = _clean_text(entry.get("submittedAt"))
    if created:
        review_record["created_date"] = created
    author = _clean_text(entry.get("submittedBy"))
    if author:
        review_record["author"] = author
    rating = _parse_review_rating(entry.get("rating"))
    if rating is not None:
        review_record["rating"] = rating
    helpfulness = entry.get("helpfulness")
    if isinstance(helpfulness, int):
        review_record["helpfulness"] = helpfulness
    is_verified = entry.get("isVerified")
    if isinstance(is_verified, bool):
        review_record["is_verified"] = is_verified
    is_incentivized = entry.get("isIncentivized")
    if isinstance(is_incentivized, bool):
        review_record["is_incentivized"] = is_incentivized
    photo_count = _review_photo_count(entry.get("paginatedPhotos"))
    if photo_count is not None:
        review_record["photo_count"] = photo_count
    return (
        review_record
        if review_record.get("comment") or review_record.get("headline")
        else None
    )


def _extract_reviews_from_payload(payload: object) -> list[dict[str, object]]:
    state = _nested_mapping(
        payload,
        ("props", "pageProps", "__APOLLO_CHEWY_API_STATE__"),
    )
    if state is None:
        return []

    reviews: list[dict[str, object]] = []
    seen: set[str] = set()
    for key, value in state.items():
        if not str(key).startswith("Review:") or not isinstance(value, Mapping):
            continue
        review = _clean_review(value)
        if not review:
            continue
        identity = str(review.get("review_id") or review.get("comment") or review)
        if identity in seen:
            continue
        seen.add(identity)
        reviews.append(review)
        if len(reviews) >= _MAX_REVIEWS:
            break
    return reviews


def _extract_reviews(soup: BeautifulSoup) -> list[dict[str, object]]:
    for payload in _json_script_payloads(soup):
        reviews = _extract_reviews_from_payload(payload)
        if reviews:
            return reviews
    return []


class ChewyAdapter(RetailerAdapter):
    """Parse Chewy PDPs from browser-rendered DOM state."""

    retailer = "chewy"

    def __init__(self) -> None:
        self._gallery_images: list[str] = []
        self._details: dict[str, object] = {}
        self._rating: float | None = None
        self._review_count: int | None = None
        self._reviews: list[dict[str, object]] = []

    def primary_id_from_url(self, url: str) -> str | None:
        match = _PARENT_FROM_URL.search(url)
        if not match:
            return None
        return _clean_text(match.group(1))

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        self._gallery_images = []
        self._details = {}
        self._rating = None
        self._review_count = None
        self._reviews = []

        soup = BeautifulSoup(html, "lxml")
        body_text = _clean_text(soup.get_text(" ", strip=True)) or ""
        title = _extract_title(soup)
        brand = _extract_brand(soup)
        category_path = _extract_category_path(soup)
        self._gallery_images = _extract_gallery_images(soup, title)
        self._details = _extract_details(soup)
        self._rating = _extract_rating(body_text)
        self._review_count = _extract_review_count(body_text)
        self._reviews = _extract_reviews(soup)

        price = _extract_price(soup, body_text)
        list_price = _extract_list_price(soup, body_text)
        availability = _extract_availability(soup, body_text)
        size_text = _extract_selected_option(soup, "Size") or _size_from_title(title)
        flavor = _extract_selected_option(soup, "Flavor")
        hero_image = self._gallery_images[0] if self._gallery_images else None

        payload: dict[str, object] = {}
        if brand:
            payload["brand"] = brand
        if title:
            payload["name"] = title
            payload["title"] = title
        if category_path:
            payload["categoryPath"] = category_path
        if self._details:
            detail_summary = self._details.get("details")
            if isinstance(detail_summary, list):
                payload["description"] = " ".join(str(item) for item in detail_summary)
            elif isinstance(detail_summary, str):
                payload["description"] = detail_summary

        variant_payload: dict[str, object] = {}
        if price:
            variant_payload["price"] = price
            variant_payload["currency"] = "USD"
        if list_price:
            variant_payload["listPrice"] = list_price
        if size_text:
            variant_payload["size"] = size_text
        if flavor:
            variant_payload["flavor"] = flavor
        if availability:
            variant_payload["availability"] = availability
        if hero_image:
            variant_payload["image"] = hero_image
            variant_payload["swatchImage"] = hero_image
        if variant_payload:
            variant_payload["id"] = "selected"
            variant_payload["sku"] = "selected"
            payload["variants"] = [variant_payload]

        if not payload:
            return ()
        return (
            EvidenceBlob(
                source="chewy_dom_state",
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
        if parent is not None:
            if self._gallery_images:
                parent.extras["gallery_images"] = list(self._gallery_images)
                parent.extras["hero_image_url"] = self._gallery_images[0]
            if self._details:
                parent.extras["details"] = dict(self._details)
            if self._rating is not None:
                parent.extras["rating"] = self._rating
            if self._review_count is not None:
                parent.extras["review_count"] = self._review_count
            if self._reviews:
                parent.extras["reviews"] = list(self._reviews)
                parent.extras["reviews_meta"] = {
                    "provider": "chewy_apollo",
                    "source": "embedded_app_state",
                    "limit": _MAX_REVIEWS,
                }

            for variant in variants:
                if variant.variant_id == "selected":
                    variant.variant_id = parent.parent_product_id

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
