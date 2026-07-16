from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from scripts import backfill_retailer_observation_store as backfill_script


class _FakePDPStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.listing_observations = []
        self.filter_surfaces = []
        self.filter_observations = []

    def append_retailer_listing_observations(self, *, crawl_ts, observations):
        self.listing_observations.extend(
            (crawl_ts, observation) for observation in observations
        )

    def append_retailer_filter_surfaces(self, *, crawl_ts, surfaces):
        self.filter_surfaces.extend((crawl_ts, surface) for surface in surfaces)

    def append_retailer_filter_observations(self, *, crawl_ts, observations):
        self.filter_observations.extend(
            (crawl_ts, observation) for observation in observations
        )


def test_backfill_retailer_observation_store_imports_discovery_csvs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stores: list[_FakePDPStore] = []

    def _store_factory(path: Path) -> _FakePDPStore:
        store = _FakePDPStore(path)
        stores.append(store)
        return store

    monkeypatch.setattr(backfill_script, "PDPStore", _store_factory)
    pdp_store_path = tmp_path / "pdp_store"
    discovery_root = tmp_path / "discovery_runs" / "cdp"
    run_dir = discovery_root / "chewy" / "20260429T120000Z"
    evidence_root = tmp_path / "retailer_filter_evidence"
    run_dir.mkdir(parents=True)
    evidence_root.mkdir(parents=True)
    crawl_ts = "2026-04-29T12:00:00+00:00"
    (run_dir / "summary.json").write_text(
        json.dumps({"crawl_ts": crawl_ts}),
        encoding="utf-8",
    )
    pl.DataFrame(
        {
            "crawl_ts": [crawl_ts],
            "retailer": ["chewy"],
            "category_key": ["wet_cat_food"],
            "source_surface": ["category"],
            "sort_mode": ["newest"],
            "page": [1],
            "position": [1],
            "pdp_url": ["https://www.chewy.com/product/dp/123"],
            "parent_product_id": ["123"],
            "product_name": ["Chicken Dinner"],
            "brand": ["Brand"],
            "has_new_badge": [False],
            "listing_url": ["https://www.chewy.com/b/wet-food-389"],
        }
    ).write_csv(run_dir / "retailer_listing_observations.csv")
    pl.DataFrame(
        {
            "crawl_ts": [crawl_ts, crawl_ts],
            "retailer": ["chewy", "__type_guard__"],
            "category_key": ["wet_cat_food", "__type_guard__"],
            "filter_family": ["lifestage", "__type_guard__"],
            "filter_value": ["adult", "__type_guard__"],
            "filter_url": [
                "https://www.chewy.com/b/wet-food-389?lifestage=adult",
                "__type_guard__",
            ],
            "filter_label": ["Adult", "__type_guard__"],
        }
    ).write_csv(run_dir / "retailer_filter_surfaces.csv")
    pl.DataFrame(
        {
            "crawl_ts": [crawl_ts],
            "retailer": ["chewy"],
            "category_key": ["wet_cat_food"],
            "filter_family": ["lifestage"],
            "filter_value": ["adult"],
            "source_surface": ["filter:lifestage=adult"],
            "pdp_url": ["https://www.chewy.com/product/dp/123"],
            "parent_product_id": ["123"],
            "page": [1],
            "position": [1],
            "listing_url": ["https://www.chewy.com/b/wet-food-389?lifestage=adult"],
        }
    ).write_csv(run_dir / "retailer_filter_observations.csv")

    exit_code = backfill_script.main(
        [
            "--pdp-store-path",
            str(pdp_store_path),
            "--discovery-root",
            str(discovery_root),
            "--evidence-root",
            str(evidence_root),
        ]
    )

    assert exit_code == 0
    assert len(stores) == 1
    assert stores[0].path == pdp_store_path
    assert len(stores[0].listing_observations) == 1
    assert len(stores[0].filter_surfaces) == 1
    assert len(stores[0].filter_observations) == 1
