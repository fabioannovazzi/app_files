from __future__ import annotations

from pathlib import Path

import polars as pl

from modules.pdp.attribute_cache_refresh import (
    refresh_pdp_attribute_cache_from_postfill,
)


def test_refresh_pdp_attribute_cache_from_postfill_preserves_base_delta(
    tmp_path: Path,
) -> None:
    postfill_dir = tmp_path / "postfill"
    cache_root = tmp_path / "pdp_attribute_cache"
    postfill_dir.mkdir()
    kiko_cache_dir = cache_root / "kiko"
    ulta_cache_dir = cache_root / "ulta"
    kiko_cache_dir.mkdir(parents=True)
    ulta_cache_dir.mkdir(parents=True)

    pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "parent_product_id": "k1",
                "category_key": "blush",
                "format": "pressed powder",
                "finish": "radiant",
            }
        ]
    ).write_parquet(postfill_dir / "parents.parquet")
    pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "variant_id": "kv1",
                "parent_product_id": "k1",
                "category_key": "blush",
                "format": "pressed powder",
            }
        ]
    ).write_parquet(postfill_dir / "variants.parquet")
    pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "parent_product_id": "k1",
                "category_key": "blush",
                "format": "pressed powder",
            }
        ]
    ).write_parquet(postfill_dir / "parents_all.parquet")

    pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "parent_product_id": "k1",
                "category_key": "blush",
                "form": None,
            },
            {
                "retailer": "kiko",
                "parent_product_id": "k2",
                "category_key": "lip_gloss",
                "form": "wand",
            },
        ]
    ).write_parquet(kiko_cache_dir / "parents.parquet")
    pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "variant_id": "kv2",
                "parent_product_id": "k2",
                "category_key": "lip_gloss",
                "form": "wand",
            }
        ]
    ).write_parquet(kiko_cache_dir / "variants.parquet")
    pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "parent_product_id": "k2",
                "category_key": "lip_gloss",
                "form": "wand",
            }
        ]
    ).write_parquet(kiko_cache_dir / "parents_all.parquet")
    pl.DataFrame(
        [{"retailer": "ulta", "parent_product_id": "u1", "category_key": "blush"}]
    ).write_parquet(ulta_cache_dir / "parents.parquet")

    written = refresh_pdp_attribute_cache_from_postfill(
        retailers=["kiko"],
        postfill_cache_dir=postfill_dir,
        attribute_cache_root=cache_root,
    )

    refreshed = pl.read_parquet(kiko_cache_dir / "parents.parquet").sort(
        "parent_product_id"
    )
    ulta = pl.read_parquet(ulta_cache_dir / "parents.parquet")

    assert kiko_cache_dir / "parents.parquet" in written
    assert refreshed.select(["parent_product_id", "form"]).to_dicts() == [
        {"parent_product_id": "k1", "form": "pressed powder"},
        {"parent_product_id": "k2", "form": "wand"},
    ]
    assert "format" not in refreshed.columns
    assert ulta.to_dicts() == [
        {"retailer": "ulta", "parent_product_id": "u1", "category_key": "blush"}
    ]


def test_refresh_pdp_attribute_cache_applies_kiko_filter_evidence(
    tmp_path: Path,
) -> None:
    postfill_dir = tmp_path / "postfill"
    cache_root = tmp_path / "pdp_attribute_cache"
    evidence_root = tmp_path / "retailer_filter_evidence"
    postfill_dir.mkdir()
    (evidence_root / "kiko").mkdir(parents=True)

    pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "parent_product_id": "k1",
                "category_key": "foundation",
                "finish": "natural",
            }
        ]
    ).write_parquet(postfill_dir / "parents.parquet")
    pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "variant_id": "kv1",
                "parent_product_id": "k1",
                "category_key": "foundation",
            }
        ]
    ).write_parquet(postfill_dir / "variants.parquet")
    pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "parent_product_id": "k1",
                "category_key": "foundation",
                "finish": "natural",
            }
        ]
    ).write_parquet(postfill_dir / "parents_all.parquet")
    pl.DataFrame(
        [
            {
                "retailer": "kiko",
                "parent_product_id": "k1",
                "category_key": "foundation",
                "filter_family": "finish",
                "filter_value": "matte",
            },
            {
                "retailer": "kiko",
                "parent_product_id": "k1",
                "category_key": "foundation",
                "filter_family": "coverage",
                "filter_value": "full",
            },
        ]
    ).write_parquet(evidence_root / "kiko" / "filter_observations.parquet")

    refresh_pdp_attribute_cache_from_postfill(
        retailers=["kiko"],
        postfill_cache_dir=postfill_dir,
        attribute_cache_root=cache_root,
        retailer_filter_evidence_root=evidence_root,
    )

    refreshed = pl.read_parquet(cache_root / "kiko" / "parents.parquet")

    assert refreshed.select(
        [
            "parent_product_id",
            "finish",
            "coverage",
            "our_finish",
            "kiko_filter_finish",
            "finish_authority_source",
        ]
    ).to_dicts() == [
        {
            "parent_product_id": "k1",
            "finish": "matte",
            "coverage": "full",
            "our_finish": "natural",
            "kiko_filter_finish": "matte",
            "finish_authority_source": "kiko_filter",
        }
    ]
