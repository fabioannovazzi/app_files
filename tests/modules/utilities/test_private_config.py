from __future__ import annotations

from pathlib import Path

import pytest

from modules.utilities.private_config import resolve_private_config_path


def test_resolve_private_config_path_prefers_specific_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    default_path = tmp_path / "repo" / "config" / "site_page_permissions.json"
    private_dir = tmp_path / "private"
    specific_path = tmp_path / "site-permissions.json"
    monkeypatch.setenv("APP_PRIVATE_CONFIG_DIR", str(private_dir))
    monkeypatch.setenv("SITE_PAGE_PERMISSIONS_FILE", str(specific_path))

    resolved = resolve_private_config_path(
        default_path,
        filename="site_page_permissions.json",
        specific_env_var="SITE_PAGE_PERMISSIONS_FILE",
    )

    assert resolved == specific_path


def test_resolve_private_config_path_uses_private_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    default_path = tmp_path / "repo" / "config" / "presentation_permissions.json"
    private_dir = tmp_path / "private"
    monkeypatch.setenv("APP_PRIVATE_CONFIG_DIR", str(private_dir))

    resolved = resolve_private_config_path(
        default_path,
        filename="presentation_permissions.json",
    )

    assert resolved == private_dir / "presentation_permissions.json"


def test_resolve_private_config_path_rejects_nested_filename(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not contain a path"):
        resolve_private_config_path(
            tmp_path / "permissions.json",
            filename="nested/permissions.json",
        )
