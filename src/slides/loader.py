from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Iterator

from bs4 import BeautifulSoup  # type: ignore[import]

from .errors import DeckNotFoundError, InvalidDeckError, SlideNotFoundError
from .html_normalizer import normalizeSlideHtml
from .models import Deck, IndexSlideEntry, Section, Slide, Subsection
from .notebooklm_style import resolve_prompt_style_key

__all__ = [
    "INDEX_HTML",
    "INDEX_JSON",
    "find_index_file",
    "is_index_filename",
    "iter_deck_ids",
    "load_deck",
    "load_slide",
    "read_index",
]

INDEX_HTML = "index.html"
INDEX_JSON = "index.json"
_INDEX_FILENAMES = ("index.html", "index.htm")
_SLIDE_SUFFIXES = (".html", ".htm")
_SLIDE_PATTERN = re.compile(r"^.*\.html?$", re.IGNORECASE)
_SCRIPT_ARRAY_PATTERN = re.compile(
    r"\bslides\s*=\s*\[(?P<body>.*?)\]", re.IGNORECASE | re.DOTALL
)
_JS_COMMENT_PATTERN = re.compile(r"//.*?$|/\*.*?\*/", re.MULTILINE | re.DOTALL)
_STRING_PATTERN = re.compile(
    r"\"([^\"\\]*(?:\\.[^\"\\]*)*)\"|'([^'\\]*(?:\\.[^'\\]*)*)'",
    re.DOTALL,
)


def iter_deck_ids(root: Path) -> Iterable[str]:
    """Yield deck identifiers available under ``root``."""

    root = Path(root)
    if not root.exists():
        return []
    return (
        entry.name
        for entry in sorted(root.iterdir())
        if entry.is_dir()
        and not entry.name.startswith(".")
        and find_index_file(entry) is not None
    )


def is_index_filename(value: str) -> bool:
    """Return ``True`` when ``value`` matches a deck index file name."""

    return value.lower() in _INDEX_FILENAMES


def find_index_file(deck_path: Path) -> Path | None:
    """Return the preferred index file for ``deck_path`` if it exists."""

    deck_path = Path(deck_path)
    if not deck_path.exists():
        return None
    candidates: list[tuple[int, Path]] = []
    for entry in deck_path.iterdir():
        if not entry.is_file():
            continue
        name = entry.name.lower()
        if name in _INDEX_FILENAMES:
            candidates.append((_INDEX_FILENAMES.index(name), entry))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1].name.lower()))
    return candidates[0][1]


def read_index(
    deck_path: Path,
) -> tuple[list[IndexSlideEntry], list[Section], str, str | None, list[str]]:
    """Return slide entries, section metadata, prompt style, and access metadata."""

    deck_path = Path(deck_path)
    json_path = deck_path / INDEX_JSON
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise InvalidDeckError(f"Invalid JSON in {json_path}") from exc
        slides = data.get("slides")
        if not isinstance(slides, list):
            raise InvalidDeckError(f"Unexpected structure in {json_path}")
        entries = [_parse_slide_entry(item, json_path) for item in slides]
        sections_data = data.get("sections")
        sections = _parse_sections(sections_data, json_path)
        prompt_style_value = data.get("promptStyle")
        prompt_style = resolve_prompt_style_key(
            prompt_style_value if isinstance(prompt_style_value, str) else None
        )
        owner_email = data.get("ownerEmail")
        resolved_owner = owner_email.strip() if isinstance(owner_email, str) else None
        shared_raw = data.get("sharedWith")
        shared_with = _parse_shared_with(shared_raw)
        return (entries, sections, prompt_style, resolved_owner, shared_with)

    index_path = find_index_file(deck_path)
    if index_path is None:
        raise DeckNotFoundError(f"Missing {INDEX_HTML} in {deck_path}")

    html = index_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    slide_files: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if isinstance(href, str):
            _append_slide_candidate(slide_files, seen, href)
    if not slide_files:
        for tag in soup.select("[data-slide]"):
            value = tag.get("data-slide")
            if isinstance(value, str):
                _append_slide_candidate(slide_files, seen, value)
    if not slide_files:
        script_defined = _slides_from_scripts(soup)
        for slide in script_defined:
            _append_slide_candidate(slide_files, seen, slide)
    if not slide_files:
        discovered = _slides_from_filesystem(deck_path)
        for slide in discovered:
            _append_slide_candidate(slide_files, seen, slide)
    entries = [IndexSlideEntry(file=slide_id) for slide_id in slide_files]
    return (entries, [], resolve_prompt_style_key(None), None, [])


