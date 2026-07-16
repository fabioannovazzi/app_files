from __future__ import annotations

import polars as pl
import pytest
from polars.exceptions import ColumnNotFoundError
from polars.testing import assert_frame_equal

from modules.add_attributes.attribute_product_insight import (
    group_stats_and_tests,
    train_decision_tree,
)


def _sort_df(df: pl.DataFrame, by: str) -> pl.DataFrame:
    """Helper to sort a Polars DataFrame deterministically by one column."""

    return df.sort(by)


def test_group_stats_and_tests_golden_path_stats_anova_chi2():
    # Arrange: two groups with varying metrics; boolean top flag for chi-square
    df = pl.DataFrame(
        {
            "Category": ["A", "A", "A", "B", "B", "B"],
            "Sales": [10, 20, 30, 5, 15, 25],
            # Within-group variance present; different group means (1.0 vs 2.0)
            "Price": [1.0, 1.1, 0.9, 2.0, 2.1, 1.9],
            "Top": [True, False, True, False, True, False],
        }
    )

    # Act
    res = group_stats_and_tests(df, "Category", ["Sales", "Price"], top_flag_col="Top")

    # Assert: stats shape and aggregates
    stats_df = _sort_df(res["stats"], "Category")
    expected_counts = pl.Series("count", [3, 3])
    assert stats_df.height == 2
    assert stats_df["count"].to_list() == expected_counts.to_list()
    # Means per group
    assert pytest.approx(stats_df["mean_sales"][0]) == 20.0  # A
    assert pytest.approx(stats_df["mean_sales"][1]) == 15.0  # B
    assert pytest.approx(stats_df["mean_price"][0]) == 1.0   # A
    assert pytest.approx(stats_df["mean_price"][1]) == 2.0   # B

    # Assert: ANOVA computed for both metrics with valid p-values
    anova = res["anova"]
    assert set(anova.keys()) == {"Sales", "Price"}
    assert 0.0 <= anova["Sales"]["p"] <= 1.0
    assert 0.0 <= anova["Price"]["p"] <= 1.0

    # Assert: Chi-square structure and expected table schema
    chi2 = res["chi2"]
    assert chi2 is not None
    # Rebuild contingency to validate degrees of freedom and expected schema
    cont = (
        df.group_by(["Category", "Top"])  # columns become 'true'/'false'
        .agg(pl.len().alias("count"))
        .pivot("Top", index="Category", values="count")
        .fill_null(0)
    )
    observed = cont.drop("Category").to_numpy()
    rows, cols = observed.shape
    assert chi2["dof"] == (rows - 1) * (cols - 1)
    expected_df = chi2["expected"]
    assert isinstance(expected_df, pl.DataFrame)
    # Same shape and column names as the pivoted contingency (without index col)
    assert expected_df.shape == cont.drop("Category").shape
    assert set(expected_df.columns) == set(cont.drop("Category").columns)


def test_group_stats_and_tests_missing_metric_and_single_group():
    # Arrange: only one attribute group; include a metric not in the DataFrame
    df = pl.DataFrame({"Category": ["A", "A"], "Sales": [1, 3]})

    # Act
    res = group_stats_and_tests(df, "Category", ["Sales", "Units"])  # Units missing

    # Assert: no ANOVA with a single group; missing metric is ignored
    assert res["anova"] == {}
    stats_cols = set(res["stats"].columns)
    assert "mean_sales" in stats_cols
    assert "mean_units" not in stats_cols
    assert res["chi2"] is None


def test_train_decision_tree_importances_sum_and_keys():
    # Arrange
    df = pl.DataFrame(
        {
            "x1": [0.1, 0.2, 0.8, 0.9, 0.4, 0.6],
            "x2": [1, 2, 1, 2, 2, 1],
            "y": [0, 0, 1, 1, 0, 1],
        }
    )

    # Act
    clf, importances = train_decision_tree(
        df, ["x1", "x2"], "y", max_depth=3, random_state=0
    )

    # Assert
    from sklearn.tree import DecisionTreeClassifier as _DTC  # local import for type check

    assert isinstance(clf, _DTC)
    assert set(importances.keys()) == {"x1", "x2"}
    assert pytest.approx(sum(importances.values())) == 1.0


def test_train_decision_tree_constant_feature_zero_importance():
    # Arrange: x2 is constant, so it should get zero importance
    df = pl.DataFrame(
        {
            "x1": [0, 1, 0, 1, 0, 1],
            "x2": [5, 5, 5, 5, 5, 5],  # constant
            "y": [0, 1, 0, 1, 0, 1],
        }
    )

    # Act
    _, importances = train_decision_tree(df, ["x1", "x2"], "y", random_state=0)

    # Assert
    assert importances["x2"] == 0.0
    assert importances["x1"] >= 0.0


def test_train_decision_tree_missing_feature_raises():
    # Arrange
    df = pl.DataFrame({"x1": [0, 1], "y": [0, 1]})

    # Act / Assert
    with pytest.raises(ColumnNotFoundError):
        train_decision_tree(df, ["x1", "missing"], "y")
