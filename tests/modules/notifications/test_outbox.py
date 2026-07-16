from __future__ import annotations

from pathlib import Path

from modules.notifications import outbox


def test_email_outbox_retries_pending_notification_after_failed_attempt(
    tmp_path: Path, monkeypatch
) -> None:
    store_path = tmp_path / "notifications.json"
    monkeypatch.setattr(outbox, "_OUTBOX", outbox.JsonRecordStore(store_path))

    notification_id = outbox.enqueue_email(
        recipients=["User@example.com", "user@example.com", "team@example.com"],
        subject="Ready",
        body="Done",
        cta_label="Open",
        cta_url="https://example.com/result",
    )

    assert notification_id is not None

    failed_count = outbox.process_email_outbox(lambda *_args: False)
    delivered: list[tuple[list[str], str, str, str | None, str | None]] = []

    def deliver(
        recipients: list[str],
        subject: str,
        body: str,
        cta_label: str | None,
        cta_url: str | None,
    ) -> bool:
        delivered.append((recipients, subject, body, cta_label, cta_url))
        return True

    delivered_count = outbox.process_email_outbox(deliver)
    second_pass_count = outbox.process_email_outbox(deliver)

    assert failed_count == 0
    assert delivered_count == 1
    assert second_pass_count == 0
    assert delivered == [
        (
            ["User@example.com", "team@example.com"],
            "Ready",
            "Done",
            "Open",
            "https://example.com/result",
        )
    ]
