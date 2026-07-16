from __future__ import annotations

import json

import polars as pl
import pytest
from polars.testing import assert_frame_equal

import modules.add_attributes.attribute_scoring as scoring
from modules.add_attributes.attribute_scoring import (
    score_attributes_for_products,
    score_product_attributes,
    score_to_stars,
)


@pytest.mark.parametrize(
    "inp, expected",
    [
        (1, "*"),
        (3, "***"),
        (5, "*****"),
        (0, "*"),  # lower clamp
        (6, "*****"),  # upper clamp
        (-2, "*"),  # negative -> clamp to 1
    ],
)
def test_score_to_stars_bounds_and_basic(inp: int, expected: str) -> None:
    assert score_to_stars(inp) == expected


def test_score_product_attributes_parses_scores_and_confidence(monkeypatch) -> None:
    # Arrange: stub LLM call to return deterministic JSON
    resp = {
        "scores": {
            "Speed": {"score": "4", "explanation": "probably fast"},
            "Color": {"score": "*****", "explanation": "Bright"},
            # Missing attribute will be ignored (validation case)
        }
    }

    def fake_run_step_json(_llm, _step, _sys, _user, **_kwargs):
        return [resp]

    monkeypatch.setattr(scoring, "run_step_json", fake_run_step_json)

    # Act
    out = score_product_attributes(
        object(),
        product="Widget",
        attributes=["Speed", "Color", "Missing"],
        output_mode="confidence",
    )

    # Assert: only present attributes included; numeric strings normalized; stars preserved
    assert set(out.keys()) == {"Speed", "Color"}
    assert out["Speed"]["score"] == "****"  # "4" -> 4 stars
    assert out["Speed"]["explanation"] == "probably fast"
    assert out["Speed"]["confidence"] == "Low"  # contains uncertainty
    assert out["Color"]["score"] == "*****"  # star string passed through
    assert out["Color"]["confidence"] == "High"


def test_score_attributes_for_products_batch_stub_confidence(monkeypatch) -> None:
    # Arrange: minimal DataFrame and attr map for All products
    df = pl.DataFrame({"product": ["Foo"]})
    attr_map = {"All products": ["Speed"]}

    # Batch hook: provide canned batch output matching the module's parser
    payload = {"scores": {"Speed": {"score": "3", "explanation": "maybe good"}}}
    batch_line = json.dumps(
        {
            "response": {
                "output": [
                    {
                        "content": [
                            {
                                "text": json.dumps(payload),
                            }
                        ]
                    }
                ]
            }
        }
    )

    def fake_wait_for_batch(_llm, _bid):
        return {"0": batch_line}

    # Install test hook on the module globals
    monkeypatch.setattr(scoring, "wait_for_batch", fake_wait_for_batch, raising=False)

    # Act
    result = score_attributes_for_products(
        object(),
        df,
        product_col="product",
        products=["Foo"],
        attr_map=attr_map,
        use_batch=True,
        output_mode="confidence",
    )

    # Assert: expected columns and values; confidence derived from explanation
    expected = pl.DataFrame(
        [
            {
                "product": "Foo",
                "group": "All products",
                "Speed_score": "***",
                "Speed_confidence": "Low",
            }
        ]
    )

    # Compare deterministically (order of columns may vary)
    result_sorted = result.select(sorted(result.columns))
    expected_sorted = expected.select(sorted(expected.columns))
    assert_frame_equal(result_sorted, expected_sorted)
