from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

# Import the public functions under test
from src.attribute_excel_logic import (
    merge_attributes_from_excel,
    merge_or_classify_attributes_from_excel,
    shared_columns,
)


def test_shared_columns_intersection_sorted(monkeypatch):
    # Arrange
    df = pl.DataFrame({
        "Line": ["A1"],
        "Category": ["shoes"],
        "Color": ["red"],
    })

    excel_df = pl.DataFrame({
        "Line": ["B2"],
        "Category": ["bags"],
        "Size": ["M"],
        "Color": ["blue"],
    })

    monkeypatch.setattr(
        "src.attribute_excel_logic._read_excel", lambda _file: excel_df
    )

    # Act
    cols = shared_columns(df, b"ignored")

    # Assert
    assert cols == ["Category", "Color", "Line"]


def test_merge_attributes_from_excel_merges_and_renames(monkeypatch):
    # Arrange
    base_df = pl.DataFrame(
        {
            "Line": ["A1", "B2", "C3", "D4"],
            "Category": ["shoes", "shoes", "shoes", "bags"],
        }
    )

    # Excel has attribute columns with mixed case; one row lacks a value
    excel_df = pl.DataFrame(
        {
            "Line": ["A1", "B2", "C3", "D4"],
            "Category": ["shoes", "shoes", "shoes", "bags"],
            "color": ["red", "blue", None, "green"],
            "Material": ["leather", None, "rubber", "canvas"],
        }
    )

    # Allowed leaves only for 'shoes'; case-insensitive mapping should rename
    monkeypatch.setattr(
        "src.attribute_excel_logic._allowed_leaves",
        lambda cat: {"Color", "Material"} if str(cat).lower() == "shoes" else set(),
    )
    monkeypatch.setattr(
        "src.attribute_excel_logic._read_excel", lambda _file: excel_df
    )

    # Act
    out = merge_attributes_from_excel(
        base_df, b"ignored", product_col="Line", category_col="Category"
    )

    # Assert shape and values; join should not change row count
    assert isinstance(out, pl.DataFrame)
    assert out.height == base_df.height
    assert set(["Color", "Material"]).issubset(set(out.columns))

    # Compare deterministic subset sorted by Line
    result = out.select(["Line", "Color", "Material"]).sort("Line")
    expected = pl.DataFrame(
        {
            "Line": ["A1", "B2", "C3", "D4"],
            "Color": ["red", "blue", "N/A", "N/A"],
            "Material": ["leather", "N/A", "rubber", "N/A"],
        }
    )
    expected = expected.sort("Line")
    assert_frame_equal(result, expected, check_row_order=True)


def test_merge_attributes_from_excel_returns_original_when_no_allowed(monkeypatch):
    # Arrange
    base_df = pl.DataFrame({"Line": ["A1", "B2"], "Category": ["x", "y"]})
    excel_df = pl.DataFrame(
        {"Line": ["A1", "B2"], "Category": ["x", "y"], "Color": ["r", "b"]}
    )
    monkeypatch.setattr("src.attribute_excel_logic._read_excel", lambda _f: excel_df)
    # No categories have allowed leaves
    monkeypatch.setattr(
        "src.attribute_excel_logic._allowed_leaves", lambda _cat: set()
    )

    # Act
    out = merge_attributes_from_excel(
        base_df, b"ignored", product_col="Line", category_col="Category"
    )

    # Assert: returns the original object unchanged, no new columns
    assert out is base_df
    assert out.columns == base_df.columns


def test_merge_attributes_from_excel_debug_info(monkeypatch):
    base_df = pl.DataFrame({"Line": ["A1"], "Category": ["shoes"]})
    excel_df = pl.DataFrame(
        {
            "Line": ["A1"],
            "Category": ["shoes"],
            "Color": ["red"],
        }
    )
    monkeypatch.setattr("src.attribute_excel_logic._read_excel", lambda _f: excel_df)
    monkeypatch.setattr(
        "src.attribute_excel_logic._allowed_leaves",
        lambda cat: {"Color", "Material"} if cat == "shoes" else set(),
    )

    out, diagnostics = merge_attributes_from_excel(
        base_df,
        b"ignored",
        product_col="Line",
        category_col="Category",
        return_debug=True,
    )

    assert isinstance(out, pl.DataFrame)
    assert "Color" in diagnostics["matched_columns"]
    assert diagnostics["allowed_leaves_by_category"]["shoes"] == ["Color", "Material"]
    assert diagnostics["merged_columns"] == ["Color"]
    assert diagnostics["numeric_columns_skipped"] == []
    assert diagnostics["duplicate_products"] == []
    assert diagnostics["row_count_changed"] is False
    assert diagnostics["original_row_count"] == base_df.height
    assert diagnostics["joined_row_count"] == base_df.height


