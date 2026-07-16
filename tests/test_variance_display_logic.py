from __future__ import annotations

import pytest
import polars as pl
from polars.testing import assert_series_equal

import src.variance_display_logic as vdl


def _minimal_naming(overrides: dict | None = None) -> dict:
    base = {
        # used by drop_columns_not_in_output
        "drilldownKey": "drill",
        "randomKey": "rand",
        "numberOfNodes": "nodes",
        "uniqueValuesInCombination": "uniq",
        "normalizedStem": "norm",
        # used by build_plotly_table_figure
        "separatorString": "|",
        "plotlyTable": "table",
        "varianceTypeName": "Variance Type",
        "emojiNumberDict": "emoji",
        "rowNumber": "Row #",
        "variancePercentChangeName": "Variance %",
        "runningTotalName": "Running Total",
        "pricePerUnitNetDiscountName": "Price/Unit Net",
        "pricePerVolumeNetDiscountName": "Price/Volume Net",
        "categoryWeightedDistributionName": "Cat Weight",
        "totalDistributionPointsName": "Total Dist",
        "checkoutsName": "Checkouts",
        "visitsName": "Visits",
        "costPerUnitName": "Cost/Unit",
        "cogsPerUnitName": "COGS/Unit",
        "cogsPerVolumeName": "COGS/Volume",
        "indirectCostsName": "Indirect",
        "netMarginName": "Net Margin",
    }
    return {**base, **(overrides or {})}


def _minimal_config(overrides: dict | None = None) -> dict:
    base = {
        "periodsArray": ["t0", "t1"],
        "emoji": {1: "1️⃣", 2: "2️⃣", 3: "3️⃣"},
        "configPlotlyDict": {"table": {"dummy": True}},
    }
    return {**base, **(overrides or {})}


def test_drop_columns_not_in_output_drops_helpers_empty_and_fills(monkeypatch):
    # Arrange: patch naming and find_columns_by_stem
    from modules.utilities.helpers import find_columns_by_stem as real_find

    monkeypatch.setattr(vdl, "get_naming_params", lambda: _minimal_naming())
    monkeypatch.setattr(vdl, "find_columns_by_stem", real_find, raising=False)

    df = pl.DataFrame(
        {
            "keep1": ["x", None],
            "text_null": [None, "y"],
            "norm_metric": [None, None],  # matches normalizedStem and should drop
            "drill": ["h", "h"],
            "rand": [None, None],
            "nodes": [None, None],
            "uniq": [None, None],
            "index": [1, 2],
        }
    )

    # Act
    out = vdl.drop_columns_not_in_output(df)

    # Assert: helper + normalized + all-null columns are gone; nulls filled with ""
    assert set(out.columns) == {"keep1", "text_null"}
    assert out.height == 2
    assert_series_equal(out["keep1"], pl.Series("keep1", ["x", ""]))
    assert_series_equal(out["text_null"], pl.Series("text_null", ["", "y"]))


def test_drop_columns_not_in_output_as_lazy_returns_lazyframe(monkeypatch):
    from modules.utilities.helpers import find_columns_by_stem as real_find

    monkeypatch.setattr(vdl, "get_naming_params", lambda: _minimal_naming())
    monkeypatch.setattr(vdl, "find_columns_by_stem", real_find, raising=False)

    df = pl.DataFrame({"keep": ["a"], "norm_x": [None], "drill": [None]})

    out = vdl.drop_columns_not_in_output(df, as_lazy=True)
    assert isinstance(out, pl.LazyFrame)
    collected = out.collect()
    assert set(collected.columns) == {"keep"}
    assert collected["keep"][0] == "a"


