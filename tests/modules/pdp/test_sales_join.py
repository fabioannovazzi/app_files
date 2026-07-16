from __future__ import annotations

from datetime import date

import polars as pl
import pytest

import modules.pdp.sales_join as sales_join_mod


@pytest.mark.parametrize(
    ("resolver_name", "loader_name"),
    [
        ("_resolve_sales_path", "load_sales_data"),
        ("_resolve_full_sales_path", "load_full_sales_data"),
    ],
)
def test_sales_loaders_parse_year_only_months_from_parquet(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    resolver_name: str,
    loader_name: str,
) -> None:
    parquet_path = tmp_path / "sales.parquet"
    frame = pl.DataFrame(
        {
            "month": ["2024", "2025"],
            "merchant": ["kiko", "kiko"],
            "category": ["blush", "blush"],
            "brand": ["kiko milano", "kiko milano"],
            "sku": ["sku1", "sku2"],
            "sales": [10.0, 12.0],
            "units": [1.0, 2.0],
        }
    )
    frame.write_parquet(parquet_path)

    monkeypatch.setattr(
        sales_join_mod,
        resolver_name,
        lambda _retailer=None, _dataset=None: parquet_path,
    )
    sales_join_mod._SALES_CACHE.clear()
    loader = getattr(sales_join_mod, loader_name)

    loaded = loader(dataset="kiko")

    assert loaded.schema.get("month") == pl.Date
    assert loaded.select(pl.col("month").is_null().sum()).item() == 0
    assert loaded.get_column("month").to_list() == [
        date(2024, 1, 1),
        date(2025, 1, 1),
    ]
