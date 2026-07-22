from __future__ import annotations

import pytest

import modules.notifications.notifier as notifier


def test_notify_finished_sends_email_and_pings(monkeypatch):
    # Arrange
    calls: list[tuple] = []

    def fake_ping(_notifier, label: str) -> None:
        calls.append(("ping", label))

    def fake_pretty(seconds: float) -> str:
        assert seconds == 125  # sanity: elapsed seconds passed through
        return "PRETTY"

    def fake_send_email(
        dest: str, pretty: str, step: str, lang: str, link=None
    ) -> None:
        calls.append(("email", dest, pretty, step, lang, link))

    monkeypatch.setattr(notifier, "_ping_browser", fake_ping)
    monkeypatch.setattr(notifier, "_pretty", fake_pretty)
    monkeypatch.setattr(notifier, "_send_email", fake_send_email)
    monkeypatch.setattr(notifier, "is_resend_configured", lambda: True)

    session = {"notify_email": "user@example.com"}

    # Act
    notifier.notify_finished(125, "statements", session)

    # Assert
    # Browser is pinged first with the mapped label for 'statements'
    assert calls[0] == ("ping", "reconciliation")
    # Email receives the pretty string and original step
    assert ("email", "user@example.com", "PRETTY", "statements", "en", None) in calls


def test_notify_finished_unknown_step_no_contacts(monkeypatch):
    # Arrange
    ping_labels: list[str] = []
    pretty_args: list[float] = []
    email_calls: list[tuple] = []

    monkeypatch.setattr(
        notifier, "_ping_browser", lambda _notifier, label: ping_labels.append(label)
    )

    def fake_pretty(seconds: float) -> str:
        pretty_args.append(seconds)
        return "SENTINEL"

    monkeypatch.setattr(notifier, "_pretty", fake_pretty)
    monkeypatch.setattr(
        notifier,
        "_send_email",
        lambda dest, pretty, step, lang, link=None: email_calls.append(
            (dest, pretty, step, lang, link)
        ),
    )

    # Act
    notifier.notify_finished(0, "customstep", {})

    # Assert
    assert ping_labels == ["Customstep"]  # default capitalization for unknown step
    assert pretty_args == [0]
    assert email_calls == []


@pytest.mark.parametrize(
    "session,expected",
    [
        ({"notify_email": "user@example.com"}, True),
        ({}, False),
    ],
)
def test_notify_failed_sends_error_email_conditionally(monkeypatch, session, expected):
    # Arrange
    sent: list[tuple[str, str]] = []

    def fake_error_email(dest: str, step: str, lang: str, link=None) -> None:
        sent.append((dest, step, lang, link))

    monkeypatch.setattr(notifier, "_send_error_email", fake_error_email)

    # Act
    notifier.notify_failed("entries", session)

    # Assert
    if expected:
        assert sent == [("user@example.com", "entries", "en", None)]
    else:
        assert sent == []


@pytest.mark.parametrize(
    ("language_alias", "expected_language"),
    (("ita", "it"), ("spa", "es"), ("español", "es")),
)
def test_notify_finished_uses_session_language(
    monkeypatch, language_alias: str, expected_language: str
):
    langs: list[str] = []

    monkeypatch.setattr(notifier, "_ping_browser", lambda _notifier, label: None)
    monkeypatch.setattr(notifier, "_pretty", lambda seconds: "PRETTY")
    monkeypatch.setattr(
        notifier,
        "_send_email",
        lambda dest, pretty, step, lang, link=None: langs.append(lang),
    )
    monkeypatch.setattr(notifier, "is_resend_configured", lambda: True)

    session = {"notify_email": "user@example.com", "notify_lang": language_alias}

    notifier.notify_finished(42, "entries", session)

    assert langs == [expected_language]


def test_send_email_uses_spanish_content_and_cta(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(notifier, "is_resend_configured", lambda: True)

    def fake_send_email(
        recipients, subject, text_body, *, cta_label=None, cta_url=None, **kwargs
    ) -> bool:
        captured["subject"] = subject
        captured["text_body"] = text_body
        captured["cta_label"] = cta_label
        return True

    monkeypatch.setattr(notifier, "send_email", fake_send_email)

    notifier._send_email(
        "user@example.com",
        "1 min 05 s",
        "report",
        "es",
        "https://mparanza.com/results/123",
    )

    assert captured["subject"] == "Tu informe está listo"
    assert "El informe acaba de generarse" in str(captured["text_body"])
    assert "Resultados: https://mparanza.com/results/123" in str(captured["text_body"])
    assert captured["cta_label"] == "Abrir resultados"


def test_send_error_email_uses_spanish_content(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(notifier, "is_resend_configured", lambda: True)

    def fake_send_email(
        recipients, subject, text_body, *, cta_label=None, cta_url=None, **kwargs
    ) -> bool:
        captured["subject"] = subject
        captured["text_body"] = text_body
        return True

    monkeypatch.setattr(notifier, "send_email", fake_send_email)

    notifier._send_error_email("user@example.com", "entries", "es")

    assert captured["subject"] == "Problema con la revisión de asientos"
    assert "Puedes descargar los resultados parciales" in str(captured["text_body"])


def test_send_email_uses_localized_cta_for_success_link(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(notifier, "is_resend_configured", lambda: True)

    def fake_send_email(
        recipients, subject, text_body, *, cta_label=None, cta_url=None, **kwargs
    ) -> bool:
        captured["recipients"] = recipients
        captured["subject"] = subject
        captured["text_body"] = text_body
        captured["cta_label"] = cta_label
        captured["cta_url"] = cta_url
        return True

    monkeypatch.setattr(notifier, "send_email", fake_send_email)

    notifier._send_email(
        "user@example.com",
        "PRETTY",
        "entries",
        "it",
        "https://mparanza.com/results/123",
    )

    assert captured["recipients"] == ["user@example.com"]
    assert captured["cta_label"] == "Apri i risultati"
    assert captured["cta_url"] == "https://mparanza.com/results/123"
    assert "Results: https://mparanza.com/results/123" in captured["text_body"]


def test_send_error_email_uses_localized_cta_for_error_link(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(notifier, "is_resend_configured", lambda: True)

    def fake_send_email(
        recipients, subject, text_body, *, cta_label=None, cta_url=None, **kwargs
    ) -> bool:
        captured["recipients"] = recipients
        captured["subject"] = subject
        captured["text_body"] = text_body
        captured["cta_label"] = cta_label
        captured["cta_url"] = cta_url
        return True

    monkeypatch.setattr(notifier, "send_email", fake_send_email)

    notifier._send_error_email(
        "user@example.com",
        "entries",
        "fr",
        "https://mparanza.com/results/partial",
    )

    assert captured["recipients"] == ["user@example.com"]
    assert captured["cta_label"] == "Ouvrir les résultats"
    assert captured["cta_url"] == "https://mparanza.com/results/partial"
    assert "Results: https://mparanza.com/results/partial" in captured["text_body"]
