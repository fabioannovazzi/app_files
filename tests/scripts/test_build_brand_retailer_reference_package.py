from __future__ import annotations

import json
import zipfile
from pathlib import Path

import polars as pl
import pytest

from modules.utilities.utils import get_row_count
from scripts import build_brand_retailer_reference_package as reference_builder
from scripts.build_brand_retailer_reference_package import build_package


def _write_signal_csv(path: Path, rows: list[dict[str, object]]) -> None:
    pl.DataFrame(rows).write_csv(path)


def _write_valid_source_package_validation(package_dir: Path) -> None:
    (package_dir / "package_integrity.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "summary": {"failure_count": 0, "warning_count": 0},
            }
        ),
        encoding="utf-8",
    )
    source_snapshot_dir = package_dir / "source_snapshots"
    source_snapshot_dir.mkdir(parents=True, exist_ok=True)
    (source_snapshot_dir / "source_manifest.json").write_text(
        json.dumps(
            {
                "snapshots": {
                    "listing_observations": {"row_count": 1},
                    "filter_observations": {"row_count": 1},
                    "mapped_product_attributes": {"row_count": 1},
                }
            }
        ),
        encoding="utf-8",
    )


def _patch_database_catalogs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    owned_rows: list[dict[str, object]],
    retailer_rows: list[dict[str, object]],
    owned_variant_rows: list[dict[str, object]] | None = None,
    retailer_variant_rows: list[dict[str, object]] | None = None,
    owned_source: str = "kiko",
    retailer_source: str = "ulta",
) -> None:
    def _frame(rows: list[dict[str, object]] | None) -> pl.DataFrame:
        return pl.DataFrame(rows or [], infer_schema_length=None)

    def _source_rows(
        rows: list[dict[str, object]], source: str
    ) -> list[dict[str, object]]:
        filtered = [
            row
            for row in rows
            if str(row.get("retailer", source)).strip().lower() == source
        ]
        return filtered

    def fake_load_database_catalog_products(
        *,
        source_label: str,
        category_key: str,
        category_keys: object = None,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        del category_key, category_keys
        source = source_label.strip().lower()
        if source == owned_source:
            return (
                _frame(_source_rows(owned_rows, source)),
                _frame(_source_rows(owned_variant_rows or [], source)),
            )
        if source == retailer_source:
            return (
                _frame(_source_rows(retailer_rows, source)),
                _frame(_source_rows(retailer_variant_rows or [], source)),
            )
        return pl.DataFrame(), pl.DataFrame()

    monkeypatch.setattr(
        reference_builder,
        "_load_database_catalog_products",
        fake_load_database_catalog_products,
    )


def _write_minimal_retailer_signal_source(
    *,
    tmp_path: Path,
    retailer: str = "ulta",
    category_key: str = "blush",
) -> tuple[Path, Path]:
    innovation_package_dir = tmp_path / "launch" / category_key / retailer
    innovation_brief_path = (
        tmp_path / "briefs" / "launch" / category_key / f"{retailer}.md"
    )
    innovation_package_dir.mkdir(parents=True)
    innovation_brief_path.parent.mkdir(parents=True)
    (innovation_package_dir / "summary.json").write_text(
        json.dumps(
            {
                "retailer": retailer,
                "retailer_label": retailer.title(),
                "category_key": category_key,
                "category_label": category_key.replace("_", " "),
            }
        ),
        encoding="utf-8",
    )
    innovation_brief_path.write_text(
        "Use this source brief to interpret retailer signals.",
        encoding="utf-8",
    )
    _write_valid_source_package_validation(innovation_package_dir)
    _write_signal_csv(
        innovation_package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_key": "form=powder + finish=radiant",
                "bundle_label": "powder + radiant",
                "count_top_seller": 5,
                "count_other": 4,
                "top_seller_brand_count": 2,
                "other_brand_count": 2,
                "pct_top_seller": 0.5,
                "pct_other": 0.2,
                "delta": 0.3,
                "prevalence_ratio": 2.5,
            }
        ],
    )
    return innovation_package_dir, innovation_brief_path


def test_parse_bundle_key_canonicalizes_format_to_form() -> None:
    components = reference_builder._parse_bundle_key("format=stick + finish=matte")

    assert {"attribute": "form", "value": "stick"} in components
    assert {"attribute": "finish", "value": "matte"} in components
    assert all(component["attribute"] != "format" for component in components)


def test_product_component_matching_uses_one_hot_and_normalized_columns() -> None:
    row = {
        "product_name": "Oasis Snake-Embossed Leather Sneaker",
        "color_family": "White",
        "material__leather": True,
        "design_detail__logo_detail": "true",
    }

    assert reference_builder._product_matches_component(
        row, attribute="color", value="white"
    )
    assert reference_builder._product_matches_component(
        row, attribute="material", value="leather"
    )
    assert reference_builder._product_matches_component(
        row, attribute="design detail", value="logo detail"
    )


def test_add_standard_columns_derives_text_from_one_hot_attributes() -> None:
    products = pl.DataFrame(
        [
            {
                "parent_product_id": "owned-1",
                "product_name": "Leather Sneaker",
                "brand": "Vince",
                "category_key": "low_top_sneakers",
                "material__leather": True,
                "material__suede": False,
                "design_detail__logo_detail": True,
            }
        ]
    )

    standardized = reference_builder._add_standard_columns(
        products,
        category_key="low_top_sneakers",
        source_label="vince",
        product_scope="manufacturer_catalog",
    )

    assert standardized.item(0, "material") == "leather"
    assert standardized.item(0, "design_detail") == "logo detail"


def test_build_package_requires_retailer_signal_brief(tmp_path: Path) -> None:
    innovation_package_dir = tmp_path / "launch" / "eyeshadow" / "ulta"
    output_root = tmp_path / "packages"
    stale_output_dir = output_root / "eyeshadow" / "ulta" / "kiko"
    stale_zip_path = output_root / "eyeshadow" / "ulta" / "eyeshadow_ulta_kiko.zip"
    stale_output_dir.mkdir(parents=True)
    stale_output_dir.joinpath("stale.csv").write_text("old", encoding="utf-8")
    stale_zip_path.write_text("old zip", encoding="utf-8")
    innovation_package_dir.mkdir(parents=True)
    (innovation_package_dir / "summary.json").write_text(
        json.dumps(
            {
                "retailer": "ulta",
                "retailer_label": "Ulta",
                "category_key": "eyeshadow",
                "category_label": "eyeshadow",
            }
        ),
        encoding="utf-8",
    )
    _write_signal_csv(
        innovation_package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_key": "form=stick + finish=shimmer",
                "bundle_label": "stick + shimmer",
                "count_top_seller": 5,
                "count_other": 4,
                "top_seller_brand_count": 2,
                "other_brand_count": 2,
                "pct_top_seller": 0.5,
                "pct_other": 0.2,
                "delta": 0.3,
                "prevalence_ratio": 2.5,
            }
        ],
    )

    missing_brief = tmp_path / "briefs" / "launch" / "eyeshadow" / "ulta.md"

    with pytest.raises(FileNotFoundError, match="requires an existing retailer signal"):
        build_package(
            brand_source_retailer="kiko",
            brand_name="KIKO Milano",
            category_key="eyeshadow",
            retailer="ulta",
            innovation_package_dir=innovation_package_dir,
            innovation_brief_path=missing_brief,
            output_root=output_root,
            retailer_live_check=False,
        )

    assert not stale_output_dir.exists()
    assert not stale_zip_path.exists()


def test_source_package_categories_discovers_retailer_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages" / "launch"
    monkeypatch.setattr(reference_builder, "DEFAULT_INNOVATION_ROOT", package_root)
    (package_root / "blush" / "ulta").mkdir(parents=True)
    (package_root / "lip_gloss" / "ulta").mkdir(parents=True)
    (package_root / "sneakers" / "saksfifthavenue").mkdir(parents=True)

    categories = reference_builder._source_package_categories("ulta")

    assert categories == ["blush", "lip_gloss"]


def test_source_package_categories_falls_back_to_legacy_retailer_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages" / "launch"
    monkeypatch.setattr(reference_builder, "DEFAULT_INNOVATION_ROOT", package_root)
    (package_root / "ulta" / "blush").mkdir(parents=True)
    (package_root / "ulta" / "lip_gloss").mkdir(parents=True)
    (package_root / "saksfifthavenue" / "sneakers").mkdir(parents=True)

    categories = reference_builder._source_package_categories("ulta")

    assert categories == ["blush", "lip_gloss"]


def test_innovation_source_paths_prefer_new_layout_but_accept_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages" / "launch"
    brief_root = tmp_path / "briefs" / "launch"
    monkeypatch.setattr(reference_builder, "DEFAULT_INNOVATION_ROOT", package_root)
    monkeypatch.setattr(reference_builder, "DEFAULT_BRIEF_ROOT", brief_root)
    legacy_package_dir = package_root / "ulta" / "blush"
    legacy_brief_path = brief_root / "ulta" / "blush.md"
    legacy_package_dir.mkdir(parents=True)
    legacy_brief_path.parent.mkdir(parents=True)
    legacy_brief_path.write_text("legacy brief", encoding="utf-8")

    assert reference_builder._innovation_package_dir("ulta", "blush") == (
        legacy_package_dir
    )
    assert reference_builder._innovation_brief_path("ulta", "blush") == (
        legacy_brief_path
    )

    new_package_dir = package_root / "blush" / "ulta"
    new_brief_path = brief_root / "blush" / "ulta.md"
    new_package_dir.mkdir(parents=True)
    new_brief_path.parent.mkdir(parents=True)
    new_brief_path.write_text("new brief", encoding="utf-8")

    assert reference_builder._innovation_package_dir("ulta", "blush") == (
        new_package_dir
    )
    assert reference_builder._innovation_brief_path("ulta", "blush") == new_brief_path


def test_selected_category_keys_keeps_categories_as_tokens() -> None:
    args = reference_builder.argparse.Namespace(
        categories=None,
        category_groups=["blush", "bronzer"],
    )

    categories = reference_builder._selected_category_keys(args)

    assert categories == ["blush", "bronzer"]


def test_default_output_root_matches_brand_fit_package_family() -> None:
    assert reference_builder.DEFAULT_OUTPUT_ROOT == Path(
        "data/pdp/reports/packages/brand_fit"
    )


