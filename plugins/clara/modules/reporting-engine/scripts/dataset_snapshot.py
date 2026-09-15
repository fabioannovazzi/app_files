"""Apply explicit tabular parser settings once before component execution."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from profile_dataset import get_row_count, load_dataset_frame

__all__ = ["prepare_dataset_input"]


def prepare_dataset_input(
    source: Path, directory: Path, settings: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    """Normalize a selected sheet/dialect; never reinterpret dataset meaning."""
    if set(settings) - {"sheet_name", "csv_options"}:
        raise ValueError("Unknown dataset parser settings")
    frame, metadata = load_dataset_frame(
        source,
        sheet_name=settings.get("sheet_name"),
        csv_options=settings.get("csv_options"),
    )
    target = directory / "parsed-input.csv"
    # CSV has one table, a fixed UTF-8 dialect and explicit headers, so downstream
    # adapters cannot choose a different Excel sheet or regional separator.
    frame.write_csv(target)
    return target, {
        "status": "normalized_with_explicit_parser_settings",
        "parser_settings": settings,
        "source_parser": metadata,
        "normalized_format": "utf8_comma_csv",
        "normalized_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "row_count": get_row_count(frame),
        "column_count": frame.width,
        "boundary": "Parsing and exact input bytes only; no semantic review is implied.",
    }
