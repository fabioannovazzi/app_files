from __future__ import annotations

import types

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.data.cohort_processing import (
    add_cohort_column,
    add_lost_and_dropped_column,
    prepare_cohort_and_period_data_for_analysis,
)
from modules.utilities.config import get_naming_params


def _make_minimal_col_dict() -> dict:
    """Return a minimal `colDict` with required tab keys present."""
    naming = get_naming_params()
    return {
        naming["plotChartsTab"]: "plot",
        naming["filterDataTab"]: "filter",
        naming["setVarianceOptionsTab"]: "variance",
    }


def test_prepare_cohort_impossible_to_process_returns_placeholders_and_preserves_paramdict():
    # Arrange
    naming = get_naming_params()
    impossible_key = naming["impossibleToProcessFile"]
    processing_choice_key = naming["processingChoice"]

    param = {impossible_key: True}
    df = pl.DataFrame({})  # empty -> not a valid dataset
    df_dates = pl.DataFrame({})
    df_periods = pl.DataFrame({})
    df_all_periods = pl.DataFrame({})
    df_plan = pl.DataFrame({})
    df_dict: dict = {}
    col_dict = _make_minimal_col_dict()
    tab_dict: dict = {}
    chart_dict = {processing_choice_key: "any"}
    automate_dict: dict = {}
    plan_playback_dict: dict = {}

    # Act
    out = prepare_cohort_and_period_data_for_analysis(
        param,
        df,
        df_dates,
        df_periods,
        df_all_periods,
        df_plan,
        df_dict,
        col_dict,
        tab_dict,
        chart_dict,
        automate_dict,
        plan_playback_dict,
    )

    # Assert: early return placeholders and original param dict preserved
    assert out[:7] == (None, None, None, None, None, None, None)
    assert out[7] is param  # unchanged reference returned
    assert out[8:] == (None, None, None)


def test_prepare_cohort_golden_path_minimal_flow(monkeypatch):
    # Arrange: tiny deterministic inputs and lightweight stubs for collaborators
    naming = get_naming_params()
    impossible_key = naming["impossibleToProcessFile"]
    filter_dict_key = naming["filterDictName"]
    column_order_key = naming["columnOrderName"]

    param = {impossible_key: False}
    df = pl.DataFrame({"Item": ["A", "B"], "Period": ["2024-01", "2024-01"], "Value": [1, 2]})
    df_dates = pl.DataFrame({"Item": ["A"], "Period": ["2024-01"]})
    df_periods = pl.DataFrame({"Period": ["2024-01", "2024-02"]})
    df_all_periods = pl.DataFrame({"Item": ["A", "B"], "Period": ["2024-01", "2024-01"]})
    df_plan = pl.DataFrame({"PlanCol": [1]})

    col_dict = _make_minimal_col_dict()
    chart_dict = {filter_dict_key: {}}

    # Stubs to isolate this function's contract
    index_cols = ["Item", "Period"]
    value_cols = ["Value"]
    original_value_cols = ["Value"]

    def stub_check_date_and_group_data(param_dict, in_df):
        return in_df, index_cols, value_cols, param_dict, original_value_cols

    def stub_set_up_cohort_widget(df_all, param_dict, chart_d, automate, idx_cols, tab):
        return chart_d

    def stub_add_cohort(df_, dfd, dfp, dfa, dfpl, idx, param_dict, chart_d):
        return df_, dfd, dfp, dfa, dfpl, idx

    def stub_add_lost(df_, dfd, dfp, dfa, dfpl, idx, param_dict, chart_d):
        return df_, dfd, dfp, dfa, dfpl, idx

    def stub_manage_filtering(df_, idx, param_dict, chart_d, automate, vals, ftab, vtab):
        return df_, idx, ["obsolete"], param_dict, chart_d

    def echo_df(df_, _filters):
        return df_

    # Apply stubs in module under test
    monkeypatch.setattr(
        "modules.data.cohort_processing.check_date_and_group_data",
        stub_check_date_and_group_data,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.set_up_cohort_column_widget",
        stub_set_up_cohort_widget,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.add_cohort_column",
        stub_add_cohort,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.add_lost_and_dropped_column",
        stub_add_lost,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.manage_filtering",
        stub_manage_filtering,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.query_filter_dataframe_dates",
        echo_df,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.query_filter_dataframe_periods",
        echo_df,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.query_filter_dataframe_all_periods",
        echo_df,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.query_filter_dataframe_plan",
        echo_df,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.download_filtered_file",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.set_up_count_metrics_widget",
        lambda *a, **k: chart_dict,
    )
    monkeypatch.setattr(
        "modules.data.cohort_processing.get_count_metric_names",
        lambda chart_d, vals: chart_d,
    )

    # Act
    (
        out_df,
        out_dates,
        out_periods,
        out_all_periods,
        out_plan,
        out_index_cols,
        out_value_cols,
        out_param,
        out_chart,
        to_drop,
        original_value_cols_copy,
    ) = prepare_cohort_and_period_data_for_analysis(
        param,
        df,
        df_dates,
        df_periods,
        df_all_periods,
        df_plan,
        {},
        col_dict,
        {},
        chart_dict,
        {},
        {},
    )

    # Assert
    assert_frame_equal(out_df, df)
    assert_frame_equal(out_dates, df_dates)
    assert_frame_equal(out_periods, df_periods)
    assert_frame_equal(out_all_periods, df_all_periods)
    assert_frame_equal(out_plan, df_plan)
    assert out_index_cols == index_cols
    assert out_value_cols == value_cols
    assert out_chart is chart_dict
    assert to_drop == ["obsolete"]
    assert original_value_cols_copy == original_value_cols
    # column order captured from df_plan
    assert out_param[column_order_key] == ["PlanCol"]


