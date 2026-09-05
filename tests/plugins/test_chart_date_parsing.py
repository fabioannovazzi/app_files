"""Regression for the monthly grain accepted by the reporting profiler."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal


@pytest.mark.parametrize(
    "values,expected",
    [
        (["2026-01", "2026-02"], [date(2026, 1, 1), date(2026, 2, 1)]),
        (["2026/01", "2026/02"], [date(2026, 1, 1), date(2026, 2, 1)]),
        (["2026-01", "2026-02-17"], [date(2026, 1, 1), date(2026, 2, 17)]),
        (
            [date(2026, 1, 31), date(2026, 2, 28)],
            [date(2026, 1, 31), date(2026, 2, 28)],
        ),
    ],
)
def test_month_and_day_grains_keep_their_calendar_meaning(values, expected):
    path = (
        Path(__file__).resolve().parents[2]
        / "plugins/_shared/vendor/modules/chart_harness/date_parsing.py"
    )
    spec = importlib.util.spec_from_file_location("chart_date_parsing", path)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)

    result = pl.DataFrame({"date": values}).select(parser.parse_date_expression("date"))

    assert_frame_equal(result, pl.DataFrame({"date": expected}))
