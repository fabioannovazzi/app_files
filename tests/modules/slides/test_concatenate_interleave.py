from __future__ import annotations

import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from src.slides.models import Deck, Slide
from src.slides.storage import DeckStorage

__all__: list[str] = []


def _ensure_jinja_stub() -> None:
    """Provide a minimal jinja2 stub so module imports remain self-contained."""

    if "jinja2" in sys.modules:
        return
    jinja2_stub = types.ModuleType("jinja2")

    def pass_context(func: Callable[..., object]) -> Callable[..., object]:
        return func

    class FileSystemLoader:
        def __init__(self, directory: object) -> None:
            self.directory = directory

    class _Template:
        def render(self, context: dict[str, object]) -> str:
            return ""

    class Environment:
        def __init__(self, **_: object) -> None:
            self.globals: dict[str, object] = {}

        def get_template(self, _name: str) -> _Template:
            return _Template()

    jinja2_stub.pass_context = pass_context
    jinja2_stub.FileSystemLoader = FileSystemLoader
    jinja2_stub.Environment = Environment
    sys.modules["jinja2"] = jinja2_stub


_ensure_jinja_stub()

from modules.slides.api import _concatenate_deck_payload


def _make_deck(deck_id: str, titles: list[str]) -> Deck:
    slides = [
        Slide(
            id=f"slide{index}.html",
            title_html=title,
            body_html=f"<h1 data-role='title'>{title}</h1><p>{title}</p>",
        )
        for index, title in enumerate(titles)
    ]
    return Deck(deck_id=deck_id, slides=slides)


def _save_ocr_payload(storage: DeckStorage, deck_id: str, texts: list[str]) -> None:
    generated_at = datetime.now(UTC).isoformat()
    payload = {
        "deck_id": deck_id,
        "lang": "eng",
        "generated_at": generated_at,
        "slides": [
            {
                "slide_id": f"slide{index}.html",
                "slide_number": index + 1,
                "page_number": index + 1,
                "ocr_text": text,
                "lines": [],
            }
            for index, text in enumerate(texts)
        ],
    }
    storage.save_ocr_payload(deck_id, payload)


def test_interleave_by_index_preserves_duplicate_signatures(tmp_path: Path) -> None:
    storage = DeckStorage(tmp_path)
    duplicate_titles = ["Shared 1", "Shared 2"]
    storage.save_deck(_make_deck("deckA", duplicate_titles))
    storage.save_deck(_make_deck("deckB", duplicate_titles))

    combined_deck, _ = _concatenate_deck_payload(
        "comboOrdered",
        ["deckA", "deckB"],
        storage,
        prompt_style="uniform",
        interleave_by_index=True,
    )

    ordered_titles = [slide.title_html for slide in combined_deck.slides]
    assert ordered_titles == ["Shared 1", "Shared 1", "Shared 2", "Shared 2"]


def test_interleave_by_index_uses_longest_deck_as_guide(tmp_path: Path) -> None:
    storage = DeckStorage(tmp_path)
    deck_a_titles = ["A1", "A2", "A3", "A4"]
    deck_b_titles = ["B1", "B2"]
    deck_c_titles = ["C1", "C2", "C3"]
    storage.save_deck(_make_deck("deckA", deck_a_titles))
    storage.save_deck(_make_deck("deckB", deck_b_titles))
    storage.save_deck(_make_deck("deckC", deck_c_titles))

    combined_deck, _ = _concatenate_deck_payload(
        "comboLongest",
        ["deckA", "deckB", "deckC"],
        storage,
        prompt_style="uniform",
        interleave_by_index=True,
        interleave_guide="longest",
    )

    ordered_titles = [slide.title_html for slide in combined_deck.slides]
    assert ordered_titles == ["A1", "B1", "C1", "A2", "B2", "C2", "A3", "C3", "A4"]


