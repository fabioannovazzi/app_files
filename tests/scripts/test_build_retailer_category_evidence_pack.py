from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from scripts import build_retailer_category_evidence_pack as pack_builder

_UNIT_STORES: dict[Path, dict[str, list[dict[str, Any]]]] = {}


class _UnitCursor:
    def __init__(self, rows: list[tuple[Any, ...]]):
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None


class _UnitStoreConnection:
    def __init__(self, rows_by_table: dict[str, list[dict[str, Any]]]):
        self._rows_by_table = rows_by_table

    def __enter__(self) -> _UnitStoreConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(
        self, query: str, params: tuple[Any, ...] | list[Any] = ()
    ) -> _UnitCursor:
        query_key = " ".join(query.lower().split())
        if "select max(crawl_ts)" in query_key:
            table = (
                "retailer_filter_observations"
                if "retailer_filter_observations" in query_key
                else "retailer_listing_observations"
            )
            retailer, category_key = params
            matches = [
                row["crawl_ts"]
                for row in self._rows_by_table.get(table, [])
                if row["retailer"] == retailer and row["category_key"] == category_key
            ]
            return _UnitCursor([(max(matches),)] if matches else [])

        if "group by retailer, category_key" in query_key:
            retailer_filter = params[0] if params else None
            pairs = {
                (row["retailer"], row["category_key"])
                for row in self._rows_by_table.get("retailer_listing_observations", [])
                if retailer_filter is None or row["retailer"] == retailer_filter
            }
            return _UnitCursor(sorted(pairs))

        if "from parent_products" in query_key:
            retailer, *parent_ids = params
            parent_id_set = set(parent_ids)
            rows = [
                (
                    row["parent_product_id"],
                    row.get("title_raw"),
                    row.get("brand_raw"),
                    row.get("pdp_url"),
                    row.get("extras"),
                )
                for row in self._rows_by_table.get("parent_products", [])
                if row["retailer"] == retailer
                and row["parent_product_id"] in parent_id_set
            ]
            return _UnitCursor(rows)

        if "from retailer_listing_observations" in query_key:
            crawl_ts, retailer, category_key = params
            columns = (
                "crawl_ts",
                "retailer",
                "category_key",
                "source_surface",
                "sort_mode",
                "page",
                "position",
                "pdp_url",
                "parent_product_id",
                "product_name",
                "brand",
                "has_new_badge",
                "listing_url",
            )
            return _UnitCursor(
                [
                    tuple(row.get(column) for column in columns)
                    for row in self._rows_by_table.get(
                        "retailer_listing_observations", []
                    )
                    if row["crawl_ts"] == crawl_ts
                    and row["retailer"] == retailer
                    and row["category_key"] == category_key
                ]
            )

        if "from retailer_filter_observations" in query_key:
            crawl_ts, retailer, category_key = params
            columns = (
                "crawl_ts",
                "retailer",
                "category_key",
                "filter_family",
                "filter_value",
                "source_surface",
                "pdp_url",
                "parent_product_id",
                "page",
                "position",
                "listing_url",
            )
            return _UnitCursor(
                [
                    tuple(row.get(column) for column in columns)
                    for row in self._rows_by_table.get(
                        "retailer_filter_observations", []
                    )
                    if row["crawl_ts"] == crawl_ts
                    and row["retailer"] == retailer
                    and row["category_key"] == category_key
                ]
            )

        return _UnitCursor([])


def _store_rows(path: Path) -> dict[str, list[dict[str, Any]]]:
    return _UNIT_STORES.setdefault(
        path,
        {
            "parent_products": [],
            "retailer_filter_observations": [],
            "retailer_listing_observations": [],
        },
    )


@pytest.fixture(autouse=True)
def _use_unit_store(monkeypatch: pytest.MonkeyPatch) -> None:
    _UNIT_STORES.clear()
    monkeypatch.delenv("PDP_DATABASE_URL", raising=False)
    monkeypatch.delenv("PDP_BACKUP_DATABASE_URL", raising=False)
    monkeypatch.setattr(pack_builder, "load_env_from_secrets_file", lambda: {})
    monkeypatch.setattr(
        pack_builder,
        "pdp_database_exists",
        lambda path: Path(path) in _UNIT_STORES,
    )
    monkeypatch.setattr(
        pack_builder,
        "connect_pdp_database",
        lambda path: _UnitStoreConnection(_UNIT_STORES[Path(path)]),
    )
    yield
    _UNIT_STORES.clear()


def _write_listing_pair_table(pdp_store_path: Path) -> None:
    _store_rows(pdp_store_path)["retailer_listing_observations"].extend(
        [
            {"retailer": "ulta", "category_key": "lip_gloss"},
            {"retailer": "ulta", "category_key": "blush"},
            {"retailer": "ulta", "category_key": "blush"},
            {
                "retailer": "saksfifthavenue",
                "category_key": "cashmere_sweaters",
            },
        ]
    )


def _empty_mapped_attribute_frames() -> pack_builder._MappedAttributeFrames:
    return pack_builder._MappedAttributeFrames(
        parent_df=pl.DataFrame(),
        variant_df=pl.DataFrame(),
    )


def test_discovered_retailer_categories_filters_to_one_retailer(
    tmp_path: Path,
) -> None:
    pdp_store_path = tmp_path / "pdp_store"
    _write_listing_pair_table(pdp_store_path)

    pairs = pack_builder._discovered_retailer_categories(
        pdp_store_path, retailer="ulta"
    )

    assert pairs == [("ulta", "blush"), ("ulta", "lip_gloss")]


def test_build_all_packs_builds_each_category_for_retailer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdp_store_path = tmp_path / "pdp_store"
    output_root = tmp_path / "packages"
    calls: list[tuple[str, str]] = []
    preload_calls: list[tuple[str, ...]] = []
    preloaded_attribute_frames = _empty_mapped_attribute_frames()
    _write_listing_pair_table(pdp_store_path)

    def fake_load_mapped_attribute_frames(
        *,
        pdp_store_path: Path,
        retailer: str,
        category_keys: list[str],
    ) -> pack_builder._MappedAttributeFrames:
        preload_calls.append(tuple(category_keys))
        return preloaded_attribute_frames

    def fake_build_pack(
        *,
        retailer: str,
        category_key: str,
        run_dir: Path | None,
        pdp_store_path: Path,
        cli_root: Path,
        output_root: Path,
        max_pack_images: int | None = None,
        attribute_frames: pack_builder._MappedAttributeFrames | None = None,
    ) -> Path:
        calls.append((retailer, category_key))
        assert attribute_frames is preloaded_attribute_frames
        return output_root / category_key / retailer

    monkeypatch.setattr(
        pack_builder,
        "_load_mapped_attribute_frames",
        fake_load_mapped_attribute_frames,
    )
    monkeypatch.setattr(pack_builder, "build_pack", fake_build_pack)

    summary = pack_builder.build_all_packs(
        pdp_store_path=pdp_store_path,
        cli_root=tmp_path / "cli",
        output_root=output_root,
        retailer="ulta",
    ).sort("category_key")

    assert calls == [("ulta", "blush"), ("ulta", "lip_gloss")]
    assert preload_calls == [("blush", "lip_gloss")]
    assert summary.get_column("status").to_list() == ["built", "built"]
    assert summary.get_column("package_zip").to_list() == [
        str(output_root / "blush" / "blush_ulta.zip"),
        str(output_root / "lip_gloss" / "lip_gloss_ulta.zip"),
    ]


def test_build_all_packs_uses_explicit_categories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdp_store_path = tmp_path / "pdp_store"
    output_root = tmp_path / "packages"
    calls: list[tuple[str, str]] = []
    preload_calls: list[tuple[str, ...]] = []
    _write_listing_pair_table(pdp_store_path)

    def fake_load_mapped_attribute_frames(
        *,
        pdp_store_path: Path,
        retailer: str,
        category_keys: list[str],
    ) -> pack_builder._MappedAttributeFrames:
        preload_calls.append(tuple(category_keys))
        return _empty_mapped_attribute_frames()

    def fake_build_pack(
        *,
        retailer: str,
        category_key: str,
        run_dir: Path | None,
        pdp_store_path: Path,
        cli_root: Path,
        output_root: Path,
        max_pack_images: int | None = None,
        attribute_frames: pack_builder._MappedAttributeFrames | None = None,
    ) -> Path:
        calls.append((retailer, category_key))
        return output_root / category_key / retailer

    monkeypatch.setattr(
        pack_builder,
        "_load_mapped_attribute_frames",
        fake_load_mapped_attribute_frames,
    )
    monkeypatch.setattr(pack_builder, "build_pack", fake_build_pack)

    summary = pack_builder.build_all_packs(
        pdp_store_path=pdp_store_path,
        cli_root=tmp_path / "cli",
        output_root=output_root,
        retailer="ulta",
        category_keys=["blush"],
    )

    assert calls == [("ulta", "blush")]
    assert preload_calls == [("blush",)]
    assert summary.get_column("category_key").to_list() == ["blush"]
    assert summary.get_column("status").to_list() == ["built"]


def test_review_theme_package_rows_compare_current_package_cohorts() -> None:
    review_rows = [
        ("top-review-1", "top-product-1"),
        ("top-review-2", "top-product-2"),
        ("top-review-3", "top-product-3"),
        ("other-review-1", "other-product-1"),
        ("other-review-2", "other-product-2"),
        ("other-review-3", "other-product-3"),
        ("other-review-4", "other-product-4"),
        ("other-review-5", "other-product-5"),
        ("other-review-6", "other-product-6"),
    ]
    tag_rows = [
        (
            "top-review-1",
            "top-product-1",
            "cat_acceptance__eats",
            "Eats it",
            "Cat acceptance",
            "positive",
            "my cat eats this",
            "cat",
            "food",
            0.9,
            "Brand A",
            "Top food 1",
            5.0,
        ),
        (
            "top-review-2",
            "top-product-2",
            "cat_acceptance__eats",
            "Eats it",
            "Cat acceptance",
            "positive",
            "cleans the bowl",
            "cat",
            "food",
            0.9,
            "Brand B",
            "Top food 2",
            5.0,
        ),
        (
            "other-review-1",
            "other-product-1",
            "cat_acceptance__eats",
            "Eats it",
            "Cat acceptance",
            "positive",
            "cat ate some",
            "cat",
            "food",
            0.7,
            "Brand C",
            "Other food 1",
            4.0,
        ),
    ]
    comparison_specs = [
        {
            "comparison_type": "top_seller_vs_other",
            "focus_label": "top sellers",
            "baseline_label": "other products",
            "focus_product_ids": {
                "top-product-1",
                "top-product-2",
                "top-product-3",
            },
            "baseline_product_ids": {
                "other-product-1",
                "other-product-2",
                "other-product-3",
                "other-product-4",
                "other-product-5",
                "other-product-6",
            },
        }
    ]

    rows = pack_builder._build_review_theme_package_comparison_rows(
        review_rows=review_rows,
        tag_rows=tag_rows,
        comparison_specs=comparison_specs,
    )

    assert len(rows) == 1
    assert rows[0]["comparison_type"] == "top_seller_vs_other"
    assert rows[0]["focus_products_with_theme"] == 2
    assert rows[0]["baseline_products_with_theme"] == 1
    assert rows[0]["focus_product_mention_rate"] == pytest.approx(2 / 3)
    assert rows[0]["baseline_product_mention_rate"] == pytest.approx(1 / 6)
    assert rows[0]["theme_level"] == "subtheme"
    assert rows[0]["experience_signal_class"] == "positive_over_index"
    assert rows[0]["focus_positive_review_rate"] == pytest.approx(2 / 3)
    assert rows[0]["baseline_positive_review_rate"] == pytest.approx(1 / 6)