def test_load_owned_products_filters_aggregate_cache_to_source_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_database_catalogs(
        monkeypatch,
        owned_source="tikicat",
        owned_rows=[
            {
                "retailer": "tikicat",
                "parent_product_id": "tiki-1",
                "category_key": "wet_cat_food",
                "product_name": "Tiki Cat Luau Chicken",
                "brand": "Tiki Cat",
            },
            {
                "retailer": "chewy",
                "parent_product_id": "chewy-1",
                "category_key": "wet_cat_food",
                "product_name": "Other Wet Food",
                "brand": "Other",
            },
        ],
        owned_variant_rows=[
            {
                "retailer": "tikicat",
                "parent_product_id": "tiki-1",
                "variant_id": "tiki-1-v1",
                "category_key": "wet_cat_food",
            },
            {
                "retailer": "chewy",
                "parent_product_id": "chewy-1",
                "variant_id": "chewy-1-v1",
                "category_key": "wet_cat_food",
            },
        ],
        retailer_rows=[],
    )

    owned = reference_builder._load_owned_products(
        category_key="wet_cat_food",
        source_label="tikicat",
    )

    assert owned["parent_product_id"].to_list() == ["tiki-1"]
    assert owned.item(0, "variant_count") == 1


def test_retailer_brand_listing_url_uses_ulta_loreal_slug() -> None:
    url = reference_builder._retailer_brand_listing_url("ulta", "L'Oreal Paris")

    assert url == "https://www.ulta.com/brand/loreal"


def test_retailer_brand_listing_url_uses_ulta_category_filter() -> None:
    url = reference_builder._retailer_brand_listing_url(
        "ulta",
        "L'Oreal Paris",
        category_key="blush",
    )

    assert url == "https://www.ulta.com/brand/loreal?category=makeup%2Cface%2Cblush"


def test_brand_filter_repairs_loreal_mojibake() -> None:
    products = pl.DataFrame(
        [
            {
                "product_name": "Infallible Blush",
                "brand": "L'Or\u00c3\u00a9al",
                "category_key": "blush",
            },
            {
                "product_name": "Silky Tint",
                "brand": "P\u00dcR",
                "category_key": "blush",
            },
        ]
    )

    filtered = reference_builder._filter_brand_if_possible(
        products,
        "L'Oreal Paris",
    )

    assert filtered["product_name"].to_list() == ["Infallible Blush"]


def test_brand_filter_treats_purina_as_portfolio_brand() -> None:
    products = pl.DataFrame(
        [
            {
                "product_name": "Medleys Seafood Collection",
                "brand": "Fancy Feast",
                "category_key": "wet_cat_food",
            },
            {
                "product_name": "Shreds Turkey and Cheese Dinner",
                "brand": "Friskies",
                "category_key": "wet_cat_food",
            },
            {
                "product_name": "Complete Essentials Chicken Entree",
                "brand": "Purina Pro Plan",
                "category_key": "wet_cat_food",
            },
            {
                "product_name": "Tastefuls Chicken Entree",
                "brand": "Blue Buffalo",
                "category_key": "wet_cat_food",
            },
        ]
    )

    filtered = reference_builder._filter_brand_if_possible(products, "Purina")

    assert filtered["product_name"].to_list() == [
        "Medleys Seafood Collection",
        "Shreds Turkey and Cheese Dinner",
        "Complete Essentials Chicken Entree",
    ]


def test_brand_stripped_product_key_strips_purina_portfolio_alias() -> None:
    stripped_key = reference_builder._brand_stripped_product_key(
        "Fancy Feast Classic Pate Chicken Feast Wet Cat Food",
        "Purina",
    )

    assert stripped_key == "classic pate chicken feast wet cat food"


def test_parse_ulta_brand_page_products_strips_loreal_alias() -> None:
    live_html = """
    <a href="https://www.ulta.com/p/infallible-24h-fresh-wear-soft-matte-blush-pimprod2039299">
      L'Or\u00e9al Infallible 24H Fresh Wear Soft Matte Blush
    </a>
    """

    products = reference_builder._parse_ulta_brand_page_products(
        live_html,
        brand_name="L'Oreal Paris",
    )
    live_product = reference_builder._live_product_match_for_owned(
        {
            "product_key": "infallible up to 24h fresh wear soft matte blush",
            "product_name": "Infallible Up to 24H Fresh Wear Soft Matte Blush",
            "parent_product_id": "infallible-fresh-wear-blush",
            "pdp_url": (
                "https://www.lorealparisusa.com/makeup/face/blush/"
                "infallible-fresh-wear-blush"
            ),
        },
        products,
    )

    assert "infallible 24h fresh wear soft matte blush" in products
    assert (
        products["infallible 24h fresh wear soft matte blush"]["product_name"]
        == "Infallible 24H Fresh Wear Soft Matte Blush"
    )
    assert live_product is not None
    assert live_product["pdp_url"].endswith("pimprod2039299")
    assert reference_builder._product_key_matches_any(
        "infallible up to 24h fresh wear soft matte blush",
        {"infallible 24h fresh wear soft matte blush"},
    )


def test_live_presence_match_accepts_loreal_retailer_name_expansion() -> None:
    live_html = """
    <a href="/p/true-match-super-blendable-blush-VP10730?sku=2114143">
      L'Or\u00e9al True Match Super Blendable Blush
    </a>
    """
    products = reference_builder._parse_ulta_brand_page_products(
        live_html,
        brand_name="L'Oreal Paris",
    )

    live_product = reference_builder._live_product_match_for_owned(
        {
            "product_key": "true match blush",
            "product_name": "True Match Blush",
            "parent_product_id": "true-match-blush",
            "pdp_url": (
                "https://www.lorealparisusa.com/makeup/face/blush/" "true-match-blush"
            ),
        },
        products,
    )

    assert live_product is not None
    assert live_product["product_name"] == "True Match Super Blendable Blush"


def test_live_presence_match_accepts_loreal_bronzer_slug_expansion() -> None:
    live_html = """
    <a href="/p/lumi-bronze-le-stick-soleil-bronzer-pimprod2055936?sku=2648166">
      L'Or\u00e9al Lumi Bronze Le Stick Soleil Bronzer
    </a>
    """
    products = reference_builder._parse_ulta_brand_page_products(
        live_html,
        brand_name="L'Oreal Paris",
    )

    live_product = reference_builder._live_product_match_for_owned(
        {
            "product_key": "lumi lumi bronze le stick soleil face bronzing stick",
            "product_name": "Lumi Lumi Bronze Le Stick Soleil Face Bronzing Stick",
            "parent_product_id": "lumi-bronze-le-stick-soleil",
            "pdp_url": (
                "https://www.lorealparisusa.com/makeup/face/bronzer/"
                "lumi-bronze-le-stick-soleil"
            ),
        },
        products,
    )

    assert "lumi bronze le stick soleil bronzer" in products
    assert live_product is not None
    assert live_product["pdp_url"] == (
        "https://www.ulta.com/p/lumi-bronze-le-stick-soleil-bronzer-pimprod2055936?sku=2648166"
    )


def test_generic_anchor_matching_allows_loreal_name_variant() -> None:
    owned = reference_builder._add_standard_columns(
        pl.DataFrame(
            [
                {
                    "parent_product_id": "owned-bronzer",
                    "product_name": "Infallible Up to 24H Fresh Wear Soft Matte Bronzer",
                    "brand": "L'Oreal Paris",
                    "category_key": "bronzer",
                    "pdp_url": "https://brand.example/bronzer",
                    "variant_count": 1,
                    "image_file": "images/manufacturer_catalog/owned-bronzer.webp",
                }
            ]
        ),
        category_key="bronzer",
        source_label="lorealparis",
        product_scope="manufacturer_catalog",
    )
    retailer_products = reference_builder._add_standard_columns(
        pl.DataFrame(
            [
                {
                    "parent_product_id": "pimprod2032578",
                    "product_name": "Infallible 24H Fresh Wear Soft Matte Bronzer",
                    "brand": "L'Or\u00c3\u00a9al",
                    "category_key": "bronzer",
                    "pdp_url": "https://www.ulta.com/p/infallible-24h-fresh-wear-soft-matte-bronzer-pimprod2032578",
                    "variant_count": 1,
                }
            ]
        ),
        category_key="bronzer",
        source_label="ulta",
        product_scope="brand_at_retailer",
    )

    anchors = reference_builder._build_anchors(
        owned,
        retailer_products,
        brand_source_retailer="lorealparis",
        retailer="ulta",
        category_key="bronzer",
    )

    assert anchors.item(0, "anchor_status") == "matched_owned_product"
    assert anchors.item(0, "owned_parent_product_id") == "owned-bronzer"
    assert anchors.item(0, "product_identity_match_method") == "name_token_sort_fuzzy"


