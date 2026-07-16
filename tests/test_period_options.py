from __future__ import annotations

import polars as pl

from modules.utilities.config import get_naming_params
from src.period_options import (
    determine_most_recent_period_options,
    get_time_period_layout,
)


def test_get_time_period_layout_returns_expected_lists():
    # Act
    cols, expanders = get_time_period_layout()

    # Assert
    assert cols == [1, 1, 1, 1]
    assert expanders == [1, 2, 3, 4]


def test_determine_most_recent_options_year_unique_periods_golden():
    # Arrange
    naming = get_naming_params()
    period_col = naming["periodName"]
    period_choice = naming["periodChoice"]
    year_name = naming["yearName"]
    period_found = naming["periodColFound"]

    # three distinct periods => 3 periods -> 2 choices ["n-1", "n"], default index 1
    df = pl.DataFrame({period_col: [2020, 2021, 2022]}).lazy()
    param_dict = {period_found: True}
    chart_dict = {period_choice: year_name}

    # Act
    options, mapping, default_idx, show, returned_params = determine_most_recent_period_options(
        df, param_dict, chart_dict
    )

    # Assert
    assert options == ["n-1", "n"]
    assert mapping == {"n-1": -2, "n": -1}
    assert default_idx == 1
    assert show is True
    assert returned_params == param_dict


def test_determine_most_recent_options_filter_dates_hides_and_clears_mapping():
    # Arrange
    naming = get_naming_params()
    period_choice = naming["periodChoice"]
    month_name = naming["monthName"]
    period_found = naming["periodColFound"]
    filter_dates = naming["filterDates"]

    # month mode forces 14 periods -> 13 choices (n-12..n)
    df = pl.DataFrame({naming["periodName"]: [1]}).lazy()
    param_dict = {period_found: True}
    chart_dict = {period_choice: month_name, filter_dates: True}

    # Act
    options, mapping, default_idx, show, _ = determine_most_recent_period_options(
        df, param_dict, chart_dict
    )

    # Assert
    expected_options = [f"n-{i}" for i in range(12, 0, -1)] + ["n"]
    assert options == expected_options
    assert mapping == {}
    assert default_idx == -1
    assert show is False


def test_determine_most_recent_options_period_to_date_without_compare_hides_slider():
    # Arrange
    naming = get_naming_params()
    period_col = naming["periodName"]
    period_choice = naming["periodChoice"]
    year_name = naming["yearName"]
    period_found = naming["periodColFound"]
    period_to_date = naming["periodToDate"]
    compare_key = naming["compareWithYearBefore"]

    df = pl.DataFrame({period_col: [2020, 2021, 2022]}).lazy()
    param_dict = {period_found: True}
    chart_dict = {period_choice: year_name, period_to_date: True, compare_key: False}

    # Act
    options, mapping, default_idx, show, _ = determine_most_recent_period_options(
        df, param_dict, chart_dict
    )

    # Assert
    assert options == ["n-1", "n"]
    assert mapping  # not empty when filterDates is not set
    assert default_idx == 1
    assert show is False
