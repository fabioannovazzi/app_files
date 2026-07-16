from __future__ import annotations

import hashlib
from pathlib import Path

from src.slides.pptx_template_manifest import (
    DECK_PPTX_TEMPLATE_FILENAME,
    DECK_PPTX_TEMPLATE_MANIFEST_FILENAME,
)
from src.slides.pptx_template_store import (
    apply_saved_pptx_template_to_deck,
    clear_deck_pptx_template,
    list_saved_pptx_templates,
    load_default_pptx_template_id,
    save_uploaded_pptx_template,
    set_default_pptx_template,
)


def test_save_uploaded_pptx_template_persists_manifest_and_sets_default(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    template_bytes = Path("src/review_brief/pptx_templates/uniform.pptx").read_bytes()

    record = save_uploaded_pptx_template(
        storage_root,
        "user@example.com",
        filename="Corporate Template.pptx",
        file_bytes=template_bytes,
        set_default=True,
    )

    templates = list_saved_pptx_templates(storage_root, "user@example.com")

    assert record.name == "Corporate Template"
    assert record.is_default is True
    assert len(templates) == 1
    assert templates[0].template_id == record.template_id
    assert templates[0].is_default is True
    assert (
        load_default_pptx_template_id(storage_root, "user@example.com")
        == record.template_id
    )
    owner_digest = hashlib.sha256(b"user@example.com").hexdigest()[:12]
    assert (storage_root / "_pptx_templates" / f"user-{owner_digest}").is_dir()


def test_apply_saved_pptx_template_to_deck_uses_selected_or_default_template(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    deck_path = tmp_path / "deck"
    deck_path.mkdir(parents=True, exist_ok=True)
    template_bytes = Path("src/review_brief/pptx_templates/uniform.pptx").read_bytes()
    saved = save_uploaded_pptx_template(
        storage_root,
        "user@example.com",
        filename="Uniform Copy.pptx",
        file_bytes=template_bytes,
        set_default=False,
    )
    set_default_pptx_template(storage_root, "user@example.com", saved.template_id)

    applied_default = apply_saved_pptx_template_to_deck(
        storage_root,
        "user@example.com",
        deck_path=deck_path,
        template_id=None,
        use_uniform_template=False,
    )

    assert applied_default == saved.template_id
    assert (deck_path / DECK_PPTX_TEMPLATE_FILENAME).exists()
    assert (deck_path / DECK_PPTX_TEMPLATE_MANIFEST_FILENAME).exists()

    cleared = apply_saved_pptx_template_to_deck(
        storage_root,
        "user@example.com",
        deck_path=deck_path,
        template_id=None,
        use_uniform_template=True,
    )

    assert cleared is None
    assert not (deck_path / DECK_PPTX_TEMPLATE_FILENAME).exists()
    assert not (deck_path / DECK_PPTX_TEMPLATE_MANIFEST_FILENAME).exists()

    clear_deck_pptx_template(deck_path)
