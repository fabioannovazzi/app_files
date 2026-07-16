from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import polars as pl

from .image_archiver import VariantImageMetadata

__all__ = ["PersistedImageArchive", "VariantImageStore"]


@dataclass(slots=True)
class PersistedImageArchive:
    """Summary of a persisted image archive."""

    archive_path: Path
    metadata_path: Path
    record_count: int


class VariantImageStore:
    """Persist archived variant images and their metadata to disk."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path("data/pdp/images")
        self.root.mkdir(parents=True, exist_ok=True)
        self._metadata_path = self.root / "metadata.parquet"

    def persist_archive(
        self,
        archive_bytes: bytes,
        metadata: Sequence[VariantImageMetadata],
        *,
        profile: str | None = None,
    ) -> PersistedImageArchive | None:
        """Write the archive bytes to disk and append metadata rows."""

        if not metadata:
            return None

        timestamp = dt.datetime.now(dt.timezone.utc)
        archive_name = self._build_archive_name(profile, timestamp)
        archive_path = self.root / archive_name
        archive_path.write_bytes(archive_bytes)

        frame = self._metadata_frame(metadata, archive_path, timestamp, profile)
        self._append_metadata(frame)

        return PersistedImageArchive(
            archive_path=archive_path,
            metadata_path=self._metadata_path,
            record_count=len(metadata),
        )

    def _metadata_frame(
        self,
        metadata: Sequence[VariantImageMetadata],
        archive_path: Path,
        timestamp: dt.datetime,
        profile: str | None,
    ) -> pl.DataFrame:
        rows: list[dict[str, object]] = []
        archive_rel = archive_path.relative_to(self.root)
        stored_at = timestamp.isoformat()
        for entry in metadata:
            rows.append(
                {
                    "retailer": entry.retailer,
                    "parent_product_id": entry.parent_product_id,
                    "variant_id": entry.variant_id,
                    "image_type": entry.image_type,
                    "image_url": entry.image_url,
                    "file_name": entry.file_name,
                    "sha256": entry.sha256,
                    "content_length": entry.content_length,
                    "shade_name_raw": entry.shade_name_raw,
                    "shade_name_normalized": entry.shade_name_normalized,
                    "shade_finish": entry.shade_finish,
                    "size_text_raw": entry.size_text_raw,
                    "downloaded_at": entry.downloaded_at.isoformat(),
                    "stored_at": stored_at,
                    "archive_path": archive_rel.as_posix(),
                    "archive_member": entry.file_name,
                    "profile": profile,
                }
            )

        schema = {
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
        return pl.from_dicts(rows, schema=schema)

    def _append_metadata(self, frame: pl.DataFrame) -> None:
        if self._metadata_path.exists():
            existing = pl.read_parquet(self._metadata_path)
            combined = pl.concat([existing, frame], how="vertical_relaxed")
        else:
            combined = frame
        combined.write_parquet(self._metadata_path)

    def _build_archive_name(self, profile: str | None, timestamp: dt.datetime) -> str:
        suffix = timestamp.strftime("%Y%m%d-%H%M%S")
        if profile:
            safe_profile = profile.replace(" ", "-").replace("/", "-")
            return f"{safe_profile}-variant-images-{suffix}.zip"
        return f"variant-images-{suffix}.zip"

