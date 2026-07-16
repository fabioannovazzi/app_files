import polars as pl
import pytest

from modules.data.common_data_utils import (
    build_equal_to_query_string_element,
    check_value_column_exist,
    get_query_string_from_dict,
)


def test_check_value_column_exist_filters_and_preserves_order_dataframe():
    # Arrange
    df = pl.DataFrame({"A": [1, 2], "B": [3, 4], "C": [5, 6]})
    requested = ["B", "X", "A"]

    # Act
    result = check_value_column_exist(df, requested)

    # Assert
    assert result == ["B", "A"]


def test_check_value_column_exist_with_lazyframe_and_no_matches():
    # Arrange
    df = pl.DataFrame({"A": [1], "B": [2]}).lazy()
    requested = ["X", "Y"]

    # Act
    result = check_value_column_exist(df, requested)

    # Assert
    assert result == []


@pytest.mark.parametrize(
    "col,value,expected",
    [
        ("category", "books", "category == 'books'"),
        ("name", "O'Reilly", "name == 'OReilly'"),  # strips single quotes
        ("id", 42, "id == '42'"),  # casts to string
    ],
)
def test_build_equal_to_query_string_element_cases(col, value, expected):
    # Act
    result = build_equal_to_query_string_element(col, value)

    # Assert
    assert result == expected


def test_get_query_string_from_dict_multiple_entries():
    # Arrange: insertion order matters for the output
    filters = {"col1": "foo", "col2": "bar"}

    # Act
    result = get_query_string_from_dict(filters)

    # Assert
    assert result == "col1 == 'foo' and col2 == 'bar'"


def test_get_query_string_from_dict_empty_returns_empty_string():
    # Act
    result = get_query_string_from_dict({})

    # Assert
    assert result == ""
