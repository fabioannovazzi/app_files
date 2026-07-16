from __future__ import annotations

import json

from modules.pdp import review_theme_codebook as rtc
from modules.pdp.review_theme_codebook import (
    ReviewRecord,
    ReviewTheme,
    discover_review_theme_codebook,
    sample_reviews_by_stratum,
    sanitize_codebook_response,
    sanitize_tag_response,
    tag_reviews_with_codebook,
)


def _record(
    review_id: str,
    *,
    parent_product_id: str,
    is_top_seller: bool = False,
    rating: float | None = 5.0,
) -> ReviewRecord:
    return ReviewRecord(
        review_id=review_id,
        retailer="chewy",
        category_key="wet_cat_food",
        parent_product_id=parent_product_id,
        product_name="Test food",
        brand="Test Brand",
        pdp_url=None,
        review_hash=f"hash-{review_id}",
        review_unit_index=0,
        source="review",
        headline=None,
        comment=None,
        text="My cat eats this.",
        rating=rating,
        review_created_date=None,
        is_top_seller=is_top_seller,
        is_new_launch=False,
    )


def test_sanitize_codebook_response_flattens_parent_subthemes_with_cap() -> None:
    response = {
        "parent_themes": [
            {
                "parent_id": "cat_acceptance",
                "parent_label": "Cat acceptance / refusal",
                "subthemes": [
                    {
                        "subtheme_id": "accepts_eagerly",
                        "subtheme_label": "Eagerly eats",
                        "description": "Cat eats or strongly prefers the food.",
                    },
                    {
                        "subtheme_id": "refuses",
                        "subtheme_label": "Refusal",
                        "description": "Cat refuses the food.",
                    },
                ],
            }
        ]
    }

    themes = sanitize_codebook_response(response, max_themes=1)

    assert len(themes) == 1
    assert themes[0].theme_id == "cat_acceptance__accepts_eagerly"
    assert themes[0].theme_family == "Cat acceptance / refusal"
    assert themes[0].theme_label == "Eagerly eats"


def test_sample_reviews_by_stratum_keeps_top_and_non_top_separate() -> None:
    top_record = _record("top-review", parent_product_id="top", is_top_seller=True)
    non_top_record = _record(
        "non-top-review",
        parent_product_id="non-top",
        is_top_seller=False,
    )

    sampled = sample_reviews_by_stratum(
        [top_record, non_top_record],
        reviews_per_stratum=1,
        seed=1,
        stratum_names=("top_sellers", "non_top_sellers"),
    )

    assert sampled["top_sellers"] == (top_record,)
    assert sampled["non_top_sellers"] == (non_top_record,)


def test_sanitize_tag_response_preserves_exact_theme_ids() -> None:
    record = _record("review-1", parent_product_id="product-1")
    theme = ReviewTheme(
        theme_id="cat_acceptance__accepts_eagerly",
        theme_label="Eagerly eats",
        theme_family="Cat acceptance / refusal",
        description="Cat eats or strongly prefers the food.",
    )
    response = {
        "themes": [
            {
                "theme_id": "cat_acceptance__accepts_eagerly",
                "polarity": "positive",
                "evidence_span": "my cat eats this",
                "target": "food",
                "actor": "cat",
                "confidence": 0.9,
            }
        ]
    }

    tags = sanitize_tag_response(
        response, record=record, theme_by_id={theme.theme_id: theme}
    )

    assert len(tags) == 1
    assert tags[0].theme_id == theme.theme_id
    assert tags[0].polarity == "positive"


def test_sanitize_tag_response_dedupes_repeated_theme_entries() -> None:
    record = _record("review-1", parent_product_id="product-1")
    theme = ReviewTheme(
        theme_id="cat_acceptance__accepts_eagerly",
        theme_label="Eagerly eats",
        theme_family="Cat acceptance / refusal",
        description="Cat eats or strongly prefers the food.",
    )
    repeated_tag = {
        "theme_id": theme.theme_id,
        "polarity": "positive",
        "evidence_span": "my cat eats this",
    }

    tags = sanitize_tag_response(
        {"themes": [repeated_tag, repeated_tag]},
        record=record,
        theme_by_id={theme.theme_id: theme},
    )

    assert len(tags) == 1


def test_sanitize_tag_response_rejects_unknown_theme_ids() -> None:
    record = _record("review-1", parent_product_id="product-1")
    theme = ReviewTheme(
        theme_id="cat_acceptance__accepts_eagerly",
        theme_label="Eagerly eats",
        theme_family="Cat acceptance / refusal",
        description="Cat eats or strongly prefers the food.",
    )
    response = {
        "themes": [
            {
                "theme_id": "invented_theme",
                "polarity": "positive",
                "evidence_span": "my cat eats this",
            }
        ]
    }

    tags = sanitize_tag_response(
        response, record=record, theme_by_id={theme.theme_id: theme}
    )

    assert tags == ()


