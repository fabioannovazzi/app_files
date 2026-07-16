import pytest
import polars as pl
from polars.testing import assert_frame_equal

from modules.utilities.config import (
    get_naming_params,
    get_variance_aggregation_params,
)
from modules.variance.variance_orchestrator import (
    ensure_lazyframe,
    build_variance_calculation_array,
    select_variance_aggregations_to_plot,
)


def test_ensure_lazyframe_from_dataframe_returns_equivalent_lazyframe():
    # Arrange
    df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})

    # Act
    lf = ensure_lazyframe(df)

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    assert_frame_equal(lf.collect(), df)


def test_ensure_lazyframe_from_lazyframe_passes_through():
    # Arrange
    base = pl.DataFrame({"x": [10, 20]}).lazy()

    # Act
    out = ensure_lazyframe(base)

    # Assert
    assert out is base  # should not create a new object


def test_ensure_lazyframe_unsupported_type_raises_typeerror():
    # Arrange
    bad_obj = {"a": [1, 2]}  # not a DataFrame/LazyFrame

    # Act / Assert
    with pytest.raises(TypeError):
        ensure_lazyframe(bad_obj)  # type: ignore[arg-type]


def test_build_variance_calculation_array_inserts_dates_and_moves_balance():
    # Arrange
    n = get_naming_params()
    selected_periods_key = n["selectedPeriods"]
    costs_units_agg = n["costsUnitsAggregation"]
    chart_dict = {selected_periods_key: ["P0", "P1"]}

    # Act
    result = build_variance_calculation_array([costs_units_agg], chart_dict)

    # Assert
    # Inserts first and last periods
    assert result[0] == "P0"
    assert result[-1] == "P1"
    # Balance should be right before the last inserted period
    assert result[-2] == "Balance"
    # Core components for this aggregation are present (order-preserving, no dups)
    for label in (
        "Price on margin",
        "Units & mix on margin",
        "Cost",
        "Indirect Costs",
        "Balance",
    ):
        assert label in result


def test_build_variance_calculation_array_invalid_selected_periods_raises():
    # Arrange
    n = get_naming_params()
    selected_periods_key = n["selectedPeriods"]
    costs_units_agg = n["costsUnitsAggregation"]
    chart_dict = {selected_periods_key: ["OnlyOne"]}  # must be exactly two

    # Act / Assert
    with pytest.raises(ValueError):
        build_variance_calculation_array([costs_units_agg], chart_dict)


def test_select_variance_aggregations_sales_filters_and_sets_flag():
    # Arrange
    n = get_naming_params()
    variance_params = get_variance_aggregation_params()
    options_key = n["varianceAggregationOptionsArray"]
    chosen_key = n["varianceAggregation"]
    diff_calc_key = n["varianceDifferentCalculations"]
    met = n["metConditionValue"]

    total_var = n["totalVarianceAggregation"]  # in sales set
    mix_units = n["mixAndUnitsAggregation"]  # in sales set
    costs_units = n["costsUnitsAggregation"]  # not in sales set to plot

    chart_dict = {
        options_key: [total_var, mix_units, costs_units],
        chosen_key: total_var,
    }

    # Act
    aggregations_to_plot, updated = select_variance_aggregations_to_plot(chart_dict)

    # Assert
    assert aggregations_to_plot == [total_var, mix_units]
    assert updated[options_key] == [total_var, mix_units]
    assert updated[diff_calc_key] == met
    # The selected aggregation remains unchanged for sales path
    assert updated[chosen_key] == total_var


def test_select_variance_aggregations_cogs_filters_and_sets_primary_choice():
    # Arrange
    n = get_naming_params()
    options_key = n["varianceAggregationOptionsArray"]
    chosen_key = n["varianceAggregation"]
    diff_calc_key = n["varianceDifferentCalculations"]
    met = n["metConditionValue"]

    cogs_choice = n["cogsAggregation"]  # in cogs aggregation array
    costs_units = n["costsUnitsAggregation"]
    margin_units_rate = n["marginUnitsRateAggregation"]
    total_var = n["totalVarianceAggregation"]  # not in the margin list to plot

    chart_dict = {
        options_key: [costs_units, margin_units_rate, total_var],
        chosen_key: cogs_choice,
    }

    # Act
    aggregations_to_plot, updated = select_variance_aggregations_to_plot(chart_dict)

    # Assert
    assert aggregations_to_plot == [costs_units, margin_units_rate]
    assert updated[options_key] == [costs_units, margin_units_rate]
    assert updated[diff_calc_key] == met
    # For cogs, if marginUnitsRateAggregation is present, it becomes the chosen aggregation
    assert updated[chosen_key] == margin_units_rate
