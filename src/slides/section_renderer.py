from __future__ import annotations

from html import escape
from typing import Sequence

from .models import Section

__all__ = ["build_section_header_content"]

_DEFAULT_SECTION_HEADER_TITLE = ""


def build_section_header_content(
    sections: Sequence[Section],
    section_id: str | None,
    subsection_id: str | None = None,
) -> tuple[str, str]:
    """Return ``(title_html, body_html)`` for a section header slide.

    The generated HTML intentionally avoids inline styles so that the
    presentation layer can style the resulting markup as required.
    """

    if not sections or not section_id:
        return ("", _empty_body())

    section_lookup = {section.id: section for section in sections}
    section = section_lookup.get(section_id)
    if section is None:
        return ("", _missing_section_body(section_id))

    title_html = ""
    section_items = [
        _render_section_item(section_item, subsection_id, is_current=section_item.id == section_id)
        for section_item in sections
    ]
    body_html = "".join(section_items)
    stylesheet_link = '<link rel="stylesheet" href="./section_header.css" />'
    body_markup = (
        '<section class="section-header">'
        f"{stylesheet_link}"
        f'<ol class="section-header__sections">{body_html}</ol>'
        "</section>"
    )
    return (title_html, body_markup)


def _render_section_item(
    section: Section,
    current_subsection_id: str | None,
    *,
    is_current: bool,
) -> str:
    classes = ["section-header__section"]
    if is_current:
        classes.append("is-current")
    subsection_markup = ""
    if section.subsections and is_current:
        subsection_markup = _render_subsection_list(
            section,
            current_subsection_id,
            is_current=is_current,
        )
    label = escape(section.title or section.id)
    return (
        f'<li class="{' '.join(classes)}">'
        f'<span class="section-header__section-label">{label}</span>'
        f"{subsection_markup}"
        "</li>"
    )


def _render_subsection_list(
    section: Section,
    current_subsection_id: str | None,
    *,
    is_current: bool,
) -> str:
    items: list[str] = []
    for subsection in section.subsections:
        classes = ["section-header__subsection"]
        if is_current and subsection.id == current_subsection_id:
            classes.append("is-current")
        label = escape(subsection.title or subsection.id)
        items.append(f'<li class="{' '.join(classes)}">{label}</li>')
    return f'<ul class="section-header__subsections">{"".join(items)}</ul>'


def _empty_body() -> str:
    return (
        '<section class="section-header">'
        '<p class="section-header__placeholder">Define sections to see a preview.</p>'
        "</section>"
    )


def _missing_section_body(section_id: str) -> str:
    safe_id = escape(section_id)
    return (
        '<section class="section-header">'
        f'<p class="section-header__placeholder">Unknown section {safe_id!s}.</p>'
        "</section>"
    )


def _wrap_span(content: str, class_name: str) -> str:
    return f'<span class="{class_name}">{escape(content)}</span>'
