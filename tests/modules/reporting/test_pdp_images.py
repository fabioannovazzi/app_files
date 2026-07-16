from __future__ import annotations

import polars as pl

from modules.reporting.pdp_images import load_image_metadata, query_image_metadata


def test_query_image_metadata_filters_and_augments(tmp_path) -> None:
    metadata_dir = tmp_path / "reports" / "pdp" / "images"
    metadata_dir.mkdir(parents=True)
    metadata_path = metadata_dir / "metadata.parquet"

    frame = pl.DataFrame(
        {
            "retailer": ["ulta", "sephora"],
            "parent_product_id": ["parent1", "parent2"],
            "variant_id": ["sku1", "sku2"],
            "image_type": ["hero", "swatch"],
            "image_url": ["https://example.com/hero.jpg", "https://example.com/swatch.jpg"],
            "file_name": ["parent1-sku1-hero.jpg", "parent2-sku2-swatch.jpg"],
            "sha256": ["abc", "def"],
            "content_length": [10, 12],
            "shade_name_raw": ["Sunrise", "Moon"],
            "shade_name_normalized": ["sunrise", "moon"],
            "shade_finish": ["Matte", "Gloss"],
            "size_text_raw": ["Full", "Mini"],
            "downloaded_at": ["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"],
            "stored_at": ["2024-01-01T00:00:01Z", "2024-01-02T00:00:01Z"],
            "archive_path": ["ulta-variant-images.zip", "sephora-variant-images.zip"],
            "archive_member": ["parent1-sku1-hero.jpg", "parent2-sku2-swatch.jpg"],
            "profile": ["ulta_lipstick", "sephora_gloss"],
        }
    )
    frame.write_parquet(metadata_path)

    loaded = load_image_metadata(metadata_path)
    assert loaded.height == 2

    filtered = query_image_metadata(
        metadata_path=metadata_path,
        retailer="ulta",
        shade_finish="Matte",
    )
    assert filtered.height == 1
    row = filtered.row(0, named=True)
    assert row["archive_file_path"].endswith("ulta-variant-images.zip")
    assert row["download_hint"].startswith("zip://")
