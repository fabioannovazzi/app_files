import pytest
import polars as pl
from polars.testing import assert_frame_equal

from modules.utilities.config import get_naming_params
from modules.data.waterfall_data_prep import (
    ensure_lazyframe,
    get_totals_for_discount_variance_aggregations,
    get_totals_for_margin_variance_aggregations,
)


def test_ensure_lazyframe_on_dataframe_returns_lazyframe_with_same_data():
    # Arrange
    df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})

    # Act
    lf = ensure_lazyframe(df)

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    assert_frame_equal(lf.collect(), df)


def test_ensure_lazyframe_on_lazyframe_returns_same_object():
    # Arrange
    df = pl.DataFrame({"x": [10]})
    lf = df.lazy()

    # Act
    res = ensure_lazyframe(lf)

    # Assert
    assert res is lf


def test_ensure_lazyframe_unsupported_type_raises_typeerror():
    # Arrange
    not_a_frame = {"x": [1, 2, 3]}

    # Act / Assert
    with pytest.raises(TypeError):
        ensure_lazyframe(not_a_frame)  # type: ignore[arg-type]


def test_get_totals_for_discount_variance_basic_not_filtered_not_percent():
    # Arrange
    naming = get_naming_params()
    is_filtered = naming["isFilteredKey"]
    not_met = naming["notMetConditionValue"]

    p0_key = naming["totalNetOfDiscountPeriodZero"]
    p1_key = naming["totalNetOfDiscountPeriodOne"]
    variance_key = naming["netOfDiscountVariance"]

    param = {
        is_filtered: not_met,
        p0_key: 10.0,
        p1_key: 15.0,
        variance_key: 5.0,
    }
    chart = {}

    # Act
    (
        total_var,
        total_p0,
        total_p1,
        label_p0,
        label_p1,
        df_filtered,
    ) = get_totals_for_discount_variance_aggregations(
        param, chart, mainDimension="m", element="e", dfBase=None, count=0, run="r"
    )

    # Assert
    assert total_var == 5.0
    assert total_p0 == 10.0
    assert total_p1 == 15.0
    assert label_p0 == p0_key
    assert label_p1 == p1_key
    assert isinstance(df_filtered, pl.LazyFrame)
    assert df_filtered.collect().height == 0


def test_get_totals_for_discount_variance_percent_and_filtered():
    # Arrange
    naming = get_naming_params()
    is_filtered = naming["isFilteredKey"]
    met = naming["metConditionValue"]
    not_met = naming["notMetConditionValue"]

    p0_key = naming["totalNetOfDiscountPeriodZero"]
    p1_key = naming["totalNetOfDiscountPeriodOne"]
    p0_filt_key = naming["totalNetOfDiscountPeriodZeroFiltered"]
    p1_filt_key = naming["totalNetOfDiscountPeriodOneFiltered"]
    p0_pct_key = naming["totalNetOfDiscountPeriodZeroinPercent"]
    p1_pct_key = naming["totalNetOfDiscountPeriodOneinPercent"]
    p0_pct_filt_key = naming["totalNetOfDiscountPeriodZeroinPercentFiltered"]
    p1_pct_filt_key = naming["totalNetOfDiscountPeriodOneinPercentFiltered"]
    variance_key = naming["netOfDiscountVariance"]
    pct_variance_key = naming["percentVarianceAfterDiscounts"]
    pct_switch = naming["varianceInPercent"]

    # Must include filtered "plain" keys because the function sets them
    # before entering the percent branch when filtered.
    param = {
        is_filtered: met,  # filtered
        p0_key: 0.0,
        p1_key: 0.0,
        p0_filt_key: 1.0,
        p1_filt_key: 2.0,
        variance_key: -1.0,
        p0_pct_filt_key: 40.0,
        p1_pct_filt_key: 60.0,
        pct_variance_key: 20.0,
    }
    chart = {pct_switch: met}

    # Act
    (
        total_var,
        total_p0,
        total_p1,
        label_p0,
        label_p1,
        df_filtered,
    ) = get_totals_for_discount_variance_aggregations(
        param, chart, mainDimension="m", element="e", dfBase=None, count=0, run="r"
    )

    # Assert
    assert total_var == 20.0
    assert total_p0 == 40.0
    assert total_p1 == 60.0
    assert label_p0 == p0_pct_key
    assert label_p1 == p1_pct_key
    assert isinstance(df_filtered, pl.LazyFrame)


def test_get_totals_for_margin_variance_basic_not_filtered_not_percent_no_indirect_cost():
    # Arrange
    naming = get_naming_params()
    is_filtered = naming["isFilteredKey"]
    not_met = naming["notMetConditionValue"]

    p0_key = naming["totalMarginPeriodZero"]
    p1_key = naming["totalMarginPeriodOne"]
    variance_key = naming["marginVariance"]

    param = {
        is_filtered: not_met,
        p0_key: 10.0,
        p1_key: 20.0,
        variance_key: 10.0,
    }
    chart = {}

    # Act
    (
        total_var,
        total_p0,
        total_p1,
        label_p0,
        label_p1,
        df_filtered,
    ) = get_totals_for_margin_variance_aggregations(
        param, chart, mainDimension="m", element="e", dfBase=None, count=0, run="r"
    )

    # Assert
    assert total_var == 10.0
    assert total_p0 == 10.0
    assert total_p1 == 20.0
    assert label_p0 == p0_key
    assert label_p1 == p1_key
    assert isinstance(df_filtered, pl.LazyFrame)
    assert df_filtered.collect().height == 0


