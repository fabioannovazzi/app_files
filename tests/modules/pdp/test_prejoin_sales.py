from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

import polars as pl
import pytest
from polars.testing import assert_frame_equal

import modules.pdp.attribute_mapping_core as mapping_mod
from modules.add_attributes.attribute_fill import (
    fill_missing_attribute_values,
    fill_unique_attribute_values,
    resolve_attribute_conflicts,
)
from modules.pdp.attribute_mapping_core import (
    _checkpoint_response_map,
    _fill_attributes_from_web,
    _fill_parent_attributes_from_images,
    _fill_variant_attributes_from_other_retailers,
    _merge_cache_with_base_delta,
    _normalize_catalog_parents,
    _normalize_catalog_variants,
    _taxonomy_attribute_columns_by_scope,
    _taxonomy_attribute_meta_by_id,
)
from modules.pdp.prejoin_sales import JoinConfig, _join_retailer, _normalize_sales
from modules.utilities.utils import get_schema_and_column_names


def test_prejoin_main_rejects_attribute_mapping_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    def fail_if_sales_loads():
        raise AssertionError("mapping stage must not load sales CSVs")

    monkeypatch.setattr(prejoin_mod, "_load_sales_csvs", fail_if_sales_loads)

    with pytest.raises(SystemExit, match="Attribute fill moved upstream"):
        prejoin_mod.main(stage="mapping")


def test_prejoin_public_wrappers_use_single_purpose_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    calls: list[tuple[str | None, str]] = []

    def fake_main(*, dataset: str | None = None, stage: str = "join") -> None:
        calls.append((dataset, stage))

    monkeypatch.setattr(prejoin_mod, "main", fake_main)

    prejoin_mod.run_sales_join(dataset="kiko")

    assert calls == [("kiko", "join")]


def test_checkpoint_response_map_ignores_inactive_resume_rows() -> None:
    assert _checkpoint_response_map([]) == {}


def test_normalize_sales_derives_kiko_category_from_prodlast_levels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    monkeypatch.setattr(prejoin_mod, "ACTIVE_SALES_DATASET", "kiko")

    raw_sales = pl.DataFrame(
        [
            {
                "sku": "sku-1",
                "product_name": "Cream Blush 01",
                "prodlast_lev3": "BLUSHES",
                "prodlast_lev4": "COMPACT BLUSH",
                "period": "2024",
                "channel": "SHOPS",
                "sales": 100.0,
                "units": 10.0,
            },
            {
                "sku": "sku-2",
                "product_name": "Fluid Lipstick 02",
                "prodlast_lev3": "LIPSTICK",
                "prodlast_lev4": "FLUID LIPSTICK",
                "period": "2025",
                "channel": "WEB",
                "sales": 80.0,
                "units": 8.0,
            },
            {
                "sku": "sku-3",
                "product_name": "Face Primer",
                "prodlast_lev3": "PRIMERS AND FIXERS FACE",
                "prodlast_lev4": "PRIMERS FACE",
                "period": "2025",
                "channel": "SHOPS",
                "sales": 50.0,
                "units": 5.0,
            },
            {
                "sku": "sku-4",
                "product_name": "Sculpting Touch Creamy Stick Contour",
                "prodlast_lev3": "CONTOURING",
                "prodlast_lev4": "STICK CONTOURING",
                "period": "2025",
                "channel": "SHOPS",
                "sales": 40.0,
                "units": 4.0,
            },
            {
                "sku": "sku-5",
                "product_name": "Wood Eye Pencil 01",
                "prodlast_lev3": "EYELINER",
                "prodlast_lev4": "WOOD EYE PENCILS",
                "period": "2025",
                "channel": "SHOPS",
                "sales": 30.0,
                "units": 3.0,
            },
        ]
    )

    normalized = _normalize_sales(raw_sales)

    columns, _schema = get_schema_and_column_names(normalized)
    assert {
        "month",
        "period",
        "merchant",
        "category",
        "brand",
        "sku",
        "product_description",
        "sales",
        "units",
        "line",
    }.issubset(set(columns))

    by_sku = {
        row["sku"]: row["category"]
        for row in normalized.select(["sku", "category"]).to_dicts()
    }
    assert by_sku["sku-1"] == "blush"
    assert by_sku["sku-2"] == "liquid lipstick"
    assert by_sku["sku-3"] == "face primer"
    assert by_sku["sku-4"] == "contour"
    assert by_sku["sku-5"] == "wood eye pencils"

    assert normalized.get_column("merchant").unique().to_list() == ["kiko"]
    assert normalized.get_column("brand").unique().to_list() == ["kiko milano"]
    assert sorted(normalized.get_column("line").unique().to_list()) == ["shops", "web"]

    month_by_sku = {
        row["sku"]: row["month"]
        for row in normalized.select(["sku", "month"]).to_dicts()
    }
    assert month_by_sku["sku-1"] == "2024"
    assert month_by_sku["sku-2"] == "2025"
    assert normalized.schema["month"] == pl.Utf8

    period_by_sku = {
        row["sku"]: row["period"]
        for row in normalized.select(["sku", "period"]).to_dicts()
    }
    assert period_by_sku["sku-1"] == "2024"
    assert period_by_sku["sku-2"] == "2025"


def test_merge_cache_with_base_delta_appends_missing_keys_only() -> None:
    preferred = pl.DataFrame(
        [
            {
                "retailer": "amazon",
                "variant_id": "A1",
                "value": "from_shared",
            },
            {
                "retailer": "amazon",
                "variant_id": "A2",
                "value": "from_shared",
            },
            {
                "retailer": "sephora",
                "variant_id": "S1",
                "value": "from_shared",
            },
        ]
    )
    fallback = pl.DataFrame(
        [
            {
                "retailer": "amazon",
                "variant_id": "A1",
                "value": "from_base",
            },
            {
                "retailer": "amazon",
                "variant_id": "A3",
                "value": "from_base",
            },
            {
                "retailer": "ulta",
                "variant_id": "U1",
                "value": "from_base",
            },
        ]
    )

    merged = _merge_cache_with_base_delta(
        preferred,
        fallback,
        key_columns=("retailer", "variant_id"),
        label="variants",
    )

    assert merged.height == 5
    assert (
        merged.filter(
            (pl.col("retailer") == "amazon") & (pl.col("variant_id") == "A1")
        ).height
        == 1
    )
    assert (
        merged.filter((pl.col("retailer") == "amazon") & (pl.col("variant_id") == "A1"))
        .get_column("value")
        .item()
        == "from_shared"
    )
    assert (
        merged.filter(
            (pl.col("retailer") == "amazon") & (pl.col("variant_id") == "A3")
        ).height
        == 1
    )
    assert (
        merged.filter(
            (pl.col("retailer") == "ulta") & (pl.col("variant_id") == "U1")
        ).height
        == 1
    )


def test_merge_cache_with_base_delta_prefers_fallback_when_preferred_empty() -> None:
    preferred = pl.DataFrame()
    fallback = pl.DataFrame(
        [
            {
                "retailer": "amazon",
                "parent_product_id": "P1",
                "value": "from_base",
            }
        ]
    )

    merged = _merge_cache_with_base_delta(
        preferred,
        fallback,
        key_columns=("retailer", "parent_product_id"),
        label="parents",
    )

    assert_frame_equal(merged, fallback)


