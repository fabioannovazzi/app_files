from __future__ import annotations

import json
from pathlib import Path

from modules.pdp.signal_quality import (
    category_has_signal_quality_rules,
    parse_signal_bundle_key,
    signal_insight_metadata,
)


def test_default_signal_quality_has_no_category_specific_rules() -> None:
    components = parse_signal_bundle_key("lifestage=Adult + packaging type=Can")

    metadata = signal_insight_metadata(
        category_key="wet_cat_food",
        components=components,
        base_score=100.0,
        signal_layers=("winning_now",),
    )

    assert not category_has_signal_quality_rules("wet_cat_food")
    assert metadata["signal_usefulness"] == "selected_signal"
    assert metadata["signal_role"] == "unclassified_signal"
    assert metadata["insight_adjusted_signal_score"] == 100.0


def test_signal_quality_can_still_use_explicit_category_rules(tmp_path: Path) -> None:
    config_path = tmp_path / "signal_quality.json"
    config_path.write_text(
        json.dumps(
            {
                "categories": {
                    "demo_category": {
                        "category_center_component_values": {"packaging type": ["can"]},
                        "discriminating_attributes": ["food texture"],
                        "category_center_score_multiplier": 0.05,
                        "discriminating_score_multiplier": 0.18,
                        "category_center_component_penalty": 12.0,
                        "headline_min_discriminating_components": 2,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    components = parse_signal_bundle_key("food texture=Pate + packaging type=Can")

    metadata = signal_insight_metadata(
        category_key="demo_category",
        components=components,
        base_score=50.0,
        signal_layers=("winning_now",),
        layer_bonus_by_layer={"winning_now": 4.0},
        config_path=str(config_path),
    )

    assert metadata["signal_usefulness"] == "supporting_signal"
    assert metadata["signal_role"] == "supporting_differentiation"
    assert metadata["discriminating_component_count"] == 1
    assert metadata["category_center_component_count"] == 1
    assert metadata["base_rate_component_count"] == 1
    assert metadata["insight_adjusted_signal_score"] == 51.0
