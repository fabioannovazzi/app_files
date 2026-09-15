from __future__ import annotations

from pathlib import Path

import pytest

from src.slides.models import Deck, Slide
from src.slides.storage import DeckStorage


@pytest.mark.parametrize("payload_kind", ["ocr", "layout", "slide_analysis"])
def test_save_deck_reorders_evidence_by_identity_and_removes_deleted_slides(
    tmp_path: Path, payload_kind: str
) -> None:
    storage = DeckStorage(tmp_path)
    slides = [
        Slide("slide0.html", "First", "First body"),
        Slide("slide1.html", "Deleted", "Deleted body"),
        Slide("slide2.html", "Last", "Last body"),
    ]
    storage.save_deck(Deck("case", slides=slides))
    getattr(storage, f"save_{payload_kind}_payload")(
        "case",
        {
            "source": "reviewed-source.pdf",
            "slides": [
                {"slide_id": "slide0.html", "claim": "First evidence"},
                {"slide_id": "slide1.html", "claim": "Deleted evidence"},
                {
                    "slideId": "slide2.html",
                    "slideNumber": 3,
                    "pageNumber": 3,
                    "claim": "Last evidence",
                },
            ],
        },
    )

    storage.save_deck(Deck("case", slides=[slides[2], slides[0]]))

    assert getattr(storage, f"load_{payload_kind}_payload")("case") == {
        "source": "reviewed-source.pdf",
        "slides": [
            {
                "slideId": "slide2.html",
                "slideNumber": 1,
                "pageNumber": 1,
                "claim": "Last evidence",
            },
            {
                "slide_id": "slide0.html",
                "slide_number": 2,
                "page_number": 2,
                "claim": "First evidence",
            },
        ],
    }
    assert not (tmp_path / "case" / "slide1.html").exists()


def test_import_slide_copies_local_evidence_assets_and_preserves_external_source(
    tmp_path: Path,
) -> None:
    storage = DeckStorage(tmp_path)
    source = tmp_path / "source"
    assets = source / "assets"
    assets.mkdir(parents=True)
    (assets / "chart.svg").write_text("<svg>reviewed chart</svg>")
    (assets / "background.svg").write_text("<svg>background</svg>")
    original = (
        "<html><head><style>.chart {background: url(assets/background.svg)}</style>"
        '</head><body><h1>Reviewed result</h1><div class="slide-body">'
        '<img src="./assets/chart.svg?version=1#plot">'
        '<a href="https://example.org/source">Source</a></div>'
        '<aside class="slide-notes">Forecast excludes financing costs.</aside>'
        '<footer class="slide-source">Reviewed source, page 4.</footer>'
        "</body></html>"
    )
    (source / "slide0.html").write_text(original)

    slide = storage.import_slide("source", "slide0.html", "target")

    assert slide.id == "slide0.html"
    assert "/slides/deck/target/assets/chart.svg?version=1#plot" in slide.full_html
    assert "/slides/deck/target/assets/background.svg" in slide.full_html
    assert "https://example.org/source" in slide.full_html
    assert "Forecast excludes financing costs." in slide.notes_html
    assert "Reviewed source, page 4." in slide.source_html
    assert (tmp_path / "target/assets/chart.svg").read_bytes() == (
        assets / "chart.svg"
    ).read_bytes()
    assert (tmp_path / "target/assets/background.svg").read_bytes() == (
        assets / "background.svg"
    ).read_bytes()
    assert (source / "slide0.html").read_text() == original
