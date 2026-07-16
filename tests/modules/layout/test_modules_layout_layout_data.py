import pytest
import polars as pl
from polars.testing import assert_frame_equal

from modules.layout.layout_data import (
    collect_lazyframe,
    collect_and_store_in_session_state,
    collect_base,
)


@pytest.mark.parametrize(
    "fn",
    [collect_lazyframe, collect_and_store_in_session_state],
)
@pytest.mark.parametrize(
    "df",
    [
        pl.DataFrame({"a": [1, 2], "b": ["x", "y"]}),
        pl.DataFrame(schema={"a": pl.Int64, "b": pl.Utf8}),  # empty with schema
    ],
)
def test_collect_functions_return_polars_dataframe_equal_to_input(fn, df):
    # Arrange
    lf = df.lazy()

    # Act
    out = fn(lf)

    # Assert
    assert isinstance(out, pl.DataFrame)
    assert_frame_equal(out, df)


def test_collect_lazyframe_raises_on_non_lazy_input():
    # Arrange: a Polars DataFrame (no .collect method)
    df = pl.DataFrame({"a": [1]})

    # Act / Assert
    with pytest.raises(AttributeError):
        collect_lazyframe(df)  # type: ignore[arg-type]


def test_collect_base_is_memoized_across_calls_with_same_params():
    # Arrange
    base_df = pl.DataFrame({"x": [1, 2], "y": [10, 20]})
    lf = base_df.lazy()

    # Same params but different order in list (normalized by decorator)
    index_cols_1 = ["id", "date", "extra"]
    index_cols_2 = ["extra", "date", "id"]
    params = {"p": 1}

    # Act
    out1 = collect_base(lf, index_cols_1, params)
    out2 = collect_base(lf, index_cols_2, params)  # should hit cache

    # Assert: content equal and same cached instance
    assert_frame_equal(out1, base_df)
    assert out1 is out2

    # Changing non-polars params breaks the cache key
    out3 = collect_base(lf, index_cols_2, {"p": 2})
    assert_frame_equal(out3, base_df)
    assert out3 is not out1
