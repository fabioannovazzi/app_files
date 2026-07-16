import pytest
import polars as pl
import plotly.graph_objects as go

from modules.charting.plot_horizontal_bar import plot_horizontal_bar


@pytest.mark.parametrize("as_lazy", [False, True])
def test_plot_horizontal_bar_basic_sorted_rounds_and_layout(as_lazy: bool):
    # Arrange
    df = pl.DataFrame({
        "x": [3.7, 1.2, 2.6],  # unsorted floats to be rounded then cast to int
        "y": ["c", "a", "b"],
    })
    data_in = df.lazy() if as_lazy else df

    # Act
    fig = plot_horizontal_bar(data_in, "x", "y", title="My Title")

    # Assert
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    bar = fig.data[0]
    assert bar.orientation == "h"
    assert bar.marker.color == "black"

    # Values rounded to ints and sorted by original x ascending
    assert list(bar.x) == [1, 3, 4]
    assert all(isinstance(v, int) for v in bar.x)
    assert list(bar.y) == ["a", "b", "c"]
    # Text labels mirror rounded values (Plotly stores text as strings)
    assert list(bar.text) == [str(v) for v in bar.x]

    # Layout details
    assert fig.layout.title.text == "My Title"
    assert fig.layout.xaxis.title.text == "x"
    assert fig.layout.yaxis.title.text == "y"
    assert fig.layout.xaxis.showticklabels is False


@pytest.mark.parametrize(
    "x_col,y_col",
    [
        ("missing", "y"),
        ("x", "missing"),
    ],
)
def test_plot_horizontal_bar_missing_columns_returns_none(x_col: str, y_col: str):
    # Arrange
    df = pl.DataFrame({"x": [1.2], "y": ["a"]})

    # Act
    fig = plot_horizontal_bar(df, x_col, y_col, title="T")

    # Assert
    assert fig is None
