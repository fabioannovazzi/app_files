from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.data.multidimensional_charts_prep import (
    correct_other_rank_number_for_missing_items,
    ensure_polars_df,
    prepare_overlay_data_for_stacked_bar,
)
from modules.utilities.config import get_naming_params


def test_ensure_polars_df_handles_df_and_lazy():
    # Arrange
    df = pl.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})

    # Act
    same_df = ensure_polars_df(df)
    collected = ensure_polars_df(df.lazy())

    # Assert
    assert same_df is df  # DataFrame returned as-is
    assert_frame_equal(collected, df)


def test_ensure_polars_df_builds_from_sequence_and_rejects_invalid():
    # Arrange
    records = [{"x": 1}, {"x": 2}]

    # Act
    built = ensure_polars_df(records)

    # Assert (golden path)
    assert_frame_equal(built, pl.DataFrame(records))

    # Negative: unsupported object should raise a TypeError
    with pytest.raises(TypeError):
        ensure_polars_df(object())


@pytest.mark.parametrize(
    "label, expected",
    [
        ("Others rank >5", "Others rank >2"),  # rank too high -> corrected
        ("Others rank >2", "Others rank >2"),  # already correct -> unchanged
    ],
)
def test_correct_other_rank_number_for_missing_items(label: str, expected: str):
    # Arrange: first column is the label column by contract
    df = pl.DataFrame({
        "Label": ["A", label, "B"],
        "Value": [1, 2, 3],
    })

    # Act
    lf = correct_other_rank_number_for_missing_items(df, label)
    out = lf.collect()

    # Assert
    assert out.get_column("Label").to_list()[1] == expected


def test_prepare_overlay_data_for_stacked_bar_sets_overlay_for_total():
    # Arrange
    naming = get_naming_params()
    period_col = naming["periodName"]
    total_name = naming["totalName"]

    # Keep x_col != total_name and set the overlay metric to the literal total
    # column name so the internal rename({totalName: overlayMetric}) is a no-op.
    x_col = "Item"
    overlay_metric = total_name

    df = pl.DataFrame(
        {
            x_col: ["A", "B", "A", "Others rank >5"],
            period_col: ["2023", "2023", "2024", "2024"],
            overlay_metric: [10.0, 5.0, 11.0, 2.0],
        }
    )

    chart_dict = {
        naming["metricsToPlot"]: ["Sales", overlay_metric],
        naming["toPlotPeriod"]: "2024",
        naming["selectedPeriods"]: ["2023", "2024"],
        naming["yAxisDimension"]: x_col,
    }
    param_dict: dict = {}

    # Act
    out_dict = prepare_overlay_data_for_stacked_bar(
        df,
        df_counts := pl.DataFrame(),  # unused by the function
        total_name,
        x_col,
        "Others rank >5",
        [overlay_metric],
        chart_dict,
        param_dict,
    )

    # Assert: overlay entries are populated for the Total branch
    assert out_dict[naming["overlayChartMetric"]] == overlay_metric
    assert out_dict[naming["overlayChartDimension"]] == total_name

    overlay_df = out_dict[naming["overlayChartDf"]]
    assert isinstance(overlay_df, (pl.DataFrame, pl.LazyFrame))
    overlay_pl = overlay_df.collect() if isinstance(overlay_df, pl.LazyFrame) else overlay_df

    # Expected: two rows for the selected period, with label corrected
    expected = pl.DataFrame({x_col: ["A", "Others rank >1"], overlay_metric: [11.0, 2.0]}).sort(x_col)
    assert period_col not in overlay_pl.columns
    assert_frame_equal(overlay_pl.sort(x_col), expected)


def test_prepare_overlay_data_for_stacked_bar_non_total_adds_small_multiple_and_updates_dimension():
    # Arrange
    naming = get_naming_params()
    period_col = naming["periodName"]
    total_name = naming["totalName"]

    # Keep x_col != total_name and set overlay metric to total name to avoid renaming conflicts
    x_col = "Item"
    overlay_metric = total_name
    small_multiple_dim_value = "R1"
    column_name = "Region"

    df = pl.DataFrame(
        {
            x_col: ["A", "Others rank >5"],
            period_col: ["2024", "2024"],
            overlay_metric: [11.0, 2.0],
        }
    )

    chart_dict = {
        naming["metricsToPlot"]: ["Sales", overlay_metric],
        naming["toPlotPeriod"]: "2024",
        naming["selectedPeriods"]: ["2023", "2024"],
        naming["overlayChartDimension"]: total_name,  # simulate previous Total run
        naming["smallMultiplesDimension"]: small_multiple_dim_value,
    }
    param_dict: dict = {}

    # Act
    out_dict = prepare_overlay_data_for_stacked_bar(
        df,
        df_counts := pl.DataFrame(),
        column_name,  # not total
        x_col,
        "Others rank >5",
        [overlay_metric],
        chart_dict,
        param_dict,
    )

    # Assert: overlay dimension switches to the provided column and the column is added
    assert out_dict[naming["overlayChartDimension"]] == column_name
    overlay_df = out_dict[naming["overlayChartDf"]]
    overlay_pl = overlay_df.collect() if isinstance(overlay_df, pl.LazyFrame) else overlay_df
    # Invariants: new column added; period removed; expected values present
    assert column_name in overlay_pl.columns
    assert set(overlay_pl.get_column(column_name).to_list()) == {small_multiple_dim_value}
    assert period_col not in overlay_pl.columns
    # Expected content
    expected = (
        pl.DataFrame({x_col: ["A", "Others rank >1"], overlay_metric: [11.0, 2.0], column_name: [small_multiple_dim_value, small_multiple_dim_value]})
        .sort([x_col, column_name])
    )
    assert_frame_equal(overlay_pl.sort([x_col, column_name]), expected)