def test_tikicat_chewy_anchor_matching_uses_line_and_recipe() -> None:
    owned = pl.DataFrame(
        [
            {
                "source": "tikicat",
                "product_scope": "manufacturer_catalog",
                "product_name": "Chicken & Egg Pate",
                "product_key": reference_builder._normalize_product_key(
                    "Chicken & Egg Pate"
                ),
                "parent_product_id": "chicken-egg-pate",
                "pdp_url": (
                    "https://tikipets.com/product/tiki-cat/tiki-cat-wet-food/"
                    "shredded-cat/luau/chicken-egg-pate/"
                ),
                "brand": "Tiki Cat",
                "category_key": "wet_cat_food",
                "category_path": ["Pet", "Cat", "Wet Cat Food", "Minced", "Luau"],
                "food_texture": "Pate",
                "lifestage": "Adult",
                "variant_count": 1,
                "image_file": "images/manufacturer_catalog/chicken-egg-pate.png",
            },
            {
                "source": "tikicat",
                "product_scope": "manufacturer_catalog",
                "product_name": "Chicken & Quail Egg Recipe in Chicken Broth",
                "product_key": reference_builder._normalize_product_key(
                    "Chicken & Quail Egg Recipe in Chicken Broth"
                ),
                "parent_product_id": "pate-chicken-quail-egg-recipe-in-broth",
                "pdp_url": (
                    "https://tikipets.com/product/tiki-cat/tiki-cat-wet-food/"
                    "shredded-cat/after-dark/pate-chicken-quail-egg-recipe-in-broth/"
                ),
                "brand": "Tiki Cat",
                "category_key": "wet_cat_food",
                "category_path": [
                    "Pet",
                    "Cat",
                    "Wet Cat Food",
                    "Minced",
                    "After Dark",
                ],
                "food_texture": "Pate",
                "lifestage": "Adult",
                "variant_count": 1,
                "image_file": (
                    "images/manufacturer_catalog/"
                    "pate-chicken-quail-egg-recipe-in-broth.png"
                ),
            },
        ]
    )
    retailer_products = pl.DataFrame(
        [
            {
                "source": "chewy",
                "product_scope": "brand_at_retailer",
                "product_name": (
                    "Tiki Cat After Dark Pate+ Chicken & Quail Egg "
                    "Grain-Free Wet Cat Food, 2.8-oz can, case of 12"
                ),
                "product_key": reference_builder._normalize_product_key(
                    "Tiki Cat After Dark Pate+ Chicken & Quail Egg "
                    "Grain-Free Wet Cat Food, 2.8-oz can, case of 12"
                ),
                "parent_product_id": "1043602",
                "pdp_url": "https://www.chewy.com/tiki-cat-after-dark-pate/dp/1043602",
                "brand": "Tiki Cat",
                "category_key": "wet_cat_food",
                "food_texture": "pate",
                "lifestage": "adult",
                "variant_count": 1,
                "image_file": None,
            }
        ]
    )

    anchors = reference_builder._build_anchors(
        owned,
        retailer_products,
        brand_source_retailer="tikicat",
        retailer="chewy",
        category_key="wet_cat_food",
    )
    missing = reference_builder._build_missing_owned(
        owned,
        retailer_products,
        anchors=anchors,
    )

    assert anchors.item(0, "anchor_status") == "matched_owned_product"
    assert anchors.item(0, "owned_parent_product_id") == (
        "pate-chicken-quail-egg-recipe-in-broth"
    )
    assert anchors.item(0, "product_identity_match_method") == (
        "tikicat_chewy_name_line_fuzzy"
    )
    assert missing.select("parent_product_id").to_series().to_list() == [
        "chicken-egg-pate"
    ]


def test_anchor_signal_fit_flags_current_anchor_without_signal_match() -> None:
    anchors = pl.DataFrame(
        [
            {
                "source": "ulta",
                "product_scope": "brand_at_retailer",
                "product_name": "Lumi Blush",
                "product_key": "lumi blush",
                "parent_product_id": "pimprod1",
                "pdp_url": "https://ulta.example/lumi-blush",
                "brand": "L'Oreal Paris",
                "category_key": "blush",
                "variant_count": 4,
                "image_file": None,
                "anchor_status": "matched_owned_product",
            }
        ]
    )

    fit = reference_builder._build_anchor_signal_fit(anchors, pl.DataFrame())

    assert fit.item(0, "matched_signal_count") == 0
    assert fit.item(0, "fit_status") == (
        "current_anchor_not_explained_by_selected_retailer_signals"
    )
    assert "Do not infer weak commercial relevance" in fit.item(0, "commercial_read")


def test_anchor_signal_fit_preserves_top_seller_anchor_without_signal_match() -> None:
    anchors = pl.DataFrame(
        [
            {
                "source": "ulta",
                "product_scope": "brand_at_retailer",
                "product_name": "Lumi Blush",
                "product_key": "lumi blush",
                "parent_product_id": "pimprod1",
                "pdp_url": "https://ulta.example/lumi-blush",
                "brand": "L'Oreal Paris",
                "category_key": "blush",
                "variant_count": 4,
                "image_file": None,
                "anchor_status": "matched_owned_product",
            }
        ]
    )

    fit = reference_builder._build_anchor_signal_fit(
        anchors,
        pl.DataFrame(),
        top_seller_lookup={
            "lumi blush": {
                "pareto_bucket": "A",
                "pareto_rank": 1,
                "sales_share": 0.2,
                "top_seller_status": "top_seller",
            }
        },
    )

    assert fit.item(0, "top_seller_sort_present")
    assert fit.item(0, "fit_status") == (
        "top_seller_anchor_not_explained_by_selected_retailer_signals"
    )
    assert "commercially important current evidence" in fit.item(0, "commercial_read")


def test_build_all_packages_builds_selected_categories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_build_package(
        *,
        category_key: str,
        output_root: Path,
        brand_source_retailer: str,
        retailer: str,
        **_kwargs: object,
    ) -> Path:
        calls.append(category_key)
        return output_root / category_key / retailer / brand_source_retailer

    monkeypatch.setattr(reference_builder, "build_package", fake_build_package)

    summary = reference_builder.build_all_packages(
        brand_source_retailer="kiko",
        brand_name="KIKO Milano",
        retailer="ulta",
        category_keys=["blush", "lip_gloss"],
        output_root=tmp_path / "packages",
    ).sort("category_key")

    assert calls == ["blush", "lip_gloss"]
    assert summary.get_column("status").to_list() == ["built", "built"]
    assert (
        tmp_path / "packages" / "_bulk_rebuild_summary" / "ulta" / "kiko.csv"
    ).exists()


def test_build_all_packages_skips_missing_source_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_build_package(
        *,
        category_key: str,
        **_kwargs: object,
    ) -> Path:
        if category_key == "missing_brief":
            raise FileNotFoundError("missing retailer brief")
        return tmp_path / "packages" / category_key / "ulta" / "kiko"

    monkeypatch.setattr(reference_builder, "build_package", fake_build_package)

    summary = reference_builder.build_all_packages(
        brand_source_retailer="kiko",
        brand_name="KIKO Milano",
        retailer="ulta",
        category_keys=["blush", "missing_brief"],
        output_root=tmp_path / "packages",
    ).sort("category_key")

    assert summary.get_column("status").to_list() == ["built", "skipped"]
    assert "missing retailer brief" in str(
        summary.filter(pl.col("status") == "skipped").item(0, "error")
    )


def test_build_package_enriches_current_anchors_from_launch_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    innovation_package_dir, innovation_brief_path = (
        _write_minimal_retailer_signal_source(
            tmp_path=tmp_path,
            category_key="blush",
        )
    )
    _write_signal_csv(
        innovation_package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_key": "coverage=buildable + form=pressed powder",
                "bundle_label": "Buildable + Pressed powder",
                "count_top_seller": 25,
                "count_other": 54,
                "top_seller_brand_count": 19,
                "other_brand_count": 30,
                "pct_top_seller": 0.258,
                "pct_other": 0.172,
                "delta": 0.086,
                "prevalence_ratio": 1.5,
            }
        ],
    )
    pl.DataFrame(
        [
            {
                "parent_product_id": "pimprod2032252",
                "product_name": "KIKO Milano Unlimited Blush",
                "brand": "KIKO Milano",
                "category_key": "blush",
                "pdp_url": "https://www.ulta.com/p/unlimited-blush-pimprod2032252",
                "resolved_form": "Pressed powder",
                "resolved_coverage": "Buildable",
                "resolved_finish": "Matte | Luminous",
                "skin benefits": "Brightening",
            }
        ]
    ).write_csv(innovation_package_dir / "product_filter_matrix.csv")

    manufacturer_cli_dir = tmp_path / "cli" / "kiko_blush"
    manufacturer_images_dir = manufacturer_cli_dir / "images"
    output_root = tmp_path / "packages"
    manufacturer_images_dir.mkdir(parents=True)
    (manufacturer_images_dir / "owned-unlimited_hero.webp").write_bytes(
        b"owned-unlimited-image"
    )

    owned_rows = [
        {
            "parent_product_id": "owned-unlimited",
            "product_name": "Unlimited Blush",
            "brand": "KIKO Milano",
            "category_key": "blush",
            "pdp_url": "https://www.kikocosmetics.com/en-us/p/unlimited-blush/",
            "form": "pressed powder",
            "coverage": "buildable",
            "finish": "metallic",
        }
    ]
    retailer_rows = [
        {
            "parent_product_id": "pimprod2032252",
            "product_name": "Unlimited Blush",
            "brand": "KIKO Milano",
            "category_key": "blush",
            "pdp_url": "https://www.ulta.com/p/unlimited-blush-pimprod2032252",
            "form": None,
            "coverage": "buildable",
            "finish": "metallic",
        }
    ]
    _patch_database_catalogs(
        monkeypatch,
        owned_rows=owned_rows,
        retailer_rows=retailer_rows,
    )

    output_dir = build_package(
        brand_source_retailer="kiko",
        brand_name="KIKO Milano",
        category_key="blush",
        retailer="ulta",
        innovation_package_dir=innovation_package_dir,
        innovation_brief_path=innovation_brief_path,
        owned_cli_dir=manufacturer_cli_dir,
        output_root=output_root,
        retailer_live_check=False,
    )

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    package_integrity = json.loads(
        (output_dir / "package_integrity.json").read_text(encoding="utf-8")
    )
    package_warnings = json.loads(
        (output_dir / "package_warnings.json").read_text(encoding="utf-8")
    )
    anchors = pl.read_csv(output_dir / "retailer_brand_anchors.csv")
    anchor_matches = pl.read_csv(output_dir / "brand_at_retailer_bundle_matches.csv")
    anchor_signal_fit = pl.read_csv(output_dir / "retailer_brand_anchor_signal_fit.csv")

    assert summary["sources"]["retailer_product_attribute_source_files"] == [
        "product_filter_matrix.csv"
    ]
    assert summary["package_integrity"]["status"] == "pass"
    assert summary["counts"]["package_integrity_failures"] == 0
    assert package_integrity["status"] == "pass"
    assert package_warnings["status"] == "pass_with_warnings"
    assert summary["package_warning_count"] == 2
    assert {warning["code"] for warning in package_warnings["warnings"]} == {
        "retailer_live_check_disabled",
        "current_brand_review_evidence_unavailable",
    }
    assert (
        package_integrity["summary"][
            "recovered_anchor_bundle_matches_after_attribute_enrichment"
        ]
        == 1
    )
    assert anchors.item(0, "form") == "Pressed powder"
    assert anchors.item(0, "coverage") == "Buildable"
    assert anchors.item(0, "finish") == "Matte | Luminous"
    assert anchors.item(0, "skin benefits") == "Brightening"
    assert anchor_matches.item(0, "bundle_label") == "Buildable + Pressed powder"
    assert anchor_signal_fit.item(0, "matched_signal_labels") == (
        "Buildable + Pressed powder"
    )


