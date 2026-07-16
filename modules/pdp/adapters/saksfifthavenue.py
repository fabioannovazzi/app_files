from __future__ import annotations

import json
import re
from collections.abc import Sequence

from bs4 import BeautifulSoup  # type: ignore[import]
from bs4.element import Tag  # type: ignore[import]

from ..brand_identity import brand_has_product_evidence as _brand_has_product_evidence
from ..brand_identity import (
    infer_brand_from_product_context as _infer_brand_from_product_context,
)
from ..brand_identity import product_slug_from_url as _product_slug_from_url
from ..brand_identity import should_replace_brand as _should_replace_brand
from ..brand_identity import slugify_text as _slugify_text
from ..models import EvidenceBlob, ParentProduct, Variant
from . import RetailerAdapter

__all__ = ["SaksfifthavenueAdapter"]


_PARENT_FROM_URL = re.compile(
    r"/product/[^/?#]*?([0-9]{8,})\.html",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{2})?)")
_STYLE_CODE_RE = re.compile(r"\bStyle\s+Code:\s*([A-Za-z0-9-]+)", re.IGNORECASE)
_NON_COLOR_LINES = {
    "color",
    "style",
    "image",
    "size",
    "size guide",
    "select size",
}
_MAX_COLOR_LABEL_LENGTH = 80
_INVALID_COLOR_SNIPPETS = (
    "waitlist",
    "marketing",
    "text alerts",
    "email alerts",
    "terms of use",
    "message and data rates",
    "phone number",
    "opt-outs",
)


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def _clean_lines(value: object) -> list[str]:
    if value is None or not hasattr(value, "get_text"):
        return []
    return [
        line
        for raw in value.get_text("\n", strip=True).splitlines()
        for line in [_clean_text(raw)]
        if line
    ]


def _jsonld_payloads(soup: BeautifulSoup) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for node in soup.select("script[type='application/ld+json']"):
        raw = _clean_text(node.string or node.get_text())
        if not raw:
            continue
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = loaded if isinstance(loaded, list) else [loaded]
        for item in items:
            if isinstance(item, dict):
                payloads.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    payloads.extend(entry for entry in graph if isinstance(entry, dict))
    return payloads


def _nested_text(payload: object, path: Sequence[str]) -> str | None:
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _clean_text(current)


def _jsonld_product(
    soup: BeautifulSoup,
    *,
    parent_id: str | None = None,
    product_url: str | None = None,
) -> dict[str, object]:
    products: list[dict[str, object]] = []
    for payload in _jsonld_payloads(soup):
        raw_type = payload.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if any(str(item).lower() == "product" for item in types):
            products.append(payload)
    if not products:
        return {}
    if len(products) == 1:
        return products[0]

    product_slug = _product_slug_from_url(product_url)
    scored: list[tuple[int, dict[str, object]]] = []
    for payload in products:
        score = 0
        for path in (
            ("sku",),
            ("productID",),
            ("productId",),
            ("id",),
            ("mpn",),
        ):
            value = _nested_text(payload, path)
            if parent_id and value == parent_id:
                score += 10
        for path in (("url",), ("@id",), ("offers", "url")):
            value = _nested_text(payload, path)
            if parent_id and value and parent_id in value:
                score += 8
        name_slug = _slugify_text(payload.get("name"))
        if product_slug and name_slug and product_slug.endswith(name_slug):
            score += 4
        scored.append((score, payload))

    best_score, best_payload = max(scored, key=lambda item: item[0])
    return best_payload if best_score > 0 else {}


def _extract_meta(soup: BeautifulSoup, *selectors: str) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        value = _clean_text(node.get("content"))
        if value:
            return value
    return None


def _extract_title(soup: BeautifulSoup, product_json: dict[str, object]) -> str | None:
    for selector in (
        "h1",
        "[data-testid*='product-name' i]",
        "[class*='product-name' i]",
    ):
        node = soup.select_one(selector)
        if node is None:
            continue
        title = _clean_text(node.get_text(" ", strip=True))
        if title and "saks" not in title.casefold():
            return title
    name = product_json.get("name")
    title = _clean_text(name if isinstance(name, str) else None)
    if title:
        return title
    meta_title = _extract_meta(soup, "meta[property='og:title']", "meta[name='title']")
    if not meta_title:
        return None
    return meta_title.split("|", 1)[0].strip() or meta_title