def test_interleave_by_index_uses_shortest_deck_as_guide(tmp_path: Path) -> None:
    storage = DeckStorage(tmp_path)
    deck_a_titles = ["A1", "A2", "A3", "A4"]
    deck_b_titles = ["B1", "B2"]
    deck_c_titles = ["C1", "C2", "C3"]
    storage.save_deck(_make_deck("deckA", deck_a_titles))
    storage.save_deck(_make_deck("deckB", deck_b_titles))
    storage.save_deck(_make_deck("deckC", deck_c_titles))

    combined_deck, _ = _concatenate_deck_payload(
        "comboShortest",
        ["deckA", "deckB", "deckC"],
        storage,
        prompt_style="uniform",
        interleave_by_index=True,
        interleave_guide="shortest",
    )

    ordered_titles = [slide.title_html for slide in combined_deck.slides]
    assert ordered_titles == ["A1", "B1", "C1", "A2", "B2", "C2", "A3", "A4", "C3"]


def test_interleave_by_index_with_ocr_keeps_aligned_order(tmp_path: Path) -> None:
    storage = DeckStorage(tmp_path)
    deck_a_titles = ["Intro", "Overview"]
    deck_b_titles = ["Intro", "Overview"]
    storage.save_deck(_make_deck("deckA", deck_a_titles))
    storage.save_deck(_make_deck("deckB", deck_b_titles))
    _save_ocr_payload(
        storage,
        "deckA",
        ["intro launch plan", "overview market analysis baseline"],
    )
    _save_ocr_payload(
        storage,
        "deckB",
        ["intro launch plan", "overview market analysis baseline"],
    )

    combined_deck, _ = _concatenate_deck_payload(
        "comboAlignedOcr",
        ["deckA", "deckB"],
        storage,
        prompt_style="uniform",
        interleave_by_index=True,
    )

    ordered_titles = [slide.title_html for slide in combined_deck.slides]
    assert ordered_titles == ["Intro", "Intro", "Overview", "Overview"]


def test_interleave_by_index_without_ocr_uses_index_fallback_on_drift(
    tmp_path: Path,
) -> None:
    storage = DeckStorage(tmp_path)
    storage.save_deck(_make_deck("deckA", ["Intro", "Overview", "Results"]))
    storage.save_deck(_make_deck("deckB", ["Intro", "Agenda", "Overview", "Results"]))

    combined_deck, _ = _concatenate_deck_payload(
        "comboDriftNoOcr",
        ["deckA", "deckB"],
        storage,
        prompt_style="uniform",
        interleave_by_index=True,
    )

    ordered_titles = [slide.title_html for slide in combined_deck.slides]
    assert ordered_titles == [
        "Intro",
        "Intro",
        "Overview",
        "Agenda",
        "Results",
        "Overview",
        "Results",
    ]


def test_interleave_by_index_ocr_similarity_corrects_local_drift(
    tmp_path: Path,
) -> None:
    storage = DeckStorage(tmp_path)
    storage.save_deck(_make_deck("deckA", ["Intro", "Overview", "Results"]))
    storage.save_deck(_make_deck("deckB", ["Intro", "Agenda", "Overview", "Results"]))
    _save_ocr_payload(
        storage,
        "deckA",
        [
            "intro launch plan",
            "overview market analysis baseline",
            "results experiment outcome delta",
        ],
    )
    _save_ocr_payload(
        storage,
        "deckB",
        [
            "intro launch plan",
            "agenda logistics timing",
            "overview market analysis baseline",
            "results experiment outcome delta",
        ],
    )

    combined_deck, _ = _concatenate_deck_payload(
        "comboDriftOcr",
        ["deckA", "deckB"],
        storage,
        prompt_style="uniform",
        interleave_by_index=True,
    )

    ordered_titles = [slide.title_html for slide in combined_deck.slides]
    assert ordered_titles == [
        "Intro",
        "Intro",
        "Overview",
        "Overview",
        "Results",
        "Results",
        "Agenda",
    ]
