from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.charting.upset_helpers import build_upset_matrix


def test_build_upset_matrix_basic_membership_and_sorting():
    """Build boolean membership matrix per Name; columns follow given sets order."""
    # Arrange: minimal mapping of Name->set with duplicates
    df = pl.DataFrame(
        {
            "Name": ["A", "A", "B", "C"],
            "set": ["x", "y", "y", "z"],
        }
    )
    sets = ["x", "y", "z", "w"]  # include a set with no membership

    # Act
    out = build_upset_matrix(df.lazy(), sets).collect()

    # Assert: rows sorted by Name, boolean membership per set, columns order preserved
    expected = pl.DataFrame(
        {
            "Name": ["A", "B", "C"],
            "x": [True, False, False],
            "y": [True, True, False],
            "z": [False, False, True],
            "w": [False, False, False],
        }
    )
    assert_frame_equal(out, expected)


def test_build_upset_matrix_empty_sets_returns_unique_names_only():
    """When no sets requested, only unique Names are returned (sorted)."""
    df = pl.DataFrame({"Name": ["B", "A", "A"], "set": ["x", "x", "y"]})

    out = build_upset_matrix(df.lazy(), []).collect()

    expected = pl.DataFrame({"Name": ["A", "B"]})
    assert_frame_equal(out, expected)


def test_build_upset_matrix_raises_when_required_columns_missing():
    """Missing the 'set' or 'Name' column should error on collect."""
    df_missing_set = pl.DataFrame({"Name": ["A", "B"]})
    with pytest.raises(Exception):
        build_upset_matrix(df_missing_set.lazy(), ["x"]).collect()
