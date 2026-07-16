import pytest

import polars as pl
from polars.testing import assert_frame_equal

from modules.charting.plotting_utilities import (
    check_if_two_periods_in_distribution_chart,
    check_if_negative_bubble_size_values,
    calculate_percentage_data_column_metric,
)
from modules.utilities.config import get_naming_params


@pytest.mark.parametrize(
    "periods,expected",
    [
        (["P0", "P1", "P2"], ("P0", "P1")),
        (["Only"], ("Only", "")),
    ],
)
def test_check_if_two_periods_in_distribution_chart(periods, expected):
    # Act
    result = check_if_two_periods_in_distribution_chart(periods)

    # Assert
    assert result == expected


def test_check_if_two_periods_in_distribution_chart_raises_on_empty():
    # Act & Assert
    with pytest.raises(IndexError):
        check_if_two_periods_in_distribution_chart([])


@pytest.mark.parametrize("use_lazy", [False, True])
def test_check_if_negative_bubble_size_values_filters_negatives_and_adds_message(use_lazy):
    # Arrange
    naming = get_naming_params()
    bubble_col = "size"
    chartDict = {naming["bubbleSize"]: bubble_col}
    paramDict: dict = {}

    df = pl.DataFrame({bubble_col: [1, -2, 0]})
    data_obj = df.lazy() if use_lazy else df

    # Act
    result, updated_params = check_if_negative_bubble_size_values(
        data_obj, chartDict, paramDict
    )

    # Assert
    # result type mirrors input type
    if use_lazy:
        assert isinstance(result, pl.LazyFrame)
        collected = result.collect()
    else:
        assert isinstance(result, pl.DataFrame)
        collected = result

    # Only strictly positive values remain (> 0)
    assert_frame_equal(collected, pl.DataFrame({bubble_col: [1]}))

    # A single warning message is added to the correct tab
    app_arr_key = naming["appMessageArray"]
    app_type_key = naming["appMessageType"]
    app_tab_key = naming["appMessageTab"]
    warn_type = naming["warningMessageType"]
    plot_tab = naming["plotChartsTab"]

    assert app_arr_key in updated_params
    assert len(updated_params[app_arr_key]) == 1
    msg = updated_params[app_arr_key][0]
    assert msg[app_type_key] == warn_type
    assert msg[app_tab_key] == plot_tab
    # Message content mentions the offending column and negatives
    content_key = naming["appMessageContent"]
    assert bubble_col in msg[content_key]
    assert "negative" in msg[content_key].lower()


def test_check_if_negative_bubble_size_values_no_negatives_no_message_and_identity():
    # Arrange
    naming = get_naming_params()
    bubble_col = "size"
    chartDict = {naming["bubbleSize"]: bubble_col}
    paramDict: dict = {}
    df = pl.DataFrame({bubble_col: [0, 2]})  # zeros should be kept when no negatives

    # Act
    result, updated_params = check_if_negative_bubble_size_values(
        df, chartDict, paramDict
    )

    # Assert
    assert isinstance(result, pl.DataFrame)
    assert_frame_equal(result, df)
    assert naming["appMessageArray"] not in updated_params


def test_calculate_percentage_data_column_metric_adds_column_and_updates_state():
    # Arrange
    naming = get_naming_params()
    num, den, pct = "num", "den", "pct"
    df = pl.DataFrame({num: [1.0, 2.0, 3.0], den: [2.0, None, 4.0]})
    chartDict = {naming["averageTotalValue"]: {}, naming["dataColMetricName"]: {}}
    numberOfMetrics = 0
    sumColsArray: list[str] = []

    # Act
    (
        out_df,
        out_chart,
        out_sumcols,
        out_nmetrics,
        out_sumcols_again,
    ) = calculate_percentage_data_column_metric(
        df, num, den, pct, numberOfMetrics, sumColsArray, chartDict
    )

    # Assert
    # New column computed with null-handling (None -> 0%)
    expected = df.with_columns(((pl.col(num) / pl.col(den) * 100).fill_null(0)).alias(pct))
    assert_frame_equal(out_df, expected)

    # Chart dict updated with totals and name mapping
    total_avg = df[num].sum() / df[den].sum() * 100
    assert out_chart[naming["averageTotalValue"]][pct] == pytest.approx(total_avg)
    assert out_chart[naming["dataColMetricName"]][pct] == pct

    # Counters and arrays updated
    assert out_nmetrics == numberOfMetrics + 1
    assert out_sumcols[-1] == pct
    assert out_sumcols == out_sumcols_again
