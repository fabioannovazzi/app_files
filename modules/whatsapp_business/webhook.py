"""Normalize the small, read-only subset of Meta webhook events Vera stores."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from modules.whatsapp_business.security import normalize_phone_number
from modules.whatsapp_business.store import IncomingWhatsAppMessage

__all__ = ["ParsedWebhook", "parse_whatsapp_webhook"]

_MAX_MESSAGE_BODY_CHARACTERS = 10_000
_SUPPORTED_MESSAGE_TYPES = {
    "audio",
    "button",
    "document",
    "image",
    "interactive",
    "sticker",
    "text",
    "video",
}


class ParsedWebhook:
    """Messages grouped by signed WABA and phone-number IDs."""

    def __init__(self) -> None:
        self.messages_by_account: dict[
            tuple[str, str],
            list[IncomingWhatsAppMessage],
        ] = {}
        self.ignored_events = 0

    def add(self, waba_id: str, message: IncomingWhatsAppMessage) -> None:
        account_key = (waba_id, message.phone_number_id)
        self.messages_by_account.setdefault(account_key, []).append(message)


def _text(value: object, *, max_length: int = _MAX_MESSAGE_BODY_CHARACTERS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _message_body(message: Mapping[str, Any], message_type: str) -> str:
    typed = _mapping(message.get(message_type))
    if message_type == "text":
        return _text(typed.get("body"))
    if message_type in {"image", "video", "document"}:
        caption = _text(typed.get("caption"))
        return caption or f"[{message_type}]"
    if message_type == "audio":
        return "[audio]"
    if message_type == "sticker":
        return "[sticker]"
    if message_type == "button":
        return _text(typed.get("text")) or "[button reply]"
    if message_type == "interactive":
        button_reply = _mapping(typed.get("button_reply"))
        list_reply = _mapping(typed.get("list_reply"))
        return (
            _text(button_reply.get("title"))
            or _text(list_reply.get("title"))
            or _text(list_reply.get("description"))
            or "[interactive reply]"
        )
    return ""


def _media_id(message: Mapping[str, Any], message_type: str) -> str | None:
    del message, message_type
    return None


def _opaque_meta_id(value: object) -> str:
    raw_value = _text(value, max_length=512)
    if not raw_value:
        return ""
    return f"meta_{hashlib.sha256(raw_value.encode('utf-8')).hexdigest()}"


def _occurred_at(timestamp: object) -> str | None:
    try:
        unix_timestamp = int(str(timestamp))
    except (TypeError, ValueError):
        return None
    if unix_timestamp <= 0:
        return None
    try:
        parsed = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return parsed.replace(microsecond=0).isoformat()


def _contact_names(value: Mapping[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    contacts = value.get("contacts")
    if not isinstance(contacts, list):
        return names
    for contact in contacts:
        if not isinstance(contact, Mapping):
            continue
        wa_id = _text(contact.get("wa_id"), max_length=64)
        name = _text(_mapping(contact.get("profile")).get("name"), max_length=512)
        if wa_id and name:
            names[wa_id] = name
    return names


def _parse_message(
    raw_message: Mapping[str, Any],
    *,
    phone_number_id: str,
    business_phone: str,
    contact_names: Mapping[str, str],
) -> IncomingWhatsAppMessage | None:
    if "group_id" in raw_message:
        return None
    message_id = _opaque_meta_id(raw_message.get("id"))
    raw_sender = _text(raw_message.get("from"), max_length=64)
    occurred_at = _occurred_at(raw_message.get("timestamp"))
    message_type = _text(raw_message.get("type"), max_length=64).lower()
    if (
        not message_id
        or not raw_sender
        or occurred_at is None
        or message_type not in _SUPPORTED_MESSAGE_TYPES
    ):
        return None
    try:
        sender_phone = normalize_phone_number(raw_sender)
    except ValueError:
        return None
    if sender_phone == business_phone:
        return None
    body = _message_body(raw_message, message_type)
    if not body:
        return None
    context = _mapping(raw_message.get("context"))
    reply_to = _opaque_meta_id(context.get("id")) or None
    return IncomingWhatsAppMessage(
        message_id=message_id,
        phone_number_id=phone_number_id,
        sender_phone=sender_phone,
        sender_name=contact_names.get(raw_sender),
        occurred_at=occurred_at,
        message_type=message_type,
        body=body,
        reply_to_message_id=reply_to,
        media_id=_media_id(raw_message, message_type),
    )


def parse_whatsapp_webhook(payload: object) -> ParsedWebhook:
    """Parse current `messages` events without retaining the raw payload.

    History, outbound echoes, statuses, messages marked with Meta's `group_id`,
    messages without a numeric sender phone, and unsupported event types are
    intentionally ignored.
    """

    parsed = ParsedWebhook()
    if not isinstance(payload, Mapping):
        parsed.ignored_events += 1
        return parsed
    if payload.get("object") != "whatsapp_business_account":
        parsed.ignored_events += 1
        return parsed
    entries = payload.get("entry")
    if not isinstance(entries, list):
        parsed.ignored_events += 1
        return parsed
    for entry in entries:
        if not isinstance(entry, Mapping):
            parsed.ignored_events += 1
            continue
        waba_id = _text(entry.get("id"), max_length=128)
        if not waba_id:
            parsed.ignored_events += 1
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            parsed.ignored_events += 1
            continue
        for change in changes:
            if not isinstance(change, Mapping) or change.get("field") != "messages":
                parsed.ignored_events += 1
                continue
            value = _mapping(change.get("value"))
            metadata = _mapping(value.get("metadata"))
            phone_number_id = _text(metadata.get("phone_number_id"), max_length=128)
            try:
                business_phone = normalize_phone_number(
                    _text(metadata.get("display_phone_number"), max_length=64)
                )
            except ValueError:
                parsed.ignored_events += 1
                continue
            messages = value.get("messages")
            if not phone_number_id or not isinstance(messages, list):
                parsed.ignored_events += 1
                continue
            names = _contact_names(value)
            for raw_message in messages:
                if not isinstance(raw_message, Mapping):
                    parsed.ignored_events += 1
                    continue
                message = _parse_message(
                    raw_message,
                    phone_number_id=phone_number_id,
                    business_phone=business_phone,
                    contact_names=names,
                )
                if message is None:
                    parsed.ignored_events += 1
                    continue
                parsed.add(waba_id, message)
    return parsed
