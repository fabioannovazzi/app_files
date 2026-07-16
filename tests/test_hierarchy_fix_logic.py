from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from src.hierarchy_fix_logic import (
    _build_chains,  # exercises the nested `dfs`
    order_hierarchy_pairs,
    resolve_hierarchies,
)


def test_build_chains_root_to_leaves_branching():
    # Arrange
    pairs = [("A", "B"), ("C", "B"), ("B", "D")]

    # Act
    chains = _build_chains(pairs)

    # Assert: returns root→leaf chains for both leaves
    assert chains == [["D", "B", "A"], ["D", "B", "C"]]


def test_build_chains_cycle_returns_empty():
    # Arrange: simple 2-node cycle has no root→leaf chains
    pairs = [("A", "B"), ("B", "A")]

    # Act
    chains = _build_chains(pairs)

    # Assert
    assert chains == []


def test_order_hierarchy_pairs_orders_leaves_before_parents_and_dedups():
    # Arrange: include duplicates; leaves (A,C) should come before (B,D)
    pairs = [("A", "B"), ("C", "B"), ("B", "D"), ("A", "B"), ("B", "D")]

    # Act
    ordered = order_hierarchy_pairs(pairs)

    # Assert: unique pairs preserved and leaf→parent ordering honored
    expected_set = {("A", "B"), ("C", "B"), ("B", "D")}
    assert set(ordered) == expected_set
    idx = {p: i for i, p in enumerate(ordered)}
    assert idx[("B", "D")] > idx[("A", "B")]
    assert idx[("B", "D")] > idx[("C", "B")]


def test_order_hierarchy_pairs_empty():
    # Act / Assert
    assert order_hierarchy_pairs([]) == []


def test_resolve_hierarchies_unifies_parents_with_weights_and_returns_params():
    # Arrange: counts tie for A; weight breaks tie to X. For B, tie broken lexicographically to W.
    df = pl.DataFrame(
        {
            "child": ["A", "A", "B", "B", "B", "B"],
            "parent": ["X", "Y", "W", "W", "Z", "Z"],
            "weight": [10, 1, 1, 1, 1, 1],
        }
    )
    pairs = [("child", "parent")]
    params = {"keep": "me"}

    # Act
    result, out_params = resolve_hierarchies(
        df, pairs, weight_col="weight", ambiguous_pct=100, param_dict=params
    )

    # Assert: all rows for A→X, B→W; params passed through unchanged
    expected = pl.DataFrame(
        {
            "child": ["A", "A", "B", "B", "B", "B"],
            "parent": ["X", "X", "W", "W", "W", "W"],
            "weight": [10, 1, 1, 1, 1, 1],
        }
    )
    assert_frame_equal(result, expected)
    assert out_params == params


def test_resolve_hierarchies_ambiguous_children_placeholder_applied():
    # Arrange: A is ambiguous (two parents), B is not. Placeholder should replace A's parent.
    df = pl.DataFrame({"child": ["A", "A", "B"], "parent": ["X", "Y", "Z"]})
    pairs = [("child", "parent")]

    # Act
    result, _ = resolve_hierarchies(
        df, pairs, weight_col=None, ambiguous_pct=0, param_dict={}, ambiguous_placeholder="AMBIG"
    )

    # Assert: ambiguous A rows replaced with placeholder; B preserved
    expected = pl.DataFrame({"child": ["A", "A", "B"], "parent": ["AMBIG", "AMBIG", "Z"]})
    assert_frame_equal(result, expected)