def test_parent_attribute_resolution_scopes_to_taxonomy_columns_only() -> None:
    taxonomy = {
        "categories": [
            {
                "id": "lipstick",
                "attributes": [
                    {
                        "id": "finish",
                        "label": "Finish",
                        "scope": "product",
                    }
                ],
            }
        ]
    }
    parents_df = pl.DataFrame(
        [
            {
                "retailer": "amazon",
                "parent_product_id": "p1",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "brand": "Demo",
                "product_name": "Cloud Lip",
                "description": "Amazon native PDP text.",
                "finish": "N/A",
            },
            {
                "retailer": "ulta",
                "parent_product_id": "p2",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "brand": "Demo",
                "product_name": "Cloud Lip",
                "description": "Ulta native PDP text.",
                "finish": "matte",
            },
        ]
    )

    meta_by_id = _taxonomy_attribute_meta_by_id(taxonomy)
    product_scope_cols, _variant_scope_cols = _taxonomy_attribute_columns_by_scope(
        parents_df, meta_by_id
    )

    resolved = resolve_attribute_conflicts(
        parents_df,
        retailer_priority=["ulta", "amazon"],
        attribute_columns=product_scope_cols,
    )
    filled = fill_missing_attribute_values(
        resolved,
        retailer_priority=["ulta", "amazon"],
        attribute_columns=product_scope_cols,
    )

    by_retailer = {
        row["retailer"]: row
        for row in filled.select(["retailer", "description", "finish"]).to_dicts()
    }
    assert by_retailer["amazon"]["description"] == "Amazon native PDP text."
    assert by_retailer["ulta"]["description"] == "Ulta native PDP text."
    assert by_retailer["amazon"]["finish"] == "matte"
    assert by_retailer["ulta"]["finish"] == "matte"


def test_normalize_sales_preserves_non_date_period_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    monkeypatch.setattr(prejoin_mod, "ACTIVE_SALES_DATASET", "kiko")

    raw_sales = pl.DataFrame(
        [
            {
                "sku": "sku-period-text",
                "product_name": "Plan Product",
                "prodlast_lev3": "LIPSTICK",
                "period": "Plan 2026",
                "channel": "WEB",
                "sales": 20.0,
                "units": 2.0,
            }
        ]
    )

    normalized = _normalize_sales(raw_sales)
    row = normalized.select(["month", "period"]).row(0)

    assert row[0] == "Plan 2026"
    assert row[1] == "Plan 2026"
    assert normalized.schema["month"] == pl.Utf8


def test_normalize_sales_backfills_missing_category_from_product_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    monkeypatch.setattr(prejoin_mod, "ACTIVE_SALES_DATASET", "kiko")

    raw_sales = pl.DataFrame(
        [
            {
                "month": "2024-01-01",
                "merchant": "kiko",
                "category": None,
                "brand": "kiko milano",
                "sku": "sku-lip-marker",
                "product_description": "Long Lasting Colour Lip Marker - 101",
                "sales": 10.0,
                "units": 1.0,
            },
            {
                "month": "2024-01-01",
                "merchant": "kiko",
                "category": None,
                "brand": "kiko milano",
                "sku": "sku-eyes-clics",
                "product_description": "Eyes Clics 01",
                "sales": 8.0,
                "units": 1.0,
            },
        ]
    )

    normalized = _normalize_sales(raw_sales)
    by_sku = {
        row["sku"]: row["category"]
        for row in normalized.select(["sku", "category"]).to_dicts()
    }

    assert by_sku["sku-lip-marker"] == "lipstick"
    assert by_sku["sku-eyes-clics"] == "palette"


def test_prejoin_sales_variant_name_fallback_is_unique_or_product_level(
    monkeypatch, tmp_path
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    monkeypatch.setattr(prejoin_mod, "SALES_DIR", tmp_path)

    raw_sales = pl.DataFrame(
        [
            {
                "product_collection": "sku_match",
                "month": "2024-01-01",
                "merchant": "sephora",
                "category": "lipstick",
                "brand": "BrandX",
                "sku": "111",
                "product_description": "Product A — Shade One",
                "sales": 10.0,
                "units": 1.0,
                "line": None,
                "time_period": None,
                "extra": None,
            },
            {
                "product_collection": "variant_name_unique",
                "month": "2024-01-01",
                "merchant": "sephora",
                "category": "lipstick",
                "brand": "BrandX",
                "sku": "null",
                "product_description": "Product A — Shade Two",
                "sales": 20.0,
                "units": 2.0,
                "line": None,
                "time_period": None,
                "extra": None,
            },
            {
                "product_collection": "product_only_no_variant_hint",
                "month": "2024-01-01",
                "merchant": "sephora",
                "category": "lipstick",
                "brand": "BrandX",
                "sku": "null",
                "product_description": "Product A",
                "sales": 30.0,
                "units": 3.0,
                "line": None,
                "time_period": None,
                "extra": None,
            },
            {
                "product_collection": "variant_name_ambiguous_goes_product_level",
                "month": "2024-01-01",
                "merchant": "sephora",
                "category": "lipstick",
                "brand": "BrandX",
                "sku": "null",
                "product_description": "Product A — Shade",
                "sales": 40.0,
                "units": 4.0,
                "line": None,
                "time_period": None,
                "extra": None,
            },
            {
                "product_collection": "sku_match_duplicate_shade_1",
                "month": "2024-01-01",
                "merchant": "sephora",
                "category": "lipstick",
                "brand": "BrandX",
                "sku": "333",
                "product_description": "Product A — Shade",
                "sales": 50.0,
                "units": 5.0,
                "line": None,
                "time_period": None,
                "extra": None,
            },
            {
                "product_collection": "sku_match_duplicate_shade_2",
                "month": "2024-01-01",
                "merchant": "sephora",
                "category": "lipstick",
                "brand": "BrandX",
                "sku": "444",
                "product_description": "Product A — Shade",
                "sales": 60.0,
                "units": 6.0,
                "line": None,
                "time_period": None,
                "extra": None,
            },
        ]
    )

    sales_df = _normalize_sales(raw_sales)

    raw_variants = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "variant_id": "111",
                "parent_product_id": "P1",
                "shade_name_raw": "Shade One",
                "shade_name_normalized": "Shade One",
                "size_text_raw": None,
                "price_raw": None,
                "currency": None,
                "barcode": None,
                "availability": None,
                "swatch_image_url": None,
                "hero_image_url": None,
                "variant_description": None,
                "product_name": "Product A",
                "brand": "BrandX",
                "category_label": "lipstick",
            },
            {
                "retailer": "sephora",
                "variant_id": "222",
                "parent_product_id": "P1",
                "shade_name_raw": "Shade Two",
                "shade_name_normalized": "Shade Two",
                "size_text_raw": None,
                "price_raw": None,
                "currency": None,
                "barcode": None,
                "availability": None,
                "swatch_image_url": None,
                "hero_image_url": None,
                "variant_description": None,
                "product_name": "Product A",
                "brand": "BrandX",
                "category_label": "lipstick",
            },
            {
                "retailer": "sephora",
                "variant_id": "333",
                "parent_product_id": "P1",
                "shade_name_raw": "Shade",
                "shade_name_normalized": "Shade",
                "size_text_raw": None,
                "price_raw": None,
                "currency": None,
                "barcode": None,
                "availability": None,
                "swatch_image_url": None,
                "hero_image_url": None,
                "variant_description": None,
                "product_name": "Product A",
                "brand": "BrandX",
                "category_label": "lipstick",
            },
            {
                "retailer": "sephora",
                "variant_id": "444",
                "parent_product_id": "P1",
                "shade_name_raw": "Shade",
                "shade_name_normalized": "Shade",
                "size_text_raw": None,
                "price_raw": None,
                "currency": None,
                "barcode": None,
                "availability": None,
                "swatch_image_url": None,
                "hero_image_url": None,
                "variant_description": None,
                "product_name": "Product A",
                "brand": "BrandX",
                "category_label": "lipstick",
            },
        ]
    )
    variants_df = _normalize_catalog_variants(raw_variants)

    raw_parents = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "pdp_url": "https://example.com/product-a",
                "brand": "BrandX",
                "product_name": "Product A",
                "category_label": "lipstick",
            }
        ]
    )
    parents_df = _normalize_catalog_parents(raw_parents)

    cfg = JoinConfig(
        sales_sku_field="sku",
        catalog_variant_field="variant_id",
        catalog_parent_field="parent_product_id",
    )

    manifest: dict = {"retailers": [], "generated_at": date.today().isoformat()}
    joined = _join_retailer(
        "sephora",
        sales_df=sales_df,
        variants_df=variants_df,
        cfg=cfg,
        manifest=manifest,
        parents_df=parents_df,
    )

    assert joined.height == 6
    assert joined.get_column("product_collection").n_unique() == 6

    # SKU join should still work.
    sku_match = joined.filter(pl.col("product_collection") == "sku_match")
    assert sku_match.height == 1
    assert sku_match.get_column("variant_id").item() == "111"

    # Variant-name join should resolve to a single variant when unique.
    by_name = joined.filter(pl.col("product_collection") == "variant_name_unique")
    assert by_name.height == 1
    assert by_name.get_column("variant_id").item() == "222"

    # When no variant hint exists, only product-level join should apply (no variant_id).
    product_only = joined.filter(
        pl.col("product_collection") == "product_only_no_variant_hint"
    )
    assert product_only.height == 1
    assert product_only.get_column("variant_id").is_null().all()
    assert product_only.get_column("parent_product_id").item() == "P1"

    # Ambiguous variant-name matches should fall back to product-level join (no fanout).
    ambiguous = joined.filter(
        pl.col("product_collection") == "variant_name_ambiguous_goes_product_level"
    )
    assert ambiguous.height == 1
    assert ambiguous.get_column("variant_id").is_null().all()
    assert ambiguous.get_column("parent_product_id").item() == "P1"