def test_merge_attributes_from_excel_without_taxonomy(monkeypatch):
    base_df = pl.DataFrame({
        "Line": ["A1"],
        "Segment": ["premium"],
    })
    excel_df = pl.DataFrame(
        {
            "Line": ["A1"],
            "Segment": ["premium"],
            "Shade": ["red"],
            "Finish": ["matte"],
        }
    )

    monkeypatch.setattr("src.attribute_excel_logic._read_excel", lambda _f: excel_df)

    out, diagnostics = merge_attributes_from_excel(
        base_df,
        b"ignored",
        product_col="Line",
        category_col="Segment",
        return_debug=True,
        enforce_taxonomy=False,
        exclude_numeric=True,
    )

    assert isinstance(out, pl.DataFrame)
    assert set(["Shade", "Finish"]).issubset(set(out.columns))
    assert diagnostics["enforce_taxonomy"] is False
    assert set(diagnostics["matched_columns"]) == {"Shade", "Finish"}
    assert diagnostics["merged_columns"] == ["Finish", "Shade"]
    assert diagnostics["numeric_columns_skipped"] == []
    assert diagnostics["duplicate_products"] == []
    assert diagnostics["row_count_changed"] is False
    assert diagnostics["original_row_count"] == base_df.height
    assert diagnostics["joined_row_count"] == base_df.height


def test_merge_attributes_from_excel_excludes_numeric(monkeypatch):
    base_df = pl.DataFrame({
        "Line": ["A1"],
        "Segment": ["premium"],
        "Price": [5.0],
    })
    excel_df = pl.DataFrame(
        {
            "Line": ["A1"],
            "Segment": ["premium"],
            "Price": [10.0],
            "total_amount": [100.0],
            "Shade": ["red"],
        }
    )

    monkeypatch.setattr("src.attribute_excel_logic._read_excel", lambda _f: excel_df)

    out, diagnostics = merge_attributes_from_excel(
        base_df,
        b"ignored",
        product_col="Line",
        category_col="Segment",
        return_debug=True,
        enforce_taxonomy=False,
        exclude_numeric=True,
    )

    assert isinstance(out, pl.DataFrame)
    assert "Shade" in out.columns
    assert "Price" in out.columns
    assert out.get_column("Price").to_list() == [5.0]
    assert "total_amount" not in diagnostics["matched_columns"]
    assert "Price" not in diagnostics["matched_columns"]
    assert diagnostics["merged_columns"] == ["Shade"]
    assert diagnostics["numeric_columns_skipped"] == ["Price", "total_amount"]
    assert diagnostics["duplicate_products"] == []
    assert diagnostics["row_count_changed"] is False
    assert diagnostics["original_row_count"] == base_df.height
    assert diagnostics["joined_row_count"] == base_df.height


def test_merge_attributes_from_excel_allows_numeric_when_not_excluded(monkeypatch):
    base_df = pl.DataFrame(
        {
            "Line": ["A1", "B2"],
            "Category": ["shoes", "shoes"],
            "Weight": [5.0, 7.5],
        }
    )

    excel_df = pl.DataFrame(
        {
            "Line": ["A1", "B2"],
            "Category": ["shoes", "shoes"],
            "Weight": [10.0, None],
            "Size": [42, 38],
        }
    )

    monkeypatch.setattr("src.attribute_excel_logic._read_excel", lambda _f: excel_df)
    monkeypatch.setattr(
        "src.attribute_excel_logic._allowed_leaves",
        lambda cat: {"Weight", "Size"} if cat == "shoes" else set(),
    )

    out = merge_attributes_from_excel(
        base_df,
        b"ignored",
        product_col="Line",
        category_col="Category",
        enforce_taxonomy=True,
        exclude_numeric=False,
    )

    result = out.select(["Line", "Weight", "Size"]).sort("Line")
    expected = pl.DataFrame(
        {
            "Line": ["A1", "B2"],
            "Weight": [10.0, 7.5],
            "Size": [42, 38],
        }
    ).sort("Line")

    assert_frame_equal(result, expected, check_row_order=True)


