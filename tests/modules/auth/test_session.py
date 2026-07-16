from __future__ import annotations

from dataclasses import replace

import pytest

from modules.auth.config import AuthConfig
from modules.auth.google_identity import GoogleUserInfo
from modules.auth.session import (
    AuthenticatedUser,
    InvalidSessionError,
    SessionExpiredError,
    create_session_cookie,
    decode_session_cookie,
)


def _config(**overrides) -> AuthConfig:
    base = AuthConfig(
        google_client_id="client",
        google_authorized_origins=(),
        allowed_domains=(),
        allowed_emails=(),
        authentication_enabled=True,
        session_secret="secret",
        session_cookie_name="mp_auth",
        session_ttl_seconds=300,
        cookie_secure=True,
        magic_link_ttl_seconds=900,
        magic_link_default_redirect="/",
    )
    return replace(base, **overrides)


def _user() -> GoogleUserInfo:
    return GoogleUserInfo(
        email="User@example.com",
        full_name="Test User",
        given_name="Test",
        family_name="User",
        picture="https://example.com/avatar.png",
    )


def test_create_and_decode_session_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config(session_ttl_seconds=120)
    monkeypatch.setattr("modules.auth.session.time.time", lambda: 100)

    cookie_value, expires_at = create_session_cookie(_user(), config)

    assert expires_at == 220

    monkeypatch.setattr("modules.auth.session.time.time", lambda: 150)
    user = decode_session_cookie(cookie_value, config)
    assert isinstance(user, AuthenticatedUser)
    assert user.email == "user@example.com"
    assert user.full_name == "Test User"


def test_decode_session_cookie_rejects_tampering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    monkeypatch.setattr("modules.auth.session.time.time", lambda: 50)
    cookie_value, _ = create_session_cookie(_user(), config)
    tampered = cookie_value[:-1] + ("A" if cookie_value[-1] != "A" else "B")

    with pytest.raises(InvalidSessionError):
        decode_session_cookie(tampered, config)


def test_decode_session_cookie_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config(session_ttl_seconds=10)
    monkeypatch.setattr("modules.auth.session.time.time", lambda: 10)
    cookie_value, _ = create_session_cookie(_user(), config)
    monkeypatch.setattr("modules.auth.session.time.time", lambda: 40)

    with pytest.raises(SessionExpiredError):
        decode_session_cookie(cookie_value, config)