def test_prejoin_sales_drops_category_mismatch_even_with_sku_match(
    monkeypatch, tmp_path
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    monkeypatch.setattr(prejoin_mod, "SALES_DIR", tmp_path)

    raw_sales = pl.DataFrame(
        [
            {
                "month": "2025-01-01",
                "merchant": "kiko",
                "category": "skin care",
                "brand": "kiko milano",
                "sku": "111",
                "product_description": "Face Cream",
                "sales": 10.0,
                "units": 1.0,
            }
        ]
    )
    sales_df = _normalize_sales(raw_sales)

    raw_variants = pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "variant_id": "111",
                "parent_product_id": "P1",
                "product_name": "Face Cream",
                "brand": "kiko milano",
                "category_label": "lipstick",
            }
        ]
    )
    variants_df = _normalize_catalog_variants(raw_variants)

    cfg = JoinConfig(
        sales_sku_field="sku",
        catalog_variant_field="variant_id",
        catalog_parent_field="parent_product_id",
    )
    manifest: dict = {"retailers": [], "generated_at": date.today().isoformat()}

    joined = _join_retailer(
        "kiko",
        sales_df=sales_df,
        variants_df=variants_df,
        cfg=cfg,
        manifest=manifest,
        parents_df=pl.DataFrame(),
    )

    assert joined.is_empty()
    assert manifest["retailers"][0]["joined_rows"] == 0


@pytest.mark.parametrize(
    ("sales_category", "catalog_category"),
    [
        ("eyebrow", "WOOD EYE PENCILS"),
        ("wood eye pencils", "EYELINER"),
        ("eyeliner", "AUTOMATIC EYE PENCIL"),
        ("palette", "FACE MAKE-UP KIT"),
    ],
)
def test_prejoin_sales_accepts_kiko_category_aliases_and_compatibility(
    monkeypatch,
    tmp_path,
    sales_category: str,
    catalog_category: str,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    monkeypatch.setattr(prejoin_mod, "SALES_DIR", tmp_path)

    raw_sales = pl.DataFrame(
        [
            {
                "month": "2025-01-01",
                "merchant": "kiko",
                "category": sales_category,
                "brand": "kiko milano",
                "sku": "111",
                "product_description": "Category-compatible test product",
                "sales": 10.0,
                "units": 1.0,
            }
        ]
    )
    sales_df = _normalize_sales(raw_sales)

    raw_variants = pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "variant_id": "111",
                "parent_product_id": "P1",
                "product_name": "Category-compatible test product",
                "brand": "kiko milano",
                "category_label": catalog_category,
            }
        ]
    )
    variants_df = _normalize_catalog_variants(raw_variants)

    cfg = JoinConfig(
        sales_sku_field="sku",
        catalog_variant_field="variant_id",
        catalog_parent_field="parent_product_id",
    )
    manifest: dict = {"retailers": [], "generated_at": date.today().isoformat()}

    joined = _join_retailer(
        "kiko",
        sales_df=sales_df,
        variants_df=variants_df,
        cfg=cfg,
        manifest=manifest,
        parents_df=pl.DataFrame(),
    )

    assert joined.height == 1
    assert joined.get_column("variant_id").item() == "111"


def test_normalize_catalog_variants_builds_backend_join_keys() -> None:
    raw_variants = pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "variant_id": "45115",
                "backend_id": "KC000001015001B",
                "parent_product_id": "45123",
                "backend_parent_id": "KC000001015",
                "product_name": "Dreamphoria Heavenly Skin Blush",
                "brand": "KIKO Milano",
                "category_label": "blush",
            },
            {
                "retailer": "ulta",
                "variant_id": "2641254",
                "parent_product_id": "pimprod2051987",
                "product_name": "3D Hydra Lip Oil",
                "brand": "KIKO Milano",
                "category_label": "lip oil",
            },
        ]
    )

    normalized = _normalize_catalog_variants(raw_variants)
    rows = normalized.select(
        [
            "retailer",
            "variant_id",
            "parent_product_id",
            "variant_id_or_backend_id",
            "parent_product_id_or_backend_id",
        ]
    ).to_dicts()
    lookup = {(str(row["retailer"]), str(row["variant_id"])): row for row in rows}

    kiko = lookup[("kiko", "45115")]
    assert kiko["variant_id_or_backend_id"] == "KC000001015001B"
    assert kiko["parent_product_id_or_backend_id"] == "KC000001015"

    ulta = lookup[("ulta", "2641254")]
    assert ulta["variant_id_or_backend_id"] == "2641254"
    assert ulta["parent_product_id_or_backend_id"] == "pimprod2051987"


def test_join_retailer_matches_kiko_sku_with_backend_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    monkeypatch.setattr(prejoin_mod, "SALES_DIR", tmp_path)

    raw_sales = pl.DataFrame(
        [
            {
                "month": "2025-01-01",
                "merchant": "kiko",
                "category": "blush",
                "brand": "kiko milano",
                "sku": "KC000001015001B",
                "product_description": "Dreamphoria Heavenly Skin Blush 01",
                "sales": 120.0,
                "units": 10.0,
            }
        ]
    )
    sales_df = _normalize_sales(raw_sales)

    raw_variants = pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "variant_id": "45115",
                "backend_id": "KC000001015001B",
                "parent_product_id": "45123",
                "backend_parent_id": "KC000001015",
                "product_name": "Dreamphoria Heavenly Skin Blush",
                "brand": "kiko milano",
                "category_label": "blush",
            }
        ]
    )
    variants_df = _normalize_catalog_variants(raw_variants)

    cfg = JoinConfig(
        sales_sku_field="sku",
        catalog_variant_field="variant_id_or_backend_id",
        catalog_parent_field="parent_product_id",
    )
    manifest: dict = {"retailers": [], "generated_at": date.today().isoformat()}

    joined = _join_retailer(
        "kiko",
        sales_df=sales_df,
        variants_df=variants_df,
        cfg=cfg,
        manifest=manifest,
        parents_df=pl.DataFrame(),
    )

    assert joined.height == 1
    assert joined.get_column("variant_id").item() == "45115"
    assert manifest["retailers"][0]["matched_primary"] == 1