def test_build_package_creates_bundle_handoff_for_pro(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    innovation_package_dir = tmp_path / "launch" / "lipstick" / "ulta"
    innovation_brief_path = tmp_path / "briefs" / "launch" / "lipstick" / "ulta.md"
    innovation_images_dir = innovation_package_dir / "images"
    manufacturer_cli_dir = tmp_path / "cli" / "kiko_lipstick"
    manufacturer_images_dir = manufacturer_cli_dir / "images"
    output_root = tmp_path / "packages"

    innovation_images_dir.mkdir(parents=True)
    manufacturer_images_dir.mkdir(parents=True)
    (innovation_images_dir / "source-example.png").write_bytes(b"source-image")
    (innovation_images_dir / "source-unused.png").write_bytes(b"unused-image")
    (manufacturer_images_dir / "owned-1_hero.webp").write_bytes(b"owned-1-image")
    (manufacturer_images_dir / "owned-2_hero.webp").write_bytes(b"owned-2-image")
    (manufacturer_images_dir / "owned-3_hero.webp").write_bytes(b"owned-3-image")

    (innovation_package_dir / "summary.json").write_text(
        json.dumps(
            {
                "retailer": "ulta",
                "retailer_label": "Ulta",
                "category_key": "lipstick",
                "category_label": "lipstick",
                "review_theme_cohort_comparison_rows": 1,
                "top_seller_review_validation_rows": 1,
                "bundle_review_validation_rows": 1,
            }
        ),
        encoding="utf-8",
    )
    _write_valid_source_package_validation(innovation_package_dir)
    innovation_brief_path.parent.mkdir(parents=True)
    innovation_brief_path.write_text(
        (
            "Color rows are shade-range architecture, not standalone product "
            "innovation. Stick format is a legacy wording. Stick formats are "
            "legacy wording too."
        ),
        encoding="utf-8",
    )
    pl.DataFrame(
        [
            {
                "parent_product_id": "source-1",
                "product_name": "Source Matte Full Lipstick",
                "image_file": "images/source-example.png",
                "image_available": True,
                "image_source": "local_image_path",
                "inspect_rule": "inspect",
            },
            {
                "parent_product_id": "source-2",
                "product_name": "Unreferenced Source Product",
                "image_file": "images/source-unused.png",
                "image_available": True,
                "image_source": "local_image_path",
                "inspect_rule": "inspect",
            },
        ]
    ).write_csv(innovation_package_dir / "image_index.csv")
    _write_signal_csv(
        innovation_package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_key": "finish=matte + coverage=full coverage",
                "bundle_label": "matte + full coverage",
                "count_top_seller": 8,
                "count_other": 10,
                "top_seller_brand_count": 3,
                "other_brand_count": 5,
                "pct_top_seller": 0.4,
                "pct_other": 0.1,
                "delta": 0.3,
                "prevalence_ratio": 4.0,
                "top_seller_sales_share_sum": 0.2,
                "top_seller_brands": "Brand A | Brand B | Brand C",
                "top_seller_example_products": "Source Matte Full Lipstick",
                "top_seller_top_pareto_products": "Source Matte Full Lipstick",
            }
        ],
    )
    _write_signal_csv(
        innovation_package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_key": "form=stick + color lips=pink",
                "bundle_label": "stick + pink",
                "count_recent": 6,
                "count_rest": 3,
                "recent_brand_count": 3,
                "rest_brand_count": 2,
                "pct_recent": 0.3,
                "pct_rest": 0.08,
                "delta": 0.22,
                "prevalence_ratio": 3.75,
                "recent_sales_share_sum": 0.08,
                "recent_brands": "Brand D | Brand E | Brand F",
                "recent_example_products": "Source Stick Pink Lipstick",
                "recent_top_pareto_products": "Source Stick Pink Lipstick",
                "rank_weighted_gross_visibility_share": 0.27,
                "rank_weighted_incremental_visibility_share": 0.09,
                "rank_weighted_visibility_density_index": 1.2,
                "rank_weighted_visibility_alpha_scenarios": 3,
                "rank_weighted_visibility_best_shelf_rank": 2,
                "rank_weighted_visibility_gross_sku_count": 10,
                "rank_weighted_visibility_incremental_sku_count": 5,
                "rank_weighted_visibility_gross_brand_count": 4,
                "rank_weighted_visibility_incremental_brand_count": 3,
                "rank_weighted_visibility_top_products": "Source Stick Pink Lipstick (#4)",
                "rank_weighted_visibility_top_brands": "Brand D (40.0%) | Brand E (30.0%)",
            }
        ],
    )
    _write_signal_csv(
        innovation_package_dir / "web_shelf_selected_shelves.csv",
        [
            {
                "alpha": 1.0,
                "shelf_rank": 1,
                "bundle_key": "form=stick + color lips=pink",
                "bundle_size": 2,
                "attributes": "form=stick | color lips=pink",
                "gross_weight_share": 0.31,
                "incremental_weight_share": 0.12,
                "cumulative_weight_share": 0.12,
                "gross_sku_count": 12,
                "incremental_sku_count": 6,
                "gross_sku_share": 0.24,
                "incremental_sku_share": 0.12,
                "density_index": 1.29,
                "gross_brand_count": 4,
                "incremental_brand_count": 3,
                "top_products": "Source Stick Pink Lipstick (#4)",
                "top_brands": "Brand D (40.0%) | Brand E (30.0%)",
            }
        ],
    )
    _write_signal_csv(
        innovation_package_dir / "web_shelf_candidate_shelves.csv",
        [
            {
                "alpha": 1.0,
                "bundle_key": "form=stick + color lips=pink",
                "bundle_size": 2,
                "gross_weight_share": 0.31,
                "incremental_weight_share": 0.12,
                "density_index": 1.29,
                "gross_sku_count": 12,
                "incremental_sku_count": 6,
                "gross_brand_count": 4,
                "incremental_brand_count": 3,
            }
        ],
    )
    _write_signal_csv(
        innovation_package_dir / "web_shelf_robustness_summary.csv",
        [
            {
                "bundle_key": "form=stick + color lips=pink",
                "times_selected": 3,
                "best_shelf_rank": 1,
                "average_shelf_rank": 1.3,
                "average_gross_weight_share": 0.3,
                "average_incremental_weight_share": 0.11,
                "average_density_index": 1.25,
                "selected_under_alpha_0_0": True,
                "selected_under_alpha_0_7": True,
                "selected_under_alpha_1_0": True,
                "selected_under_alpha_1_2": False,
            }
        ],
    )
    _write_signal_csv(
        innovation_package_dir / "web_shelf_product_assignments.csv",
        [
            {
                "alpha": 1.0,
                "shelf_rank": 1,
                "bundle_key": "form=stick + color lips=pink",
                "parent_product_id": "source-1",
                "product_name": "Source Stick Pink Lipstick",
                "rank_weight": 0.82,
                "selected_incrementally": True,
            }
        ],
    )
    _write_signal_csv(
        innovation_package_dir / "web_shelf_third_attribute_refinements.csv",
        [
            {
                "alpha": 1.0,
                "base_bundle_key": "form=stick + color lips=pink",
                "third_attribute": "finish",
                "third_value": "matte",
                "candidate_bundle_key": ("form=stick + color lips=pink + finish=matte"),
                "incremental_weight_share": 0.04,
            }
        ],
    )
    _write_signal_csv(
        innovation_package_dir / "review_theme_cohort_comparison.csv",
        [
            {
                "comparison_key": "top_seller_vs_other",
                "theme_id": "theme_blendability",
                "theme_family": "application",
                "theme_label": "Blendability",
                "experience_signal_class": "positive_over_index",
                "experience_signal_summary": (
                    "Blendability over-indexes among top-seller reviews."
                ),
                "focus_product_count": 8,
                "baseline_product_count": 12,
            }
        ],
    )
    _write_signal_csv(
        innovation_package_dir / "top_seller_review_validation.csv",
        [
            {
                "bundle_key": "finish=matte + coverage=full coverage",
                "product_name": "Source Matte Full Lipstick",
                "review_headline": "Smooth color",
                "review_comment": "Applies evenly.",
            }
        ],
    )
    _write_signal_csv(
        innovation_package_dir / "bundle_review_validation.csv",
        [
            {
                "bundle_key": "form=stick + color lips=pink",
                "product_name": "Source Stick Pink Lipstick",
                "review_headline": "Easy stick",
                "review_comment": "Quick to apply.",
            }
        ],
    )
    pl.DataFrame(
        [
            {
                "listing_identity": "retailer-1",
                "parent_product_id": "retailer-1",
                "brand": "KIKO Milano",
                "product_name": "KIKO Milano Matte Full Lipstick",
                "pdp_url": "https://ulta.example/retailer-1",
                "rating": 4.7,
                "review_count": 128,
                "review_snippet_count": 4,
                "reviews_positive_headline": "Color lasts",
                "reviews_positive_comment": "Shoppers praise the color payoff.",
                "reviews_negative_headline": "Can feel dry",
                "reviews_negative_comment": "Some reviews mention dry wear.",
                "review_1_headline": "Great pigment",
                "review_1_comment": "Comfortable color with strong payoff.",
                "review_1_rating": 5.0,
                "review_1_created_date": "2025-01-02",
                "review_2_headline": "A little dry",
                "review_2_comment": "Pretty shade, but I need balm first.",
                "review_2_rating": 3.0,
                "review_2_created_date": "2025-01-03",
            }
        ]
    ).write_csv(innovation_package_dir / "product_filter_matrix.csv")

    owned_rows = [
        {
            "parent_product_id": "owned-1",
            "product_name": "Matte Full Lipstick",
            "brand": "KIKO Milano",
            "category_key": "lipstick",
            "pdp_url": "https://example.test/owned-1",
            "form": "bullet lipstick",
            "finish": "matte",
            "coverage": "full",
            "color family": "red",
        },
        {
            "parent_product_id": "owned-2",
            "product_name": "Pink Stylo",
            "brand": "KIKO Milano",
            "category_key": "lipstick",
            "pdp_url": "https://example.test/owned-2",
            "form": "lip crayon/pencil",
            "finish": "satin",
            "coverage": "buildable",
            "color family": "pink",
        },
        {
            "parent_product_id": "owned-3",
            "product_name": "Plain Balm",
            "brand": "KIKO Milano",
            "category_key": "lipstick",
            "pdp_url": "https://example.test/owned-3",
            "form": "balm",
            "finish": "natural",
            "coverage": "sheer",
            "color family": "clear",
        },
    ]
    owned_variant_rows = [
        {"parent_product_id": parent_id}
        for parent_id in [
            "owned-1",
            *["owned-2" for _index in range(16)],
            "owned-3",
        ]
    ]
    retailer_rows = [
        {
            "parent_product_id": "retailer-1",
            "product_name": "Matte Full Lipstick",
            "brand": "KIKO Milano",
            "category_key": "lipstick",
            "pdp_url": "https://ulta.example/retailer-1",
            "form": "bullet lipstick",
            "finish": "matte",
            "coverage": "full",
            "color family": "red",
        }
    ]
    _patch_database_catalogs(
        monkeypatch,
        owned_rows=owned_rows,
        owned_variant_rows=owned_variant_rows,
        retailer_rows=retailer_rows,
    )

    output_dir = build_package(
        brand_source_retailer="kiko",
        brand_name="KIKO Milano",
        category_key="lipstick",
        retailer="ulta",
        innovation_package_dir=innovation_package_dir,
        innovation_brief_path=innovation_brief_path,
        owned_cli_dir=manufacturer_cli_dir,
        output_root=output_root,
        retailer_live_check=False,
    )

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    package_integrity = json.loads(
        (output_dir / "package_integrity.json").read_text(encoding="utf-8")
    )
    package_warnings = json.loads(
        (output_dir / "package_warnings.json").read_text(encoding="utf-8")
    )
    anchors = pl.read_csv(output_dir / "retailer_brand_anchors.csv")
    signal_bundles = pl.read_csv(output_dir / "signal_bundles.csv")
    anchor_signal_fit = pl.read_csv(output_dir / "retailer_brand_anchor_signal_fit.csv")
    anchor_matches = pl.read_csv(output_dir / "brand_at_retailer_bundle_matches.csv")
    brand_reviews = pl.read_csv(output_dir / "brand_at_retailer_review_validation.csv")
    manufacturer_matches = pl.read_csv(
        output_dir / "manufacturer_catalog_bundle_matches.csv"
    )
    plain_language_signal_guide = pl.read_csv(
        output_dir / "plain_language_signal_guide.csv"
    )
    attribute_coverage = pl.read_csv(output_dir / "attribute_coverage.csv")
    candidates = pl.read_csv(output_dir / "reference_candidates.csv")
    image_index = pl.read_csv(output_dir / "image_index.csv")
    brand_fit_context = (output_dir / "brand_fit_context.md").read_text(
        encoding="utf-8"
    )
    prompt = (output_dir / "prompt_for_pro.txt").read_text(encoding="utf-8")
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    source_brief = (output_dir / "source_innovation_brief.md").read_text(
        encoding="utf-8"
    )

    assert summary["analysis_type"] == "brand_retailer_reference_handoff"
    assert summary["source_innovation_brief_file"] == "source_innovation_brief.md"
    assert summary["counts"]["signal_bundles"] == 2
    assert summary["counts"]["signal_bundles_with_rank_weighted_visibility"] == 1
    assert summary["counts"]["retailer_brand_anchor_products"] == 1
    assert (
        summary["counts"]["retailer_brand_anchor_products_with_rating_or_review_count"]
        == 1
    )
    assert summary["counts"]["retailer_brand_anchor_products_with_review_text"] == 1
    assert summary["counts"]["retailer_brand_anchor_review_text_snippets"] == 4
    assert summary["counts"]["brand_at_retailer_review_validation_rows"] == 1
    assert summary["counts"]["brand_at_retailer_bundle_matches"] == 1
    assert summary["counts"]["manufacturer_catalog_products"] == 3
    assert summary["counts"]["reference_candidates"] == 1
    assert summary["package_integrity"]["status"] == "pass"
    assert summary["counts"]["package_integrity_failures"] == 0
    assert summary["counts"]["source_web_shelf_artifact_files"] == 5
    assert summary["counts"]["source_web_shelf_selected_shelves_rows"] == 1
    assert summary["counts"]["source_web_shelf_candidate_shelves_rows"] == 1
    assert summary["counts"]["source_web_shelf_robustness_summary_rows"] == 1
    assert summary["counts"]["source_web_shelf_product_assignments_rows"] == 1
    assert summary["counts"]["source_web_shelf_third_attribute_refinements_rows"] == 1
    assert summary["counts"]["source_review_evidence_artifact_files"] == 3
    assert summary["counts"]["source_review_theme_cohort_comparison_rows"] == 1
    assert summary["counts"]["source_top_seller_review_validation_rows"] == 1
    assert summary["counts"]["source_bundle_review_validation_rows"] == 1
    assert package_integrity["status"] == "pass"
    assert package_warnings["status"] == "pass_with_warnings"
    assert summary["package_warning_count"] == 1
    assert package_warnings["warnings"][0]["code"] == "retailer_live_check_disabled"
    assert summary["sources"]["retailer_review_source_files"] == [
        "product_filter_matrix.csv"
    ]
    assert summary["sources"]["source_web_shelf_artifacts"]["expected"] is True
    assert {
        file_info["package_file"]
        for file_info in summary["sources"]["source_web_shelf_artifacts"]["files"]
    } == {
        "source_web_shelf_selected_shelves.csv",
        "source_web_shelf_candidate_shelves.csv",
        "source_web_shelf_robustness_summary.csv",
        "source_web_shelf_product_assignments.csv",
        "source_web_shelf_third_attribute_refinements.csv",
    }
    assert (output_dir / "source_web_shelf_selected_shelves.csv").exists()
    assert (output_dir / "source_web_shelf_candidate_shelves.csv").exists()
    assert (output_dir / "source_web_shelf_robustness_summary.csv").exists()
    assert (output_dir / "source_web_shelf_product_assignments.csv").exists()
    assert (output_dir / "source_web_shelf_third_attribute_refinements.csv").exists()
    assert summary["sources"]["source_review_evidence_artifacts"]["expected"] is True
    assert {
        file_info["package_file"]
        for file_info in summary["sources"]["source_review_evidence_artifacts"]["files"]
    } == {
        "source_review_theme_cohort_comparison.csv",
        "source_top_seller_review_validation.csv",
        "source_bundle_review_validation.csv",
    }
    assert (output_dir / "source_review_theme_cohort_comparison.csv").exists()
    assert (output_dir / "source_top_seller_review_validation.csv").exists()
    assert (output_dir / "source_bundle_review_validation.csv").exists()
    assert set(signal_bundles["signal_layers"].to_list()) == {
        "winning_now",
        "innovation",
    }
    assert (
        signal_bundles.filter(pl.col("bundle_label") == "stick + pink").item(
            0, "rank_weighted_incremental_visibility_share"
        )
        == 0.09
    )
    assert anchor_matches.item(0, "bundle_label") == "matte + full coverage"
    assert anchors.item(0, "review_count") == 128
    assert anchors.item(0, "review_1_comment") == (
        "Comfortable color with strong payoff."
    )
    assert anchor_signal_fit.item(0, "review_1_headline") == "Great pigment"
    assert anchor_matches.item(0, "review_2_comment") == (
        "Pretty shade, but I need balm first."
    )
    assert brand_reviews.item(0, "stored_review_text_count") == 4
    assert brand_reviews.item(0, "review_evidence_source_file") == (
        "product_filter_matrix.csv"
    )
    assert "stick + pink" in manufacturer_matches["bundle_label"].to_list()
    assert candidates.item(0, "product_name") == "Pink Stylo"
    assert candidates.item(0, "innovation_bundle_count") == 1
    assert candidates.item(0, "rank_weighted_visibility_bundle_count") == 1
    assert "credible variant range" in candidates.item(0, "reference_rationale")
    assert "rank-weighted visibility support" in candidates.item(
        0, "reference_rationale"
    )
    assert get_row_count(plain_language_signal_guide) == 2
    assert (
        plain_language_signal_guide.item(0, "plain_english_read")
        and "retailer signal" in prompt
    )
    assert (
        "matte + full coverage" in plain_language_signal_guide["signal_name"].to_list()
    )
    assert any(
        "rank-weighted visibility" in str(value)
        for value in plain_language_signal_guide[
            "rank_weighted_visibility_evidence"
        ].to_list()
    )
    assert get_row_count(attribute_coverage) > 0
    assert "Brand Fit Context Guide" in brand_fit_context
    assert "Do not print internal IDs" in brand_fit_context
    assert 'Use "form" as the attribute name' in brand_fit_context
    assert get_row_count(image_index) == 4
    assert "buyer-readable Brand Fit report" in prompt
    assert "Read `source_innovation_brief.md` first" in prompt
    assert "Read `brand_fit_context.md` second" in prompt
    assert "plain_language_signal_guide.csv" in prompt
    assert "package_integrity.json" in prompt
    assert "package_warnings.json" in prompt
    assert "attribute_coverage.csv" in prompt
    assert "rank-weighted visibility as a metric attached to retailer signals" in prompt
    assert "source_web_shelf_selected_shelves.csv" in prompt
    assert "audit trail behind rank-weighted visibility" in prompt
    assert "source_review_theme_cohort_comparison.csv" in prompt
    assert "secondary retailer-level experience layer" in prompt
    assert "shopper path attribution" in prompt
    assert "variant-level attributes" in prompt
    assert "Do not discover new signals" in prompt
    assert "Reason by retailer signals, not isolated single attributes" in prompt
    assert "Be skeptical" in prompt
    assert "It is acceptable to conclude" in prompt
    assert "not as final recommendations" in prompt
    assert "If no product clears the evidence bar" in prompt
    assert "This is not an assortment gap report" in prompt
    assert "not as automatic launch, listing, or assortment recommendations" in prompt
    assert "Do not print internal IDs" in prompt
    assert "Avoid internal jargon" in prompt
    assert 'Use "form" as the attribute name' in prompt
    assert "Do not create a Word or DOCX document" in prompt
    assert "do not embed images in the output" in prompt
    assert "Do not insert screenshots, product photos, or image grids" in prompt
    assert "brand_at_retailer_review_validation.csv" in prompt
    assert "package_integrity.json" in readme
    assert "package_warnings.json" in readme
    assert "brand_at_retailer_review_validation.csv" in readme
    assert "Source web-shelf audit files" in readme
    assert "source_web_shelf_robustness_summary.csv" in readme
    assert "Source Review Evidence Files" in readme
    assert "source_review_theme_cohort_comparison.csv" in readme
    assert "Stick form is a legacy wording." in source_brief
    assert "Stick forms are legacy wording too." in source_brief
    assert "format" not in source_brief.casefold()

    zip_path = output_dir.parent / "lipstick_ulta_kiko.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "kiko/prompt_for_pro.txt" in names
    assert "kiko/brand_fit_context.md" in names
    assert "kiko/package_integrity.json" in names
    assert "kiko/package_warnings.json" in names
    assert "kiko/plain_language_signal_guide.csv" in names
    assert "kiko/attribute_coverage.csv" in names
    assert "kiko/brand_at_retailer_review_validation.csv" in names
    assert "kiko/source_innovation_brief.md" in names
    assert "kiko/signal_bundles.csv" in names
    assert "kiko/source_web_shelf_selected_shelves.csv" in names
    assert "kiko/source_web_shelf_candidate_shelves.csv" in names
    assert "kiko/source_web_shelf_robustness_summary.csv" in names
    assert "kiko/source_web_shelf_product_assignments.csv" in names
    assert "kiko/source_web_shelf_third_attribute_refinements.csv" in names
    assert "kiko/source_review_theme_cohort_comparison.csv" in names
    assert "kiko/source_top_seller_review_validation.csv" in names
    assert "kiko/source_bundle_review_validation.csv" in names
    assert "kiko/images/innovation_examples/source-example.png" in names
    assert "kiko/images/innovation_examples/source-unused.png" not in names
    assert "kiko/images/manufacturer_catalog/owned-2.webp" in names
    assert "kiko/images/manufacturer_catalog/owned-3.webp" not in names


