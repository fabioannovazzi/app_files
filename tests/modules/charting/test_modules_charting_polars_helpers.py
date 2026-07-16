from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.charting.polars_helpers import (
    ensure_lazyframe,
    get_schema_and_column_names,
)


def test_get_schema_and_column_names_dataframe_returns_expected_columns_and_schema():
    # Arrange
    df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})

    # Act
    cols, schema = get_schema_and_column_names(df)

    # Assert
    assert cols == ["a", "b"]
    assert schema == dict(df.schema)


def test_get_schema_and_column_names_lazyframe_matches_collect_schema():
    # Arrange
    df = pl.DataFrame({"x": [1], "y": [2.5]})
    lf = df.lazy()
    expected_schema = dict(lf.collect_schema())

    # Act
    cols, schema = get_schema_and_column_names(lf)

    # Assert
    assert cols == list(expected_schema.keys())
    assert schema == expected_schema


def test_get_schema_and_column_names_empty_dataframe_returns_empty_results():
    # Arrange: empty frame with no columns
    df = pl.DataFrame({})

    # Act
    cols, schema = get_schema_and_column_names(df)

    # Assert
    assert cols == []
    assert schema == {}


def test_ensure_lazyframe_from_dataframe_returns_lazy_and_roundtrips():
    # Arrange
    df = pl.DataFrame({"v": [10, 20]})

    # Act
    lf = ensure_lazyframe(df)

    # Assert
    assert isinstance(lf, pl.LazyFrame)
    assert_frame_equal(lf.collect(), df)


def test_ensure_lazyframe_idempotent_for_lazyframe():
    # Arrange
    lf = pl.DataFrame({"z": [1]}).lazy()

    # Act
    out = ensure_lazyframe(lf)

    # Assert
    assert out is lf


def test_ensure_lazyframe_invalid_type_raises_typeerror():
    # Arrange
    bad = [{"a": 1}]

    # Act / Assert
    with pytest.raises(TypeError):
        ensure_lazyframe(bad)  # type: ignore[arg-type]
