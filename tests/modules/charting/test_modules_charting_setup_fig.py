from __future__ import annotations

import math

import plotly.graph_objects as go

from modules.charting.setup_fig import (
    setup_fig_for_horizontal_waterfall_charts,
    setup_fig_for_multitier_bar_charts,
    setup_fig_for_stacked_column_charts,
)
from modules.utilities.config import get_config_params, get_naming_params


def _base_chart_dict(**overrides):
    """Minimal chartDict with required keys for setup functions.

    Accepts overrides to toggle behaviour in tests.
    """
    n = get_naming_params()
    base = {
        n["chosenChart"]: n["stackedBarChart"],  # value unused but required
        n["plotSmallMultiplesOtherCharts"]: False,
        "X": {n["numberOfTop"]: 3},  # used by multi-tier path when not Total
    }
    base.update(overrides)
    return base


def test_setup_fig_for_stacked_column_charts_small_multiples_sets_rows_cols_and_fig_key():
    n = get_naming_params()
    repeat = ["A", "B", "C"]  # 3 items -> rows = ceil(3/2) = 2, cols = 2
    param_dict = {}
    chart_dict = _base_chart_dict(**{n["plotSmallMultiplesOtherCharts"]: True})

    updated, ncols, nrows = setup_fig_for_stacked_column_charts(
        df=None,
        repeatArray=repeat,
        chosenDimension="any",
        paramDict=param_dict,
        chartDict=chart_dict,
    )

    assert (ncols, nrows) == (2, 2)
    assert n["figureName"] in updated
    assert isinstance(updated[n["figureName"]], go.Figure)


def test_setup_fig_for_stacked_column_charts_single_no_small_multiples_is_1x1():
    n = get_naming_params()
    param_dict = {}
    chart_dict = _base_chart_dict(**{n["plotSmallMultiplesOtherCharts"]: False})

    updated, ncols, nrows = setup_fig_for_stacked_column_charts(
        df=None,
        repeatArray=["only"],
        chosenDimension="any",
        paramDict=param_dict,
        chartDict=chart_dict,
    )

    assert (ncols, nrows) == (1, 1)
    assert isinstance(updated[n["figureName"]], go.Figure)


def test_setup_fig_for_multitier_bar_charts_small_multiples_total_dimension_sizes():
    n = get_naming_params()
    c = get_config_params()
    gr = c[n["goldenRatio"]]

    # 2 items -> rows=ceil(2/2)=1, cols=2; Total path sets explicit height/width
    repeat = ["A", "B"]
    chart_dict = _base_chart_dict(**{n["plotSmallMultiplesOtherCharts"]: True})

    fig, height, width, ncols, nrows = setup_fig_for_multitier_bar_charts(
        repeatArray=repeat,
        chosenDimension=n["totalName"],
        paramDict={},
        chartDict=chart_dict,
    )

    assert isinstance(fig, go.Figure)
    assert (ncols, nrows) == (2, 1)

    # Expected from code: height = 150 + 20*rows + 20*(rows-1)
    exp_height = 150 + 20 * 1 + 20 * (1 - 1)
    assert math.isclose(height, exp_height, rel_tol=1e-9)

    # width = height * goldenRatio * ncols * 2.2
    exp_width = exp_height * gr * 2 * 2.2
    assert math.isclose(width, exp_width, rel_tol=1e-9)


def test_setup_fig_for_multitier_bar_charts_no_small_multiples_defaults_to_3_cols():
    n = get_naming_params()
    chart_dict = _base_chart_dict(**{n["plotSmallMultiplesOtherCharts"]: False})

    fig, height, width, ncols, nrows = setup_fig_for_multitier_bar_charts(
        repeatArray=["metric"],
        chosenDimension="not_total",
        paramDict={},
        chartDict=chart_dict,
    )

    assert (ncols, nrows) == (3, 1)
    assert height is None and width is None
    # Titles include Δ and Δ%
    titles = [a.text for a in (fig.layout.annotations or [])]
    assert any(t for t in titles if t == n["deltaName"])
    assert any(t for t in titles if t == f"{n['deltaName']}%")


def test_setup_fig_for_horizontal_waterfall_small_multiples_dimensions():
    n = get_naming_params()
    c = get_config_params()
    gr = c[n["goldenRatio"]]

    # 1 item, small multiples path: cols fixed at 2, rows=1
    chart_dict = _base_chart_dict(**{n["plotSmallMultiplesOtherCharts"]: True})
    fig, height, width, ncols, nrows = setup_fig_for_horizontal_waterfall_charts(
        repeatArray=["A"],
        chosenDimension="any",
        chartDict=chart_dict,
        plotWithPins=False,
    )

    assert isinstance(fig, go.Figure)
    assert (ncols, nrows) == (2, 1)
    assert math.isclose(height, 400, rel_tol=1e-9)
    assert math.isclose(width, 400 * gr * 2, rel_tol=1e-9)


def test_setup_fig_for_horizontal_waterfall_with_pins_uses_two_rows_single_col():
    n = get_naming_params()
    c = get_config_params()
    gr = c[n["goldenRatio"]]

    chart_dict = _base_chart_dict(**{n["plotSmallMultiplesOtherCharts"]: True})
    fig, height, width, ncols, nrows = setup_fig_for_horizontal_waterfall_charts(
        repeatArray=["A"],
        chosenDimension="any",
        chartDict=chart_dict,
        plotWithPins=True,
    )

    assert (ncols, nrows) == (1, 2)
    assert math.isclose(height, 500, rel_tol=1e-9)
    assert math.isclose(width, 500 * gr * 1, rel_tol=1e-9)
