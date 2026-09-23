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
        photo_src = photo.get("src", "")
        if name == "Francesco Giraldo":
            assert photo_src == (
                "/static/shared/vera/images/contributors/francesco-giraldo.jpg"
            ), "Francesco Giraldo's refreshed photo must use the site-hosted asset."
        if photo_src.startswith("/"):
            local_photo = ROOT / photo_src.lstrip("/")
            assert local_photo.is_file() and local_photo.stat().st_size > 0, (
                f"{name}'s site-hosted profile photo must exist and not be empty."
            )
        else:
            assert photo_src.startswith("https://"), (
                f"{name}'s profile photo must use HTTPS or a valid site-hosted path."
            )
        assert photo.get("alt") == f"Foto di {name}", (
            f"{name}'s profile photo must be labelled with the same contributor name."
        )
