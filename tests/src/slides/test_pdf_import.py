from __future__ import annotations

from pathlib import Path

import fitz  # type: ignore[import-not-found]
import pytest

from src.slides.errors import InvalidDeckError
from src.slides.pdf_import import render_pdf_deck
from src.slides.storage import DeckStorage

__all__: list[str] = []


def _pdf_bytes(*, width: float, height: float) -> bytes:
    document = fitz.open()
    document.new_page(width=width, height=height)
    payload = document.tobytes()
    document.close()
    return payload


def test_render_pdf_deck_rejects_non_notebooklm_dimensions(tmp_path: Path) -> None:
    storage = DeckStorage(tmp_path)
    deck_id = "invalid-dimensions"

    with pytest.raises(
        InvalidDeckError,
        match="Uploaded PDF must use NotebookLM slide pages",
    ):
        render_pdf_deck(
            deck_id,
            storage.root / deck_id,
            _pdf_bytes(width=1280, height=720),
            storage,
            prompt_style="uniform",
            owner_email=None,
            shared_with=[],
        )


def test_render_pdf_deck_persists_valid_notebooklm_page(tmp_path: Path) -> None:
    storage = DeckStorage(tmp_path)
    deck_id = "valid-dimensions"
    deck_path = storage.root / deck_id

    render_pdf_deck(
        deck_id,
        deck_path,
        _pdf_bytes(width=1376, height=768),
        storage,
        prompt_style="uniform",
        owner_email=None,
        shared_with=[],
    )

    deck = storage.load_deck(deck_id)
    assert len(deck.slides) == 1
    assert (deck_path / "source.pdf").is_file()
    assert len(list((deck_path / "assets").glob("*.png"))) == 1
    assert f"/slides/deck/{deck_id}/assets/" in deck.slides[0].body_html
