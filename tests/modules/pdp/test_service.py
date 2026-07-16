from __future__ import annotations

from pathlib import Path

from decimal import Decimal

import polars as pl

from modules.pdp.models import (
    ParentProduct,
    Variant,
)
from modules.pdp.service import (
    PARENT_SCHEMA,
    VARIANT_SCHEMA,
    flatten_for_export,
    load_parent_status,
    parents_to_frame,
    variants_to_frame,
)
from modules.utilities.utils import get_row_count


def test_parents_to_frame_returns_expected_schema() -> None:
    parent = ParentProduct(
        retailer="ulta",
        parent_product_id="pimprod123",
        pdp_url="https://example.com/pimprod123",
        brand_raw="Brand",
        brand_normalized="Brand",
        title_raw="Sample Lipstick",
        title_normalized="Sample Lipstick",
        series_label_raw=None,
        category_path=("Makeup", "Lips"),
        has_color_selector=True,
    )

    frame = parents_to_frame([parent])
    assert frame.schema == PARENT_SCHEMA
    assert get_row_count(frame) == 1


def test_variants_to_frame_handles_empty_list() -> None:
    frame = variants_to_frame([])
    assert frame.schema == VARIANT_SCHEMA
    assert get_row_count(frame) == 0


def test_variants_to_frame_populates_rows() -> None:
    variant = Variant(
        retailer="ulta",
        parent_product_id="pimprod123",
        variant_id="sku101",
        shade_name_raw="Shade",
        shade_name_normalized="Shade",
        size_text_raw="Full Size",
        price_raw="19.00",
        price=Decimal("19.00"),
        currency="USD",
        barcode=None,
        swatch_image_url=None,
        hero_image_url=None,
        availability="InStock",
    )

    frame = variants_to_frame([variant])
    assert get_row_count(frame) == 1


def test_flatten_for_export_turns_lists_into_strings() -> None:
    parent = ParentProduct(
        retailer="ulta",
        parent_product_id="pimprod123",
        pdp_url="https://example.com/pimprod123",
        brand_raw="Brand",
        brand_normalized="Brand",
        title_raw="Sample Lipstick",
        title_normalized="Sample Lipstick",
        series_label_raw=None,
        category_path=("Makeup", "Lips"),
        has_color_selector=True,
        qa_flags=("flag1", "flag2"),
    )

    parent_df = parents_to_frame([parent])
    export_df = flatten_for_export(parent_df)
    assert (
        export_df.schema["category_path"] == export_df.schema["qa_flags"] == pl.String
    )
    assert export_df.select("category_path").item() == "Makeup | Lips"


