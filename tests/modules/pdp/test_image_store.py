from __future__ import annotations

import datetime as dt

import polars as pl

from modules.pdp.image_archiver import VariantImageMetadata
from modules.pdp.image_store import VariantImageStore


def test_variant_image_store_persists_archive(tmp_path) -> None:
    store = VariantImageStore(root=tmp_path)
    metadata = [
        VariantImageMetadata(
            retailer="ulta",
            parent_product_id="parent1",
            variant_id="sku123",
            image_type="hero",
            image_url="https://example.com/hero.jpg",
            file_name="parent1-sku123-hero.jpg",
            sha256="deadbeef",
            content_length=4,
            shade_name_raw="Sunrise",
            shade_name_normalized="sunrise",
            shade_finish="Matte",
            size_text_raw="Full Size",
            downloaded_at=dt.datetime(2024, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc),
        )
    ]

    result = store.persist_archive(b"test-bytes", metadata, profile="ulta_lipstick")

    assert result is not None
    assert result.archive_path.exists()
    assert result.metadata_path.exists()

    frame = pl.read_parquet(result.metadata_path)
    assert frame.height == 1
    row = frame.row(0, named=True)
    assert row["archive_member"] == "parent1-sku123-hero.jpg"
    assert row["profile"] == "ulta_lipstick"