def _append_slide_candidate(slide_files: list[str], seen: set[str], value: str) -> None:
    normalized = _normalize_slide_reference(value)
    if not normalized:
        return
    if "/" not in normalized and is_index_filename(normalized):
        return
    if not _SLIDE_PATTERN.match(normalized):
        return
    if normalized in seen:
        return
    slide_files.append(normalized)
    seen.add(normalized)


def _parse_shared_with(value: object) -> list[str]:
    if not value:
        return []
    if not isinstance(value, list):
        return []
    shared_with: list[str] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, str):
            continue
        cleaned = entry.strip()
        if not cleaned or cleaned in seen:
            continue
        shared_with.append(cleaned)
        seen.add(cleaned)
    return shared_with


def _normalize_slide_reference(value: str) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    # Remove URL fragments and query parameters which are not part of the filename
    for separator in ("#", "?"):
        if separator in candidate:
            candidate = candidate.split(separator, 1)[0]
    candidate = candidate.replace("\\", "/")
    # Strip drive letters such as ``C:``
    candidate = re.sub(r"^[A-Za-z]:", "", candidate)
    candidate = candidate.lstrip("/")
    while candidate.startswith("./"):
        candidate = candidate[2:]
    candidate = re.sub(r"/{2,}", "/", candidate)
    parts: list[str] = []
    for part in candidate.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                # Avoid directory traversal outside the deck root
                return None
            parts.pop()
            continue
        parts.append(part)
    normalized = "/".join(parts)
    return normalized or None


def _slides_from_scripts(soup: BeautifulSoup) -> list[str]:
    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        if not text:
            continue
        for match in _SCRIPT_ARRAY_PATTERN.finditer(text):
            body = match.group("body")
            sanitized = _JS_COMMENT_PATTERN.sub("", body)
            slides: list[str] = []
            for string_match in _STRING_PATTERN.finditer(sanitized):
                raw_value = string_match.group(1) or string_match.group(2) or ""
                decoded = bytes(raw_value, "utf-8").decode("unicode_escape")
                if decoded.strip():
                    slides.append(decoded)
            if slides:
                return slides
    return []


def _slides_from_filesystem(deck_path: Path) -> list[str]:
    html_files: list[str] = []
    iterator: Iterator[Path] = deck_path.rglob("*")
    sorted_entries = sorted(
        (entry for entry in iterator if entry.is_file()),
        key=lambda p: p.relative_to(deck_path).as_posix(),
    )
    for entry in sorted_entries:
        if entry.suffix.lower() not in _SLIDE_SUFFIXES:
            continue
        if entry.parent == deck_path and is_index_filename(entry.name):
            continue
        rel_path = entry.relative_to(deck_path).as_posix()
        html_files.append(rel_path)
    return html_files


def load_slide(deck_path: Path, slide_entry: IndexSlideEntry | str) -> Slide:
    """Load ``slide_entry`` from ``deck_path`` and return a :class:`Slide`."""

    deck_path = Path(deck_path)
    if isinstance(slide_entry, str):
        entry = IndexSlideEntry(file=slide_entry)
    else:
        entry = slide_entry

    if entry.kind == "sectionHeader":
        return Slide(
            id=entry.file,
            title_html="",
            body_html="",
            kind="sectionHeader",
            section_id=entry.section_id,
            subsection_id=entry.subsection_id,
        )

    slide_path = deck_path / entry.file
    if not slide_path.exists():
        raise SlideNotFoundError(f"Slide {entry.file} not found in {deck_path}")

    html = slide_path.read_text(encoding="utf-8")
    normalized_html = normalizeSlideHtml(html)
    soup = BeautifulSoup(normalized_html, "html.parser")
    body = soup.body or soup
    container = body.select_one(".slide-container") or body

    title_element = container.select_one('[data-role="title"]')
    if title_element is None:
        title_element = container.select_one(".slide-title")
    if title_element is None:
        title_element = container.select_one(".title")
    if title_element is None:
        title_element = container.find(["h1", "h2"])
    title_html = title_element.decode_contents().strip() if title_element else ""

    body_element = container.select_one(".slide-body") or container
    body_html = body_element.decode_contents().strip()

    notes_element = container.select_one("aside.slide-notes")
    notes_html = notes_element.decode_contents().strip() if notes_element else ""

    source_element = container.select_one("footer.slide-source")
    source_html = source_element.decode_contents().strip() if source_element else ""

    return Slide(
        id=entry.file,
        title_html=title_html,
        body_html=body_html,
        notes_html=notes_html,
        source_html=source_html,
        full_html=normalized_html,
    )