def test_review_theme_package_rows_surface_parent_table_stakes() -> None:
    review_rows = [
        ("top-review-1", "top-product-1"),
        ("top-review-2", "top-product-2"),
        ("top-review-3", "top-product-3"),
        ("other-review-1", "other-product-1"),
        ("other-review-2", "other-product-2"),
        ("other-review-3", "other-product-3"),
        ("other-review-4", "other-product-4"),
        ("other-review-5", "other-product-5"),
        ("other-review-6", "other-product-6"),
    ]
    tag_rows = [
        (
            "top-review-1",
            "top-product-1",
            "acceptance__general",
            "General acceptance",
            "Cat acceptance",
            "positive",
            "cat eats it",
            "cat",
            "food",
            0.9,
            "Brand A",
            "Top food 1",
            5.0,
        ),
        (
            "top-review-2",
            "top-product-2",
            "acceptance__general",
            "General acceptance",
            "Cat acceptance",
            "positive",
            "cat likes it",
            "cat",
            "food",
            0.9,
            "Brand B",
            "Top food 2",
            5.0,
        ),
        (
            "top-review-3",
            "top-product-3",
            "acceptance__refusal",
            "Refusal",
            "Cat acceptance",
            "negative",
            "cat refused it",
            "cat",
            "food",
            0.9,
            "Brand C",
            "Top food 3",
            2.0,
        ),
        *[
            (
                f"other-review-{index}",
                f"other-product-{index}",
                "acceptance__general" if index <= 4 else "acceptance__refusal",
                "General acceptance" if index <= 4 else "Refusal",
                "Cat acceptance",
                "positive" if index <= 4 else "negative",
                "cat eats it" if index <= 4 else "cat refused it",
                "cat",
                "food",
                0.9,
                "Brand D",
                f"Other food {index}",
                4.0 if index <= 4 else 2.0,
            )
            for index in range(1, 7)
        ],
    ]
    comparison_specs = [
        {
            "comparison_type": "top_seller_vs_other",
            "focus_label": "top sellers",
            "baseline_label": "other products",
            "focus_product_ids": {
                "top-product-1",
                "top-product-2",
                "top-product-3",
            },
            "baseline_product_ids": {
                "other-product-1",
                "other-product-2",
                "other-product-3",
                "other-product-4",
                "other-product-5",
                "other-product-6",
            },
        }
    ]

    rows = pack_builder._build_review_theme_package_comparison_rows(
        review_rows=review_rows,
        tag_rows=tag_rows,
        comparison_specs=comparison_specs,
    )
    parent_rows = [
        row
        for row in rows
        if row["theme_level"] == "parent_theme"
        and row["theme_family"] == "Cat acceptance"
    ]

    assert len(parent_rows) == 1
    assert parent_rows[0]["experience_signal_class"] == "table_stakes"
    assert parent_rows[0]["focus_review_mention_rate"] == pytest.approx(1.0)
    assert parent_rows[0]["baseline_review_mention_rate"] == pytest.approx(1.0)
    assert parent_rows[0]["net_positive_review_rate_delta"] == pytest.approx(0.0)


def test_build_all_packs_records_data_readiness_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdp_store_path = tmp_path / "pdp_store"
    preload_calls: list[tuple[str, ...]] = []
    _write_listing_pair_table(pdp_store_path)

    def fake_load_mapped_attribute_frames(
        *,
        pdp_store_path: Path,
        retailer: str,
        category_keys: list[str],
    ) -> pack_builder._MappedAttributeFrames:
        preload_calls.append(tuple(category_keys))
        return _empty_mapped_attribute_frames()

    def fake_build_pack(
        *,
        retailer: str,
        category_key: str,
        run_dir: Path | None,
        pdp_store_path: Path,
        cli_root: Path,
        output_root: Path,
        max_pack_images: int | None = None,
        attribute_frames: pack_builder._MappedAttributeFrames | None = None,
    ) -> Path:
        if category_key == "tinted_moisturizer":
            raise pack_builder.PackageBuildSkipped("ranked surfaces are identical")
        return output_root / category_key / retailer

    monkeypatch.setattr(
        pack_builder,
        "_load_mapped_attribute_frames",
        fake_load_mapped_attribute_frames,
    )
    monkeypatch.setattr(pack_builder, "build_pack", fake_build_pack)

    summary = pack_builder.build_all_packs(
        pdp_store_path=pdp_store_path,
        cli_root=tmp_path / "cli",
        output_root=tmp_path / "packages",
        retailer="ulta",
        category_keys=["blush", "tinted_moisturizer"],
    ).sort("category_key")

    assert summary.get_column("status").to_list() == ["built", "skipped"]
    assert preload_calls == [("blush", "tinted_moisturizer")]
    skipped = summary.filter(pl.col("status") == "skipped").row(0, named=True)
    assert skipped["category_key"] == "tinted_moisturizer"
    assert skipped["error"] == "ranked surfaces are identical"


def test_prepare_mapped_attribute_frame_flattens_list_values() -> None:
    export_df = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "parent_product_id": ["p1", "p2"],
            "category_key": ["blush", "blush"],
            "brand": ["Brand A", "Brand B"],
            "benefits": [["hydrating", "vegan"], ["not stated"]],
        }
    )

    mapped_df, mapped_columns = pack_builder._prepare_mapped_attribute_frame(
        export_df,
        retailer="ulta",
        category_key="blush",
    )

    assert mapped_df.schema["benefits"] == pl.Utf8
    assert mapped_df.sort("parent_product_id").get_column("benefits").to_list() == [
        "hydrating | vegan",
        None,
    ]
    assert mapped_columns == ["benefits"]


def test_semantic_analysis_attribute_columns_falls_back_to_filter_columns() -> None:
    columns = pack_builder._semantic_analysis_attribute_columns(
        mapped_semantic_columns=[],
        filter_attribute_columns=["flavor", "food texture", "filter_coverage"],
        available_columns=["flavor", "food texture", "filter_coverage"],
    )

    assert columns == ["flavor", "food texture"]


def test_semantic_analysis_attribute_columns_prefers_mapped_columns() -> None:
    columns = pack_builder._semantic_analysis_attribute_columns(
        mapped_semantic_columns=["benefits", "skin type"],
        filter_attribute_columns=["flavor", "food texture"],
        available_columns=["benefits", "skin type", "flavor", "food texture"],
    )

    assert columns == ["benefits", "skin type"]


def test_build_product_universe_preserves_brand() -> None:
    listing_df = pl.DataFrame(
        {
            "listing_identity": ["p1", "p2"],
            "category_key": ["wet_cat_food", "wet_cat_food"],
            "parent_product_id": ["p1", "p2"],
            "brand": ["Fancy Feast", "Friskies"],
            "product_name": ["A", "B"],
            "pdp_url": ["https://example.com/a", "https://example.com/b"],
            "has_new_badge": [False, True],
        }
    )

    universe = pack_builder._build_product_universe(
        category_listing_raw=listing_df,
        category_filters=pl.DataFrame(),
        mapped_export_df=pl.DataFrame(),
    ).sort("listing_identity")

    assert universe.get_column("brand").to_list() == ["Fancy Feast", "Friskies"]


def test_parent_detail_rows_loads_brand_and_stored_hero_url(tmp_path: Path) -> None:
    pdp_store_path = tmp_path / "pdp_store"
    _store_rows(pdp_store_path)["parent_products"].append(
        {
            "retailer": "chewy",
            "parent_product_id": "p1",
            "title_raw": "Example Product",
            "brand_raw": "Fancy Feast",
            "pdp_url": "https://example.com/p1",
            "extras": json.dumps(
                {"hero_image_url": "https://cdn.example.com/parent-hero.jpg"}
            ),
        }
    )

    rows = pack_builder._parent_detail_rows(pdp_store_path, "chewy", ["p1"])

    assert rows["p1"]["brand_raw"] == "Fancy Feast"
    assert rows["p1"]["hero_image_url"] == ("https://cdn.example.com/parent-hero.jpg")


def test_package_diagnostic_warnings_flags_brand_and_bundle_inconsistency() -> None:
    warnings = pack_builder._package_diagnostic_warnings(
        listing_products=100,
        products_with_brand=0,
        materialized_filter_attribute_rows=200,
        mapped_attribute_comparison_rows=10,
        top_seller_mapped_attribute_comparison_rows=8,
        recent_products=20,
        top_seller_products=15,
        innovation_pair_rows=0,
        innovation_triple_rows=0,
        top_seller_pair_rows=0,
        top_seller_triple_rows=0,
        recent_products_with_reviews=12,
        top_seller_review_validation_rows=0,
        bundle_review_validation_rows=0,
    )

    codes = {warning["code"] for warning in warnings}
    assert "brand_column_empty" in codes
    assert "top_seller_bundles_empty_despite_attribute_signal" in codes
    assert "innovation_bundles_empty_despite_attribute_signal" in codes


def test_package_diagnostic_warnings_stays_quiet_for_sane_counts() -> None:
    warnings = pack_builder._package_diagnostic_warnings(
        listing_products=100,
        products_with_brand=100,
        materialized_filter_attribute_rows=200,
        mapped_attribute_comparison_rows=25,
        top_seller_mapped_attribute_comparison_rows=20,
        recent_products=20,
        top_seller_products=15,
        innovation_pair_rows=5,
        innovation_triple_rows=2,
        top_seller_pair_rows=12,
        top_seller_triple_rows=7,
        recent_products_with_reviews=12,
        top_seller_review_validation_rows=8,
        bundle_review_validation_rows=11,
    )

    assert warnings == []


def test_launch_package_warning_payload_combines_integrity_and_context() -> None:
    payload = pack_builder._launch_package_warning_payload(
        summary={
            "sale_pressure_products": 0,
            "sale_pressure_available": True,
            "sale_pressure_sort_mode": "sale",
            "sale_pressure_absence_interpretation": (
                "Absence from the captured sale-pressure window is not proof."
            ),
        },
        package_integrity={
            "issues": [
                {
                    "severity": "warning",
                    "check_id": "mapped_attribute_source_coverage_brittle",
                    "message": "Some products have no mapped PDP attributes.",
                }
            ]
        },
        diagnostic_warnings=[
            {
                "code": "brand_column_empty",
                "message": "Brand column is empty.",
            }
        ],
    )

    assert payload["status"] == "pass_with_warnings"
    codes = {warning["code"] for warning in payload["warnings"]}
    assert "mapped_attribute_source_coverage_brittle" in codes
    assert "brand_column_empty" in codes
    assert "sale_pressure_absence_not_proof_of_no_discount" in codes


def test_launch_package_warning_payload_marks_missing_sale_surface() -> None:
    payload = pack_builder._launch_package_warning_payload(
        summary={
            "sale_pressure_products": 0,
            "sale_pressure_available": False,
            "sale_pressure_sort_mode": None,
        },
        package_integrity={"issues": []},
        diagnostic_warnings=[],
    )

    assert payload["status"] == "pass_with_warnings"
    assert payload["warnings"][0]["code"] == "sale_pressure_surface_unavailable"


def test_image_rows_falls_back_to_canonical_category_alias(tmp_path: Path) -> None:
    images_dir = tmp_path / "chewy_wet_cat_food" / "images"
    images_dir.mkdir(parents=True)
    image_path = images_dir / "p1_hero.jpg"
    image_path.write_bytes(b"fake-image")

    rows = pack_builder._image_rows(
        tmp_path,
        "chewy",
        "wet_cat_food",
        pl.DataFrame(),
    )

    assert rows["p1"]["local_image_path"] == str(image_path.resolve())


def test_require_pack_images_raises_when_recent_products_have_no_images() -> None:
    with pytest.raises(RuntimeError, match="zero pack images"):
        pack_builder._require_pack_images(
            retailer="chewy",
            category_key="wet_cat_food",
            recent_products=10,
            recent_products_with_pack_image=0,
        )


def test_require_pack_images_accepts_nonempty_image_output() -> None:
    pack_builder._require_pack_images(
        retailer="chewy",
        category_key="wet_cat_food",
        recent_products=10,
        recent_products_with_pack_image=3,
    )


def test_split_bundle_values_accepts_list_values() -> None:
    assert pack_builder._split_bundle_values(["hydrating | vegan", "Hydrating"]) == [
        "hydrating",
        "vegan",
    ]


def test_rank_weighted_visibility_metrics_attach_to_matching_bundle() -> None:
    bundle_df = pl.DataFrame(
        [
            {
                "bundle_size": 2,
                "bundle_key": "Finish=Matte + Form=Stick",
                "bundle_label": "matte + stick",
            }
        ]
    )
    candidate_shelves = pl.DataFrame(
        [
            {
                "alpha": 1.0,
                "bundle_key": "finish=matte + form=stick",
                "bundle_size": 2,
                "attributes": "finish=matte | form=stick",
                "gross_weight_share": 0.31,
                "gross_sku_count": 9,
                "gross_sku_share": 0.3,
                "density_index": 1.03,
                "gross_brand_count": 4,
                "top_products": "A (#1)",
                "top_brands": "Brand A",
            }
        ]
    )
    selected_shelves = pl.DataFrame(
        [
            {
                "alpha": 1.0,
                "shelf_rank": 2,
                "bundle_key": "finish=matte + form=stick",
                "bundle_size": 2,
                "attributes": "finish=matte | form=stick",
                "gross_weight_share": 0.31,
                "incremental_weight_share": 0.12,
                "cumulative_weight_share": 0.5,
                "gross_sku_count": 9,
                "incremental_sku_count": 5,
                "gross_sku_share": 0.3,
                "incremental_sku_share": 0.16,
                "density_index": 1.03,
                "gross_brand_count": 4,
                "incremental_brand_count": 3,
                "top_products": "A (#1)",
                "top_brands": "Brand A",
            }
        ]
    )
    robustness = pl.DataFrame(
        [
            {
                "bundle_key": "finish=matte + form=stick",
                "times_selected": 3,
                "best_shelf_rank": 1,
                "average_shelf_rank": 1.7,
                "average_gross_weight_share": 0.3,
                "average_incremental_weight_share": 0.11,
                "average_density_index": 1.05,
            }
        ]
    )

    out = pack_builder._with_rank_weighted_visibility_metrics(
        bundle_df,
        candidate_shelves=candidate_shelves,
        selected_shelves=selected_shelves,
        robustness_summary=robustness,
    )

    assert out.item(0, "rank_weighted_gross_visibility_share") == 0.3
    assert out.item(0, "rank_weighted_incremental_visibility_share") == 0.11
    assert out.item(0, "rank_weighted_visibility_alpha_scenarios") == 3
    assert out.item(0, "rank_weighted_visibility_incremental_available") is True


