from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Mapping, Sequence

from bs4 import BeautifulSoup  # type: ignore[import]

from ..models import EvidenceBlob, ParentProduct, Variant
from . import RetailerAdapter

BRAND_NAME = "KIKO Milano"
_URL_RE = re.compile(r"/p[-/](?P<slug>[^/?#]+)")


def _coerce_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _coerce_text_list(values: object | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        cleaned = _coerce_text(values)
        return [cleaned] if cleaned else []
    if not isinstance(values, Sequence):
        return []
    items: list[str] = []
    for value in values:
        cleaned = _coerce_text(value)
        if cleaned:
            items.append(cleaned)
    return items


def _extract_media_url(media: Mapping[str, object] | None, target: str) -> str | None:
    if not isinstance(media, Mapping):
        return None
    # Explicit primary image shortcut
    if target == "primary":
        primary = media.get("primary_image")
        if isinstance(primary, Mapping):
            url = primary.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()
    items = media.get("media")
    if isinstance(items, Sequence):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            name = item.get("name")
            if isinstance(name, str) and name.lower() == target.lower():
                url = item.get("url")
                if isinstance(url, str) and url.strip():
                    return url.strip()
    return None


class KikoAdapter:
    """Adapter for KIKO Milano PDPs."""

    retailer = "kiko"

    def __init__(self) -> None:
        self._page_props: Mapping[str, object] | None = None

    def primary_id_from_url(
        self, url: str
    ) -> str | None:  # noqa: D401 - protocol compatibility
        match = _URL_RE.search(url)
        if not match:
            return None
        slug = match.group("slug").rstrip("/")
        if not slug:
            return None
        parts = slug.split("-")
        for part in reversed(parts):
            if part.isdigit():
                return part
        return slug

    def extra_blobs(self, html: str) -> Sequence[EvidenceBlob]:
        soup = BeautifulSoup(html, "lxml")
        script = soup.find("script", id="__NEXT_DATA__")
        self._page_props = None
        if not script or not script.string:
            return ()
        try:
            payload = json.loads(script.string)
        except json.JSONDecodeError:
            return ()
        page_props = payload.get("props", {}).get("pageProps")
        if not isinstance(page_props, Mapping):
            return ()
        self._page_props = page_props
        return (
            EvidenceBlob(
                source="kiko_next_data",
                selector="script#__NEXT_DATA__",
                index=-1,
                payload=page_props,
            ),
        )

    def retailer_specific_fixes(
        self,
        parent: ParentProduct | None,
        variants: list[Variant],
        profile_name: str | None = None,
    ) -> None:
        if not self._page_props:
            return

        page_props = self._page_props
        root = page_props.get("root") if isinstance(page_props, Mapping) else None
        selected = (
            page_props.get("selected") if isinstance(page_props, Mapping) else None
        )
        children = (
            page_props.get("children") if isinstance(page_props, Mapping) else None
        )
        root_backend_id: str | None = None
        root_custom_ids: list[str] = []

        if isinstance(root, Mapping) and parent:
            parent_id = str(
                root.get("product_id") or parent.parent_product_id or ""
            ).strip()
            if parent_id:
                parent.parent_product_id = parent_id
            root_backend_id = _coerce_text(root.get("backend_id"))
            if root_backend_id:
                parent.extras["backend_id"] = root_backend_id
            root_custom_ids = _coerce_text_list(root.get("custom_ids"))
            if root_custom_ids:
                parent.extras["custom_ids"] = root_custom_ids
            parent.brand_raw = BRAND_NAME
            parent.brand_normalized = BRAND_NAME

            product_name = root.get("product_name")
            if isinstance(product_name, str) and product_name.strip():
                parent.title_raw = product_name.strip()
                parent.title_normalized = product_name.strip()

            primitive_name = root.get("primitive_name")
            if isinstance(primitive_name, str) and primitive_name.strip():
                parent.series_label_raw = primitive_name.strip()

            categories: list[str] = []
            if isinstance(selected, Mapping):
                for key in (
                    "product_class_lev1_desc",
                    "product_class_lev2_desc",
                    "product_class_lev3_desc",
                    "product_class_lev4_desc",
                ):
                    value = selected.get(key)
                    if isinstance(value, str) and value.strip():
                        categories.append(value.strip())
            if categories:
                # Preserve insertion order while removing duplicates
                parent.category_path = tuple(dict.fromkeys(categories))

            for key in ("short_description", "long_description"):
                value = root.get(key)
                if isinstance(value, str) and value.strip():
                    parent.extras.setdefault(key, value)

        parent_id = parent.parent_product_id if parent else ""
        variant_map = {
            variant.variant_id: variant for variant in variants if variant.variant_id
        }
        updated_count = 0
        variant_payloads: Sequence[object] = (
            children if isinstance(children, Sequence) else ()
        )
        if not variant_payloads and isinstance(selected, Mapping):
            variant_payloads = (selected,)

        for index, child in enumerate(variant_payloads):
            if not isinstance(child, Mapping):
                continue
            raw_variant_id = child.get("product_id") or child.get("slug")
            variant_id = str(raw_variant_id or f"{parent_id}-{index}").strip()
            variant = variant_map.get(variant_id)
            if variant is None:
                continue
            color = child.get("color")
            if isinstance(color, str):
                color = color.strip()

            price_value = child.get("display_price")
            price_raw: str | None = None
            price_decimal: Decimal | None = None
            if price_value is not None:
                price_raw = str(price_value)
                try:
                    price_decimal = Decimal(str(price_value))
                except Exception:  # pragma: no cover - defensive
                    price_decimal = None

            currency = child.get("currency_id")
            if isinstance(currency, str):
                currency = currency.strip()

            media = child.get("product_media") if isinstance(child, Mapping) else None
            hero = _extract_media_url(media, "primary") or _extract_media_url(
                media, "application"
            )
            swatch = _extract_media_url(media, "swatch")

            availability: str | None = None
            if isinstance(child.get("has_stock"), bool):
                availability = "in_stock" if child["has_stock"] else "out_of_stock"
            elif isinstance(child.get("is_available"), bool):
                availability = "in_stock" if child["is_available"] else "out_of_stock"
            elif isinstance(child.get("is_sellable"), bool):
                availability = "in_stock" if child["is_sellable"] else "out_of_stock"

            variant.shade_name_raw = color
            if price_value is not None:
                variant.price_raw = price_raw
                variant.price = price_decimal
            if currency:
                variant.currency = currency
            variant.swatch_image_url = swatch or variant.swatch_image_url
            variant.hero_image_url = hero or variant.hero_image_url
            variant.availability = availability or variant.availability
            variant.source_index = index
            variant.retailer = self.retailer
            variant.parent_product_id = (
                parent.parent_product_id if parent else parent_id
            )
            slug = child.get("slug")
            if isinstance(slug, str) and slug.strip():
                variant.extras["slug"] = slug.strip()
            backend_id = _coerce_text(child.get("backend_id"))
            if not backend_id and index < len(root_custom_ids):
                backend_id = root_custom_ids[index]
            if backend_id:
                variant.extras["backend_id"] = backend_id
            if root_backend_id:
                variant.extras["backend_parent_id"] = root_backend_id
            barcodes = _coerce_text_list(child.get("barcodes"))
            if barcodes:
                variant.extras["barcodes"] = barcodes
                if not variant.barcode:
                    variant.barcode = barcodes[0]
            discounts = child.get("discounts")
            if discounts:
                variant.extras["discounts"] = discounts
            updated_count += 1

        if parent:
            parent.has_color_selector = updated_count > 1


__all__ = ["KikoAdapter"]
