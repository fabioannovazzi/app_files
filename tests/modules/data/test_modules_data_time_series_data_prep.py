import pytest
import polars as pl
from polars.testing import assert_frame_equal

from modules.data.time_series_data_prep import (
    prepare_data_for_timeline_plot,
    prepare_data_for_slope_plot,
)
from modules.utilities.config import get_naming_params
from modules.utilities.utils import get_schema_and_column_names


def test_prepare_data_for_timeline_plot_pivots_and_drops_zero_sum():
    # Arrange
    n = get_naming_params()
    date_col = n["dateName"]  # "Date"
    df = pl.DataFrame(
        [
            {date_col: "2024-01-01", "Cat": "A", "value": 1.0},
            {date_col: "2024-01-01", "Cat": "B", "value": 0.0},
        ]
    )
    # uniqueItems must match output column labels after cleaning ("_A", "_B")
    unique_items = ["_A", "_B"]
    chart_dict = {
        n["chosenChart"]: n["timelineChart"],
        n["periodChoice"]: n["yearName"],
        n["periodToDate"]: False,
        n["compareWithYearBefore"]: False,
    }

    # Act
    lf = prepare_data_for_timeline_plot(df, "Cat", "value", unique_items, chart_dict)
    out = lf.collect()

    # Assert
    # Column "_B" is zero-sum and should be dropped; unique_items mutated accordingly
    expected = pl.DataFrame({date_col: ["2024-01-01"], "_A": [1.0]})
    assert_frame_equal(out, expected)
    assert unique_items == ["_A"]


def test_prepare_data_for_timeline_plot_appends_invisible_char_when_not_timeline_chart():
    # Arrange
    n = get_naming_params()
    date_col = n["dateName"]
    invisible = n["invisibleCharacter"]
    df = pl.DataFrame(
        [
            {date_col: "2024-01-01", "Cat": "A", "value": 1.0},
            {date_col: "2024-01-02", "Cat": "B", "value": 2.0},
        ]
    )
    unique_items: list[str] = []
    # Trigger the branch that appends the invisible character on the date
    chart_dict = {
        n["chosenChart"]: "slope",  # anything not equal to timelineChart
        n["periodChoice"]: n["yearName"],
        n["periodToDate"]: False,
        n["compareWithYearBefore"]: False,
    }

    # Act
    out = prepare_data_for_timeline_plot(
        df, "Cat", "value", unique_items, chart_dict
    ).collect()

    # Assert
    col_vals = out.get_column(date_col).to_list()
    assert all(str(v).endswith(invisible) for v in col_vals)
    # Sanity: pivoted metric columns exist (cleaned names like "_A", "_B")
    cols, _ = get_schema_and_column_names(out)
    assert any(c.endswith("A") for c in cols)
    assert any(c.endswith("B") for c in cols)


def test_prepare_data_for_slope_plot_pivots_metric_and_label_and_drops_zero_sum():
    # Arrange
    n = get_naming_params()
    period_col = n["periodName"]  # "Period"
    label_col = n["labelName"]  # "label"
    invisible = n["invisibleCharacter"]
    df = pl.DataFrame(
        [
            {period_col: "2024", "Cat": "A", "value": 2.0, label_col: "x"},
            {period_col: "2024", "Cat": "B", "value": 0.0, label_col: "y"},
        ]
    )
    # uniqueItems must reference post-clean metric column names for drop logic
    unique_items = ["_A", "_B"]
    param_dict: dict = {}
    chart_dict: dict = {}

    # Act
    out = prepare_data_for_slope_plot(
        df, "Cat", "value", unique_items, param_dict, chart_dict
    ).collect()

    # Assert
    # Period values should have invisible character appended
    periods = out.get_column(period_col).to_list()
    assert periods == [f"2024{invisible}"]

    # Zero-sum metric column "_B" is dropped; label columns remain
    cols, _ = get_schema_and_column_names(out)
    assert "_A" in cols and "_B" not in cols
    assert "label_A" in cols and "label_B" in cols
    assert unique_items == ["_A"]


def test_prepare_data_for_timeline_plot_raises_when_chosen_chart_missing():
    # Arrange
    n = get_naming_params()
    date_col = n["dateName"]
    df = pl.DataFrame([{date_col: "2024-01-01", "Cat": "A", "value": 1.0}])
    unique_items: list[str] = []
    chart_dict: dict = {}  # missing required chosenChart key

    # Act / Assert
    with pytest.raises(KeyError):
        prepare_data_for_timeline_plot(df, "Cat", "value", unique_items, chart_dict)