def test_build_package_uses_category_aliases_for_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    innovation_package_dir = tmp_path / "launch" / "lip_balm" / "ulta"
    innovation_brief_path = tmp_path / "briefs" / "launch" / "lip_balm" / "ulta.md"
    manufacturer_cli_dir = tmp_path / "cli" / "kiko_lip_balm"
    alternate_manufacturer_cli_dir = tmp_path / "cli" / "kiko_lip_treatment"
    output_root = tmp_path / "packages"

    innovation_package_dir.mkdir(parents=True)
    (alternate_manufacturer_cli_dir / "images").mkdir(parents=True)
    (alternate_manufacturer_cli_dir / "images" / "owned-1_hero.webp").write_bytes(
        b"owned-1-image"
    )
    (innovation_package_dir / "summary.json").write_text(
        json.dumps(
            {
                "retailer": "ulta",
                "retailer_label": "Ulta",
                "category_key": "lip_balm",
                "category_label": "lip balm",
            }
        ),
        encoding="utf-8",
    )
    _write_valid_source_package_validation(innovation_package_dir)
    innovation_brief_path.parent.mkdir(parents=True)
    innovation_brief_path.write_text(
        "Lip balm signals should be read as care-plus-shine propositions.",
        encoding="utf-8",
    )
    _write_signal_csv(
        innovation_package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_key": "form=balm + finish=glossy",
                "bundle_label": "balm + glossy",
                "count_top_seller": 5,
                "count_other": 8,
                "top_seller_brand_count": 3,
                "other_brand_count": 5,
                "pct_top_seller": 0.4,
                "pct_other": 0.1,
                "delta": 0.3,
                "prevalence_ratio": 4.0,
                "top_seller_sales_share_sum": 0.2,
                "top_seller_brands": "Brand A | Brand B | Brand C",
                "top_seller_example_products": "Source Balm",
                "top_seller_top_pareto_products": "Source Balm",
            }
        ],
    )

    owned_rows = [
        {
            "parent_product_id": "owned-1",
            "product_name": "Glossy Care Balm",
            "brand": "KIKO Milano",
            "category_key": "coloured_lip_balm",
            "pdp_url": "https://example.test/owned-1",
            "form": "balm",
            "finish": "glossy",
        },
        {
            "parent_product_id": "owned-2",
            "product_name": "Velvet Mascara",
            "brand": "KIKO Milano",
            "category_key": "mascara",
            "pdp_url": "https://example.test/owned-2",
            "form": "mascara",
            "finish": "natural",
        },
    ]
    retailer_rows = [
        {
            "parent_product_id": "retailer-1",
            "product_name": "Retail Gloss Balm",
            "brand": "KIKO Milano",
            "category_key": "lip_balms",
            "pdp_url": "https://ulta.example/retailer-1",
            "form": "balm",
            "finish": "glossy",
        },
        {
            "parent_product_id": "retailer-2",
            "product_name": "Retail Mascara",
            "brand": "KIKO Milano",
            "category_key": "mascara",
            "pdp_url": "https://ulta.example/retailer-2",
            "form": "mascara",
            "finish": "natural",
        },
    ]
    _patch_database_catalogs(
        monkeypatch,
        owned_rows=owned_rows,
        retailer_rows=retailer_rows,
    )

    output_dir = build_package(
        brand_source_retailer="kiko",
        brand_name="KIKO Milano",
        category_key="lip_balm",
        retailer="ulta",
        innovation_package_dir=innovation_package_dir,
        innovation_brief_path=innovation_brief_path,
        owned_cli_dirs=(manufacturer_cli_dir, alternate_manufacturer_cli_dir),
        owned_category_keys=("coloured_lip_balm",),
        retailer_category_keys=("lip_balms",),
        output_root=output_root,
        retailer_live_check=False,
    )

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    manufacturer_products = pl.read_csv(
        output_dir / "manufacturer_catalog_products.csv"
    )
    anchors = pl.read_csv(output_dir / "retailer_brand_anchors.csv")
    candidates = pl.read_csv(output_dir / "reference_candidates.csv")
    image_index = pl.read_csv(output_dir / "image_index.csv")

    assert output_dir.name == "kiko"
    assert output_dir.parent.name == "ulta"
    assert output_dir.parent.parent.name == "lip_balm"
    assert summary["sources"]["owned_category_keys"] == ["coloured_lip_balm"]
    assert summary["sources"]["owned_cli_dirs"] == [
        str(manufacturer_cli_dir),
        str(alternate_manufacturer_cli_dir),
    ]
    assert summary["sources"]["retailer_category_keys"] == ["lip_balms"]
    assert summary["counts"]["manufacturer_catalog_products"] == 1
    assert summary["counts"]["retailer_brand_anchor_products"] == 1
    assert summary["counts"]["reference_candidates"] == 1
    assert summary["counts"]["images"] == 1
    assert manufacturer_products.item(0, "category_key") == "coloured_lip_balm"
    assert anchors.item(0, "category_key") == "lip_balms"
    assert candidates.item(0, "product_name") == "Glossy Care Balm"
    assert (
        image_index.item(0, "image_file") == "images/manufacturer_catalog/owned-1.webp"
    )


