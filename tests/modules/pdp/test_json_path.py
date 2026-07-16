from __future__ import annotations

import pytest

from modules.pdp.json_path import extract_all_non_empty, extract_first_non_null, extract_values


def test_extract_values_handles_nested_lists() -> None:
    payload = {
        "product": {
            "variants": [
                {"sku": "sku1", "name": "Shade 1"},
                {"sku": "sku2", "name": "Shade 2"},
            ]
        }
    }

    values = extract_values(payload, "$.product.variants[*].sku")
    assert values == ("sku1", "sku2")


def test_extract_first_non_null_returns_first_match() -> None:
    payload = {"a": {"b": None}, "c": {"d": "value"}}
    result = extract_first_non_null(payload, ("$.a.b", "$.c.d"))
    assert result == "value"


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("$.breadcrumb[*].name", ("Level 1", "Level 2")),
        ("$.product.name", ("Lipstick",)),
    ],
)
def test_extract_all_non_empty(expression: str, expected: tuple[str, ...]) -> None:
    payload = {
        "breadcrumb": [{"name": "Level 1"}, {"name": "Level 2"}],
        "product": {"name": "Lipstick"},
    }
    result = extract_all_non_empty(payload, (expression,))
    assert result == expected
