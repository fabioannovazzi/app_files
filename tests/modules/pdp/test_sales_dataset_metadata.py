from __future__ import annotations

import json

from modules.pdp import sales_join


def test_sales_dataset_metadata_defaults_to_usd(monkeypatch, tmp_path) -> None:
    dataset_dir = tmp_path / "default_sales"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sales_join, "get_sales_dataset_name", lambda _dataset=None: "default")
    monkeypatch.setattr(sales_join, "get_sales_dataset_dir", lambda _dataset=None: dataset_dir)

    metadata = sales_join.get_sales_dataset_metadata()

    assert metadata["currency"] == "USD"
    assert metadata["industry"] == "Cosmetics in USA"
    assert metadata["dataset"] == "default"


def test_sales_dataset_metadata_defaults_kiko_to_eur(monkeypatch, tmp_path) -> None:
    dataset_dir = tmp_path / "kiko"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sales_join, "get_sales_dataset_name", lambda _dataset=None: "kiko")
    monkeypatch.setattr(sales_join, "get_sales_dataset_dir", lambda _dataset=None: dataset_dir)

    metadata = sales_join.get_sales_dataset_metadata()

    assert metadata["currency"] == "EUR"
    assert metadata["industry"] == "Cosmetics in Europe"


def test_sales_dataset_metadata_json_overrides_defaults(monkeypatch, tmp_path) -> None:
    dataset_dir = tmp_path / "kiko"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "metadata.json").write_text(
        json.dumps({"industry": "Cosmetics in Italy", "currency": "eur"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sales_join, "get_sales_dataset_name", lambda _dataset=None: "kiko")
    monkeypatch.setattr(sales_join, "get_sales_dataset_dir", lambda _dataset=None: dataset_dir)

    metadata = sales_join.get_sales_dataset_metadata()

    assert metadata["currency"] == "EUR"
    assert metadata["industry"] == "Cosmetics in Italy"
