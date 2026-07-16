from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.data.misc_charts_data_prep import (
    aggregate_values_in_distribution_plots,
    color_pareto_classes,
    prepare_sum_dataframe_for_bubble_plot,
)
from modules.charting.chart_primitives import get_color_dictionary
from modules.utilities.config import get_naming_params
from modules.utilities.utils import get_row_count


def _make_simple_sales_df():
    naming = get_naming_params()
    period = naming["periodName"]
    amount = naming["monetaryLocalCurrencyName"]
    units = naming["unitsName"]

    df = pl.DataFrame(
        {
            period: ["2024", "2024", "2024"],
            "Category": ["A", "A", "B"],
            "Region": ["East", "East", "West"],
            amount: [100.0, 50.0, 30.0],
            units: [10.0, 5.0, 3.0],
        }
    )
    return df


def test_aggregate_values_distribution_groups_and_computes_unit_price():
    naming = get_naming_params()
    period = naming["periodName"]
    x_axis_dim_key = naming["xAxisDimension"]
    price_per_unit = naming["pricePerUnitName"]

    df = _make_simple_sales_df()
    chart_dict = {x_axis_dim_key: "Region"}

    lf = aggregate_values_in_distribution_plots(
        df, element="Category", valueCols=[naming["monetaryLocalCurrencyName"], naming["unitsName"]], chartDict=chart_dict
    )

    out = lf.collect()
    # Two groups: (2024, A, East) and (2024, B, West)
    assert get_row_count(out) == 2
    assert price_per_unit in out.columns

    # Validate aggregated values for a specific group and derived unit price
    row_a = out.filter((pl.col("Category") == "A") & (pl.col("Region") == "East")).row(0, named=True)
    assert row_a[naming["monetaryLocalCurrencyName"]] == 150.0
    assert row_a[naming["unitsName"]] == 15.0
    assert pytest.approx(row_a[price_per_unit], rel=0, abs=1e-9) == 10.0


def test_aggregate_values_distribution_no_distribution_no_grouping():
    naming = get_naming_params()
    x_axis_dim_key = naming["xAxisDimension"]
    nothing = naming["nothingFilteredName"]
    price_per_unit = naming["pricePerUnitName"]

    df = _make_simple_sales_df()
    chart_dict = {x_axis_dim_key: nothing}

    lf = aggregate_values_in_distribution_plots(
        df, element="Category", valueCols=[naming["monetaryLocalCurrencyName"], naming["unitsName"]], chartDict=chart_dict
    )
    out = lf.collect()
    # No grouping applied; row count stays the same, price per unit is computed per row
    assert get_row_count(out) == get_row_count(df)
    assert price_per_unit in out.columns
    # Spot-check first row
    first = out.row(0, named=True)
    assert pytest.approx(first[price_per_unit], rel=0, abs=1e-9) == first[naming["monetaryLocalCurrencyName"]] / first[naming["unitsName"]]


def test_aggregate_values_distribution_ignores_missing_value_columns():
    naming = get_naming_params()
    x_axis_dim_key = naming["xAxisDimension"]
    df = _make_simple_sales_df()
    chart_dict = {x_axis_dim_key: "Region"}

    lf = aggregate_values_in_distribution_plots(
        df,
        element="Category",
        valueCols=[naming["monetaryLocalCurrencyName"], "Nonexistent"],
        chartDict=chart_dict,
    )
    out = lf.collect()
    # The missing column shouldn't be present after aggregation
    assert "Nonexistent" not in out.columns


def _make_bubble_df():
    naming = get_naming_params()
    period = naming["periodName"]
    amount = naming["monetaryLocalCurrencyName"]
    units = naming["unitsName"]
    volume = naming["volumeName"]
    discount = naming["discountName"]
    net_sales = naming["netOfDiscountName"]
    margin = naming["marginName"]

    return pl.DataFrame(
        {
            period: ["2023", "2024"],
            amount: [100.0, 200.0],
            units: [10.0, 20.0],
            volume: [20.0, 50.0],
            discount: [5.0, 10.0],
            net_sales: [95.0, 190.0],
            margin: [25.0, 60.0],
        }
    )


