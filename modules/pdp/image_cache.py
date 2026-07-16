from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

__all__ = [
    "DEFAULT_IMAGE_ROOT",
    "CachedImage",
    "build_image_cache",
    "find_local_image",
]


DEFAULT_IMAGE_ROOT = Path("data/pdp/cli")

_IMAGE_STEM_RE = re.compile(
    r"""
    ^
    (?P<parent>[A-Za-z0-9_-]+?)
    (?:[-_]
        (?P<variant>[A-Za-z0-9_-]+?)
    )?
    [-_]
    (?P<type>hero|Hero|HERO|swatch|Swatch|SWATCH)
    (?:[-_][0-9]+)?
    $
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class CachedImage:
    path: Path
    image_type: str
    variant_key: Optional[str]


def _normalize_image_identifier(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalised = unicodedata.normalize("NFKD", text)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", ascii_only).strip("-")
    return cleaned.lower() or None


def _parse_cached_image(path: Path) -> tuple[str, str | None, str] | None:
    match = _IMAGE_STEM_RE.match(path.stem)
    if not match:
        return None
    parent = match.group("parent")
    image_type = match.group("type")
    if not parent or not image_type:
        return None
    normalized_type = image_type.lower()
    if normalized_type.endswith("-"):
        normalized_type = normalized_type.rstrip("-")
    if normalized_type not in {"hero", "swatch"}:
        normalized_type = normalized_type.split("-")[0]
    if normalized_type not in {"hero", "swatch"}:
        return None
    variant = match.group("variant")
    parent_key = parent.lower()
    variant_key = variant.lower() if variant else None
    return parent_key, variant_key, normalized_type


def _pick_image(images: list[CachedImage], variant_key: str | None) -> Path | None:
    if not images:
        return None
    if variant_key:
        variant_matches = [item for item in images if item.variant_key == variant_key]
        for candidate in variant_matches:
            if candidate.image_type == "hero":
                return candidate.path
        if variant_matches:
            return variant_matches[0].path
    for candidate in images:
        if candidate.image_type == "hero":
            return candidate.path
    return images[0].path


def build_image_cache(root: Path | None = None) -> Dict[str, List[CachedImage]]:
    base_root = root or DEFAULT_IMAGE_ROOT
    mapping: Dict[str, List[CachedImage]] = {}

    if not base_root.exists():
        return mapping

    candidate_dirs: list[Path] = []
    try:
        first_level = list(base_root.iterdir())
    except FileNotFoundError:
        first_level = []

    for entry in first_level:
        if not entry.is_dir():
            continue
        if entry.name.lower().startswith("images"):
            candidate_dirs.append(entry)
            continue
        try:
            second_level = list(entry.iterdir())
        except FileNotFoundError:
            continue
        for child in second_level:
            if child.is_dir() and child.name.lower().startswith("images"):
                candidate_dirs.append(child)

    for images_dir in candidate_dirs:
        try:
            image_iter = list(images_dir.iterdir())
        except FileNotFoundError:
            continue
        for image_path in image_iter:
            if not image_path.is_file():
                continue
            parsed = _parse_cached_image(image_path)
            if not parsed:
                continue
            parent_key, variant_key, image_type = parsed
            bucket = mapping.setdefault(parent_key, [])
            bucket.append(
                CachedImage(
                    path=image_path,
                    image_type=image_type,
                    variant_key=variant_key,
                )
            )

    for images in mapping.values():
        images.sort(key=lambda item: item.path.name)

    return mapping


def find_local_image(
    cache: Mapping[str, list[CachedImage]],
    parent_id: str | None,
    variant_id: str | None = None,
) -> Path | None:
    if not parent_id:
        return None
    parent_key = _normalize_image_identifier(parent_id)
    if not parent_key:
        return None
    entries = cache.get(parent_key)
    if not entries:
        return None
    variant_key = _normalize_image_identifier(variant_id)
    return _pick_image(entries, variant_key)
