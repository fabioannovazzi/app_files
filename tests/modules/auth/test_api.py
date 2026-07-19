from __future__ import annotations

from dataclasses import replace
import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from modules.auth.api import (
    auth_page,
    router as auth_router,
    site_router as auth_site_router,
)
from modules.auth.config import AuthConfig
from modules.auth.google_identity import GoogleUserInfo
from modules.auth.magic_links import MagicLinkRecord


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
        cookie_secure=False,
        magic_link_ttl_seconds=900,
        magic_link_default_redirect="/app",
    )
    return replace(base, **overrides)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(auth_site_router)
    return app


def test_login_sets_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    user = GoogleUserInfo(email="user@example.com", full_name="User Example")
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    monkeypatch.setattr(
        "modules.auth.api.verify_google_identity_token",
        lambda *args, **kwargs: user,
    )
    client = TestClient(_build_app())

    response = client.post("/auth/login", json={"credential": "token"})

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
    assert config.session_cookie_name in response.cookies


def test_session_endpoint_returns_current_user(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    user = GoogleUserInfo(email="user@example.com", full_name="User Example")
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    monkeypatch.setattr(
        "modules.auth.api.verify_google_identity_token",
        lambda *args, **kwargs: user,
    )
    app = _build_app()
    client = TestClient(app)

    login_response = client.post("/auth/login", json={"credential": "token"})
    assert login_response.status_code == 200

    session_response = client.get("/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["email"] == "user@example.com"


def test_session_endpoint_rejects_invalid_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    client = TestClient(_build_app())
    client.cookies.set(config.session_cookie_name, "invalid")

    response = client.get("/auth/session")
    assert response.status_code == 401


def test_logout_clears_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    user = GoogleUserInfo(email="user@example.com")
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    monkeypatch.setattr(
        "modules.auth.api.verify_google_identity_token",
        lambda *args, **kwargs: user,
    )
    client = TestClient(_build_app())

    login_response = client.post("/auth/login", json={"credential": "token"})
    assert login_response.status_code == 200
    assert client.cookies.get(config.session_cookie_name)

    logout_response = client.post("/auth/logout")
    assert logout_response.status_code == 200
    assert config.session_cookie_name not in client.cookies


def test_magic_link_request_sends_email(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    sent: dict[str, str | None] = {}
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    monkeypatch.setattr("modules.auth.api.is_resend_configured", lambda: True)
    monkeypatch.setattr(
        "modules.auth.api.issue_magic_link", lambda *a, **k: "magictoken"
    )

    def fake_send(
        email: str,
        subject: str,
        text_body: str,
        *,
        html_body: str | None = None,
    ) -> bool:
        sent["email"] = email
        sent["subject"] = subject
        sent["text_body"] = text_body
        sent["html_body"] = html_body
        return True

    monkeypatch.setattr("modules.auth.api.send_email", fake_send)
    client = TestClient(_build_app())

    response = client.post("/auth/magic/request", json={"email": "user@example.com"})

    assert response.status_code == 200
    assert response.json() == {"status": "sent"}
    assert sent["email"] == "user@example.com"
    assert sent["subject"] == "Sign in to Mparanza"
    assert "magictoken" in (sent["text_body"] or "")
    assert "Mparanza sign-in request" in (sent["text_body"] or "")
    assert "Sign in to Mparanza" in (sent["html_body"] or "")
    assert "magictoken" in (sent["html_body"] or "")


def test_magic_link_verify_sets_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    record = MagicLinkRecord(
        email="user@example.com",
        expires_at=time.time() + 100,
        redirect_path="/workspace",
    )
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    monkeypatch.setattr("modules.auth.api._consume_magic_token", lambda token: record)
    client = TestClient(_build_app())

    response = client.post("/auth/magic/verify", json={"token": "abc"})

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "user@example.com"
    assert data["redirect_path"] == "/workspace"
    assert config.session_cookie_name in response.cookies


def test_magic_link_consume_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    record = MagicLinkRecord(
        email="user@example.com",
        expires_at=time.time() + 100,
        redirect_path="/workspace",
    )
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    monkeypatch.setattr("modules.auth.api._consume_magic_token", lambda token: record)
    client = TestClient(_build_app(), follow_redirects=False)

    response = client.get("/auth/magic/consume", params={"token": "abc"})

    assert response.status_code == 307
    assert response.headers["location"] == "/workspace"
    assert config.session_cookie_name in response.cookies


def test_magic_link_consume_invalid_token_renders_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    monkeypatch.setattr(
        "modules.auth.api._consume_magic_token",
        lambda token: (_ for _ in ()).throw(
            HTTPException(
                status_code=400,
                detail="Magic link is invalid or already used.",
            )
        ),
    )
    client = TestClient(_build_app())

    response = client.get("/auth/magic/consume", params={"token": "abc", "lang": "en"})

    assert response.status_code == 400
    assert "Request a new link" in response.text
    assert "family=Instrument+Sans" in response.text
    assert 'font-family: "Instrument Sans", sans-serif' in response.text
    assert 'font-family: "Inter"' not in response.text


def test_auth_page_embeds_redirect_target(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/page",
            "headers": [],
            "query_string": b"lang=it&redirect=%2Fslides%2Fpage%3Flang%3Dit",
        },
        receive=lambda: None,
    )

    response = auth_page(request)

    assert response.status_code == 200
    assert response.context["redirect_path"] == "/slides/page?lang=it"
    assert response.context["page_label"] == "Accedi"
    assert response.context["copy"]["magic_link_email_label"] == "Email"
    assert response.context["copy"]["magic_link_button"] == "Invia link"


def test_auth_page_hides_google_button_on_unconfigured_local_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(google_authorized_origins=())
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/page",
            "headers": [(b"host", b"127.0.0.1:8000")],
            "query_string": b"redirect=%2Fcase-notes%2Fvoice",
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
        },
        receive=lambda: None,
    )

    response = auth_page(request)

    assert response.context["google_client_id"] == ""
    assert response.context["redirect_path"] == "/case-notes/voice"


def test_auth_page_keeps_google_button_for_configured_local_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(google_authorized_origins=("http://127.0.0.1:8000",))
    monkeypatch.setattr("modules.auth.api.get_auth_config", lambda: config)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/page",
            "headers": [(b"host", b"127.0.0.1:8000")],
            "query_string": b"",
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
        },
        receive=lambda: None,
    )

    response = auth_page(request)

    assert response.context["google_client_id"] == "client"
