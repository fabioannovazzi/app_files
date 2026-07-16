import math

import polars as pl
import plotly.graph_objects as go
import pytest
from plotly.subplots import make_subplots

from modules.charting.draw_bubble import (
    add_labels_and_values_to_bubbles,
    add_split_lines,
    add_total_bubble_to_bubble_chart,
    draw_motion_chart,
    start_bubble_axes_from_zero,
)
from modules.utilities.config import get_naming_params


def _base_chart_dict_for_axes(x_col: str, y_col: str, *, start_from_zero: bool):
    np = get_naming_params()
    return {
        np["xAxisMetric"]: x_col,
        np["yAxisMetric"]: y_col,
        np["startAxesFromZero"]: start_from_zero,
    }


def _base_chart_dict_for_labels(*, adjust_labels: bool):
    np = get_naming_params()
    return {
        np["xAxisMetric"]: "x",
        np["yAxisMetric"]: "y",
        np["xAxisDimension"]: "label",
        np["bubbleSize"]: "size",
        np["adjustBubbleLabels"]: adjust_labels,
        np["showBubbleLabel"]: np["showBoth"],
    }


def test_add_split_lines_adds_domain_hv_lines():
    # Arrange
    fig = go.Figure()

    # Act
    out = add_split_lines(fig)

    # Assert
    assert out is fig
    assert len(fig.layout.shapes) == 2
    # Horizontal line at y=0.5 in y domain
    h, v = fig.layout.shapes[0], fig.layout.shapes[1]
    assert h["yref"] == "y domain"
    assert pytest.approx(h["y0"]) == 0.5 and pytest.approx(h["y1"]) == 0.5
    # Vertical line at x=0.5 in x domain
    assert v["xref"] == "x domain"
    assert pytest.approx(v["x0"]) == 0.5 and pytest.approx(v["x1"]) == 0.5


def test_start_bubble_axes_from_zero_flag_sets_tozero_and_titles():
    # Arrange
    df = pl.DataFrame({"x": [1, 2], "y": [3, 4]})
    np = get_naming_params()
    chart_dict = _base_chart_dict_for_axes("x", "y", start_from_zero=True)
    fig = go.Figure()

    # Act
    out = start_bubble_axes_from_zero(
        fig, df, column=np["totalName"], chartDict=chart_dict, countRows=1, countCols=1
    )

    # Assert
    assert out is fig
    assert fig.layout.xaxis.rangemode == "tozero"
    assert fig.layout.yaxis.rangemode == "tozero"
    # Titles should be set when single subplot
    assert fig.layout.xaxis.title.text == "x"
    assert fig.layout.yaxis.title.text == "y"


def test_start_bubble_axes_from_zero_computes_ranges_with_fallbacks():
    # Arrange: x is entirely null -> falls back to provided min/max; y uses data
    df = pl.DataFrame({"x": [None, None], "y": [1.0, 2.0]})
    np = get_naming_params()
    chart_dict = _base_chart_dict_for_axes("x", "y", start_from_zero=False)
    # Provide fallbacks for X only
    chart_dict[np["minXDimension"]] = 10.0
    chart_dict[np["maxXDimension"]] = 20.0
    fig = go.Figure()

    # Act
    out = start_bubble_axes_from_zero(
        fig, df, column=np["totalName"], chartDict=chart_dict, countRows=1, countCols=1
    )

    # Assert: X from fallbacks (0.9/1.1 multipliers), Y from data
    assert out is fig
    assert fig.layout.xaxis.rangemode == "normal"
    assert fig.layout.yaxis.rangemode == "normal"
    assert fig.layout.xaxis.range == pytest.approx([9.0, 22.0])
    assert fig.layout.yaxis.range == pytest.approx([0.9, 2.2])
    # Titles preserved for single subplot
    assert fig.layout.xaxis.title.text == "x"
    assert fig.layout.yaxis.title.text == "y"


def test_add_total_bubble_uses_summed_size_and_average_axis_position():
    # Arrange
    df = pl.DataFrame(
        {
            "Unit Price": [10.0, 30.0, 50.0],
            "CWD": [2.0, 6.0, 10.0],
            "size": [5.0, 15.0, 20.0],
        }
    )
    totals = pl.DataFrame({"Unit Price": [999.0], "CWD": [999.0], "size": [40.0]})
    np = get_naming_params()
    chart_dict = {
        np["xAxisMetric"]: "Unit Price",
        np["yAxisMetric"]: "CWD",
        np["bubbleSize"]: "size",
    }
    chart_dict[np["plotTotalBubble"]] = True
    fig = make_subplots(rows=1, cols=1)

    # Act
    out = add_total_bubble_to_bubble_chart(
        fig, df, chart_dict, totals, sizeRef=1.0, countRows=1, countCols=1
    )

    # Assert
    assert out is fig
    total_trace = fig.data[0]
    assert list(total_trace.x) == pytest.approx([30.0])
    assert list(total_trace.y) == pytest.approx([6.0])
    assert list(total_trace.marker.size) == pytest.approx([40.0])
    assert fig.layout.annotations[0].text.startswith("Total:")


def test_add_total_bubble_skips_when_axis_metric_is_summable():
    # Arrange
    df = pl.DataFrame(
        {
            "Unit Price": [10.0, 30.0, 50.0],
            "Units": [2.0, 6.0, 10.0],
            "size": [5.0, 15.0, 20.0],
        }
    )
    totals = pl.DataFrame({"Unit Price": [999.0], "Units": [18.0], "size": [40.0]})
    np = get_naming_params()
    chart_dict = {
        np["xAxisMetric"]: "Unit Price",
        np["yAxisMetric"]: "Units",
        np["bubbleSize"]: "size",
    }
    chart_dict[np["plotTotalBubble"]] = True
    fig = make_subplots(rows=1, cols=1)

    # Act
    out = add_total_bubble_to_bubble_chart(
        fig, df, chart_dict, totals, sizeRef=1.0, countRows=1, countCols=1
    )

    # Assert
    assert out is fig
    assert len(fig.data) == 0
    assert len(fig.layout.annotations) == 0


