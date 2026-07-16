from __future__ import annotations

import polars as pl
import pytest

from modules.utilities.utils import get_row_count
from src.final_pass_filter import clean_bank_not_matched


@pytest.mark.parametrize(
    ("description", "should_keep"),
    [
        ("31/01/2024 84.780,53 - 1 84.780,53 -", False),
        ("01/07/2024 129,86 - 31 4.025,66 -", False),
        ("31/12/2024 EXTRAFIDO 10.000,00 10.000,00", False),
        ("BON.DA EXAMPLE SUPPLIER S.R.L. - CONSORZIO", True),
        (
            "VOSTRA DISPOSIZIONE BONIFICO URG./ISTANTANEO VS.DISP. RIF. MBVT12345",
            True,
        ),
    ],
)
def test_clean_bank_not_matched_samples(description: str, should_keep: bool) -> None:
    df = pl.DataFrame({"description": [description]})

    cleaned = clean_bank_not_matched(df, amount_col="description")

    assert get_row_count(cleaned) == (1 if should_keep else 0)
    if should_keep:
        assert cleaned["description"].to_list() == [description]
