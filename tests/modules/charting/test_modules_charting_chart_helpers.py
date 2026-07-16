from __future__ import annotations

import sys
import types

import polars as pl
import pytest
from polars.testing import assert_frame_equal

import importlib


class _DummyExpander:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def chart_helpers_module(monkeypatch):
    # Provide lightweight stubs for the LLM package to avoid importing heavy modules
    llm_pkg = types.ModuleType("modules.llm")
    llm_pkg.__path__ = []  # mark as package
    llm_confirm = types.ModuleType("modules.llm.confirm_plots")
    llm_confirm.get_comments_from_data = lambda *a, **k: None
    llm_confirm.get_comments_from_data_fragment = lambda *a, **k: None
    llm_confirm.get_comments_from_images = lambda *a, **k: None
    sys.modules["modules.llm"] = llm_pkg
    sys.modules["modules.llm.confirm_plots"] = llm_confirm
    # Import the target module after stubbing
    return importlib.import_module("modules.charting.chart_helpers")


def test_ensure_lazyframe_from_dataframe_returns_lazyframe(monkeypatch):
    ch = chart_helpers_module(monkeypatch)
    # Arrange
    df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})

    # Act
    lf = ch.ensure_lazyframe(df)

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    assert_frame_equal(lf.collect(), df)


def test_ensure_lazyframe_idempotent_for_lazyframe(monkeypatch):
    ch = chart_helpers_module(monkeypatch)
    # Arrange
    df = pl.DataFrame({"x": [1]})
    lf = df.lazy()

    # Act
    out = ch.ensure_lazyframe(lf)

    # Assert
    assert out is lf  # returns the same lazy object


def test_ensure_lazyframe_invalid_type_raises_typeerror(monkeypatch):
    ch = chart_helpers_module(monkeypatch)
    # Arrange
    bad_obj = [{"a": 1}]

    # Act / Assert
    with pytest.raises(TypeError):
        ch.ensure_lazyframe(bad_obj)  # type: ignore[arg-type]


def test_download_chart_dataframe_converts_and_triggers_download(monkeypatch):
    # Arrange
    ch = chart_helpers_module(monkeypatch)
    from modules.utilities.config import get_naming_params

    naming = get_naming_params()
    row_key = naming["rowToPlotName"]
    entire = naming["entireDatasetName"]
    prep_key = naming["prepareFileForDownload"]

    chart_dict = {row_key: 7, prep_key: True}
    df_charts = pl.DataFrame({"v": [10]})

    calls: dict[str, tuple] = {}

    def fake_convert_df(df):
        assert isinstance(df, pl.DataFrame)
        return "MOCK_CSV_PAYLOAD"

    def fake_download_text_data(csv, label, file_name):
        calls["args"] = (csv, label, file_name)

    # Patch UI caption to a no-op, and helper functions/vars
    monkeypatch.setattr(ch, "convert_df", fake_convert_df)
    monkeypatch.setattr(ch, "download_text_data", fake_download_text_data, raising=False)
    monkeypatch.setattr(ch, "fileName", "out.csv", raising=False)
    monkeypatch.setattr(ch.ui, "caption", lambda *_a, **_k: None)

    # Act
    ch.download_chart_dataframe(chart_dict, df_charts, _DummyExpander())

    # Assert
    # Row label is rewritten and download is triggered with expected args
    assert chart_dict[row_key] == "report row #7"
    assert calls.get("args") == ("MOCK_CSV_PAYLOAD", ("Press to Download ",), "out.csv")