def test_copy_manufacturer_images_uses_cached_hero_image_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "package"
    products = pl.DataFrame(
        [
            {
                "parent_product_id": "owned-1",
                "product_name": "Smart Colour Blush",
                "product_scope": "manufacturer_catalog",
                "hero_image_url": "https://images.example/smart-colour.webp",
            },
            {
                "parent_product_id": "owned-2",
                "product_name": "Unused Bronzer",
                "product_scope": "manufacturer_catalog",
                "hero_image_url": "https://images.example/unused.webp",
            },
        ]
    )

    def fake_download_image_preview(url: str, destination: Path) -> str:
        assert url == "https://images.example/smart-colour.webp"
        preview_destination = destination.with_suffix(".webp")
        preview_destination.parent.mkdir(parents=True)
        preview_destination.write_bytes(b"image")
        return str(preview_destination)

    monkeypatch.setattr(
        reference_builder, "_download_image_preview", fake_download_image_preview
    )

    enriched, image_rows = reference_builder._copy_manufacturer_images(
        products,
        cli_dir=tmp_path / "missing_cli",
        output_dir=output_dir,
        parent_ids={"owned-1"},
    )

    assert (
        enriched.filter(pl.col("parent_product_id") == "owned-1").item(0, "image_file")
        == "images/manufacturer_catalog/owned-1.webp"
    )
    assert (
        enriched.filter(pl.col("parent_product_id") == "owned-2").item(0, "image_file")
        is None
    )
    assert image_rows == [
        {
            "image_scope": "manufacturer_catalog",
            "parent_product_id": "owned-1",
            "product_name": "Smart Colour Blush",
            "image_file": "images/manufacturer_catalog/owned-1.webp",
            "image_available": True,
            "image_source": "https://images.example/smart-colour.webp",
            "inspect_rule": "Use to verify product form, finish cue, packaging, and shade-family fit.",
        }
    ]


def test_validate_brand_image_coverage_fails_without_candidate_images() -> None:
    owned = pl.DataFrame(
        [
            {
                "parent_product_id": "owned-1",
                "product_name": "Smart Colour Blush",
                "image_file": None,
            }
        ]
    )
    candidates = pl.DataFrame(
        [
            {
                "parent_product_id": "owned-1",
                "product_name": "Smart Colour Blush",
                "image_file": None,
            }
        ]
    )

    with pytest.raises(RuntimeError, match="No reference candidate has a brand image"):
        reference_builder._validate_brand_image_coverage(
            brand_source_retailer="kiko",
            brand_name="KIKO Milano",
            retailer="ulta",
            category_key="blush",
            owned=owned,
            candidates=candidates,
            manufacturer_image_rows=[],
            allow_missing_brand_images=False,
        )


def test_validate_brand_image_coverage_fails_without_any_brand_images() -> None:
    owned = pl.DataFrame(
        [
            {
                "parent_product_id": "owned-1",
                "product_name": "Smart Colour Blush",
                "image_file": None,
            }
        ]
    )
    candidates = pl.DataFrame(schema={})

    with pytest.raises(RuntimeError, match="No brand images were copied"):
        reference_builder._validate_brand_image_coverage(
            brand_source_retailer="kiko",
            brand_name="KIKO Milano",
            retailer="ulta",
            category_key="blush",
            owned=owned,
            candidates=candidates,
            manufacturer_image_rows=[],
            allow_missing_brand_images=False,
        )


