from __future__ import annotations

import polars as pl

from modules.utilities.utils import get_row_count
from src.final_pass_filter import clean_bank_not_matched


def test_return_dropped_rows() -> None:
    df = pl.DataFrame(
        {
            "description": [
                "SALDO EXTRAFIDO 10.000,00",
                "BON.DA EXAMPLE SUPPLIER S.R.L.",
                "01/12/2023    1.234,56    0    1.234,56",
            ],
            "amount": [None, 100.0, 0.0],
            "page": [1, 1, 1],
        }
    )

    cleaned, dropped, report = clean_bank_not_matched(
        df, page_col="page", return_dropped_rows=True
    )

    assert get_row_count(cleaned) == 1
    assert cleaned["description"].to_list() == ["BON.DA EXAMPLE SUPPLIER S.R.L."]

    assert get_row_count(dropped) == 2
    assert dropped["description"].to_list() == [
        "SALDO EXTRAFIDO 10.000,00",
        "01/12/2023    1.234,56    0    1.234,56",
    ]
    assert report.counts_by_rule["drop_balance_summary"] == 2
