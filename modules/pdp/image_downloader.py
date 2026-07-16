"""Utilities to download and package PDP variant images."""

from __future__ import annotations

import hashlib
import io
import mimetypes
import re
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence, Tuple
from urllib.parse import urlparse

import requests

from .fetcher import DEFAULT_HEADERS as DEFAULT_REQUEST_HEADERS
from .models import Variant


__all__ = [
    "ArchivedImage",
    "DownloadedImage",
    "ImageDownloadError",
    "archive_variant_images",
    "download_variant_images",
]


VariantLike = Variant | Mapping[str, object]
MAX_NORMALIZED_IDENTIFIER_LENGTH = 96
IDENTIFIER_HASH_LENGTH = 12

# Default headers emulate a common browser to reduce the chances of 403 responses
# when fetching assets directly from CDNs.
DEFAULT_IMAGE_HEADERS: Mapping[str, str] = {
    **DEFAULT_REQUEST_HEADERS,
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


@dataclass(slots=True)
class DownloadedImage:
    """Metadata for a downloaded product image."""

    parent_product_id: str | None
    variant_id: str | None
    image_type: str
    url: str
    path: Path


@dataclass(slots=True)
class ImageDownloadError:
    """Capture failures encountered while downloading images."""

    parent_product_id: str | None
    variant_id: str | None
    attempted_urls: tuple[str, ...]
    reason: str


@dataclass(slots=True)
class ArchivedImage:
    """Metadata for images included in an archive."""

    parent_product_id: str | None
    variant_id: str | None
    image_type: str
    url: str
    file_name: str


def _normalise_identifier(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    normalised = unicodedata.normalize("NFKD", text)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", ascii_only).strip("-")
    if len(cleaned) > MAX_NORMALIZED_IDENTIFIER_LENGTH:
        digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[
            :IDENTIFIER_HASH_LENGTH
        ]
        prefix_length = max(
            1,
            MAX_NORMALIZED_IDENTIFIER_LENGTH - IDENTIFIER_HASH_LENGTH - 1,
        )
        prefix = cleaned[:prefix_length].rstrip("-")
        cleaned = f"{prefix}-{digest}"
    return cleaned or None


def _extract_variant_fields(item: VariantLike) -> tuple[str | None, str | None, str | None, str | None]:
    if isinstance(item, Variant):
        return (
            item.parent_product_id,
            item.variant_id,
            item.hero_image_url,
            item.swatch_image_url,
        )
    parent = item.get("parent_product_id") if isinstance(item, Mapping) else None
    variant = item.get("variant_id") if isinstance(item, Mapping) else None
    hero = item.get("hero_image_url") if isinstance(item, Mapping) else None
    swatch = item.get("swatch_image_url") if isinstance(item, Mapping) else None
    return (
        str(parent) if parent is not None else None,
        str(variant) if variant is not None else None,
        str(hero) if hero is not None else None,
        str(swatch) if swatch is not None else None,
    )


def _guess_extension(url: str, content_type: str | None) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return ".jpg" if suffix == ".jpe" else suffix
    if content_type:
        mime = content_type.split(";", 1)[0].strip()
        guessed = mimetypes.guess_extension(mime)
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed
    return ".jpg"


def _candidate_urls(
    hero_url: str | None,
    swatch_url: str | None,
    *,
    prefer_hero: bool,
    fallback_to_swatch: bool,
) -> Sequence[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    if prefer_hero:
        if hero_url:
            candidates.append(("hero", hero_url))
        if fallback_to_swatch and swatch_url:
            candidates.append(("swatch", swatch_url))
    else:
        if swatch_url:
            candidates.append(("swatch", swatch_url))
        if fallback_to_swatch and hero_url:
            candidates.append(("hero", hero_url))
    return candidates


def _normalise_url(url: str | None) -> str | None:
    if url is None:
        return None
    text = str(url).strip()
    if not text:
        return None
    if "\\u" in text or "\\/" in text:
        try:
            text = text.encode("utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            pass
    text = text.replace("\\/", "/")
    if text.startswith("http:\\\\"):
        text = text.replace("http:\\\\", "http://", 1)
    if text.startswith("https:\\\\"):
        text = text.replace("https:\\\\", "https://", 1)
    if text.startswith("http:/") and not text.startswith("http://"):
        text = text.replace("http:/", "http://", 1)
    if text.startswith("https:/") and not text.startswith("https://"):
        text = text.replace("https:/", "https://", 1)
    text = text.replace("\\", "/")
    if text.startswith("data:"):
        return None
    return text


_IMAGE_NAME_RE = re.compile(
    r"^(?P<parent>[A-Za-z0-9-]+)"
    r"(?:_(?P<variant>[A-Za-z0-9-]+))?"
    r"_(?P<type>[A-Za-z0-9-]+?)"
    r"(?:_(?P<suffix>\d+))?$"
)


def _existing_image_lookup(directory: Path) -> Dict[Tuple[str | None, str | None, str], Path]:
    lookup: Dict[Tuple[str | None, str | None, str], Path] = {}
    if not directory.exists():
        return lookup
    for item in directory.iterdir():
        if not item.is_file():
            continue
        match = _IMAGE_NAME_RE.match(item.stem)
        if not match:
            continue
        image_type = match.group("type")
        if not image_type:
            continue
        normalized_type = image_type.lower()
        if normalized_type.endswith("-"):
            normalized_type = normalized_type.rstrip("-")
        if normalized_type not in {"hero", "swatch"}:
            normalized_type = normalized_type.split("-")[0]
        if normalized_type not in {"hero", "swatch"}:
            continue
        parent = match.group("parent")
        variant = match.group("variant")
        key = (
            parent.lower() if parent else None,
            variant.lower() if variant else None,
            normalized_type,
        )
        if key not in lookup:
            lookup[key] = item
    return lookup


def download_variant_images(
    variants: Iterable[VariantLike],
    output_dir: Path,
    *,
    prefer_hero: bool = True,
    fallback_to_swatch: bool = True,
    headers: Mapping[str, str] | None = None,
    session: requests.Session | None = None,
    timeout: float = 20.0,
    skip_existing: bool = False,
) -> tuple[list[DownloadedImage], list[ImageDownloadError]]:
    """Download variant images and return metadata along with failures."""

    output_dir.mkdir(parents=True, exist_ok=True)
    http = session or requests.Session()
    downloaded: list[DownloadedImage] = []
    errors: list[ImageDownloadError] = []
    used_names: set[str] = set()
    base_headers = dict(DEFAULT_IMAGE_HEADERS)
    if headers:
        base_headers.update(headers)
    existing_lookup: Dict[Tuple[str | None, str | None, str], Path] = {}
    if skip_existing:
        existing_lookup = _existing_image_lookup(output_dir)

    for item in variants:
        parent_id, variant_id, hero_url, swatch_url = _extract_variant_fields(item)
        hero_url = _normalise_url(hero_url)
        swatch_url = _normalise_url(swatch_url)
        attempts: list[str] = []
        last_reason: str | None = None
        parent_slug = _normalise_identifier(parent_id) or "product"
        variant_slug = _normalise_identifier(variant_id)
        parent_key = parent_slug.lower()
        variant_key = variant_slug.lower() if variant_slug else None
        candidates = _candidate_urls(
            hero_url,
            swatch_url,
            prefer_hero=prefer_hero,
            fallback_to_swatch=fallback_to_swatch,
        )

        for image_type, url in candidates:
            if not url:
                continue
            attempts.append(url)
            cache_key = (parent_key, variant_key, image_type)
            if skip_existing:
                existing_path = existing_lookup.get(cache_key)
                if (
                    existing_path is not None
                    and existing_path.exists()
                    and existing_path.stat().st_size > 0
                ):
                    downloaded.append(
                        DownloadedImage(
                            parent_product_id=parent_id,
                            variant_id=variant_id,
                            image_type=image_type,
                            url=url,
                            path=existing_path,
                        )
                    )
                    break
            try:
                request_headers = dict(base_headers)
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc:
                    referer = f"{parsed.scheme}://{parsed.netloc}/"
                    request_headers.setdefault("Referer", referer)
                response = http.get(url, headers=request_headers, timeout=timeout)
                response.raise_for_status()
            except requests.RequestException as exc:  # pragma: no cover - network errors mocked in tests
                last_reason = str(exc)
                continue

            ext = _guess_extension(url, response.headers.get("Content-Type"))
            parts = [parent_slug]
            if variant_slug:
                parts.append(variant_slug)
            parts.append(image_type)
            base_name = "_".join(parts)
            candidate_name = f"{base_name}{ext}"
            counter = 1
            while candidate_name in used_names:
                candidate_name = f"{base_name}_{counter}{ext}"
                counter += 1
            used_names.add(candidate_name)
            file_path = output_dir / candidate_name
            file_path.write_bytes(response.content)

            downloaded.append(
                DownloadedImage(
                    parent_product_id=parent_id,
                    variant_id=variant_id,
                    image_type=image_type,
                    url=url,
                    path=file_path,
                )
            )
            if skip_existing:
                existing_lookup[cache_key] = file_path
            break
        else:
            if attempts:
                reason = last_reason or "Image download failed"
            else:
                reason = "No image URLs available"
            errors.append(
                ImageDownloadError(
                    parent_product_id=parent_id,
                    variant_id=variant_id,
                    attempted_urls=tuple(attempts),
                    reason=reason,
                )
            )

    return downloaded, errors


def archive_variant_images(
    variants: Iterable[VariantLike],
    *,
    prefer_hero: bool = True,
    fallback_to_swatch: bool = True,
    headers: Mapping[str, str] | None = None,
    session: requests.Session | None = None,
    timeout: float = 20.0,
) -> tuple[bytes, list[ArchivedImage], list[ImageDownloadError]]:
    """Download variant images and return a ZIP archive along with metadata."""

    if session is None:
        session = requests.Session()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        downloaded, errors = download_variant_images(
            variants,
            tmp_path,
            prefer_hero=prefer_hero,
            fallback_to_swatch=fallback_to_swatch,
            headers=headers,
            session=session,
            timeout=timeout,
        )
        if not downloaded:
            return b"", [], errors

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in downloaded:
                archive.write(item.path, arcname=item.path.name)
        buffer.seek(0)

        metadata = [
            ArchivedImage(
                parent_product_id=item.parent_product_id,
                variant_id=item.variant_id,
                image_type=item.image_type,
                url=item.url,
                file_name=item.path.name,
            )
            for item in downloaded
        ]

    return buffer.getvalue(), metadata, errors
