from __future__ import annotations

"""Audit log for per-attribute notes captured during classification.

Appends minimal, schema-stable rows so the log can be queried or exported
separately from the canonical product attributes cache. Stored under the
shared caches root.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

import polars as pl

from modules.utilities.cache import get_cache_dir, get_cache_path

_REPO_NOTES_PATH = get_cache_path("attribute_notes.parquet")
_FALLBACK_NOTES_PATH = get_cache_dir("mparanza_app") / "attribute_notes.parquet"

__all__ = ["append_notes", "load_notes", "get_notes_log_path"]


def _get_log_path() -> Path:
    try:
        _REPO_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        return _REPO_NOTES_PATH
    except PermissionError:
        _FALLBACK_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        return _FALLBACK_NOTES_PATH


def _ensure_schema(df: pl.DataFrame) -> pl.DataFrame:
    cols = {
        "timestamp": pl.Datetime,
        "product": pl.Utf8,
        "category": pl.Utf8,
        "attribute": pl.Utf8,
        "note": pl.Utf8,
        "raw_value": pl.Utf8,
    }
    for name, dtype in cols.items():
        if name not in df.columns:
            df = df.with_columns(pl.lit(None).cast(dtype).alias(name))
    return df.select(list(cols.keys()))


def get_notes_log_path() -> Path:
    """Return the path to the attribute notes audit parquet file."""

    return _get_log_path()


def append_notes(rows: Iterable[Dict[str, Any]]) -> None:
    """Append one or more attribute note rows to the audit log.

    Each row may contain: product, category, attribute, note, raw_value.
    Missing fields are filled with nulls. A UTC timestamp is added.
    """

    now = datetime.now(timezone.utc)
    prepared = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        note_val = r.get("note")
        # Skip empty/blank notes defensively
        if note_val is None or str(note_val).strip() == "":
            continue
        prepared.append(
            {
                "timestamp": now,
                "product": str(r.get("product", "")),
                "category": (
                    None if r.get("category") in ("", None) else str(r.get("category"))
                ),
                "attribute": str(r.get("attribute", "")),
                "note": str(note_val),
                "raw_value": (
                    None if r.get("raw_value") in ("", None) else str(r.get("raw_value"))
                ),
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


def load_notes() -> pl.DataFrame:
    """Return the attribute notes audit log as a DataFrame (empty if missing)."""

    path = _get_log_path()
    if path.exists():
        try:
            return _ensure_schema(pl.read_parquet(path))
        except Exception:
            pass
    return _ensure_schema(pl.DataFrame())

