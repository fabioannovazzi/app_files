from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence

from .errors import InvalidDeckError
from .html_normalizer import update_slide_document
from .models import Deck, Section, Slide, Subsection
from .notebooklm_style import resolve_prompt_style_key

__all__ = ["deck_from_payload", "deck_to_payload", "generate_slide_filename"]

_SLIDE_ID_PATTERN = re.compile(r"^slide(\d+)\.html$", re.IGNORECASE)


def deck_from_payload(
    deck_id: str,
    slides_data: Sequence[Mapping[str, object]],
    *,
    sections_data: Sequence[Mapping[str, object]] | None = None,
    prompt_style: str | None = None,
    owner_email: str | None = None,
    shared_with: Sequence[str] | None = None,
) -> Deck:
    """Build a :class:`Deck` from API payload ``slides_data``."""

    slides: list[Slide] = []
    seen: set[str] = set()
    for entry in slides_data:
        try:
            slide_id = str(entry["id"])
        except KeyError as exc:
            raise InvalidDeckError("Slide entries must include an 'id' field") from exc
        if slide_id in seen:
            raise InvalidDeckError(f"Duplicate slide id '{slide_id}' in payload")
        seen.add(slide_id)
        title_html = str(entry.get("titleHtml", ""))
        body_html = str(entry.get("bodyHtml", ""))
        kind = str(entry.get("kind", "normal"))
        if kind not in {"normal", "sectionHeader"}:
            raise InvalidDeckError(f"Unsupported slide kind '{kind}' in payload")
        section_id = entry.get("sectionId")
        subsection_id = entry.get("subsectionId")
        notes_html = str(entry.get("notesHtml", ""))
        source_html = str(entry.get("sourceHtml", ""))
        full_html = str(entry.get("fullHtml", ""))
        slides.append(
            Slide(
                id=slide_id,
                title_html=title_html,
                body_html=body_html,
                notes_html=notes_html,
                source_html=source_html,
                full_html=full_html,
                kind="sectionHeader" if kind == "sectionHeader" else "normal",
                section_id=str(section_id) if isinstance(section_id, str) else None,
                subsection_id=(
                    str(subsection_id) if isinstance(subsection_id, str) else None
                ),
            )
        )
        slides[-1].full_html = update_slide_document(
            slides[-1].full_html,
            title_html=slides[-1].title_html,
            body_html=slides[-1].body_html,
            notes_html=slides[-1].notes_html,
            source_html=slides[-1].source_html,
        )
    sections = list(_parse_sections(sections_data or []))
    resolved_prompt_style = resolve_prompt_style_key(prompt_style)
    deck = Deck(
        deck_id=deck_id,
        prompt_style=resolved_prompt_style,
        owner_email=owner_email,
        shared_with=list(shared_with or []),
        slides=slides,
        sections=sections,
    )
    deck.sync_section_headers()
    return deck


def deck_to_payload(deck: Deck) -> dict[str, object]:
    """Convert ``deck`` into a serialisable payload."""

    deck.sync_section_headers()
    return {
        "deckId": deck.deck_id,
        "promptStyle": deck.prompt_style,
        "ownerEmail": deck.owner_email,
        "sharedWith": list(deck.shared_with),
        "slides": [
            {
                "id": slide.id,
                "titleHtml": slide.title_html,
                "bodyHtml": slide.body_html,
                "notesHtml": slide.notes_html,
                "sourceHtml": slide.source_html,
                "fullHtml": slide.full_html,
                "kind": slide.kind,
                "sectionId": slide.section_id,
                "subsectionId": slide.subsection_id,
            }
            for slide in deck
        ],
        "sections": [
            {
                "id": section.id,
                "title": section.title,
                "startSlide": section.start_slide,
                "subsections": [
                    {
                        "id": subsection.id,
                        "title": subsection.title,
                        "startSlide": subsection.start_slide,
                    }
                    for subsection in section.subsections
                ],
            }
            for section in deck.sections
        ],
    }


def generate_slide_filename(existing_ids: Iterable[str]) -> str:
    """Return the next ``slideN.html`` filename not present in ``existing_ids``."""

    max_index = -1
    for slide_id in existing_ids:
        match = _SLIDE_ID_PATTERN.match(slide_id)
        if match:
            try:
                index = int(match.group(1))
            except ValueError:
                continue
            max_index = max(max_index, index)
    next_index = max_index + 1
    return f"slide{next_index}.html"


def _parse_sections(
    sections: Sequence[Mapping[str, object]] | None,
) -> Iterable[Section]:
    if not sections:
        return []
    parsed: list[Section] = []
    for entry in sections:
        section_id = str(entry.get("id", "")).strip()
        if not section_id:
            raise InvalidDeckError("Sections must include a non-empty 'id'")
        title = str(entry.get("title", ""))
        start_slide_value = entry.get("startSlide")
        if not isinstance(start_slide_value, str) or not start_slide_value:
            raise InvalidDeckError(f"Section {section_id} requires a 'startSlide'")
        subsections = list(_parse_subsections(entry.get("subsections")))
        parsed.append(
            Section(
                id=section_id,
                title=title,
                start_slide=start_slide_value,
                subsections=subsections,
            )
        )
    return parsed


def _parse_subsections(
    subsections: Sequence[Mapping[str, object]] | None,
) -> Iterable[Subsection]:
    if not subsections:
        return []
    parsed: list[Subsection] = []
    for entry in subsections:
        subsection_id = str(entry.get("id", "")).strip()
        if not subsection_id:
            raise InvalidDeckError("Subsections must include a non-empty 'id'")
        title = str(entry.get("title", ""))
        start_slide_value = entry.get("startSlide")
        if not isinstance(start_slide_value, str) or not start_slide_value:
            raise InvalidDeckError(
                f"Subsection {subsection_id} requires a 'startSlide'"
            )
        parsed.append(
            Subsection(id=subsection_id, title=title, start_slide=start_slide_value)
        )
    return parsed
