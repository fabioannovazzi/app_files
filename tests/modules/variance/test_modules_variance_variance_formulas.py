import polars as pl
import pytest

from polars.testing import assert_frame_equal

from modules.utilities.config import get_config_params, get_naming_params
from modules.variance.variance_formulas import (
    set_variance_if_one_period_no_sales_and_cogs,
    set_variance_if_one_period_no_sales_and_discount,
    set_volume_and_price_variance_if_one_period_no_sales,
)


def _basic_columns():
    """Helper to build common column names from config/naming."""
    config = get_config_params()
    naming = get_naming_params()
    p0, p1 = config["periodsArray"]
    sep = naming["separatorString"]
    amount0 = naming["monetaryLocalCurrencyName"] + sep + p0
    amount1 = naming["monetaryLocalCurrencyName"] + sep + p1
    return {
        "amount0": amount0,
        "amount1": amount1,
        "volume_var": naming["volumeVariance"],
        "price_var": naming["priceVariance"],
        "new_vol": naming["newVolumeVarianceName"],
        "lost_vol": naming["lostVolumeVarianceName"],
        "cogs0": naming["cogsName"] + sep + p0,
        "cogs1": naming["cogsName"] + sep + p1,
        "discount0": naming["discountName"] + sep + p0,
        "discount1": naming["discountName"] + sep + p1,
        "cost_var": naming["costVariance"],
    }


def test_set_volume_and_price_variance_new_or_lost_true():
    # Arrange
    cols = _basic_columns()
    df = pl.DataFrame(
        {
            cols["amount0"]: [0, 5, 5],
            cols["amount1"]: [10, 0, 5],
            cols["volume_var"]: [7, 7, 7],
            cols["price_var"]: [3, 3, 3],
        }
    )

    # Act
    out_df, out_params = set_volume_and_price_variance_if_one_period_no_sales(
        df, True, "onGrossSales", {}
    )

    # Assert
    expected = pl.DataFrame(
        {
            cols["new_vol"]: [10, 0, 0],
            cols["lost_vol"]: [0, -5, 0],
            cols["volume_var"]: [0, 0, 7],
            cols["price_var"]: [0, 0, 3],
        }
    )
    assert_frame_equal(
        out_df.select(expected.columns), expected, check_row_order=True
    )
    assert out_params == {}


def test_set_volume_and_price_variance_changed_branch():
    # Arrange
    cols = _basic_columns()
    df = pl.DataFrame(
        {
            cols["amount0"]: [0, 5, 5],
            cols["amount1"]: [10, 0, 5],
            cols["volume_var"]: [7, 7, 7],
            cols["price_var"]: [3, 3, 3],
        }
    )

    # Act (newOrLost=False enters the changed-items branch)
    out_df, out_params = set_volume_and_price_variance_if_one_period_no_sales(
        df, False, "onGrossSales", {}
    )

    # Assert
    expected = pl.DataFrame(
        {
            cols["volume_var"]: [10, -5, 7],
            cols["price_var"]: [0, 0, 3],
        }
    )
    assert_frame_equal(
        out_df.select(expected.columns), expected, check_row_order=True
    )
    assert out_params == {}


def test_set_variance_if_one_period_no_sales_and_cogs_updates_volume_and_cost():
    # Arrange
    cols = _basic_columns()
    df = pl.DataFrame(
        {
            cols["amount0"]: [0, 5, 5],
            cols["amount1"]: [10, 0, 5],
            cols["cogs0"]: [1, 7, 1],
            cols["cogs1"]: [11, 3, 1],
            cols["volume_var"]: [100, 100, 100],
            cols["cost_var"]: [9, 8, 7],
        }
    )

    # Act
    out_df, out_params = set_variance_if_one_period_no_sales_and_cogs(
        df, cols["cost_var"], "onGrossSales", {}
    )

    # Assert
    expected = pl.DataFrame(
        {
            cols["volume_var"]: [100 - 11, 100 + 7, 100],
            cols["cost_var"]: [0, 0, 7],
        }
    )
    assert_frame_equal(
        out_df.select(expected.columns), expected, check_row_order=True
    )
    assert out_params == {}


def test_set_variance_if_one_period_no_sales_and_discount_assigns_from_discounts():
    # Arrange
    cols = _basic_columns()
    df = pl.DataFrame(
        {
            cols["amount0"]: [0, 5, 5],
            cols["amount1"]: [10, 0, 5],
            cols["discount0"]: [3, 20, 5],
            cols["discount1"]: [2, 40, 6],
            cols["cost_var"]: [100, 100, 100],  # reuse cost_var as a generic target column
        }
    )

    # Act
    out_df = set_variance_if_one_period_no_sales_and_discount(df, cols["cost_var"])

    # Assert
    expected = pl.DataFrame({cols["cost_var"]: [-2, 20, 100]})
    assert_frame_equal(
        out_df.select(expected.columns), expected, check_row_order=True
    )


def test_set_volume_and_price_variance_raises_on_wrong_type():
    with pytest.raises(TypeError):
        set_volume_and_price_variance_if_one_period_no_sales(
            {"not": "a polars df"}, True, "onGrossSales", {}
        )