def _extract_brand(
    soup: BeautifulSoup,
    product_json: dict[str, object],
    *,
    product_url: str | None,
    title: str | None,
    summary: str | None,
) -> str | None:
    meta_brand = _extract_meta(
        soup,
        "meta[property='product:brand']",
        "meta[name='brand']",
        "meta[itemprop='brand']",
    )
    if meta_brand:
        return meta_brand

    raw_brand = product_json.get("brand")
    if isinstance(raw_brand, dict):
        brand = _clean_text(raw_brand.get("name"))
        if brand:
            return brand
    brand = _clean_text(raw_brand if isinstance(raw_brand, str) else None)
    if brand:
        return brand

    inferred_brand = _infer_brand_from_product_context(
        product_url=product_url,
        title=title,
        summary=summary,
    )
    if inferred_brand:
        return inferred_brand

    for selector in (
        "[data-testid*='brand' i] a",
        "[class*='brand' i] a",
        "a[href*='/brand/']",
        "a[href*='/designer/']",
    ):
        node = soup.select_one(selector)
        if node is None:
            continue
        label = _clean_text(node.get_text(" ", strip=True))
        if (
            label
            and label.casefold() not in {"designer", "brand"}
            and _brand_has_product_evidence(
                label,
                product_url=product_url,
                title=title,
                summary=summary,
            )
        ):
            return label
    return None


def _extract_summary(
    soup: BeautifulSoup,
    product_json: dict[str, object],
    details: dict[str, object],
) -> str | None:
    description = _clean_text(product_json.get("description"))
    if description:
        return description
    meta = _extract_meta(
        soup,
        "meta[name='description']",
        "meta[property='og:description']",
    )
    if meta:
        return meta
    raw_details = details.get("description_markdown")
    return _clean_text(raw_details if isinstance(raw_details, str) else None)


def _extract_category_path(soup: BeautifulSoup) -> list[str]:
    selectors = (
        "nav[aria-label*='breadcrumb' i] a",
        "[data-testid*='breadcrumb' i] a",
        ".breadcrumb a",
        "[class*='breadcrumb' i] a",
    )
    categories: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        for node in soup.select(selector):
            label = _clean_text(node.get_text(" ", strip=True))
            key = str(label or "").casefold()
            if not label or key in seen or key in {"home", "saks"}:
                continue
            seen.add(key)
            categories.append(label)
        if categories:
            return categories

    for line in _body_lines(soup):
        key = line.casefold()
        if key in {"shoes", "sneakers", "low-tops", "low tops"} and key not in seen:
            seen.add(key)
            categories.append(line)
    return categories


def _extract_gallery_images(
    soup: BeautifulSoup, product_json: dict[str, object]
) -> list[str]:
    images: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                add(item)
            return
        url = _clean_text(value if isinstance(value, str) else None)
        if not url or url.startswith("data:"):
            return
        if url.startswith("//"):
            url = f"https:{url}"
        if url in seen:
            return
        seen.add(url)
        images.append(url)

    add(product_json.get("image"))
    add(_extract_meta(soup, "meta[property='og:image']", "meta[name='twitter:image']"))
    for image in soup.select("img[src], img[data-src], source[srcset]"):
        if image.name == "source":
            srcset = _clean_text(image.get("srcset"))
            first = srcset.split(",", 1)[0].split(" ", 1)[0] if srcset else None
            add(first)
            continue
        add(image.get("src"))
        add(image.get("data-src"))
    return images


def _body_lines(soup: BeautifulSoup) -> list[str]:
    return [
        line
        for raw in soup.get_text("\n", strip=True).splitlines()
        for line in [_clean_text(raw)]
        if line
    ]


def _section_lines(
    soup: BeautifulSoup,
    heading: str,
    *,
    terminators: Sequence[str],
) -> list[str]:
    lines = _body_lines(soup)
    lower_heading = heading.casefold()
    start = next(
        (index for index, line in enumerate(lines) if line.casefold() == lower_heading),
        None,
    )
    if start is None:
        return []
    end = len(lines)
    terminator_set = {item.casefold() for item in terminators}
    for index in range(start + 1, len(lines)):
        if lines[index].casefold() in terminator_set:
            end = index
            break
    return lines[start + 1 : end]


