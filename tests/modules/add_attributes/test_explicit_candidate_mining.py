from __future__ import annotations

import polars as pl

from modules.add_attributes.explicit_candidate_mining import (
    mine_explicit_declaration_candidates,
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


def test_mine_explicit_declaration_candidates_generates_pending_candidates() -> None:
    source_df = pl.DataFrame(
        {
            "retailer": ["sephora", "sephora"],
            "parent_product_id": ["P1", "P2"],
            "category_key": ["lipstick", "lipstick"],
            "pdp_text": [
                "This formula gives a matte finish for all-day wear.",
                "Choose this satin finish lipstick for shine.",
            ],
        }
    )
    rules = {
        "version": "1.0.0",
        "updated_at": "2026-03-05T00:00:00Z",
        "categories": {},
        "metadata": {},
    }

    candidates = mine_explicit_declaration_candidates(
        source_df,
        taxonomy=_taxonomy(),
        rules=rules,
        min_sample_count=1,
    )

    by_pattern = {candidate.pattern: candidate for candidate in candidates}
    assert "matte finish" in by_pattern
    assert "satin finish" in by_pattern
    assert by_pattern["matte finish"].status == "pending"
    assert by_pattern["matte finish"].sample_count == 1


def test_mine_explicit_declaration_candidates_estimates_conflict_rate() -> None:
    source_df = pl.DataFrame(
        {
            "retailer": ["sephora"],
            "parent_product_id": ["P1"],
            "category_key": ["lipstick"],
            "pdp_text": ["Claims both matte finish and satin finish in one PDP."],
        }
    )

    candidates = mine_explicit_declaration_candidates(
        source_df,
        taxonomy=_taxonomy(),
        rules={"version": "1", "updated_at": "", "categories": {}, "metadata": {}},
        min_sample_count=1,
    )

    assert candidates
    assert all(candidate.estimated_conflict_rate == 1.0 for candidate in candidates)
