from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator, Literal, Sequence

from .html_normalizer import update_slide_document

__all__ = [
    "Slide",
    "SlideSummary",
    "Deck",
    "Section",
    "Subsection",
    "IndexSlideEntry",
]


SlideKind = Literal["normal", "sectionHeader"]


@dataclass(slots=True)
class Slide:
    """Single HTML slide extracted from a deck."""

    id: str
    title_html: str
    body_html: str
    notes_html: str = ""
    source_html: str = ""
    full_html: str = ""
    kind: SlideKind = "normal"
    section_id: str | None = None
    subsection_id: str | None = None

    def summary(self) -> "SlideSummary":
        """Return a lightweight summary representation."""

        return SlideSummary(id=self.id, title_html=self.title_html)

    @property
    def is_section_header(self) -> bool:
        """Return ``True`` when the slide represents a section header."""

        return self.kind == "sectionHeader"


@dataclass(slots=True)
class SlideSummary:
    """Summary information exposed when listing decks."""

    id: str
    title_html: str


@dataclass
class Deck:
    """Ordered collection of slides for a deck."""

    deck_id: str
    prompt_style: str = "uniform"
    owner_email: str | None = None
    shared_with: list[str] = field(default_factory=list)
    slides: list[Slide] = field(default_factory=list)
    sections: list["Section"] = field(default_factory=list)

    def __iter__(self) -> Iterator[Slide]:
        return iter(self.slides)

    def __len__(self) -> int:  # pragma: no cover - trivial wrapper
        return len(self.slides)

    def slide_ids(self) -> list[str]:
        """Return the list of slide identifiers in order."""

        return [slide.id for slide in self.slides]

    def find(self, slide_id: str) -> Slide:
        """Return the slide with the given ``slide_id`` or raise ``KeyError``."""

        for slide in self.slides:
            if slide.id == slide_id:
                return slide
        raise KeyError(f"Slide {slide_id} not found in deck {self.deck_id}")

    def replace_slide(self, updated: Slide) -> None:
        """Replace an existing slide with ``updated`` preserving order."""

        for idx, slide in enumerate(self.slides):
            if slide.id == updated.id:
                self.slides[idx] = updated
                return
        raise KeyError(f"Slide {updated.id} not found in deck {self.deck_id}")

    def insert_after(self, slide_id: str | None, new_slide: Slide) -> None:
        """Insert ``new_slide`` after ``slide_id`` (or at start when ``None``)."""

        if slide_id is None:
            self.slides.insert(0, new_slide)
            return
        for idx, slide in enumerate(self.slides):
            if slide.id == slide_id:
                self.slides.insert(idx + 1, new_slide)
                return
        raise KeyError(f"Slide {slide_id} not found in deck {self.deck_id}")

    def remove(self, slide_id: str) -> Slide:
        """Remove and return the slide identified by ``slide_id``."""

        for idx, slide in enumerate(self.slides):
            if slide.id == slide_id:
                return self.slides.pop(idx)
        raise KeyError(f"Slide {slide_id} not found in deck {self.deck_id}")

    def reorder(self, ordered_ids: Sequence[str]) -> None:
        """Reorder slides according to ``ordered_ids`` preserving members."""

        if set(ordered_ids) != set(self.slide_ids()):
            raise ValueError("ordered_ids must reference the same slides as the deck")
        id_to_slide = {slide.id: slide for slide in self.slides}
        self.slides = [id_to_slide[slide_id] for slide_id in ordered_ids]

    def extend(self, slides: Iterable[Slide]) -> None:
        """Append ``slides`` to the end of the deck."""

        self.slides.extend(list(slides))

    def _infer_section_context(self, slide_index: int) -> tuple[str | None, str | None]:
        """Infer the section/subsection ids based on the next content slide."""

        next_content_id = ""
        for candidate in self.slides[slide_index + 1 :]:
            if not candidate.is_section_header:
                next_content_id = candidate.id
                break
        if not next_content_id:
            return (None, None)
        for section in self.sections:
            if section.start_slide == next_content_id:
                return (section.id, None)
            for subsection in section.subsections:
                if subsection.start_slide == next_content_id:
                    return (section.id, subsection.id)
        return (None, None)

    def sync_section_headers(self) -> None:
        """Refresh generated content for section header slides."""

        from .section_renderer import build_section_header_content

        for index, slide in enumerate(self.slides):
            if not slide.is_section_header:
                continue
            section_id = slide.section_id
            subsection_id = slide.subsection_id
            if not section_id:
                section_id, subsection_id = self._infer_section_context(index)
            elif not subsection_id:
                inferred_section_id, inferred_subsection_id = (
                    self._infer_section_context(index)
                )
                if inferred_section_id == section_id and inferred_subsection_id:
                    subsection_id = inferred_subsection_id
            slide.section_id = section_id
            slide.subsection_id = subsection_id
            title_html, body_html = build_section_header_content(
                self.sections,
                section_id,
                subsection_id,
            )
            slide.title_html = title_html
            slide.body_html = body_html
            slide.full_html = update_slide_document(
                slide.full_html,
                title_html=slide.title_html,
                body_html=slide.body_html,
                notes_html=slide.notes_html,
                source_html=slide.source_html,
            )


@dataclass(slots=True)
class Subsection:
    """Metadata describing a subsection."""

    id: str
    title: str
    start_slide: str


@dataclass(slots=True)
class Section:
    """Metadata describing a top-level section within a deck."""

    id: str
    title: str
    start_slide: str
    subsections: list[Subsection] = field(default_factory=list)


@dataclass(slots=True)
class IndexSlideEntry:
    """Slide entry as declared in the deck index."""

    file: str
    kind: SlideKind = "normal"
    section_id: str | None = None
    subsection_id: str | None = None

    def to_slide(self) -> Slide:
        """Return a :class:`Slide` stub from the index entry."""

        return Slide(
            id=self.file,
            title_html="",
            body_html="",
            kind=self.kind,
            section_id=self.section_id,
            subsection_id=self.subsection_id,
        )