def test_join_retailer_matches_kiko_backend_sku_despite_category_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    monkeypatch.setattr(prejoin_mod, "SALES_DIR", tmp_path)

    raw_sales = pl.DataFrame(
        [
            {
                "month": "2025-01-01",
                "merchant": "kiko",
                "category": "liquid lipstick",
                "brand": "kiko milano",
                "sku": "KM0020102310144",
                "product_description": "Unlimited Double Touch 103",
                "sales": 120.0,
                "units": 10.0,
            }
        ]
    )
    sales_df = _normalize_sales(raw_sales)

    raw_variants = pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "variant_id": "10500",
                "backend_id": "KM0020102310144",
                "parent_product_id": "10497",
                "backend_parent_id": "KM00201023",
                "product_name": "Unlimited Double Touch",
                "brand": "kiko milano",
                "category_label": "lipstick",
            }
        ]
    )
    variants_df = _normalize_catalog_variants(raw_variants)

    cfg = JoinConfig(
        sales_sku_field="sku",
        catalog_variant_field="variant_id_or_backend_id",
        catalog_parent_field="parent_product_id",
    )
    manifest: dict = {"retailers": [], "generated_at": date.today().isoformat()}

    joined = _join_retailer(
        "kiko",
        sales_df=sales_df,
        variants_df=variants_df,
        cfg=cfg,
        manifest=manifest,
        parents_df=pl.DataFrame(),
    )

    assert joined.height == 1
    assert joined.get_column("variant_id").item() == "10500"
    assert manifest["retailers"][0]["matched_primary"] == 1


@pytest.mark.parametrize(
    ("rows", "expected_values"),
    [
        (
            [
                {"retailer": "A", "attribute_value": "x1"},
                {"retailer": "B", "attribute_value": None},
                {"retailer": "C", "attribute_value": "unknown"},
            ],
            ["x1", "x1", "x1"],
        ),
        (
            [
                {"retailer": "A", "attribute_value": "x1"},
                {"retailer": "B", "attribute_value": "x1"},
                {"retailer": "C", "attribute_value": None},
            ],
            ["x1", "x1", "x1"],
        ),
        (
            [
                {"retailer": "A", "attribute_value": "x1"},
                {"retailer": "B", "attribute_value": "x2"},
                {"retailer": "C", "attribute_value": None},
            ],
            ["x1", "x1", "x1"],
        ),
        (
            [
                {"retailer": "A", "attribute_value": "x1"},
                {"retailer": "B", "attribute_value": "not in taxonomy"},
                {"retailer": "C", "attribute_value": None},
            ],
            ["x1", "x1", "x1"],
        ),
    ],
)
def test_fill_unique_attribute_values_fills_unique_values(
    rows, expected_values
) -> None:
    # Arrange
    canonical_id = "canon-1"
    base_rows = [{"canonical_id": canonical_id, **row} for row in rows]
    df = pl.DataFrame(base_rows)

    # Act
    result = fill_unique_attribute_values(df)

    # Assert
    expected = pl.DataFrame(
        {
            "canonical_id": [canonical_id] * len(expected_values),
            "retailer": [row["retailer"] for row in rows],
            "attribute_value": expected_values,
        }
    )
    assert_frame_equal(result, expected)


def test_fill_unique_attribute_values_prefers_ulta_over_sephora() -> None:
    # Arrange
    df = pl.DataFrame(
        [
            {
                "canonical_id": "canon-1",
                "retailer": "sephora",
                "attribute_value": "matte",
            },
            {"canonical_id": "canon-1", "retailer": "ulta", "attribute_value": "satin"},
            {"canonical_id": "canon-1", "retailer": "amazon", "attribute_value": None},
        ]
    )

    # Act
    result = fill_unique_attribute_values(df).sort("retailer")

    # Assert: Ulta wins; everyone becomes satin.
    expected = df.with_columns(pl.lit("satin").alias("attribute_value")).sort(
        "retailer"
    )
    assert_frame_equal(result, expected)


def test_fill_unique_attribute_values_meaningful_beats_not_in_taxonomy_even_when_lower_priority() -> (
    None
):
    # Arrange: higher-priority retailer reports taxonomy-miss, lower priority has meaningful.
    df = pl.DataFrame(
        [
            {
                "canonical_id": "canon-1",
                "retailer": "ulta",
                "attribute_value": "not in taxonomy",
            },
            {
                "canonical_id": "canon-1",
                "retailer": "sephora",
                "attribute_value": "matte",
            },
            {"canonical_id": "canon-1", "retailer": "amazon", "attribute_value": None},
        ]
    )

    # Act
    result = fill_unique_attribute_values(df).sort("retailer")

    # Assert: meaningful wins and overwrites taxonomy-miss; N/A gets filled.
    expected = df.with_columns(pl.lit("matte").alias("attribute_value")).sort(
        "retailer"
    )
    assert_frame_equal(result, expected)


def test_fill_unique_attribute_values_does_not_fill_na_from_only_not_in_taxonomy() -> (
    None
):
    # Arrange: no meaningful value exists.
    df = pl.DataFrame(
        [
            {
                "canonical_id": "canon-1",
                "retailer": "ulta",
                "attribute_value": "not in taxonomy",
            },
            {"canonical_id": "canon-1", "retailer": "sephora", "attribute_value": None},
            {"canonical_id": "canon-1", "retailer": "amazon", "attribute_value": "N/A"},
        ]
    )

    # Act
    result = fill_unique_attribute_values(df).sort("retailer")

    # Assert: taxonomy-miss stays, N/A stays.
    expected = df.sort("retailer")
    assert_frame_equal(result, expected)


def test_prejoin_sales_variant_fill_stable_variant_attribute_fills_na_across_retailers() -> (
    None
):
    df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "variant_id": "U1",
                "canonical_id": "canon-1",
                "category_key": "cat-1",
                "finish": "matte",
            },
            {
                "retailer": "ulta",
                "variant_id": "U2",
                "canonical_id": "canon-1",
                "category_key": "cat-1",
                "finish": "matte",
            },
            {
                "retailer": "sephora",
                "variant_id": "S1",
                "canonical_id": "canon-1",
                "category_key": "cat-1",
                "finish": None,
            },
            {
                "retailer": "sephora",
                "variant_id": "S2",
                "canonical_id": "canon-1",
                "category_key": "cat-1",
                "finish": "N/A",
            },
        ]
    )

    result = _fill_variant_attributes_from_other_retailers(
        df, retailer_priority=["ulta", "sephora"]
    ).sort(["retailer", "variant_id"])

    expected = df.with_columns(pl.lit("matte").alias("finish")).sort(
        ["retailer", "variant_id"]
    )
    assert_frame_equal(result, expected)


def test_prejoin_sales_variant_fill_varying_variant_attribute_fills_by_variant_match_key() -> (
    None
):
    df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "variant_id": "U1",
                "canonical_id": "canon-2",
                "category_key": "cat-1",
                "shade_name_normalized": "Red",
                "finish": "matte",
            },
            {
                "retailer": "ulta",
                "variant_id": "U2",
                "canonical_id": "canon-2",
                "category_key": "cat-1",
                "shade_name_normalized": "Yellow",
                "finish": "satin",
            },
            {
                "retailer": "sephora",
                "variant_id": "S1",
                "canonical_id": "canon-2",
                "category_key": "cat-1",
                "shade_name_normalized": "Red",
                "finish": None,
            },
            {
                "retailer": "sephora",
                "variant_id": "S2",
                "canonical_id": "canon-2",
                "category_key": "cat-1",
                "shade_name_normalized": "Yellow",
                "finish": "N/A",
            },
        ]
    )

    result = _fill_variant_attributes_from_other_retailers(
        df, retailer_priority=["ulta", "sephora"]
    ).sort(["retailer", "variant_id"])

    expected = df.with_columns(
        pl.when(pl.col("retailer") == "sephora")
        .then(
            pl.when(pl.col("shade_name_normalized") == "Red")
            .then(pl.lit("matte"))
            .otherwise(pl.lit("satin"))
        )
        .otherwise(pl.col("finish"))
        .alias("finish")
    ).sort(["retailer", "variant_id"])
    assert_frame_equal(result, expected)


