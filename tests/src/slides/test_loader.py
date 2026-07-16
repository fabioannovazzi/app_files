from __future__ import annotations

import json
from pathlib import Path

from src.slides.loader import iter_deck_ids, load_deck, load_slide, read_index
from src.slides.models import Deck


def _write_slide(path: Path, heading: str, body: str) -> None:
    path.write_text(
        f"<!DOCTYPE html>\n<html><body><h1>{heading}</h1>{body}</body></html>",
        encoding="utf-8",
    )


def test_iter_deck_ids_handles_case_insensitive_indexes(tmp_path: Path) -> None:
    upper_dir = tmp_path / "DeckUpper"
    upper_dir.mkdir()
    (upper_dir / "INDEX.HTML").write_text(
        "<html><body></body></html>", encoding="utf-8"
    )
    htm_dir = tmp_path / "DeckHtm"
    htm_dir.mkdir()
    (htm_dir / "index.HTM").write_text("<html><body></body></html>", encoding="utf-8")

    assert set(iter_deck_ids(tmp_path)) == {"DeckUpper", "DeckHtm"}


def test_read_index_from_html(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deckA"
    deck_dir.mkdir()
    (deck_dir / "index.html").write_text(
        '<html><body><ul><li><a href="slide0.html">s0</a></li>'
        '<li><a href="slide1.html">s1</a></li></ul></body></html>',
        encoding="utf-8",
    )
    _write_slide(deck_dir / "slide0.html", "Title", "<p>Body</p>")
    _write_slide(deck_dir / "slide1.html", "Second", "<div>Next</div>")

    entries, sections, _, _, _ = read_index(deck_dir)

    assert [entry.file for entry in entries] == ["slide0.html", "slide1.html"]
    assert sections == []


def test_read_index_supports_htm_extension(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deckHtm"
    deck_dir.mkdir()
    (deck_dir / "index.HTM").write_text(
        '<html><body><a href="slideA.HTM">alpha</a></body></html>',
        encoding="utf-8",
    )
    (deck_dir / "slideA.HTM").write_text(
        "<html><body>One</body></html>", encoding="utf-8"
    )

    entries, sections, _, _, _ = read_index(deck_dir)

    assert [entry.file for entry in entries] == ["slideA.HTM"]
    assert sections == []


def test_read_index_from_script_array(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deckScript"
    slides_dir = deck_dir / "slides"
    slides_dir.mkdir(parents=True)
    (deck_dir / "index.html").write_text(
        """
        <html><body>
        <script>
        const slides = [
            "slides/slide2.html",
            //"slides/unused.html",
            "slides/slide1.html"
        ];
        </script>
        </body></html>
        """,
        encoding="utf-8",
    )
    _write_slide(slides_dir / "slide1.html", "Second", "<p>Body</p>")
    _write_slide(slides_dir / "slide2.html", "First", "<p>Intro</p>")

    entries, sections, _, _, _ = read_index(deck_dir)

    assert [entry.file for entry in entries] == [
        "slides/slide2.html",
        "slides/slide1.html",
    ]
    assert sections == []


def test_read_index_normalizes_script_paths(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deckPaths"
    slides_dir = deck_dir / "slides" / "nested"
    slides_dir.mkdir(parents=True)
    (deck_dir / "slides" / "slide1.html").write_text(
        "<html><body>One</body></html>", encoding="utf-8"
    )
    (slides_dir / "slide2.html").write_text(
        "<html><body>Two</body></html>", encoding="utf-8"
    )
    (deck_dir / "index.html").write_text(
        """
        <html><body>
        <script>
        const slides = [
            "/slides\\slide1.html?cache=123#section",
            "./slides/../slides/nested/slide2.html",
            "C:/slides/slide1.html"
        ];
        </script>
        </body></html>
        """,
        encoding="utf-8",
    )

    entries, _, _, _, _ = read_index(deck_dir)

    assert [entry.file for entry in entries] == [
        "slides/slide1.html",
        "slides/nested/slide2.html",
    ]


def test_read_index_falls_back_to_filesystem(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deckFallback"
    slides_dir = deck_dir / "slides"
    slides_dir.mkdir(parents=True)
    (deck_dir / "index.html").write_text(
        "<html><body><p>No links here</p></body></html>",
        encoding="utf-8",
    )
    _write_slide(slides_dir / "beta.html", "Beta", "<p>Body</p>")
    _write_slide(slides_dir / "alpha.html", "Alpha", "<p>Body</p>")

    entries, sections, _, _, _ = read_index(deck_dir)

    assert [entry.file for entry in entries] == [
        "slides/alpha.html",
        "slides/beta.html",
    ]
    assert sections == []


def test_load_deck_parses_heading_and_body(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deckB"
    deck_dir.mkdir()
    (deck_dir / "index.html").write_text(
        '<html><body><a href="slide0.html">slide0</a></body></html>',
        encoding="utf-8",
    )
    (deck_dir / "slide0.html").write_text(
        "<!DOCTYPE html>\n<html><body>\n<h2><em>Important</em></h2>"
        "<section><p>Numbers 123 stay</p></section>\n</body></html>",
        encoding="utf-8",
    )

    deck = load_deck("deckB", tmp_path)

    assert isinstance(deck, Deck)
    assert deck.deck_id == "deckB"
    assert len(deck.slides) == 1
    slide = deck.slides[0]
    assert slide.title_html == "<em>Important</em>"
    assert "Numbers" in slide.body_html
    assert "<h2" not in slide.body_html


def test_read_index_from_json(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deckC"
    deck_dir.mkdir()
    (deck_dir / "index.json").write_text(
        '{\n  "slides": ["slide0.html", "slide1.html"]\n}\n',
        encoding="utf-8",
    )
    for name in ("slide0.html", "slide1.html"):
        _write_slide(deck_dir / name, name, "<p>Body</p>")

    entries, sections, _, _, _ = read_index(deck_dir)
    assert [entry.file for entry in entries] == ["slide0.html", "slide1.html"]
    assert sections == []
    slide = load_slide(deck_dir, "slide0.html")
    assert slide.title_html == "slide0.html"


def test_read_index_missing_prompt_style_defaults_to_uniform(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deckPromptStyle"
    deck_dir.mkdir()
    index_payload = {"slides": ["slide0.html"]}
    (deck_dir / "index.json").write_text(
        json.dumps(index_payload, indent=2), encoding="utf-8"
    )
    _write_slide(deck_dir / "slide0.html", "Title", "<p>Body</p>")

    entries, sections, prompt_style, _, _ = read_index(deck_dir)

    assert [entry.file for entry in entries] == ["slide0.html"]
    assert sections == []
    assert prompt_style == "uniform"
    deck = load_deck("deckPromptStyle", tmp_path)
    assert deck.prompt_style == "uniform"


def test_read_index_includes_access_metadata(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deckAccess"
    deck_dir.mkdir()
    index_payload = {
        "slides": ["slide0.html"],
        "ownerEmail": "owner@example.com",
        "sharedWith": ["shared@example.com", "shared@example.com", 123, "  "],
    }
    (deck_dir / "index.json").write_text(
        json.dumps(index_payload, indent=2), encoding="utf-8"
    )
    _write_slide(deck_dir / "slide0.html", "Title", "<p>Body</p>")

    entries, sections, prompt_style, owner_email, shared_with = read_index(deck_dir)

    assert [entry.file for entry in entries] == ["slide0.html"]
    assert sections == []
    assert prompt_style == "uniform"
    assert owner_email == "owner@example.com"
    assert shared_with == ["shared@example.com"]


def test_load_deck_with_sections(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deckSections"
    deck_dir.mkdir()
    _write_slide(deck_dir / "slide1.html", "Intro", "<p>First body</p>")
    _write_slide(deck_dir / "slide2.html", "Second", "<p>Next</p>")
    index_data = {
        "slides": [
            {"file": "header-a.html", "kind": "sectionHeader", "sectionId": "A"},
            "slide1.html",
            {"file": "header-b.html", "kind": "sectionHeader", "sectionId": "B"},
            "slide2.html",
        ],
        "sections": [
            {
                "id": "A",
                "title": "A – Market",
                "startSlide": "slide1.html",
                "subsections": [],
            },
            {
                "id": "B",
                "title": "B – Customers",
                "startSlide": "slide2.html",
                "subsections": [],
            },
        ],
    }
    (deck_dir / "index.json").write_text(
        json.dumps(index_data, indent=2),
        encoding="utf-8",
    )

    deck = load_deck("deckSections", tmp_path)

    assert deck.sections[0].title == "A – Market"
    header_slide = deck.slides[0]
    assert header_slide.kind == "sectionHeader"
    assert "section-header__sections" in header_slide.body_html
    assert "is-current" in header_slide.body_html

    deck.sections[0].title = "A – Updated"
    deck.sync_section_headers()
    assert "A – Updated" in deck.slides[0].body_html

    deck.sections = list(reversed(deck.sections))
    deck.sync_section_headers()
    body_html = deck.slides[0].body_html
    assert body_html.index("B – Customers") < body_html.index("A – Updated")