def test_validate_package_ready_for_pro_fails_on_cross_brand_anchor() -> None:
    anchors = pl.DataFrame(
        [
            {
                "product_name": "Silky Tint",
                "brand": "P\u00dcR",
            }
        ]
    )

    with pytest.raises(RuntimeError, match="different brand"):
        reference_builder._validate_package_ready_for_pro(
            brand_name="L'Oreal Paris",
            retailer="ulta",
            category_key="blush",
            anchors=anchors,
            retailer_live_audit=pl.DataFrame(schema={}),
            retailer_live_check=False,
        )


def test_validate_package_ready_for_pro_fails_when_live_audit_unavailable() -> None:
    live_audit = pl.DataFrame(
        [
            {
                "audit_status": "live_check_unavailable",
            }
        ]
    )

    with pytest.raises(RuntimeError, match="live presence audit did not complete"):
        reference_builder._validate_package_ready_for_pro(
            brand_name="L'Oreal Paris",
            retailer="ulta",
            category_key="blush",
            anchors=pl.DataFrame(schema={}),
            retailer_live_audit=live_audit,
            retailer_live_check=True,
        )


def test_live_audit_zero_products_builds_as_no_current_retailer_presence() -> None:
    owned = pl.DataFrame(
        [
            {
                "product_name": "Flawless Fusion Bronzer Powder",
                "product_key": "flawless fusion bronzer powder",
                "parent_product_id": "owned-bronzer-1",
                "pdp_url": "https://kiko.example/flawless-fusion",
            }
        ]
    )
    retailer_products = pl.DataFrame(
        [
            {
                "product_name": "Flawless Fusion Bronzer Powder",
                "product_key": "flawless fusion bronzer powder",
                "parent_product_id": "pimprod2020354",
                "pdp_url": "https://www.ulta.com/p/flawless-fusion-bronzer-pimprod2020354",
            }
        ]
    )

    validated, audit, live_count, live_url = (
        reference_builder._audit_live_retailer_presence(
            owned=owned,
            retailer_products=retailer_products,
            brand_name="KIKO Milano",
            category_key="bronzer",
            retailer="ulta",
            enabled=True,
            timeout=1.0,
            fetcher=lambda _url: "<html><body>No products found</body></html>",
        )
    )

    reference_builder._validate_package_ready_for_pro(
        brand_name="KIKO Milano",
        retailer="ulta",
        category_key="bronzer",
        anchors=validated,
        retailer_live_audit=audit,
        retailer_live_check=True,
    )
    assert live_url == (
        "https://www.ulta.com/brand/kiko-milano?category=makeup%2Cface%2Cbronzer"
    )
    assert live_count == 0
    assert validated.height == 0
    assert audit.item(0, "audit_status") == (
        "cached_package_anchor_not_on_live_brand_page"
    )
    assert audit.item(0, "live_removed_from_retailer_products")


def test_live_audit_positive_count_without_products_remains_unavailable() -> None:
    owned = pl.DataFrame(
        [
            {
                "product_name": "Flawless Fusion Bronzer Powder",
                "product_key": "flawless fusion bronzer powder",
                "parent_product_id": "owned-bronzer-1",
            }
        ]
    )
    retailer_products = owned.clone()

    _validated, audit, live_count, _live_url = (
        reference_builder._audit_live_retailer_presence(
            owned=owned,
            retailer_products=retailer_products,
            brand_name="KIKO Milano",
            category_key="bronzer",
            retailer="ulta",
            enabled=True,
            timeout=1.0,
            fetcher=lambda _url: "<html><body>7 results</body></html>",
        )
    )

    assert live_count == 0
    assert audit.item(0, "audit_status") == "live_check_unavailable"


def test_validate_package_ready_for_pro_fails_on_package_integrity_failure() -> None:
    package_integrity = {
        "status": "fail",
        "summary": {"failure_count": 2},
    }

    with pytest.raises(RuntimeError, match="Package integrity audit failed"):
        reference_builder._validate_package_ready_for_pro(
            brand_name="L'Oreal Paris",
            retailer="ulta",
            category_key="blush",
            anchors=pl.DataFrame(schema={}),
            retailer_live_audit=pl.DataFrame(schema={}),
            retailer_live_check=False,
            package_integrity=package_integrity,
        )


