from __future__ import annotations

import os
from pathlib import Path

import pytest

from modules.utilities import secrets_loader


def test_load_env_prefers_ignored_host_local_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    module_path = repo_root / "modules" / "utilities" / "secrets_loader.py"
    module_path.parent.mkdir(parents=True)
    (repo_root / ".git").mkdir()
    secrets_dir = repo_root / ".secrets"
    secrets_dir.mkdir()
    (secrets_dir / "secrets.toml").write_text(
        'PDP_DATABASE_URL="host=127.0.0.1 port=5433"\n',
        encoding="utf-8",
    )
    (secrets_dir / "secrets.local.toml").write_text(
        'PDP_DATABASE_URL="host=127.0.0.1 port=5432"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(secrets_loader, "__file__", str(module_path))
    monkeypatch.delenv("PDP_DATABASE_URL", raising=False)

    loaded = secrets_loader.load_env_from_secrets_file()

    assert loaded["PDP_DATABASE_URL"] == "host=127.0.0.1 port=5432"
    assert os.environ["PDP_DATABASE_URL"] == "host=127.0.0.1 port=5432"


def test_load_env_uses_project_secrets_when_host_local_file_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    module_path = repo_root / "modules" / "utilities" / "secrets_loader.py"
    module_path.parent.mkdir(parents=True)
    (repo_root / ".git").mkdir()
    secrets_dir = repo_root / ".secrets"
    secrets_dir.mkdir()
    (secrets_dir / "secrets.toml").write_text(
        'PDP_DATABASE_URL="host=127.0.0.1 port=5433"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(secrets_loader, "__file__", str(module_path))
    monkeypatch.delenv("PDP_DATABASE_URL", raising=False)

    loaded = secrets_loader.load_env_from_secrets_file()

    assert loaded["PDP_DATABASE_URL"] == "host=127.0.0.1 port=5433"


def test_load_env_from_secrets_file_overrides_existing_resend_sender(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secrets_path = tmp_path / "secrets.toml"
    secrets_path.write_text(
        'RESEND_FROM_EMAIL="Your App <noreply@updates.mparanza.com>"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEND_FROM_EMAIL", "existing@example.com")

    loaded = secrets_loader.load_env_from_secrets_file(secrets_path)

    assert loaded["RESEND_FROM_EMAIL"] == "Your App <noreply@updates.mparanza.com>"
    assert os.environ["RESEND_FROM_EMAIL"] == "Your App <noreply@updates.mparanza.com>"


def test_load_env_from_secrets_file_overrides_existing_resend_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secrets_path = tmp_path / "secrets.toml"
    secrets_path.write_text(
        "RESEND_API_KEY=REMOVED_CREDENTIAL_VALUE\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEND_API_KEY", "re_old")

    loaded = secrets_loader.load_env_from_secrets_file(secrets_path)

    assert loaded["RESEND_API_KEY"] == "REMOVED_CREDENTIAL_VALUE"
    assert os.environ["RESEND_API_KEY"] == "REMOVED_CREDENTIAL_VALUE"


def test_load_env_from_secrets_file_clears_existing_resend_values_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secrets_path = tmp_path / "secrets.toml"
    secrets_path.write_text('openAiKey="sk-test"\n', encoding="utf-8")
    monkeypatch.setenv("RESEND_API_KEY", "re_old")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "existing@example.com")

    loaded = secrets_loader.load_env_from_secrets_file(secrets_path)

    assert "RESEND_API_KEY" not in loaded
    assert "RESEND_FROM_EMAIL" not in loaded
    assert "RESEND_API_KEY" not in os.environ
    assert "RESEND_FROM_EMAIL" not in os.environ


def test_load_env_from_secrets_file_falls_back_to_simple_kv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secrets_path = tmp_path / "secrets.toml"
    secrets_path.write_text(
        "\n".join(
            [
                "# This intentionally mixes quoted and unquoted values",
                "openAiKey=sk-test",
                'CUSTOM_SETTING="custom-test"',
                "RESEND_API_KEY=re_test # trailing comment",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("openAiKey", raising=False)
    monkeypatch.delenv("CUSTOM_SETTING", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    loaded = secrets_loader.load_env_from_secrets_file(secrets_path)

    assert loaded["openAiKey"] == "sk-test"
    assert loaded["CUSTOM_SETTING"] == "custom-test"
    assert loaded["RESEND_API_KEY"] == "re_test"
    assert os.environ["openAiKey"] == "sk-test"
    assert os.environ["CUSTOM_SETTING"] == "custom-test"
    assert os.environ["RESEND_API_KEY"] == "re_test"
