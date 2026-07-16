import polars as pl
import pytest
from polars.exceptions import ColumnNotFoundError
from polars.testing import assert_frame_equal

from modules.variance.variance_utils import (
    ensure_lazyframe,
    get_column_sum,
    get_row_count,
)


@pytest.mark.parametrize("as_lazy", [False, True])
def test_ensure_lazyframe_returns_lazyframe_and_preserves_data(as_lazy: bool):
    # Arrange
    df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    obj = df.lazy() if as_lazy else df

    # Act
    lf = ensure_lazyframe(obj)

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    assert_frame_equal(lf.collect(), df)


def test_ensure_lazyframe_invalid_input_raises_typeerror():
    # Arrange
    obj = {"a": [1, 2]}  # not a DataFrame or LazyFrame

    # Act / Assert
    with pytest.raises(TypeError):
        ensure_lazyframe(obj)  # type: ignore[arg-type]


@pytest.mark.parametrize("as_lazy", [False, True])
def test_get_column_sum_sums_values_for_df_and_lazy(as_lazy: bool):
    # Arrange
    df = pl.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]})
    obj = df.lazy() if as_lazy else df

    # Act
    total = get_column_sum(obj, "x")

    # Assert
    assert total == 6
    assert isinstance(total, (int, float))


def test_get_column_sum_missing_column_raises():
    # Arrange
    df = pl.DataFrame({"x": [1, 2, 3]})

    # Act / Assert
    with pytest.raises(ColumnNotFoundError):
        get_column_sum(df, "does_not_exist")


@pytest.mark.parametrize(
    "n_rows,as_lazy",
    [
        (0, False),
        (0, True),
        (3, False),
        (3, True),
    ],
)
def test_get_row_count_handles_df_and_lazy_and_empty(n_rows: int, as_lazy: bool):
    # Arrange
    df = pl.DataFrame({"x": list(range(n_rows))})
    obj = df.lazy() if as_lazy else df

    # Act
    count = get_row_count(obj)

    # Assert
    assert count == n_rows
    assert isinstance(count, int)


def test_get_row_count_invalid_type_raises_typeerror():
    # Arrange
    obj = [1, 2, 3]

    # Act / Assert
    with pytest.raises(TypeError):
        get_row_count(obj)  # type: ignore[arg-type]
