from io import BytesIO

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from src.io_utils import collect_streaming, convert_df_csv, convert_df_parquet


def test_collect_streaming_dataframe_returns_same_instance():
    # Arrange
    df = pl.DataFrame({"a": [1, 2]})

    # Act
    out = collect_streaming(df)

    # Assert
    assert out is df
    assert_frame_equal(out, df)


def test_collect_streaming_lazyframe_materializes_equal_dataframe():
    # Arrange
    df = pl.DataFrame({"a": [2, 1], "b": ["y", "x"]})
    lf = df.lazy()

    # Act
    out = collect_streaming(lf)

    # Assert: materialized and content-equal (ignore potential row order)
    assert isinstance(out, pl.DataFrame)
    assert_frame_equal(out.sort("a"), df.sort("a"))


def test_convert_df_csv_replaces_invalid_bytes_and_preserves_columns():
    # Arrange: include a Binary column with invalid UTF-8 sequences
    data = {
        "bin": [b"a\xffb", b"c\x80d"],
        "txt": ["x", "y"],
        "num": [1, 2],
    }
    df = pl.DataFrame(data, schema={"bin": pl.Binary, "txt": pl.Utf8, "num": pl.Int64})

    # Act
    csv_bytes = convert_df_csv(df)

    # Assert: read back and verify replacement character and values
    read_back = pl.read_csv(BytesIO(csv_bytes))
    expected = pl.DataFrame({
        "bin": ["a�b", "c�d"],
        "txt": ["x", "y"],
        "num": [1, 2],
    })
    assert_frame_equal(read_back, expected)


def test_convert_df_parquet_roundtrip_preserves_data():
    # Arrange
    df = pl.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})

    # Act
    pq_bytes = convert_df_parquet(df)

    # Assert: round-trip via Polars
    read_back = pl.read_parquet(BytesIO(pq_bytes))
    assert_frame_equal(read_back, df)


def test_convert_df_parquet_invalid_input_raises_attribute_error():
    # Arrange & Act / Assert
    with pytest.raises(AttributeError):
        convert_df_parquet(123)  # type: ignore[arg-type]
