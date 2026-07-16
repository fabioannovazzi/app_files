from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from scripts.build_sales_priority_links import (
    build_category_sales_plan,
    main,
    merge_category_links,
)


def test_build_category_sales_plan_reaches_target_coverage() -> None:
    sales_df = pl.DataFrame(
        [
            {
                "merchant": "amazon",
                "category": "blush",
                "sku": "B000000001",
                "sales": 60.0,
            },
            {
                "merchant": "amazon",
                "category": "blush",
                "sku": "B000000002",
                "sales": 25.0,
            },
            {
                "merchant": "amazon",
                "category": "blush",
                "sku": "B000000003",
                "sales": 15.0,
            },
            {
                "merchant": "amazon",
                "category": "bronzer",
                "sku": "B000000004",
                "sales": 10.0,
            },
        ]
    )

    selected, summary = build_category_sales_plan(
        sales_df,
        retailer="amazon",
        category_key="blush",
        target_coverage_pct=80.0,
        max_urls_per_category=0,
    )

    assert selected.height == 2
    assert selected.get_column("sku").to_list() == ["B000000001", "B000000002"]
    assert summary["selected_url_count"] == 2
    assert summary["coverage_pct"] == 85.0


def test_build_category_sales_plan_maps_setting_spray_powder_label() -> None:
    sales_df = pl.DataFrame(
        [
            {
                "merchant": "amazon",
                "category": "setting spray & powder",
                "sku": "B000000010",
                "sales": 90.0,
            },
            {
                "merchant": "amazon",
                "category": "setting spray & powder",
                "sku": "B000000011",
                "sales": 10.0,
            },
        ]
    )

    selected, summary = build_category_sales_plan(
        sales_df,
        retailer="amazon",
        category_key="setting_spray_powder",
        target_coverage_pct=80.0,
        max_urls_per_category=0,
    )

    assert selected.height == 1
    assert selected.get_column("sku").to_list() == ["B000000010"]
    assert summary["coverage_pct"] == 90.0


def test_merge_category_links_canonicalizes_and_appends() -> None:
    existing = [
        "https://www.amazon.com/gp/product/B000000001?psc=1",
        "https://www.amazon.com/dp/B000000002",
    ]
    selected = [
        "https://www.amazon.com/dp/B000000001",
        "https://www.amazon.com/dp/B000000003",
    ]

    merged = merge_category_links(
        existing,
        selected,
        replace_category_links=False,
    )

    assert merged == [
        "https://www.amazon.com/dp/B000000001",
        "https://www.amazon.com/dp/B000000002",
        "https://www.amazon.com/dp/B000000003",
    ]


def test_build_category_sales_plan_adds_recent_launch_booster() -> None:
    sales_df = pl.DataFrame(
        [
            {
                "merchant": "amazon",
                "category": "blush",
                "month": "2025-01-01",
                "sku": "B000000001",
                "sales": 900.0,
            },
            {
                "merchant": "amazon",
                "category": "blush",
                "month": "2025-01-01",
                "sku": "B000000002",
                "sales": 80.0,
            },
            {
                "merchant": "amazon",
                "category": "blush",
                "month": "2025-01-01",
                "sku": "B000000003",
                "sales": 20.0,
            },
            {
                "merchant": "amazon",
                "category": "blush",
                "month": "2025-06-01",
                "sku": "B000000001",
                "sales": 5.0,
            },
            {
                "merchant": "amazon",
                "category": "blush",
                "month": "2025-06-01",
                "sku": "B000000004",
                "sales": 40.0,
            },
            {
                "merchant": "amazon",
                "category": "blush",
                "month": "2025-06-01",
                "sku": "B000000005",
                "sales": 2.0,
            },
        ]
    )

    selected, summary = build_category_sales_plan(
        sales_df,
        retailer="amazon",
        category_key="blush",
        target_coverage_pct=80.0,
        max_urls_per_category=0,
        recent_months=2,
        recent_top_skus=20,
        recent_min_category_share_pct=5.0,
    )

    assert selected.get_column("sku").to_list() == ["B000000001", "B000000004"]
    assert selected.get_column("selection_source").to_list() == [
        "core_coverage",
        "recent_launch",
    ]
    assert summary["coverage_pct"] > summary["coverage_pct_core"]
    assert summary["recent_candidate_count"] == 1
    assert summary["recent_selected_count"] == 1


def test_build_category_sales_plan_recent_booster_respects_url_cap() -> None:
    sales_df = pl.DataFrame(
        [
            {
                "merchant": "amazon",
                "category": "blush",
                "month": "2025-01-01",
                "sku": "B000000001",
                "sales": 900.0,
            },
            {
                "merchant": "amazon",
                "category": "blush",
                "month": "2025-06-01",
                "sku": "B000000004",
                "sales": 40.0,
            },
        ]
    )

    selected, summary = build_category_sales_plan(
        sales_df,
        retailer="amazon",
        category_key="blush",
        target_coverage_pct=80.0,
        max_urls_per_category=1,
        recent_months=2,
        recent_top_skus=20,
        recent_min_category_share_pct=0.0,
    )

    assert selected.get_column("sku").to_list() == ["B000000001"]
    assert summary["selected_url_count"] == 1
    assert summary["recent_selected_count"] == 0


def test_main_updates_links_file(monkeypatch, tmp_path: Path) -> None:
    links_path = tmp_path / "links.json"
    links_path.write_text(
        json.dumps(
            {
                "amazon": {
                    "blush": ["https://www.amazon.com/dp/B000000111"],
                }
            }
        ),
        encoding="utf-8",
    )

    sales_df = pl.DataFrame(
        [
            {
                "merchant": "amazon",
                "category": "blush",
                "sku": "B000000001",
                "sales": 60.0,
            },
            {
                "merchant": "amazon",
                "category": "blush",
                "sku": "B000000002",
                "sales": 40.0,
            },
        ]
    )

    def _fake_load_sales_dataframe(dataset: str | None) -> tuple[pl.DataFrame, str]:
        _ = dataset
        return sales_df, "default"

    monkeypatch.setattr(
        "scripts.build_sales_priority_links._load_sales_dataframe",
        _fake_load_sales_dataframe,
    )

    rc = main(
        [
            "--links-path",
            str(links_path),
            "--categories",
            "blush",
            "--target-coverage-pct",
            "80",
            "--report-dir",
            str(tmp_path),
        ]
    )

    assert rc == 0

    updated = json.loads(links_path.read_text(encoding="utf-8"))
    blush_links = updated["amazon"]["blush"]
    assert blush_links == [
        "https://www.amazon.com/dp/B000000111",
        "https://www.amazon.com/dp/B000000001",
        "https://www.amazon.com/dp/B000000002",
    ]

    summary_files = list(tmp_path.glob("amazon_sales_priority_links_summary_*.json"))
    selection_files = list(tmp_path.glob("amazon_sales_priority_links_selected_*.csv"))
    assert len(summary_files) == 1
    assert len(selection_files) == 1
