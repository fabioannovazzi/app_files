from __future__ import annotations

import io
from zipfile import ZipFile

from modules.pdp.image_archiver import archive_variant_images
from modules.pdp.models import Variant


def test_archive_variant_images_returns_metadata_for_urls() -> None:
    variant = Variant(
        retailer="ulta",
        parent_product_id="parent1",
        variant_id="sku123",
        shade_name_raw="Sunrise",
        shade_name_normalized="sunrise",
        size_text_raw="Full Size",
        price_raw="19.00",
        price=None,
        currency="USD",
        barcode=None,
        swatch_image_url="https://example.com/swatch.png",
        hero_image_url="https://example.com/hero.jpg",
        availability="InStock",
    )

    def fake_fetch(url: str) -> bytes:
        return ("image:" + url).encode("utf-8")

    archive_bytes, metadata = archive_variant_images([variant], fetch_image=fake_fetch)

    assert len(metadata) == 2
    paths = {entry.file_name for entry in metadata}
    assert any(name.endswith("swatch.png") for name in paths)
    assert any(name.endswith("hero.jpg") for name in paths)

    with ZipFile(io.BytesIO(archive_bytes), mode="r") as zf:
        assert set(zf.namelist()) == paths
