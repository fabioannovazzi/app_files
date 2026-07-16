from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.projects import permissions as presentation_permissions


def _write_permissions_file(tmp_path: Path, payload: dict[object, object]) -> Path:
    permissions_file = tmp_path / "presentation_permissions.json"
    permissions_file.write_text(json.dumps(payload), encoding="utf-8")
    return permissions_file


def test_get_presentation_permissions_normalizes_emails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    permissions_file = _write_permissions_file(
        tmp_path,
        {
            "Pres1": ["UserA@Example.com", " userb@example.com ", 123],
            "Pres2": [],
            7: ["ignored@example.com"],
        },
    )
    monkeypatch.setattr(
        presentation_permissions, "_PRESENTATION_PERMISSIONS_FILE", permissions_file
    )
    presentation_permissions._load_presentation_permissions.cache_clear()

    permissions = presentation_permissions.get_presentation_permissions()

    assert permissions["pres1"] == {"usera@example.com", "userb@example.com"}
    assert permissions["pres2"] == set()


def test_get_launch_report_permissions_normalizes_emails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permissions_file = _write_permissions_file(
        tmp_path,
        {
            "Launch-One": ["UserA@Example.com", " userb@example.com ", 123],
            "Launch-Two": [],
        },
    )
    monkeypatch.setattr(
        presentation_permissions,
        "_LAUNCH_REPORT_PERMISSIONS_FILE",
        permissions_file,
    )
    presentation_permissions._load_launch_report_permissions.cache_clear()

    permissions = presentation_permissions.get_launch_report_permissions()

    assert permissions["launch-one"] == {"usera@example.com", "userb@example.com"}
    assert permissions["launch-two"] == set()


def test_get_brand_report_permissions_normalizes_emails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permissions_file = _write_permissions_file(
        tmp_path,
        {
            "Brand-One": ["UserA@Example.com", " userb@example.com ", 123],
            "Brand-Two": [],
        },
    )
    monkeypatch.setattr(
        presentation_permissions,
        "_BRAND_REPORT_PERMISSIONS_FILE",
        permissions_file,
    )
    presentation_permissions._load_brand_report_permissions.cache_clear()

    permissions = presentation_permissions.get_brand_report_permissions()

    assert permissions["brand-one"] == {"usera@example.com", "userb@example.com"}
    assert permissions["brand-two"] == set()


def test_build_presentation_listing_marks_allowed_and_denied() -> None:
    documents = [
        presentation_permissions.PresentationDocumentInfo(
            doc_id="deck_one", title="Deck One"
        ),
        presentation_permissions.PresentationDocumentInfo(
            doc_id="deck_two", title="Deck Two"
        ),
    ]
    permissions = {"deck_one": {"user@example.com"}, "deck_two": set()}

    listing = presentation_permissions.build_presentation_listing(
        documents,
        "user@example.com",
        permissions,
    )

    assert [item.allowed for item in listing] == [True, False]
