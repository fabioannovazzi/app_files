from __future__ import annotations

import pytest

from modules.notifications import resend_client


def test_is_resend_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
    assert resend_client.is_resend_configured() is False

    monkeypatch.setenv("RESEND_API_KEY", "key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Sender <sender@example.com>")
    assert resend_client.is_resend_configured() is True


def test_is_resend_configured_rejects_placeholder_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "key")
    monkeypatch.setenv(
        "RESEND_FROM_EMAIL", "Your App <noreply@updates.mparanza.com>"
    )

    assert resend_client.is_resend_configured() is False


def test_send_plain_text_email_requires_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
    assert (
        resend_client.send_plain_text_email("user@example.com", "Hi", "Body") is False
    )


def test_send_plain_text_email_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Sender <sender@example.com>")

    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, json: dict, headers: dict, timeout: float):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return DummyResponse()

    monkeypatch.setattr(resend_client.requests, "post", fake_post)

    assert resend_client.send_plain_text_email("user@example.com", "Hi", "Body")
    assert captured["json"]["to"] == ["user@example.com"]
    assert captured["json"]["subject"] == "Hi"
    assert captured["json"]["text"] == "Body"
    assert "Mparanza" in captured["json"]["html"]
    assert "Body" in captured["json"]["html"]


def test_send_plain_text_email_strips_wrapping_quotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", '"key"')
    monkeypatch.setenv("RESEND_FROM_EMAIL", '"Sender <sender@example.com>"')

    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, json: dict, headers: dict, timeout: float):
        captured["json"] = json
        captured["headers"] = headers
        return DummyResponse()

    monkeypatch.setattr(resend_client.requests, "post", fake_post)

    assert resend_client.send_plain_text_email("user@example.com", "Hi", "Body")
    assert captured["json"]["from"] == "Sender <sender@example.com>"
    assert captured["headers"]["Authorization"] == "Bearer key"


def test_send_email_includes_html_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Sender <sender@example.com>")

    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, json: dict, headers: dict, timeout: float):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr(resend_client.requests, "post", fake_post)

    assert resend_client.send_email(
        "user@example.com",
        "Hi",
        "Plain body",
        html_body="<p>HTML body</p>",
    )
    assert captured["json"]["text"] == "Plain body"
    assert captured["json"]["html"] == "<p>HTML body</p>"


def test_send_email_includes_reply_to(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Sender <sender@example.com>")

    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, json: dict, headers: dict, timeout: float):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr(resend_client.requests, "post", fake_post)

    assert resend_client.send_email(
        "user@example.com",
        "Hi",
        "Plain body",
        reply_to="Example User <user@example.com>",
    )
    assert captured["json"]["reply_to"] == "Example User <user@example.com>"


def test_send_email_generates_cta_button_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Sender <sender@example.com>")

    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, json: dict, headers: dict, timeout: float):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr(resend_client.requests, "post", fake_post)

    assert resend_client.send_email(
        "user@example.com",
        "Results ready",
        "Open the link below.",
        cta_label="Open results",
        cta_url="https://mparanza.com/jobs/123",
    )
    assert "Open results" in captured["json"]["html"]
    assert "https://mparanza.com/jobs/123" in captured["json"]["html"]
