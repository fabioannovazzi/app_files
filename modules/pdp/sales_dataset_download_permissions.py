from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from modules.pdp.sales_dataset_paths import (
    get_sales_dataset_name,
)

__all__ = [
    "get_sales_dataset_download_permissions",
    "is_sales_dataset_download_allowed",
    "sales_dataset_download_permissions_configured",
]

LOGGER = logging.getLogger(__name__)


def _resolve_config_path(filename: str) -> Path:
    """Resolve config paths relative to the project root when possible."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent / "config" / filename
    return Path("config") / filename


_SALES_DATASET_DOWNLOAD_PERMISSIONS_FILE = _resolve_config_path(
    "sales_dataset_download_permissions.json"
)


def _sales_dataset_download_permissions_cache_key() -> tuple[str, int, int]:
    """Return a cache key that changes whenever the permissions file changes."""

    path = _SALES_DATASET_DOWNLOAD_PERMISSIONS_FILE
    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return (os.fspath(path), 0, 0)
    except OSError:
        return (os.fspath(path), 0, 0)
    return (os.fspath(path), int(stat_result.st_mtime_ns), int(stat_result.st_size))


@lru_cache(maxsize=4)
def _load_sales_dataset_download_permissions(
    cache_key: tuple[str, int, int],
) -> tuple[dict[str, set[str]], bool]:
    path_str, _mtime_ns, _size = cache_key
    path = Path(path_str)
    if not path.exists():
        LOGGER.warning(
            "Sales dataset download permissions file not found at %s; allowing downloads for authorized datasets.",
            path,
        )
        return {}, False

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}") from exc

    if not isinstance(raw, dict):
        LOGGER.warning(
            "Sales dataset download permissions file at %s is not a JSON object; denying all downloads.",
            path,
        )
        return {}, True

    permissions: dict[str, set[str]] = {}
    for dataset, entries in raw.items():
        if not isinstance(dataset, str):
            continue
        dataset_name = get_sales_dataset_name(dataset)
        if not dataset_name:
            continue
        if not isinstance(entries, list):
            permissions[dataset_name] = set()
            continue
        normalized: set[str] = set()
        for entry in entries:
            if not isinstance(entry, str):
                continue
            email = entry.strip().lower()
            if email:
                normalized.add(email)
        permissions[dataset_name] = normalized

    return permissions, True


def get_sales_dataset_download_permissions() -> dict[str, set[str]]:
    """Return the cached per-dataset download permission map."""

    permissions, _configured = _load_sales_dataset_download_permissions(
        _sales_dataset_download_permissions_cache_key()
    )
    return permissions


def sales_dataset_download_permissions_configured() -> bool:
    """Return True when a dataset download permissions file is configured."""

    _permissions, configured = _load_sales_dataset_download_permissions(
        _sales_dataset_download_permissions_cache_key()
    )
    return configured


def is_sales_dataset_download_allowed(
    dataset: str | None,
    user_email: str | None,
    permissions: dict[str, set[str]] | None = None,
) -> bool:
    """Return True when the user can download for the resolved sales dataset."""

    dataset_name = get_sales_dataset_name(dataset)
    if permissions is None:
        permissions = get_sales_dataset_download_permissions()
    configured = sales_dataset_download_permissions_configured()
    if not configured:
        return True

    allowed = permissions.get(dataset_name)
    if not allowed:
        return False

    normalized_email = (user_email or "").strip().lower()
    if not normalized_email:
        return False
    return normalized_email in allowed
