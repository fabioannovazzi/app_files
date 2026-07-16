from __future__ import annotations

import polars as pl
import plotly.graph_objects as go
import pytest

from polars.testing import assert_frame_equal
from modules.utilities.config import get_naming_params


def _import_draw_multitier_with_stubs(monkeypatch):
    """Import draw_multitier while stubbing problematic LLM package imports."""
    import sys
    import types

    # Stub the 'modules.llm' package and its 'confirm_plots' submodule to avoid
    # importing heavy or broken dependencies during tests.
    llm_pkg = types.ModuleType("modules.llm")
    confirm_plots = types.ModuleType("modules.llm.confirm_plots")
    interpret_plots = types.ModuleType("modules.llm.interpret_plots")

    def _noop(*_a, **_k):
        return None

    confirm_plots.get_comments_from_data = _noop
    confirm_plots.get_comments_from_data_fragment = _noop
    confirm_plots.get_comments_from_images = _noop
    interpret_plots.explain_metrics_for_barmekko_prompt = _noop
    interpret_plots.explain_metrics_for_stacked_column_prompt = _noop

    sys.modules["modules.llm"] = llm_pkg
    sys.modules["modules.llm.confirm_plots"] = confirm_plots
    sys.modules["modules.llm.interpret_plots"] = interpret_plots

    import importlib

    return importlib.import_module("modules.charting.draw_multitier")


@pytest.mark.parametrize("as_lazy", [False, True])
def test_unique_values_lazy_preserves_order(monkeypatch, as_lazy: bool) -> None:
    # Arrange
    dm = _import_draw_multitier_with_stubs(monkeypatch)
    df = pl.DataFrame({"C": ["x", "y", "x", "z"]})
    data = df.lazy() if as_lazy else df

    # Act
    out = dm.unique_values_lazy("C", data)

    # Assert
    assert out == ["x", "y", "z"]


def test_adjust_multitier_column_plot_updates_annotation_font(monkeypatch) -> None:
    # Arrange: minimal fig and inputs
    dm = _import_draw_multitier_with_stubs(monkeypatch)
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=1, cols=1)
    df = pl.DataFrame({"AC": [1, 2]})
    params = {"columnHash": "h"}
    naming = get_naming_params()
    chartDict = {naming["chosenChart"]: naming["multitierColumnChart"]}

    # Stub heavy helpers with no-ops and add a simple annotation so font update applies
    monkeypatch.setattr(dm, "update_multitier_column_layout", lambda *a, **k: a[1])
    monkeypatch.setattr(dm, "get_user_message", lambda *a, **k: (a[0], "note"))

    def _add_title(fig, title, *_args, **_kwargs):
        fig.add_annotation(text=title)
        return fig

    monkeypatch.setattr(dm, "add_title_as_annotation", _add_title)
    monkeypatch.setattr(dm, "add_message_as_annotation", lambda f, *a, **k: f)

    # Act
    res = dm.adjust_multitier_column_plot(
        fig,
        df,
        key="k",
        metric="m",
        title="T",
        height=400,
        width=600,
        paramDict=params,
        chartDict=chartDict,
        plotWithPins=False,
    )

    # Assert: one annotation exists and font applied from config
    assert isinstance(res, go.Figure)
    assert res.layout.annotations and len(res.layout.annotations) >= 1
    ann = res.layout.annotations[0]
    # Font attributes are set on annotations via update_annotations
    assert ann.font.size > 0
    assert isinstance(ann.font.family, str) and len(ann.font.family) > 0


def test_add_absolute_value_bars_to_multitier_column_adds_traces_and_sanitizes_zero(monkeypatch) -> None:
    # Arrange
    dm = _import_draw_multitier_with_stubs(monkeypatch)
    naming = get_naming_params()
    df = pl.DataFrame(
        {
            naming["dateName"]: ["2023", "2024"],
            naming["pyName"]: [10.0, 20.0],
            naming["acName"]: [15.0, 0.0],  # zero should become null in result
        }
    )
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=1, cols=1)
    chartDict = {
        naming["chosenChart"]: naming["multitierColumnChart"],
        naming["colorChoice"]: naming["redToGreen"],
    }

    # Patch millify to a lightweight transformation that produces required columns
    def _millify_stub(lf, metric, _second, out_col, chart_dict):
        naming_local = get_naming_params()
        label_col = naming_local["labelName"]
        work_two = naming_local["workColumnTwo"]
        # ensure metric is numeric
        lf2 = (lf.lazy() if isinstance(lf, pl.DataFrame) else lf).with_columns(
            pl.col(metric).cast(pl.Float64).alias(metric)
        )
        if out_col:
            lf2 = lf2.with_columns(pl.col(metric).round(0).cast(pl.Utf8).alias(out_col))
        # also ensure both expected text columns exist
        if label_col not in [out_col]:
            lf2 = lf2.with_columns(pl.col(metric).round(0).cast(pl.Utf8).alias(label_col))
        if work_two not in [out_col]:
            lf2 = lf2.with_columns(pl.col(metric).round(0).cast(pl.Utf8).alias(work_two))
        return lf2, chart_dict

    monkeypatch.setattr(dm, "millify_dataframe", _millify_stub)

    # Act
    fig, out_df, _ = dm.add_absolute_value_bars_to_multitier_column(
        fig,
        df,
        metric="m",
        paramDict={},
        offset=0,
        constant=2,
        colorSequenceArray=["#111111", "#222222"],
        lineWidth=1,
        row=1,
        col=1,
        chartDict=chartDict,
    )

    # Assert: two bar traces (PY and AC) and AC zero -> null
    names = {tr.name for tr in fig.data}
    assert {naming["pyName"], naming["acName"]}.issubset(names)
    ac_values = out_df[naming["acName"]].to_list()
    assert ac_values[-1] is None


def test_add_absolute_value_bars_to_multitier_column_no_metrics_no_traces(monkeypatch) -> None:
    # Arrange: only dates column present
    dm = _import_draw_multitier_with_stubs(monkeypatch)
    naming = get_naming_params()
    df = pl.DataFrame({naming["dateName"]: ["2023"]})
    fig = go.Figure()
    chartDict = {
        naming["chosenChart"]: naming["multitierColumnChart"],
        naming["colorChoice"]: naming["redToGreen"],
    }

    # Use same lightweight millify stub to avoid heavy dependencies
    def _millify_stub(lf, metric, _second, out_col, chart_dict):
        return (lf.lazy() if isinstance(lf, pl.DataFrame) else lf), chart_dict

    monkeypatch.setattr(dm, "millify_dataframe", _millify_stub)

    # Act
    fig, out_df, _ = dm.add_absolute_value_bars_to_multitier_column(
        fig,
        df,
        metric="m",
        paramDict={},
        offset=0,
        constant=1,
        colorSequenceArray=["#111111", "#222222"],
        lineWidth=1,
        row=1,
        col=1,
        chartDict=chartDict,
    )

    # Assert: no traces added; label/work columns created lazily are harmless
    assert len(fig.data) == 0
    assert naming["dateName"] in out_df.columns