def test_get_totals_for_margin_variance_percent_and_filtered_no_indirect_cost():
    # Arrange
    naming = get_naming_params()
    is_filtered = naming["isFilteredKey"]
    met = naming["metConditionValue"]

    p0_key = naming["totalMarginPeriodZero"]
    p1_key = naming["totalMarginPeriodOne"]
    p0_filt_key = naming["totalMarginPeriodZeroFiltered"]
    p1_filt_key = naming["totalMarginPeriodOneFiltered"]
    p0_pct_key = naming["totalMarginPeriodZeroinPercent"]
    p1_pct_key = naming["totalMarginPeriodOneinPercent"]
    p0_pct_filt_key = naming["totalMarginPeriodZeroinPercentFiltered"]
    p1_pct_filt_key = naming["totalMarginPeriodOneinPercentFiltered"]
    variance_key = naming["marginVariance"]
    pct_variance_key = naming["percentVarianceAfterCogs"]
    pct_switch = naming["varianceInPercent"]

    param = {
        is_filtered: met,  # filtered
        p0_key: 0.0,
        p1_key: 0.0,
        p0_filt_key: 1.0,
        p1_filt_key: 2.0,
        variance_key: -1.0,
        p0_pct_filt_key: 30.0,
        p1_pct_filt_key: 70.0,
        pct_variance_key: 40.0,
    }
    chart = {pct_switch: met}

    # Act
    (
        total_var,
        total_p0,
        total_p1,
        label_p0,
        label_p1,
        df_filtered,
    ) = get_totals_for_margin_variance_aggregations(
        param, chart, mainDimension="m", element="e", dfBase=None, count=0, run="r"
    )

    # Assert
    assert total_var == 40.0
    assert total_p0 == 30.0
    assert total_p1 == 70.0
    assert label_p0 == p0_pct_key
    assert label_p1 == p1_pct_key
    assert isinstance(df_filtered, pl.LazyFrame)


def test_get_totals_for_margin_variance_with_indirect_costs_not_filtered():
    # Arrange
    naming = get_naming_params()
    is_filtered = naming["isFilteredKey"]
    not_met = naming["notMetConditionValue"]

    indirect_key = naming["indirectCostsVariance"]
    p0_net_key = naming["totalNetMarginPeriodZero"]
    p1_net_key = naming["totalNetMarginPeriodOne"]
    variance_key = naming["marginVariance"]

    param = {
        is_filtered: not_met,
        indirect_key: True,  # presence triggers the "indirect" path
        p0_net_key: 100.0,
        p1_net_key: 105.0,
        variance_key: 5.0,
    }
    chart = {}

    # Act
    (
        total_var,
        total_p0,
        total_p1,
        label_p0,
        label_p1,
        df_filtered,
    ) = get_totals_for_margin_variance_aggregations(
        param, chart, mainDimension="m", element="e", dfBase=None, count=0, run="r"
    )

    # Assert
    assert total_var == 5.0
    assert total_p0 == 100.0
    assert total_p1 == 105.0
    assert label_p0 == p0_net_key
    assert label_p1 == p1_net_key
    assert isinstance(df_filtered, pl.LazyFrame)


def test_get_totals_for_margin_variance_small_multiples_calls_subtotals(monkeypatch):
    # Arrange
    naming = get_naming_params()
    plot_sm = naming["plotSmallMultiplesWaterfall"]
    pct_switch = naming["varianceInPercent"]

    stub_df = pl.DataFrame({"x": [1]}).lazy()

    # Patch the module-level get_subtotals used by waterfall_data_prep
    def stub_get_subtotals(*args, **kwargs):
        return 11.0, 22.0, 33.0, stub_df

    import modules.data.waterfall_data_prep as wdp

    monkeypatch.setattr(wdp, "get_subtotals", stub_get_subtotals)

    param = {naming["isFilteredKey"]: naming["notMetConditionValue"]}
    chart = {plot_sm: True, pct_switch: naming["metConditionValue"]}

    # Act
    (
        total_var,
        total_p0,
        total_p1,
        label_p0,
        label_p1,
        df_filtered,
    ) = get_totals_for_margin_variance_aggregations(
        param,
        chart,
        mainDimension="m",
        element="e",
        dfBase=pl.DataFrame({"dummy": [1]}),
        count=0,
        run="r",
    )

    # Assert
    assert (total_p0, total_p1, total_var) == (11.0, 22.0, 33.0)
    assert label_p0 == naming["totalMarginPeriodZeroinPercent"]
    assert label_p1 == naming["totalMarginPeriodOneinPercent"]
    assert_frame_equal(df_filtered.collect(), stub_df.collect())
