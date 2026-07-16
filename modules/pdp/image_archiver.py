from __future__ import annotations

import datetime as dt
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile

import requests

from .models import Variant

__all__ = [
    "VariantImageMetadata",
    "archive_variant_images",
]


@dataclass(slots=True)
class VariantImageMetadata:
    """Metadata describing a single archived variant image."""

    retailer: str
    parent_product_id: str
    variant_id: str
    image_type: str
    image_url: str
    file_name: str
    sha256: str
    content_length: int
    shade_name_raw: str | None
    shade_name_normalized: str | None
    shade_finish: str | None
    size_text_raw: str | None
    downloaded_at: dt.datetime


FetchImageFn = Callable[[str], bytes]


def _default_fetch_image(url: str) -> bytes:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.content


def _file_name_for(variant: Variant, image_type: str, url: str) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".jpg"
    parent = variant.parent_product_id or "unknown_parent"
    variant_id = variant.variant_id or "unknown_variant"
    safe_parent = parent.replace("/", "-")
    safe_variant = variant_id.replace("/", "-")
    safe_type = image_type.replace("/", "-")
    return f"{safe_parent}-{safe_variant}-{safe_type}{suffix}"


def _extract_finish(variant: Variant) -> str | None:
    value = None
    extras = getattr(variant, "extras", None)
    if isinstance(extras, dict):
        attributes = extras.get("attributes")
        if isinstance(attributes, dict):
            raw = attributes.get("Finish") or attributes.get("finish")
            if isinstance(raw, str):
                value = raw.strip() or None
        finish = extras.get("finish")
        if value is None and isinstance(finish, str):
            stripped = finish.strip()
            if stripped:
                value = stripped
    return value


def archive_variant_images(
    variants: Sequence[Variant | Mapping[str, Any]],
    *,
    fetch_image: FetchImageFn | None = None,
) -> tuple[bytes, list[VariantImageMetadata]]:
    """Download variant hero/swatch images and bundle them into a zip archive.

    Parameters
    ----------
    variants:
        Iterable of parsed variants to source hero/swatch URLs from.
    fetch_image:
        Optional callable used to download an image URL. Defaults to ``requests``.

    Returns
    -------
    tuple[bytes, list[VariantImageMetadata]]
        The in-memory zip archive bytes and metadata describing each image.
    """

    downloader = fetch_image or _default_fetch_image
    timestamp = dt.datetime.now(dt.timezone.utc)

    archive_buffer = io.BytesIO()
    metadata: list[VariantImageMetadata] = []

    with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        for variant in variants:
            variant_obj = _ensure_variant(variant)
            if variant_obj is None:
                continue
            for image_type, url in _iter_variant_images(variant_obj):
                try:
                    content = downloader(url)
                except Exception:
                    continue
                if not content:
                    continue

                file_name = _file_name_for(variant_obj, image_type, url)
                zf.writestr(file_name, content)

                digest = hashlib.sha256(content).hexdigest()
                metadata.append(
                    VariantImageMetadata(
                        retailer=variant_obj.retailer,
                        parent_product_id=variant_obj.parent_product_id,
                        variant_id=variant_obj.variant_id,
                        image_type=image_type,
                        image_url=url,
                        file_name=file_name,
                        sha256=digest,
                        content_length=len(content),
                        shade_name_raw=variant_obj.shade_name_raw,
                        shade_name_normalized=variant_obj.shade_name_normalized,
                        shade_finish=_extract_finish(variant_obj),
                        size_text_raw=variant_obj.size_text_raw,
                        downloaded_at=timestamp,
                    )
                )

    return archive_buffer.getvalue(), metadata


def _iter_variant_images(variant: Variant) -> Iterable[tuple[str, str]]:
    candidates: list[tuple[str, str | None]] = [
        ("hero", getattr(variant, "hero_image_url", None)),
        ("swatch", getattr(variant, "swatch_image_url", None)),
    ]
    for image_type, url in candidates:
        if isinstance(url, str) and url.strip():
            yield image_type, url.strip()


def _ensure_variant(candidate: Variant | Mapping[str, Any]) -> Variant | None:
    if isinstance(candidate, Variant):
        return candidate
    if not isinstance(candidate, Mapping):
        return None

    kwargs: dict[str, Any] = {
        "retailer": candidate.get("retailer"),
        "parent_product_id": candidate.get("parent_product_id"),
        "variant_id": candidate.get("variant_id"),
        "shade_name_raw": candidate.get("shade_name_raw"),
        "shade_name_normalized": candidate.get("shade_name_normalized"),
        "size_text_raw": candidate.get("size_text_raw"),
        "price_raw": candidate.get("price_raw"),
        "price": candidate.get("price"),
        "currency": candidate.get("currency"),
        "barcode": candidate.get("barcode"),
        "swatch_image_url": candidate.get("swatch_image_url"),
        "hero_image_url": candidate.get("hero_image_url"),
        "availability": candidate.get("availability"),
        "source_index": candidate.get("source_index"),
        "qa_flags": tuple(candidate.get("qa_flags", ())),
        "extras": candidate.get("extras", {}),
    }
    try:
        return Variant(**kwargs)  # type: ignore[arg-type]
    except Exception:
        return None

