from __future__ import annotations

import pytest

from modules.add_attributes.taxonomy_schema import validate_branch


def test_validate_branch_preserves_leaf_governance_fields() -> None:
    # Arrange
    branch = {
        "id": "face_primer",
        "label": "Face primer",
        "attributes": [
            {
                "id": "form",
                "label": "Format",
                "hierarchical": False,
                "levels": 1,
                "nodes": [
                    {
                        "id": "oil",
                        "label": "Oil",
                        "status": "needs_review",
                        "governance_action": "merge",
                        "successor_leaf_ids": ["liquid"],
                        "governance_reason": "Possible subtype of liquid.",
                    },
                    {"id": "liquid", "label": "Liquid"},
                ],
            }
        ],
    }

    # Act
    normalized, _warnings = validate_branch(branch)

    # Assert
    nodes = normalized["attributes"][0]["nodes"]
    oil_node = next(node for node in nodes if node["id"] == "oil")
    assert oil_node["status"] == "needs_review"
    assert oil_node["governance_action"] == "merge"
    assert oil_node["successor_leaf_ids"] == ["liquid"]
    assert oil_node["governance_reason"] == "Possible subtype of liquid"


def test_validate_branch_rejects_parent_governance_fields() -> None:
    # Arrange
    branch = {
        "id": "concealer",
        "label": "Concealer",
        "attributes": [
            {
                "id": "form",
                "label": "Format",
                "hierarchical": True,
                "levels": 2,
                "nodes": [
                    {
                        "id": "liquid",
                        "label": "Liquid",
                        "status": "active",
                        "children": [{"id": "tube", "label": "Tube"}],
                    }
                ],
            }
        ],
    }

    # Act / Assert
    with pytest.raises(ValueError, match="parent node must not carry status"):
        validate_branch(branch)


def test_validate_branch_rejects_unknown_successor_leaf_id() -> None:
    # Arrange
    branch = {
        "id": "face_primer",
        "label": "Face primer",
        "attributes": [
            {
                "id": "form",
                "label": "Format",
                "hierarchical": False,
                "levels": 1,
                "nodes": [
                    {
                        "id": "oil",
                        "label": "Oil",
                        "status": "deprecated",
                        "governance_action": "merge",
                        "successor_leaf_ids": ["liquid"],
                    }
                ],
            }
        ],
    }

    # Act / Assert
    with pytest.raises(ValueError, match="successor_leaf_ids must point to existing leaves"):
        validate_branch(branch)


def test_validate_branch_allows_split_for_multi_select_attribute() -> None:
    branch = {
        "id": "lipstick",
        "label": "Lipstick",
        "attributes": [
            {
                "id": "finish",
                "label": "Finish",
                "hierarchical": False,
                "levels": 1,
                "selection": "multi",
                "nodes": [
                    {
                        "id": "matte_dewy",
                        "label": "Matte Dewy",
                        "status": "deprecated",
                        "governance_action": "split",
                        "successor_leaf_ids": ["matte", "dewy"],
                    },
                    {"id": "matte", "label": "Matte"},
                    {"id": "dewy", "label": "Dewy"},
                ],
            }
        ],
    }

    normalized, _warnings = validate_branch(branch)

    matte_dewy = normalized["attributes"][0]["nodes"][0]
    assert matte_dewy["governance_action"] == "split"
    assert matte_dewy["successor_leaf_ids"] == ["matte", "dewy"]


def test_validate_branch_rejects_split_for_single_select_attribute() -> None:
    branch = {
        "id": "lipstick",
        "label": "Lipstick",
        "attributes": [
            {
                "id": "finish",
                "label": "Finish",
                "hierarchical": False,
                "levels": 1,
                "selection": "single",
                "nodes": [
                    {
                        "id": "matte_dewy",
                        "label": "Matte Dewy",
                        "status": "deprecated",
                        "governance_action": "split",
                        "successor_leaf_ids": ["matte", "dewy"],
                    },
                    {"id": "matte", "label": "Matte"},
                    {"id": "dewy", "label": "Dewy"},
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match="requires selection='multi'"):
        validate_branch(branch)


def test_validate_branch_drops_cross_attribute_duplicate_synonyms() -> None:
    branch = {
        "id": "face_primer",
        "label": "Face primer",
        "attributes": [
            {
                "id": "form",
                "label": "Format",
                "hierarchical": False,
                "levels": 1,
                "nodes": [
                    {"id": "oil", "label": "Oil", "synonyms": ["oil based"]},
                ],
            },
            {
                "id": "base_type",
                "label": "Base type",
                "hierarchical": False,
                "levels": 1,
                "nodes": [
                    {
                        "id": "oil_based",
                        "label": "Oil-based",
                        "synonyms": ["oil based", "emollient base"],
                    }
                ],
            },
        ],
    }

    normalized, warnings = validate_branch(branch)

    format_node = normalized["attributes"][0]["nodes"][0]
    base_type_node = normalized["attributes"][1]["nodes"][0]
    assert "synonyms" not in format_node
    assert base_type_node["synonyms"] == ["emollient base", "oil based"]
    assert any("dropping cross-attribute synonym 'oil based'" in warning for warning in warnings)


def test_validate_branch_warns_on_cross_attribute_single_token_labels() -> None:
    branch = {
        "id": "lipstick",
        "label": "Lipstick",
        "attributes": [
            {
                "id": "finish",
                "label": "Finish",
                "hierarchical": False,
                "levels": 1,
                "nodes": [
                    {"id": "sheer", "label": "Sheer"},
                ],
            },
            {
                "id": "coverage",
                "label": "Coverage",
                "hierarchical": False,
                "levels": 1,
                "nodes": [
                    {"id": "sheer", "label": "Sheer"},
                ],
            },
        ],
    }

    _normalized, warnings = validate_branch(branch)

    assert any(
        "ambiguous single-token label 'sheer' appears across attributes" in warning
        for warning in warnings
    )
