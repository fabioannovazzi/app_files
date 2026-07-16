from __future__ import annotations

import re
import zipfile
from pathlib import Path

from src.review_brief.pptx_template import (
    REVIEW_BRIEF_PPTX_SPEC_FILENAME,
    build_review_brief_pptx_spec,
    load_review_brief_pptx_spec,
    write_review_brief_pptx_spec,
)
from src.review_brief.slides_deck import build_review_brief_deck_spec


def test_review_brief_pptx_spec_round_trips_with_relative_chart_paths(tmp_path) -> None:
    payload = {
        "category": "Blush",
        "retailers": ["ulta", "sephora"],
        "prompt_style": "uniform",
        "start_month": "2024-01-01",
        "end_month": "2024-12-01",
        "charts": [
            {
                "chart_id": "chart_demo_1",
                "title": "Category mix by form",
                "subtitle": "Monthly values",
                "normalization": "share_of_category_total",
            }
        ],
        "interpretations": {
            "chart_demo_1": {
                "chart_id": "chart_demo_1",
                "headline": "Cream outpaces powder",
                "bullets": ["Cream gains 12 pp.", "Powder loses 7 pp."],
            }
        },
        "selected": ["chart_demo_1"],
        "narrative": {
            "executive_narrative": "The category is shifting toward cream formats.",
            "key_takeaways": ["Cream is the main winner.", "Powder is retreating."],
            "suggested_flow": [
                {"title": "Format mix shift", "chart_ids": ["chart_demo_1"]}
            ],
        },
        "requested_scope": {},
    }

    deck_spec = build_review_brief_deck_spec(payload)
    spec = build_review_brief_pptx_spec(
        payload,
        deck_spec,
        chart_image_urls={
            "chart_demo_1": "/slides/deck/deckUniform/assets/chart_demo_1.png"
        },
    )
    write_review_brief_pptx_spec(tmp_path, spec)

    loaded = load_review_brief_pptx_spec(tmp_path)

    assert (tmp_path / REVIEW_BRIEF_PPTX_SPEC_FILENAME).exists()
    assert loaded.template_key == "uniform"
    assert loaded.prompt_style == "uniform"
    assert len(loaded.slides) == 2
    assert loaded.slides[0].eyebrow == ""
    assert loaded.slides[0].title == "Blush review: ulta, sephora"
    assert loaded.slides[0].body == (
        "The category is shifting toward cream formats. "
        "Retailers: ulta, sephora. Period: 2024-01-01 to 2024-12-01."
    )
    assert loaded.slides[0].scope_items == [
        "Retailers: ulta, sephora",
        "Category: Blush",
        "Period: 2024-01-01 to 2024-12-01",
    ]
    assert loaded.slides[1].eyebrow == ""
    assert loaded.slides[1].body == "Cream outpaces powder"
    assert loaded.slides[1].chart_path == "assets/chart_demo_1.png"
    assert loaded.slides[1].chart_caption == "Category mix by form"


def test_uniform_pptx_template_asset_exists_without_seed_slides() -> None:
    template_path = Path("src/review_brief/pptx_templates/uniform.pptx")

    assert template_path.exists()
    with zipfile.ZipFile(template_path) as archive:
        names = archive.namelist()

    assert "ppt/presentation.xml" in names
    assert "ppt/slideLayouts/slideLayout7.xml" in names
    assert not any(re.match(r"ppt/slides/slide\\d+\\.xml$", name) for name in names)