def test_merge_attributes_from_excel_case_insensitive_replacement(monkeypatch):
    base_df = pl.DataFrame({
        "Line": ["A1"],
        "Category": ["shoes"],
        "Coverage": ["medium"],
    })
    excel_df = pl.DataFrame(
        {
            "Line": ["A1"],
            "Category": ["shoes"],
            "coverage": ["full"],
        }
    )

    monkeypatch.setattr("src.attribute_excel_logic._read_excel", lambda _f: excel_df)
    monkeypatch.setattr(
        "src.attribute_excel_logic._allowed_leaves",
        lambda cat: {"Coverage"} if cat == "shoes" else set(),
    )

    out, diagnostics = merge_attributes_from_excel(
        base_df,
        b"ignored",
        product_col="Line",
        category_col="Category",
        return_debug=True,
    )

    assert isinstance(out, pl.DataFrame)
    assert "Coverage" in out.columns
    assert out.get_column("Coverage").to_list() == ["full"]
    assert "coverage" not in out.columns
    assert diagnostics["merged_columns"] == ["Coverage"]


def test_merge_attributes_from_excel_missing_excel_column_raises(monkeypatch):
    # Arrange: Excel missing the product column
    base_df = pl.DataFrame({"Line": ["A1"], "Category": ["shoes"]})
    excel_df = pl.DataFrame({"Category": ["shoes"], "Color": ["red"]})
    monkeypatch.setattr("src.attribute_excel_logic._read_excel", lambda _f: excel_df)

    # Act / Assert
    with pytest.raises(KeyError) as exc:
        merge_attributes_from_excel(
            base_df, b"ignored", product_col="Line", category_col="Category"
        )
    msg = str(exc.value)
    assert "not found in Excel file" in msg and "'Line'" in msg


def test_merge_or_classify_attributes_from_excel_uses_merge_path(monkeypatch):
    # Arrange: Excel already contains allowed attribute columns
    base_df = pl.DataFrame({
        "Line": ["A1", "B2"],
        "Category": ["shoes", "shoes"],
    })
    excel_df = pl.DataFrame({
        "Line": ["A1", "B2"],
        "Category": ["shoes", "shoes"],
        "Color": ["red", "blue"],
    })
    monkeypatch.setattr(
        "src.attribute_excel_logic._read_excel", lambda _file: excel_df
    )
    # Allowed attribute IDs for the provided category
    monkeypatch.setattr(
        "src.attribute_excel_logic._allowed_attributes", lambda _cat: {"Color"}
    )
    monkeypatch.setattr(
        "src.attribute_excel_logic._allowed_leaves",
        lambda cat: {"Color"} if str(cat).lower() == "shoes" else set(),
    )

    # Act
    out = merge_or_classify_attributes_from_excel(
        base_df, b"ignored", category="shoes", line_col="Line"
    )

    # Assert: merged column present with expected values
    assert isinstance(out, pl.DataFrame)
    result = out.select(["Line", "Color"]).sort("Line")
    expected = pl.DataFrame({"Line": ["A1", "B2"], "Color": ["red", "blue"]})
    expected = expected.sort("Line")
    assert_frame_equal(result, expected, check_row_order=True)


def test_merge_or_classify_attributes_from_excel_classifies_when_no_attrs(monkeypatch):
    # Arrange: Excel lacks attribute columns, triggers classification path
    base_df = pl.DataFrame({"Line": ["A1", "B2"]})
    excel_df = pl.DataFrame({"Line": ["A1", "B2"], "Category": ["shoes", "shoes"]})
    monkeypatch.setattr(
        "src.attribute_excel_logic._read_excel", lambda _file: excel_df
    )
    monkeypatch.setattr(
        "src.attribute_excel_logic._allowed_attributes", lambda _cat: {"Material"}
    )

    def fake_classify(_llm, df, product_col, products, attr_map, group_col=None):
        # Return a minimal classification table for the listed products
        return pl.DataFrame(
            {
                product_col: list(products),
                "Material": ["leather", "suede"],
            }
        )

    # Act
    out = merge_or_classify_attributes_from_excel(
        base_df,
        b"ignored",
        category="shoes",
        line_col="Line",
        classify_fn=fake_classify,
        llm_wrapper=None,
    )

    # Assert
    assert isinstance(out, pl.DataFrame)
    result = out.select(["Line", "Material"]).sort("Line")
    expected = pl.DataFrame({"Line": ["A1", "B2"], "Material": ["leather", "suede"]})
    expected = expected.sort("Line")
    assert_frame_equal(result, expected, check_row_order=True)
