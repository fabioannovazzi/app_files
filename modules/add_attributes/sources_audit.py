from __future__ import annotations

"""Audit log for web-search sources used during attribute classification.

Appends rows with minimal, schema-stable fields so the log can be queried
or exported later. Stored under the caches root, .
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

import polars as pl

from modules.utilities.cache import get_cache_dir, get_cache_path

_REPO_SOURCES_PATH = get_cache_path("attribute_search_sources.parquet")
_FALLBACK_SOURCES_PATH = get_cache_dir("mparanza_app") / "attribute_search_sources.parquet"

__all__ = ["append_sources", "load_sources", "get_sources_log_path"]


def _get_log_path() -> Path:
    try:
        _REPO_SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
        return _REPO_SOURCES_PATH
    except PermissionError:
        _FALLBACK_SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
        return _FALLBACK_SOURCES_PATH


def _ensure_schema(df: pl.DataFrame) -> pl.DataFrame:
    cols = {
        "timestamp": pl.Datetime,
        "product": pl.Utf8,
        "category": pl.Utf8,
        "url": pl.Utf8,
        "title": pl.Utf8,
        "snippet": pl.Utf8,
    }
    for name, dtype in cols.items():
        if name not in df.columns:
            df = df.with_columns(pl.lit(None).cast(dtype).alias(name))
    return df.select(list(cols.keys()))


def get_sources_log_path() -> Path:
    """Return the path to the sources audit parquet file."""
    return _get_log_path()


def append_sources(rows: Iterable[Dict[str, Any]]) -> None:
    """Append one or more source rows to the audit log.

    Each row may contain: product, category, url, title, snippet. Missing
    fields are filled with nulls. A UTC timestamp is added automatically.
    """
    now = datetime.now(timezone.utc)
    prepared = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        prepared.append(
            {
                "timestamp": now,
                "product": str(r.get("product", "")),
                "category": (None if r.get("category") in ("", None) else str(r.get("category"))),
                "url": (None if r.get("url") in ("", None) else str(r.get("url"))),
                "title": (None if r.get("title") in ("", None) else str(r.get("title"))),
                "snippet": (None if r.get("snippet") in ("", None) else str(r.get("snippet"))),
            }
        )
    if not prepared:
        return

    path = _get_log_path()
    new_df = _ensure_schema(pl.DataFrame(prepared))
    if path.exists():
        try:
            existing = pl.read_parquet(path)
        except Exception:
            # Overwrite with new content on read failures
            new_df.write_parquet(path)
            return
        existing = _ensure_schema(existing)
        new_df = new_df.select(existing.columns)
        pl.concat([existing, new_df], how="vertical").write_parquet(path)
    else:
        new_df.write_parquet(path)


def load_sources() -> pl.DataFrame:
    """Return the sources audit log as a DataFrame (empty if missing)."""
    path = _get_log_path()
    if path.exists():
        try:
            return _ensure_schema(pl.read_parquet(path))
        except Exception:
            pass
    return _ensure_schema(pl.DataFrame())
