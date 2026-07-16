from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from fastapi import HTTPException
from polars.testing import assert_frame_equal


def test_postfill_attribute_cache_roundtrip(monkeypatch, tmp_path: Path) -> None:
    import modules.pdp.api as api_mod
    import modules.pdp.attribute_mapping_core as mapping_mod

    cache_dir = tmp_path / "postfill_attribute_cache"
    monkeypatch.setattr(mapping_mod, "POSTFILL_ATTRIBUTE_CACHE_DIR", cache_dir)
    monkeypatch.setattr(
        mapping_mod, "POSTFILL_PARENTS_OUTPUT", cache_dir / "parents.parquet"
    )
    monkeypatch.setattr(
        mapping_mod, "POSTFILL_VARIANTS_OUTPUT", cache_dir / "variants.parquet"
    )
    monkeypatch.setattr(
        mapping_mod, "POSTFILL_PARENTS_ALL_OUTPUT", cache_dir / "parents_all.parquet"
    )
    monkeypatch.setattr(
        mapping_mod, "POSTFILL_COMBINED_OUTPUT", cache_dir / "combined.parquet"
    )

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "P1",
                "brand": "BrandX",
                "product_name": "Product A",
                "category_key": "lipstick",
                "form": "stick",
            },
            {
                "retailer": "sephora",
                "parent_product_id": "P2",
                "brand": "BrandY",
                "product_name": "Product B",
                "category_key": "lipstick",
                "form": "liquid",
            },
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "shade_name_normalized": "Red",
                "form": "stick",
            },
            {
                "retailer": "sephora",
                "parent_product_id": "P2",
                "variant_id": "V2",
                "shade_name_normalized": "Nude",
                "form": "liquid",
            },
        ]
    )

    mapping_mod._write_postfill_attribute_cache(
        parents_df=parents_df, variants_df=variants_df
    )

    assert (cache_dir / "parents.parquet").exists()
    assert (cache_dir / "variants.parquet").exists()
    assert (cache_dir / "parents_all.parquet").exists()
    assert (cache_dir / "combined.parquet").exists()

    monkeypatch.setattr(api_mod, "_POSTFILL_ATTRIBUTE_CACHE_DIR", cache_dir)
    monkeypatch.setattr(api_mod, "_POSTFILL_TABLES_STATE", None)

    tables = api_mod._load_postfill_review_tables()
    assert tables is not None

    assert_frame_equal(
        tables.parents.select(parents_df.columns).sort(
            ["retailer", "parent_product_id"]
        ),
        parents_df.sort(["retailer", "parent_product_id"]),
    )
    assert_frame_equal(
        tables.variants.select(variants_df.columns).sort(["retailer", "variant_id"]),
        variants_df.sort(["retailer", "variant_id"]),
    )
    assert "also_blush" in tables.parents.columns
    assert "also_blush" in tables.variants.columns

    combined = tables.combined
    assert not combined.is_empty()
    assert set(combined.get_column("record_type").unique().to_list()) == {
        "parent",
        "variant",
    }


def test_api_loader_backfills_hybrid_columns_for_legacy_postfill_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import modules.pdp.api as api_mod

    cache_dir = tmp_path / "postfill_attribute_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "P1",
                "product_name": "Glow Blonzer Duo",
                "category_key": "bronzer",
                "description": "A 2 in 1 blush bronzer compact.",
            }
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "product_name": "Glow Blonzer Duo",
                "category_key": "bronzer",
                "variant_description": "Blonzer finish.",
            }
        ]
    )
    parents_df.write_parquet(cache_dir / "parents.parquet")
    variants_df.write_parquet(cache_dir / "variants.parquet")

    monkeypatch.setattr(api_mod, "_POSTFILL_ATTRIBUTE_CACHE_DIR", cache_dir)
    monkeypatch.setattr(api_mod, "_POSTFILL_TABLES_STATE", None)

    tables = api_mod._load_postfill_review_tables()
    assert tables is not None
    assert tables.parents.height == 1
    assert tables.variants.height == 1
    assert bool(tables.parents.get_column("also_blush").item()) is True
    assert bool(tables.variants.get_column("also_blush").item()) is True
    assert tables.parents.get_column("also_blush_source").item() == "brand_claim"