def test_rank_weighted_visibility_metrics_preserve_sparse_original_schema() -> None:
    rows = [
        {
            "bundle_size": 2,
            "bundle_key": f"Finish=Matte + Form=Stick {index}",
            "bundle_label": None,
        }
        for index in range(101)
    ]
    rows.append(
        {
            "bundle_size": 2,
            "bundle_key": "bundle-a",
            "bundle_label": "natural + primer",
        }
    )
    bundle_df = pl.DataFrame(
        rows,
        schema={
            "bundle_size": pl.Int64,
            "bundle_key": pl.Utf8,
            "bundle_label": pl.Utf8,
        },
    )

    out = pack_builder._with_rank_weighted_visibility_metrics(
        bundle_df,
        candidate_shelves=pl.DataFrame(),
        selected_shelves=pl.DataFrame(),
        robustness_summary=pl.DataFrame(),
    )

    assert out.schema["bundle_label"] == pl.Utf8
    assert out.item(101, "bundle_label") == "natural + primer"
    assert out.item(101, "rank_weighted_visibility_incremental_available") is False


def test_with_listing_identity_adds_column_to_empty_filter_frame() -> None:
    empty_filters = pack_builder._empty_filter_observations()

    out = pack_builder._with_listing_identity(empty_filters)

    assert "listing_identity" in out.columns
    assert out.height == 0


def test_build_family_denominators_handles_empty_filter_frame() -> None:
    empty_filters = pack_builder._with_listing_identity(
        pack_builder._empty_filter_observations()
    )
    status_df = pl.DataFrame({"listing_identity": ["p1"], "listing_status": ["recent"]})

    out = pack_builder._build_family_denominators(empty_filters, status_df)

    assert out.height == 0
    assert out.schema == {
        "filter_family": pl.Utf8,
        "listing_status": pl.Utf8,
        "family_product_count": pl.Int64,
    }


def test_resolve_slot_values_prefers_ulta_and_falls_back_to_mapped() -> None:
    rows = [
        {
            "finish": "high shine",
            "coverage": None,
            "color lips": None,
            "form": None,
            "finish effect": "natural",
            "color payoff": "sheer tint",
            "shade family": "pink",
            "product type": "tube",
        }
    ]

    resolved = pack_builder._resolve_slot_values(rows)
    row = resolved[0]

    assert row["resolved_finish"] == "high shine"
    assert row["resolved_finish_source"] == "ulta"
    assert row["resolved_coverage"] == "sheer tint"
    assert row["resolved_coverage_source"] == "mapped"
    assert row["resolved_color"] == "pink"
    assert row["resolved_color_source"] == "mapped"
    assert row["resolved_form"] == "tube"
    assert row["resolved_form_source"] == "mapped"
    assert row["mapped_form_source_column"] == "product type"


def test_resolve_slot_values_marks_missing_when_no_source_exists() -> None:
    rows = [
        {
            "finish": None,
            "coverage": None,
            "color lips": None,
            "form": None,
        }
    ]

    resolved = pack_builder._resolve_slot_values(rows)
    row = resolved[0]

    assert row["resolved_finish"] is None
    assert row["resolved_finish_source"] == "missing"
    assert row["resolved_coverage"] is None
    assert row["resolved_color"] is None
    assert row["resolved_form"] is None


def test_resolve_slot_values_prefers_retailer_filter_color() -> None:
    rows = [
        {
            "color": "Camel | Black",
            "available_color_families": "black | brown",
            "color family": "brown",
            "shade family": "neutral",
        }
    ]

    resolved = pack_builder._resolve_slot_values(rows)
    row = resolved[0]

    assert row["filter_color"] == "Camel | Black"
    assert row["filter_color_source_column"] == "color"
    assert row["rollup_color"] == "black | brown"
    assert row["mapped_color"] == "brown"
    assert row["resolved_color"] == "Camel | Black"
    assert row["resolved_color_source"] == "retailer_filter"


def test_resolve_slot_values_falls_back_to_variant_color_rollup() -> None:
    rows = [
        {
            "available_color_families": "black | blue",
            "color family": "black",
        }
    ]

    resolved = pack_builder._resolve_slot_values(rows)
    row = resolved[0]

    assert row["rollup_color"] == "black | blue"
    assert row["rollup_color_source_column"] == "available_color_families"
    assert row["resolved_color"] == "black | blue"
    assert row["resolved_color_source"] == "attribute_rollup"


def test_merge_filter_primary_attributes_prefers_filter_values_for_saloncentric() -> (
    None
):
    row = {
        "product benefit": "gray coverage | shine",
        "benefit": "not in taxonomy",
        "ingredient preference": "ammonia-free",
        "ingredient_preference": "N/A",
        "product type": "permanent",
        "product type_mapped": "not in taxonomy",
    }

    out = pack_builder._merge_filter_primary_attributes(
        row,
        retailer="saloncentric",
        category_key="permanent",
        mapped_attribute_columns=[
            "benefit",
            "ingredient_preference",
            "product type",
        ],
    )

    assert out["benefit"] == "gray coverage | shine"
    assert out["ingredient_preference"] == "ammonia-free"
    assert out["product type"] == "permanent"
    assert out["benefit_effective_source"] == "retailer_filter"
    assert out["ingredient_preference_effective_source"] == "retailer_filter"
    assert out["product type_effective_source"] == "retailer_filter"


def test_merge_filter_primary_attributes_falls_back_to_export_when_filter_missing() -> (
    None
):
    row = {
        "product benefit": None,
        "benefit": "bonding",
        "ingredient preference": "",
        "ingredient_preference": "vegan",
    }

    out = pack_builder._merge_filter_primary_attributes(
        row,
        retailer="saloncentric",
        category_key="permanent",
        mapped_attribute_columns=["benefit", "ingredient_preference"],
    )

    assert out["benefit"] == "bonding"
    assert out["ingredient_preference"] == "vegan"
    assert out["benefit_effective_source"] == "pdp_attribute_values"
    assert out["ingredient_preference_effective_source"] == "pdp_attribute_values"


def test_merge_filter_primary_attributes_prefers_saks_color_and_material_filters() -> (
    None
):
    row = {
        "color": "White | Black",
        "material": "Leather",
        "closure": "lace-up",
    }

    out = pack_builder._merge_filter_primary_attributes(
        row,
        retailer="saksfifthavenue",
        category_key="low_top_sneakers",
        mapped_attribute_columns=["closure"],
    )

    assert out["color"] == "white | black"
    assert out["material"] == "leather"
    assert out["closure"] == "lace-up"
    assert out["color_effective_source"] == "retailer_filter"
    assert out["material_effective_source"] == "retailer_filter"
    assert out["closure_effective_source"] == "pdp_attribute_values"


def test_merge_filter_primary_attributes_maps_saks_cashmere_filter_families() -> None:
    row = {
        "color": "Camel",
        "style": "Oversized",
        "sleeve length": "Long Sleeve",
        "lifestyle": "Premier Designer",
        "sleeve_length_mapped": "Short Sleeve",
    }

    out = pack_builder._merge_filter_primary_attributes(
        row,
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        mapped_attribute_columns=["sleeve_length"],
    )

    assert out["color"] == "Camel"
    assert out["style"] == "oversized"
    assert out["sleeve_length"] == "long sleeve"
    assert out["lifestyle"] == "Premier Designer"
    assert out["sleeve_length_effective_source"] == "retailer_filter"


def test_rebuilt_matrix_applies_codex_correction_only_when_codex_is_effective() -> None:
    source_listing = pl.DataFrame(
        [
            {
                "crawl_ts": "2026-07-15T00:00:00Z",
                "retailer": "retailer",
                "category_key": "skin-care",
                "source_surface": "category",
                "sort_mode": "new_arrivals",
                "page": 1,
                "position": position,
                "pdp_url": f"https://example.test/{product_id}",
                "parent_product_id": product_id,
                "product_name": f"Product {product_id}",
                "brand": "Example",
                "has_new_badge": product_id == "p1",
                "listing_url": "https://example.test/listing",
            }
            for position, product_id in enumerate(("p1", "p2"), start=1)
        ]
    )
    source_filters = pl.DataFrame(
        [
            {
                "crawl_ts": "2026-07-15T00:00:00Z",
                "retailer": "retailer",
                "category_key": "skin-care",
                "filter_family": "finish",
                "filter_value": "Matte",
                "source_surface": "filter",
                "pdp_url": "https://example.test/p2",
                "parent_product_id": "p2",
                "page": 1,
                "position": 2,
                "listing_url": "https://example.test/listing",
            }
        ]
    )

    def rebuilt(codex_value: str) -> pl.DataFrame:
        source_attributes = pl.DataFrame(
            [
                {
                    "parent_product_id": product_id,
                    "category_key": "skin-care",
                    "finish": codex_value,
                    "finish_effective_source": "codex",
                }
                for product_id in ("p1", "p2")
            ]
        )
        return pack_builder._build_source_expected_product_matrix(
            retailer="retailer",
            category_key="skin-care",
            source_listing_observations=source_listing,
            source_filter_observations=source_filters,
            source_mapped_attributes=source_attributes,
            recent_share=0.5,
            recent_sort_mode="new_arrivals",
            sale_pressure_sort_mode=None,
        )

    before = rebuilt("Matte")
    after = rebuilt("Dewy")
    before_by_product = {row["parent_product_id"]: row for row in before.to_dicts()}
    after_by_product = {row["parent_product_id"]: row for row in after.to_dicts()}

    assert before_by_product["p1"]["finish"] == "Matte"
    assert after_by_product["p1"]["finish"] == "Dewy"
    assert after_by_product["p1"]["finish_effective_source"] == "codex"
    assert before_by_product["p2"]["finish"] == "Matte"
    assert after_by_product["p2"]["finish"] == "Matte"
    assert after_by_product["p2"]["finish_effective_source"] == "retailer_filter"


def test_merge_filter_primary_attributes_normalizes_taxonomy_synonyms() -> None:
    row = {
        "material": "Embellished | Patent Leather | Suede",
    }

    out = pack_builder._merge_filter_primary_attributes(
        row,
        retailer="saksfifthavenue",
        category_key="low_top_sneakers",
        mapped_attribute_columns=[],
    )

    assert out["material"] == "embellished material | patent leather | suede"


def test_merge_filter_primary_attributes_normalizes_saks_cashmere_style() -> None:
    row = {
        "style": "Graphic & Logo | Oversized",
    }

    out = pack_builder._merge_filter_primary_attributes(
        row,
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        mapped_attribute_columns=[],
    )

    assert out["style"] == "graphic & logo | oversized"


def test_saks_cashmere_bundle_columns_include_mapped_sweater_structure() -> None:
    out = pack_builder._bundle_attribute_columns(
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        available_columns=[
            "color",
            "style",
            "sleeve_length",
            "lifestyle",
            "garment type",
            "neckline",
            "knit_detail",
            "ignored",
        ],
        default_columns=[],
    )

    assert out == [
        "color",
        "style",
        "sleeve_length",
        "garment type",
        "neckline",
        "knit_detail",
    ]


