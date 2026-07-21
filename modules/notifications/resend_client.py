from __future__ import annotations

"""Thin helper for sending emails through the Resend API."""

import html
import logging
import os
import re
from typing import Iterable, Sequence

import requests

__all__ = [
    "ResendAuthenticationError",
    "is_resend_configured",
    "send_email",
    "send_plain_text_email",
]

LOGGER = logging.getLogger(__name__)
_RESEND_ENDPOINT = "https://api.resend.com/emails"
_ENV_API_KEY = "RESEND_API_KEY"
_ENV_FROM_EMAIL = "RESEND_FROM_EMAIL"
_URL_PATTERN = re.compile(r"https?://[^\s<]+")
_SALUTATIONS = {
    "hi there,",
    "ciao,",
    "bonjour,",
    "hallo,",
}


class ResendAuthenticationError(RuntimeError):
    """Raised when the Resend API rejects credentials."""


def _clean(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return cleaned
    return cleaned.strip("\"'")


def _redact_email(value: str | None) -> str:
    cleaned = _clean(value)
    if not cleaned or "@" not in cleaned:
        return "***"
    local_part, domain = cleaned.split("@", 1)
    if len(local_part) <= 2:
        redacted_local = f"{local_part}***"
    else:
        redacted_local = f"{local_part[:2]}***"
    return f"{redacted_local}@{domain}"


def _truncate_detail(value: str, max_length: int = 200) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


def _get_request_id(response: requests.Response | None) -> str | None:
    if response is None:
        return None
    for header in ("X-Request-Id", "X-Request-ID", "Request-Id"):
        request_id = response.headers.get(header)
        if request_id:
            return _truncate_detail(request_id)
    return None


def _summarize_error_response(response: requests.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        text = (response.text or "").strip()
        if text:
            return _truncate_detail(text)
        return None
    summary_parts: list[str] = []
    for key in ("code", "error_code", "name", "message", "error", "error_message"):
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, dict):
            for nested_key in ("code", "name", "message"):
                if nested_key in value and isinstance(value[nested_key], str):
                    summary_parts.append(f"{key}.{nested_key}={value[nested_key]}")
            continue
        if isinstance(value, str):
            summary_parts.append(f"{key}={value}")
            continue
        summary_parts.append(f"{key}={value}")
    if not summary_parts:
        return None
    return _truncate_detail("; ".join(summary_parts))


def _normalise_recipients(recipients: str | Sequence[str]) -> list[str]:
    if isinstance(recipients, str):
        candidates: Iterable[str] = [recipients]
    else:
        candidates = recipients
    cleaned = [_clean(entry).lower() for entry in candidates if _clean(entry)]
    return cleaned


def _normalise_header_recipients(recipients: str | Sequence[str]) -> list[str]:
    if isinstance(recipients, str):
        candidates: Iterable[str] = [recipients]
    else:
        candidates = recipients
    return [_clean(entry) for entry in candidates if _clean(entry)]


def _linkify_text(text: str) -> str:
    parts: list[str] = []
    last_end = 0
    for match in _URL_PATTERN.finditer(text):
        parts.append(html.escape(text[last_end : match.start()]))
        url = match.group(0)
        safe_url = html.escape(url, quote=True)
        parts.append(
            f'<a href="{safe_url}" '
            'style="color:#1f3d7a;text-decoration:none;word-break:break-all;">'
            f"{html.escape(url)}</a>"
        )
        last_end = match.end()
    parts.append(html.escape(text[last_end:]))
    return "".join(parts)


def _render_text_blocks(body: str) -> str:
    normalized = body.replace("\r\n", "\n").strip()
    if not normalized:
        return (
            '<p style="margin:0;font-size:16px;line-height:1.7;color:#353127;">'
            "Mparanza notification."
            "</p>"
        )
    paragraphs = [
        block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()
    ]
    if paragraphs and paragraphs[0].strip().lower() in _SALUTATIONS:
        paragraphs = paragraphs[1:]
    if not paragraphs:
        paragraphs = [normalized]

    rendered: list[str] = []
    for block in paragraphs:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if lines and all(line.startswith(("- ", "* ")) for line in lines):
            items = "".join(
                "<li>" f"{_linkify_text(line[2:].strip())}" "</li>" for line in lines
            )
            rendered.append(
                '<ul style="margin:0 0 22px 20px;padding:0;color:#353127;font-size:16px;line-height:1.7;">'
                f"{items}"
                "</ul>"
            )
            continue
        paragraph_html = "<br>".join(
            _linkify_text(line) for line in lines
        ) or _linkify_text(block)
        rendered.append(
            '<p style="margin:0 0 18px;font-size:16px;line-height:1.7;color:#353127;">'
            f"{paragraph_html}"
            "</p>"
        )
    return "".join(rendered)


def _build_default_html_email(
    subject: str,
    text_body: str,
    *,
    cta_label: str | None = None,
    cta_url: str | None = None,
) -> str:
    safe_subject = html.escape(subject)
    body_html = _render_text_blocks(text_body)
    cta_html = ""
    footer_link_html = ""
    if cta_label and cta_url:
        safe_cta_url = html.escape(cta_url, quote=True)
        cta_html = (
            '<p style="margin:0 0 24px;">'
            f'<a href="{safe_cta_url}" style="display:inline-block;padding:13px 22px;'
            "border-radius:999px;background:#1f3d7a;color:#fffdf8;text-decoration:none;"
            'font-size:15px;font-weight:600;">'
            f"{html.escape(cta_label)}</a>"
            "</p>"
        )
        footer_link_html = (
            '<p style="margin:0;font-size:13px;line-height:1.6;color:#7a7367;">'
            "If the button does not work, copy and paste this link into your browser:<br>"
            f'<a href="{safe_cta_url}" style="color:#1f3d7a;word-break:break-all;">{html.escape(cta_url)}</a>'
            "</p>"
        )

    return (
        "<!doctype html>"
        "<html>"
        '<body style="margin:0;padding:0;background:#f5f3ee;color:#1c1c18;'
        "font-family:Georgia,'Times New Roman',serif;\">"
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="background:#f5f3ee;padding:32px 16px;">'
        '<tr><td align="center">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="max-width:560px;background:#fffdf8;border:1px solid #ddd5c6;border-radius:18px;'
        'padding:36px 32px;">'
        "<tr><td>"
        '<p style="margin:0 0 12px;font-size:14px;letter-spacing:0.08em;text-transform:uppercase;'
        'color:#6f6759;">Mparanza</p>'
        '<h1 style="margin:0 0 18px;font-size:28px;line-height:1.2;font-weight:600;color:#1c1c18;">'
        f"{safe_subject}</h1>"
        f"{body_html}"
        f"{cta_html}"
        f"{footer_link_html}"
        "</td></tr></table>"
        "</td></tr></table>"
        "</body>"
        "</html>"
    )


def is_resend_configured() -> bool:
    """Return ``True`` when both API key and sender are defined."""

    return bool(_clean(os.getenv(_ENV_API_KEY)) and _clean(os.getenv(_ENV_FROM_EMAIL)))


def send_email(
    recipients: str | Sequence[str],
    subject: str,
    text_body: str,
    *,
    html_body: str | None = None,
    cta_label: str | None = None,
    cta_url: str | None = None,
    reply_to: str | Sequence[str] | None = None,
    sender: str | None = None,
    api_key: str | None = None,
    timeout: float = 10.0,
) -> bool:
    """Send an email via Resend.

    Returns ``True`` on success, ``False`` when configuration is missing or the API call fails.
    """

    to_list = _normalise_recipients(recipients)
    if not to_list:
        LOGGER.debug("Skipping Resend send: no valid recipients provided.")
        return False

    resolved_sender = _clean(sender) or _clean(os.getenv(_ENV_FROM_EMAIL))
    resolved_key = _clean(api_key) or _clean(os.getenv(_ENV_API_KEY))
    if not (resolved_sender and resolved_key):
        LOGGER.debug(
            "Skipping Resend send: credentials are missing or sender identity is a placeholder."
        )
        return False

    resolved_html_body = html_body
    if resolved_html_body is None:
        resolved_html_body = _build_default_html_email(
            subject,
            text_body,
            cta_label=cta_label,
            cta_url=cta_url,
        )

    payload = {
        "from": resolved_sender,
        "to": to_list,
        "subject": subject,
        "text": text_body,
    }
    if reply_to:
        reply_to_list = _normalise_header_recipients(reply_to)
        if len(reply_to_list) == 1:
            payload["reply_to"] = reply_to_list[0]
        elif reply_to_list:
            payload["reply_to"] = reply_to_list
    if resolved_html_body:
        payload["html"] = resolved_html_body
    headers = {
        "Authorization": f"Bearer {resolved_key}",
        "Content-Type": "application/json",
    }

    response: requests.Response | None = None
    try:
        response = requests.post(
            _RESEND_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - log path
        detail = ""
        response_for_error = exc.response or response
        status_code = response_for_error.status_code if response_for_error else None
        summary = (
            _summarize_error_response(response_for_error)
            if response_for_error is not None
            else None
        )
        request_id = _get_request_id(response_for_error)
        if status_code is not None:
            detail = f" (status={status_code})"
        if status_code in {401, 403}:
            has_env_key = bool(_clean(os.getenv(_ENV_API_KEY)))
            has_env_sender = bool(_clean(os.getenv(_ENV_FROM_EMAIL)))
            redacted_sender = _redact_email(os.getenv(_ENV_FROM_EMAIL))
            summary_detail = f"; error_summary={summary}" if summary else ""
            request_id_detail = f"; request_id={request_id}" if request_id else ""
            LOGGER.warning(
                "Resend authentication failed: %s (status=%s); resend_api_key_present=%s; "
                "resend_from_email_present=%s; sender=%s%s%s",
                exc,
                status_code,
                has_env_key,
                has_env_sender,
                redacted_sender,
                summary_detail,
                request_id_detail,
            )
            raise ResendAuthenticationError("Resend authentication failed.") from exc
        summary_detail = f"; error_summary={summary}" if summary else ""
        request_id_detail = f"; request_id={request_id}" if request_id else ""
        LOGGER.warning(
            "Resend email delivery failed: %s%s%s%s",
            exc,
            detail,
            summary_detail,
            request_id_detail,
        )
        return False

    return True


def send_plain_text_email(
    recipients: str | Sequence[str],
    subject: str,
    body: str,
    *,
    reply_to: str | Sequence[str] | None = None,
    sender: str | None = None,
    api_key: str | None = None,
    timeout: float = 10.0,
) -> bool:
    """Send an email with a plain-text body and generated HTML presentation."""

    return send_email(
        recipients,
        subject,
        body,
        reply_to=reply_to,
        sender=sender,
        api_key=api_key,
        timeout=timeout,
    )