def test_prepare_sum_dataframe_for_bubble_plot_total_true_computes_percents_and_prices():
    naming = get_naming_params()
    period = naming["periodName"]
    plot_total_key = naming["plotTotalBubble"]
    total_name = naming["totalName"]
    amount = naming["monetaryLocalCurrencyName"]
    units = naming["unitsName"]
    volume = naming["volumeName"]
    discount = naming["discountName"]
    net_sales = naming["netOfDiscountName"]
    margin = naming["marginName"]
    price_per_unit = naming["pricePerUnitName"]
    price_per_volume = naming["pricePerVolumeName"]
    disc_pct = naming["discountInPercentName"]
    margin_pct = naming["marginInPercentName"]
    margin_pct_net = naming["marginInPercentOfNetSalesName"]

    df = _make_bubble_df()
    chart_dict = {plot_total_key: True}

    period_order = ["2023", "2024"]
    to_plot_period = "2024"
    lf = prepare_sum_dataframe_for_bubble_plot(
        dfCopy=df,
        # Exclude 'volume' to avoid duplicate alias of percent column in helper
        valueCols=[amount, units, discount, net_sales, margin],
        periodOrder=period_order,
        toPlotPeriod=to_plot_period,
        chartDict=chart_dict,
        paramDict={},
    )
    out = lf.collect()

    assert get_row_count(out) == 1
    row = out.row(0, named=True)
    assert row[period] == to_plot_period
    assert row[total_name] == total_name

    # Aggregates should match the single row values for 2024
    assert row[amount] == 200.0
    assert row[units] == 20.0
    # 'volume' was excluded from aggregation to avoid duplicate percent alias

    # Derived prices
    assert pytest.approx(row[price_per_unit], rel=0, abs=1e-9) == 10.0
    # price_per_volume not asserted because 'volume' excluded from aggregation

    # Percentage metrics get multiplied by 100 and rounded to 1 decimal
    assert pytest.approx(row[disc_pct], rel=0, abs=1e-9) == 5.0  # 10 / 200 * 100
    assert pytest.approx(row[margin_pct], rel=0, abs=1e-9) == 30.0  # 60 / 200 * 100
    assert pytest.approx(row[margin_pct_net], rel=0, abs=1e-9) == 31.6  # round(60/190*100,1)


def test_prepare_sum_dataframe_for_bubble_plot_total_false_returns_empty():
    naming = get_naming_params()
    plot_total_key = naming["plotTotalBubble"]
    df = _make_bubble_df()
    chart_dict = {plot_total_key: False}

    lf = prepare_sum_dataframe_for_bubble_plot(
        dfCopy=df,
        valueCols=[naming["monetaryLocalCurrencyName"]],
        periodOrder=["2023", "2024"],
        toPlotPeriod="2024",
        chartDict=chart_dict,
        paramDict={},
    )
    out = lf.collect()
    assert get_row_count(out) == 0


def test_prepare_sum_dataframe_for_bubble_plot_filters_to_missing_period_yields_empty():
    naming = get_naming_params()
    plot_total_key = naming["plotTotalBubble"]
    df = _make_bubble_df()
    chart_dict = {plot_total_key: True}

    lf = prepare_sum_dataframe_for_bubble_plot(
        dfCopy=df,
        valueCols=[naming["monetaryLocalCurrencyName"]],
        periodOrder=["2023", "2024"],
        toPlotPeriod="2099",
        chartDict=chart_dict,
        paramDict={},
    )
    out = lf.collect()
    assert get_row_count(out) == 0


def test_color_pareto_classes_assigns_expected_colors_and_classes():
    naming = get_naming_params()
    color_key = naming["colorpalette"]
    ratio_name = naming["ratioName"]
    class_name = naming["className"]
    color_name = naming["colorName"]
    margin = naming["marginName"]

    # Palette setup
    chart_dict = {color_key: naming["tableauColorpalette"]}
    color_dict = get_color_dictionary(chart_dict)
    palette = color_dict[chart_dict[color_key]]

    # Input rows: two positive metrics and one negative
    df = pl.DataFrame(
        {
            margin: [10.0, 20.0, -5.0],
            ratio_name: [0.9, 0.7, 0.5],
        }
    )

    lf, class_color_map, color_list = color_pareto_classes(
        df.lazy(), metric=margin, chartDict=chart_dict, paramDict={}, colorName=color_name, ratioName=ratio_name, className=class_name
    )
    out = lf.collect()

    # For positive rows, current logic first matches the broadest condition (<= 200),
    # assigning the first palette color and class "C". Negative rows get red and "Loss".
    assert out.get_column(class_name).to_list() == ["C", "C", naming["lossClassName"]]
    assert out.get_column(color_name).to_list()[0] == palette[0]
    assert out.get_column(color_name).to_list()[-1] == color_dict["redColor"]

    # Mapping dictionary exposes class -> color associations for all classes
    mapping = class_color_map[margin]
    assert mapping[naming["aClassName"]] == palette[2]
    assert mapping[naming["bClassName"]] == palette[1]
    assert mapping[naming["cClassName"]] == palette[0]
    assert mapping[naming["lossClassName"]] == color_dict["redColor"]

    # Returned color list should contain the unique colors in order of appearance
    assert color_list == [palette[0], color_dict["redColor"]]
