from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from modules.pdp.attribute_table_templates import (
    ATTRIBUTE_TABLE_TEMPLATE_FILES,
    build_attribute_table_frames,
    build_attribute_tables_from_package,
    write_attribute_table_artifacts,
)


def _signal_row(
    *,
    bundle_key: str,
    bundle_label: str,
    count: int,
    brand_count: int,
    focus_pct: float,
    baseline_pct: float,
    examples: str,
    layer: str,
) -> dict[str, object]:
    common = {
        "bundle_key": bundle_key,
        "bundle_label": bundle_label,
        "delta": focus_pct - baseline_pct,
        "prevalence_ratio": focus_pct / baseline_pct,
        "signal_usefulness": "headline_signal",
        "signal_role": "differentiating",
        "insight_adjusted_signal_score": 30.0,
    }
    if layer == "winning_now":
        common.update(
            {
                "count_top_seller": count,
                "count_other": 4,
                "top_seller_brand_count": brand_count,
                "pct_top_seller": focus_pct,
                "pct_other": baseline_pct,
                "top_seller_top_pareto_products": examples,
            }
        )
    else:
        common.update(
            {
                "count_recent": count,
                "count_rest": 4,
                "recent_brand_count": brand_count,
                "pct_recent": focus_pct,
                "pct_rest": baseline_pct,
                "recent_top_pareto_products": examples,
            }
        )
    return common


def _write_minimal_attribute_package(package_dir: Path) -> None:
    package_dir.mkdir()
    pl.DataFrame(
        [
            _signal_row(
                bundle_key="coverage=Buildable + form=Pressed powder",
                bundle_label="Buildable + Pressed powder",
                count=5,
                brand_count=4,
                focus_pct=0.50,
                baseline_pct=0.25,
                examples="Powder A (#1)",
                layer="winning_now",
            )
        ]
    ).write_csv(package_dir / "top_seller_pairs.csv")
    pl.DataFrame(
        [
            _signal_row(
                bundle_key="coverage=Buildable + form=Pressed powder",
                bundle_label="Buildable + Pressed powder",
                count=4,
                brand_count=3,
                focus_pct=0.40,
                baseline_pct=0.20,
                examples="Glow B (#5)",
                layer="innovation",
            )
        ]
    ).write_csv(package_dir / "innovation_pairs.csv")


def test_build_attribute_table_frames_creates_four_deterministic_tables() -> None:
    frames = {
        "top_seller_pairs": pl.DataFrame(
            [
                _signal_row(
                    bundle_key="coverage=Buildable + form=Pressed powder",
                    bundle_label="Buildable + Pressed powder",
                    count=5,
                    brand_count=4,
                    focus_pct=0.50,
                    baseline_pct=0.25,
                    examples="Powder A (#1) | Powder B (#2)",
                    layer="winning_now",
                )
            ]
        ),
        "innovation_pairs": pl.DataFrame(
            [
                _signal_row(
                    bundle_key="coverage=Buildable + form=Pressed powder",
                    bundle_label="Buildable + Pressed powder",
                    count=4,
                    brand_count=3,
                    focus_pct=0.40,
                    baseline_pct=0.20,
                    examples="Glow B (#5) | Powder A (#1)",
                    layer="innovation",
                )
            ]
        ),
        "top_seller_triples": pl.DataFrame(),
        "innovation_triples": pl.DataFrame(),
        "web_shelf_selected_shelves": pl.DataFrame(
            [
                {
                    "alpha": 1.0,
                    "shelf_rank": 1,
                    "bundle_key": "coverage=buildable + spf=15 - 30",
                    "gross_weight_share": 0.60,
                    "incremental_weight_share": 0.25,
                    "cumulative_weight_share": 0.25,
                    "incremental_sku_count": 10,
                    "incremental_brand_count": 6,
                    "top_products": "Powder A (#1) | Glow B (#5)",
                    "top_brands": "Brand A (30.0%) | Brand B (20.0%)",
                }
            ]
        ),
        "web_shelf_robustness_summary": pl.DataFrame(
            [
                {
                    "bundle_key": "coverage=buildable + spf=15 - 30",
                    "times_selected": 4,
                    "selected_under_alpha_0": True,
                    "selected_under_alpha_0_7": True,
                    "selected_under_alpha_1": True,
                    "selected_under_alpha_1_2": True,
                }
            ]
        ),
        "top_seller_products": pl.DataFrame(
            [
                {
                    "product_name": "Powder A",
                    "brand": "Brand A",
                    "pareto_rank": 1,
                    "rating": 4.8,
                    "review_count": 120,
                    "resolved_form": "Pressed powder",
                    "resolved_finish": "Matte",
                    "resolved_coverage": "Buildable",
                    "pack_image_file": "powder-a.png",
                }
            ]
        ),
        "recent_products": pl.DataFrame(
            [
                {
                    "product_name": "Glow B",
                    "brand": "Brand B",
                    "pareto_rank": 5,
                    "rating": 4.5,
                    "review_count": 30,
                    "resolved_form": "Pressed powder",
                    "resolved_finish": "Luminous",
                    "resolved_coverage": "Buildable",
                    "pack_image_file": "glow-b.png",
                }
            ]
        ),
    }

    tables = build_attribute_table_frames(frames)

    assert set(tables) == set(ATTRIBUTE_TABLE_TEMPLATE_FILES)
    bundle_table = tables["attribute_bundle_comparison_table"]
    assert bundle_table.get_column("signal_bundle").to_list() == [
        "Buildable + Pressed powder",
        "Buildable + Pressed powder",
    ]
    assert bundle_table.get_column("focus_n").to_list() == ["5", "4"]
    assert bundle_table.get_column("baseline_n").to_list() == ["4", "4"]
    assert bundle_table.get_column("focus_share").to_list() == ["50.0%", "40.0%"]
    assert bundle_table.get_column("baseline_share").to_list() == ["25.0%", "20.0%"]
    assert bundle_table.get_column("index").to_list() == ["2.00x", "2.00x"]
    bridge_table = tables["attribute_bridge_table"]
    assert bridge_table.item(0, "alignment") == "Bridge"
    assert bridge_table.item(0, "current_share") == "50.0%"
    assert bridge_table.item(0, "emerging_share") == "40.0%"
    visibility_table = tables["rank_weighted_visibility_table"]
    assert visibility_table.item(0, "incremental") == "25.0%"
    assert visibility_table.item(0, "robustness") == "4/4 alpha settings"
    product_table = tables["product_signal_evidence_table"]
    assert product_table.item(0, "product") == "Powder A"
    assert product_table.item(0, "matched_signal") == ("Buildable + Pressed powder")
    assert product_table.item(0, "rating") == "4.8"
    assert product_table.item(0, "reviews") == "120"


