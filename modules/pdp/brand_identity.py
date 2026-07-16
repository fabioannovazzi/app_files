from __future__ import annotations

import re
from typing import Any

__all__ = [
    "brand_has_product_evidence",
    "infer_brand_from_product_context",
    "product_slug_from_url",
    "product_context_summary",
    "should_replace_brand",
    "slugify_text",
]

_PRODUCT_SLUG_FROM_URL = re.compile(
    r"/product/(?P<slug>[^/?#]+?)-[0-9]{8,}\.html",
    re.IGNORECASE,
)


def _clean_text(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def slugify_text(value: object | None) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")


def product_slug_from_url(url: object | None) -> str:
    text = _clean_text(url)
    if not text:
        return ""
    match = _PRODUCT_SLUG_FROM_URL.search(text)
    if not match:
        return ""
    return slugify_text(match.group("slug"))


def _display_brand_from_slug(
    slug: str,
    *reference_texts: object | None,
) -> str | None:
    clean_slug = slugify_text(slug)
    if not clean_slug:
        return None
    display = " ".join(part.capitalize() for part in clean_slug.split("-") if part)
    if not display:
        return None
    pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(display)}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    for reference in reference_texts:
        text = _clean_text(reference)
        if not text:
            continue
        match = pattern.search(text)
        if match:
            return text[match.start() : match.end()]
    return display


def brand_has_product_evidence(
    brand: object | None,
    *,
    product_url: object | None,
    title: object | None,
    summary: object | None,
) -> bool:
    brand_text = _clean_text(brand)
    if not brand_text:
        return False
    brand_slug = slugify_text(brand_text)
    product_slug = product_slug_from_url(product_url)
    if product_slug and brand_slug and product_slug.startswith(f"{brand_slug}-"):
        return True
    pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(brand_text)}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    return any(
        pattern.search(text) is not None
        for text in (_clean_text(title), _clean_text(summary))
        if text
    )


def infer_brand_from_product_context(
    *,
    product_url: object | None,
    title: object | None,
    summary: object | None,
) -> str | None:
    product_slug = product_slug_from_url(product_url)
    title_slug = slugify_text(title)
    if product_slug and title_slug and product_slug.endswith(title_slug):
        prefix = product_slug[: -len(title_slug)].strip("-")
        inferred = _display_brand_from_slug(prefix, title, summary)
        if inferred:
            return inferred

    title_text = _clean_text(title)
    summary_text = _clean_text(summary)
    if title_text and summary_text:
        title_index = summary_text.casefold().find(title_text.casefold())
        if title_index > 0:
            prefix = summary_text[:title_index].strip(" -:|")
            if 0 < len(prefix) <= 80:
                return prefix
    return None


def should_replace_brand(
    current_brand: object | None,
    candidate_brand: object | None,
    *,
    product_url: object | None,
    title: object | None,
    summary: object | None,
) -> bool:
    current = _clean_text(current_brand)
    candidate = _clean_text(candidate_brand)
    if not candidate:
        return False
    if not current:
        return True
    if current.casefold() == candidate.casefold():
        return False
    return brand_has_product_evidence(
        candidate,
        product_url=product_url,
        title=title,
        summary=summary,
    ) and not brand_has_product_evidence(
        current,
        product_url=product_url,
        title=title,
        summary=summary,
    )


def product_context_summary(extras: dict[str, Any]) -> str | None:
    raw = extras.get("summary")
    return _clean_text(raw)
