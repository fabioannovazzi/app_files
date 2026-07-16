import polars as pl
import pytest
from polars.exceptions import ColumnNotFoundError
from polars.testing import assert_frame_equal
from plotly.subplots import make_subplots

from modules.charting.draw_width_and_stacked_plots import (
    _center_subplot_titles,
    drop_all_null_rows_lazy,
    is_numeric_dtype,
    percentage_cols_lazy,
)


def test_drop_all_null_rows_lazy_removes_only_all_null_rows():
    # Arrange
    df = pl.DataFrame({"a": [1, None, 3, None], "b": [None, None, 4, None]})
    lf = df.lazy()

    # Act
    out = drop_all_null_rows_lazy(lf).collect()

    # Assert
    expected = pl.DataFrame({"a": [1, 3], "b": [None, 4]})
    assert_frame_equal(out, expected)


def test_drop_all_null_rows_lazy_no_columns_returns_unchanged():
    # Arrange
    df = pl.DataFrame({})
    lf = df.lazy()

    # Act
    out = drop_all_null_rows_lazy(lf).collect()

    # Assert
    assert out.height == 0 and out.width == 0


@pytest.mark.parametrize(
    "df, cols, denom, expected",
    [
        (
            pl.DataFrame({"a": [20, 50], "b": [30, 50], "value": [100, 200]}),
            ["a", "b"],
            "value",
            pl.DataFrame({"a": [20.0, 25.0], "b": [30.0, 25.0], "value": [100, 200]}),
        ),
        (
            pl.DataFrame({"a": [1, 2], "b": [3, 4], "value": [0, 100]}),
            ["a", "b"],
            "value",
            pl.DataFrame({"a": [0.0, 2.0], "b": [0.0, 4.0], "value": [0, 100]}),
        ),
    ],
)
def test_percentage_cols_lazy_basic_and_zero_denom(df, cols, denom, expected):
    # Arrange
    lf = df.lazy()

    # Act
    out = percentage_cols_lazy(lf, cols, denom).collect()

    # Assert
    assert_frame_equal(out, expected)


def test_percentage_cols_lazy_missing_denom_raises_on_collect():
    # Arrange
    df = pl.DataFrame({"a": [1, 2], "value": [10, 20]})
    lf = df.lazy()

    # Act / Assert
    with pytest.raises(ColumnNotFoundError):
        percentage_cols_lazy(lf, ["a"], "missing").collect()


@pytest.mark.parametrize(
    "dtype, expected",
    [
        (pl.Int64, True),
        (pl.Float64, True),
        (pl.Boolean, False),
        (pl.Utf8, False),
        (pl.Date, False),
    ],
)
def test_is_numeric_dtype_recognises_numeric_and_non_numeric(dtype, expected):
    assert is_numeric_dtype(dtype) is expected


def test_center_subplot_titles_aligns_lower_row_with_panel_domain():
    # Arrange
    lower_row_top = 0.47
    title_gap = 0.008
    expected_lower_title_y = lower_row_top + title_gap
    fig = make_subplots(
        rows=2,
        cols=2,
        vertical_spacing=0.06,
        horizontal_spacing=0.12,
        subplot_titles=["Permanent", "Male", "Root", "Semi-Permanent"],
    )
    for annotation in fig.layout.annotations:
        annotation.x = 0.22
        annotation.y = min(float(annotation.y) + 0.04, 1.0)
        annotation.xref = "paper"
        annotation.yref = "paper"

    # Act
    _center_subplot_titles(fig, ["Permanent", "Male", "Root", "Semi-Permanent"])

    # Assert
    title_positions = [
        (round(float(annotation.x), 3), round(float(annotation.y), 3))
        for annotation in fig.layout.annotations
    ]
    assert title_positions == [
        (0.22, 1.0),
        (0.78, 1.0),
        (0.22, expected_lower_title_y),
        (0.78, expected_lower_title_y),
    ]
