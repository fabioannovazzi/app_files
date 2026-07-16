from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from modules.add_attributes.explicit_declaration_classifier import (
    DEFAULT_ACTIVATION_DEFAULTS,
    classify_explicit_declarations,
    classify_explicit_declarations_with_evidence,
    load_explicit_declaration_rules,
    validate_explicit_declaration_rules,
)


def _taxonomy() -> dict:
    return {
        "categories": [
            {
                "id": "lipstick",
                "label": "Lipstick",
                "attributes": [
                    {
                        "id": "finish",
                        "label": "Finish",
                        "nodes": [
                            {"id": "matte", "label": "matte"},
                            {"id": "satin", "label": "satin"},
                        ],
                    }
                ],
            }
        ]
    }


def _rules_for_finish() -> dict:
    return {
        "version": "1.0.0",
        "updated_at": "2026-03-04T00:00:00Z",
        "categories": {
            "lipstick": {
                "attributes": {
                    "finish": {
                        "values": {
                            "matte": {
                                "certainty_signals": [
                                    {
                                        "rule_id": "lipstick.finish.matte.1",
                                        "type": "phrase",
                                        "pattern": "matte finish",
                                        "reviewed_samples": 50,
                                        "observed_precision": 1.0,
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        },
        "metadata": {"owner": "test"},
    }


def test_classify_explicit_declarations_phrase_match() -> None:
    df = pl.DataFrame(
        [
            {
                "product_name": "Sample Matte Lipstick",
                "category_key": "lipstick",
                "description": "This lipstick delivers a matte finish all day.",
            }
        ]
    )

    result = classify_explicit_declarations(
        df,
        key_columns=["product_name", "category_key"],
        category_column="category_key",
        text_columns=["description"],
        attr_map={"lipstick": ["finish"]},
        taxonomy=_taxonomy(),
        rules=_rules_for_finish(),
    )

    assert result.height == 1
    assert result.row(0, named=True)["finish"] == "matte"


def test_classify_explicit_declarations_requires_configured_phrase() -> None:
    df = pl.DataFrame(
        [
            {
                "product_name": "Sample Matte Lipstick",
                "category_key": "lipstick",
                "description": "A matte lipstick for daily wear.",
            }
        ]
    )

    result = classify_explicit_declarations(
        df,
        key_columns=["product_name", "category_key"],
        category_column="category_key",
        text_columns=["description"],
        attr_map={"lipstick": ["finish"]},
        taxonomy=_taxonomy(),
        rules=_rules_for_finish(),
    )

    assert result.height == 1
    assert result.row(0, named=True)["finish"] == "N/A"


def test_classify_explicit_declarations_conflict_returns_na() -> None:
    rules = _rules_for_finish()
    rules["categories"]["lipstick"]["attributes"]["finish"]["values"]["satin"] = {
        "certainty_signals": [
            {
                "rule_id": "lipstick.finish.satin.1",
                "type": "phrase",
                "pattern": "satin finish",
                "reviewed_samples": 50,
                "observed_precision": 1.0,
            }
        ]
    }
    df = pl.DataFrame(
        [
            {
                "product_name": "Sample Lipstick",
                "category_key": "lipstick",
                "description": "Features both matte finish and satin finish claims.",
            }
        ]
    )

    result = classify_explicit_declarations(
        df,
        key_columns=["product_name", "category_key"],
        category_column="category_key",
        text_columns=["description"],
        attr_map={"lipstick": ["finish"]},
        taxonomy=_taxonomy(),
        rules=rules,
    )

    assert result.height == 1
    assert result.row(0, named=True)["finish"] == "N/A"


def test_validate_explicit_declaration_rules_rejects_unknown_value() -> None:
    rules = _rules_for_finish()
    rules["categories"]["lipstick"]["attributes"]["finish"]["values"] = {
        "velvet": {
            "certainty_signals": [
                {
                    "rule_id": "lipstick.finish.velvet.1",
                    "type": "phrase",
                    "pattern": "velvet finish",
                    "reviewed_samples": 50,
                    "observed_precision": 1.0,
                }
            ]
        }
    }

    with pytest.raises(ValueError, match="Unknown canonical value"):
        validate_explicit_declaration_rules(rules, _taxonomy())


def test_load_explicit_rules_applies_activation_defaults(tmp_path: Path) -> None:
    rules_path = tmp_path / "explicit_rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "updated_at": "2026-03-05T00:00:00Z",
                "categories": {},
                "metadata": {"owner": "test"},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_explicit_declaration_rules(rules_path)
    activation_defaults = loaded["metadata"]["activation_defaults"]

    assert (
        activation_defaults["min_reviewed_samples"]
        == DEFAULT_ACTIVATION_DEFAULTS["min_reviewed_samples"]
    )
    assert (
        activation_defaults["min_precision"]
        == DEFAULT_ACTIVATION_DEFAULTS["min_precision"]
    )
    assert activation_defaults["broad_pattern_requires_justification"] is True


def test_classify_with_evidence_returns_rule_and_snippet() -> None:
    df = pl.DataFrame(
        [
            {
                "product_name": "Sample Matte Lipstick",
                "category_key": "lipstick",
                "description": "This lipstick provides a matte finish that lasts.",
            }
        ]
    )

    result, evidence = classify_explicit_declarations_with_evidence(
        df,
        key_columns=["product_name", "category_key"],
        category_column="category_key",
        text_columns=["description"],
        attr_map={"lipstick": ["finish"]},
        taxonomy=_taxonomy(),
        rules=_rules_for_finish(),
    )

    assert result.height == 1
    assert result.row(0, named=True)["finish"] == "matte"
    row_key = ("Sample Matte Lipstick", "lipstick")
    assert evidence[row_key]["finish"]["decision"] == "matched"
    assert evidence[row_key]["finish"]["rule_id"] == "lipstick.finish.matte.1"
    assert "matte finish" in evidence[row_key]["finish"]["snippet"].lower()


def test_validate_explicit_declaration_rules_rejects_missing_quality_fields() -> None:
    rules = _rules_for_finish()
    signal = rules["categories"]["lipstick"]["attributes"]["finish"]["values"]["matte"][
        "certainty_signals"
    ][0]
    signal.pop("reviewed_samples", None)

    with pytest.raises(ValueError, match="reviewed_samples"):
        validate_explicit_declaration_rules(rules, _taxonomy())


def test_validate_explicit_declaration_rules_rejects_non_active_leaf() -> None:
    rules = _rules_for_finish()
    taxonomy = _taxonomy()
    taxonomy["categories"][0]["attributes"][0]["nodes"][0]["status"] = "needs_review"

    with pytest.raises(ValueError, match="is not active"):
        validate_explicit_declaration_rules(rules, taxonomy)
