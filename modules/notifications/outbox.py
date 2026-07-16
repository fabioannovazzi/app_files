"""JSON-backed notification outbox for restart-safe email delivery."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

from modules.utilities.cache import get_cache_dir
from modules.utilities.json_record_store import JsonRecordStore

__all__ = [
    "EmailDelivery",
    "enqueue_email",
    "process_email_outbox",
]

LOGGER = logging.getLogger(__name__)

EmailDelivery = Callable[
    [list[str], str, str, str | None, str | None],
    bool,
]

_OUTBOX_PATH = Path(get_cache_dir("notification_outbox")) / "notifications.json"
_OUTBOX = JsonRecordStore(_OUTBOX_PATH)


def _clean_recipients(recipients: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in recipients:
        candidate = str(raw or "").strip()
        key = candidate.lower()
        if not candidate or key in seen:
            continue
        seen.add(key)
        cleaned.append(candidate)
    return cleaned


def enqueue_email(
    *,
    recipients: Sequence[str],
    subject: str,
    body: str,
    cta_label: str | None = None,
    cta_url: str | None = None,
) -> str | None:
    """Persist an email notification for later delivery."""

    cleaned = _clean_recipients(recipients)
    if not cleaned:
        return None
    notification_id = uuid.uuid4().hex
    now = time.time()
    _OUTBOX.upsert(
        notification_id,
        {
            "notification_id": notification_id,
            "recipients": cleaned,
            "subject": subject,
            "body": body,
            "cta_label": cta_label,
            "cta_url": cta_url,
            "status": "pending",
            "attempts": 0,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
            "sent_at": None,
        },
    )
    return notification_id


def _mark_sent(notification_id: str) -> None:
    now = time.time()
    _OUTBOX.update(
        notification_id,
        lambda row: {
            **row,
            "status": "sent",
            "last_error": None,
            "updated_at": now,
            "sent_at": now,
        },
    )


def _mark_pending_retry(notification_id: str, error: str | None) -> None:
    _OUTBOX.update(
        notification_id,
        lambda row: {
            **row,
            "status": "pending",
            "attempts": int(row.get("attempts") or 0) + 1,
            "last_error": error or "Email delivery failed.",
            "updated_at": time.time(),
        },
    )


def process_email_outbox(
    deliver: EmailDelivery,
    *,
    limit: int = 50,
    notification_id: str | None = None,
) -> int:
    """Attempt delivery for pending notifications.

    The outbox leaves failed attempts as ``pending`` so a future process restart
    or explicit flush can retry them.
    """

    if limit <= 0:
        return 0
    if notification_id:
        selected = [_OUTBOX.get(notification_id)]
        rows = [row for row in selected if row and row.get("status") == "pending"]
    else:
        rows = sorted(
            (row for row in _OUTBOX.all() if row.get("status") == "pending"),
            key=lambda row: float(row.get("created_at") or 0),
        )[:limit]

    delivered_count = 0
    for row in rows[:limit]:
        notification_id_value = str(row.get("notification_id") or "")
        try:
            recipients = row.get("recipients")
            if not isinstance(recipients, list):
                raise ValueError("recipients payload must be a list")
            sent = deliver(
                [str(recipient) for recipient in recipients],
                str(row.get("subject") or ""),
                str(row.get("body") or ""),
                row.get("cta_label"),
                row.get("cta_url"),
            )
        except Exception as exc:  # noqa: BLE001 - retryable outbox failure
            LOGGER.warning(
                "Notification delivery failed for %s: %s",
                notification_id_value,
                exc,
            )
            _mark_pending_retry(notification_id_value, str(exc))
            continue
        if sent:
            _mark_sent(notification_id_value)
            delivered_count += 1
        else:
            _mark_pending_retry(notification_id_value, "Email provider returned false.")
    return delivered_count
