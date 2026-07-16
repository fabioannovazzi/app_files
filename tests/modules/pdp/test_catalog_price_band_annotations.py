from __future__ import annotations

import polars as pl

from modules.pdp.api import _annotate_records_with_sales_and_price
from modules.pdp.attribute_review_logic import ReviewTables


def test_annotate_records_uses_scraped_prices_only_for_price_bands() -> None:
    display_df = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta", "ulta", "ulta", "ulta"],
            "parent_product_id": ["p1", "p2", "p3", "p4", "p5"],
            "category_key": ["blush", "blush", "blush", "blush", "blush"],
        }
    )
    variants_df = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta", "ulta", "ulta", "ulta"],
            "parent_product_id": ["p1", "p2", "p3", "p4", "p5"],
            "category_key": ["blush", "blush", "blush", "blush", "blush"],
            "price_raw": ["10", "20", "30", "40", "100"],
        }
    )
    empty = pl.DataFrame(schema=display_df.schema)
    tables = ReviewTables(
        parents=display_df,
        variants=variants_df,
        combined=display_df,
        parents_all=empty,
    )

    annotated, category_meta = _annotate_records_with_sales_and_price(
        display_df=display_df,
        tables=tables,
        retailer=["ulta"],
        selected_keys=["blush"],
        record_type="parent",
    )

    assert "price_band" in annotated.columns
    band_by_parent = {
        str(row["parent_product_id"]): row["price_band"]
        for row in annotated.select(["parent_product_id", "price_band"]).to_dicts()
    }
    assert band_by_parent["p1"] == "value"
    assert band_by_parent["p5"] == "premium"
    assert category_meta["blush"]["meta_key"] == "ulta:blush"
    assert "pareto_shares" not in category_meta["blush"]
