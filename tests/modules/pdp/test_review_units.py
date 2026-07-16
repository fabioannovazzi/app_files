from __future__ import annotations

from modules.pdp.review_units import (
    canonical_review_units_from_payload,
    review_set_hash_from_payload,
    review_text_unit_count_from_payload,
)


def test_review_set_hash_is_stable_across_irrelevant_metadata() -> None:
    payload = {
        "reviews": [
            {
                "review_id": "a",
                "headline": " Cats loved it ",
                "comment": "  Both cats finished the bowl. ",
                "rating": "5",
                "author": "A",
                "helpfulness": 10,
            }
        ]
    }
    same_review_payload = {
        "reviews": [
            {
                "review_id": "different-id",
                "headline": "Cats loved it",
                "comment": "Both cats finished the bowl.",
                "rating": 5.0,
                "author": "B",
                "helpfulness": 0,
            }
        ]
    }

    assert review_set_hash_from_payload(payload) == review_set_hash_from_payload(
        same_review_payload
    )


def test_review_set_hash_changes_when_review_text_changes() -> None:
    accepted_payload = {
        "reviews": [
            {
                "headline": "Cats loved it",
                "comment": "Both cats finished the bowl.",
                "rating": 5,
            }
        ]
    }
    rejected_payload = {
        "reviews": [
            {
                "headline": "Cats refused it",
                "comment": "Neither cat would eat it.",
                "rating": 1,
            }
        ]
    }

    assert review_set_hash_from_payload(
        accepted_payload
    ) != review_set_hash_from_payload(rejected_payload)


def test_review_set_hash_is_order_independent_for_same_review_set() -> None:
    first_payload = {
        "reviews": [
            {"headline": "Good", "comment": "Cat ate it.", "rating": 5},
            {"headline": "Bad", "comment": "Texture was dry.", "rating": 2},
        ]
    }
    second_payload = {
        "reviews": [
            {"headline": "Bad", "comment": "Texture was dry.", "rating": 2},
            {"headline": "Good", "comment": "Cat ate it.", "rating": 5},
        ]
    }

    assert review_set_hash_from_payload(first_payload) == review_set_hash_from_payload(
        second_payload
    )


def test_review_units_include_positive_and_negative_summaries() -> None:
    payload = {
        "reviews_positive": {
            "headline": "Blends beautifully",
            "comment": "The powder is easy to blend.",
        },
        "reviews_negative": {
            "headline": "Too orange",
            "comment": "The undertone looked orange on fair skin.",
        },
    }

    units = canonical_review_units_from_payload(payload)

    assert review_text_unit_count_from_payload(payload) == 2
    assert {unit["source"] for unit in units} == {
        "positive_summary",
        "negative_summary",
    }


def test_review_units_use_all_stored_reviews() -> None:
    payload = {
        "reviews": [
            {
                "headline": f"Review {index}",
                "comment": f"Stored review text {index}.",
                "rating": 5,
            }
            for index in range(7)
        ]
    }

    units = canonical_review_units_from_payload(payload)

    assert len(units) == 7
    assert review_text_unit_count_from_payload(payload) == 7


def test_review_set_hash_returns_none_without_review_text() -> None:
    payload = {"rating": 4.8, "review_count": 120}

    assert review_set_hash_from_payload(payload) is None
    assert review_text_unit_count_from_payload(payload) == 0
