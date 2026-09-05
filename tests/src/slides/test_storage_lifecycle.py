from __future__ import annotations

from pathlib import Path

import pytest

from src.slides.errors import DeckNotFoundError
from src.slides.storage import DeckStorage


def test_archive_moves_deck_and_preserves_its_bytes(tmp_path: Path) -> None:
    deck = tmp_path / "review"
    deck.mkdir()
    (deck / "slide0.html").write_bytes(b"source evidence")

    assert DeckStorage(tmp_path).archive_deck("review") is True

    assert not deck.exists()
    assert (tmp_path / ".trash/review/slide0.html").read_bytes() == b"source evidence"


def test_restore_moves_archived_deck_back(tmp_path: Path) -> None:
    archive = tmp_path / ".trash/review"
    archive.mkdir(parents=True)
    (archive / "slide0.html").write_bytes(b"source evidence")

    assert DeckStorage(tmp_path).restore_deck("review") is True

    assert not archive.exists()
    assert (tmp_path / "review/slide0.html").read_bytes() == b"source evidence"


@pytest.mark.parametrize("method", ["archive_deck", "restore_deck"])
def test_archive_lifecycle_missing_deck_returns_false(
    tmp_path: Path, method: str
) -> None:
    assert getattr(DeckStorage(tmp_path), method)("missing") is False


@pytest.mark.parametrize("method", ["archive_deck", "restore_deck"])
def test_archive_lifecycle_refuses_destination_collision(
    tmp_path: Path, method: str
) -> None:
    (tmp_path / "review").mkdir()
    (tmp_path / ".trash/review").mkdir(parents=True)

    with pytest.raises(DeckNotFoundError):
        getattr(DeckStorage(tmp_path), method)("review")

    assert (tmp_path / "review").is_dir()
    assert (tmp_path / ".trash/review").is_dir()


def test_analysis_payload_roundtrip_preserves_unicode_evidence(tmp_path: Path) -> None:
    (tmp_path / "review").mkdir()
    storage = DeckStorage(tmp_path)
    payload = {"slides": [{"id": "slide0.html", "notes": "Évidence"}]}

    storage.save_slide_analysis_payload("review", payload)

    assert storage.load_slide_analysis_payload("review") == payload


def test_analysis_payload_save_requires_existing_deck(tmp_path: Path) -> None:
    with pytest.raises(DeckNotFoundError):
        DeckStorage(tmp_path).save_slide_analysis_payload("missing", {"slides": []})


def test_analysis_payload_missing_is_unavailable(tmp_path: Path) -> None:
    assert DeckStorage(tmp_path).load_slide_analysis_payload("missing") is None


def test_import_slide_copies_evidence_assets_without_changing_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    (source / "assets").mkdir(parents=True)
    original = (
        '<html><body><h1>Evidence</h1><img src="assets/evidence.png"></body></html>'
    )
    (source / "slide0.html").write_text(original, encoding="utf-8")
    (source / "assets/evidence.png").write_bytes(b"image fixture")

    slide = DeckStorage(tmp_path).import_slide("source", "slide0.html", "target")

    assert slide.id == "slide0.html"
    assert (tmp_path / "target/slide0.html").is_file()
    assert (tmp_path / "target/assets/evidence.png").read_bytes() == b"image fixture"
    assert (source / "slide0.html").read_text(encoding="utf-8") == original
    assert slide.kind == "normal"
    assert slide.section_id is None


def test_import_slide_rejects_missing_source_deck(tmp_path: Path) -> None:
    with pytest.raises(DeckNotFoundError):
        DeckStorage(tmp_path).import_slide("missing", "slide0.html", "target")