def test_prepare_variant_color_rollups_groups_meaningful_color_families() -> None:
    variant_df = pl.DataFrame(
        {
            "retailer": [
                "saksfifthavenue",
                "saksfifthavenue",
                "saksfifthavenue",
                "saksfifthavenue",
                "saksfifthavenue",
                "ulta",
            ],
            "parent_product_id": ["p1", "p1", "p1", "p2", "p3", "p1"],
            "category_key": [
                "cashmere_sweaters",
                "cashmere_sweaters",
                "cashmere_sweaters",
                "cashmere_sweaters",
                "low_top_sneakers",
                "cashmere_sweaters",
            ],
            "color family": [
                "blue",
                "black",
                "black",
                "not in taxonomy",
                "red",
                "pink",
            ],
        }
    )

    rollups = pack_builder._prepare_variant_color_rollups_from_frame(
        variant_df,
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
        parent_ids={"p1", "p2", "p3"},
    )

    assert rollups.to_dicts() == [
        {
            "parent_product_id": "p1",
            "available_color_families": "black | blue",
            "available_color_family_count": 2,
            "available_color_source": "variant_export",
        }
    ]


def test_apply_available_color_fallbacks_uses_filter_when_rollup_missing() -> None:
    df = pl.DataFrame(
        {
            "parent_product_id": ["p1", "p2"],
            "color": ["Camel | Black", "Blue"],
            "available_color_families": ["brown", None],
            "available_color_family_count": [1, None],
            "available_color_source": ["variant_export", None],
        }
    )

    out = pack_builder._apply_available_color_fallbacks(df).sort("parent_product_id")

    assert out.select(
        [
            "parent_product_id",
            "available_color_families",
            "available_color_family_count",
            "available_color_source",
        ]
    ).to_dicts() == [
        {
            "parent_product_id": "p1",
            "available_color_families": "brown",
            "available_color_family_count": 1,
            "available_color_source": "variant_export",
        },
        {
            "parent_product_id": "p2",
            "available_color_families": "Blue",
            "available_color_family_count": 1,
            "available_color_source": "retailer_filter",
        },
    ]


def test_merge_metadata_fallbacks_prefers_non_null_export_values() -> None:
    row = {
        "product_name": None,
        "product_name_mapped": "Majirel",
        "brand": "",
        "brand_mapped": "L'Oréal Professionnel",
    }

    out = pack_builder._merge_metadata_fallbacks(row)

    assert out["product_name"] == "Majirel"
    assert out["brand"] == "L'Oréal Professionnel"


def test_price_band_maps_expected_ranges() -> None:
    assert pack_builder._price_band(9.99) == "under_10"
    assert pack_builder._price_band(10.0) == "10_to_14_99"
    assert pack_builder._price_band(15.0) == "15_to_24_99"
    assert pack_builder._price_band(25.0) == "25_to_39_99"
    assert pack_builder._price_band(40.0) == "40_plus"
    assert pack_builder._price_band(None) is None


def test_build_price_summary_uses_snapshot_prices() -> None:
    df = pl.DataFrame(
        {
            "listing_status": ["recent", "recent", "rest", "rest"],
            "entry_price": [12.0, 24.0, 8.0, None],
            "max_price": [12.0, 30.0, 8.0, None],
            "price_snapshot_min_at": [
                "2026-04-02T10:00:00+00:00",
                "2026-04-02T11:00:00+00:00",
                "2025-11-22T10:00:00+00:00",
                None,
            ],
            "price_snapshot_max_at": [
                "2026-04-02T10:00:00+00:00",
                "2026-04-02T11:00:00+00:00",
                "2025-11-22T10:00:00+00:00",
                None,
            ],
        }
    )

    summary = pack_builder._build_price_summary(df)

    recent = summary["groups"]["recent"]
    rest = summary["groups"]["rest"]

    assert recent["priced_products"] == 2
    assert recent["entry_price_median"] == 18.0
    assert recent["entry_price_min"] == 12.0
    assert recent["entry_price_max"] == 24.0
    assert recent["snapshot_min_at"] == "2026-04-02T10:00:00+00:00"
    assert recent["snapshot_max_at"] == "2026-04-02T11:00:00+00:00"

    assert rest["products"] == 2
    assert rest["priced_products"] == 1
    assert rest["priced_product_share"] == 0.5
    assert rest["entry_price_median"] == 8.0


def test_build_image_index_marks_images_optional() -> None:
    df = pl.DataFrame(
        {
            "parent_product_id": ["p1", "p2"],
            "product_name": ["A", "B"],
            "pack_image_file": ["images/p1.png", None],
            "pack_image_source": ["local", None],
        }
    )

    out = pack_builder._build_image_index(df)

    assert out.to_dicts() == [
        {
            "parent_product_id": "p1",
            "product_name": "A",
            "image_file": "images/p1.png",
            "image_available": True,
            "image_source": "local",
            "inspect_rule": "Open only if this product matters to your analysis.",
        },
        {
            "parent_product_id": "p2",
            "product_name": "B",
            "image_file": None,
            "image_available": False,
            "image_source": None,
            "inspect_rule": "Open only if this product matters to your analysis.",
        },
    ]


def test_bounded_pack_image_limit_caps_above_hard_limit() -> None:
    assert (
        pack_builder._bounded_pack_image_limit(pack_builder.PACK_IMAGE_HARD_LIMIT + 100)
        == pack_builder.PACK_IMAGE_HARD_LIMIT
    )

    assert pack_builder._bounded_pack_image_limit(0) == 0

    with pytest.raises(ValueError, match="cannot be negative"):
        pack_builder._bounded_pack_image_limit(-1)


def test_materialize_limited_pack_image_stops_at_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str | None] = []

    def fake_materialize_pack_image(**kwargs: object) -> dict[str, str | None]:
        parent_id = kwargs["parent_id"]
        calls.append(str(parent_id) if parent_id is not None else None)
        return {
            "pack_image_path": str(tmp_path / f"{parent_id}.jpg"),
            "pack_image_source": "local_image_path",
            "og_image_url": None,
        }

    monkeypatch.setattr(
        pack_builder, "_materialize_pack_image", fake_materialize_pack_image
    )

    copied_pack_images = 0
    rows: list[dict[str, str | None]] = []
    for parent_id in ["p1", "p2", "p3"]:
        pack_image_meta, copied_pack_images = (
            pack_builder._materialize_limited_pack_image(
                output_dir=tmp_path,
                parent_id=parent_id,
                local_image_path=f"{parent_id}.jpg",
                hero_image_url=None,
                swatch_image_url=None,
                pdp_url=None,
                listing_status="recent",
                copied_pack_images=copied_pack_images,
                max_pack_images=2,
            )
        )
        rows.append(pack_image_meta)

    assert copied_pack_images == 2
    assert calls == ["p1", "p2"]
    assert rows[0]["pack_image_path"] == str(tmp_path / "p1.jpg")
    assert rows[1]["pack_image_path"] == str(tmp_path / "p2.jpg")
    assert rows[2]["pack_image_path"] is None


def test_zero_byte_pack_never_fetches_pdp_or_downloads_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_fetch(value: str | None) -> str | None:
        del value
        raise AssertionError("URL-only server package must not fetch a PDP")

    monkeypatch.setattr(pack_builder, "_fetch_og_image_url", unexpected_fetch)

    metadata, copied = pack_builder._materialize_limited_pack_image(
        output_dir=tmp_path,
        parent_id="p1",
        local_image_path=None,
        hero_image_url="https://cdn.example.com/hero.jpg",
        swatch_image_url=None,
        pdp_url="https://retailer.example.com/p1",
        listing_status="recent",
        copied_pack_images=0,
        max_pack_images=0,
    )

    assert copied == 0
    assert metadata == {
        "pack_image_path": None,
        "pack_image_source": None,
        "og_image_url": None,
    }
    assert not (tmp_path / "images").exists()


def test_package_output_dir_uses_stable_retailer_category_layout(
    tmp_path: Path,
) -> None:
    output_dir = pack_builder._package_output_dir(
        tmp_path,
        retailer="cosmoprofbeauty",
        category_key="lip-balms",
    )

    assert output_dir == tmp_path / "lip_balm" / "cosmoprofbeauty"
    assert pack_builder._package_zip_path(output_dir) == (
        tmp_path / "lip_balm" / "lip_balm_cosmoprofbeauty.zip"
    )


def test_prepare_mapped_attribute_frame_accepts_setting_spray_powder_category_key() -> (
    None
):
    export_df = pl.DataFrame(
        {
            "retailer": ["ulta"],
            "parent_product_id": ["setting-1"],
            "category_key": ["setting_spray_powder"],
            "product_name": ["Soft Focus Powder"],
            "form": ["powder"],
        }
    )

    category_df, mapped_columns = pack_builder._prepare_mapped_attribute_frame(
        export_df,
        retailer="ulta",
        category_key="setting_spray_powder",
    )

    assert category_df.height == 1
    assert category_df.item(0, "category_key") == "setting_spray_powder"
    assert mapped_columns == ["form"]


