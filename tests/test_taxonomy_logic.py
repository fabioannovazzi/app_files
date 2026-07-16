from __future__ import annotations

import pytest


def _stub_taxonomy_basic():
    """Small deterministic taxonomy for tests.

    Structure (labels intentionally use mixed case):
    - Category: "Main"
      - Attribute: "Color"
        - Nodes: "Red" -> ["Crimson", "Scarlet"], "Blue"
    """

    return {
        "categories": [
            {
                "label": "Main",
                "attributes": [
                    {
                        "label": "Color",
                        "nodes": [
                            {
                                "label": "Red",
                                "children": [
                                    {"label": "Crimson"},
                                    {"label": "Scarlet"},
                                ],
                            },
                            {"label": "Blue"},
                        ],
                    }
                ],
            }
        ]
    }


def test_flatten_taxonomy_basic(monkeypatch):
    # Arrange
    from src.taxonomy_logic import flatten_taxonomy as _fn

    monkeypatch.setattr(
        "src.taxonomy_logic.get_attribute_taxonomy", lambda: _stub_taxonomy_basic()
    )

    # Act
    rows = _fn()

    # Assert: three leaf terms with lowercased labels and expected paths
    assert isinstance(rows, list) and len(rows) == 3
    paths = {row["path"] for row in rows}
    terms = {row["term"] for row in rows}
    assert paths == {"red > crimson", "red > scarlet", "blue"}
    assert terms == {"crimson", "scarlet", "blue"}
    # All rows share the same category/attribute, lowercased
    assert {row["category"] for row in rows} == {"main"}
    assert {row["attribute"] for row in rows} == {"color"}
    # Keys and value types are consistent
    for row in rows:
        assert set(row.keys()) == {"category", "attribute", "term", "path"}
        assert all(isinstance(v, str) for v in row.values())


@pytest.mark.parametrize("query,expected_paths", [
    ("scarl", {"red > scarlet"}),  # substring match
    ("main color blue", {"blue"}),  # match across category/attribute/term
])
def test_flatten_taxonomy_query_filters(monkeypatch, query, expected_paths):
    # Arrange
    from src.taxonomy_logic import flatten_taxonomy as _fn

    monkeypatch.setattr(
        "src.taxonomy_logic.get_attribute_taxonomy", lambda: _stub_taxonomy_basic()
    )

    # Act
    rows = _fn(query)

    # Assert
    assert {r["path"] for r in rows} == expected_paths


@pytest.mark.parametrize("query", [None, ""])  # empty string behaves like no filter
def test_flatten_taxonomy_query_none_or_empty_returns_all(monkeypatch, query):
    # Arrange
    from src.taxonomy_logic import flatten_taxonomy as _fn

    monkeypatch.setattr(
        "src.taxonomy_logic.get_attribute_taxonomy", lambda: _stub_taxonomy_basic()
    )

    # Act
    rows = _fn(query)

    # Assert
    assert len(rows) == 3


def test_flatten_taxonomy_handles_missing_and_non_string_labels(monkeypatch):
    # Arrange: category label missing, attribute label None, node label is int
    from src.taxonomy_logic import flatten_taxonomy as _fn

    taxonomy = {
        "categories": [
            {
                # missing category label -> empty string lowercased
                "attributes": [
                    {
                        "label": None,  # becomes "none"
                        "nodes": [
                            {"label": 123},  # becomes "123"
                        ],
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr("src.taxonomy_logic.get_attribute_taxonomy", lambda: taxonomy)

    # Act
    rows = _fn(query="no-match")  # negative filter returns empty list

    # Assert negative case first
    assert rows == []

    # Act again without filter to check normalization
    rows_all = _fn()
    assert len(rows_all) == 1
    row = rows_all[0]
    assert row["category"] == ""  # missing -> empty string
    assert row["attribute"] == "none"
    assert row["term"] == "123"
    assert row["path"] == "123"
