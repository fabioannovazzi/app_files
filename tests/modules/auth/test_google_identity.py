from __future__ import annotations

import pytest

from modules.auth.google_identity import (
    GoogleUserInfo,
    InvalidGoogleTokenError,
    UnauthorizedGoogleUserError,
    verify_google_identity_token,
)


class DummyRequest:
    """Simple stand-in for :class:`google.auth.transport.requests.Request`."""


@pytest.fixture()
def dummy_request() -> DummyRequest:
    return DummyRequest()


def test_verify_google_identity_token_success_returns_sanitized_info(
    monkeypatch, dummy_request
):
    captured_args: dict[str, object] = {}

    def fake_verify(
        token: str, request: DummyRequest, audience: str
    ) -> dict[str, object]:
        captured_args["token"] = token
        captured_args["request"] = request
        captured_args["audience"] = audience
        return {
            "email": "User@example.com ",
            "email_verified": "true",
            "name": "User Example",
            "given_name": "User",
            "family_name": "Example",
            "picture": "https://example.com/avatar.png",
        }

    monkeypatch.setattr(
        "modules.auth.google_identity.id_token.verify_oauth2_token",
        fake_verify,
    )

    user_info = verify_google_identity_token(
        "token",
        "client-id",
        allowed_domains=("example.com",),
        request=dummy_request,
    )

    assert isinstance(user_info, GoogleUserInfo)
    assert user_info.email == "user@example.com"
    assert user_info.full_name == "User Example"
    assert user_info.given_name == "User"
    assert user_info.family_name == "Example"
    assert user_info.picture == "https://example.com/avatar.png"
    assert captured_args == {
        "token": "token",
        "request": dummy_request,
        "audience": "client-id",
    }


def test_verify_google_identity_token_invalid_token_raises(monkeypatch, dummy_request):
    def fake_verify(token: str, request: DummyRequest, audience: str) -> None:
        raise ValueError("boom")

    monkeypatch.setattr(
        "modules.auth.google_identity.id_token.verify_oauth2_token",
        fake_verify,
    )

    with pytest.raises(InvalidGoogleTokenError):
        verify_google_identity_token(
            "invalid",
            "client-id",
            request=dummy_request,
        )


def test_verify_google_identity_token_unverified_email_raises(
    monkeypatch, dummy_request
):
    def fake_verify(
        token: str, request: DummyRequest, audience: str
    ) -> dict[str, object]:
        return {
            "email": "user@example.com",
            "email_verified": False,
        }

    monkeypatch.setattr(
        "modules.auth.google_identity.id_token.verify_oauth2_token",
        fake_verify,
    )

    with pytest.raises(InvalidGoogleTokenError):
        verify_google_identity_token(
            "token",
            "client-id",
            request=dummy_request,
        )


def test_verify_google_identity_token_missing_email_raises(monkeypatch, dummy_request):
    def fake_verify(
        token: str, request: DummyRequest, audience: str
    ) -> dict[str, object]:
        return {
            "email_verified": True,
        }

    monkeypatch.setattr(
        "modules.auth.google_identity.id_token.verify_oauth2_token",
        fake_verify,
    )

    with pytest.raises(InvalidGoogleTokenError):
        verify_google_identity_token(
            "token",
            "client-id",
            request=dummy_request,
        )


def test_verify_google_identity_token_disallowed_domain_raises(
    monkeypatch, dummy_request
):
    def fake_verify(
        token: str, request: DummyRequest, audience: str
    ) -> dict[str, object]:
        return {
            "email": "user@other.example",
            "email_verified": True,
        }

    monkeypatch.setattr(
        "modules.auth.google_identity.id_token.verify_oauth2_token",
        fake_verify,
    )

    with pytest.raises(UnauthorizedGoogleUserError):
        verify_google_identity_token(
            "token",
            "client-id",
            allowed_domains=("example.com",),
            request=dummy_request,
        )


def test_verify_google_identity_token_disallowed_email_raises(
    monkeypatch, dummy_request
):
    def fake_verify(
        token: str, request: DummyRequest, audience: str
    ) -> dict[str, object]:
        return {
            "email": "user@example.com",
            "email_verified": True,
        }

    monkeypatch.setattr(
        "modules.auth.google_identity.id_token.verify_oauth2_token",
        fake_verify,
    )

    with pytest.raises(UnauthorizedGoogleUserError):
        verify_google_identity_token(
            "token",
            "client-id",
            allowed_emails=("admin@example.com",),
            request=dummy_request,
        )


def test_verify_google_identity_token_allows_listed_email(monkeypatch, dummy_request):
    def fake_verify(
        token: str, request: DummyRequest, audience: str
    ) -> dict[str, object]:
        return {
            "email": "User@Example.com",
            "email_verified": True,
        }

    monkeypatch.setattr(
        "modules.auth.google_identity.id_token.verify_oauth2_token",
        fake_verify,
    )

    user_info = verify_google_identity_token(
        "token",
        "client-id",
        allowed_emails=("user@example.com",),
        request=dummy_request,
    )

    assert user_info.email == "user@example.com"
