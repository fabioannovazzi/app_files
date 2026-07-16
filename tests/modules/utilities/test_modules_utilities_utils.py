from __future__ import annotations

import pytest
import polars as pl

from modules.utilities.utils import (
    get_schema_and_column_names,
    is_valid_lazyframe,
    get_row_count,
)


def test_get_schema_and_column_names_on_dataframe_returns_columns_and_schema():
    # Arrange
    df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})

    # Act
    columns, schema = get_schema_and_column_names(df)

    # Assert
    assert columns == df.columns
    assert isinstance(schema, dict) and schema == df.schema


def test_get_schema_and_column_names_on_object_without_schema_uses_columns_only():
    # Arrange: object with callable `columns` and no `schema`
    class Dummy:
        def __init__(self, cols):
            self._cols = cols

        def columns(self):  # callable to exercise callable-path
            return list(self._cols)

    obj = Dummy(["u", "v"])

    # Act
    columns, schema = get_schema_and_column_names(obj)

    # Assert
    assert columns == ["u", "v"]
    assert schema is None


@pytest.mark.parametrize(
    "obj, expected",
    [
        (pl.DataFrame({"a": [1]}), True),  # non-empty eager
        (pl.DataFrame(schema={"a": pl.Int64}), False),  # empty eager
        (pl.DataFrame({"a": [1]}).lazy(), True),  # lazy with schema
        (None, False),  # not a frame
    ],
)
def test_is_valid_lazyframe_various_objects(obj, expected):
    # Act / Assert
    assert is_valid_lazyframe(obj) is expected


def test_get_row_count_dataframe_and_lazyframe_and_type_error():
    # Arrange
    df = pl.DataFrame({"a": [1, 2, 3]})
    lf = df.lazy()

    # Act / Assert: counts match
    assert get_row_count(df) == 3
    assert get_row_count(lf) == 3

    # Negative: unsupported type
    with pytest.raises(TypeError) as excinfo:
        get_row_count(42)  # type: ignore[arg-type]
    assert "Unsupported object type" in str(excinfo.value)
