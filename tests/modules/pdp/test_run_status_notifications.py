from __future__ import annotations

import datetime as dt

from modules.pdp.run_status_notifications import (
    resolve_notification_recipients,
    send_run_notification,
)


def test_resolve_notification_recipients_merges_cli_and_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "PDP_RUN_NOTIFY_EMAILS",
        "team@example.com, Ops@example.com ; runner@example.com",
    )

    recipients = resolve_notification_recipients(
        ["Runner@example.com", "", "alerts@example.com"]
    )

    assert recipients == (
        "runner@example.com",
        "alerts@example.com",
        "team@example.com",
        "ops@example.com",
    )


def test_send_run_notification_returns_false_without_recipients() -> None:
    started_at = dt.datetime(2026, 2, 13, tzinfo=dt.timezone.utc)
    sent = send_run_notification(
        run_name="test-run",
        status="success",
        recipients=(),
        started_at=started_at,
    )

    assert sent is False


def test_resolve_notification_recipients_is_empty_without_configuration(
    monkeypatch,
) -> None:
    monkeypatch.delenv("PDP_RUN_NOTIFY_EMAILS", raising=False)
    recipients = resolve_notification_recipients()
    assert recipients == ()
