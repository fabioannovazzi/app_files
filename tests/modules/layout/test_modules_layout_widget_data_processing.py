from __future__ import annotations

import polars as pl
from datetime import date
import pytest

from modules.layout.widget_data_processing import (
    count_periods,
    select_possible_aggregation_options,
    check_if_options_compatible_with_one_dimensional,
)
from modules.utilities.config import get_naming_params


def test_count_periods_with_date_and_year_choice_counts_unique_years():
    # Arrange
    naming = get_naming_params()
    date_col_found = naming["dateColFound"]
    period_col_found = naming["periodColFound"]
    date_name = naming["dateName"]
    year_name = naming["yearName"]
    period_choice = naming["periodChoice"]

    df = pl.DataFrame(
        {date_name: pl.Series(date_name, [
            date(2020, 1, 1),
            date(2021, 1, 1),
            date(2021, 5, 1),
            None,
        ], dtype=pl.Date)}
    )
    chart_dict = {period_choice: year_name}
    param_dict = {date_col_found: True, period_col_found: False}

    # Act
    n_periods, out_params = count_periods(df.lazy(), chart_dict, param_dict.copy())

    # Assert
    assert isinstance(n_periods, int)
    assert n_periods == 2  # unique years: 2020, 2021; None ignored
    # No error flags set/added in the happy path
    assert out_params.get(date_col_found) is True
    assert out_params.get(period_col_found) is False


def test_count_periods_with_period_column_counts_unique_non_null():
    # Arrange
    naming = get_naming_params()
    period_col_found = naming["periodColFound"]
    period_name = naming["periodName"]
    period_choice = naming["periodChoice"]
    year_name = naming["yearName"]

    df = pl.DataFrame({period_name: [1, 1, 2, None, 3]})
    chart_dict = {period_choice: year_name}  # not month or quarter => count unique
    param_dict = {period_col_found: True}

    # Act
    n_periods, _ = count_periods(df.lazy(), chart_dict, param_dict)

    # Assert
    assert n_periods == 3  # 1,2,3 (None ignored)


def test_count_periods_when_no_date_or_period_sets_error_and_impossible_flag():
    # Arrange
    naming = get_naming_params()
    impossible = naming["impossibleToProcessFile"]
    met_val = naming["metConditionValue"]
    app_msgs = naming["appMessageArray"]

    df = pl.DataFrame({})
    chart_dict = {}
    param_dict: dict = {}

    # Act
    n_periods, out_params = count_periods(df, chart_dict, param_dict)

    # Assert
    assert n_periods == 1  # falls back to default
    assert out_params.get(impossible) is met_val
    # An error message should be recorded in app message array
    assert app_msgs in out_params
    assert isinstance(out_params[app_msgs], list) and len(out_params[app_msgs]) >= 1


def test_select_possible_aggregation_options_happy_path_includes_expected_options():
    # Arrange
    naming = get_naming_params()
    cogs_found = naming["cogsColFound"]
    discount_found = naming["discountColFound"]
    units_found = naming["unitsColFound"]
    volume_found = naming["volumeColFound"]

    price_and_units = naming["priceAndUnitsAggregation"]
    price_and_volume = naming["priceAndVolumeAggregation"]
    net_of_discount = naming["netOfDiscountAggregation"]
    margin_variance = naming["marginVarianceAggregation"]
    discounts_units_cogs = naming["discountsUnitsCogsAggregation"]
    units_on_sales = naming["unitsOnSalesAggregation"]
    unit_price_on_sales = naming["unitPriceOnSalesAggregation"]

    flags = {
        cogs_found: True,
        discount_found: True,
        units_found: True,
        volume_found: True,
    }

    # Act
    options, percents, expanded = select_possible_aggregation_options(flags)

    # Assert
    assert isinstance(options, list) and options  # non-empty
    # Includes selections from each detected group
    assert margin_variance in options  # from COGS
    assert net_of_discount in options  # from discounts
    assert price_and_units in options  # from units
    assert price_and_volume in options  # from volume
    # When units present, the unit-specific COGS aggregation is allowed
    assert discounts_units_cogs in options

    # Percent aggregations are fixed
    assert percents == [margin_variance]

    # Expanded choices include expected children for price_and_units
    assert isinstance(expanded, dict)
    assert expanded.get(price_and_units) == [units_on_sales, unit_price_on_sales]


def test_select_possible_aggregation_options_without_units_filters_unit_requirements():
    # Arrange
    naming = get_naming_params()
    cogs_found = naming["cogsColFound"]
    units_found = naming["unitsColFound"]
    volume_found = naming["volumeColFound"]
    discounts_units_cogs = naming["discountsUnitsCogsAggregation"]
    discounts_volume_cogs = naming["discountsVolumeCogsAggregation"]

    flags = {cogs_found: True, units_found: False, volume_found: True}

    # Act
    options, _, _ = select_possible_aggregation_options(flags)

    # Assert
    assert discounts_units_cogs not in options  # requires units -> filtered out
    assert discounts_volume_cogs in options  # allowed with volume present


def test_select_possible_aggregation_options_with_no_signals_returns_empty():
    # Arrange
    flags: dict = {}

    # Act
    options, percents, expanded = select_possible_aggregation_options(flags)

    # Assert
    assert options == []
    assert isinstance(percents, list) and isinstance(expanded, dict)


def test_check_if_options_compatible_with_one_dimensional_returns_copy_for_one_dimensional():
    # Arrange
    naming = get_naming_params()
    processing_choice = naming["processingChoice"]
    run_one_dimensional = naming["runOneDimensionalAnalysis"]
    opts = [naming["priceAndUnitsAggregation"], naming["driverAndUnitsAggregation"]]
    chart = {processing_choice: run_one_dimensional}

    # Act
    out = check_if_options_compatible_with_one_dimensional(opts, chart)

    # Assert
    assert out == opts
    assert out is not opts  # copy returned in one-dimensional branch


def test_check_if_options_compatible_with_one_dimensional_returns_same_object_otherwise():
    # Arrange
    naming = get_naming_params()
    processing_choice = naming["processingChoice"]
    run_variable = naming["runVariableDimensionalAnalysis"]
    opts = [naming["priceAndVolumeAggregation"]]
    chart = {processing_choice: run_variable}

    # Act
    out = check_if_options_compatible_with_one_dimensional(opts, chart)

    # Assert
    assert out is opts