def test_require_source_package_integrity_fails_when_missing_or_failed(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "launch" / "blush" / "ulta"
    package_dir.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="validated source retailer package"):
        reference_builder._require_source_package_integrity(package_dir)

    (package_dir / "package_integrity.json").write_text(
        json.dumps({"status": "fail", "summary": {"failure_count": 1}}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="status=fail"):
        reference_builder._require_source_package_integrity(package_dir)


def test_require_source_package_snapshot_manifest_fails_when_missing(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "launch" / "blush" / "ulta"
    package_dir.mkdir(parents=True)

    with pytest.raises(
        RuntimeError, match="requires source retailer package snapshots"
    ):
        reference_builder._require_source_package_snapshot_manifest(package_dir, {})


def test_copy_source_web_shelf_artifacts_requires_complete_audit_files(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "launch" / "lipstick" / "ulta"
    package_dir.mkdir(parents=True)
    output_dir = tmp_path / "brand_fit" / "lipstick" / "ulta" / "kiko"
    output_dir.mkdir(parents=True)
    _write_signal_csv(
        package_dir / "web_shelf_selected_shelves.csv",
        [{"bundle_key": "form=stick", "incremental_weight_share": 0.2}],
    )
    signal_bundles = pl.DataFrame(
        [
            {
                "bundle_key": "form=stick",
                "rank_weighted_incremental_visibility_share": 0.2,
            }
        ]
    )

    with pytest.raises(RuntimeError, match="web-shelf audit files are incomplete"):
        reference_builder._copy_source_web_shelf_artifacts(
            package_dir,
            output_dir=output_dir,
            source_innovation_summary={"counts": {"web_shelf_selected_rows": 1}},
            signal_bundles=signal_bundles,
        )


def test_copy_source_web_shelf_artifacts_fails_on_row_count_mismatch(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "launch" / "lipstick" / "ulta"
    package_dir.mkdir(parents=True)
    output_dir = tmp_path / "brand_fit" / "lipstick" / "ulta" / "kiko"
    output_dir.mkdir(parents=True)
    for source_name, _package_name in reference_builder.SOURCE_WEB_SHELF_ARTIFACTS:
        _write_signal_csv(package_dir / source_name, [{"bundle_key": "form=stick"}])

    with pytest.raises(RuntimeError, match="row-count mismatches"):
        reference_builder._copy_source_web_shelf_artifacts(
            package_dir,
            output_dir=output_dir,
            source_innovation_summary={"counts": {"web_shelf_selected_rows": 2}},
            signal_bundles=pl.DataFrame(),
        )


def test_optional_source_artifact_prompt_lines_are_quiet_when_absent() -> None:
    summary = {
        "brand_name": "KIKO Milano",
        "retailer_label": "Ulta",
        "category_label": "blush",
        "sources": {},
        "counts": {
            "signal_bundles": 1,
            "retailer_brand_anchor_products": 1,
            "manufacturer_catalog_products": 1,
            "reference_candidates": 0,
            "brand_at_retailer_bundle_matches": 0,
            "manufacturer_catalog_bundle_matches": 0,
            "images": 0,
        },
        "package_integrity": {"status": "pass"},
    }

    assert reference_builder._web_shelf_prompt_line(summary) == ""
    assert reference_builder._review_evidence_prompt_line(summary) == ""
    context = reference_builder._brand_fit_context_text(
        summary,
        pl.DataFrame(),
        pl.DataFrame(),
    )
    readme = reference_builder._readme_text(summary)
    assert "Source web-shelf audit files" not in context
    assert "Source review evidence files" not in context
    assert "Source web-shelf audit files" not in readme
    assert "Source review evidence files" not in readme


def test_copy_source_review_evidence_artifacts_requires_complete_files(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "launch" / "bronzer" / "ulta"
    package_dir.mkdir(parents=True)
    output_dir = tmp_path / "brand_fit" / "bronzer" / "ulta" / "kiko"
    output_dir.mkdir(parents=True)
    _write_signal_csv(
        package_dir / "review_theme_cohort_comparison.csv",
        [
            {
                "comparison_key": "top_seller_vs_other",
                "theme_id": "theme_blendability",
            }
        ],
    )

    with pytest.raises(RuntimeError, match="source review evidence files"):
        reference_builder._copy_source_review_evidence_artifacts(
            package_dir,
            output_dir=output_dir,
            source_innovation_summary={
                "review_theme_cohort_comparison_rows": 1,
                "top_seller_review_validation_rows": 1,
            },
        )


def test_copy_source_review_evidence_artifacts_fails_on_row_count_mismatch(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "launch" / "bronzer" / "ulta"
    package_dir.mkdir(parents=True)
    output_dir = tmp_path / "brand_fit" / "bronzer" / "ulta" / "kiko"
    output_dir.mkdir(parents=True)
    _write_signal_csv(
        package_dir / "review_theme_cohort_comparison.csv",
        [
            {
                "comparison_key": "top_seller_vs_other",
                "theme_id": "theme_blendability",
            }
        ],
    )

    with pytest.raises(RuntimeError, match="row-count mismatches"):
        reference_builder._copy_source_review_evidence_artifacts(
            package_dir,
            output_dir=output_dir,
            source_innovation_summary={"review_theme_cohort_comparison_rows": 2},
        )


def test_build_package_cleans_partial_output_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "brand_fit"

    def _failing_impl(**kwargs: object) -> Path:
        output_dir = reference_builder._package_output_dir(
            output_root,
            brand_source_retailer="kiko",
            retailer="ulta",
            category_key="bronzer",
        )
        output_dir.mkdir(parents=True)
        (output_dir / "partial.csv").write_text("bad\n", encoding="utf-8")
        reference_builder._package_zip_path(output_dir).write_text(
            "partial",
            encoding="utf-8",
        )
        raise RuntimeError("quality gate failed")

    monkeypatch.setattr(reference_builder, "_build_package_impl", _failing_impl)

    with pytest.raises(RuntimeError, match="quality gate failed"):
        reference_builder.build_package(
            brand_source_retailer="kiko",
            brand_name="KIKO Milano",
            category_key="bronzer",
            retailer="ulta",
            output_root=output_root,
        )

    output_dir = reference_builder._package_output_dir(
        output_root,
        brand_source_retailer="kiko",
        retailer="ulta",
        category_key="bronzer",
    )
    assert not output_dir.exists()
    assert not reference_builder._package_zip_path(output_dir).exists()


def test_package_integrity_audit_fails_when_anchor_drops_source_attributes() -> None:
    anchors = pl.DataFrame(
        [
            {
                "product_scope": "brand_at_retailer",
                "source": "ulta",
                "product_name": "Unlimited Blush",
                "product_key": "unlimited blush",
                "parent_product_id": "pimprod2032252",
                "brand": "KIKO Milano",
                "category_key": "blush",
                "form": None,
                "coverage": "Buildable",
                "finish": "Metallic",
            }
        ]
    )
    signal_bundles = pl.DataFrame(
        [
            {
                "bundle_id": "bundle_1",
                "bundle_label": "Buildable + Pressed powder",
                "bundle_key": "coverage=buildable + form=pressed powder",
                "bundle_size": 2,
                "components_json": json.dumps(
                    [
                        {"attribute": "coverage", "value": "buildable"},
                        {"attribute": "form", "value": "pressed powder"},
                    ]
                ),
                "component_labels": "coverage=buildable | form=pressed powder",
                "signal_layers": "winning_now",
                "signal_score": 1.0,
                "source_files": "top_seller_pairs.csv",
            }
        ]
    )
    anchor_signal_fit = pl.DataFrame(
        [
            {
                "product_name": "Unlimited Blush",
                "product_key": "unlimited blush",
                "matched_signal_count": 0,
                "matched_signal_labels": "",
            }
        ]
    )

    audit = reference_builder._build_package_integrity_audit(
        brand_name="KIKO Milano",
        anchors=anchors,
        signal_bundles=signal_bundles,
        anchor_matches=pl.DataFrame(schema={}),
        anchor_signal_fit=anchor_signal_fit,
        attribute_lookup={
            "id:pimprod2032252": {
                "form": "Pressed powder",
                "coverage": "Buildable",
                "finish": "Matte | Luminous",
            }
        },
        attribute_source_files=["product_filter_matrix.csv"],
        pre_attribute_anchor_matches=pl.DataFrame(schema={}),
    )

    assert audit["status"] == "fail"
    assert audit["summary"]["failure_count"] == 2
    assert {
        issue["attribute"]
        for issue in audit["issues"]
        if issue["check_id"] == "retailer_anchor_attribute_propagation"
    } == {"form", "finish"}


def test_package_integrity_audit_fails_when_owned_catalog_has_no_attributes() -> None:
    owned = pl.DataFrame(
        [
            {
                "product_scope": "manufacturer_catalog",
                "source": "kiko",
                "product_name": "Bare Product",
                "product_key": "bare product",
                "parent_product_id": "owned-1",
                "brand": "KIKO Milano",
                "category_key": "blush",
            }
        ]
    )

    audit = reference_builder._build_package_integrity_audit(
        brand_name="KIKO Milano",
        anchors=pl.DataFrame(schema={}),
        owned=owned,
        signal_bundles=pl.DataFrame(schema={"bundle_id": pl.Utf8}),
        anchor_matches=pl.DataFrame(schema={}),
        anchor_signal_fit=pl.DataFrame(schema={}),
        attribute_lookup={},
        attribute_source_files=[],
        pre_attribute_anchor_matches=pl.DataFrame(schema={}),
    )

    assert audit["status"] == "fail"
    assert audit["summary"]["failure_count"] == 1
    assert audit["issues"][0]["check_id"] == "brand_fit_product_attributes_nonempty"
    assert audit["issues"][0]["product_scope"] == "manufacturer_catalog"


def test_build_package_adds_live_brand_page_match_as_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    innovation_package_dir, innovation_brief_path = (
        _write_minimal_retailer_signal_source(
            tmp_path=tmp_path,
            category_key="bronzer",
        )
    )
    manufacturer_cli_dir = tmp_path / "cli" / "kiko_bronzer"
    manufacturer_images_dir = manufacturer_cli_dir / "images"
    output_root = tmp_path / "packages"
    manufacturer_images_dir.mkdir(parents=True)
    (manufacturer_images_dir / "owned-bronzer-1_hero.webp").write_bytes(
        b"owned-bronzer-image"
    )

    owned_rows = [
        {
            "parent_product_id": "owned-bronzer-1",
            "product_name": "Flawless Fusion Bronzer Powder",
            "brand": "KIKO Milano",
            "category_key": "bronzer",
            "pdp_url": "https://kiko.example/flawless-fusion",
            "form": "pressed powder",
            "finish": "radiant",
        },
        {
            "parent_product_id": "owned-bronzer-2",
            "product_name": "Catalog Only Bronzer",
            "brand": "KIKO Milano",
            "category_key": "bronzer",
            "pdp_url": "https://kiko.example/catalog-only",
            "form": "cream",
            "finish": "matte",
        },
    ]
    retailer_rows = [
        {
            "parent_product_id": "retailer-other-1",
            "product_name": "Other Brand Bronzer",
            "brand": "Other Brand",
            "category_key": "bronzer",
            "pdp_url": "https://ulta.example/other",
            "form": "pressed powder",
            "finish": "radiant",
        }
    ]
    _patch_database_catalogs(
        monkeypatch,
        owned_rows=owned_rows,
        retailer_rows=retailer_rows,
    )

    live_html = """
    <a class="pal-c-Link" href="https://www.ulta.com/p/flawless-fusion-bronzer-powder-pimprod2020354?sku=2626575">
      <span class="pal-c-Text pal-c-Text__isScreenReader">KIKO Milano Flawless Fusion Bronzer Powder</span>
    </a>
    """

    output_dir = build_package(
        brand_source_retailer="kiko",
        brand_name="KIKO Milano",
        category_key="bronzer",
        retailer="ulta",
        innovation_package_dir=innovation_package_dir,
        innovation_brief_path=innovation_brief_path,
        owned_cli_dir=manufacturer_cli_dir,
        output_root=output_root,
        retailer_live_fetcher=lambda _url: live_html,
    )

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    audit = pl.read_csv(output_dir / "retailer_live_presence_audit.csv")
    anchors = pl.read_csv(output_dir / "retailer_brand_anchors.csv")
    missing = pl.read_csv(output_dir / "manufacturer_products_not_at_retailer.csv")
    anchor_matches = pl.read_csv(output_dir / "brand_at_retailer_bundle_matches.csv")

    assert summary["sources"]["retailer_live_brand_page_url"] == (
        "https://www.ulta.com/brand/kiko-milano?category=makeup%2Cface%2Cbronzer"
    )
    assert summary["counts"]["retailer_live_brand_page_products"] == 1
    assert summary["counts"]["retailer_live_products_added_as_anchors"] == 1
    assert summary["counts"]["retailer_brand_anchor_products"] == 1
    assert audit.item(0, "audit_status") == "live_brand_page_missing_from_package"
    assert audit.item(0, "live_added_to_retailer_products")
    assert anchors.item(0, "product_name") == "Flawless Fusion Bronzer Powder"
    assert anchors.item(0, "parent_product_id") == "pimprod2020354"
    assert anchors.item(0, "pdp_url") == (
        "https://www.ulta.com/p/flawless-fusion-bronzer-powder-pimprod2020354?sku=2626575"
    )
    assert "Flawless Fusion Bronzer Powder" not in missing["product_name"].to_list()
    assert anchor_matches.item(0, "product_name") == "Flawless Fusion Bronzer Powder"


def test_build_package_removes_cached_anchor_absent_from_live_brand_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    innovation_package_dir, innovation_brief_path = (
        _write_minimal_retailer_signal_source(
            tmp_path=tmp_path,
            category_key="bronzer",
        )
    )
    manufacturer_cli_dir = tmp_path / "cli" / "kiko_bronzer"
    manufacturer_images_dir = manufacturer_cli_dir / "images"
    output_root = tmp_path / "packages"
    manufacturer_images_dir.mkdir(parents=True)
    (manufacturer_images_dir / "owned-bronzer-1_hero.webp").write_bytes(
        b"owned-bronzer-image"
    )

    owned_row = {
        "parent_product_id": "owned-bronzer-1",
        "product_name": "Flawless Fusion Bronzer Powder",
        "brand": "KIKO Milano",
        "category_key": "bronzer",
        "pdp_url": "https://kiko.example/flawless-fusion",
        "form": "pressed powder",
        "finish": "radiant",
    }
    retailer_rows = [
        {
            **owned_row,
            "parent_product_id": "pimprod2020354",
            "pdp_url": "https://www.ulta.com/p/flawless-fusion-bronzer-powder-pimprod2020354",
        }
    ]
    _patch_database_catalogs(
        monkeypatch,
        owned_rows=[owned_row],
        retailer_rows=retailer_rows,
    )

    live_html = """
    <a class="pal-c-Link" href="https://www.ulta.com/p/3d-hydra-lip-oil-pimprod2032251">
      <span class="pal-c-Text pal-c-Text__isScreenReader">KIKO Milano 3D Hydra Lip Oil</span>
    </a>
    """

    output_dir = build_package(
        brand_source_retailer="kiko",
        brand_name="KIKO Milano",
        category_key="bronzer",
        retailer="ulta",
        innovation_package_dir=innovation_package_dir,
        innovation_brief_path=innovation_brief_path,
        owned_cli_dir=manufacturer_cli_dir,
        output_root=output_root,
        retailer_live_fetcher=lambda _url: live_html,
    )

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    audit = pl.read_csv(output_dir / "retailer_live_presence_audit.csv")
    anchors = pl.read_csv(output_dir / "retailer_brand_anchors.csv")
    missing = pl.read_csv(output_dir / "manufacturer_products_not_at_retailer.csv")

    assert summary["counts"]["retailer_live_brand_page_products"] == 1
    assert summary["counts"]["retailer_live_cached_products_removed_as_anchors"] == 1
    assert summary["counts"]["retailer_brand_anchor_products"] == 0
    assert audit.item(0, "audit_status") == (
        "cached_package_anchor_not_on_live_brand_page"
    )
    assert audit.item(0, "package_anchor_present_before_live_check")
    assert audit.item(0, "live_removed_from_retailer_products")
    assert anchors.height == 0
    assert missing.item(0, "product_name") == "Flawless Fusion Bronzer Powder"
