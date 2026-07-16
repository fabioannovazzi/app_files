from datetime import date

import pytest
import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.charting.draw_timeline import (
    add_annotations_to_timeline,
    column_to_list,
    adjust_slope_plot,
    adjust_timeline_plot,
)
from modules.data.time_series_data_prep import prepare_data_for_timeline_plot
from modules.utilities.config import get_naming_params


def make_minimal_params():
    np = get_naming_params()
    # get_user_message accesses paramDict[np["columnHash"]]
    return {np["columnHash"]: ""}


def test_column_to_list_basic_and_nulls():
    # Arrange
    lf = pl.DataFrame({"a": [1, None, 3]}).lazy()

    # Act
    result = column_to_list(lf, "a")

    # Assert
    assert result == [1, None, 3]


def test_column_to_list_empty_frame_returns_empty_list():
    # Arrange
    empty = pl.DataFrame({"a": pl.Series("a", [], dtype=pl.Int64)}).lazy()

    # Act
    result = column_to_list(empty, "a")

    # Assert
    assert result == []


def test_column_to_list_missing_column_raises():
    # Arrange
    lf = pl.DataFrame({"a": [1, 2]}).lazy()

    # Act / Assert
    with pytest.raises(Exception):
        column_to_list(lf, "missing")


def test_adjust_slope_plot_updates_layout_and_title_annotation():
    # Arrange
    np = get_naming_params()
    fig = go.Figure()
    df = pl.DataFrame({"x": [1]}).lazy()
    chart_dict = {np["chosenChart"]: np["slopeChart"]}
    params = make_minimal_params()
    title = "Slope Title"

    # Act
    out = adjust_slope_plot(
        fig,
        df,
        key="dim",
        metric="metric",
        title=title,
        height=400,
        width=600,
        paramDict=params,
        chartDict=chart_dict,
    )

    # Assert
    assert out is fig
    assert fig.layout.width == 600
    assert fig.layout.height == 400
    assert fig.layout.dragmode == "drawrect"  # enable_draw_shapes applied
    assert any(a["text"] == title for a in fig.layout.annotations)


def test_adjust_timeline_plot_updates_layout_and_title_annotation():
    # Arrange
    np = get_naming_params()
    fig = go.Figure()
    df = pl.DataFrame({"x": [1]}).lazy()
    chart_dict = {np["chosenChart"]: np["timelineChart"]}
    params = make_minimal_params()
    title = "Timeline Title"

    # Act
    out = adjust_timeline_plot(
        fig,
        df,
        key="dim",
        metric="metric",
        title=title,
        height=300,
        width=500,
        paramDict=params,
        chartDict=chart_dict,
    )

    # Assert
    assert out is fig
    assert fig.layout.width == 500
    # update_timeline_chart_layout adds (topMargin-100) to height
    from modules.utilities.config import get_config_params

    cfg = get_config_params()
    ann = cfg[np["annotationDict"]]
    expected_height = 300 + (ann[np["timelineChart"]]["topMargin"] - 100)
    assert fig.layout.height == expected_height
    assert fig.layout.dragmode == "drawrect"
    assert any(a["text"] == title for a in fig.layout.annotations)


def test_adjust_timeline_plot_missing_chosen_chart_raises_keyerror():
    # Arrange
    fig = go.Figure()
    df = pl.DataFrame({"x": [1]}).lazy()
    params = make_minimal_params()

    # Act / Assert
    with pytest.raises(KeyError):
        adjust_timeline_plot(
            fig,
            df,
            key="k",
            metric="m",
            title="T",
            height=200,
            width=400,
            paramDict=params,
            chartDict={},  # missing chosenChart mapping
        )


def test_prepare_data_for_timeline_plot_sorts_date_axis():
    # Arrange
    np = get_naming_params()
    first_date = date(2019, 1, 31)
    middle_date = date(2019, 2, 28)
    last_date = date(2019, 3, 31)
    frame = pl.DataFrame(
        {
            "Date": [last_date, first_date, middle_date],
            "Company": ["Total", "Total", "Total"],
            "Sales": [30.0, 10.0, 20.0],
        }
    )

    # Act
    result = prepare_data_for_timeline_plot(
        frame,
        "Company",
        "Sales",
        ["Total"],
        {np["chosenChart"]: np["timelineChart"]},
    ).collect(engine="streaming")

    # Assert
    assert result.get_column("Date").to_list() == [
        first_date,
        middle_date,
        last_date,
    ]
    assert result.get_column("_Total").to_list() == [10.0, 20.0, 30.0]


def test_add_annotations_to_timeline_uses_date_axis_with_direct_labels():
    # Arrange
    np = get_naming_params()
    first_date = date(2019, 1, 31)
    middle_date = date(2019, 2, 28)
    last_date = date(2019, 3, 31)
    frame = pl.DataFrame(
        {
            "Date": [first_date, middle_date, last_date],
            "Total": [10.0, 30.0, 20.0],
        }
    )
    fig = make_subplots(rows=1, cols=1)

    # Act
    add_annotations_to_timeline(
        frame,
        fig,
        ["Total"],
        ["#343434"],
        {
            np["chosenChart"]: np["timelineChart"],
            np["plotValuesAsChoice"]: np["absolute"],
        },
        1,
        1,
    )

    # Assert
    assert list(fig.data[0].x) == [first_date, middle_date, last_date]
    assert fig.layout.xaxis.type == "date"
    assert fig.layout.xaxis.tickformat == "%b %Y"
    labels_by_date = {annotation.x: annotation for annotation in fig.layout.annotations}
    assert set(labels_by_date) == {first_date, middle_date, last_date}
    assert labels_by_date[first_date].xshift == 18
    assert labels_by_date[last_date].xshift == -18