def test_prejoin_sales_variant_fill_varying_variant_attribute_skips_ambiguous_match_keys() -> (
    None
):
    df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "variant_id": "U1",
                "canonical_id": "canon-3",
                "category_key": "cat-1",
                "shade_name_normalized": "Red",
                "finish": "matte",
            },
            {
                "retailer": "ulta",
                "variant_id": "U2",
                "canonical_id": "canon-3",
                "category_key": "cat-1",
                "shade_name_normalized": "Yellow",
                "finish": "satin",
            },
            # Sephora has a duplicated shade name, so the match key is ambiguous and should not be filled.
            {
                "retailer": "sephora",
                "variant_id": "S1",
                "canonical_id": "canon-3",
                "category_key": "cat-1",
                "shade_name_normalized": "Red",
                "finish": None,
            },
            {
                "retailer": "sephora",
                "variant_id": "S2",
                "canonical_id": "canon-3",
                "category_key": "cat-1",
                "shade_name_normalized": "Red",
                "finish": "N/A",
            },
            {
                "retailer": "sephora",
                "variant_id": "S3",
                "canonical_id": "canon-3",
                "category_key": "cat-1",
                "shade_name_normalized": "Yellow",
                "finish": "N/A",
            },
        ]
    )

    result = _fill_variant_attributes_from_other_retailers(
        df, retailer_priority=["ulta", "sephora"]
    ).sort(["retailer", "variant_id"])

    expected = df.with_columns(
        pl.when(
            (pl.col("retailer") == "sephora")
            & (pl.col("shade_name_normalized") == "Yellow")
        )
        .then(pl.lit("satin"))
        .otherwise(pl.col("finish"))
        .alias("finish")
    ).sort(["retailer", "variant_id"])
    assert_frame_equal(result, expected)


def test_prejoin_sales_parent_image_fill_fills_missing_form(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "blush",
                "label": "blush",
                "image_allowlist": ["form"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                            {"id": "other", "label": "not in taxonomy"},
                        ],
                    }
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "U1",
                "canonical_id": "canon-1",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush A",
                "hero_image_url": "https://example.com/u1.jpg",
                "form": None,
            },
            {
                "retailer": "sephora",
                "parent_product_id": "S1",
                "canonical_id": "canon-1",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush A",
                "hero_image_url": "https://example.com/s1.jpg",
                "form": "N/A",
            },
        ]
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        assert len(prompts) == 1
        user_content = prompts[0]["user_content"]
        assert user_content[1]["type"] == "input_image"
        return [{"attributes": {"form": {"value": "Powder", "confidence": 0.9}}}]

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    result, audit = _fill_parent_attributes_from_images(
        parents_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["ulta", "sephora"],
    )

    expected = parents_df.with_columns(pl.lit("powder").alias("form")).sort("retailer")
    assert_frame_equal(result.sort("retailer"), expected)
    assert not audit.is_empty()


def test_prejoin_sales_parent_image_fill_accepts_string_confidence(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "blush",
                "label": "blush",
                "image_allowlist": ["form"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                            {"id": "other", "label": "not in taxonomy"},
                        ],
                    }
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "U1",
                "canonical_id": "canon-1",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush A",
                "hero_image_url": "https://example.com/u1.jpg",
                "form": None,
            }
        ]
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        assert len(prompts) == 1
        return [{"attributes": {"form": {"value": "Powder", "confidence": "0.91"}}}]

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    result, audit = _fill_parent_attributes_from_images(
        parents_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["ulta"],
    )

    expected = parents_df.with_columns(pl.lit("powder").alias("form"))
    assert_frame_equal(result, expected)
    assert not audit.is_empty()


def test_prejoin_sales_parent_image_fill_handles_short_responses(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "blush",
                "label": "blush",
                "image_allowlist": ["form"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                            {"id": "other", "label": "not in taxonomy"},
                        ],
                    }
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "U1",
                "canonical_id": "canon-1",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush A",
                "hero_image_url": "https://example.com/u1.jpg",
                "form": None,
            },
            {
                "retailer": "sephora",
                "parent_product_id": "S1",
                "canonical_id": "canon-2",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandY",
                "product_name": "Blush B",
                "hero_image_url": "https://example.com/s1.jpg",
                "form": None,
            },
        ]
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        assert len(prompts) == 2
        return [{"attributes": {"form": {"value": "Powder", "confidence": 0.95}}}]

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    result, audit = _fill_parent_attributes_from_images(
        parents_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["ulta", "sephora"],
    )

    assert result.get_column("form").to_list().count("powder") == 1
    assert audit.height == 2


def test_prejoin_sales_parent_image_fill_skips_invalid_image_url(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "blush",
                "label": "blush",
                "image_allowlist": ["form"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                            {"id": "other", "label": "not in taxonomy"},
                        ],
                    }
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "S1",
                "canonical_id": "canon-1",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush A",
                "hero_image_url": "https://www.sephora.com/productimages/sku/sundefined-main-zoom.jpg?imwidth=50",
                "form": None,
            }
        ]
    )

    monkeypatch.setattr(mapping_mod, "build_image_cache", lambda *_args, **_kwargs: {})

    def fake_run_step_json(*_args, **_kwargs):
        raise AssertionError("run_step_json should not be called for invalid URLs")

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    result, audit = _fill_parent_attributes_from_images(
        parents_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["sephora"],
    )

    assert_frame_equal(result, parents_df)
    assert audit.is_empty()


def test_prejoin_sales_parent_image_fill_uses_local_image_first(
    monkeypatch, tmp_path
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "blush",
                "label": "blush",
                "image_allowlist": ["form"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                            {"id": "other", "label": "not in taxonomy"},
                        ],
                    }
                ],
            }
        ]
    }

    img_path = tmp_path / "sample.png"
    from PIL import Image

    with img_path.open("wb") as fh:
        Image.new("RGB", (1, 1), color=(255, 0, 0)).save(fh, format="PNG")

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "S1",
                "canonical_id": "canon-1",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush A",
                "hero_image_url": "https://www.sephora.com/productimages/sku/sundefined-main-zoom.jpg?imwidth=50",
                "form": None,
            }
        ]
    )

    monkeypatch.setattr(
        mapping_mod, "build_image_cache", lambda *_args, **_kwargs: {"x": []}
    )
    monkeypatch.setattr(
        mapping_mod, "find_local_image", lambda *_args, **_kwargs: img_path
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        assert len(prompts) == 1
        user_content = prompts[0]["user_content"]
        image_url = user_content[1]["image_url"]
        assert isinstance(image_url, str)
        assert image_url.startswith("data:image/")
        return [{"attributes": {"form": {"value": "Powder", "confidence": 0.92}}}]

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    result, audit = _fill_parent_attributes_from_images(
        parents_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["sephora"],
    )

    expected = parents_df.with_columns(pl.lit("powder").alias("form"))
    assert_frame_equal(result, expected)
    assert not audit.is_empty()


def test_prejoin_sales_image_path_to_data_url_converts_unsupported_extension(
    tmp_path: Path,
) -> None:
    from PIL import Image

    image_path = tmp_path / "sample.avif"
    with image_path.open("wb") as fh:
        image = Image.new("RGB", (1, 1), color=(255, 0, 0))
        image.save(fh, format="PNG")

    data_url = mapping_mod._image_path_to_data_url(image_path)

    assert data_url is not None
    assert data_url.startswith("data:image/png;base64,")


def test_prejoin_sales_image_path_to_data_url_converts_mislabeled_avif_jpg(
    tmp_path: Path,
) -> None:
    import pillow_avif  # noqa: F401
    from PIL import Image

    image_path = tmp_path / "sample.jpg"
    with image_path.open("wb") as fh:
        image = Image.new("RGB", (1, 1), color=(255, 0, 0))
        image.save(fh, format="AVIF")

    data_url = mapping_mod._image_path_to_data_url(image_path)

    assert data_url is not None
    assert data_url.startswith("data:image/png;base64,")


def test_prejoin_sales_image_path_to_data_url_downloads_supported_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from io import BytesIO

    from PIL import Image

    image_path = tmp_path / "sample.avif"
    image_path.write_bytes(b"not a decodable local avif")
    jpeg_buffer = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(jpeg_buffer, format="JPEG")
    jpeg_bytes = jpeg_buffer.getvalue()

    class FakeHeaders:
        def get_content_type(self) -> str:
            return "image/jpeg"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int) -> bytes:
            return jpeg_bytes

    def fake_urlopen(request, timeout: int):
        assert timeout == 30
        assert request.full_url.startswith("https://example.com/image")
        return FakeResponse()

    monkeypatch.setattr(mapping_mod, "urlopen", fake_urlopen)

    data_url = mapping_mod._image_path_to_data_url(
        image_path,
        fallback_url="https://example.com/image?wid=100",
    )

    assert data_url is not None
    assert data_url.startswith("data:image/jpeg;base64,")


