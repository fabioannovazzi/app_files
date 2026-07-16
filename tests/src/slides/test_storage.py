from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup  # type: ignore[import]

from src.slides.models import Deck, Slide
from src.slides.storage import DeckStorage


def _make_deck(deck_id: str) -> Deck:
    return Deck(
        deck_id=deck_id,
        slides=[
            Slide(id="slide0.html", title_html="<strong>Intro</strong>", body_html="<p>Welcome</p>"),
            Slide(id="slide1.html", title_html="Numbers", body_html="<ul><li>1</li></ul>"),
        ],
    )


def test_save_deck_writes_files(tmp_path: Path) -> None:
    storage = DeckStorage(tmp_path)
    deck = _make_deck("deckA")

    storage.save_deck(deck)

    deck_dir = tmp_path / "deckA"
    assert (deck_dir / "index.html").exists()
    assert (deck_dir / "index.json").exists()
    html = (deck_dir / "slide0.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body
    assert body is not None
    container = body.select_one(".slide-container")
    assert container is not None
    title_element = container.select_one('[data-role="title"]')
    assert title_element is not None
    assert "<strong>Intro</strong>" in title_element.decode_contents()
    slide_body = container.select_one(".slide-body")
    assert slide_body is not None
    assert "<p>Welcome</p>" in slide_body.decode_contents()
    assert container.select_one("aside.slide-notes") is not None
    assert container.select_one("footer.slide-source") is not None
    assert soup.title is not None and soup.title.string == "Intro"


def test_save_deck_removes_deleted_slides(tmp_path: Path) -> None:
    storage = DeckStorage(tmp_path)
    deck = _make_deck("deckB")
    storage.save_deck(deck)

    # remove one slide and save again
    deck.slides.pop()
    storage.save_deck(deck)

    deck_dir = tmp_path / "deckB"
    remaining = sorted(p.name for p in deck_dir.glob("*.html") if p.name != "index.html")
    assert remaining == ["slide0.html"]


def test_list_slide_ids(tmp_path: Path) -> None:
    storage = DeckStorage(tmp_path)
    storage.save_deck(_make_deck("deckC"))

    assert storage.list_slide_ids("deckC") == ["slide0.html", "slide1.html"]


def test_list_slide_ids_includes_htm_files(tmp_path: Path) -> None:
    storage = DeckStorage(tmp_path)
    deck_dir = tmp_path / "deckHtm"
    deck_dir.mkdir()
    (deck_dir / "index.HTM").write_text("<html><body></body></html>", encoding="utf-8")
    (deck_dir / "slideA.HTM").write_text("<html><body>One</body></html>", encoding="utf-8")

    assert storage.list_slide_ids("deckHtm") == ["slideA.HTM"]


def test_list_decks_detects_case_insensitive_index(tmp_path: Path) -> None:
    deck_dir = tmp_path / "DeckUpper"
    deck_dir.mkdir()
    (deck_dir / "INDEX.HTML").write_text("<html><body></body></html>", encoding="utf-8")
    storage = DeckStorage(tmp_path)

    assert storage.list_decks() == ["DeckUpper"]
