import pytest
import polars as pl

from modules.charting import chart_primitives as cp
from modules.charting.chart_primitives import (
    get_hashed_key,
    get_unique_categories,
    preparare_parameters_for_each_variance_calculation,
)


@pytest.mark.parametrize(
    "key,column_hash,expected",
    [
        ("base", "abc", "base_abc"),
        ("id", 123, "id_123"),  # non‑string hash coerced to str
        ("plain", None, "plain"),
        ("plain", "", "plain"),
        ("zero", 0, "zero"),  # falsy => unchanged
    ],
)
def test_get_hashed_key_variants(key, column_hash, expected):
    # Act
    result = get_hashed_key(key, column_hash)

    # Assert
    assert result == expected


def test_get_unique_categories_first_column_unique_values():
    # Arrange: duplicates and nulls; expect order of first appearance, nulls dropped
    df = pl.DataFrame({
        "cat": ["a", "b", "a", None, "c", "b", None],
        "val": [1, 2, 3, 4, 5, 6, 7],
    })

    # Act
    cats = get_unique_categories(df)

    # Assert
    assert cats == ["a", "b", "c"]


def test_preparare_parameters_for_each_variance_calculation_monkeypatched(monkeypatch):
    # Arrange: stub config and color helper to make behaviour deterministic
    naming = {
        "varianceAggregation": "varianceAggKey",
        "runOneDimensionalAnalysis": "RUN_ONE_DIM",
    }
    monkeypatch.setattr(cp, "get_naming_params", lambda: naming)
    fake_colors = {"some": "#000"}
    monkeypatch.setattr(cp, "get_color_dictionary", lambda d: fake_colors)

    chart_dict = {"existing": 1}
    element = "sum"

    # Act
    out_dict, out_colors, message = preparare_parameters_for_each_variance_calculation(
        chart_dict, element
    )

    # Assert
    assert out_dict is chart_dict  # in‑place update
    assert out_dict["varianceAggKey"] == element
    assert out_colors == fake_colors
    assert message == "RUN_ONE_DIM"