def test_prejoin_sales_parent_image_fill_preserves_late_attributes(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "blush",
                "label": "blush",
                "image_allowlist": ["form", "configuration"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                            {"id": "other", "label": "not in taxonomy"},
                        ],
                    },
                    {
                        "id": "configuration",
                        "label": "configuration",
                        "scope": "product",
                        "nodes": [
                            {"id": "single", "label": "Single"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                            {"id": "other", "label": "not in taxonomy"},
                        ],
                    },
                ],
            }
        ]
    }

    rows = []
    for idx in range(105):
        rows.append(
            {
                "retailer": "sephora",
                "parent_product_id": f"S{idx}",
                "canonical_id": f"canon-{idx}",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": f"Blush {idx}",
                "hero_image_url": f"https://example.com/{idx}.jpg",
                "form": None if idx < 104 else "powder",
                "configuration": "single" if idx < 104 else None,
            }
        )
    parents_df = pl.DataFrame(
        rows,
        schema_overrides={"form": pl.Utf8, "configuration": pl.Utf8},
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        responses = []
        for prompt in prompts:
            text = prompt["user_content"][0]["text"]
            if '"configuration"' in text:
                responses.append(
                    {
                        "attributes": {
                            "configuration": {"value": "single", "confidence": 0.9}
                        }
                    }
                )
            else:
                responses.append(
                    {"attributes": {"form": {"value": "Powder", "confidence": 0.9}}}
                )
        return responses

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    result, audit = _fill_parent_attributes_from_images(
        parents_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["sephora"],
    )

    assert (
        result.filter(pl.col("canonical_id") == "canon-104")
        .get_column("configuration")
        .item()
        == "single"
    )
    assert result.get_column("form").to_list().count("powder") == 105
    assert audit.height == 105


def test_prejoin_sales_parent_image_fill_skips_low_coverage_attributes(
    monkeypatch,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "blush",
                "label": "blush",
                "image_allowlist": ["form"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    }
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush One",
                "hero_image_url": "https://example.com/p1.jpg",
                "form": None,
            },
            {
                "retailer": "sephora",
                "parent_product_id": "P2",
                "canonical_id": "canon-2",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush Two",
                "hero_image_url": "https://example.com/p2.jpg",
                "form": "powder",
            },
            {
                "retailer": "sephora",
                "parent_product_id": "P3",
                "canonical_id": "canon-3",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush Three",
                "hero_image_url": "https://example.com/p3.jpg",
                "form": "powder",
            },
            {
                "retailer": "sephora",
                "parent_product_id": "P4",
                "canonical_id": "canon-4",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush Four",
                "hero_image_url": "https://example.com/p4.jpg",
                "form": None,
            },
        ]
    )

    monkeypatch.setattr(
        mapping_mod,
        "_load_no_value_query_suppression",
        lambda **_kwargs: (set(), set()),
    )

    def fake_run_step_json(*_args, **_kwargs):
        raise AssertionError("run_step_json should not be called below coverage gate")

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    result, audit = _fill_parent_attributes_from_images(
        parents_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["sephora"],
        min_attribute_coverage=0.7,
    )

    assert_frame_equal(result, parents_df)
    assert audit.is_empty()


def test_prejoin_sales_parent_image_fill_replays_checkpoint_response(
    monkeypatch,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "blush",
                "label": "blush",
                "image_allowlist": ["form"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    }
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "blush",
                "category_label": "blush",
                "brand": "BrandX",
                "product_name": "Blush One",
                "hero_image_url": "https://example.com/p1.jpg",
                "form": None,
            }
        ]
    )

    monkeypatch.setattr(
        mapping_mod,
        "_load_no_value_query_suppression",
        lambda **_kwargs: (set(), set()),
    )

    request_key = mapping_mod._vision_request_key(
        group_info={"canonical_id": "canon-1", "category_key": "blush"},
        category_key="blush",
        source_retailer="sephora",
        source_parent_product_id="P1",
        missing_attrs=["form"],
    )
    checkpoint_map = {
        request_key: {"attributes": {"form": {"value": "powder", "confidence": 0.95}}}
    }

    def fake_run_step_json(*_args, **_kwargs):
        raise AssertionError("run_step_json should not be called for replayed requests")

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    result, audit = _fill_parent_attributes_from_images(
        parents_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["sephora"],
        checkpoint_response_by_key=checkpoint_map,
    )

    assert result.get_column("form").item() == "powder"
    assert audit.height == 1
    assert audit.get_column("replayed_from_checkpoint").item() is True
    assert audit.get_column("request_key").item() == request_key


