import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pytest

from modules.charting.draw_waterfall import (
    color_first_bar_vertical,
    set_semantic_bar_color,
    add_total_variance_arrow_horizontal,
)
from modules.utilities.config import get_naming_params


def _base_colors():
    # Minimal color dictionary required by the target functions
    return {
        "whiteColor": "#ffffff",
        "lightGreyColor": "#cccccc",
        "veryLightGreyColor": "#eeeeee",
        "greenColor": "#00ff00",
        "redColor": "#ff0000",
    }


@pytest.mark.parametrize(
    "is_expected,param_dict,expected",
    [
        (True, {}, ("#ffffff", 0.5, "#cccccc")),
        # previous-year styling when not expected data
        (False, {get_naming_params()["isYearBeforePy"]: True}, ("#eeeeee", 0.5, "#eeeeee")),
        # default grey when neither expected nor previous-year
        (False, {}, ("#cccccc", 0.5, "#cccccc")),
    ],
)
def test_set_semantic_bar_color_variants(is_expected, param_dict, expected):
    color_dict = _base_colors()
    result = set_semantic_bar_color(is_expected, color_dict, param_dict)
    assert result == expected


def test_color_first_bar_vertical_adds_rect_for_plan_label():
    naming = get_naming_params()
    work_col = naming["workColumn"]
    var_col = naming["varianceAmountName"]

    # First label contains a plan stem (e.g., "PL"), variance positive
    df = pl.DataFrame({work_col: ["PL"], var_col: [100]})
    fig = make_subplots(rows=1, cols=1)

    chart_dict = {
        naming["showInitialAndFinalValues"]: True,
        naming["varianceAggregation"]: naming["totalVarianceAggregation"],
    }
    color_dict = _base_colors()

    out = color_first_bar_vertical(df, fig, {}, chart_dict, color_dict, run="")

    # A rectangle should have been added with the semantic color for expected data
    assert len(out.layout.shapes) == 1
    shape = out.layout.shapes[0]
    assert shape.type == "rect"
    assert shape.fillcolor == color_dict["whiteColor"]
    # The bar spans from 0 to the first variance value
    assert shape.x0 == 0
    assert shape.x1 == 100


def test_color_first_bar_vertical_skips_on_drilldown_with_non_total_variance():
    naming = get_naming_params()
    work_col = naming["workColumn"]
    var_col = naming["varianceAmountName"]

    df = pl.DataFrame({work_col: ["AC"], var_col: [50]})
    fig = make_subplots(rows=1, cols=1)

    chart_dict = {
        naming["showInitialAndFinalValues"]: True,
        # Use a variance aggregation not in the allowed list
        naming["varianceAggregation"]: "some-other-aggregation",
    }
    color_dict = _base_colors()
    # Run string contains the drilldown flag, which suppresses initial/final shapes
    run = naming["drilldownReportRunName"] + " active"

    out = color_first_bar_vertical(df, fig, {}, chart_dict, color_dict, run)
    assert len(out.layout.shapes) == 0


def test_add_total_variance_arrow_horizontal_adds_green_arrow_and_annotation():
    naming = get_naming_params()
    var_col = naming["varianceAmountName"]

    # period0=100 -> period1=120 (positive change)
    df = pl.DataFrame({var_col: [100, 120]})
    fig = make_subplots(rows=1, cols=1)

    chart_dict = {
        naming["showInitialAndFinalValues"]: True,
        naming["varianceAggregation"]: naming["totalVarianceAggregation"],
    }
    color_dict = _base_colors()

    out = add_total_variance_arrow_horizontal(
        df,
        fig,
        {},
        chart_dict,
        color_dict,
        run="",
        metric=naming["marginName"],  # not a reversed-color metric
        row=1,
        col=1,
    )

    # Three shapes added: baseline, final line, and the arrow (last, width=5)
    assert len(out.layout.shapes) == 3
    arrow = out.layout.shapes[-1]
    assert arrow.line.width == 5
    assert arrow.line.color == color_dict["greenColor"]

    # Annotation present with delta text (content formatting not asserted exactly)
    assert len(out.layout.annotations) >= 1
    assert any("Δ" in ann.text for ann in out.layout.annotations)


def test_add_total_variance_arrow_horizontal_no_annotation_when_base_zero():
    naming = get_naming_params()
    var_col = naming["varianceAmountName"]

    # period0=0 -> period1=50 triggers no annotation branch
    df = pl.DataFrame({var_col: [0, 50]})
    fig = make_subplots(rows=1, cols=1)
    chart_dict = {
        naming["showInitialAndFinalValues"]: True,
        naming["varianceAggregation"]: naming["totalVarianceAggregation"],
    }
    color_dict = _base_colors()

    out = add_total_variance_arrow_horizontal(
        df,
        fig,
        {},
        chart_dict,
        color_dict,
        run="",
        metric=naming["marginName"],
        row=1,
        col=1,
    )

    # Shapes added but no annotation when the base period is zero
    assert len(out.layout.shapes) == 3
    assert len(out.layout.annotations) == 0
    assert out.layout.shapes[-1].line.color == color_dict["greenColor"]


def test_add_total_variance_arrow_horizontal_reversed_metric_uses_red_on_increase():
    naming = get_naming_params()
    var_col = naming["varianceAmountName"]

    df = pl.DataFrame({var_col: [100, 120]})
    fig = make_subplots(rows=1, cols=1)
    chart_dict = {
        naming["showInitialAndFinalValues"]: True,
        naming["varianceAggregation"]: naming["totalVarianceAggregation"],
    }
    color_dict = _base_colors()

    out = add_total_variance_arrow_horizontal(
        df,
        fig,
        {},
        chart_dict,
        color_dict,
        run="",
        metric=naming["discountName"],  # reversed-color metric
        row=1,
        col=1,
    )

    assert len(out.layout.shapes) == 3
    arrow = out.layout.shapes[-1]
    assert arrow.line.width == 5
    assert arrow.line.color == color_dict["redColor"]
