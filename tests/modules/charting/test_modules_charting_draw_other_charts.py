import sys
import types

import polars as pl
from plotly.subplots import make_subplots
import pytest


@pytest.fixture(scope="module")
def mod():
    # Stub only the problematic dependency before importing the target module.
    fake_ch = types.ModuleType("modules.charting.chart_helpers")

    def _noop_setup(*_a, **_k):
        return {}

    fake_ch.set_up_tab_for_show_or_download_chart = _noop_setup
    sys.modules["modules.charting.chart_helpers"] = fake_ch

    # Additional light stubs to avoid deep import chains not exercised here
    fake_tl = types.ModuleType("modules.charting.draw_timeline")
    fake_tl.add_labels_to_timeline_chart = lambda *a, **k: a[0] if a else None
    sys.modules["modules.charting.draw_timeline"] = fake_tl

    fake_mt = types.ModuleType("modules.charting.make_titles")
    fake_mt.make_horizontal_waterfall_chart_title = (
        lambda df, chosen, param, key, metric, chart, py, ac: ("", param, chart)
    )
    fake_mt.make_stacked_pareto_and_pareto_chart_title = (
        lambda df, chosen, param, key, metric, chart, period, _: ("", param, chart)
    )
    sys.modules["modules.charting.make_titles"] = fake_mt

    fake_sf = types.ModuleType("modules.charting.setup_fig")
    fake_sf.add_integrated_legends_to_trend_plot = lambda *a, **k: a[0]
    fake_sf.setup_fig_for_actual_vs_previous_year_charts = lambda *a, **k: a[0]
    sys.modules["modules.charting.setup_fig"] = fake_sf

    # Now import the real module under test
    from modules.charting import draw_other_charts as _mod

    return _mod


def _stub_colors():
    # Minimal palette keys used by targets
    return {
        "whiteColor": "white",
        "almostBlackColor": "black",
        "greyColor": "grey",
        "lightGreyColor": "lightgrey",
        "greenColor": "green",
        "redColor": "red",
    }


def _stub_naming_params():
    # Provide only the keys referenced by the targeted functions
    return {
        "periodName": "period",
        "labelName": "label",
        "otherLabelName": "py_label",
        "colorName": "color",
        "timelineChart": "timeline",
        "plotValuesAsChoice": "plotValuesAsChoice",
        "absolute": "absolute",
        "chosenChart": "chosenChartKey",
        "metConditionValue": 1,
        "notMetConditionValue": 0,
        "trendComparisonChart": "trendComparison",
        "trendComparisonByPeriodChart": "trendComparisonByPeriod",
        "plotAsBaseline": "plotAsBaselineKey",
        "pyName": "py",
        "labelPosition": "label_pos",
        "maxValue": "max",
        "minValue": "min",
    }


@pytest.mark.parametrize(
    "label,expected",
    [
        (1, "green"),
        (2, "green"),
        (0, "red"),
        (-1, "red"),
    ],
)
def test_fillcol_threshold(mod, monkeypatch, label, expected):
    # Arrange: isolate color dictionary
    monkeypatch.setattr(mod, "get_color_dictionary", lambda _cd: _stub_colors())
    # Act
    color = mod.fillcol(label, chartDict={})
    # Assert
    assert color == expected


def test_adjust_ac_py_plot_calls_in_order(mod, monkeypatch):
    # Arrange: stub naming and the called helpers with side effects on fig
    monkeypatch.setattr(mod, "get_naming_params", lambda: {"chosenChart": "chosen"})
    seen = {"chosen": None}

    class DummyFig:
        def __init__(self):
            self.steps = []

    def _update(fig, *a, **k):
        fig.steps.append("layout")
        return fig

    def _user_msg(fig, chosen_chart, metric, key, *a, **k):
        seen["chosen"] = chosen_chart
        fig.steps.append("user_message")
        return fig, "the-msg"

    def _add_msg(fig, message, *a, **k):
        assert message == "the-msg"  # message propagated
        fig.steps.append("add_message")
        return fig

    def _add_title(fig, *a, **k):
        fig.steps.append("add_title")
        return fig

    def _enable_shapes(fig, *a, **k):
        fig.steps.append("enable_shapes")
        return fig

    monkeypatch.setattr(mod, "update_cy_ac_layout", _update)
    monkeypatch.setattr(mod, "get_user_message", _user_msg)
    monkeypatch.setattr(mod, "add_message_as_annotation", _add_msg)
    monkeypatch.setattr(mod, "add_title_as_annotation", _add_title)
    monkeypatch.setattr(mod, "enable_draw_shapes", _enable_shapes)

    fig = DummyFig()
    chartDict = {"chosen": "resolved-chart-name"}

    # Act
    out = mod.adjust_ac_py_plot(
        fig,
        df=None,
        key="k",
        metric="m",
        title="T",
        height=100,
        width=200,
        paramDict={},
        chartDict=chartDict,
        plotWithPins=False,
    )

    # Assert
    assert out is fig
    assert seen["chosen"] == "resolved-chart-name"  # chartDict lookup happened
    assert fig.steps == [
        "layout",
        "user_message",
        "add_message",
        "add_title",
        "enable_shapes",
    ]


def test_draw_cy_ac_plotly_traces_and_layout(mod, monkeypatch):
    # Arrange: tiny deterministic frame with two color groups (1,1) then (0,0)
    df = pl.DataFrame(
        {
            "color": [1, 1, 0, 0],
            "min": [1.0, 2.0, 1.0, 1.0],
            "max": [3.0, 5.0, 2.0, 3.0],
            "ac": [5.0, 6.0, 7.0, 8.0],
            "py": [4.0, 5.0, 6.0, 7.0],
            "label": ["a", "b", "c", "d"],
            "py_label": ["pa", "pb", "pc", "pd"],
        }
    )

    monkeypatch.setattr(mod, "get_naming_params", _stub_naming_params)
    monkeypatch.setattr(mod, "get_color_dictionary", lambda _cd: _stub_colors())

    fig = make_subplots(rows=1, cols=1)
    chartDict = {"chosenChartKey": "trendComparison"}

    # Act
    fig, returned_chartDict = mod.draw_cy_ac_plotly(
        fig,
        df,
        paramDict={},
        title="irrelevant",
        countRows=1,
        countCols=1,
        yArray=["ac", "py"],
        chartDict=chartDict,
    )

    # Assert: stacked bars layout and chartDict round-trips
    assert fig.layout.barmode == "stack"
    assert returned_chartDict is chartDict

    # There are always two bar traces per color run -> 4 in total
    bar_traces = [t for t in fig.data if t.type == "bar"]
    assert len(bar_traces) == 4
    # Colored bars (exclude the white base) reflect group colors: green then red
    colored = [t for t in bar_traces if getattr(t.marker, "color", None) != "white"]
    assert [t.marker.color for t in colored] == ["green", "red"]

    # Total traces differ only by the optional area-fill per group when baseline
    assert len(fig.data) == 10
