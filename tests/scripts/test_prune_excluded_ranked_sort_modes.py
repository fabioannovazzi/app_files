from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from scripts import prune_excluded_ranked_sort_modes as prune_script


@pytest.fixture(autouse=True)
def _disable_env_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDP_DATABASE_URL", raising=False)
    monkeypatch.delenv("PDP_BACKUP_DATABASE_URL", raising=False)
    monkeypatch.setattr(prune_script, "load_env_from_secrets_file", lambda: {})


def test_prune_excluded_ranked_sort_modes_removes_default_and_sale(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdp_store_path = tmp_path / "pdp_store"
    pruned_store_paths: list[Path] = []

    def _fake_prune_pdp_store(path: Path) -> int:
        pruned_store_paths.append(path)
        return 0

    monkeypatch.setattr(prune_script, "_prune_pdp_store", _fake_prune_pdp_store)

    run_dir = tmp_path / "runs" / "saks"
    run_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "crawl_ts": ["ts", "ts", "ts"],
            "retailer": ["saksfifthavenue", "saksfifthavenue", "saksfifthavenue"],
            "category_key": ["cashmere", "cashmere", "cashmere"],
            "source_surface": ["category", "category", "category"],
            "sort_mode": ["default", "sale_first", "new_arrivals"],
            "page": [1, 1, 1],
            "position": [1, 2, 3],
            "pdp_url": ["u1", "u2", "u3"],
            "parent_product_id": ["1", "2", "3"],
            "product_name": ["A", "B", "C"],
            "brand": ["Brand", "Brand", "Brand"],
            "has_new_badge": [False, False, True],
            "listing_url": ["l1", "l2", "l3"],
        }
    ).write_csv(run_dir / "retailer_listing_observations.csv")
    pl.DataFrame(
        {
            "parent_product_id": ["1", "2", "3"],
            "new_rest_class": ["rest", "rest", "new"],
        }
    ).write_csv(run_dir / "retailer_listing_classification.csv")
    (run_dir / "summary.json").write_text(
        json.dumps({"sort_modes": ["default", "sale_first", "new_arrivals"]}),
        encoding="utf-8",
    )

    exit_code = prune_script.main(
        [
            "--pdp-store-path",
            str(pdp_store_path),
            "--roots",
            str(tmp_path / "runs"),
        ]
    )

    assert exit_code == 0
    assert pruned_store_paths == [pdp_store_path]
    csv_rows = (
        pl.read_csv(run_dir / "retailer_listing_observations.csv")
        .select(["sort_mode", "pdp_url", "parent_product_id"])
        .to_dicts()
    )
    assert csv_rows == [
        {"sort_mode": "new_arrivals", "pdp_url": "u3", "parent_product_id": 3}
    ]
    classification_rows = (
        pl.read_csv(run_dir / "retailer_listing_classification.csv")
        .select(["parent_product_id", "new_rest_class", "pareto_class"])
        .to_dicts()
    )
    assert classification_rows == [
        {"parent_product_id": 3, "new_rest_class": "rest", "pareto_class": None}
    ]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["sort_modes"] == ["new_arrivals"]
    assert summary["removed_sort_modes"] == ["default", "sale_first"]