def load_deck(deck_id: str, root: Path) -> Deck:
    """Load ``deck_id`` from ``root`` returning a :class:`Deck`."""

    root = Path(root)
    deck_path = root / deck_id
    if not deck_path.exists():
        raise DeckNotFoundError(f"Deck {deck_id} not found under {root}")

    slide_entries, sections, prompt_style, owner_email, shared_with = read_index(
        deck_path
    )
    slides = [load_slide(deck_path, entry) for entry in slide_entries]
    deck = Deck(
        deck_id=deck_id,
        prompt_style=prompt_style,
        owner_email=owner_email,
        shared_with=shared_with,
        slides=slides,
        sections=sections,
    )
    deck.sync_section_headers()
    return deck


def _parse_slide_entry(item: object, source: Path) -> IndexSlideEntry:
    if isinstance(item, str):
        return IndexSlideEntry(file=item)
    if isinstance(item, dict):
        try:
            raw_file = str(item["file"])
        except KeyError as exc:
            raise InvalidDeckError(
                f"Slide entries in {source} must include 'file'"
            ) from exc
        file = _normalize_slide_reference(raw_file)
        if not file:
            raise InvalidDeckError(
                f"Slide entries in {source} must include a valid 'file'"
            )
        kind_value = str(item.get("kind", "normal"))
        if kind_value not in {"normal", "sectionHeader"}:
            raise InvalidDeckError(f"Unknown slide kind '{kind_value}' in {source}")
        if kind_value == "sectionHeader":
            slide_kind = "sectionHeader"
        else:
            slide_kind = "normal"
        section_id = item.get("sectionId")
        subsection_id = item.get("subsectionId")
        return IndexSlideEntry(
            file=file,
            kind=slide_kind,
            section_id=str(section_id) if isinstance(section_id, str) else None,
            subsection_id=(
                str(subsection_id) if isinstance(subsection_id, str) else None
            ),
        )
    raise InvalidDeckError(f"Unexpected slide entry in {source}: {item!r}")


def _parse_sections(data: object, source: Path) -> list[Section]:
    if not data:
        return []
    if not isinstance(data, list):
        raise InvalidDeckError(f"Sections must be a list in {source}")
    sections: list[Section] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise InvalidDeckError(f"Invalid section entry in {source}: {entry!r}")
        try:
            section_id = str(entry["id"])
            title = str(entry.get("title", ""))
            start_slide = str(entry["startSlide"])
        except KeyError as exc:
            raise InvalidDeckError(
                f"Section entries in {source} require 'id' and 'startSlide'"
            ) from exc
        subsections_data = entry.get("subsections", [])
        subsections = _parse_subsections(subsections_data, source)
        sections.append(
            Section(
                id=section_id,
                title=title,
                start_slide=start_slide,
                subsections=subsections,
            )
        )
    return sections


def _parse_subsections(data: object, source: Path) -> list[Subsection]:
    if not data:
        return []
    if not isinstance(data, list):
        raise InvalidDeckError(f"Subsections must be a list in {source}")
    subsections: list[Subsection] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise InvalidDeckError(f"Invalid subsection entry in {source}: {entry!r}")
        try:
            subsection_id = str(entry["id"])
            title = str(entry.get("title", ""))
            start_slide = str(entry["startSlide"])
        except KeyError as exc:
            raise InvalidDeckError(
                f"Subsection entries in {source} require 'id' and 'startSlide'"
            ) from exc
        subsections.append(
            Subsection(id=subsection_id, title=title, start_slide=start_slide)
        )
    return subsections
