import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.data.data_cleaning import (
    delete_index_columns,
    order_initial_columns,
    use_volume_data_to_calculate_variance,
)
from modules.utilities.config import get_naming_params


def test_use_volume_data_to_calculate_variance_creates_units_from_volume():
    # Arrange
    naming = get_naming_params()
    vol = naming["volumeName"]
    units = naming["unitsName"]
    variance_agg_key = naming["varianceAggregation"]
    units_col_found = naming["unitsColFound"]
    met_val = naming["metConditionValue"]
    impossible_key = naming["impossibleToProcessFile"]

    df = pl.DataFrame({vol: [1, 2], "Other": [10, 20]})
    param = {impossible_key: False}
    chart = {variance_agg_key: vol.lower()}  # contains "volume"

    # Act
    out_df, out_param = use_volume_data_to_calculate_variance(df, param, chart)

    # Assert
    expected = df.with_columns(pl.col(vol).alias(units))
    assert_frame_equal(out_df, expected)
    assert out_param[units_col_found] == met_val


def test_use_volume_data_to_calculate_variance_skips_when_impossible_flag_set():
    # Arrange
    naming = get_naming_params()
    vol = naming["volumeName"]
    units = naming["unitsName"]
    variance_agg_key = naming["varianceAggregation"]
    impossible_key = naming["impossibleToProcessFile"]

    df = pl.DataFrame({vol: [3, 4]})
    param = {impossible_key: True}
    chart = {variance_agg_key: vol.lower()}

    # Act
    out_df, out_param = use_volume_data_to_calculate_variance(df, param, chart)

    # Assert
    assert units not in out_df.columns  # no new column
    assert impossible_key in out_param and out_param[impossible_key] is True
    # unitsColFound key is not introduced when impossible flag is set
    assert naming["unitsColFound"] not in out_param


def test_delete_index_columns_drops_selected_and_groups(monkeypatch):
    # Arrange
    naming = get_naming_params()
    period = naming["periodName"]
    correct_period_key = naming["correctPeriodAggregation"]
    variance_agg_key = naming["varianceAggregation"]
    processing_choice_key = naming["processingChoice"]
    run_var_dim = naming["runVariableDimensionalAnalysis"]

    df = pl.DataFrame(
        {
            period: ["2024-01", "2024-01"],
            "Region": ["R1", "R2"],
            "Category": ["C1", "C1"],
            "v1": [10, 20],
            "v2": [1, 2],
        }
    )
    index_cols = [period, "Region", "Category"]
    value_cols = ["v1", "v2"]
    param = {correct_period_key: True, naming["columnHash"]: "hash"}
    chart = {variance_agg_key: "any", processing_choice_key: run_var_dim}

    # Stub the UI-driven selector to drop the "Region" column
    def fake_select_index_columns_to_drop(*_a, **_k):
        return ["Region"]

    import modules.data.data_cleaning as dc

    monkeypatch.setattr(
        dc, "select_index_columns_to_drop", fake_select_index_columns_to_drop
    )

    # Act
    out_df, out_index_cols, to_drop, _ = delete_index_columns(
        df, index_cols, param, chart, {}, value_cols, col=None
    )

    # Assert
    assert to_drop == ["Region"]
    assert out_index_cols == [period, "Category"]
    assert "Region" not in out_df.columns

    expected = pl.DataFrame({period: ["2024-01"], "Category": ["C1"], "v1": [30], "v2": [3]})
    assert_frame_equal(out_df.sort([period, "Category"]), expected)


def test_delete_index_columns_noop_when_variance_aggregation_missing():
    # Arrange
    naming = get_naming_params()
    period = naming["periodName"]
    correct_period_key = naming["correctPeriodAggregation"]

    df = pl.DataFrame({period: ["2024-01"], "Region": ["R1"], "v": [1]})
    index_cols = [period, "Region"]
    value_cols = ["v"]
    param = {correct_period_key: True}
    chart = {}  # varianceAggregation not provided -> branch skipped

    # Act
    out_df, out_index_cols, to_drop, _ = delete_index_columns(
        df, index_cols, param, chart, {}, value_cols, col=None
    )

    # Assert
    assert to_drop == []
    assert out_index_cols == index_cols
    assert_frame_equal(out_df, df)


def test_order_initial_columns_moves_var_first_when_string():
    # Arrange
    df = pl.DataFrame({"B": [1, 2], "A": [3, 4], "C": [5, 6]})

    # Act
    out = order_initial_columns(df, "A")

    # Assert
    expected = df.select(["A", "B", "C"])
    assert_frame_equal(out, expected)


def test_order_initial_columns_raises_for_unknown_column():
    # Arrange
    df = pl.DataFrame({"A": [1], "B": [2]})

    # Act / Assert
    with pytest.raises(Exception):
        order_initial_columns(df, ["Z"])  # Z does not exist