def test_download_chart_dataframe_noop_for_entire_dataset(monkeypatch):
    # Arrange
    ch = chart_helpers_module(monkeypatch)
    from modules.utilities.config import get_naming_params

    naming = get_naming_params()
    row_key = naming["rowToPlotName"]
    entire = naming["entireDatasetName"]
    prep_key = naming["prepareFileForDownload"]

    chart_dict = {row_key: entire, prep_key: True}
    df_charts = pl.DataFrame({"v": [10]})

    called = {"download": False, "convert": False}

    monkeypatch.setattr(
        ch, "convert_df", lambda *_a, **_k: called.__setitem__("convert", True),
    )
    monkeypatch.setattr(
        ch,
        "download_text_data",
        lambda *_a, **_k: called.__setitem__("download", True),
        raising=False,
    )
    monkeypatch.setattr(ch.ui, "caption", lambda *_a, **_k: None)

    # Act
    ch.download_chart_dataframe(chart_dict, df_charts, _DummyExpander())

    # Assert: nothing changes and no download occurs
    assert chart_dict[row_key] == entire
    assert called["convert"] is False
    assert called["download"] is False


def test_get_highlighted_items_stacked_pareto_sets_unique_items_and_calls_widget(
    monkeypatch,
):
    # Arrange: choose a path that avoids heavy data ops (stacked pareto)
    ch = chart_helpers_module(monkeypatch)
    from modules.utilities.config import get_naming_params

    naming = get_naming_params()
    stacked_pareto = naming["stackedParetoChart"]
    agg_key = naming["aggregateUniquesByDimension"]
    small_multiples_col_key = naming["smallMultiplesColumn"]
    number_of_top_key = naming["numberOfTop"]
    highlighted_key = naming["highlightedDimension"]
    col_hash_key = naming["columnHash"]

    df_all = pl.DataFrame({"segment": ["A"]}).lazy()
    df_periods = pl.DataFrame({"segment": ["A"]}).lazy()
    value_cols: list[str] = []
    chart_dict: dict = {
        agg_key: True,
        small_multiples_col_key: "segment",
        "X": {number_of_top_key: 5},
    }
    automate_dict: dict = {}
    param_dict: dict = {col_hash_key: "colhash"}
    expected_unique_items = ["A"]

    # Stub the widget module imported inside the function
    suw = types.ModuleType("modules.layout.set_up_widgets")
    suw.uniqueItems = None  # will be set by the function under test

    def fake_widget(cd, _auto, _hash, _params):
        # Simulate widget enriching the dict
        cd[highlighted_key] = "picked"
        return cd

    suw.show_highlighted_items_widget = fake_widget  # type: ignore[attr-defined]
    monkeypatch.setattr(
        ch,
        "show_only_largest",
        lambda *_args, **_kwargs: (
            pl.DataFrame({"segment": ["A"]}),
            expected_unique_items,
            "other",
            value_cols,
        ),
    )
    # Ensure the import path resolves to our stub
    pkg = sys.modules.get("modules.layout")
    if pkg is None:
        pkg = types.ModuleType("modules.layout")
        sys.modules["modules.layout"] = pkg
    setattr(pkg, "set_up_widgets", suw)
    sys.modules["modules.layout.set_up_widgets"] = suw

    # Act
    out = ch.get_highlighted_items(
        df_all, df_periods, value_cols, stacked_pareto, chart_dict, automate_dict, param_dict
    )

    # Assert: the widget was called and saw the expected unique item order
    assert suw.uniqueItems == expected_unique_items
    assert out is chart_dict
    assert out[highlighted_key] == "picked"


def test_get_highlighted_items_dimensions_missing_returns_unchanged(monkeypatch):
    # Arrange: choose a chart that requires explicit dimensions but provide none
    ch = chart_helpers_module(monkeypatch)
    from modules.utilities.config import get_naming_params

    naming = get_naming_params()
    slope = naming["slopeChart"]

    df_all = pl.DataFrame({"x": [1]})
    df_periods = pl.DataFrame({"x": [1]})
    value_cols: list[str] = []
    chart_dict: dict = {}
    automate_dict: dict = {}
    param_dict: dict = {naming["columnHash"]: "colhash"}

    # Act
    out = ch.get_highlighted_items(
        df_all, df_periods, value_cols, slope, chart_dict, automate_dict, param_dict
    )

    # Assert: no changes when required dimensions are missing
    assert out == chart_dict