def test_draw_motion_chart_builds_frames_and_ranges_and_sizes():
    # Arrange
    np = get_naming_params()
    df = pl.DataFrame(
        {
            np["dateName"]: ["2023", "2024", "2023", "2024"],
            "x": [1.0, 2.0, 3.0, 4.0],
            "y": [10.0, 20.0, 30.0, 40.0],
            "size": [100.0, 200.0, 300.0, 400.0],
            "name": ["A", "A", "B", "B"],
            "color": ["cat1", "cat1", "cat2", "cat2"],
        }
    )
    chart_dict = {
        np["chosenChart"]: np["motionChart"],
        np["selectedPeriods"]: ["P0", "P1"],
        np["xAxisMetric"]: "x",
        np["yAxisMetric"]: "y",
        np["bubbleSize"]: "size",
        np["xAxisDimension"]: "name",
        np["yAxisDimension"]: "color",
        np["plotValuesAsChoice"]: np["absolute"],
        np["showBubbleLabel"]: np["showNothing"],  # avoid text branch
    }

    # Act
    fig = draw_motion_chart(
        df, paramDict={}, periodOrder=["2023", "2024"], chartDict=chart_dict
    )

    # Assert
    assert isinstance(fig, go.Figure)
    # Two dates -> two frames, ordered by first appearance
    assert [fr.name for fr in fig.frames] == ["2023", "2024"]
    # Ranges reflect min/max padding
    assert fig.layout.xaxis.range == pytest.approx([0.8, 4.8])
    assert fig.layout.yaxis.range == pytest.approx([8.0, 48.0])
    # Verify first frame trace content and sizing
    first = fig.frames[0].data[0]
    assert first.mode == "markers"
    assert list(first.x) == [1.0, 3.0]
    assert list(first.y) == [10.0, 30.0]
    assert list(first.marker.size) == [100.0, 300.0]
    expected_sizeref = 2.0 * 400.0 / (70.0**2)
    assert first.marker.sizeref == pytest.approx(expected_sizeref)


def test_add_labels_and_values_to_bubbles_keeps_sparse_adjusted_labels():
    # Arrange
    df = pl.DataFrame(
        {
            "label": ["North", "South", "East"],
            "x": [10.0, 50.0, 90.0],
            "y": [10.0, 55.0, 90.0],
            "size": [100.0, 120.0, 140.0],
        }
    )
    chart_dict = _base_chart_dict_for_labels(adjust_labels=True)
    fig = make_subplots(rows=1, cols=1)

    # Act
    add_labels_and_values_to_bubbles(
        fig,
        df,
        chart_dict,
        {"blackColor": "#000000"},
        sizeRef=0.2,
        countRows=1,
        countCols=1,
    )

    # Assert
    annotation_texts = [annotation.text for annotation in fig.layout.annotations]
    assert {"North", "South", "East"}.issubset(annotation_texts)
    assert len(fig.layout.annotations) == 6


def test_add_labels_and_values_to_bubbles_hides_overlapping_adjusted_labels():
    # Arrange
    cluster_count = 8
    df = pl.DataFrame(
        {
            "label": [f"Cluster {index}" for index in range(cluster_count)]
            + ["Top Outlier", "Right Outlier"],
            "x": [10.0 + (index * 0.05) for index in range(cluster_count)]
            + [75.0, 95.0],
            "y": [10.0 + (index * 0.05) for index in range(cluster_count)]
            + [95.0, 70.0],
            "size": [10.0 + index for index in range(cluster_count)] + [500.0, 450.0],
        }
    )
    chart_dict = _base_chart_dict_for_labels(adjust_labels=True)
    fig = make_subplots(rows=1, cols=1)

    # Act
    add_labels_and_values_to_bubbles(
        fig,
        df,
        chart_dict,
        {"blackColor": "#000000"},
        sizeRef=0.25,
        countRows=1,
        countCols=1,
    )

    # Assert
    annotation_texts = [annotation.text for annotation in fig.layout.annotations]
    rendered_labels = [
        text
        for text in annotation_texts
        if text.startswith("Cluster") or text.endswith("Outlier")
    ]
    assert "Top Outlier" in rendered_labels
    assert "Right Outlier" in rendered_labels
    assert len(rendered_labels) < df.height


def test_add_labels_and_values_to_bubbles_prioritizes_aggregate_other_label():
    # Arrange
    cluster_count = 10
    df = pl.DataFrame(
        {
            "label": [f"Cluster {index}" for index in range(cluster_count)]
            + ["Others rank >6", "Top Outlier"],
            "x": [1.0 + (index * 0.02) for index in range(cluster_count)] + [0.2, 10.0],
            "y": [1.0 + (index * 0.02) for index in range(cluster_count)] + [0.2, 10.0],
            "size": [100.0 + index for index in range(cluster_count)] + [1.0, 1000.0],
        }
    )
    chart_dict = _base_chart_dict_for_labels(adjust_labels=True)
    fig = make_subplots(rows=1, cols=1)

    # Act
    add_labels_and_values_to_bubbles(
        fig,
        df,
        chart_dict,
        {"blackColor": "#000000"},
        sizeRef=0.5,
        countRows=1,
        countCols=1,
    )

    # Assert
    annotation_texts = [annotation.text for annotation in fig.layout.annotations]
    assert "Others rank >6" in annotation_texts
