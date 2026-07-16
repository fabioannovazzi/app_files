import polars as pl
import pytest
from polars.exceptions import ColumnNotFoundError
from polars.testing import assert_frame_equal

from src.attribute_merge_logic import (
    merge_attribute_results,
    propagate_attribute_results,
    try_merge_attribute_results,
)


def test_merge_attribute_results_basic_join_text_attrs():
    # Arrange
    df = pl.DataFrame({"SKU": ["A", "B"], "price": [10, 20]})
    scores = pl.DataFrame(
        {
            "sku": ["A", "B"],  # case-insensitive key
            "brand": ["Acme", None],  # eligible text attribute
            "rank": [1, 2],  # metric column, should be excluded
        }
    )
    classification = pl.DataFrame({"SKU": ["A", "B"], "category": ["Cat1", "Cat2"]})

    # Act
    out = merge_attribute_results(
        df, {"product_column": "SKU"}, scores=scores, classification=classification
    )

    # Assert: row count preserved, attributes merged, metrics excluded, nulls filled
    assert out.height == 2
    assert "Brand" in out.columns and "Category" in out.columns
    assert "rank" not in out.columns
    assert out.width == 4  # original 2 + 2 added attributes

    expected_attrs = pl.DataFrame(
        {"Brand": ["Acme", "N/A"], "Category": ["Cat1", "Cat2"]}
    )
    assert_frame_equal(out.select(["Brand", "Category"]), expected_attrs)


def test_merge_attribute_results_normalizes_attribute_names():
    # Arrange
    df = pl.DataFrame({"SKU": ["A"], "price": [10]})
    classification = pl.DataFrame(
        {
            "SKU": ["A"],
            "strong finish": ["matte"],
            "coverage": ["full"],
        }
    )

    # Act
    out = merge_attribute_results(
        df,
        {"product_column": "SKU"},
        classification=classification,
    )

    # Assert: attribute columns renamed to Title/underscore style
    assert "Strong_Finish" in out.columns
    assert "Coverage" in out.columns
    assert "strong finish" not in out.columns
    assert "coverage" not in out.columns
    attrs = out.select(["Strong_Finish", "Coverage"])
    expected = pl.DataFrame({"Strong_Finish": ["matte"], "Coverage": ["full"]})
    assert_frame_equal(attrs, expected)


def test_merge_attribute_results_normalizes_existing_columns():
    # Arrange
    df = pl.DataFrame({"SKU": ["A"], "coverage": ["Gloss"], "price": [10]})
    classification = pl.DataFrame({"SKU": ["A"], "coverage": ["Matte"]})

    # Act
    out = merge_attribute_results(
        df, {"product_column": "SKU"}, classification=classification
    )

    # Assert: existing coverage column renamed to normalised form and updated
    assert "Coverage" in out.columns
    assert "coverage" not in out.columns
    result = out.select(["Coverage"])
    expected = pl.DataFrame({"Coverage": ["Matte"]})
    assert_frame_equal(result, expected)


def test_merge_attribute_results_include_scores_cast_and_fill():
    # Arrange
    df = pl.DataFrame({"SKU": ["X", "Y"]})
    scores = pl.DataFrame({"SKU": ["X", "Y"], "quality_score": [90, None]})

    # Act
    out = merge_attribute_results(
        df, {"product_column": "SKU"}, scores=scores, include_scores=True
    )

    # Assert: score column included, cast to Utf8, nulls filled with "N/A"
    assert "Quality_Score" in out.columns
    assert out.schema["Quality_Score"] == pl.Utf8
    expected = pl.DataFrame({"Quality_Score": ["90", "N/A"]})
    assert_frame_equal(out.select(["Quality_Score"]), expected)


def test_merge_attribute_results_missing_product_column_raises():
    # Arrange
    df = pl.DataFrame({"product": ["A"], "price": [10]})

    # Act / Assert
    with pytest.raises(ColumnNotFoundError):
        merge_attribute_results(df, {"product_column": "SKU"})


def test_try_merge_attribute_results_empty_scores_raises_with_context():
    # Arrange
    df = pl.DataFrame({"SKU": ["A", "B"]})
    # Empty scores with correct schema
    scores = pl.DataFrame({"SKU": pl.Series([], dtype=pl.Utf8)})

    # Act / Assert
    with pytest.raises(ValueError) as exc:
        try_merge_attribute_results(
            df,
            {"product_column": "SKU"},
            scores=scores,
            classification=None,
            dataset_name="periods",
        )
    msg = str(exc.value)
    assert "periods:" in msg and "scores dataframe is empty" in msg


def test_propagate_attribute_results_merges_only_valid_inputs():
    # Arrange: only df_dates is valid; others are None
    df_dates = pl.DataFrame({"SKU": ["A"], "qty": [1]})
    scores = pl.DataFrame({"SKU": ["A"], "brand": ["Zed"]})

    # Act
    out_dates, out_periods, out_all_periods, out_plan = propagate_attribute_results(
        df_dates,
        None,
        None,
        None,
        {"product_column": "SKU"},
        scores=scores,
    )

    # Assert: only dates merged; others unchanged (None)
    assert out_periods is None and out_all_periods is None and out_plan is None
    expected_dates = pl.DataFrame({"SKU": ["A"], "qty": [1], "Brand": ["Zed"]})
    assert_frame_equal(out_dates.select(["SKU", "qty", "Brand"]), expected_dates)