def test_load_discovery_observations_from_store_uses_latest_crawl(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "pdp_store"
    old_ts = "2026-02-08T00:00:00Z"
    latest_ts = "2026-02-09T00:00:00Z"

    rows = _store_rows(db_path)
    for crawl_ts, parent_id, product_name in (
        (old_ts, "old", "Old Product"),
        (latest_ts, "new", "New Product"),
    ):
        rows["retailer_listing_observations"].append(
            {
                "crawl_ts": crawl_ts,
                "retailer": "saksfifthavenue",
                "category_key": "low_top_sneakers",
                "source_surface": "category",
                "sort_mode": "new_arrivals",
                "page": 1,
                "position": 1,
                "pdp_url": f"https://example.com/{parent_id}",
                "parent_product_id": parent_id,
                "product_name": product_name,
                "brand": "Brand",
                "has_new_badge": 0,
                "listing_url": None,
            }
        )
        rows["retailer_filter_observations"].append(
            {
                "crawl_ts": crawl_ts,
                "retailer": "saksfifthavenue",
                "category_key": "low_top_sneakers",
                "filter_family": "material",
                "filter_value": "Leather",
                "source_surface": "filter",
                "pdp_url": f"https://example.com/{parent_id}",
                "parent_product_id": parent_id,
                "page": 1,
                "position": 1,
                "listing_url": None,
            }
        )

    listing_df, filter_df, crawl_ts = (
        pack_builder._load_discovery_observations_from_store(
            db_path,
            retailer="saksfifthavenue",
            category_key="low_top_sneakers",
        )
    )

    assert crawl_ts == latest_ts
    assert listing_df.get_column("parent_product_id").to_list() == ["new"]
    assert filter_df.get_column("parent_product_id").to_list() == ["new"]


def test_canonical_package_category_key_preserves_setting_spray_powder() -> None:
    assert (
        pack_builder._canonical_package_category_key("setting_spray_powder")
        == "setting_spray_powder"
    )


def test_package_output_dir_supports_saks_low_top_sneakers_layout(
    tmp_path: Path,
) -> None:
    output_dir = pack_builder._package_output_dir(
        tmp_path,
        retailer="saksfifthavenue",
        category_key="low_top_sneakers",
    )

    assert output_dir == tmp_path / "low_top_sneakers" / "saksfifthavenue"
    assert pack_builder._canonical_package_category_label("low_top_sneakers") == (
        "low-top sneakers"
    )


def test_package_output_dir_supports_saks_cashmere_sweaters_layout(
    tmp_path: Path,
) -> None:
    output_dir = pack_builder._package_output_dir(
        tmp_path,
        retailer="saksfifthavenue",
        category_key="cashmere_sweaters",
    )

    assert output_dir == tmp_path / "cashmere_sweaters" / "saksfifthavenue"
    assert pack_builder._canonical_package_category_label("cashmere_sweaters") == (
        "cashmere sweaters"
    )


def test_prepare_package_output_dir_removes_stale_generated_files(
    tmp_path: Path,
) -> None:
    stale_path = tmp_path / "lip_gloss" / "ulta" / "stale.csv"
    stale_zip_path = tmp_path / "lip_gloss" / "ulta.zip"
    stale_full_zip_path = tmp_path / "lip_gloss" / "lip_gloss_ulta.zip"
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text("old", encoding="utf-8")
    stale_zip_path.write_text("old zip", encoding="utf-8")
    stale_full_zip_path.write_text("old full zip", encoding="utf-8")

    output_dir = pack_builder._prepare_package_output_dir(
        tmp_path,
        retailer="ulta",
        category_key="lip_gloss",
    )

    assert output_dir == tmp_path / "lip_gloss" / "ulta"
    assert output_dir.exists()
    assert not stale_path.exists()
    assert not stale_zip_path.exists()
    assert not stale_full_zip_path.exists()


def test_build_pack_removes_stale_package_before_early_failure(tmp_path: Path) -> None:
    pdp_store_path = tmp_path / "missing_store"
    output_root = tmp_path / "packages"
    stale_path = output_root / "lip_gloss" / "ulta" / "stale.csv"
    stale_zip_path = output_root / "lip_gloss" / "lip_gloss_ulta.zip"
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text("old", encoding="utf-8")
    stale_zip_path.write_text("old zip", encoding="utf-8")

    with pytest.raises(RuntimeError, match="No listing discovery observations"):
        pack_builder.build_pack(
            retailer="ulta",
            category_key="lip_gloss",
            run_dir=None,
            pdp_store_path=pdp_store_path,
            cli_root=tmp_path / "cli",
            output_root=output_root,
        )

    assert not stale_path.parent.exists()
    assert not stale_zip_path.exists()


def test_build_pack_cleans_partial_output_on_late_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "packages"

    def _failing_impl(**kwargs: object) -> Path:
        output_dir = pack_builder._package_output_dir(
            output_root,
            retailer="ulta",
            category_key="lip_gloss",
        )
        output_dir.mkdir(parents=True)
        (output_dir / "partial.csv").write_text("bad\n", encoding="utf-8")
        pack_builder._package_zip_path(output_dir).write_text(
            "partial",
            encoding="utf-8",
        )
        raise RuntimeError("integrity gate failed")

    monkeypatch.setattr(pack_builder, "_build_pack_impl", _failing_impl)

    with pytest.raises(RuntimeError, match="integrity gate failed"):
        pack_builder.build_pack(
            retailer="ulta",
            category_key="lip_gloss",
            run_dir=None,
            pdp_store_path=tmp_path / "pdp_store",
            cli_root=tmp_path / "cli",
            output_root=output_root,
        )

    output_dir = pack_builder._package_output_dir(
        output_root,
        retailer="ulta",
        category_key="lip_gloss",
    )
    assert not output_dir.exists()
    assert not pack_builder._package_zip_path(output_dir).exists()


def test_write_pack_zip_excludes_prompt_and_keeps_images(tmp_path: Path) -> None:
    output_dir = tmp_path / "lip_gloss" / "ulta"
    images_dir = output_dir / "images"
    snapshots_dir = output_dir / "source_snapshots"
    attribute_tables_dir = output_dir / "attribute_tables"
    images_dir.mkdir(parents=True)
    snapshots_dir.mkdir(parents=True)
    attribute_tables_dir.mkdir(parents=True)
    for name in [
        "summary.json",
        "package_integrity.json",
        "package_warnings.json",
        "pack_manifest.json",
        "filter_comparison.csv",
        "top_seller_pairs.csv",
        "top_seller_triples.csv",
        "category_center_components.csv",
        "differentiating_signals.csv",
        "top_seller_brand_comparison.csv",
        "top_seller_mapped_attribute_comparison.csv",
        "top_seller_review_validation.csv",
        "top_seller_products.csv",
        "innovation_pairs.csv",
        "innovation_triples.csv",
        "resolved_core_comparison.csv",
        "mapped_attribute_comparison.csv",
        "price_comparison.json",
        "price_band_comparison.csv",
        "bundle_review_validation.csv",
        "product_filter_matrix.csv",
        "recent_products.csv",
        "recent_product_pdp_extracts.csv",
        "image_index.csv",
        "prompt_for_pro.txt",
    ]:
        (output_dir / name).write_text("x", encoding="utf-8")
    for name in [
        "manifest.json",
        "attribute_bundle_comparison_table.csv",
        "attribute_bridge_table.csv",
        "rank_weighted_visibility_table.csv",
        "product_signal_evidence_table.csv",
        "attribute_bundle_comparison_table.html",
        "attribute_bridge_table.html",
        "rank_weighted_visibility_table.html",
        "product_signal_evidence_table.html",
    ]:
        (attribute_tables_dir / name).write_text("x", encoding="utf-8")
    for name in [
        "source_manifest.json",
        "listing_observations.csv",
        "filter_observations.csv",
        "mapped_product_attributes.csv",
    ]:
        (snapshots_dir / name).write_text("x", encoding="utf-8")
    (output_dir / "category_center_signals.csv").write_text("x", encoding="utf-8")
    (images_dir / "sample.png").write_text("img", encoding="utf-8")

    zip_path = pack_builder._write_pack_zip(output_dir)

    assert zip_path == tmp_path / "lip_gloss" / "lip_gloss_ulta.zip"

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())

    assert "ulta/prompt_for_pro.txt" not in names
    assert "ulta/package_integrity.json" in names
    assert "ulta/package_warnings.json" in names
    assert "ulta/image_index.csv" in names
    assert "ulta/images/sample.png" in names
    assert "ulta/top_seller_pairs.csv" in names
    assert "ulta/category_center_components.csv" not in names
    assert "ulta/category_center_signals.csv" not in names
    assert "ulta/differentiating_signals.csv" in names
    assert "ulta/source_snapshots/source_manifest.json" in names
    assert "ulta/source_snapshots/listing_observations.csv" in names
    assert "ulta/top_seller_brand_comparison.csv" in names
    assert "ulta/innovation_pairs.csv" in names
    assert "ulta/innovation_triples.csv" in names
    assert "ulta/bundle_review_validation.csv" in names
    assert "ulta/attribute_tables/manifest.json" in names
    assert "ulta/attribute_tables/attribute_bridge_table.csv" in names
    assert "ulta/attribute_tables/product_signal_evidence_table.html" in names


def test_strip_provenance_columns_drops_mapped_suffixes() -> None:
    df = pl.DataFrame(
        {
            "benefit": ["shine"],
            "benefit_mapped": ["bonding"],
            "mapped_form_source_column": ["form"],
            "resolved_form": ["cream"],
        }
    )

    out = pack_builder._strip_provenance_columns(df)

    assert out.columns == ["benefit", "resolved_form"]


def test_top_seller_status_uses_pareto_bucket_a() -> None:
    assert pack_builder._top_seller_status("A") == "top_seller"
    assert pack_builder._top_seller_status("B") == "other"
    assert pack_builder._top_seller_status(None) == "other"


def test_display_sort_mode_label_uses_best_sellers_for_ulta() -> None:
    assert (
        pack_builder._display_sort_mode_label("ulta", "best_sellers") == "best_sellers"
    )
    assert pack_builder._display_sort_mode_label("ulta", "default") == "default"
    assert pack_builder._display_sort_mode_label("saloncentric", "default") == "default"


def test_popularity_rank_rows_uses_best_sellers_for_ulta_when_available() -> None:
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": [
                "best_sellers",
                "best_sellers",
                "best_sellers",
                "new_arrivals",
            ],
            "page": [1, 1, 1, 1],
            "position": [1, 2, 3, 1],
            "parent_product_id": ["p1", "p2", "p3", "p4"],
            "pdp_url": [None, None, None, None],
        }
    )

    out = pack_builder._popularity_rank_rows(
        category_listing_raw,
        retailer="ulta",
    ).sort("listing_identity")

    assert out.get_column("listing_identity").to_list() == ["p1", "p2", "p3"]
    assert out.get_column("pareto_rank").to_list() == [1, 2, 3]
    assert out.get_column("pareto_bucket").to_list() == ["A", "B", "C"]


def test_popularity_rank_rows_can_bucket_against_full_universe() -> None:
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["best_sellers", "best_sellers", "best_sellers"],
            "page": [1, 1, 1],
            "position": [1, 2, 3],
            "parent_product_id": ["p1", "p2", "p3"],
            "pdp_url": [None, None, None],
        }
    )

    out = pack_builder._popularity_rank_rows(
        category_listing_raw,
        retailer="ulta",
        total_universe_count=20,
    ).sort("listing_identity")

    assert out.get_column("listing_identity").to_list() == ["p1", "p2", "p3"]
    assert out.get_column("pareto_bucket").to_list() == ["A", "A", "A"]


def test_popularity_rank_rows_does_not_use_default_as_top_seller() -> None:
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["default", "default", "new_arrivals"],
            "page": [1, 1, 1],
            "position": [1, 2, 1],
            "parent_product_id": ["p1", "p2", "p3"],
            "pdp_url": [None, None, None],
        }
    )

    out = pack_builder._popularity_rank_rows(
        category_listing_raw,
        retailer="ulta",
    ).sort("listing_identity")

    assert out.is_empty()


def test_validate_distinct_ranked_sort_sequences_blocks_identical_newest_and_top_seller() -> (
    None
):
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["new_arrivals"] * 5 + ["best_sellers"] * 5,
            "page": [1] * 10,
            "position": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
            "parent_product_id": ["p1", "p2", "p3", "p4", "p5"] * 2,
            "pdp_url": [None] * 10,
        }
    )

    with pytest.raises(
        pack_builder.PackageBuildSkipped, match="identical product order"
    ):
        pack_builder._validate_distinct_ranked_sort_sequences(
            category_listing_raw,
            retailer="ulta",
            category_key="lipstick",
            recent_sort_mode="new_arrivals",
            top_seller_sort_mode="best_sellers",
        )


def test_validate_distinct_ranked_sort_sequences_warns_high_top_window_overlap() -> (
    None
):
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["new_arrivals"] * 10 + ["best_sellers"] * 10,
            "page": [1] * 20,
            "position": list(range(1, 11)) * 2,
            "parent_product_id": [
                "p1",
                "p2",
                "p3",
                "p4",
                "p5",
                "p6",
                "p7",
                "p8",
                "p9",
                "p10",
                "p2",
                "p1",
                "p3",
                "p4",
                "p5",
                "p6",
                "p7",
                "p8",
                "p11",
                "p12",
            ],
            "pdp_url": [None] * 20,
        }
    )

    quality = pack_builder._validate_distinct_ranked_sort_sequences(
        category_listing_raw,
        retailer="ulta",
        category_key="lipstick",
        recent_sort_mode="new_arrivals",
        top_seller_sort_mode="best_sellers",
    )

    assert quality["status"] == "warning"
    assert quality["analysis_mode"] == "rank_order_contrast"
    assert quality["top_window_overlap_count"] == 8


def test_validate_distinct_ranked_sort_sequences_allows_distinct_newest_and_top_seller() -> (
    None
):
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["new_arrivals"] * 5 + ["best_sellers"] * 5,
            "page": [1] * 10,
            "position": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
            "parent_product_id": [
                "p1",
                "p2",
                "p3",
                "p4",
                "p5",
                "p6",
                "p7",
                "p8",
                "p9",
                "p10",
            ],
            "pdp_url": [None] * 10,
        }
    )

    quality = pack_builder._validate_distinct_ranked_sort_sequences(
        category_listing_raw,
        retailer="ulta",
        category_key="lipstick",
        recent_sort_mode="new_arrivals",
        top_seller_sort_mode="best_sellers",
    )
    assert quality["status"] == "passed"


def test_build_sort_rank_delta_outputs_product_and_attribute_movement() -> None:
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["new_arrivals"] * 5 + ["best_sellers"] * 5,
            "page": [1] * 10,
            "position": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
            "parent_product_id": [
                "p1",
                "p2",
                "p3",
                "p4",
                "p5",
                "p3",
                "p1",
                "p2",
                "p5",
                "p4",
            ],
            "pdp_url": [None] * 10,
        }
    )
    enriched = pl.DataFrame(
        {
            "listing_identity": ["p1", "p2", "p3", "p4", "p5"],
            "parent_product_id": ["p1", "p2", "p3", "p4", "p5"],
            "brand": ["A", "A", "B", "B", "C"],
            "product_name": ["One", "Two", "Three", "Four", "Five"],
            "material": ["canvas", "canvas", "leather", "suede", "leather"],
        }
    )

    products = pack_builder._build_sort_rank_delta_products(
        enriched=enriched,
        category_listing_raw=category_listing_raw,
        recent_sort_mode="new_arrivals",
        top_seller_sort_mode="best_sellers",
        attribute_columns=["material"],
    )
    attributes = pack_builder._build_sort_rank_delta_attributes(
        products,
        attribute_columns=["material"],
    )

    p3 = products.filter(pl.col("parent_product_id") == "p3").to_dicts()[0]
    assert p3["newest_rank"] == 3
    assert p3["top_seller_rank"] == 1
    assert p3["rank_delta"] == 2
    assert p3["rank_delta_status"] == "sales_rank_lead"
    leather = attributes.filter(pl.col("attribute_value") == "leather").to_dicts()[0]
    assert leather["product_count"] == 2
    assert leather["sales_rank_lead_count"] == 2
    assert leather["mean_rank_delta"] == 1.5


