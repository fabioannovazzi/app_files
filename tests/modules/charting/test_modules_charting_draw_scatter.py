import pytest

import polars as pl
from polars.testing import assert_frame_equal
from plotly.subplots import make_subplots

from modules.utilities.config import get_naming_params


def _base_chart_dict_for_labels(*, adjust_labels: bool) -> dict[str, object]:
    np = get_naming_params()
    return {
        np["xAxisMetric"]: "x",
        np["yAxisMetric"]: "y",
        np["xAxisDimension"]: "label",
        np["adjustBubbleLabels"]: adjust_labels,
        np["showScatterLabels"]: True,
        np["logXAxis"]: False,
        np["logYAxis"]: False,
    }


@pytest.mark.skipif(
    not hasattr(__import__("modules.charting.draw_scatter"), "ensure_lazyframe"),
    reason="ensure_lazyframe not exposed by draw_scatter",
)
def test_ensure_lazyframe_from_dataframe_roundtrip():
    # Arrange
    from modules.charting.draw_scatter import ensure_lazyframe

    df = pl.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})

    # Act
    lf = ensure_lazyframe(df)

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    assert_frame_equal(lf.collect(), df)


@pytest.mark.skipif(
    not hasattr(__import__("modules.charting.draw_scatter"), "ensure_lazyframe"),
    reason="ensure_lazyframe not exposed by draw_scatter",
)
def test_ensure_lazyframe_idempotent_on_lazyframe():
    # Arrange
    from modules.charting.draw_scatter import ensure_lazyframe

    df = pl.DataFrame({"a": [10, 20]})
    lf_in = df.lazy()

    # Act
    lf_out = ensure_lazyframe(lf_in)

    # Assert
    assert isinstance(lf_out, pl.LazyFrame)
    assert_frame_equal(lf_out.collect(), df)


@pytest.mark.parametrize(
    "use_lazy,webgl,expected_type",
    [
        (False, False, "scatter"),  # eager DataFrame path
        (True, True, "scattergl"),  # LazyFrame path with WebGL
    ],
)
def test_add_scatter_traces_adds_expected_trace(use_lazy, webgl, expected_type):
    # Arrange
    from plotly.subplots import make_subplots
    from modules.charting.draw_scatter import add_scatter_traces

    df = pl.DataFrame(
        {
            "x": [1, 2],
            "y": [3, 4],
            # The implementation expects a column literally named "colorName"
            "colorName": [0.1, 0.2],
        }
    )
    data_obj = df.lazy() if use_lazy else df

    # draw_scatter looks up real column names from chartDict via naming keys
    chartDict = {"xAxisMetric": "x", "yAxisMetric": "y"}

    fig = make_subplots(rows=1, cols=1)

    # Act
    fig = add_scatter_traces(
        fig,
        data_obj,
        chartDict,
        {},
        name="series1",
        showLegend=True,
        size=5,
        hovertext=["h1", "h2"],
        countRows=1,
        countCols=1,
        webGL=webgl,
        legendTitle="Legend",
    )

    # Assert
    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == expected_type
    assert list(trace.x) == [1, 2]
    assert list(trace.y) == [3, 4]
    assert trace.name == "series1"
    assert getattr(trace, "showlegend", None) is True
    # legend group title text should be set
    assert getattr(trace, "legendgrouptitle").text == "Legend"


def test_draw_scatter_chart_datashader_returns_figure_with_positive_sums():
    # Arrange
    from modules.charting.draw_scatter import draw_scatter_chart_datashader
    import plotly.graph_objects as go

    df = pl.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
    chartDict = {
        "xAxisMetric": "x",
        "yAxisMetric": "y",
        # not used further but required by the function when accessing chartDict
        "selectedPeriods": ["p0", "p1"],
    }

    # Act
    fig = draw_scatter_chart_datashader(df, colorDimension=None, chartDict=chartDict)

    # Assert
    assert fig is not False
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 1


def test_draw_scatter_chart_datashader_returns_false_when_all_zero():
    # Arrange
    from modules.charting.draw_scatter import draw_scatter_chart_datashader

    df = pl.DataFrame({"x": [0, 0], "y": [0, 0]})
    chartDict = {"xAxisMetric": "x", "yAxisMetric": "y", "selectedPeriods": []}

    # Act
    fig = draw_scatter_chart_datashader(df, colorDimension=None, chartDict=chartDict)

    # Assert
    assert fig is False


def test_add_labels_to_scatter_keeps_sparse_adjusted_labels():
    # Arrange
    from modules.charting.draw_scatter import add_labels_to_scatter

    df = pl.DataFrame(
        {
            "label": ["North", "South", "East"],
            "x": [10.0, 50.0, 90.0],
            "y": [10.0, 55.0, 90.0],
        }
    )
    chart_dict = _base_chart_dict_for_labels(adjust_labels=True)
    fig = make_subplots(rows=1, cols=1)

    # Act
    add_labels_to_scatter(
        fig,
        df,
        chart_dict,
        countRows=1,
        countCols=1,
        limitItems=False,
    )

    # Assert
    annotation_texts = [annotation.text for annotation in fig.layout.annotations]
    assert {"North", "South", "East"}.issubset(annotation_texts)
    assert len(fig.layout.annotations) == df.height


def test_add_labels_to_scatter_hides_overlapping_adjusted_labels():
    # Arrange
    from modules.charting.draw_scatter import add_labels_to_scatter

    cluster_count = 8
    df = pl.DataFrame(
        {
            "label": [f"Cluster {index}" for index in range(cluster_count)]
            + ["Top Outlier", "Right Outlier"],
            "x": [10.0 + (index * 0.05) for index in range(cluster_count)]
            + [75.0, 95.0],
            "y": [10.0 + (index * 0.05) for index in range(cluster_count)]
            + [95.0, 70.0],
        }
    )
    chart_dict = _base_chart_dict_for_labels(adjust_labels=True)
    fig = make_subplots(rows=1, cols=1)

    # Act
    _fig, label_lf = add_labels_to_scatter(
        fig,
        df,
        chart_dict,
        countRows=1,
        countCols=1,
        limitItems=False,
    )
    label_df = label_lf.collect()

    # Assert
    annotation_texts = [annotation.text for annotation in fig.layout.annotations]
    assert "Top Outlier" in annotation_texts
    assert "Right Outlier" in annotation_texts
    assert len(annotation_texts) < df.height
    assert label_df.height == len(annotation_texts)


def test_add_labels_to_scatter_aggregates_duplicate_label_positions():
    # Arrange
    from modules.charting.draw_scatter import add_labels_to_scatter

    duplicate_label = "Repeated"
    aggregated_x = 91.0
    aggregated_y = 96.0
    df = pl.DataFrame(
        {
            "label": [duplicate_label, duplicate_label, "Far"],
            "x": [1.0, 90.0, 35.0],
            "y": [1.0, 95.0, 30.0],
        }
    )
    chart_dict = _base_chart_dict_for_labels(adjust_labels=True)
    fig = make_subplots(rows=1, cols=1)

    # Act
    _fig, label_lf = add_labels_to_scatter(
        fig,
        df,
        chart_dict,
        countRows=1,
        countCols=1,
        limitItems=False,
    )
    label_df = label_lf.collect()
    repeated_df = label_df.filter(pl.col("label") == duplicate_label)

    # Assert
    assert repeated_df.height == 1
    assert repeated_df.item(0, "x") == aggregated_x
    assert repeated_df.item(0, "y") == aggregated_y
