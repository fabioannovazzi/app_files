import polars as pl
import pytest

from modules.utilities.utils import get_row_count
from src.final_pass_filter import FinalPassConfig, clean_bank_not_matched


def test_numeric_table_lines_are_dropped() -> None:
    df = pl.DataFrame(
        {
            "description": [
                "31/01/2024 84.780,53 - 1 84.780,53 -",
                "01/02/2024 84.780,53 - 4 339.122,12 -",
                "01/07/2024 129,86 - 31 4.025,66 -",
                "VOSTRA DISPOSIZIONE BONIFICO URG./ISTANTANEO VS.DISP. RIF. MBVT...",
                "BON.DA EXAMPLE SUPPLIER S.R.L.",
            ],
            "amount": [None, None, None, 100.0, -50.0],
        }
    )

    cleaned = clean_bank_not_matched(df)

    assert get_row_count(cleaned) == 2
    assert cleaned["description"].to_list() == [
        "VOSTRA DISPOSIZIONE BONIFICO URG./ISTANTANEO VS.DISP. RIF. MBVT...",
        "BON.DA EXAMPLE SUPPLIER S.R.L.",
    ]


def test_numeric_table_drop_can_be_disabled() -> None:
    df = pl.DataFrame(
        {
            "description": ["84.780,53 - 1 84.780,53 -"],
            "amount": [None],
        }
    )

    cleaned = clean_bank_not_matched(
        df, config=FinalPassConfig(numeric_table_drop_enabled=False)
    )

    assert get_row_count(cleaned) == 1


def test_null_description_rows_are_not_dropped() -> None:
    df = pl.DataFrame({"description": [None], "amount": [10.0]})

    cleaned = clean_bank_not_matched(df)

    assert get_row_count(cleaned) == 1
    assert cleaned["amount"].to_list() == [10.0]


LONG_DIGITS = "1234567890" * 6


@pytest.mark.parametrize(
    "token",
    [
        "BON.",
        "BONIFICO",
        "VS.DISP.",
        "RIF.",
        "COMM.",
        "GIROCONTO",
        "F24",
        "STORNO",
    ],
)
def test_numeric_table_safelist_tokens_are_kept(token: str) -> None:
    desc = f"{token} {LONG_DIGITS} 84.780,53 - 1 84.780,53 -"
    df = pl.DataFrame({"description": [desc], "amount": [None]})

    cleaned = clean_bank_not_matched(df)

    assert get_row_count(cleaned) == 1
    assert cleaned["description"].to_list() == [desc]
