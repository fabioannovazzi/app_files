from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.check_entries.utils import (
    OK_MSG,
    flatten_mismatches,
    hide_line_numbers,
    normalize_status,
)


def test_flatten_mismatches_basic_explodes_and_unnests():
    # Arrange
    df = pl.DataFrame(
        {
            "row_id": [1, 2],
            "mismatches": [
                [
                    {"reason": "price", "expected": 10},
                    {"reason": "qty", "expected": 5},
                ],
                [{"reason": "price", "expected": 10}],
            ],
        }
    )

    # Act
    out, mapping = flatten_mismatches(df)

    # Assert
    assert mapping == {"reason": "reason", "expected": "expected"}
    expected = pl.DataFrame(
        {
            "row_id": [1, 1, 2],
            "reason": ["price", "qty", "price"],
            "expected": [10, 5, 10],
        }
    )
    assert_frame_equal(out, expected)


def test_flatten_mismatches_conflicting_field_names_are_prefixed_uniquely():
    # Arrange: existing columns collide with struct field names
    df = pl.DataFrame(
        {
            "field": ["A"],
            "mismatch_field": ["B"],
            "mismatches": [[{"field": "x", "mismatch_field": "y"}]],
        }
    )

    # Act
    out, mapping = flatten_mismatches(df, column="mismatches", prefix="mismatch_")

    # Assert: repeated prefixing to avoid collisions
    assert mapping["field"] == "mismatch_mismatch_field"
    assert mapping["mismatch_field"] == "mismatch_mismatch_mismatch_field"

    row = out.row(0, named=True)
    assert row["mismatch_mismatch_field"] == "x"
    assert row["mismatch_mismatch_mismatch_field"] == "y"
    # original columns remain
    assert set(["field", "mismatch_field"]).issubset(set(out.columns))


def test_flatten_mismatches_noop_when_column_missing():
    # Arrange
    df = pl.DataFrame({"a": [1], "b": [2]})

    # Act
    out, mapping = flatten_mismatches(df)

    # Assert
    assert mapping == {}
    assert_frame_equal(out, df)


def test_normalize_status_rewrites_verified_and_fills_explanation():
    # Arrange
    df = pl.DataFrame(
        {
            "check_status": ["verified", "verified", "verified", "error"],
            "explanation": [None, "", "Already fine", "Missing value"],
        }
    )

    # Act
    out = normalize_status(df)

    # Assert
    expected = pl.DataFrame(
        {
            "check_status": ["ok", "ok", "ok", "error"],
            "explanation": [OK_MSG, OK_MSG, "Already fine", "Missing value"],
        }
    )
    assert_frame_equal(out, expected)


def test_hide_line_numbers_drops_top_level_and_nested_entries():
    # Arrange
    df = pl.DataFrame(
        {
            "id": [1],
            "line_numbers": [[1, 2]],
            "mismatches": [
                [
                    {
                        "field": "price",
                        "message": "delta",
                        "line_numbers": [10, 11],
                    },
                    {
                        "field": "qty",
                        "message": "low",
                        "line_numbers": [12],
                    },
                ]
            ],
        }
    )

    # Act
    out = hide_line_numbers(df)

    # Assert: top-level column removed
    assert "line_numbers" not in out.columns
    # Nested entries have the key stripped
    nested = out["mismatches"].item()
    # Polars may return a Series for list-typed scalars; normalise to Python list
    if isinstance(nested, pl.Series):
        nested_list = nested.to_list()
    else:
        nested_list = nested
    assert all("line_numbers" not in entry for entry in nested_list)
    # Other fields preserved
    assert {x["field"] for x in nested_list} == {"price", "qty"}


@pytest.mark.parametrize(
    "mismatches, expected",
    [
        (None, None),
        ([], []),
    ],
)
def test_hide_line_numbers_handles_none_and_empty_lists(mismatches, expected):
    # Arrange: no top-level line_numbers column present
    df = pl.DataFrame({"id": [1], "mismatches": [mismatches]})

    # Act
    out = hide_line_numbers(df)

    # Assert
    value = out["mismatches"].item()
    if expected is None:
        assert value is None
    else:
        if isinstance(value, pl.Series):
            assert value.len() == 0
            assert value.to_list() == expected
        else:
            assert value == expected