def test_prepare_result_dataset_filters_index_and_respects_as_lazy(monkeypatch):
    # Arrange minimal stubs to avoid touching heavy pipeline pieces
    monkeypatch.setattr(vdl, "get_naming_params", lambda: _minimal_naming())
    from modules.utilities.helpers import find_columns_by_stem as real_find

    monkeypatch.setattr(vdl, "find_columns_by_stem", real_find, raising=False)
    monkeypatch.setattr(vdl, "replace_all_with_blanc_or_nan", lambda df, _v, as_lazy=True: df)
    monkeypatch.setattr(vdl, "recalculate_price", lambda df, p: (df, {**p, "priced": True}))
    monkeypatch.setattr(vdl, "add_running_total", lambda df: df)
    monkeypatch.setattr(vdl, "set_order_for_output", lambda df, idx, p: (df, []))
    monkeypatch.setattr(vdl, "round_other_columns", lambda df, ordered: (df, [], []))
    monkeypatch.setattr(vdl, "get_data_sample", lambda df, name, flag, p: {**p, "sampled": True})
    monkeypatch.setattr(vdl, "change_variance_tags_to_units", lambda df, chart: df)

    df = pl.DataFrame({"A": [1, 2], "B": [3, 4]})
    index_cols = ["A", "Z"]  # Z does not exist and should be filtered out
    param_dict = {"init": 1}
    chart_dict = {}

    # Act
    out_df, output_index, out_params, out_chart = vdl.prepare_result_dataset(
        df, index_cols, dict(param_dict), dict(chart_dict), run="r1", as_lazy=True
    )

    # Assert
    assert isinstance(out_df, pl.LazyFrame)
    assert output_index == ["A"]
    assert out_params["init"] == 1 and out_params["priced"] and out_params["sampled"]
    assert out_chart == chart_dict


def test_prepare_result_dataset_empty_df_keeps_all_index_cols(monkeypatch):
    # No pipeline should run; index cols are returned unchanged
    monkeypatch.setattr(vdl, "get_naming_params", lambda: _minimal_naming())
    df = pl.DataFrame({"A": pl.Series([], dtype=pl.Int64)})  # empty
    index_cols = ["A", "Z"]

    out_df, output_index, out_params, out_chart = vdl.prepare_result_dataset(
        df, index_cols, {}, {}, run="r0", as_lazy=False
    )

    assert isinstance(out_df, pl.DataFrame)
    assert output_index == index_cols  # unchanged when input is not a valid lazyframe
    assert out_params == {}
    assert out_chart == {}


def test_build_plotly_table_figure_minimal(monkeypatch):
    # Arrange: stub config, naming, color dict and millify to exercise core logic
    monkeypatch.setattr(vdl, "get_naming_params", lambda: _minimal_naming())
    monkeypatch.setattr(vdl, "get_config_params", lambda: _minimal_config())
    monkeypatch.setattr(
        vdl, "get_color_dictionary", lambda _chart: {
            "greyColor": "#888",
            "veryVeryLightGreyColor": "#eee",
            "whiteColor": "#fff",
            "blackColor": "#000",
        }
    )
    # millify should be a no-op that preserves the lazyframe
    monkeypatch.setattr(vdl, "millify_dataframe", lambda lf, *_args: (lf, None))

    df = pl.DataFrame(
        {
            "Category": ["A", "A", "B"],
            "Variance Type": ["X", "Y", "X"],
            "Value": [1, 2, 3],
        }
    )

    index_cols = ["Category", "Variance Type"]

    # Act
    fig, cfg = vdl.build_plotly_table_figure(df, index_cols, chart_dict={}, param_dict={})

    # Assert: figure structure and header values
    assert cfg == {"dummy": True}
    assert len(fig.data) == 1 and fig.data[0].type == "table"
    header_vals = list(fig.data[0]["header"]["values"])  # plotly stores as list-like
    # Row number + index columns must be present and bolded
    assert set(header_vals) == {"<b>Row #</b>", "<b>Category</b>", "<b>Variance Type</b>"}
    # Width follows number of columns * 100
    assert fig.layout.width == 3 * 100
    # Colors array shape matches [n_columns][n_rows]
    colors = fig.data[0]["cells"]["font"]["color"]
    assert isinstance(colors, (list, tuple)) and len(colors) == 3
    assert all(len(col) == 3 for col in colors)
