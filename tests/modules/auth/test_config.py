from __future__ import annotations

import pytest

from modules.auth.config import AuthConfig, get_auth_config


def _reset_cache() -> None:
    get_auth_config.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AUTH_ENABLED",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_AUTHORIZED_ORIGINS",
        "GOOGLE_ALLOWED_DOMAINS",
        "GOOGLE_ALLOWED_EMAILS",
        "AUTH_SESSION_SECRET",
        "AUTH_SESSION_TTL_SECONDS",
        "AUTH_COOKIE_SECURE",
    ):
        monkeypatch.delenv(key, raising=False)
    _reset_cache()


def test_get_auth_config_defaults_when_disabled() -> None:
    config = get_auth_config()
    assert isinstance(config, AuthConfig)
    assert config.authentication_enabled is False
    assert config.google_client_id == ""
    assert config.google_authorized_origins == ()
    assert config.allowed_domains == ()
    assert config.allowed_emails == ()
    assert config.session_cookie_name == "mp_auth"
    assert config.session_secret == ""
    assert config.session_ttl_seconds == 12 * 3600
    assert config.cookie_secure is True


def test_get_auth_config_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "yes")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client.apps.googleusercontent.com")
    monkeypatch.setenv(
        "GOOGLE_AUTHORIZED_ORIGINS",
        "https://mparanza.com, http://127.0.0.1:8000 ",
    )
    monkeypatch.setenv("GOOGLE_ALLOWED_DOMAINS", "Example.com, finance.corp ")
    monkeypatch.setenv(
        "GOOGLE_ALLOWED_EMAILS", "user@example.com, reviewer@example.com"
    )
    monkeypatch.setenv("AUTH_SESSION_SECRET", "super-secret")
    monkeypatch.setenv("AUTH_SESSION_TTL_SECONDS", "7200")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    _reset_cache()

    config = get_auth_config()

    assert config.authentication_enabled is True
    assert config.google_client_id == "client.apps.googleusercontent.com"
    assert config.google_authorized_origins == (
        "https://mparanza.com",
        "http://127.0.0.1:8000",
    )
    assert config.allowed_domains == ("example.com", "finance.corp")
    assert config.allowed_emails == ("user@example.com", "reviewer@example.com")
    assert config.session_secret == "super-secret"
    assert config.session_ttl_seconds == 7200
    assert config.cookie_secure is False


def test_get_auth_config_raises_on_missing_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "secret")
    _reset_cache()

    with pytest.raises(ValueError):
        get_auth_config()


def test_get_auth_config_raises_on_invalid_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "secret")
    monkeypatch.setenv("AUTH_SESSION_TTL_SECONDS", "not-a-number")
    _reset_cache()

    with pytest.raises(ValueError):
        get_auth_config()
