import sys
import types
import pytest
import polars as pl
import plotly.graph_objects as go

from modules.utilities.config import get_naming_params


@pytest.fixture()
def dv(monkeypatch):
    """Import ``modules.charting.draw_venn_upset`` with LLm submodules stubbed."""
    # Provide minimal stubs to avoid importing heavy or broken LLM modules
    llm_pkg = types.ModuleType("modules.llm")
    # Mark as a package so submodule imports succeed
    setattr(llm_pkg, "__path__", [])
    sys.modules.setdefault("modules.llm", llm_pkg)

    confirm_plots = types.ModuleType("modules.llm.confirm_plots")
    confirm_plots.get_comments_from_images = lambda *a, **k: {}
    confirm_plots.get_comments_from_data = lambda *a, **k: {}
    confirm_plots.get_comments_from_data_fragment = lambda *a, **k: {}
    sys.modules.setdefault("modules.llm.confirm_plots", confirm_plots)

    llm_api = types.ModuleType("modules.llm.llm_api")
    llm_api.remove_duplicate_charts_in_dictionary = lambda *a, **k: None
    sys.modules.setdefault("modules.llm.llm_api", llm_api)

    interpret_plots = types.ModuleType("modules.llm.interpret_plots")
    interpret_plots.explain_metrics_for_barmekko_prompt = lambda *a, **k: ""
    interpret_plots.explain_metrics_for_stacked_column_prompt = lambda *a, **k: ""
    sys.modules.setdefault("modules.llm.interpret_plots", interpret_plots)

    import importlib

    return importlib.import_module("modules.charting.draw_venn_upset")


@pytest.mark.parametrize(
    "rows, expected",
    [
        (101, [2, 1, 1, 1]),  # > 100 rows
        (51, [1.5, 1, 1, 1]),  # > 50 rows
        (50, [1, 1, 1, 1]),  # boundary: <= 50 rows
    ],
)
def test_set_col_array_for_upset_thresholds(dv, monkeypatch, rows, expected):
    # Arrange
    captured = {}

    def fake_columns(widths):
        captured["widths"] = widths
        return [f"col{i}" for i in range(len(widths))]

    monkeypatch.setattr(dv.ui, "columns", fake_columns)

    df = pl.DataFrame({"a": list(range(rows))})
    chart_dict: dict = {}

    # Act
    cols = dv.set_col_array_for_upset(df, chart_dict)

    # Assert
    assert captured["widths"] == expected
    assert isinstance(cols, list) and len(cols) == 4


def test_set_col_array_for_upset_small_multiples_overrides(dv, monkeypatch):
    # Arrange
    captured = {}

    def fake_columns(widths):
        captured["widths"] = widths
        return [f"col{i}" for i in range(len(widths))]

    monkeypatch.setattr(dv.ui, "columns", fake_columns)

    key = get_naming_params()["plotSmallMultiplesOtherCharts"]
    df = pl.DataFrame({"a": list(range(250))})  # large, but flag should override
    chart_dict = {key: True}

    # Act
    cols = dv.set_col_array_for_upset(df, chart_dict)

    # Assert
    assert captured["widths"] == [1, 1, 1, 1]
    assert isinstance(cols, list) and len(cols) == 4


