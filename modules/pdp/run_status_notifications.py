from __future__ import annotations

import datetime as dt
import logging
import os
from collections.abc import Mapping, Sequence

from modules.notifications.resend_client import (
    ResendAuthenticationError,
    is_resend_configured,
    send_plain_text_email,
)
from modules.utilities.secrets_loader import load_env_from_secrets_file

__all__ = [
    "resolve_notification_recipients",
    "send_run_notification",
]

_LOGGER = logging.getLogger(__name__)
_NOTIFY_ENV_VAR = "PDP_RUN_NOTIFY_EMAILS"


def _normalize_recipients(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values:
        cleaned = str(raw or "").strip().lower()
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return tuple(ordered)


def resolve_notification_recipients(
    cli_recipients: Sequence[str] | None = None,
) -> tuple[str, ...]:
    values: list[str] = []
    if cli_recipients:
        values.extend(str(item) for item in cli_recipients)
    env_value = str(os.getenv(_NOTIFY_ENV_VAR, "") or "").strip()
    if env_value:
        values.extend(env_value.replace(";", ",").split(","))
    return _normalize_recipients(values)


def _iso_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat()


def _format_duration(started_at: dt.datetime, finished_at: dt.datetime) -> str:
    total_seconds = max(0.0, (finished_at - started_at).total_seconds())
    minutes, seconds = divmod(int(total_seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes}m {seconds:02d}s"


def send_run_notification(
    *,
    run_name: str,
    status: str,
    recipients: Sequence[str],
    started_at: dt.datetime,
    finished_at: dt.datetime | None = None,
    details: Mapping[str, object] | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    logger_obj = logger or _LOGGER
    normalized_recipients = _normalize_recipients(tuple(recipients))
    if not normalized_recipients:
        return False
    load_env_from_secrets_file()
    if not is_resend_configured():
        logger_obj.warning(
            "Run notification skipped for %s: RESEND_API_KEY/RESEND_FROM_EMAIL are not configured.",
            run_name,
        )
        return False

    status_text = str(status or "").strip().upper() or "UNKNOWN"
    subject = f"[PDP Pipeline] {status_text} {run_name}"
    body_lines = [
        f"Run: {run_name}",
        f"Status: {status_text}",
        f"Started UTC: {_iso_utc(started_at)}",
    ]
    if finished_at is not None:
        body_lines.append(f"Finished UTC: {_iso_utc(finished_at)}")
        body_lines.append(f"Elapsed: {_format_duration(started_at, finished_at)}")
    if details:
        for key in sorted(details):
            value = details[key]
            body_lines.append(f"{key}: {value}")

    try:
        sent = send_plain_text_email(
            recipients=list(normalized_recipients),
            subject=subject,
            body="\n".join(body_lines),
        )
    except ResendAuthenticationError:
        logger_obj.warning(
            "Run notification authentication failed for %s (recipients=%s).",
            run_name,
            ",".join(normalized_recipients),
        )
        return False

    if sent:
        logger_obj.info(
            "Run notification sent for %s to %s.",
            run_name,
            ",".join(normalized_recipients),
        )
    else:
        logger_obj.warning(
            "Run notification delivery failed for %s to %s.",
            run_name,
            ",".join(normalized_recipients),
        )
    return sent
