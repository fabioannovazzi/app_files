from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest

from scripts import deploy_private_permissions
from scripts.deploy_private_permissions import PermissionConfigError


def _write_permissions(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "clara": [
                    "person@example.com",
                    {
                        "email": "temporary@example.com",
                        "expires_at": "2030-01-01T00:00:00Z",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def test_validate_permission_file_returns_non_sensitive_counts(tmp_path: Path) -> None:
    permissions_path = tmp_path / "site_page_permissions.json"
    _write_permissions(permissions_path)

    summary = deploy_private_permissions.validate_permission_file(permissions_path)

    assert summary.path == permissions_path
    assert summary.group_count == 1
    assert summary.entry_count == 2


def test_validate_permission_file_rejects_non_list_group(tmp_path: Path) -> None:
    permissions_path = tmp_path / "site_page_permissions.json"
    permissions_path.write_text(json.dumps({"clara": "invalid"}), encoding="utf-8")

    with pytest.raises(PermissionConfigError, match="must contain a list"):
        deploy_private_permissions.validate_permission_file(permissions_path)


def test_validate_permission_file_rejects_unsafe_filename(tmp_path: Path) -> None:
    permissions_path = tmp_path / "bad name_permissions.json"
    _write_permissions(permissions_path)

    with pytest.raises(PermissionConfigError, match="filename"):
        deploy_private_permissions.validate_permission_file(permissions_path)


def test_deploy_permission_files_stages_then_atomically_publishes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    permissions_path = tmp_path / "site_page_permissions.json"
    _write_permissions(permissions_path)
    commands: list[tuple[list[str], bool]] = []

    def _record_run(command: list[str], *, check: bool = True) -> None:
        commands.append((command, check))

    monkeypatch.setattr(deploy_private_permissions, "_run", _record_run)
    monkeypatch.setattr(
        deploy_private_permissions.secrets, "token_hex", lambda _length: "fixed"
    )

    summaries = deploy_private_permissions.deploy_permission_files(
        [permissions_path],
        host="myserver",
        remote_dir=PurePosixPath(".config/mparanza"),
    )

    assert len(summaries) == 1
    assert commands == [
        (
            [
                "ssh",
                "myserver",
                "install -d -m 700 .config/mparanza",
            ],
            True,
        ),
        (
            [
                "scp",
                str(permissions_path),
                "myserver:.config/mparanza/.site_page_permissions.json.fixed.tmp",
            ],
            True,
        ),
        (
            [
                "ssh",
                "myserver",
                "chmod 600 .config/mparanza/.site_page_permissions.json.fixed.tmp"
                " && mv -f .config/mparanza/.site_page_permissions.json.fixed.tmp"
                " .config/mparanza/site_page_permissions.json",
            ],
            True,
        ),
    ]
    assert "person@example.com" not in repr(commands)


def test_deploy_permission_files_rejects_unsafe_host(tmp_path: Path) -> None:
    permissions_path = tmp_path / "site_page_permissions.json"
    _write_permissions(permissions_path)

    with pytest.raises(PermissionConfigError, match="SSH host"):
        deploy_private_permissions.deploy_permission_files(
            [permissions_path],
            host="host;command",
            remote_dir=PurePosixPath(".config/mparanza"),
        )


def test_deploy_permission_files_rejects_parent_traversal(tmp_path: Path) -> None:
    permissions_path = tmp_path / "site_page_permissions.json"
    _write_permissions(permissions_path)

    with pytest.raises(PermissionConfigError, match="traverse parents"):
        deploy_private_permissions.deploy_permission_files(
            [permissions_path],
            host="myserver",
            remote_dir=PurePosixPath("../private-config"),
        )


def test_deploy_permission_files_rejects_unscoped_relative_directory(
    tmp_path: Path,
) -> None:
    permissions_path = tmp_path / "site_page_permissions.json"
    _write_permissions(permissions_path)

    with pytest.raises(PermissionConfigError, match="under '.config'"):
        deploy_private_permissions.deploy_permission_files(
            [permissions_path],
            host="myserver",
            remote_dir=PurePosixPath("private-config"),
        )
