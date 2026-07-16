from __future__ import annotations

from pathlib import Path
from typing import Sequence

import polars as pl

METADATA_PATH = Path("data/pdp/images/metadata.parquet")

__all__ = ["load_image_metadata", "query_image_metadata"]


def load_image_metadata(path: Path | None = None) -> pl.DataFrame:
    """Load the persisted variant image metadata."""

    metadata_path = path or METADATA_PATH
    if not metadata_path.exists():
        return pl.DataFrame(
            schema={
                "retailer": pl.String,
                "parent_product_id": pl.String,
                "variant_id": pl.String,
                "image_type": pl.String,
                "image_url": pl.String,
                "file_name": pl.String,
                "sha256": pl.String,
                "content_length": pl.Int64,
                "shade_name_raw": pl.String,
                "shade_name_normalized": pl.String,
                "shade_finish": pl.String,
                "size_text_raw": pl.String,
                "downloaded_at": pl.String,
                "stored_at": pl.String,
                "archive_path": pl.String,
                "archive_member": pl.String,
                "profile": pl.String,
            }
        )
    return pl.read_parquet(metadata_path)


def query_image_metadata(
    df: pl.DataFrame | None = None,
    *,
    metadata_path: Path | None = None,
    retailer: str | Sequence[str] | None = None,
    parent_ids: Sequence[str] | None = None,
    variant_ids: Sequence[str] | None = None,
    shade_finish: str | Sequence[str] | None = None,
    image_type: str | Sequence[str] | None = None,
) -> pl.DataFrame:
    """Return a filtered view of the image metadata with download hints."""

    if df is None:
        df = load_image_metadata(metadata_path)
    if df.is_empty():
        return df

    filters: list[pl.Expr] = []
    if retailer:
        filters.append(pl.col("retailer").is_in(_ensure_sequence(retailer)))
    if parent_ids:
        filters.append(pl.col("parent_product_id").is_in(list(parent_ids)))
    if variant_ids:
        filters.append(pl.col("variant_id").is_in(list(variant_ids)))
    if shade_finish:
        filters.append(pl.col("shade_finish").is_in(_ensure_sequence(shade_finish)))
    if image_type:
        filters.append(pl.col("image_type").is_in(_ensure_sequence(image_type)))

    filtered = df if not filters else df.filter(pl.all_horizontal(filters))
    root = (metadata_path or METADATA_PATH).resolve().parent

    return filtered.with_columns(
        pl.col("archive_path")
        .map_elements(lambda rel: str((root / rel).resolve()) if rel else "")
        .alias("archive_file_path"),
        pl.struct(["archive_path", "archive_member"])
        .map_elements(
            lambda row: (
                f"zip://{(root / row['archive_path']).resolve()}#{row['archive_member']}"
                if row["archive_path"] and row["archive_member"]
                else ""
            )
        )
        .alias("download_hint"),
    )


def _ensure_sequence(value: str | Sequence[str]) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]