def test_build_sort_rank_delta_products_deduplicates_attribute_columns() -> None:
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["new_arrivals", "best_sellers"],
            "page": [1, 1],
            "position": [1, 2],
            "parent_product_id": ["p1", "p1"],
            "pdp_url": [None, None],
        }
    )
    enriched = pl.DataFrame(
        {
            "listing_identity": ["p1"],
            "parent_product_id": ["p1"],
            "brand": ["Brand A"],
            "product_name": ["One"],
        }
    )

    products = pack_builder._build_sort_rank_delta_products(
        enriched=enriched,
        category_listing_raw=category_listing_raw,
        recent_sort_mode="new_arrivals",
        top_seller_sort_mode="best_sellers",
        attribute_columns=["brand"],
    )

    assert products.columns.count("brand") == 1
    assert products.get_column("brand").to_list() == ["Brand A"]


def test_build_product_universe_keeps_only_ranked_listing_products() -> None:
    category_listing_raw = pl.DataFrame(
        {
            "category_key": ["cashmere_sweaters"],
            "parent_product_id": ["p1"],
            "product_name": ["Listed product"],
            "pdp_url": ["https://example.test/p1"],
            "has_new_badge": [True],
        }
    )
    category_filters = pl.DataFrame(
        {
            "category_key": ["cashmere_sweaters", "cashmere_sweaters"],
            "parent_product_id": ["p1", "p2"],
            "pdp_url": ["https://example.test/p1", "https://example.test/p2"],
            "filter_family": ["color", "color"],
            "filter_value": ["Blue", "Black"],
        }
    )
    mapped_export_df = pl.DataFrame(
        {
            "parent_product_id": ["p2", "p3"],
            "category_key": ["cashmere_sweaters", "cashmere_sweaters"],
            "product_name": ["Filter-only product", "Export-only product"],
            "pdp_url": ["https://example.test/p2", "https://example.test/p3"],
        }
    )

    out = pack_builder._build_product_universe(
        category_listing_raw=category_listing_raw,
        category_filters=pack_builder._with_listing_identity(category_filters),
        mapped_export_df=mapped_export_df,
    ).sort("listing_identity")

    assert out.get_column("listing_identity").to_list() == ["p1"]
    assert out.get_column("product_name").to_list() == ["Listed product"]
    assert out.get_column("has_new_badge").to_list() == [True]


def test_apply_recent_status_uses_full_universe_for_cutoff() -> None:
    product_universe = pl.DataFrame(
        {
            "listing_identity": [f"p{index}" for index in range(1, 21)],
            "category_key": ["cashmere_sweaters"] * 20,
            "parent_product_id": [f"p{index}" for index in range(1, 21)],
            "product_name": [f"Product {index}" for index in range(1, 21)],
            "pdp_url": [None] * 20,
            "has_new_badge": [False] * 20,
        }
    )
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["new_arrivals", "new_arrivals", "new_arrivals"],
            "page": [1, 1, 1],
            "position": [1, 2, 3],
            "parent_product_id": ["p1", "p2", "p3"],
            "pdp_url": [None, None, None],
        }
    )

    out = pack_builder._apply_recent_status(
        product_universe,
        category_listing_raw,
        recent_share=0.2,
        recent_sort_mode="new_arrivals",
    ).sort("listing_identity")

    by_id = {row["listing_identity"]: row["listing_status"] for row in out.to_dicts()}
    assert by_id["p1"] == "recent"
    assert by_id["p2"] == "recent"
    assert by_id["p3"] == "recent"
    assert by_id["p4"] == "rest"


def test_build_brand_top_seller_comparison_over_indexes_winning_brands() -> None:
    df = pl.DataFrame(
        {
            "brand": ["A", "A", "A", "B", "B", "C"],
            "top_seller_status": [
                "top_seller",
                "top_seller",
                "other",
                "top_seller",
                "other",
                "other",
            ],
        }
    )

    out = pack_builder._build_brand_top_seller_comparison(df)
    rows = {row["brand"]: row for row in out.to_dicts()}

    assert rows["A"]["catalog_count"] == 3
    assert rows["A"]["top_seller_count"] == 2
    assert rows["A"]["top_seller_share_of_brand"] == 2 / 3
    assert rows["A"]["over_index_vs_catalog_share"] > 1.0
    assert rows["C"]["top_seller_count"] == 0


def test_from_dicts_with_full_inference_handles_late_string_values() -> None:
    rows = [{"mixed": None}, {"mixed": "cheek"}]

    out = pl.from_dicts(rows, infer_schema_length=len(rows))

    assert out.to_dicts() == rows


def test_build_value_comparison_keeps_string_values() -> None:
    df = pl.DataFrame(
        {
            "listing_status": ["recent", "rest", "rest"],
            "resolved_finish": ["high shine", "matte", None],
        }
    )

    out = pack_builder._build_value_comparison(
        df=df,
        attribute_columns=["resolved_finish"],
    )

    assert out.height == 2
    assert set(out.get_column("attribute_value").to_list()) == {"high shine", "matte"}


def test_build_value_comparison_handles_attribute_only_present_in_rest() -> None:
    df = pl.DataFrame(
        {
            "listing_status": ["rest", "rest"],
            "resolved_finish": ["matte", "natural"],
        }
    )

    out = pack_builder._build_value_comparison(
        df=df,
        attribute_columns=["resolved_finish"],
    )

    assert out.height == 2
    assert out.get_column("count_recent").to_list() == [0, 0]


def test_bundle_items_ignore_missing_and_placeholders() -> None:
    row = {
        "resolved_form": "balm",
        "resolved_finish": "matte",
        "benefits": "peptide",
        "resolved_coverage": "N/A",
        "texture feel": "not in taxonomy",
        "packaging features": None,
    }

    items = pack_builder._bundle_items_for_row(
        row,
        attribute_columns=[
            "resolved_form",
            "resolved_finish",
            "benefits",
            "resolved_coverage",
            "texture feel",
            "packaging features",
        ],
    )

    assert items == [
        ("benefits", "peptide"),
        ("finish", "matte"),
        ("form", "balm"),
    ]


def test_bundle_items_canonicalize_format_to_form() -> None:
    row = {
        "format": "stick",
        "form": "stick",
        "resolved_form": "stick",
    }

    items = pack_builder._bundle_items_for_row(
        row,
        attribute_columns=["format", "form", "resolved_form"],
    )

    assert items == [("form", "stick")]


def test_analysis_attribute_column_rejects_provenance_fields() -> None:
    assert not pack_builder._is_analysis_attribute_column("form_authority_source")
    assert not pack_builder._is_analysis_attribute_column("finish authority source")
    assert not pack_builder._is_analysis_attribute_column("mapped_form_source_column")
    assert not pack_builder._is_analysis_attribute_column("our_form")
    assert not pack_builder._is_analysis_attribute_column("review_1_comment")
    assert pack_builder._is_analysis_attribute_column("skin benefits")


def test_flatten_review_fields_exports_five_deduped_review_snippets() -> None:
    payload = {
        "reviews": [
            {
                "review_id": "r1",
                "headline": "Easy",
                "comment": "Easy to blend.",
                "rating": 5,
                "created_date": "2026-01-01",
            },
            {
                "review_id": "r2",
                "headline": "Smooth",
                "comment": "Smooth finish.",
                "rating": 4,
                "created_date": "2026-01-02",
            },
            {
                "review_id": "r3",
                "headline": "Wear",
                "comment": "Lasts all day.",
                "rating": 5,
                "created_date": "2026-01-03",
            },
            {
                "review_id": "r4",
                "headline": "Shade",
                "comment": "Shade is accurate.",
                "rating": 4,
                "created_date": "2026-01-04",
            },
            {
                "review_id": "r5",
                "headline": "Packaging",
                "comment": "Applicator is tidy.",
                "rating": 5,
                "created_date": "2026-01-05",
            },
            {
                "review_id": "r5",
                "headline": "Packaging duplicate",
                "comment": "This duplicate should not export.",
                "rating": 1,
                "created_date": "2026-01-06",
            },
            {
                "review_id": "r6",
                "headline": "Overflow",
                "comment": "This sixth unique review stays out of columns.",
                "rating": 3,
                "created_date": "2026-01-07",
            },
        ]
    }

    out = pack_builder._flatten_review_fields(payload)
    reviews_json = json.loads(out["reviews_json"])

    assert out["review_snippet_count"] == 5
    assert out["review_4_comment"] == "Shade is accurate."
    assert out["review_5_comment"] == "Applicator is tidy."
    assert "review_6_comment" not in out
    assert len(reviews_json) == 5
    assert reviews_json[4]["comment"] == "Applicator is tidy."


def test_ulta_bundle_attribute_columns_use_category_allowlist() -> None:
    columns = [
        "resolved_form",
        "resolved_finish",
        "form_authority_source",
        "spf",
        "skin benefits",
    ]

    out = pack_builder._bundle_attribute_columns(
        retailer="ulta",
        category_key="blush",
        available_columns=columns,
        default_columns=columns,
    )

    assert out == ["resolved_form", "resolved_finish", "skin benefits"]


def test_bundle_items_include_one_hot_boolean_attributes() -> None:
    row = {
        "product benefit": "grey coverage",
        "ingredient_preference__vegan": True,
        "ingredient_preference__unknown": False,
        "hair_condition__breakage": "true",
        "hair_condition__not_in_taxonomy": "false",
    }

    items = pack_builder._bundle_items_for_row(
        row,
        attribute_columns=[
            "product benefit",
            "ingredient_preference__vegan",
            "ingredient_preference__unknown",
            "hair_condition__breakage",
            "hair_condition__not_in_taxonomy",
        ],
    )

    assert items == [
        ("hair condition", "breakage"),
        ("ingredient preference", "vegan"),
        ("product benefit", "grey coverage"),
    ]


def test_products_without_any_attributes_counts_missing_and_placeholders() -> None:
    df = pl.DataFrame(
        {
            "color": ["Blue", None, "not in taxonomy", ""],
            "neckline": [None, "Crewneck", "N/A", ""],
            "ignored": ["", "", "present", ""],
        }
    )

    count = pack_builder._products_without_any_attributes(
        df,
        attribute_columns=["color", "neckline"],
    )

    assert count == 2


def test_build_bundle_signals_keeps_cross_brand_recent_pairs() -> None:
    df = pl.DataFrame(
        {
            "listing_identity": ["r1", "r2", "r3", "r4", "o1", "o2"],
            "listing_status": ["recent", "recent", "recent", "recent", "rest", "rest"],
            "brand": ["Brand A", "Brand B", "Brand C", "Brand A", "Brand A", "Brand D"],
            "product_name": ["P1", "P2", "P3", "P4", "Old1", "Old2"],
            "resolved_form": ["balm", "balm", "balm", "stick", "balm", "stick"],
            "resolved_finish": ["matte", "matte", "matte", "matte", "matte", "matte"],
            "benefits": ["peptide", "peptide", "peptide", "peptide", "peptide", None],
        }
    )

    out = pack_builder._build_bundle_signals(
        df=df,
        attribute_columns=["resolved_form", "resolved_finish", "benefits"],
        bundle_size=2,
    )

    rows = out.to_dicts()
    assert any(
        row["bundle_key"] == "benefits=peptide + form=balm"
        and row["count_recent"] == 3
        and row["recent_brand_count"] == 3
        for row in rows
    )
    assert all("resolved_coverage" not in row["bundle_key"] for row in rows)


def test_build_bundle_signals_drops_sparse_triples() -> None:
    df = pl.DataFrame(
        {
            "listing_identity": ["r1", "r2", "o1", "o2"],
            "listing_status": ["recent", "recent", "rest", "rest"],
            "brand": ["Brand A", "Brand B", "Brand A", "Brand B"],
            "product_name": ["P1", "P2", "Old1", "Old2"],
            "resolved_form": ["balm", "balm", "balm", "balm"],
            "resolved_finish": ["matte", "matte", "matte", "matte"],
            "benefits": ["peptide", None, None, None],
        }
    )

    out = pack_builder._build_bundle_signals(
        df=df,
        attribute_columns=["resolved_form", "resolved_finish", "benefits"],
        bundle_size=3,
    )

    assert out.height == 0


