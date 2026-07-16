from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.utilities.utils import get_row_count
from src.final_pass_filter import (
    CURRENCY_RE,
    DATE_RE,
    clean_bank_not_matched,
    digit_ratio,
)


def test_currency_re_matches_edge_cases() -> None:
    cases = ["1.000,00-", "0,00", " 84.780,53 "]
    for text in cases:
        assert CURRENCY_RE.fullmatch(text.strip())


def test_date_re_supports_two_and_four_digit_years() -> None:
    assert DATE_RE.fullmatch("11/06/24")
    assert DATE_RE.fullmatch("11/06/2024")


def test_digit_ratio_handles_mixed_content() -> None:
    assert digit_ratio("RIF.MBVT... 1.000,00") < 0.85
    assert digit_ratio("84.780,53 - 1 84.780,53 -") == 1.0


def test_numeric_table_rule_respects_digit_ratio() -> None:
    df = pl.DataFrame(
        {
            "description": [
                "NUMERI 1.000,00 2.000,00 3.000,00 4.000,00 5.000,00 6.000,00",
                "NUMERI 1.000,00 2.000,00 3.000,00 TOT",
            ],
            "amount": [None, None],
        }
    )

    cleaned, _ = clean_bank_not_matched(df)

    assert get_row_count(cleaned) == 1
    assert cleaned["description"].to_list() == ["NUMERI 1.000,00 2.000,00 3.000,00 TOT"]
