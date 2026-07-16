import polars as pl
import pytest
from polars.testing import assert_series_equal

# Import to ensure monkey-patches are applied to Polars classes
import modules.polars_compat as polars_compat  # noqa: F401


def test_map_dict_basic_mapping_and_dtype_utf8():
    # Arrange
    df = pl.DataFrame({"x": [1, 2, 99]})
    mapping = {1: "one", 2: "two"}

    # Act
    out = df.select(pl.col("x").map_dict(mapping, default="other").alias("mapped"))

    # Assert
    expected = pl.Series("mapped", ["one", "two", "other"])  # dtype Utf8
    assert_series_equal(out["mapped"], expected)


def test_map_dict_all_none_results_yield_null_dtype():
    # Arrange
    df = pl.DataFrame({"x": [1, 2]})

    # Act
    out = df.select(pl.col("x").map_dict({}, default=None).alias("mapped"))

    # Assert
    expected = pl.Series("mapped", [None, None], dtype=pl.Null)
    assert_series_equal(out["mapped"], expected)


def test_frame_equal_true_for_identical_frames():
    # Arrange
    a = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    b = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})

    # Act
    result = a.frame_equal(b)

    # Assert
    assert result is True


def test_frame_equal_false_logs_mismatch(monkeypatch):
    # Arrange
    a = pl.DataFrame({"a": [1, 2]})
    b = pl.DataFrame({"a": [1, 3]})

    calls = []

    def fake_write(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(polars_compat.ui, "write", fake_write, raising=True)

    # Act
    result = a.frame_equal(b)

    # Assert
    assert result is False
    assert len(calls) == 1
    assert isinstance(calls[0], tuple)
    assert len(calls[0]) >= 1 and calls[0][0] == "frame_equal mismatch:"
