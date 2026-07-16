from __future__ import annotations

import pytest
import polars as pl
from polars.exceptions import ColumnNotFoundError
from polars.testing import assert_frame_equal


def test_resolve_hierarchies_basic_counts_and_weights():
    # Arrange: two parent columns with clear winners per child
    df = pl.DataFrame(
        {
            "child": [
                "A",
                "A",
                "A",
                "A",
                "B",
                "B",
                "B",
                "B",
                "B",
            ],
            "p1": ["X", "X", "Y", "Y", "M", "M", "M", "N", "N"],
            "p2": ["R", "R", "S", "S", "V", "V", "U", "U", "V"],
            "w": [1, 1, 5, 7, 1, 1, 1, 10, 10],
        }
    )

    # Act
    from src.hierarchy_logic import resolve_hierarchies

    lf = resolve_hierarchies(df, "child", ["p1", "p2"], weight_col="w")

    # Assert: returns LazyFrame and maps a single parent per child per column
    assert isinstance(lf, pl.LazyFrame)
    result = lf.collect()
    mapping = (
        result.group_by("child")
        .agg(pl.col("p1").first().alias("p1"), pl.col("p2").first().alias("p2"))
        .sort("child")
    )
    expected = pl.DataFrame({"child": ["A", "B"], "p1": ["Y", "M"], "p2": ["S", "V"]})
    assert_frame_equal(mapping, expected)


def test_resolve_hierarchies_tie_break_by_parent_name_when_no_weight():
    # Arrange: counts tie, no weight provided; lexicographically smaller parent wins
    df = pl.DataFrame({"child": ["C", "C"], "p1": ["Z", "A"]})

    # Act
    from src.hierarchy_logic import resolve_hierarchies

    lf = resolve_hierarchies(df.lazy(), "child", ["p1"], weight_col=None)

    # Assert
    result = lf.collect()
    mapping = (
        result.group_by("child").agg(pl.col("p1").first().alias("p1")).sort("child")
    )
    expected = pl.DataFrame({"child": ["C"], "p1": ["A"]})
    assert_frame_equal(mapping, expected)


def test_resolve_hierarchies_raises_when_weight_col_missing():
    # Arrange
    df = pl.DataFrame({"child": ["X", "X"], "p1": ["A", "B"]})

    # Act & Assert: missing weight column triggers a Polars error during evaluation
    from src.hierarchy_logic import resolve_hierarchies

    with pytest.raises(ColumnNotFoundError):
        resolve_hierarchies(df, "child", ["p1"], weight_col="missing")