def test_tag_reviews_with_codebook_batches_records(monkeypatch) -> None:
    theme = ReviewTheme(
        theme_id="cat_acceptance__accepts_eagerly",
        theme_label="Eagerly eats",
        theme_family="Cat acceptance / refusal",
        description="Cat eats or strongly prefers the food.",
    )
    records = [
        _record("review-1", parent_product_id="product-1"),
        _record("review-2", parent_product_id="product-2"),
        _record("review-3", parent_product_id="product-3"),
    ]
    prompt_count = 0

    def fake_run_step_json(*args, **kwargs):
        nonlocal prompt_count
        prompts = args[3]
        prompt_count = len(prompts)
        return [
            {
                "reviews": [
                    {
                        "review_id": "review-1",
                        "themes": [
                            {
                                "theme_id": theme.theme_id,
                                "polarity": "positive",
                                "evidence_span": "My cat eats this",
                            }
                        ],
                    },
                    {"review_id": "review-2", "themes": []},
                ]
            },
            {
                "reviews": [
                    {
                        "review_id": "review-3",
                        "themes": [
                            {
                                "theme_id": theme.theme_id,
                                "polarity": "positive",
                                "evidence_span": "My cat loves this",
                            }
                        ],
                    }
                ]
            },
        ]

    monkeypatch.setattr(rtc, "run_step_json", fake_run_step_json)

    tags = tag_reviews_with_codebook(
        object(),
        records=records,
        themes=[theme],
        tag_batch_size=2,
    )

    assert prompt_count == 2
    assert [tag.review_id for tag in tags] == ["review-1", "review-3"]


def test_discover_review_theme_codebook_uses_neutral_batches_and_high_reasoning(
    monkeypatch,
) -> None:
    record = _record("review-1", parent_product_id="product-1")
    captured_reasoning_efforts: list[str] = []
    captured_candidate_prompt = None

    def fake_run_step_json(*args, **kwargs):
        nonlocal captured_candidate_prompt
        captured_reasoning_efforts.append(kwargs["reasoning_effort"])
        prompts = args[3]
        if isinstance(prompts, list):
            captured_candidate_prompt = json.loads(prompts[0])
            return [
                {
                    "parent_themes": [
                        {
                            "parent_id": "cat_acceptance",
                            "parent_label": "Cat acceptance",
                            "subthemes": [
                                {
                                    "subtheme_id": "eats",
                                    "subtheme_label": "Eats it",
                                    "description": "Cat eats the food.",
                                }
                            ],
                        }
                    ]
                }
            ]
        return [
            {
                "parent_themes": [
                    {
                        "parent_id": "cat_acceptance",
                        "parent_label": "Cat acceptance",
                        "subthemes": [
                            {
                                "subtheme_id": "eats",
                                "subtheme_label": "Eats it",
                                "description": "Cat eats the food.",
                            }
                        ],
                    }
                ]
            }
        ]

    monkeypatch.setattr(rtc, "run_step_json", fake_run_step_json)

    themes = discover_review_theme_codebook(
        object(),
        retailer="chewy",
        category_key="wet_cat_food",
        sampled_records_by_stratum={"top_sellers": [record]},
    )

    assert captured_reasoning_efforts == ["high", "high"]
    assert captured_candidate_prompt["batch_label"] == "Batch A"
    assert "top_sellers" not in json.dumps(captured_candidate_prompt)
    assert themes[0].theme_id == "cat_acceptance__eats"


def test_sample_reviews_by_stratum_can_include_general_random_remainder() -> None:
    top_record = _record("top-review", parent_product_id="top", is_top_seller=True)
    non_top_record = _record(
        "non-top-review",
        parent_product_id="non-top",
        is_top_seller=False,
    )

    sampled = sample_reviews_by_stratum(
        [top_record, non_top_record],
        reviews_per_stratum=2,
        seed=1,
        stratum_names=("top_sellers", "general_random"),
    )

    assert sampled["top_sellers"] == (top_record,)
    assert sampled["general_random"] == (non_top_record,)


def test_sample_reviews_by_stratum_adds_target_brand_only_when_requested() -> None:
    brand_record = _record("brand-review", parent_product_id="brand-product")
    other_record = _record("other-review", parent_product_id="other-product")
    brand_record = ReviewRecord(**{**brand_record.__dict__, "brand": "Purina Pro Plan"})
    other_record = ReviewRecord(**{**other_record.__dict__, "brand": "Other"})

    sampled = sample_reviews_by_stratum(
        [brand_record, other_record],
        reviews_per_stratum=1,
        seed=1,
        stratum_names=("target_brand",),
        focus_brands=("Purina",),
    )

    assert sampled["target_brand"] == (brand_record,)