def _extract_details(soup: BeautifulSoup) -> dict[str, object]:
    details: dict[str, object] = {}
    details_container = _details_container(soup)
    section = (
        _clean_lines(details_container)
        if details_container is not None
        else _section_lines(
            soup,
            "Details",
            terminators=(
                "Shipping & Returns",
                "Size Guide",
                "Shop Similar Styles",
                "Recently Viewed",
            ),
        )
    )
    if not section:
        return details

    description = next(
        (
            line
            for line in section
            if len(line) > 24
            and not line.casefold().startswith("please note")
            and not _STYLE_CODE_RE.search(line)
        ),
        None,
    )
    if description:
        details["description_markdown"] = description

    features: list[str] = []
    for line in section:
        lowered = line.casefold()
        if line == description:
            continue
        if lowered.startswith("please note") or _STYLE_CODE_RE.search(line):
            continue
        if lowered in {"details"}:
            continue
        features.append(line)
    if features:
        details["features"] = features

    fit_notes = [line for line in section if line.casefold().startswith("please note")]
    if fit_notes:
        details["fit_notes"] = fit_notes

    return details


def _details_container(soup: BeautifulSoup) -> Tag | None:
    for selector in (
        "[data-testid*='details' i]",
        "[id*='details' i]",
        "[class*='details' i]",
    ):
        node = soup.select_one(selector)
        if isinstance(node, Tag):
            return node
    return None


def _extract_style_code(soup: BeautifulSoup) -> str | None:
    match = _STYLE_CODE_RE.search(soup.get_text(" ", strip=True))
    return _clean_text(match.group(1)) if match else None


def _extract_price(soup: BeautifulSoup, product_json: dict[str, object]) -> str | None:
    offers = product_json.get("offers")
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, dict):
        price = _clean_text(offers.get("price"))
        if price:
            return price.replace("$", "").replace(",", "")
    meta_price = _extract_meta(
        soup,
        "meta[property='product:price:amount']",
        "meta[itemprop='price']",
    )
    if meta_price:
        return meta_price.replace("$", "").replace(",", "")
    match = _PRICE_RE.search(soup.get_text(" ", strip=True))
    return match.group(1).replace(",", "") if match else None


def _extract_currency(
    soup: BeautifulSoup, product_json: dict[str, object]
) -> str | None:
    offers = product_json.get("offers")
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, dict):
        currency = _clean_text(offers.get("priceCurrency"))
        if currency:
            return currency
    return _extract_meta(soup, "meta[property='product:price:currency']") or "USD"


def _extract_colors(soup: BeautifulSoup) -> list[str]:
    colors: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        raw = _clean_text(value if isinstance(value, str) else None)
        if not raw:
            return
        cleaned = re.sub(r"\s*\(?\d+\)?\s*$", "", raw).strip()
        cleaned = cleaned.replace("Refine by Color:", "").strip()
        key = cleaned.casefold()
        if (
            not cleaned
            or key in _NON_COLOR_LINES
            or key in seen
            or len(cleaned) > _MAX_COLOR_LABEL_LENGTH
            or any(snippet in key for snippet in _INVALID_COLOR_SNIPPETS)
        ):
            return
        seen.add(key)
        colors.append(cleaned.title() if cleaned.isupper() else cleaned)

    for node in soup.select(
        ".color-option, [data-color-name], "
        "[data-testid*='color' i] button, button[aria-label*='color' i], "
        "a[aria-label*='color' i]"
    ):
        add(node.get("data-color-name"))
        add(node.get("aria-label"))
        add(node.get_text(" ", strip=True))

    if colors:
        return colors

    section = _section_lines(soup, "Color", terminators=("Size", "Size Guide"))
    for line in section:
        add(line)
    return colors


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "default"


def _variant_payloads(
    *,
    parent_id: str,
    colors: Sequence[str],
    price: str | None,
    currency: str | None,
    gallery_images: Sequence[str],
) -> list[dict[str, object]]:
    values = list(colors) if colors else [""]
    variants: list[dict[str, object]] = []
    for index, color in enumerate(values):
        suffix = _slug(color) if color else "default"
        image = (
            gallery_images[index]
            if index < len(gallery_images)
            else (gallery_images[0] if gallery_images else None)
        )
        variants.append(
            {
                "id": f"{parent_id}-{suffix}",
                "itemId": f"{parent_id}-{suffix}",
                "shade": color or None,
                "color": color or None,
                "price": price,
                "currency": currency,
                "image": image,
                "availability": None,
                "attributes": {"color": color} if color else None,
            }
        )
    return variants