def test_build_bundle_signals_adds_recent_sales_validation_fields() -> None:
    df = pl.DataFrame(
        {
            "listing_identity": ["r1", "r2", "r3", "o1", "o2"],
            "listing_status": ["recent", "recent", "recent", "rest", "rest"],
            "brand": ["Brand A", "Brand B", "Brand C", "Brand A", "Brand D"],
            "product_name": ["P1", "P2", "P3", "Old1", "Old2"],
            "resolved_form": ["balm", "balm", "balm", "balm", "stick"],
            "resolved_finish": ["matte", "matte", "matte", "matte", "matte"],
            "benefits": ["peptide", "peptide", "peptide", "peptide", None],
            "pareto_rank": [5, 23, None, 80, None],
            "pareto_bucket": ["A", "B", None, "C", None],
            "sales_share": [0.08, 0.03, None, 0.01, None],
        }
    )

    out = pack_builder._build_bundle_signals(
        df=df,
        attribute_columns=["resolved_form", "resolved_finish", "benefits"],
        bundle_size=2,
    )

    row = next(
        row
        for row in out.to_dicts()
        if row["bundle_key"] == "benefits=peptide + form=balm"
    )

    assert row["recent_products_with_pareto"] == 2
    assert row["recent_pareto_a_count"] == 1
    assert row["recent_pareto_b_count"] == 1
    assert row["recent_pareto_c_count"] == 0
    assert row["recent_pareto_ab_count"] == 2
    assert row["best_recent_pareto_rank"] == 5
    assert row["prevalence_ratio"] == 2.0
    assert row["recent_sales_share_sum"] == 0.11
    assert row["recent_sales_share_mean"] == 0.055
    assert row["recent_top_pareto_products"] == "P1 (#5) | P2 (#23)"


def test_launch_package_integrity_passes_when_signal_tables_recompute() -> None:
    product_filter_matrix = pl.DataFrame(
        {
            "listing_identity": ["r1", "r2", "r3", "o1"],
            "listing_status": ["recent", "recent", "recent", "rest"],
            "top_seller_status": ["other", "other", "other", "other"],
            "sale_pressure_status": [
                "not_observed_sale_pressure",
                "not_observed_sale_pressure",
                "not_observed_sale_pressure",
                "not_observed_sale_pressure",
            ],
            "brand": ["Brand A", "Brand B", "Brand C", "Brand D"],
            "product_name": ["P1", "P2", "P3", "Old1"],
            "parent_product_id": ["r1", "r2", "r3", "o1"],
            "resolved_form": ["balm", "balm", "balm", "stick"],
            "benefits": ["peptide", "peptide", "peptide", None],
        }
    )
    attribute_columns = ["resolved_form", "benefits"]
    innovation_pairs = pack_builder._expected_signal_table(
        df=product_filter_matrix,
        attribute_columns=attribute_columns,
        bundle_size=2,
        signal_layer="innovation",
    )

    audit = pack_builder._build_launch_package_integrity_audit(
        category_key="lip_balm",
        product_filter_matrix=product_filter_matrix,
        recent_products=product_filter_matrix.filter(
            pl.col("listing_status") == "recent"
        ),
        top_seller_products=product_filter_matrix.filter(
            pl.col("top_seller_status") == "top_seller"
        ),
        sale_pressure_products=product_filter_matrix.filter(
            pl.col("sale_pressure_status") == "sale_pressure"
        ),
        innovation_pairs=innovation_pairs,
        innovation_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        top_seller_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        top_seller_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        sale_pressure_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        sale_pressure_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        bundle_attribute_columns=attribute_columns,
    )

    assert audit["status"] == "pass"
    assert audit["summary"]["failure_count"] == 0
    innovation_check = next(
        check
        for check in audit["checks"]
        if check["check_id"] == "innovation_pairs_recompute"
    )
    assert innovation_check["expected_row_count"] == 1


def test_launch_package_integrity_fails_when_signal_table_drops_rows() -> None:
    product_filter_matrix = pl.DataFrame(
        {
            "listing_identity": ["r1", "r2", "r3", "o1"],
            "listing_status": ["recent", "recent", "recent", "rest"],
            "top_seller_status": ["other", "other", "other", "other"],
            "sale_pressure_status": [
                "not_observed_sale_pressure",
                "not_observed_sale_pressure",
                "not_observed_sale_pressure",
                "not_observed_sale_pressure",
            ],
            "brand": ["Brand A", "Brand B", "Brand C", "Brand D"],
            "product_name": ["P1", "P2", "P3", "Old1"],
            "parent_product_id": ["r1", "r2", "r3", "o1"],
            "resolved_form": ["balm", "balm", "balm", "stick"],
            "benefits": ["peptide", "peptide", "peptide", None],
        }
    )

    audit = pack_builder._build_launch_package_integrity_audit(
        category_key="lip_balm",
        product_filter_matrix=product_filter_matrix,
        recent_products=product_filter_matrix.filter(
            pl.col("listing_status") == "recent"
        ),
        top_seller_products=product_filter_matrix.filter(
            pl.col("top_seller_status") == "top_seller"
        ),
        sale_pressure_products=product_filter_matrix.filter(
            pl.col("sale_pressure_status") == "sale_pressure"
        ),
        innovation_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        innovation_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        top_seller_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        top_seller_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        sale_pressure_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        sale_pressure_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        bundle_attribute_columns=["resolved_form", "benefits"],
    )

    assert audit["status"] == "fail"
    assert audit["summary"]["failure_count"] == 1
    assert audit["issues"][0]["check_id"] == "innovation_pairs_recompute"
    assert audit["issues"][0]["missing_bundle_count"] == 1


def test_launch_package_integrity_fails_when_matrix_differs_from_source_snapshots() -> (
    None
):
    source_listing = pl.DataFrame(
        [
            {
                "crawl_ts": "2026-05-01T00:00:00Z",
                "retailer": "ulta",
                "category_key": "lip_balm",
                "source_surface": "category",
                "sort_mode": "new_arrivals",
                "page": 1,
                "position": 1,
                "pdp_url": "https://example.test/p1",
                "parent_product_id": "p1",
                "product_name": "Peptide Balm",
                "brand": "Brand A",
                "has_new_badge": True,
                "listing_url": "https://example.test/listing",
            },
            {
                "crawl_ts": "2026-05-01T00:00:00Z",
                "retailer": "ulta",
                "category_key": "lip_balm",
                "source_surface": "category",
                "sort_mode": "new_arrivals",
                "page": 1,
                "position": 2,
                "pdp_url": "https://example.test/p2",
                "parent_product_id": "p2",
                "product_name": "Tint Balm",
                "brand": "Brand B",
                "has_new_badge": False,
                "listing_url": "https://example.test/listing",
            },
            {
                "crawl_ts": "2026-05-01T00:00:00Z",
                "retailer": "ulta",
                "category_key": "lip_balm",
                "source_surface": "category",
                "sort_mode": "best_sellers",
                "page": 1,
                "position": 1,
                "pdp_url": "https://example.test/p2",
                "parent_product_id": "p2",
                "product_name": "Tint Balm",
                "brand": "Brand B",
                "has_new_badge": False,
                "listing_url": "https://example.test/listing",
            },
            {
                "crawl_ts": "2026-05-01T00:00:00Z",
                "retailer": "ulta",
                "category_key": "lip_balm",
                "source_surface": "category",
                "sort_mode": "best_sellers",
                "page": 1,
                "position": 2,
                "pdp_url": "https://example.test/p1",
                "parent_product_id": "p1",
                "product_name": "Peptide Balm",
                "brand": "Brand A",
                "has_new_badge": True,
                "listing_url": "https://example.test/listing",
            },
        ]
    )
    source_filters = pl.DataFrame(
        [
            {
                "crawl_ts": "2026-05-01T00:00:00Z",
                "retailer": "ulta",
                "category_key": "lip_balm",
                "filter_family": "finish",
                "filter_value": "Glossy",
                "source_surface": "filter",
                "pdp_url": "https://example.test/p1",
                "parent_product_id": "p1",
                "page": 1,
                "position": 1,
                "listing_url": "https://example.test/listing",
            }
        ]
    )
    source_attributes = pl.DataFrame(
        [
            {
                "parent_product_id": "p1",
                "product_name": "Peptide Balm",
                "brand": "Brand A",
                "category_key": "lip_balm",
                "form": "balm",
            },
            {
                "parent_product_id": "p2",
                "product_name": "Tint Balm",
                "brand": "Brand B",
                "category_key": "lip_balm",
                "form": "balm",
            },
        ]
    )
    expected_matrix = pack_builder._build_source_expected_product_matrix(
        retailer="ulta",
        category_key="lip_balm",
        source_listing_observations=source_listing,
        source_filter_observations=source_filters,
        source_mapped_attributes=source_attributes,
        recent_share=0.5,
        recent_sort_mode="new_arrivals",
        sale_pressure_sort_mode=None,
    )
    product_filter_matrix = expected_matrix.with_columns(
        pl.when(pl.col("listing_identity") == "p1")
        .then(pl.lit("rest"))
        .otherwise(pl.col("listing_status"))
        .alias("listing_status")
    )

    audit = pack_builder._build_launch_package_integrity_audit(
        retailer="ulta",
        category_key="lip_balm",
        source_category_key="lip_balm",
        product_filter_matrix=product_filter_matrix,
        recent_products=product_filter_matrix.filter(
            pl.col("listing_status") == "recent"
        ),
        top_seller_products=product_filter_matrix.filter(
            pl.col("top_seller_status") == "top_seller"
        ),
        sale_pressure_products=product_filter_matrix.filter(
            pl.col("sale_pressure_status") == "sale_pressure"
        ),
        innovation_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        innovation_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        top_seller_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        top_seller_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        sale_pressure_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        sale_pressure_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        bundle_attribute_columns=["form"],
        source_listing_observations=source_listing,
        source_filter_observations=source_filters,
        source_mapped_attributes=source_attributes,
        recent_share=0.5,
        recent_sort_mode="new_arrivals",
        sale_pressure_sort_mode=None,
        source_snapshot_manifest={"snapshots": {}},
    )

    source_issues = [
        issue
        for issue in audit["issues"]
        if issue["check_id"] == "product_filter_matrix_source_rebuild"
    ]

    assert audit["status"] == "fail"
    assert source_issues
    assert source_issues[0]["value_mismatch_count"] == 1
    assert source_issues[0]["value_mismatch_samples"][0]["column"] == "listing_status"


def test_source_expected_matrix_uses_package_canonical_filter_values() -> None:
    source_listing = pl.DataFrame(
        [
            {
                "crawl_ts": "2026-05-01T00:00:00Z",
                "retailer": "ulta",
                "category_key": "blush",
                "source_surface": "category",
                "sort_mode": "new_arrivals",
                "page": 1,
                "position": 1,
                "pdp_url": "https://example.test/p1",
                "parent_product_id": "p1",
                "product_name": "Glow Blush",
                "brand": "Brand A",
                "has_new_badge": True,
                "listing_url": "https://example.test/listing",
            }
        ]
    )
    source_filters = pl.DataFrame(
        [
            {
                "crawl_ts": "2026-05-01T00:00:00Z",
                "retailer": "ulta",
                "category_key": "blush",
                "filter_family": "finish",
                "filter_value": "radiant",
                "source_surface": "filter",
                "pdp_url": "https://example.test/p1",
                "parent_product_id": "p1",
                "page": 1,
                "position": 1,
                "listing_url": "https://example.test/listing",
            },
            {
                "crawl_ts": "2026-05-01T00:00:00Z",
                "retailer": "ulta",
                "category_key": "blush",
                "filter_family": "form",
                "filter_value": "cream",
                "source_surface": "filter",
                "pdp_url": "https://example.test/p1",
                "parent_product_id": "p1",
                "page": 1,
                "position": 1,
                "listing_url": "https://example.test/listing",
            },
        ]
    )
    source_attributes = pl.DataFrame(
        [
            {
                "parent_product_id": "p1",
                "product_name": "Glow Blush",
                "brand": "Brand A",
                "category_key": "blush",
                "finish": "natural",
                "form": "stick",
            }
        ]
    )

    expected_matrix = pack_builder._build_source_expected_product_matrix(
        retailer="ulta",
        category_key="blush",
        source_listing_observations=source_listing,
        source_filter_observations=source_filters,
        source_mapped_attributes=source_attributes,
        recent_share=1.0,
        recent_sort_mode="new_arrivals",
        sale_pressure_sort_mode=None,
    )

    row = expected_matrix.row(0, named=True)
    assert row["finish"] == "Luminous"
    assert row["form"] == "Cream pot"


def test_launch_package_integrity_fails_when_package_has_no_data_or_attributes() -> (
    None
):
    product_filter_matrix = pl.DataFrame(
        schema={
            "listing_identity": pl.Utf8,
            "listing_status": pl.Utf8,
            "top_seller_status": pl.Utf8,
            "sale_pressure_status": pl.Utf8,
            "brand": pl.Utf8,
            "product_name": pl.Utf8,
            "parent_product_id": pl.Utf8,
        }
    )

    audit = pack_builder._build_launch_package_integrity_audit(
        category_key="lip_balm",
        product_filter_matrix=product_filter_matrix,
        recent_products=product_filter_matrix,
        top_seller_products=product_filter_matrix,
        sale_pressure_products=product_filter_matrix,
        innovation_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        innovation_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        top_seller_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        top_seller_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        sale_pressure_pairs=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        sale_pressure_triples=pl.DataFrame(schema={"bundle_key": pl.Utf8}),
        bundle_attribute_columns=[],
    )

    issue_ids = {issue["check_id"] for issue in audit["issues"]}

    assert audit["status"] == "fail"
    assert "product_filter_matrix_nonempty" in issue_ids
    assert "bundle_attribute_inputs_nonempty" in issue_ids


