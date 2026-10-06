"""Preserve statement dates across supported Polars major versions."""

from __future__ import annotations

from datetime import date, datetime

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from src.check_statements.normalisation import _parse_dates_expr


@pytest.mark.parametrize(
    "values",
    [
        ["2026-01-31", "2026-02-28"],
        ["31/01/2026", "28/02/2026"],
        ["2026-01-31T12:30:00+02:00", "2026-02-28T09:00:00Z"],
        [date(2026, 1, 31), date(2026, 2, 28)],
        [datetime(2026, 1, 31, 12, 30), datetime(2026, 2, 28, 9)],
    ],
)
def test_statement_dates_keep_calendar_meaning(values):
    actual = pl.DataFrame({"date": values}).select(_parse_dates_expr("date"))
    assert_frame_equal(
        actual,
        pl.DataFrame({"date": [date(2026, 1, 31), date(2026, 2, 28)]}),
    )
