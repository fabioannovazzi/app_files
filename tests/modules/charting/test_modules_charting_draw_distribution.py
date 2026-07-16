from __future__ import annotations

import sys
import types

import pytest
import polars as pl
import plotly.graph_objects as go

from polars.exceptions import ColumnNotFoundError

# Provide lightweight stubs to avoid importing the full LLM stack during tests
stub_llm = types.ModuleType("modules.llm")
stub_confirm = types.ModuleType("modules.llm.confirm_plots")
setattr(stub_confirm, "get_comments_from_data", lambda *a, **k: {})
setattr(stub_confirm, "get_comments_from_data_fragment", lambda *a, **k: {})
setattr(stub_confirm, "get_comments_from_images", lambda *a, **k: {})
sys.modules.setdefault("modules.llm", stub_llm)
sys.modules.setdefault("modules.llm.confirm_plots", stub_confirm)

from modules.charting.draw_distribution import (
    order_and_categorize_period_column,
    order_and_categorize_period_column_polars,
    draw_histogram_chart,
)


@pytest.fixture(autouse=True)
def minimal_params(monkeypatch):
    """Stub naming/config and color helpers with minimal values for tests."""

    # Minimal naming/config dictionaries used by the targeted functions
    naming = {
        "periodName": "Period",
        "fontSizeText": "fontSizeText",
        "fontChoice": "fontChoice",
        "selectedPeriods": "selectedPeriods",
        "cumulativeHistogram": "cumulativeHistogram",
        "logXAxis": "logXAxis",
        "metConditionValue": True,
        "notMetConditionValue": False,
        # used when colChoice=True in draw_histogram_chart via place_other_rank_at_end
        "workColumn": "__work1__",
        "workColumnTwo": "__work2__",
        "nothingFilteredName": "Nothing",
    }
    config = {"fontSizeText": 12, "fontChoice": "Arial"}

    # Patch config accessors (both at source module and where imported)
    from modules.utilities import config as cfg
    import modules.charting.draw_distribution as dd

    monkeypatch.setattr(cfg, "get_naming_params", lambda: naming, raising=True)
    monkeypatch.setattr(cfg, "get_config_params", lambda: config, raising=True)
    monkeypatch.setattr(dd, "get_naming_params", lambda: naming, raising=True)
    monkeypatch.setattr(dd, "get_config_params", lambda: config, raising=True)

    # Patch color helpers and plan detector referenced inside draw functions
    monkeypatch.setattr(dd, "get_color_dictionary", lambda _d: {
        "blackColor": "#000000",
        "veryLightGreyColor": "#DDDDDD",
        "lightGreyColor": "#AAAAAA",
        "whiteColor": "#FFFFFF",
    })
    monkeypatch.setattr(dd, "get_color_sequence", lambda *_a, **_k: (["#000000", "#AAAAAA"], 0))
    monkeypatch.setattr(dd, "check_if_plan_or_py", lambda _arr: (False, "AC"))


def test_order_and_categorize_period_column_sorts_and_sets_categorical(monkeypatch):
    # Arrange
    df = pl.DataFrame({"Period": ["B", "A"], "Value": [1, 2]})
    order = ["A", "B"]

    # Act
    lf = order_and_categorize_period_column(df, order)
    out = lf.select(pl.all()).collect()

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    assert out.get_column("Period").dtype == pl.Categorical
    assert out.get_column("Period").to_list() == ["A", "B"]
    assert out.get_column("Value").to_list() == [2, 1]


def test_order_and_categorize_period_column_polars_accepts_lazy(monkeypatch):
    # Arrange
    df = pl.DataFrame({"Period": ["B", "A"], "Value": [1, 2]}).lazy()
    order = ["A", "B"]

    # Act
    lf = order_and_categorize_period_column_polars(df, order)
    out = lf.select(pl.all()).collect()

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    assert out.get_column("Period").dtype == pl.Categorical
    assert out.get_column("Period").to_list() == ["A", "B"]


def test_order_and_categorize_period_column_missing_period_raises():
    # Arrange
    df = pl.DataFrame({"Other": ["A", "B"]})
    order = ["A", "B"]

    # Act
    lf = order_and_categorize_period_column(df, order)

    # Assert: materializing should fail due to missing Period column
    with pytest.raises(ColumnNotFoundError):
        lf.collect()


def test_draw_histogram_chart_basic_no_facets():
    # Arrange
    df = pl.DataFrame(
        {
            "Period": ["AC", "AC", "PY", "PY"],
            "Value": [1.0, 2.0, 3.0, 4.0],
        }
    )
    chart_dict = {
        "selectedPeriods": ["AC", "PY"],
        "cumulativeHistogram": False,
        "logXAxis": False,
    }

    # Act
    fig, n_items, cleaned_order, out_lf = draw_histogram_chart(
        df, "Region", "Value", False, {}, chart_dict, []
    )

    # Assert
    assert isinstance(fig, go.Figure)
    assert n_items == 1
    assert cleaned_order == ["AC", "PY"]
    assert isinstance(out_lf, pl.LazyFrame)
    # 2 traces expected (one per period value)
    assert len(fig.data) == 2


def test_draw_histogram_chart_facets_counts_unique_dimension():
    # Arrange
    df = pl.DataFrame(
        {
            "Period": ["AC", "AC", "PY", "PY"],
            "Value": [1.0, 2.0, 3.0, 4.0],
            "Region": ["East", "West", "East", "West"],
        }
    )
    chart_dict = {
        "selectedPeriods": ["AC", "PY"],
        "cumulativeHistogram": False,
        "logXAxis": False,
    }

    # Act
    fig, n_items, cleaned_order, out_lf = draw_histogram_chart(
        df, "Region", "Value", True, {}, chart_dict, ["East", "West"]
    )

    # Assert
    assert isinstance(fig, go.Figure)
    # numberOfItemsInCol equals unique count of Region
    assert n_items == 2
    assert cleaned_order == ["AC", "PY"]
    assert isinstance(out_lf, pl.LazyFrame)


def test_draw_histogram_chart_missing_metric_raises():
    # Arrange: metric column absent
    df = pl.DataFrame({"Period": ["AC", "PY"]})
    chart_dict = {
        "selectedPeriods": ["AC", "PY"],
        "cumulativeHistogram": False,
        "logXAxis": False,
    }

    # Act / Assert
    with pytest.raises(ColumnNotFoundError):
        draw_histogram_chart(df, "Region", "Value", False, {}, chart_dict, [])
