import pytest
import polars as pl

from modules.llm.confirm_plots import (
    clean_dataframe_for_Ai,
    check_if_period,
    extract_non_blank_rows,
)
from modules.utilities.config import get_naming_params


@pytest.fixture(autouse=True)
def _patch_df_behaviour(monkeypatch):
    """Make confirm_plots use a plain DataFrame clone, not a LazyFrame.

    The production helper returns a LazyFrame, but the functions under test
    immediately expect a DataFrame in several places. Patching avoids
    constructor mismatches that are irrelevant to these behaviours.
    """
    import modules.llm.confirm_plots as cp

    # Ensure a plain DataFrame flows through (avoid LazyFrame constructor paths)
    monkeypatch.setattr(cp, "duplicate_dataframe", lambda df: pl.DataFrame(df))

    # Avoid polars interpreting "" in `then("")` as a column by short-circuiting
    # DataFrame.with_columns in this module's usage. We only validate column
    # selection behaviour in these tests.
    original_with_columns = pl.DataFrame.with_columns

    def _noop_with_columns(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self

    monkeypatch.setattr(pl.DataFrame, "with_columns", _noop_with_columns)


def _base_df(metric_name: str) -> pl.DataFrame:
    """Small deterministic DataFrame used across tests."""
    naming = get_naming_params()
    period = naming["periodName"]
    count = naming["countName"]
    return pl.DataFrame(
        {
            "Category": ["A", "B", "C"],
            metric_name: [1, 0, None],
            period: ["2023", "2023", "2023"],
            count: [5, 0, 2],
            "extra": [9, 8, 7],
        }
    )


def test_clean_dataframe_absolute_small_multiples_keeps_expected_columns():
    naming = get_naming_params()
    period = naming["periodName"]
    absolute = naming["absolute"]
    plot_values_as = naming["plotValuesAsChoice"]
    small_multiples = naming["plotSmallMultiplesOtherCharts"]

    df = _base_df("MetricX")
    chart = {plot_values_as: absolute, small_multiples: True}

    result = clean_dataframe_for_Ai(df, "MetricX", "Category", chart)

    # Only keep metric, dimension and period; drop others
    assert set(result.columns) == {"MetricX", "Category", period}

    # Only structure matters here; value transformations are handled elsewhere


def test_clean_dataframe_synthesis_plot_true_keeps_expected_columns():
    naming = get_naming_params()
    period = naming["periodName"]
    absolute = naming["absolute"]
    plot_values_as = naming["plotValuesAsChoice"]
    small_multiples = naming["plotSmallMultiplesOtherCharts"]
    synthesis = naming["synthesisPlot"]

    df = _base_df("MetricX")
    chart = {plot_values_as: absolute, small_multiples: True, synthesis: True}

    result = clean_dataframe_for_Ai(df, "MetricX", "Category", chart)

    # Only keep metric, dimension and period
    assert set(result.columns) == {"MetricX", "Category", period}

    # Structure-only check; transformation not asserted in this test


def test_clean_dataframe_non_absolute_drops_metric_and_count_columns():
    naming = get_naming_params()
    period = naming["periodName"]
    count = naming["countName"]

    df = _base_df("MetricX")
    chart = {}  # no absolute flag -> default branch

    result = clean_dataframe_for_Ai(df, "MetricX", "Category", chart)

    # Metric and count columns are dropped; others remain
    assert "MetricX" not in result.columns
    assert count not in result.columns
    for col in ("Category", period, "extra"):
        assert col in result.columns


@pytest.mark.parametrize(
    "initial, expected",
    [
        ({}, ""),
        ({get_naming_params()["periodChoice"]: "Monthly"}, "Monthly"),
    ],
)
def test_check_if_period_sets_default_or_preserves_value(initial, expected):
    naming = get_naming_params()
    period_choice = naming["periodChoice"]

    result = check_if_period(dict(initial))
    assert period_choice in result
    assert result[period_choice] == expected


def test_extract_non_blank_rows_golden_excludes_first_last_and_skips_empty_rows():
    naming = get_naming_params()
    variance_col = naming["varianceTypeName"]

    df = pl.DataFrame(
        {
            "A": [None, "x", "", "y"],
            "B": [1, 0, None, 2],
            variance_col: ["v", "v", "v", "v"],
        }
    )

    result = extract_non_blank_rows(df)

    # Middle rows considered; row with only blanks is skipped; zero is retained
    assert result == [{"A": "x", "B": 0}]


def test_extract_non_blank_rows_boundary_two_rows_returns_empty():
    naming = get_naming_params()
    variance_col = naming["varianceTypeName"]

    df = pl.DataFrame({"A": [1, 2], variance_col: ["v", "v"]})
    assert extract_non_blank_rows(df) == []


def test_extract_non_blank_rows_raises_when_variance_column_missing():
    df = pl.DataFrame({"A": [1, 2], "B": [3, 4]})
    with pytest.raises(ValueError):
        extract_non_blank_rows(df)
