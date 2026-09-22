from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONTRIBUTORS_PAGE = ROOT / "static" / "shared" / "vera" / "index.html"


def test_vera_contributor_photo_is_present_and_bound_to_its_name() -> None:
    html = CONTRIBUTORS_PAGE.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("#contributors .contributor-list > li")

    assert cards, "The Vera contributors section should contain contributor cards."

    for card in cards:
        name_element = card.select_one(".contributor-name")
        assert name_element is not None, "Each contributor card must have a name."
        name = name_element.get_text(" ", strip=True)

        photos = card.select(".contributor-mark img")
        assert len(photos) == 1, f"{name} must have exactly one profile photo."

        photo = photos[0]
        assert photo.get("src", "").startswith("https://"), (
            f"{name}'s profile photo must have a public image URL."
        )
        assert photo.get("alt") == f"Foto di {name}", (
            f"{name}'s profile photo must be labelled with the same contributor name."
        )