def test_add_cohort_column_adds_since_label_from_earliest_period():
    # Arrange
    naming = get_naming_params()
    chosen_key = naming["chosenCohortColumn"]
    period_key = naming["periodName"]
    all_periods_key = naming["allPeriodsList"]
    suffix = naming["chosenCohortSuffix"]
    since = naming["sinceName"]

    param = {all_periods_key: ["2024-01", "2024-02"]}
    chart = {chosen_key: "Item"}

    # Data across periods (lazy to match internal join with LazyFrame)
    df_all_periods = pl.DataFrame(
        {
            "Item": ["A", "A", "B"],
            period_key: ["2024-01", "2024-02", "2024-02"],
        }
    ).lazy()

    df_main = pl.DataFrame({"Item": ["A", "B"], period_key: ["2024-02", "2024-02"]}).lazy()

    # Act
    out_df, d_dates, d_periods, d_all, d_plan, idx = add_cohort_column(
        df_main, None, None, df_all_periods, None, [], param, chart
    )

    # Assert
    result = out_df.collect()
    new_col = "Item" + suffix
    assert new_col in result.columns
    # Values depend on earliest period per item
    expected = {
        "A": f"{since}<br>2024-01",
        "B": f"{since}<br>2024-02",
    }
    pairs = set(zip(result["Item"].to_list(), result[new_col].to_list()))
    assert pairs == {(k, v) for k, v in expected.items()}
    assert new_col in idx  # indexCols augmented


def test_add_cohort_column_noop_when_choice_is_nothing():
    # Arrange
    naming = get_naming_params()
    chosen_key = naming["chosenCohortColumn"]
    nothing = naming["nothingFilteredName"]
    param = {naming["allPeriodsList"]: ["2024-01", "2024-02"]}
    chart = {chosen_key: nothing}
    df = pl.DataFrame({"Item": ["A"], naming["periodName"]: ["2024-01"]}).lazy()

    # Act
    out_df, *_rest = add_cohort_column(df, None, None, df, None, [], param, chart)

    # Assert: unchanged (no new columns)
    assert out_df.collect().columns == df.collect().columns


def test_add_lost_and_dropped_column_marks_lost_and_active():
    # Arrange
    naming = get_naming_params()
    period_key = naming["periodName"]
    all_periods_key = naming["allPeriodsList"]
    lost_key = naming["lostAndDroppedColumn"]
    lost_suffix = naming["lostAndDroppedSuffix"]
    lost_label = naming["lostName"]
    active_label = naming["activeName"]

    param = {all_periods_key: ["2024-01", "2024-02"]}
    chart = {lost_key: "Item"}

    df_all = pl.DataFrame(
        {
            "Item": ["A", "A", "B", "C"],
            period_key: ["2024-01", "2024-02", "2024-01", "2024-02"],
        }
    )
    df_main = pl.DataFrame({"Item": ["A", "B", "C"], period_key: ["2024-02", "2024-01", "2024-02"]})

    # Act
    out_df, *_ = add_lost_and_dropped_column(
        df_main, None, None, df_all, None, [], param, chart
    )

    # Assert
    result = out_df
    new_col = "Item" + lost_suffix
    assert new_col in result.columns
    # B is present in first but missing in second -> Lost at 2024-01; others active
    expected_map = {
        "A": active_label,
        "B": f"{lost_label}<br>2024-01",
        "C": active_label,
    }
    got = dict(zip(result["Item"].to_list(), result[new_col].to_list()))
    assert got == expected_map

