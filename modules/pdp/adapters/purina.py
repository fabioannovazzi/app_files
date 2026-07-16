from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence

from bs4 import BeautifulSoup  # type: ignore[import]

from ..models import EvidenceBlob, ParentProduct, Variant
from ..purina_catalog import (
    PURINA_CATEGORY_KEY,
    PURINA_RETAILER,
    purina_brand_from_product,
    purina_category_path,
    purina_image_url,
    purina_parent_id_from_url,
    purina_product_text,
    purina_product_url,
    purina_semantic_attribute_hints,
    purina_variant_payloads,
)
from . import RetailerAdapter

__all__ = ["PurinaAdapter"]

_WHITESPACE_RE = re.compile(r"\s+")


def _clean_text(value: object | None) -> str | None:
    text = _WHITESPACE_RE.sub(" ", str(value or "")).strip()
    return text or None


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _json_payloads_from_html(html: str) -> list[Mapping[str, object]]:
    soup = BeautifulSoup(html, "lxml")
    payloads: list[Mapping[str, object]] = []
    for node in soup.select("script#purina-api-product"):
        raw_text = node.string or node.get_text()
        if not raw_text:
            continue
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, Mapping):
            payloads.append(payload)
    return payloads


def _first_payload(html: str) -> Mapping[str, object] | None:
    payloads = _json_payloads_from_html(html)
    return payloads[0] if payloads else None


class PurinaAdapter(RetailerAdapter):
    """Parse Purina PDPs from official Purina API product rows."""

    retailer = PURINA_RETAILER

    def __init__(self) -> None:
        self._payload: Mapping[str, object] | None = None

    def primary_id_from_url(self, url: str) -> str | None:
        return purina_parent_id_from_url(url)

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        product = _first_payload(html)
        if product is None:
            self._payload = None
            return ()

        parent_id = purina_parent_id_from_url(str(product.get("url") or ""))
        if not parent_id:
            self._payload = None
            return ()

        raw_filters = product.get("site_filters")
        site_filters = (
            [dict(item) for item in raw_filters if isinstance(item, Mapping)]
            if _is_sequence(raw_filters)
            else []
        )
        site_attributes = product.get("site_attributes")
        if not isinstance(site_attributes, Mapping):
            site_attributes = purina_semantic_attribute_hints(
                product,
                site_filters=site_filters,
            )

        brand = purina_brand_from_product(
            {**dict(product), "site_filters": site_filters}
        )
        title = _clean_text(product.get("title")) or parent_id.replace("-", " ").title()
        description = purina_product_text(product)
        hero_image_url = purina_image_url(product.get("product_image"))
        product_url = purina_product_url(parent_id, str(product.get("url") or ""))
        payload: dict[str, object] = {
            "id": parent_id,
            "brand": brand,
            "name": title,
            "description": description,
            "collection": brand,
            "categoryPath": list(
                purina_category_path(product, site_filters=site_filters)
            ),
            "variants": purina_variant_payloads(product),
            "parent": {
                "parent_product_id": parent_id,
                "canonical_url": product_url,
                "category_key": PURINA_CATEGORY_KEY,
                "description_markdown": description,
                "features": _feature_lines(product, site_attributes),
                "hero_image_url": hero_image_url,
                "product_type": product.get("type"),
                "rating": product.get("rating"),
                "review_count": product.get("number_of_reviews"),
                "site_filters": site_filters,
                "site_attributes": site_attributes,
                "summary": description,
            },
        }
        self._payload = payload
        return (
            EvidenceBlob(
                source="purina_api_product",
                selector="script#purina-api-product",
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

        brand = _clean_text(self._payload.get("brand"))
        if brand:
            parent.brand_raw = brand
            parent.brand_normalized = brand

        title = _clean_text(self._payload.get("name"))
        if title:
            parent.title_raw = title
            parent.title_normalized = title

        product_url = _clean_text(raw_parent.get("canonical_url"))
        if product_url:
            parent.pdp_url = product_url

        category_path = self._payload.get("categoryPath")
        if _is_sequence(category_path):
            parent.category_path = tuple(
                text
                for item in category_path
                if (text := _clean_text(item)) is not None
            )

        for key in (
            "category_key",
            "description_markdown",
            "hero_image_url",
            "product_type",
            "summary",
        ):
            value = raw_parent.get(key)
            if (text := _clean_text(value)) is not None:
                parent.extras[key] = text

        for numeric_key, output_key in (
            ("rating", "rating"),
            ("review_count", "review_count"),
        ):
            value = raw_parent.get(numeric_key)
            if value in (None, ""):
                continue
            try:
                numeric = float(str(value))
            except ValueError:
                continue
            parent.extras[output_key] = (
                int(numeric) if output_key == "review_count" else numeric
            )

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

        hero_image_url = _clean_text(raw_parent.get("hero_image_url"))
        for variant in variants:
            if hero_image_url and not variant.hero_image_url:
                variant.hero_image_url = hero_image_url
            variant.extras.setdefault("category_key", PURINA_CATEGORY_KEY)


def _feature_lines(
    product: Mapping[str, object],
    site_attributes: Mapping[str, object],
) -> list[str]:
    lines: list[str] = []
    description = purina_product_text(product)
    if description:
        lines.append(description)
    for key, value in site_attributes.items():
        if _is_sequence(value):
            text = ", ".join(str(item) for item in value if item)
            if text:
                lines.append(f"{key}: {text}")
    return lines
