import polars as pl
import pytest

import modules.llm.chart_interpretation_prompts as chp
from modules.llm.chart_interpretation_prompts import (
    get_horizontal_waterfall_prompt,
    get_marimekko_prompt,
    get_multitier_bar_prompt,
)
from modules.utilities.config import get_naming_params
from modules.utilities.utils import get_schema_and_column_names


def _base_chart_dict():
    """Build a minimal, valid chartDict using project naming params."""
    n = get_naming_params()
    return {
        n["plotTitleText"]: "Test Title",
        n["metricsToPlot"]: ["Sales"],
        n["selectedPeriods"]: [n["pyName"], n["acName"]],
        n["toPlotPeriod"]: "FY 2024",
    }


def test_horizontal_waterfall_prompt_basic_includes_keys_and_returns_df():
    n = get_naming_params()
    df = pl.DataFrame({"v": [1, 2]})
    chart = _base_chart_dict()

    prompt, out_df = get_horizontal_waterfall_prompt(df, chart)

    # Prompt contains chart type and period tags (PY/AC)
    assert n["horizontalWaterfallChart"] in prompt
    assert "(PY)" in prompt and "(AC)" in prompt
    assert "Only provide fact-based" in prompt

    # DataFrame is returned (no schema changes required for this path)
    in_cols, _ = get_schema_and_column_names(df)
    out_cols, _ = get_schema_and_column_names(out_df)
    assert in_cols == out_cols




def test_multitier_bar_prompt_small_multiples_and_period_translation():
    n = get_naming_params()
    # Small multiples along Dimension (use branch without direct df["col"] access)
    df = pl.DataFrame({"Dimension": ["D1", "D2"], "A": [1, 2]})
    chart = _base_chart_dict() | {
        n["plotSmallMultiplesOtherCharts"]: True,
        n["selectDimensionsToPlot"]: ["Dimension", "Group"],
        # Force the alternate branch by setting xAxisDimension to 'None'
        n["xAxisDimension"]: n["nothingFilteredName"],
    }

    prompt, out_df = get_multitier_bar_prompt(df, chart)

    # Prompt mentions chart name, the small-multiples items, and translated periods
    assert n["multitierBarChart"] in prompt
    assert "D1" in prompt and "D2" in prompt
    # From traslate_ibcs_period_symbols
    assert "**Actual** (AC)" in prompt or "**Previous Year** (PY)" in prompt

    # Function returns a lazy frame (duplicate_dataframe + drop_columns)
    assert isinstance(out_df, pl.LazyFrame)


def test_horizontal_waterfall_missing_title_raises_keyerror():
    df = pl.DataFrame({"v": [1]})
    # Deliberately omit the title key
    n = get_naming_params()
    bad_chart = {
        n["metricsToPlot"]: ["Sales"],
        n["selectedPeriods"]: [n["pyName"], n["acName"]],
    }

    with pytest.raises(KeyError):
        get_horizontal_waterfall_prompt(df, bad_chart)


def test_marimekko_missing_title_raises_keyerror():
    n = get_naming_params()
    df = pl.DataFrame({"A": [1, 2], "B": [3, 4]})
    # Missing plotTitleText key should surface as a KeyError
    bad_chart = {
        n["singleMetric"]: "Sales",
        n["xAxisDimension"]: "Category",
        n["yAxisDimension"]: "Component",
        n["toPlotPeriod"]: "FY 2024",
    }

    with pytest.raises(KeyError):
        get_marimekko_prompt(df, bad_chart)