def test_prepare_upset_chart_data_happy_path(dv, monkeypatch):
    # Arrange
    calls: dict = {}
    naming = get_naming_params()
    y_key = naming["yAxisDimension"]
    x_key = naming["xAxisDimension"]
    period_name = naming["periodName"]

    df_in = pl.DataFrame({
        "XCOL": ["x1"],
        "YCOL": ["y1"],
        period_name: ["2024"],
        "val": [1],
    })

    def fake_show_only_largest(df, x_col, y_col, period_nm, value_cols, chart_dict, param_dict, marker):
        calls["show_only_largest"] = (x_col, y_col, period_nm, tuple(value_cols), marker)
        return df, ["A", "B"], "agg", "vals"

    def fake_check_if_periods_in_columns(df, period):
        return df, "P-OUT"

    def fake_prepare_data_for_upset_plot(df, x_col, y_col, period, unique_items):
        calls["prepare_data_for_upset_plot"] = (x_col, y_col, period, tuple(unique_items))
        return pl.DataFrame({"dummy": [1]})

    monkeypatch.setattr(dv, "show_only_largest", fake_show_only_largest)
    monkeypatch.setattr(dv, "check_if_periods_in_columns", fake_check_if_periods_in_columns)
    monkeypatch.setattr(dv, "prepare_data_for_upset_plot", fake_prepare_data_for_upset_plot)

    chart_dict = {y_key: "YCOL", x_key: "XCOL"}

    # Act
    df_out, df_new_lazy, x_col, y_col, period = dv.prepare_upset_chart_data(
        df_in, ["val"], chart_dict, {}, period_name
    )

    # Assert
    assert isinstance(df_new_lazy, pl.LazyFrame)
    assert x_col == "XCOL"
    assert y_col == "YCOL"
    assert period == "P-OUT"

    # Helper calls received correct arguments
    assert calls["show_only_largest"][0] == "XCOL"
    assert calls["show_only_largest"][1] == "YCOL"
    assert calls["show_only_largest"][2] == period_name
    assert calls["prepare_data_for_upset_plot"] == ("XCOL", "YCOL", "P-OUT", ("A", "B"))


def test_prepare_upset_chart_data_missing_keys_raises_keyerror(dv):
    # Arrange
    df_in = pl.DataFrame({"a": [1]})

    # Act / Assert: missing required chart keys -> KeyError
    with pytest.raises(KeyError):
        dv.prepare_upset_chart_data(df_in, ["v"], {}, {}, "Period")


def test_render_upset_chart_no_data(dv, monkeypatch):
    # Arrange: stub prepare to return empty lazy frame so draw is skipped
    calls = {"draw": 0}

    def fake_prepare(*_a, **_k):
        return pl.DataFrame({"a": []}), pl.DataFrame({"a": []}).lazy(), "X", "Y", "PER"

    def fake_draw(df, x_col, y_col, chart_dict):  # pragma: no cover - should not be called
        calls["draw"] += 1
        return go.Figure(data=[go.Bar()]), "metric"

    monkeypatch.setattr(dv, "prepare_upset_chart_data", fake_prepare)
    monkeypatch.setattr(dv, "draw_upset_chart", fake_draw)

    # Act
    fig, df, df_new, y_col, circle_metric, period = dv.render_upset_chart(
        pl.DataFrame({"a": []}), ["v"], {}, {}, "PER-IN"
    )

    # Assert
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0  # untouched default figure
    assert y_col == "Y"
    assert circle_metric == ""
    assert period == "PER"
    assert calls["draw"] == 0


def test_render_upset_chart_with_data(dv, monkeypatch):
    # Arrange: stub prepare to return non-empty lazy frame so draw is called
    def fake_prepare(*_a, **_k):
        return pl.DataFrame({"a": [1]}), pl.DataFrame({"a": [1]}).lazy(), "X", "Y", "PER"

    fig_expected = go.Figure(data=[go.Scatter()])

    def fake_draw(df, x_col, y_col, chart_dict):
        # Ensure parameters are passed through
        assert x_col == "X"
        assert y_col == "Y"
        return fig_expected, "CIRCLE"

    monkeypatch.setattr(dv, "prepare_upset_chart_data", fake_prepare)
    monkeypatch.setattr(dv, "draw_upset_chart", fake_draw)

    # Act
    fig, df, df_new, y_col, circle_metric, period = dv.render_upset_chart(
        pl.DataFrame({"a": [1]}), ["v"], {"any": "thing"}, {}, "PER-IN"
    )

    # Assert
    assert fig is fig_expected
    assert y_col == "Y"
    assert circle_metric == "CIRCLE"
    assert period == "PER"
