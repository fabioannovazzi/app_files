from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from src.period_aggregators import (
    calculate_period_to_date_same_year,
    calculate_quarter_to_date_same_year,
    calculate_rolling_period,
)
from modules.utilities.config import get_naming_params
from modules.utilities.utils import get_row_count
from src.date_helpers import start_of_quarter
from dateutil.relativedelta import relativedelta


def _weekly_dates(start: dt.datetime, weeks: int) -> list[dt.datetime]:
    return [start + dt.timedelta(weeks=i) for i in range(weeks)]


def test_calculate_rolling_period_labels_and_ty_ya_dates():
    # Arrange: ~110 weeks to exceed 24 months so rolling buckets are applied
    naming = get_naming_params()
    date_col = naming["dateName"]
    period_col = naming["periodName"]
    year_before = naming["yearBeforeName"]
    current_year = naming["currentYearName"]

    start = dt.datetime(2021, 1, 1)
    dates = _weekly_dates(start, 110)
    df = pl.DataFrame({date_col: dates, period_col: ["NA"] * len(dates)})

    params = {naming["datePeriodName"]: naming["yearName"]}
    chart = {}
    ty_ya_dates: list[str] = []

    # Act
    result, out_params, out_dates, out_chart = calculate_rolling_period(
        df, ty_ya_dates, params, chart
    )

    # Assert: last two rolling-year buckets kept (~Y and ~Yn-1)
    assert isinstance(result, pl.DataFrame)
    # Inclusive boundary yields 53 + 52 rows for the two buckets
    assert get_row_count(result) == 105

    counts = (
        result.group_by(period_col)
        .agg(pl.len().alias("n"))
        .sort(period_col)
        .to_dict(as_series=False)
    )
    labels = set(counts[period_col])
    assert labels == {current_year, f"{year_before}1"}
    # Buckets sizes: 53 weeks for ~Y (inclusive) and 52 for ~Yn-1
    n_by_label = dict(zip(counts[period_col], counts["n"]))
    assert n_by_label[current_year] == 53
    assert n_by_label[f"{year_before}1"] == 52

    most_recent = max(dates)
    first_delta = most_recent - dt.timedelta(weeks=52)
    assert out_dates == [str(most_recent), str(first_delta)]


def test_calculate_rolling_period_small_range_switches_compare_flags():
    # Arrange: <= 2 months triggers warnings and flips flags when comparing years
    naming = get_naming_params()
    date_col = naming["dateName"]
    period_col = naming["periodName"]
    choice_key = naming["datePeriodName"]
    year_name = naming["yearName"]
    compare_key = naming["compareWithYearBefore"]
    ptd_key = naming["periodToDate"]
    app_array = naming["appMessageArray"]
    app_content = naming["appMessageContent"]

    start = dt.datetime(2024, 1, 1)
    dates = _weekly_dates(start, 8)  # ~2 months
    df = pl.DataFrame({date_col: dates, period_col: ["p"] * len(dates)})

    params = {choice_key: year_name}
    chart = {compare_key: True}

    # Act
    _, out_params, out_dates, out_chart = calculate_rolling_period(
        df, [], params, chart
    )

    # Assert: flags flipped and warnings added
    assert out_chart[compare_key] is False
    assert out_chart[ptd_key] is True
    messages = [m[app_content] for m in out_params[app_array]]
    assert any("less than 24 months" in msg for msg in messages)
    assert any("Year-to-Date" in msg for msg in messages)
    assert len(out_dates) == 1  # only most recent appended


def test_calculate_period_to_date_same_year_quarter_flow():
    # Arrange: build data covering three quarters so QTD windows are selected
    naming = get_naming_params()
    date_col = naming["dateName"]
    period_col = naming["periodName"]
    choice_key = naming["datePeriodName"]
    quarter_name = naming["quarterName"]
    to_date_name = naming["quarterToDateName"]

    start = dt.datetime(2023, 10, 1)
    end = dt.datetime(2024, 5, 10)
    # Weekly dates across the range
    weeks = (end - start).days // 7 + 1
    dates = _weekly_dates(start, weeks)
    # Period content is irrelevant here; just ensure we have some unique values
    periods_seed = ["A", "B", "C", "D"]
    df = pl.DataFrame(
        {date_col: dates, period_col: [periods_seed[i % 4] for i in range(len(dates))]}
    )

    params = {choice_key: quarter_name, naming["dateColFound"]: True}

    # Act
    lazy_df, out_params = calculate_period_to_date_same_year(df, params)
    result = lazy_df.collect()

    # Assert: only dates from the last three quarter-to-date windows remain
    most_recent = max(dates)
    # Use relativedelta for clarity (two quarters back)
    earliest_expected = start_of_quarter(most_recent - relativedelta(months=6))

    assert result.select(pl.col(date_col).min()).item() == earliest_expected
    unique_labels = (
        result.select(pl.col(period_col).unique())
        .get_column(period_col)
        .to_list()
    )
    assert all(isinstance(s, str) and s.startswith(to_date_name) for s in unique_labels)
    # Function returns a LazyFrame
    assert isinstance(lazy_df, pl.LazyFrame)


def test_calculate_period_to_date_same_year_unmanaged_period_adds_warning():
    # Arrange: choose Year to trigger the warning path
    naming = get_naming_params()
    date_col = naming["dateName"]
    period_col = naming["periodName"]
    choice_key = naming["datePeriodName"]
    year_name = naming["yearName"]
    app_array = naming["appMessageArray"]
    app_content = naming["appMessageContent"]

    dates = _weekly_dates(dt.datetime(2024, 1, 1), 6)
    df = pl.DataFrame({date_col: dates, period_col: ["x"] * len(dates)})
    params = {choice_key: year_name, naming["dateColFound"]: True}

    # Act
    lazy_df, out_params = calculate_period_to_date_same_year(df, params)
    result = lazy_df.collect()

    # Assert: warning message recorded and no filtering applied
    messages = [m[app_content] for m in out_params[app_array]]
    assert f"Not managed period: {year_name}" in messages
    assert get_row_count(result) == len(dates)


def test_calculate_quarter_to_date_same_year_limits_to_three_periods():
    # Arrange: provide 4 labels but expect only 3 QTD windows to be produced
    naming = get_naming_params()
    date_col = naming["dateName"]
    period_col = naming["periodName"]
    to_date_name = naming["quarterToDateName"]

    start = dt.datetime(2023, 10, 1)
    most_recent = dt.datetime(2024, 5, 20)
    weeks = (most_recent - start).days // 7 + 1
    dates = _weekly_dates(start, weeks)
    df = pl.DataFrame({date_col: dates, period_col: ["seed"] * len(dates)})

    periods = ["P1", "P2", "P3", "P4"]  # 4 items to test the boundary

    # Act
    lazy_df, label_prefix = calculate_quarter_to_date_same_year(
        df, most_recent, periods, {}
    )
    result = lazy_df.collect()

    # Assert: only three unique labels and correct earliest date
    unique_labels = (
        result.select(pl.col(period_col).unique())
        .get_column(period_col)
        .to_list()
    )
    assert len(unique_labels) == 3
    assert all(s.startswith(to_date_name) for s in unique_labels)
    earliest_expected = start_of_quarter(most_recent - relativedelta(months=6))
    assert result.select(pl.col(date_col).min()).item() == earliest_expected
