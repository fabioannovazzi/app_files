from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from polars.exceptions import ColumnNotFoundError

from modules.add_attributes.attribute_impact_analysis import (
    merge_scores_with_metrics,
)
from modules.utilities.utils import get_row_count


def test_merge_scores_with_metrics_renames_and_inner_joins():
    # Arrange
    scores_df = pl.DataFrame({"Product": ["A", "B"], "Score": [0.1, 0.2]})
    metrics_df = pl.DataFrame(
        {
            "Product": ["A", "B", "C"],
            "total_amount": [100, 200, 300],
            "total_units": [10, 20, 30],
            "average_price": [10.0, 10.0, 10.0],
        }
    )

    # Act
    out = merge_scores_with_metrics(scores_df, metrics_df)

    # Assert: inner join keeps only A,B and renames metrics columns
    expected = pl.DataFrame(
        {
            "Product": ["A", "B"],
            "Score": [0.1, 0.2],
            "Sales": [100, 200],
            "Units": [10, 20],
            "Price": [10.0, 10.0],
        }
    )
    assert_frame_equal(out.sort("Product"), expected.sort("Product"))


def test_merge_scores_with_metrics_empty_join_preserves_renamed_schema():
    # Arrange: no overlapping products -> empty result after inner join
    scores_df = pl.DataFrame({"Product": ["X"], "Score": [1.0]})
    metrics_df = pl.DataFrame(
        {
            "Product": ["A"],
            "total_amount": [0],
            "total_units": [0],
            "average_price": [0.0],
        }
    )

    # Act
    out = merge_scores_with_metrics(scores_df, metrics_df)

    # Assert: no rows but renamed columns are present
    assert get_row_count(out) == 0
    assert out.columns == ["Product", "Score", "Sales", "Units", "Price"]


def test_merge_scores_with_metrics_missing_join_key_raises():
    # Arrange: metrics missing the join key 'Product'
    scores_df = pl.DataFrame({"Product": ["A"], "Score": [0.1]})
    metrics_df = pl.DataFrame({"total_amount": [100]})

    # Act / Assert
    with pytest.raises(ColumnNotFoundError):
        merge_scores_with_metrics(scores_df, metrics_df)


def test_merge_scores_with_metrics_custom_on_and_partial_rename():
    # Arrange: join on custom key and only one known metric present
    scores_df = pl.DataFrame({"SKU": ["S1", "S2"], "Score": [0.3, 0.4]})
    metrics_df = pl.DataFrame({"SKU": ["S1", "S2"], "total_units": [5, 6]})

    # Act
    out = merge_scores_with_metrics(scores_df, metrics_df, on="SKU")

    # Assert: only 'total_units' is renamed to 'Units'; custom key retained
    expected = pl.DataFrame({"SKU": ["S1", "S2"], "Score": [0.3, 0.4], "Units": [5, 6]})
    assert_frame_equal(out.sort("SKU"), expected.sort("SKU"))
