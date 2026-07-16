from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_sales_dataset_permissions_allow_all_when_file_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_permissions as permissions_mod

    missing_path = tmp_path / "missing.json"
    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", missing_path
    )
    permissions_mod._load_sales_dataset_permissions.cache_clear()

    permissions = permissions_mod.get_sales_dataset_permissions()
    assert permissions == {}
    assert permissions_mod.sales_dataset_permissions_configured() is False
    assert (
        permissions_mod.is_sales_dataset_allowed(
            "default",
            "user@example.com",
            permissions,
        )
        is True
    )


def test_sales_dataset_permissions_require_explicit_dataset_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = tmp_path / "sales_dataset_permissions.json"
    permissions_path.write_text(
        json.dumps({"default": ["alice@example.com"]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )
    permissions_mod._load_sales_dataset_permissions.cache_clear()

    permissions = permissions_mod.get_sales_dataset_permissions()
    assert permissions_mod.sales_dataset_permissions_configured() is True
    assert (
        permissions_mod.is_sales_dataset_allowed(
            "default",
            "alice@example.com",
            permissions,
        )
        is True
    )
    assert (
        permissions_mod.is_sales_dataset_allowed(
            "default",
            "bob@example.com",
            permissions,
        )
        is False
    )
    assert (
        permissions_mod.is_sales_dataset_allowed(
            "kiko",
            "alice@example.com",
            permissions,
        )
        is False
    )


def test_sales_dataset_permissions_normalize_dataset_aliases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import modules.pdp.sales_dataset_permissions as permissions_mod

    permissions_path = tmp_path / "sales_dataset_permissions.json"
    permissions_path.write_text(
        json.dumps({"default": ["alice@example.com"]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        permissions_mod, "_SALES_DATASET_PERMISSIONS_FILE", permissions_path
    )
    permissions_mod._load_sales_dataset_permissions.cache_clear()

    permissions = permissions_mod.get_sales_dataset_permissions()
    assert (
        permissions_mod.is_sales_dataset_allowed(
            "legacy",
            "alice@example.com",
            permissions,
        )
        is True
    )
