import polars as pl

from modules.utilities.utils import get_row_count
from src.final_pass_filter import clean_bank_not_matched


def test_extrafido_lines_are_dropped() -> None:
    df = pl.DataFrame(
        {
            "description": [
                "DETTAGLIO SALDI",
                "01/02/2024 84.780,53 - EXTRAFIDO 339.122,12 -",
                "SALDO EXTRAFIDO 10.000,00",
                "29/06/24 COMPETENZE",
                "BON.DA EXAMPLE SUPPLIER S.R.L.",
            ],
            "amount": [None, None, None, -105.0, 100.0],
            "page": [1, 1, 1, 1, 1],
        }
    )

    cleaned, report = clean_bank_not_matched(df, page_col="page", collect_stats=True)

    assert get_row_count(cleaned) == 2
    assert cleaned["description"].to_list() == [
        "29/06/24 COMPETENZE",
        "BON.DA EXAMPLE SUPPLIER S.R.L.",
    ]
    assert report.counts_by_rule["drop_balance_summary"] == 2


def test_extrafido_safelist_words_are_kept() -> None:
    df = pl.DataFrame(
        {
            "description": ["COMM. EXTRAFIDO 50,00", "BONIFICO EXTRAFIDO"],
            "amount": [None, 10.0],
        }
    )

    cleaned = clean_bank_not_matched(df)

    assert get_row_count(cleaned) == 2
    assert cleaned["description"].to_list() == [
        "COMM. EXTRAFIDO 50,00",
        "BONIFICO EXTRAFIDO",
    ]


def test_date_amount_only_two_digit_year_is_dropped() -> None:
    df = pl.DataFrame(
        {
            "description": [
                "11/06/24 84.780,53 - 339.122,12 -",
                "BON.DA EXAMPLE SUPPLIER S.R.L.",
            ],
            "amount": [None, 100.0],
        }
    )

    cleaned, report = clean_bank_not_matched(df, collect_stats=True)

    assert get_row_count(cleaned) == 1
    assert cleaned["description"].to_list() == ["BON.DA EXAMPLE SUPPLIER S.R.L."]
    assert report.counts_by_rule["drop_balance_summary"] == 1