def test_build_attribute_table_frames_repairs_mojibake_display_text() -> None:
    mojibake_brand = "Lanc\u00c3\u00b4me"
    product_name = f"{mojibake_brand} Juicy Tubes Original Lip Gloss"
    frames = {
        "top_seller_pairs": pl.DataFrame(
            [
                _signal_row(
                    bundle_key="finish=shimmer + benefits=long-wear",
                    bundle_label="shimmer + long-wear",
                    count=1,
                    brand_count=1,
                    focus_pct=0.25,
                    baseline_pct=0.10,
                    examples=f"{product_name} (#33)",
                    layer="winning_now",
                )
            ]
        ),
        "innovation_pairs": pl.DataFrame(),
        "top_seller_triples": pl.DataFrame(),
        "innovation_triples": pl.DataFrame(),
        "web_shelf_selected_shelves": pl.DataFrame(),
        "web_shelf_robustness_summary": pl.DataFrame(),
        "top_seller_products": pl.DataFrame(
            [
                {
                    "product_name": product_name,
                    "brand": mojibake_brand,
                    "pareto_rank": 33,
                    "rating": 4.6,
                    "review_count": 2204,
                    "resolved_form": "Gloss",
                    "resolved_finish": "Shimmer",
                    "resolved_coverage": "Sheer",
                    "pack_image_file": "images/pimprod2015321.jpg",
                }
            ]
        ),
        "recent_products": pl.DataFrame(),
    }

    tables = build_attribute_table_frames(frames)

    bundle_table = tables["attribute_bundle_comparison_table"]
    assert bundle_table.item(0, "signal_bundle") == "shimmer + long-wear"
    product_table = tables["product_signal_evidence_table"]
    assert product_table.item(0, "brand") == "Lanc\u00f4me"
    assert product_table.item(0, "product") == (
        "Lanc\u00f4me Juicy Tubes Original Lip Gloss"
    )


def test_write_attribute_table_artifacts_persists_manifest_and_html(
    tmp_path: Path,
) -> None:
    frames = {
        table_key: pl.DataFrame({"example": ["value"]})
        for table_key in ATTRIBUTE_TABLE_TEMPLATE_FILES
    }

    manifest_entries = write_attribute_table_artifacts(frames, tmp_path)

    manifest = json.loads(
        (tmp_path / "attribute_tables" / "manifest.json").read_text(encoding="utf-8")
    )
    assert {entry["table_key"] for entry in manifest_entries} == set(
        ATTRIBUTE_TABLE_TEMPLATE_FILES
    )
    assert manifest["tables"][0]["artifact_type"] == "table"
    assert manifest["tables"][0]["display_row_limit"] == 5
    html_text = (
        tmp_path / "attribute_tables" / "attribute_bundle_comparison_table.html"
    ).read_text(encoding="utf-8")
    assert "Attribute Bundle Comparison" in html_text
    assert "Showing up to 5 rows." in html_text
    assert "IBCS" not in html_text


def test_build_attribute_tables_from_package_writes_selected_template(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "package"
    output_dir = tmp_path / "out"
    _write_minimal_attribute_package(package_dir)

    result = build_attribute_tables_from_package(
        package_dir,
        output_dir=output_dir,
        table_keys=["attribute_bridge_table"],
    )

    manifest = json.loads(
        (output_dir / "attribute_tables" / "manifest.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "written"
    assert result["table_keys"] == ["attribute_bridge_table"]
    assert result["tables"][0]["table_key"] == "attribute_bridge_table"
    assert manifest["tables"][0]["table_key"] == "attribute_bridge_table"
    assert (output_dir / "attribute_tables" / "attribute_bridge_table.csv").exists()
    assert not (
        output_dir / "attribute_tables" / "attribute_bundle_comparison_table.csv"
    ).exists()


def test_build_attribute_tables_from_package_rejects_invalid_request(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        build_attribute_tables_from_package(tmp_path / "missing")

    with pytest.raises(ValueError, match="Unknown attribute table template"):
        build_attribute_tables_from_package(tmp_path, table_keys=["unknown_table"])
