from __future__ import annotations

import polars as pl
from polars.testing import assert_frame_equal
from plotly.subplots import make_subplots

from modules.charting.draw_pareto import (
    add_annotations_to_pareto,
    adjust_negative_metrics_lazy,
    get_data_for_pareto_prompt,
)
from modules.utilities.config import get_naming_params


def _basic_chart_dict():
    """Minimal chartDict seeded with required keys from naming params."""
    naming = get_naming_params()
    return {
        naming["plotCommentText"]: [],
        naming["plotConcentrationText"]: "",
        naming["countColumn"]: "item",
        naming["showRank"]: True,
    }


def test_get_data_for_pareto_prompt_targets_path_appends_comment_and_percent_array():
    # Arrange: minimal frame with rank, class and ratio columns
    naming = get_naming_params()
    count_rank_col = naming["countRank"]
    class_col = naming["className"]
    ratio_col = "ratio"

    # Choose ratios close to 0.80, 0.95 and 1.0
    df = pl.DataFrame(
        {
            count_rank_col: [1, 3, 5, 2, 4],
            class_col: ["A", "B", "C", "D", "E"],
            ratio_col: [0.81, 0.96, 1.00, 0.50, 0.90],
        }
    )

    chart_dict = _basic_chart_dict()

    # Act
    message_array, closest_rank, closest_idx, percent_array, out_chart = (
        get_data_for_pareto_prompt(
            df,
            metric="Sales",
            ratioName=ratio_col,
            classArray=["x", "y", "z"],  # len != 4 triggers target mode
            closestRankArray=[],
            closestIndexArray=[],
            col=1,
            chartDict=chart_dict,
        )
    )

    # Assert: three messages, fixed percent targets and one comment appended
    assert len(message_array) == 3
    assert percent_array == [0.80, 0.95, 1]
    assert len(out_chart[naming["plotCommentText"]]) == 1
    comment = out_chart[naming["plotCommentText"]][0]
    # The composed prompt mentions all three computed percents
    for p in [81, 96, 100]:
        assert f"{p}%" in comment
    # Concentration string set
    assert isinstance(out_chart[naming["plotConcentrationText"]], str) and out_chart[
        naming["plotConcentrationText"]
    ]


def test_get_data_for_pareto_prompt_class_path_returns_four_entries_and_negative_note():
    # Arrange
    naming = get_naming_params()
    count_rank_col = naming["countRank"]
    class_col = naming["className"]
    ratio_col = "ratio"

    # One row per class; order of rows is irrelevant for selection
    df = pl.DataFrame(
        {
            count_rank_col: [1, 2, 3, 4],
            class_col: ["A", "B", "C", "D"],
            ratio_col: [0.10, 0.80, 0.95, 1.00],
        }
    )
    chart_dict = _basic_chart_dict()

    # Act
    message_array, closest_rank, closest_idx, percent_array, out_chart = (
        get_data_for_pareto_prompt(
            df,
            metric="Sales",
            ratioName=ratio_col,
            classArray=["A", "B", "C", "D"],  # len == 4 triggers class mode
            closestRankArray=[],
            closestIndexArray=[],
            col=1,
            chartDict=chart_dict,
        )
    )

    # Assert: four messages and percent array mirrors the selected class ratios
    assert len(message_array) == 4
    # In class mode, percent array equals the collected ratios
    assert percent_array == [1.00, 0.95, 0.80, 0.10]
    # Comment includes the negative note clause
    assert any("since some" in s for s in out_chart[naming["plotCommentText"]])


def test_add_annotations_to_pareto_respects_showrank_false_and_adds_three_shapes():
    # Arrange
    naming = get_naming_params()
    chart_dict = {naming["showRank"]: False}
    fig = make_subplots(rows=1, cols=1)
    closest_rank = [10, 20, 30]
    closest_idx = [1, 2, 3]
    percent_array = [0.80, 0.95, 1.00]
    message_array = ["a", "b", "c"]

    # Act
    fig = add_annotations_to_pareto(
        fig,
        closest_rank,
        closest_idx,
        message_array,
        percent_array,
        classArray=["A", "B", "C"],
        col=1,
        chartDict=chart_dict,
    )

    # Assert: three shapes/annotations added and y0 follows closestIndexArray
    assert len(fig.layout.shapes) == 3
    assert [s.y0 for s in fig.layout.shapes] == [1, 2, 3]
    assert len(fig.layout.annotations) == 3
    # x equals percent - offset (0.02)
    xs = [ann.x for ann in fig.layout.annotations]
    assert xs[0] == percent_array[0] - 0.02


def test_add_annotations_to_pareto_adds_fourth_line_when_provided():
    # Arrange
    naming = get_naming_params()
    chart_dict = {naming["showRank"]: True}
    fig = make_subplots(rows=1, cols=1)

    closest_rank = [1, 2, 3, 4]
    closest_idx = [10, 20, 30, 40]
    percent_array = [0.1, 0.2, 0.3, 0.4]
    message_array = ["a", "b", "c", "d"]

    # Act
    fig = add_annotations_to_pareto(
        fig,
        closest_rank,
        closest_idx,
        message_array,
        percent_array,
        classArray=["A", "B", "C", "D"],
        col=1,
        chartDict=chart_dict,
    )

    # Assert: the 4th line is added
    assert len(fig.layout.shapes) == 4
    assert fig.layout.shapes[3].y0 == 4
    assert fig.layout.shapes[3].x1 == 0.4
    assert len(fig.layout.annotations) == 4


def test_adjust_negative_metrics_lazy_sign_rules_and_drop_temp_column():
    # Arrange
    df = pl.DataFrame(
        {
            "className": ["Other", "Other", "Loss", "Negative"],
            "m_value": [1.0, -1.0, -1.0, -1.0],  # metric+hyphen+value
            "m": [-10.0, 10.0, 10.0, -5.0],  # metric
            "r": [0.2, 0.3, 0.4, 0.5],  # ratio_name
        }
    ).lazy()

    # Act
    out = adjust_negative_metrics_lazy(
        df,
        metric="m",
        ratio_name="r",
        class_name="className",
        hyphen_name="_",
        value_name="value",
        opposite_sign="opp",
        loss_class_name="Loss",
        negative_class_name="Negative",
    ).collect()

    # Assert: column "opp" dropped and expected signs applied deterministically
    assert "opp" not in out.columns
    # Row-wise expected values derived from the function's rules
    expected = pl.DataFrame(
        {
            "className": ["Other", "Other", "Loss", "Negative"],
            "m_value": [1.0, -1.0, -1.0, -1.0],
            "m": [10.0, -10.0, -10.0, -5.0],
            "r": [0.2, 0.3, -0.4, 0.5],
        }
    )
    # Sort rows consistently for comparison
    assert_frame_equal(out.sort("className"), expected.sort("className"))
