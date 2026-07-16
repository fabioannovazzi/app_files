from __future__ import annotations

import pytest
import polars as pl
from polars.testing import assert_frame_equal

from modules.charting.draw_charts_utils import (
    collect_tail,
    to_lists,
    get_metric_array_params,
)


def test_collect_tail_lazyframe_golden_and_boundary():
    # Arrange
    df = pl.DataFrame({"x": [1, 2, 3, 4], "y": ["a", "b", "c", "d"]})
    lf = df.lazy()

    # Act (golden path)
    res_2 = collect_tail(lf, 2)

    # Assert (golden path)
    assert_frame_equal(res_2, df.tail(2))

    # Act (boundary: n = 0)
    res_0 = collect_tail(lf, 0)

    # Assert (boundary)
    assert_frame_equal(res_0, df.tail(0))


def test_to_lists_returns_expected_lists_and_empty_for_no_cols():
    # Arrange
    lf = pl.LazyFrame({"a": [1, 2], "b": [10, 20]})

    # Act (golden path)
    out = to_lists(lf, ["a", "b"])

    # Assert (golden path)
    assert out["a"] == [1, 2]
    assert out["b"] == [10, 20]

    # Act (boundary: no columns requested)
    out_empty = to_lists(lf, [])

    # Assert (boundary)
    assert out_empty == {}


def test_to_lists_raises_on_missing_column():
    # Arrange
    lf = pl.LazyFrame({"a": [1, 2]})

    # Act / Assert (negative)
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        to_lists(lf, ["missing"])  # column does not exist


def test_get_metric_array_params_structure_contains_expected_keys():
    # Act
    params = get_metric_array_params()

    # Assert: returns a dict with expected metric-group keys mapped to lists
    assert isinstance(params, dict)
    # The config-backed implementation exposes these groups; validate presence and type.
    for key in [
        "priceMetricsArray",
        "percentMetricsArray",
        "noSumMetricsArray",
        "growthMetricArray",
        "valueMetricsArray",
        "volumeMetricsArray",
    ]:
        assert key in params
        assert isinstance(params[key], list)