def _extract_badges(soup: BeautifulSoup) -> list[str]:
    badges: list[str] = []
    seen: set[str] = set()
    for line in _body_lines(soup):
        normalized = line.casefold()
        if normalized in {"best seller", "new", "exclusive", "limited inventory"}:
            if normalized not in seen:
                seen.add(normalized)
                badges.append(line)
    return badges


class SaksfifthavenueAdapter(RetailerAdapter):
    """Parse Saks Fifth Avenue PDPs from rendered DOM and JSON-LD evidence."""

    retailer = "saksfifthavenue"

    def __init__(self) -> None:
        self._gallery_images: list[str] = []
        self._details: dict[str, object] = {}
        self._badges: list[str] = []
        self._style_code: str | None = None
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
        self._badges = []
        self._style_code = None
        self._dom_title = None
        self._dom_brand = None
        self._dom_summary = None
        self._dom_category_path = ()

        soup = BeautifulSoup(html, "lxml")
        product_url = _extract_meta(soup, "meta[property='og:url']")
        style_code = _extract_style_code(soup)
        parent_id = self.primary_id_from_url(product_url or "")
        product_json = _jsonld_product(
            soup,
            parent_id=parent_id,
            product_url=product_url,
        )
        if not parent_id:
            parent_id = _clean_text(product_json.get("sku")) or _clean_text(
                product_json.get("productID")
            )
        if not parent_id:
            parent_id = style_code

        title = _extract_title(soup, product_json)
        details = _extract_details(soup)
        summary = _extract_summary(soup, product_json, details)
        brand = _extract_brand(
            soup,
            product_json,
            product_url=product_url,
            title=title,
            summary=summary,
        )
        category_path = _extract_category_path(soup)
        gallery_images = _extract_gallery_images(soup, product_json)
        price = _extract_price(soup, product_json)
        currency = _extract_currency(soup, product_json)
        colors = _extract_colors(soup)
        variants = _variant_payloads(
            parent_id=parent_id or "saks",
            colors=colors,
            price=price,
            currency=currency,
            gallery_images=gallery_images,
        )

        self._gallery_images = gallery_images
        self._details = details
        self._badges = _extract_badges(soup)
        self._style_code = style_code
        self._dom_title = title
        self._dom_brand = brand
        self._dom_summary = summary
        self._dom_category_path = tuple(category_path)

        payload: dict[str, object] = {}
        if brand:
            payload["brand"] = brand
        if title:
            payload["name"] = title
        if summary:
            payload["description"] = summary
        if category_path:
            payload["categoryPath"] = category_path
        if parent_id:
            payload["id"] = parent_id
            payload["productId"] = parent_id
        if variants:
            payload["variants"] = variants

        if not payload:
            return ()

        return (
            EvidenceBlob(
                source="saksfifthavenue_dom_state",
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
        if parent is None:
            return None

        if self._dom_title and not (parent.title_raw or "").strip():
            parent.title_raw = self._dom_title
            parent.title_normalized = self._dom_title
        summary = self._dom_summary or parent.extras.get("summary")
        if self._dom_brand and _should_replace_brand(
            parent.brand_raw,
            self._dom_brand,
            product_url=parent.pdp_url,
            title=parent.title_raw,
            summary=summary,
        ):
            parent.brand_raw = self._dom_brand
            parent.brand_normalized = self._dom_brand
            if "saks_brand_context_override" not in parent.qa_flags:
                parent.qa_flags = (*parent.qa_flags, "saks_brand_context_override")
        elif self._dom_brand and not (parent.brand_raw or "").strip():
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
        if self._badges:
            parent.extras["badges"] = list(self._badges)
        if self._style_code:
            parent.extras["style_code"] = self._style_code

        hero_image = self._gallery_images[0] if self._gallery_images else None
        if hero_image:
            for variant in variants:
                if not variant.hero_image_url:
                    variant.hero_image_url = hero_image
