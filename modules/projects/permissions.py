from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

__all__ = [
    "get_concept_permissions",
    "PresentationDocumentInfo",
    "PresentationListingItem",
    "build_presentation_listing",
    "get_brand_report_permissions",
    "get_launch_report_permissions",
    "get_presentation_permissions",
    "is_presentation_allowed",
]

LOGGER = logging.getLogger(__name__)


def _resolve_config_path(filename: str) -> Path:
    """Resolve config paths relative to the project root when possible."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent / "config" / filename
    return Path("config") / filename


_PRESENTATION_PERMISSIONS_FILE = _resolve_config_path("presentation_permissions.json")
_LAUNCH_REPORT_PERMISSIONS_FILE = _resolve_config_path("launch_report_permissions.json")
_BRAND_REPORT_PERMISSIONS_FILE = _resolve_config_path("brand_report_permissions.json")
_CONCEPT_PERMISSIONS_FILE = _resolve_config_path("concept_permissions.json")


@dataclass(frozen=True, slots=True)
class PresentationDocumentInfo:
    doc_id: str
    title: str


@dataclass(frozen=True, slots=True)
class PresentationListingItem:
    doc_id: str
    title: str
    allowed: bool


def _permissions_cache_key(path: Path) -> tuple[str, int, int]:
    """Return a cache key that changes whenever the permissions file changes."""

    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return (os.fspath(path), 0, 0)
    except OSError:
        return (os.fspath(path), 0, 0)
    return (os.fspath(path), int(stat_result.st_mtime_ns), int(stat_result.st_size))


@lru_cache(maxsize=4)
def _load_presentation_permissions(
    cache_key: tuple[str, int, int],
) -> dict[str, set[str]]:
    return _load_permissions_file(cache_key)


@lru_cache(maxsize=4)
def _load_launch_report_permissions(
    cache_key: tuple[str, int, int],
) -> dict[str, set[str]]:
    return _load_permissions_file(cache_key)


@lru_cache(maxsize=4)
def _load_brand_report_permissions(
    cache_key: tuple[str, int, int],
) -> dict[str, set[str]]:
    return _load_permissions_file(cache_key)


@lru_cache(maxsize=4)
def _load_concept_permissions(
    cache_key: tuple[str, int, int],
) -> dict[str, set[str]]:
    return _load_permissions_file(cache_key)


def _load_permissions_file(
    cache_key: tuple[str, int, int],
) -> dict[str, set[str]]:
    path_str, _mtime_ns, _size = cache_key
    path = Path(path_str)
    if not path.exists():
        LOGGER.warning(
            "Document permissions file not found at %s; allowing all documents.", path
        )
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}") from exc
    if not isinstance(raw, dict):
        LOGGER.warning(
            "Document permissions file at %s is not a JSON object; allowing all documents.",
            path,
        )
        return {}
    permissions: dict[str, set[str]] = {}
    for doc_id, entries in raw.items():
        if not isinstance(doc_id, str):
            continue
        doc_key = doc_id.strip().lower()
        if not doc_key:
            continue
        if not isinstance(entries, list):
            continue
        normalized: set[str] = set()
        for entry in entries:
            if not isinstance(entry, str):
                continue
            email = entry.strip().lower()
            if email:
                normalized.add(email)
        permissions[doc_key] = normalized
    return permissions


def get_presentation_permissions() -> dict[str, set[str]]:
    """Return the cached per-deck permission map."""

    return _load_presentation_permissions(
        _permissions_cache_key(_PRESENTATION_PERMISSIONS_FILE)
    )


def get_launch_report_permissions() -> dict[str, set[str]]:
    """Return the cached per-report permission map."""

    return _load_launch_report_permissions(
        _permissions_cache_key(_LAUNCH_REPORT_PERMISSIONS_FILE)
    )


def get_brand_report_permissions() -> dict[str, set[str]]:
    """Return the cached per-brand-report permission map."""

    return _load_brand_report_permissions(
        _permissions_cache_key(_BRAND_REPORT_PERMISSIONS_FILE)
    )


def get_concept_permissions() -> dict[str, set[str]]:
    """Return the cached per-concept permission map."""

    return _load_concept_permissions(_permissions_cache_key(_CONCEPT_PERMISSIONS_FILE))


def is_presentation_allowed(
    doc_id: str,
    user_email: str | None,
    permissions: dict[str, set[str]],
) -> bool:
    """Return True when the user is allowed to access the requested deck."""

    normalized_doc_id = (doc_id or "").strip().lower()
    if not normalized_doc_id:
        return False
    allowed = permissions.get(normalized_doc_id)
    if allowed is None:
        return True
    if not allowed:
        return False
    normalized_email = (user_email or "").strip().lower()
    if not normalized_email:
        return False
    return normalized_email in allowed


def build_presentation_listing(
    documents: list[PresentationDocumentInfo],
    user_email: str | None,
    permissions: dict[str, set[str]],
) -> list[PresentationListingItem]:
    """Return listing entries with access flags for each document."""

    return [
        PresentationListingItem(
            doc_id=document.doc_id,
            title=document.title,
            allowed=is_presentation_allowed(document.doc_id, user_email, permissions),
        )
        for document in documents
    ]
