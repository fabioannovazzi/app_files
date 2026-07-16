from __future__ import annotations

import pytest

from src.slides.models import Section, Subsection
from src.slides.section_renderer import build_section_header_content


@pytest.mark.parametrize(
    ("active_section_id", "active_subsection_id", "visible_subsections", "hidden_subsections"),
    [
        (
            "A",
            "a2",
            ("A1", "A2"),
            ("B1",),
        ),
        (
            "B",
            "b1",
            ("B1",),
            ("A1", "A2"),
        ),
    ],
)
def test_build_section_header_content_renders_subsections_only_for_active_section(
    active_section_id: str,
    active_subsection_id: str,
    visible_subsections: tuple[str, ...],
    hidden_subsections: tuple[str, ...],
) -> None:
    sections = [
        Section(
            id="A",
            title="Section A",
            start_slide="slide-001.html",
            subsections=[
                Subsection(id="a1", title="A1", start_slide="slide-001.html"),
                Subsection(id="a2", title="A2", start_slide="slide-002.html"),
            ],
        ),
        Section(
            id="B",
            title="Section B",
            start_slide="slide-003.html",
            subsections=[
                Subsection(id="b1", title="B1", start_slide="slide-003.html"),
            ],
        ),
    ]

    _title_html, body_html = build_section_header_content(
        sections,
        active_section_id,
        active_subsection_id,
    )

    assert "Section A" in body_html
    assert "Section B" in body_html
    for label in visible_subsections:
        assert label in body_html
    for label in hidden_subsections:
        assert label not in body_html