def test_signal_insight_demotes_observed_category_center_bundle_rows() -> None:
    bundle_df = pl.DataFrame(
        [
            {
                "bundle_size": 2,
                "bundle_key": "color=White + material=Leather",
                "bundle_label": "White + Leather",
                "count_top_seller": 100,
                "count_other": 200,
                "top_seller_brand_count": 20,
                "other_brand_count": 40,
                "pct_top_seller": 0.60,
                "pct_other": 0.30,
                "delta": 0.30,
            },
            {
                "bundle_size": 2,
                "bundle_key": "color=White + design detail=Logo Detail",
                "bundle_label": "White + Logo Detail",
                "count_top_seller": 80,
                "count_other": 160,
                "top_seller_brand_count": 18,
                "other_brand_count": 36,
                "pct_top_seller": 0.50,
                "pct_other": 0.25,
                "delta": 0.25,
            },
            {
                "bundle_size": 2,
                "bundle_key": "silhouette=Retro Court + material=Leather",
                "bundle_label": "Retro Court + Leather",
                "count_top_seller": 100,
                "count_other": 120,
                "top_seller_brand_count": 12,
                "other_brand_count": 20,
                "pct_top_seller": 0.30,
                "pct_other": 0.12,
                "delta": 0.18,
            },
            {
                "bundle_size": 2,
                "bundle_key": "bundle-b",
                "bundle_label": "Terrace + Logo Detail",
                "count_top_seller": 60,
                "count_other": 70,
                "top_seller_brand_count": 8,
                "other_brand_count": 14,
                "pct_top_seller": 0.15,
                "pct_other": 0.03,
                "delta": 0.12,
            },
        ]
    )
    category_center_components = pl.DataFrame(
        {
            "attribute_family": ["color", "material"],
            "attribute_value": ["White", "Leather"],
        }
    )

    with_metadata = pack_builder._with_signal_insight_metadata(
        bundle_df,
        signal_layer="winning_now",
        category_center_components=category_center_components,
    )
    selected, context = pack_builder._split_signal_rows_by_usefulness(with_metadata)

    assert selected.get_column("bundle_label").to_list() == [
        "White + Logo Detail",
        "Terrace + Logo Detail",
        "Retro Court + Leather",
    ]
    assert selected.get_column("signal_usefulness").to_list() == [
        "supporting_signal",
        "headline_signal",
        "supporting_signal",
    ]
    assert selected.get_column("signal_role").to_list() == [
        "supporting_differentiation",
        "differentiating",
        "supporting_differentiation",
    ]
    assert context.get_column("bundle_label").to_list() == ["White + Leather"]
    assert context.get_column("signal_usefulness").unique().to_list() == [
        "category_center"
    ]
    assert context.get_column("signal_role").unique().to_list() == ["category_center"]


def test_pro_visible_signal_table_hides_internal_category_center_count() -> None:
    signal_df = pl.DataFrame(
        {
            "bundle_label": ["White + Logo Detail"],
            "category_center_component_count": [1],
            "differentiating_component_count": [1],
        }
    )

    out = pack_builder._pro_visible_signal_table(signal_df)

    assert "category_center_component_count" not in out.columns
    assert "differentiating_component_count" in out.columns


def test_category_center_component_table_uses_rank_weight_and_assortment() -> None:
    products = pl.DataFrame(
        {
            "listing_identity": ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"],
            "pareto_rank": [1, 2, 3, 4, 5, None, None, None],
            "color": [
                "White",
                "White",
                "White",
                "White",
                "Black",
                "White",
                "White",
                "Black",
            ],
            "material": [
                "Leather",
                "Leather",
                "Leather",
                "Canvas",
                "Leather",
                "Leather",
                "Leather",
                "Canvas",
            ],
        }
    )

    out = pack_builder._category_center_component_table(
        products,
        attribute_columns=["color", "material"],
    )

    assert out.get_column("attribute_value").to_list() == ["White", "Leather"]
    assert out.get_column("signal_role").unique().to_list() == ["category_center"]
    assert out.get_column("ranked_product_count").to_list() == [4, 4]
    assert "rank_weighted_presence" not in out.columns


def test_bucket_from_rank_uses_20_30_50_split() -> None:
    assert pack_builder._bucket_from_rank(2, 10) == "A"
    assert pack_builder._bucket_from_rank(5, 10) == "B"
    assert pack_builder._bucket_from_rank(6, 10) == "C"


def test_apply_common_traction_layer_prefers_most_popular_rank() -> None:
    df = pl.DataFrame(
        {
            "listing_identity": ["p1", "p2", "p3"],
            "pareto_rank": [99, None, None],
            "pareto_bucket": ["C", None, None],
        }
    )
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["most_popular", "most_popular", "most_popular"],
            "page": [1, 1, 1],
            "position": [1, 2, 3],
            "parent_product_id": ["p1", "p2", "p3"],
            "pdp_url": [None, None, None],
        }
    )

    out = pack_builder._apply_common_traction_layer(
        df,
        category_listing_raw=category_listing_raw,
        retailer="saloncentric",
    ).sort("listing_identity")

    assert out.get_column("pareto_rank").to_list() == [1, 2, 3]
    assert out.get_column("pareto_bucket").to_list() == ["A", "B", "C"]


def test_apply_common_traction_layer_prefers_top_sellers_for_cosmoprofbeauty() -> None:
    df = pl.DataFrame(
        {
            "listing_identity": ["p1", "p2", "p3"],
            "pareto_rank": [None, None, None],
            "pareto_bucket": [None, None, None],
        }
    )
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["top_sellers", "top_sellers", "top_sellers"],
            "page": [1, 1, 1],
            "position": [1, 2, 3],
            "parent_product_id": ["p1", "p2", "p3"],
            "pdp_url": [None, None, None],
        }
    )

    out = pack_builder._apply_common_traction_layer(
        df,
        category_listing_raw=category_listing_raw,
        retailer="cosmoprofbeauty",
    ).sort("listing_identity")

    assert out.get_column("pareto_rank").to_list() == [1, 2, 3]
    assert out.get_column("pareto_bucket").to_list() == ["A", "B", "C"]


def test_apply_common_traction_layer_handles_discovery_only_ranks() -> None:
    df = pl.DataFrame(
        {
            "listing_identity": ["p1", "p2", "p3"],
            "discovery_pareto_rank": [1, 2, 3],
            "discovery_pareto_bucket": ["A", "B", "C"],
        }
    )
    category_listing_raw = pl.DataFrame(
        {
            "sort_mode": ["top_sellers", "top_sellers", "top_sellers"],
            "page": [1, 1, 1],
            "position": [1, 2, 3],
            "parent_product_id": ["p1", "p2", "p3"],
            "pdp_url": [None, None, None],
        }
    )

    out = pack_builder._apply_common_traction_layer(
        df,
        category_listing_raw=category_listing_raw,
        retailer="cosmoprofbeauty",
    ).sort("listing_identity")

    assert out.get_column("pareto_rank").to_list() == [1, 2, 3]
    assert out.get_column("pareto_bucket").to_list() == ["A", "B", "C"]


def test_build_bundle_review_validation_limits_to_reviewed_recent_matches() -> None:
    recent_products = pl.DataFrame(
        {
            "product_name": ["P1", "P2", "P3"],
            "brand": ["Brand A", "Brand B", "Brand C"],
            "parent_product_id": ["id1", "id2", "id3"],
            "pareto_rank": [5, 18, None],
            "pareto_bucket": ["A", "B", None],
            "sales_share": [0.08, 0.03, None],
            "rating": [4.8, 4.4, 4.9],
            "review_count": [120, 44, 0],
            "reviews_positive_headline": ["Loved it", "Great", None],
            "reviews_positive_comment": ["Hydrating and shiny", "Comfortable", None],
            "reviews_negative_headline": [None, "Too thick", None],
            "reviews_negative_comment": [None, "A bit heavy", None],
            "review_1_headline": ["Top review", "Nice", None],
            "review_1_comment": ["Super glossy", "Good balm feel", None],
            "review_1_rating": [5.0, 4.0, None],
            "review_1_created_date": ["2026-01-01", "2025-12-01", None],
            "review_2_headline": [None, None, None],
            "review_2_comment": [None, None, None],
            "review_2_rating": [None, None, None],
            "review_2_created_date": [None, None, None],
            "review_3_headline": [None, None, None],
            "review_3_comment": [None, None, None],
            "review_3_rating": [None, None, None],
            "review_3_created_date": [None, None, None],
            "resolved_form": ["balm", "balm", "stick"],
            "resolved_finish": ["high shine", "high shine", "high shine"],
            "benefits": ["peptide", "peptide", "peptide"],
        }
    )
    innovation_pairs = pl.DataFrame(
        {
            "bundle_size": [2],
            "bundle_key": ["benefits=peptide + form=balm"],
            "bundle_label": ["peptide + balm"],
        }
    )
    innovation_triples = pl.DataFrame(
        schema={"bundle_size": pl.Int64, "bundle_key": pl.Utf8, "bundle_label": pl.Utf8}
    )

    out = pack_builder._build_bundle_review_validation(
        recent_products=recent_products,
        innovation_pairs=innovation_pairs,
        innovation_triples=innovation_triples,
        attribute_columns=["resolved_form", "resolved_finish", "benefits"],
    )

    assert out.height == 2
    assert out.get_column("product_name").to_list() == ["P1", "P2"]
    assert out.get_column("bundle_key").unique().to_list() == [
        "benefits=peptide + form=balm"
    ]
    assert "review_5_comment" in out.columns


def test_build_bundle_review_validation_respects_bundle_and_product_caps() -> None:
    recent_products = pl.DataFrame(
        {
            "product_name": ["P1", "P2", "P3", "P4"],
            "brand": ["Brand A", "Brand B", "Brand C", "Brand D"],
            "parent_product_id": ["id1", "id2", "id3", "id4"],
            "pareto_rank": [1, 2, 3, 4],
            "pareto_bucket": ["A", "A", "A", "A"],
            "sales_share": [0.08, 0.07, 0.06, 0.05],
            "rating": [4.8, 4.7, 4.6, 4.5],
            "review_count": [120, 90, 80, 70],
            "reviews_positive_headline": ["Loved it"] * 4,
            "reviews_positive_comment": ["Hydrating and shiny"] * 4,
            "reviews_negative_headline": [None] * 4,
            "reviews_negative_comment": [None] * 4,
            "review_1_headline": ["Top review"] * 4,
            "review_1_comment": ["Super glossy"] * 4,
            "review_1_rating": [5.0, 4.0, 4.5, 4.2],
            "review_1_created_date": ["2026-01-01"] * 4,
            "review_2_headline": [None] * 4,
            "review_2_comment": [None] * 4,
            "review_2_rating": [None] * 4,
            "review_2_created_date": [None] * 4,
            "review_3_headline": [None] * 4,
            "review_3_comment": [None] * 4,
            "review_3_rating": [None] * 4,
            "review_3_created_date": [None] * 4,
            "resolved_form": ["balm", "balm", "balm", "stick"],
            "resolved_finish": ["high shine", "high shine", "high shine", "high shine"],
            "benefits": ["peptide", "peptide", "peptide", "peptide"],
        }
    )
    innovation_pairs = pl.DataFrame(
        {
            "bundle_size": [2, 2],
            "bundle_key": [
                "benefits=peptide + form=balm",
                "benefits=peptide + finish=high shine",
            ],
            "bundle_label": ["peptide + balm", "peptide + high shine"],
        }
    )
    innovation_triples = pl.DataFrame(
        {
            "bundle_size": [3],
            "bundle_key": ["benefits=peptide + finish=high shine + form=balm"],
            "bundle_label": ["peptide + high shine + balm"],
        }
    )

    out = pack_builder._build_bundle_review_validation(
        recent_products=recent_products,
        innovation_pairs=innovation_pairs,
        innovation_triples=innovation_triples,
        attribute_columns=["resolved_form", "resolved_finish", "benefits"],
        max_pairs=1,
        max_triples=0,
        max_products_per_bundle=2,
    )

    assert out.height == 2
    assert out.get_column("bundle_key").unique().to_list() == [
        "benefits=peptide + form=balm"
    ]
    assert out.get_column("product_name").to_list() == ["P1", "P2"]
