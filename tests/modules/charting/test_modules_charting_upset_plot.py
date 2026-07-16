from __future__ import annotations

import polars as pl
import plotly.graph_objects as go
import pytest

from modules.charting.upset_plot import plot_upset
from modules.utilities.config import get_naming_params
from modules.charting.chart_primitives import (
    get_color_dictionary,
    get_hightlight_color,
)


@pytest.mark.parametrize("as_lazy", [False, True])
def test_plot_upset_basic_counts_and_highlight_color(as_lazy: bool) -> None:
    # Arrange: small boolean grid with clear intersections
    df = pl.DataFrame(
        {
            "A": [True, True, True, False, True, False],
            "B": [True, True, False, True, True, True],
            "C": [False, True, False, False, False, True],
            # Non-boolean column must be ignored
            "X": [1, 2, 3, 4, 5, 6],
        }
    )
    lf_or_df = df.lazy() if as_lazy else df

    naming = get_naming_params()
    chart_dict = {naming["highlightedDimension"]: ["A", "B"]}
    expected_highlight = get_hightlight_color(
        chart_dict, get_color_dictionary(chart_dict)
    )

    # Act
    fig = plot_upset(lf_or_df, chart_dict)

    # Assert
    assert isinstance(fig, go.Figure)

    bar = next(trace for trace in fig.data if trace.type == "bar")
    set_size_bar = next(trace for trace in fig.data if trace.name == "Set size")
    set_label_trace = next(trace for trace in fig.data if trace.name == "Set labels")
    active_dots = next(trace for trace in fig.data if trace.name == "In intersection")
    connectors = [trace for trace in fig.data if trace.name == "Membership connector"]
    assert len(connectors) >= 2

    x_labels = list(bar.customdata)
    y_vals = list(bar.y)
    colors = list(bar.marker.color)
    by_label = {lbl: (cnt, col) for lbl, cnt, col in zip(x_labels, y_vals, colors)}

    # Expected intersections and counts
    assert by_label["A&B"][0] == 2
    assert by_label["A&B&C"][0] == 1
    assert by_label["A"][0] == 1
    assert by_label["B"][0] == 1
    assert by_label["B&C"][0] == 1

    # Highlight applies when the highlighted set is a subset of the label
    assert by_label["A&B"][1] == expected_highlight
    assert by_label["A&B&C"][1] == expected_highlight
    # Non-matching intersections stay neutral.
    assert by_label["A"][1] == "#2F2F2F"
    assert by_label["B"][1] == "#2F2F2F"
    assert by_label["B&C"][1] == "#2F2F2F"
    assert len(active_dots.x) == sum(len(label.split("&")) for label in x_labels)
    assert bar.width == 0.32
    assert bar.textposition == "outside"
    assert list(bar.text) == [str(value) for value in y_vals]
    assert bar.textfont.size == 12
    assert set_size_bar.orientation == "h"
    assert list(set_size_bar.x) == [2, 5, 4]
    assert list(set_size_bar.text) == ["2", "5", "4"]
    assert set_size_bar.textposition == "outside"
    assert set_size_bar.textfont.size == 12
    assert set_size_bar.width == 0.34
    assert set_size_bar.base == 0
    assert list(set_label_trace.text) == ["C", "B", "A"]
    assert set_label_trace.textposition == "middle left"
    assert set_label_trace.textfont.size == 12
    assert set_label_trace.cliponaxis is False
    assert fig.layout.width < 900
    assert fig.layout.font.size == 12
    assert fig.layout.yaxis3.title.font.size == 12
    assert fig.layout.xaxis4.range[0] > fig.layout.xaxis4.range[1]
    assert fig.layout.xaxis6.showticklabels is False
    assert fig.layout.xaxis6.title.text is None
    assert fig.layout.yaxis4.showticklabels is False
    assert fig.layout.yaxis6.showticklabels is False


def test_plot_upset_no_boolean_columns_returns_empty_figure() -> None:
    # Arrange: no boolean columns present
    df = pl.DataFrame({"X": [1, 2, 3]})
    chart_dict: dict = {}

    # Act
    fig = plot_upset(df, chart_dict)

    # Assert: returns an empty figure (no traces)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_plot_upset_applies_minimum_intersection_size_filter() -> None:
    # Arrange: same data as the basic test
    df = pl.DataFrame(
        {
            "A": [True, True, True, False, True, False],
            "B": [True, True, False, True, True, True],
            "C": [False, True, False, False, False, True],
        }
    )
    naming = get_naming_params()
    chart_dict = {
        naming["minIntersectionSize"]: 2,  # keep only intersections with count >= 2
        naming["highlightedDimension"]: ["C"],  # does not match "A&B"
    }

    # Act
    fig = plot_upset(df, chart_dict)

    # Assert: only the "A&B" intersection remains and is not highlighted
    assert isinstance(fig, go.Figure)
    bar = next(trace for trace in fig.data if trace.type == "bar")
    active_dots = next(trace for trace in fig.data if trace.name == "In intersection")
    x_labels = list(bar.customdata)
    y_vals = list(bar.y)
    colors = list(bar.marker.color)

    assert x_labels == ["A&B"]
    assert y_vals == [2]
    assert colors == ["#2F2F2F"]
    assert list(active_dots.customdata) == ["B", "A"]