def test_prejoin_sales_web_fill_updates_parent_and_variant(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "eyeshadow",
                "label": "eyeshadow",
                "web_allowlist": ["form", "finish"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                    {
                        "id": "finish",
                        "label": "finish",
                        "scope": "variant",
                        "nodes": [
                            {"id": "matte", "label": "Matte"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow A",
                "form": None,
            }
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "variant_id": "V1",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow A",
                "variant_description": "Shade One",
                "finish": None,
            }
        ]
    )

    def fake_lookup_websites(_llm, names, **_kwargs):
        return {str(name).strip().lower(): "https://brandx.com" for name in names}

    monkeypatch.setattr(mapping_mod, "lookup_websites", fake_lookup_websites)
    monkeypatch.setattr(
        mapping_mod, "set_lookup_market_context", lambda **_kwargs: None
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        assert len(prompts) == 1
        return [
            {
                "parent_attributes": {
                    "form": {
                        "value": "powder",
                        "confidence": 0.9,
                        "evidence_url": "https://brandx.com/p/eyeshadow-a",
                    }
                },
                "variants": {
                    "sephora:V1": {
                        "finish": {
                            "value": "matte",
                            "confidence": 0.9,
                            "evidence_url": "https://brandx.com/p/eyeshadow-a",
                        }
                    }
                },
            }
        ]

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    parents_out, variants_out, audit = _fill_attributes_from_web(
        parents_df,
        variants_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["sephora"],
    )

    assert parents_out.get_column("form").item() == "powder"
    assert variants_out.get_column("finish").item() == "matte"
    assert not audit.is_empty()


def test_prejoin_sales_web_fill_calls_checkpoint_callback(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "eyeshadow",
                "label": "eyeshadow",
                "web_allowlist": ["form", "finish"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                    {
                        "id": "finish",
                        "label": "finish",
                        "scope": "variant",
                        "nodes": [
                            {"id": "matte", "label": "Matte"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow A",
                "form": None,
            }
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "variant_id": "V1",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow A",
                "variant_description": "Shade One",
                "finish": None,
            }
        ]
    )

    def fake_lookup_websites(_llm, names, **_kwargs):
        return {str(name).strip().lower(): "https://brandx.com" for name in names}

    monkeypatch.setattr(mapping_mod, "lookup_websites", fake_lookup_websites)
    monkeypatch.setattr(
        mapping_mod, "set_lookup_market_context", lambda **_kwargs: None
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        assert len(prompts) == 1
        return [
            {
                "parent_attributes": {
                    "form": {
                        "value": "powder",
                        "confidence": 0.9,
                        "evidence_url": "https://brandx.com/p/eyeshadow-a",
                    }
                },
                "variants": {
                    "sephora:V1": {
                        "finish": {
                            "value": "matte",
                            "confidence": 0.9,
                            "evidence_url": "https://brandx.com/p/eyeshadow-a",
                        }
                    }
                },
            }
        ]

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    batches: list[list[dict[str, object]]] = []

    def fake_checkpoint(rows: Sequence[dict[str, object]]) -> None:
        batches.append(list(rows))

    parents_out, variants_out, audit = _fill_attributes_from_web(
        parents_df,
        variants_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["sephora"],
        audit_checkpoint_callback=fake_checkpoint,
    )

    assert parents_out.get_column("form").item() == "powder"
    assert variants_out.get_column("finish").item() == "matte"
    assert not audit.is_empty()
    assert len(batches) == 1
    assert len(batches[0]) == 1
    assert batches[0][0]["source_parent_product_id"] == "P1"
    assert "sephora:V1" in str(batches[0][0]["filled_variant_attributes"])


def test_prejoin_sales_web_fill_accepts_single_item_list_values(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "eyeliner",
                "label": "eyeliner",
                "web_allowlist": ["base", "finish"],
                "attributes": [
                    {
                        "id": "base",
                        "label": "base",
                        "scope": "product",
                        "nodes": [
                            {"id": "silicone-based", "label": "Silicone-based"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                    {
                        "id": "finish",
                        "label": "finish",
                        "scope": "variant",
                        "nodes": [
                            {"id": "matte", "label": "Matte"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "category_label": "eyeliner",
                "brand": "Too Faced",
                "product_name": "Killer Liner 36 Hour Waterproof Gel Eyeliner",
                "base": None,
            }
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "variant_id": "V1",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "category_label": "eyeliner",
                "brand": "Too Faced",
                "product_name": "Killer Liner 36 Hour Waterproof Gel Eyeliner",
                "variant_description": "Killer Liner",
                "finish": None,
            }
        ]
    )

    def fake_lookup_websites(_llm, names, **_kwargs):
        return {str(name).strip().lower(): "https://www.toofaced.com" for name in names}

    monkeypatch.setattr(mapping_mod, "lookup_websites", fake_lookup_websites)
    monkeypatch.setattr(
        mapping_mod, "set_lookup_market_context", lambda **_kwargs: None
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        assert len(prompts) == 1
        return [
            {
                "parent_attributes": {
                    "base": {
                        "value": ["silicone-based"],
                        "confidence": 0.9,
                        "evidence_url": "https://www.toofaced.com/product/23485/76774/Eye-Makeup/Eyeliner/Killer-Liner-36-Hour-Waterproof-Gel-Eyeliner-Pencil/Total-Control-36-Hour-Waterproof-Eyeliner",
                    }
                },
                "variants": {
                    "ulta:V1": {
                        "finish": {
                            "value": ["matte"],
                            "confidence": 0.9,
                            "evidence_url": "https://www.toofaced.com/product/23485/76774/Eye-Makeup/Eyeliner/Killer-Liner-36-Hour-Waterproof-Gel-Eyeliner-Pencil/Total-Control-36-Hour-Waterproof-Eyeliner",
                        }
                    }
                },
            }
        ]

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    parents_out, variants_out, audit = _fill_attributes_from_web(
        parents_df,
        variants_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["ulta"],
    )

    assert parents_out.get_column("base").item() == "silicone-based"
    assert variants_out.get_column("finish").item() == "matte"
    assert not audit.is_empty()


def test_prejoin_sales_web_fill_recovers_from_raw_response_fragment(
    monkeypatch,
) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "eyeliner",
                "label": "eyeliner",
                "web_allowlist": ["base", "finish"],
                "attributes": [
                    {
                        "id": "base",
                        "label": "base",
                        "scope": "product",
                        "nodes": [
                            {"id": "silicone-based", "label": "Silicone-based"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                    {
                        "id": "finish",
                        "label": "finish",
                        "scope": "variant",
                        "nodes": [
                            {"id": "matte", "label": "Matte"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "category_label": "eyeliner",
                "brand": "Too Faced",
                "product_name": "Killer Liner 36 Hour Waterproof Gel Eyeliner",
                "base": None,
            }
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "variant_id": "V1",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "category_label": "eyeliner",
                "brand": "Too Faced",
                "product_name": "Killer Liner 36 Hour Waterproof Gel Eyeliner",
                "variant_description": "Killer Liner",
                "finish": None,
            }
        ]
    )

    def fake_lookup_websites(_llm, names, **_kwargs):
        return {str(name).strip().lower(): "https://www.toofaced.com" for name in names}

    monkeypatch.setattr(mapping_mod, "lookup_websites", fake_lookup_websites)
    monkeypatch.setattr(
        mapping_mod, "set_lookup_market_context", lambda **_kwargs: None
    )

    raw_fragment = (
        ', "parent_attributes": {"base": {"value": "silicone-based", '
        '"confidence": 0.9, "evidence_url": "https://www.toofaced.com/product/23485"}}, '
        '"variants": {"ulta:V1": {"finish": {"value": "matte", "confidence": 0.9, '
        '"evidence_url": "https://www.toofaced.com/product/23485"}}}'
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        assert len(prompts) == 1
        return [
            {
                "error": "JSON parsing failed",
                "raw_response": raw_fragment,
            }
        ]

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    parents_out, variants_out, audit = _fill_attributes_from_web(
        parents_df,
        variants_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["ulta"],
    )

    assert parents_out.get_column("base").item() == "silicone-based"
    assert variants_out.get_column("finish").item() == "matte"
    assert not audit.is_empty()


def test_prejoin_sales_web_fill_reuses_relaxed_brand_cache_keys(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "setting_spray_powder",
                "label": "setting spray & powder",
                "web_allowlist": ["skin_type"],
                "attributes": [
                    {
                        "id": "skin_type",
                        "label": "skin type",
                        "scope": "product",
                        "nodes": [
                            {"id": "all skin types", "label": "All skin types"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    }
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P503732",
                "canonical_id": "canon-1",
                "category_key": "setting_spray_powder",
                "category_label": "setting spray & powder",
                "brand": "Ami Col\u00e9",
                "product_name": "Skin Melt Talc-Free Loose Setting Powder",
                "skin type": "N/A",
            }
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "variant_id": "P503732",
                "parent_product_id": "P503732",
                "canonical_id": "canon-1",
                "category_key": "setting_spray_powder",
                "category_label": "setting spray & powder",
                "brand": "Ami Col\u00e9",
                "product_name": "Skin Melt Talc-Free Loose Setting Powder",
            }
        ]
    )

    # Cache key intentionally uses a compact form ("amicolé") that does not
    # exactly match brand.lower() ("ami colé").
    def fake_lookup_websites(_llm, _names, **_kwargs):
        return {"amicol\u00e9": "https://www.amicole.com"}

    monkeypatch.setattr(mapping_mod, "lookup_websites", fake_lookup_websites)
    monkeypatch.setattr(
        mapping_mod, "set_lookup_market_context", lambda **_kwargs: None
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        assert len(prompts) == 1
        return [
            {
                "parent_attributes": {
                    "skin_type": {
                        "value": "all skin types",
                        "confidence": 0.95,
                        "evidence_url": "https://www.amicole.com/products/skin-melt-loose-powder",
                    }
                },
                "variants": {},
            }
        ]

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    parents_out, _, audit = _fill_attributes_from_web(
        parents_df,
        variants_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["sephora"],
    )

    assert parents_out.get_column("skin type").item() == "all skin types"
    assert not audit.is_empty()


def test_prejoin_sales_web_fill_skips_low_coverage_attributes(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "eyeshadow",
                "label": "eyeshadow",
                "web_allowlist": ["form", "base", "finish", "undertone"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                    {
                        "id": "base",
                        "label": "base",
                        "scope": "product",
                        "nodes": [
                            {"id": "silicone-based", "label": "Silicone-based"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                    {
                        "id": "finish",
                        "label": "finish",
                        "scope": "variant",
                        "nodes": [
                            {"id": "matte", "label": "Matte"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                    {
                        "id": "undertone",
                        "label": "undertone",
                        "scope": "variant",
                        "nodes": [
                            {"id": "warm", "label": "Warm"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow One",
                "form": None,
                "base": None,
            },
            {
                "retailer": "sephora",
                "parent_product_id": "P2",
                "canonical_id": "canon-2",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow Two",
                "form": "powder",
                "base": "silicone-based",
            },
            {
                "retailer": "sephora",
                "parent_product_id": "P3",
                "canonical_id": "canon-3",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow Three",
                "form": "powder",
                "base": "silicone-based",
            },
            {
                "retailer": "sephora",
                "parent_product_id": "P4",
                "canonical_id": "canon-4",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow Four",
                "form": None,
                "base": "silicone-based",
            },
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "variant_id": "V1",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow One",
                "variant_description": "Shade One",
                "finish": None,
                "undertone": None,
            },
            {
                "retailer": "sephora",
                "variant_id": "V2",
                "parent_product_id": "P2",
                "canonical_id": "canon-2",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow Two",
                "variant_description": "Shade Two",
                "finish": "matte",
                "undertone": "warm",
            },
            {
                "retailer": "sephora",
                "variant_id": "V3",
                "parent_product_id": "P3",
                "canonical_id": "canon-3",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow Three",
                "variant_description": "Shade Three",
                "finish": "matte",
                "undertone": "warm",
            },
            {
                "retailer": "sephora",
                "variant_id": "V4",
                "parent_product_id": "P4",
                "canonical_id": "canon-4",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow Four",
                "variant_description": "Shade Four",
                "finish": None,
                "undertone": "warm",
            },
        ]
    )

    monkeypatch.setattr(
        mapping_mod,
        "_load_no_value_query_suppression",
        lambda **_kwargs: (set(), set()),
    )

    def fake_lookup_websites(_llm, names, **_kwargs):
        return {str(name).strip().lower(): "https://brandx.com" for name in names}

    monkeypatch.setattr(mapping_mod, "lookup_websites", fake_lookup_websites)
    monkeypatch.setattr(
        mapping_mod, "set_lookup_market_context", lambda **_kwargs: None
    )

    def fake_run_step_json(_llm, _step, _system, prompts, **_kwargs):
        assert len(prompts) == 1
        assert '"base"' in prompts[0]
        assert '"undertone"' in prompts[0]
        assert '"form"' not in prompts[0]
        assert '"finish"' not in prompts[0]
        return [
            {
                "parent_attributes": {
                    "base": {
                        "value": "silicone-based",
                        "confidence": 0.95,
                        "evidence_url": "https://brandx.com/p/eyeshadow-one",
                    }
                },
                "variants": {
                    "sephora:V1": {
                        "undertone": {
                            "value": "warm",
                            "confidence": 0.95,
                            "evidence_url": "https://brandx.com/p/eyeshadow-one",
                        }
                    }
                },
            }
        ]

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    parents_out, variants_out, audit = _fill_attributes_from_web(
        parents_df,
        variants_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["sephora"],
        min_attribute_coverage=0.7,
    )

    parent_p1 = parents_out.filter(pl.col("parent_product_id") == "P1").row(
        0, named=True
    )
    variant_v1 = variants_out.filter(pl.col("variant_id") == "V1").row(0, named=True)
    assert parent_p1["base"] == "silicone-based"
    assert parent_p1["form"] is None
    assert variant_v1["undertone"] == "warm"
    assert variant_v1["finish"] is None
    assert audit.height == 1


def test_prejoin_sales_web_fill_replays_checkpoint_response(monkeypatch) -> None:
    import modules.pdp.prejoin_sales as prejoin_mod

    taxonomy = {
        "categories": [
            {
                "id": "eyeshadow",
                "label": "eyeshadow",
                "web_allowlist": ["form", "finish"],
                "attributes": [
                    {
                        "id": "form",
                        "label": "form",
                        "scope": "product",
                        "nodes": [
                            {"id": "powder", "label": "Powder"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                    {
                        "id": "finish",
                        "label": "finish",
                        "scope": "variant",
                        "nodes": [
                            {"id": "matte", "label": "Matte"},
                            {"id": "unknown", "label": "N/A (not stated)"},
                        ],
                    },
                ],
            }
        ]
    }

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow A",
                "form": None,
            }
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "variant_id": "V1",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
                "brand": "BrandX",
                "product_name": "Eyeshadow A",
                "variant_description": "Shade One",
                "finish": None,
            }
        ]
    )

    monkeypatch.setattr(
        mapping_mod,
        "_load_no_value_query_suppression",
        lambda **_kwargs: (set(), set()),
    )
    monkeypatch.setattr(
        mapping_mod,
        "lookup_websites",
        lambda _llm, names, **_kwargs: {
            str(name).strip().lower(): "https://brandx.com" for name in names
        },
    )
    monkeypatch.setattr(
        mapping_mod, "set_lookup_market_context", lambda **_kwargs: None
    )

    request_key = mapping_mod._web_request_key(
        group_info={"canonical_id": "canon-1", "category_key": "eyeshadow"},
        category_key="eyeshadow",
        source_retailer="sephora",
        source_parent_product_id="P1",
        domains=["brandx.com"],
        missing_parent_attrs=["form"],
        variant_missing_map={"sephora:V1": ["finish"]},
    )
    checkpoint_map = {
        request_key: {
            "parent_attributes": {
                "form": {
                    "value": "powder",
                    "confidence": 0.95,
                    "evidence_url": "https://brandx.com/p/eyeshadow-a",
                }
            },
            "variants": {
                "sephora:V1": {
                    "finish": {
                        "value": "matte",
                        "confidence": 0.95,
                        "evidence_url": "https://brandx.com/p/eyeshadow-a",
                    }
                }
            },
        }
    }

    def fake_run_step_json(*_args, **_kwargs):
        raise AssertionError("run_step_json should not be called for replayed requests")

    monkeypatch.setattr(mapping_mod, "run_step_json", fake_run_step_json)

    parents_out, variants_out, audit = _fill_attributes_from_web(
        parents_df,
        variants_df,
        taxonomy=taxonomy,
        llm_wrapper=object(),
        retailer_priority=["sephora"],
        checkpoint_response_by_key=checkpoint_map,
    )

    assert parents_out.get_column("form").item() == "powder"
    assert variants_out.get_column("finish").item() == "matte"
    assert audit.height == 1
    assert audit.get_column("replayed_from_checkpoint").item() is True
    assert audit.get_column("request_key").item() == request_key