def test_get_tables_requires_postfill_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    import modules.pdp.api as api_mod

    monkeypatch.setattr(api_mod, "_load_postfill_review_tables", lambda: None)

    with pytest.raises(HTTPException) as exc_info:
        api_mod._get_tables()

    assert exc_info.value.status_code == 503
    assert "Post-fill attribute cache is required" in str(exc_info.value.detail)


def test_get_tables_for_coverage_uses_postfill_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.pdp.api as api_mod

    sentinel = api_mod.ReviewTables(
        parents=pl.DataFrame({"parent_product_id": ["P1"]}),
        variants=pl.DataFrame({"variant_id": ["V1"]}),
        combined=pl.DataFrame({"record_type": ["parent"]}),
        parents_all=pl.DataFrame({"parent_product_id": ["P1"]}),
    )
    monkeypatch.setattr(api_mod, "_get_tables", lambda: sentinel)
    monkeypatch.setattr(
        api_mod, "_overlay_stage_values_on_tables", lambda tables: tables
    )
    monkeypatch.setattr(api_mod, "_COVERAGE_TABLES_STATE", None)

    assert api_mod._get_tables_for_coverage() is sentinel


def test_format_stage_overlay_value_notax_without_detail_maps_to_na() -> None:
    import modules.pdp.api as api_mod

    assert (
        api_mod._format_stage_overlay_value(
            det_value="not in taxonomy",
            det_oov=None,
            llm_value=None,
            llm_oov=None,
        )
        == "N/A"
    )
    assert (
        api_mod._format_stage_overlay_value(
            det_value=None,
            det_oov=None,
            llm_value="not in taxonomy",
            llm_oov="glossy metallic finish",
        )
        == "not in taxonomy (glossy metallic finish)"
    )
    assert (
        api_mod._format_stage_overlay_value(
            det_value=None,
            det_oov=None,
            llm_value="not in taxonomy",
            llm_oov="n/a (not stated)",
        )
        == "N/A"
    )


def test_load_postfill_attribute_cache_falls_back_to_base_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import modules.pdp.attribute_mapping_core as mapping_mod

    shared_mapping_dir = (
        tmp_path / "shared_attribute_mapping" / "postfill_attribute_cache"
    )
    monkeypatch.setattr(mapping_mod, "POSTFILL_ATTRIBUTE_CACHE_DIR", shared_mapping_dir)
    monkeypatch.setattr(
        mapping_mod, "POSTFILL_PARENTS_OUTPUT", shared_mapping_dir / "parents.parquet"
    )
    monkeypatch.setattr(
        mapping_mod, "POSTFILL_VARIANTS_OUTPUT", shared_mapping_dir / "variants.parquet"
    )

    base_variants = pl.DataFrame(
        [
            {
                "retailer": "Sephora",
                "variant_id": "V1",
                "parent_product_id": "P1",
                "category_label": "Lipstick",
                "brand": "Brand X",
                "product_name": "Product A",
            }
        ]
    )
    base_parents = pl.DataFrame(
        [
            {
                "retailer": "Sephora",
                "parent_product_id": "P1",
                "brand": "Brand X",
                "product_name": "Product A",
                "pdp_url": "https://example.test/p1",
            }
        ]
    )
    monkeypatch.setattr(
        mapping_mod,
        "_load_base_attribute_cache_for_join",
        lambda: (
            mapping_mod._normalize_catalog_parents(base_parents),
            mapping_mod._normalize_catalog_variants(base_variants),
            [],
        ),
    )

    parents_df, variants_df, variant_paths, source = (
        mapping_mod._load_postfill_attribute_cache()
    )

    assert source == "base_cache"
    assert variant_paths == []
    assert parents_df.height == 1
    assert variants_df.height == 1
    assert parents_df.get_column("retailer").item() == "sephora"
    assert variants_df.get_column("retailer").item() == "sephora"
