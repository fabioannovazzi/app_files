from __future__ import annotations

import pytest

from src.slides.errors import InvalidDeckError
from src.slides.service import (
    deck_from_payload,
    deck_to_payload,
    generate_slide_filename,
)


def test_deck_payload_roundtrip_preserves_sources_sharing_and_section_hierarchy() -> (
    None
):
    deck = deck_from_payload(
        "review",
        [
            {
                "id": "slide0.html",
                "titleHtml": "Evidence",
                "bodyHtml": "<p>Finding</p>",
                "notesHtml": "Review note",
                "sourceHtml": "Source page 2",
                "sectionId": "findings",
                "subsectionId": "evidence",
            }
        ],
        owner_email="owner@example.test",
        shared_with=["reviewer@example.test"],
        sections_data=[
            {
                "id": "findings",
                "title": "Findings",
                "startSlide": "slide0.html",
                "subsections": [
                    {"id": "evidence", "title": "Evidence", "startSlide": "slide0.html"}
                ],
            }
        ],
    )

    result = deck_to_payload(deck)

    assert result["ownerEmail"] == "owner@example.test"
    assert result["sharedWith"] == ["reviewer@example.test"]
    assert result["slides"][0]["notesHtml"] == "Review note"
    assert result["slides"][0]["sourceHtml"] == "Source page 2"
    assert "Finding" in result["slides"][0]["fullHtml"]
    assert result["sections"][0]["subsections"] == [
        {"id": "evidence", "title": "Evidence", "startSlide": "slide0.html"}
    ]


@pytest.mark.parametrize(
    ("slides", "message"),
    [
        ([{}], "include an 'id'"),
        ([{"id": "same"}, {"id": "same"}], "Duplicate slide id"),
        ([{"id": "slide0.html", "kind": "unknown"}], "Unsupported slide kind"),
    ],
)
def test_deck_payload_rejects_invalid_slide_identity(slides, message) -> None:
    with pytest.raises(InvalidDeckError, match=message):
        deck_from_payload("review", slides)


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ({"id": ""}, "Sections must include"),
        ({"id": "intro"}, "requires a 'startSlide'"),
        (
            {"id": "intro", "startSlide": "slide0.html", "subsections": [{"id": ""}]},
            "Subsections must include",
        ),
        (
            {
                "id": "intro",
                "startSlide": "slide0.html",
                "subsections": [{"id": "detail"}],
            },
            "requires a 'startSlide'",
        ),
    ],
)
def test_deck_payload_rejects_incomplete_section_hierarchy(section, message) -> None:
    with pytest.raises(InvalidDeckError, match=message):
        deck_from_payload("review", [{"id": "slide0.html"}], sections_data=[section])


@pytest.mark.parametrize(
    ("existing", "expected"),
    [
        ([], "slide0.html"),
        (["index.html", "slide2.html", "SLIDE12.HTML", "notes.txt"], "slide13.html"),
    ],
)
def test_next_slide_filename_avoids_existing_numbered_ids(existing, expected) -> None:
    assert generate_slide_filename(existing) == expected
