from __future__ import annotations

"""Queue-backed outreach sending helpers.

The queue rules are deterministic because they enforce mechanical safety:
exact status eligibility, exact hash dedupe, and exact CSV/ledger updates.
Semantic lead quality remains a separate Codex review/discovery task.
"""

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from modules.hosted_interviews.campaigns import (
    build_campaign_interview_payload,
    build_outreach_interview_case_id,
    outreach_interviewee_role,
)
from modules.outreach.batch import (
    DAILY_COUNTRY_LIMIT,
    OutreachLead,
    OutreachMessage,
    daily_quota_usage,
    email_hash,
    load_blocked_hashes,
    normalise_language,
    normalise_locale,
    normalise_quota_key,
    quota_daily_limit,
)

__all__ = [
    "QUEUE_FIELDNAMES",
    "QueueBatchResult",
    "append_leads_to_queue",
    "eligible_queue_status",
    "prepare_queue_outreach_batch",
    "record_queue_batch_sent",
]

QUEUE_FIELDNAMES = (
    "name",
    "email",
    "salutation",
    "city",
    "country",
    "source_url",
    "source_note",
    "interview_url",
    "interview_campaign_id",
    "status",
    "email_hash",
    "sent_at",
    "gmail_message_id",
    "gmail_sent_deleted_at",
    "last_error",
)


@dataclass(frozen=True)
class QueueBatchResult:
    """Outcome from selecting queued leads for one region."""

    prepared_count: int
    duplicate_count: int
    shortage_count: int
    batch_path: Path


def eligible_queue_status(value: str) -> bool:
    """Return true for queue rows the morning sender may consume."""

    return value.strip().casefold() in {"", "queued"}


def append_leads_to_queue(
    queue_path: Path,
    leads: Iterable[OutreachLead],
    *,
    ledger_path: Path,
    salt: str = "",
) -> int:
    """Append discovered leads that are not already queued or ledgered."""

    rows, fieldnames = _read_queue(queue_path)
    blocked_hashes = load_blocked_hashes(ledger_path)
    queued_hashes = _queue_hashes(rows, salt=salt)
    appended = 0
    for lead in leads:
        digest = email_hash(lead.email, salt=salt)
        if digest in blocked_hashes or digest in queued_hashes:
            continue
        rows.append(
            {
                "name": lead.name,
                "email": lead.normalised_email,
                "salutation": _default_salutation_for_lead(lead),
                "city": lead.city,
                "country": lead.country,
                "source_url": lead.source_url,
                "source_note": lead.source_note,
                "interview_url": "",
                "interview_campaign_id": "",
                "status": "queued",
                "email_hash": digest,
                "sent_at": "",
                "gmail_message_id": "",
                "gmail_sent_deleted_at": "",
                "last_error": "",
            }
        )
        queued_hashes.add(digest)
        appended += 1
    _write_queue(queue_path, rows, fieldnames)
    return appended


def prepare_queue_outreach_batch(
    queue_path: Path,
    batch_path: Path,
    *,
    ledger_path: Path,
    campaign_id: str,
    interview_campaign_id: str,
    language: str,
    locale: str,
    quota_key: str,
    message: OutreachMessage,
    run_at: datetime,
    limit: int = DAILY_COUNTRY_LIMIT,
    salt: str = "",
) -> QueueBatchResult:
    """Select sendable queue rows and write a Gmail-ready batch JSONL."""

    rows, fieldnames = _read_queue(queue_path)
    quota_day = _quota_day(run_at)
    normalised_quota_key = normalise_quota_key(quota_key)
    quota_limit = quota_daily_limit(normalised_quota_key)
    if limit < 1 or limit > quota_limit:
        raise ValueError(f"limit must be between 1 and {quota_limit}")

    used_slots = daily_quota_usage(
        ledger_path,
        quota_key=normalised_quota_key,
        quota_day=quota_day,
    )
    allowed_count = min(limit, max(0, quota_limit - used_slots))
    blocked_hashes = load_blocked_hashes(ledger_path)
    reserved_hashes = _queue_hashes(
        (row for row in rows if not eligible_queue_status(row.get("status", ""))),
        salt=salt,
    )
    seen_hashes: set[str] = set()
    records: list[dict[str, str]] = []
    duplicate_count = 0

    for row in rows:
        if len(records) >= allowed_count:
            break
        if not eligible_queue_status(row.get("status", "")):
            continue
        raw_email = (row.get("email") or "").strip()
        if not raw_email:
            row["last_error"] = "missing-email"
            continue
        try:
            digest = email_hash(raw_email, salt=salt)
        except ValueError:
            row["status"] = "blocked_invalid_email"
            row["last_error"] = "invalid-email"
            continue
        row["email_hash"] = digest
        if (
            digest in blocked_hashes
            or digest in reserved_hashes
            or digest in seen_hashes
        ):
            row["status"] = "blocked_duplicate"
            row["email"] = ""
            row["last_error"] = "duplicate-email-hash"
            duplicate_count += 1
            continue
        lead = _lead_from_row(row)
        interview_url = _ensure_interview_url(
            row,
            message=message,
            campaign_id=campaign_id,
            interview_campaign_id=interview_campaign_id,
            email_hash_value=digest,
            language=normalise_language(language),
            locale=normalise_locale(locale),
            quota_key=normalised_quota_key,
        )
        record = {
            "campaign_id": campaign_id,
            "interview_campaign_id": interview_campaign_id,
            "email_hash": digest,
            "locale": normalise_locale(locale),
            "language": normalise_language(language),
            "quota_key": normalised_quota_key,
            "quota_day": quota_day.isoformat(),
            "variant_id": message.variant_id,
            "retain_recipient_email": _should_retain_recipient_email(message),
            "interview_url": interview_url,
            "to": lead.normalised_email,
            "subject": message.subject,
            "body": _personalise_message_body(
                message.body,
                row,
                language=normalise_language(language),
                locale=normalise_locale(locale),
            ),
            "name": lead.name,
            "city": lead.city,
            "country": lead.country,
            "source_url": lead.source_url,
            "source_note": lead.source_note,
            "status": "prepared",
            "created_at": _iso_timestamp(run_at),
        }
        row["status"] = "prepared"
        row["last_error"] = ""
        records.append(record)
        seen_hashes.add(digest)

    _write_queue(queue_path, rows, fieldnames)
    _write_batch(batch_path, records)
    shortage_count = max(0, allowed_count - len(records))
    return QueueBatchResult(
        prepared_count=len(records),
        duplicate_count=duplicate_count,
        shortage_count=shortage_count,
        batch_path=batch_path,
    )


def record_queue_batch_sent(
    batch_path: Path,
    queue_path: Path,
    *,
    ledger_path: Path,
    gmail_message_ids: Mapping[str, str],
    sent_at: datetime | None = None,
    gmail_sent_deleted_at: datetime | None = None,
) -> int:
    """Record confirmed Gmail sends in the ledger and consume queue rows."""

    sent_time = sent_at or datetime.now(timezone.utc)
    sent_timestamp = _iso_timestamp(sent_time)
    deleted_timestamp = (
        _iso_timestamp(gmail_sent_deleted_at) if gmail_sent_deleted_at else ""
    )
    records = _read_batch(batch_path)
    rows, fieldnames = _read_queue(queue_path)
    rows_by_hash = {
        row.get("email_hash", ""): row for row in rows if row.get("email_hash")
    }
    ledger_records: list[dict[str, str]] = []

    for record in records:
        digest = str(record["email_hash"])
        gmail_message_id = (gmail_message_ids.get(digest) or "").strip()
        if not gmail_message_id:
            raise ValueError(f"Missing Gmail message ID for sent hash {digest}")
        row = rows_by_hash.get(digest)
        if row is None:
            raise ValueError(f"Queue row not found for sent hash {digest}")
        record["status"] = "sent"
        record["gmail_message_id"] = gmail_message_id
        record["sent_at"] = sent_timestamp
        if deleted_timestamp:
            record["gmail_sent_deleted_at"] = deleted_timestamp
        row["status"] = "sent"
        retain_recipient_email = _record_flag(record.get("retain_recipient_email"))
        if retain_recipient_email:
            record["recipient_deleted"] = False
        else:
            record.pop("to", None)
            record["recipient_deleted"] = True
            row["email"] = ""
        row["sent_at"] = sent_timestamp
        row["gmail_message_id"] = gmail_message_id
        row["gmail_sent_deleted_at"] = deleted_timestamp
        row["last_error"] = ""
        ledger_records.append(_ledger_record(record))

    _append_ledger_records(ledger_path, ledger_records)
    _write_queue(queue_path, rows, fieldnames)
    _write_batch(batch_path, records)
    return len(ledger_records)


def _read_queue(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], list(QUEUE_FIELDNAMES)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return [], list(QUEUE_FIELDNAMES)
        fieldnames = _merged_fieldnames(reader.fieldnames)
        rows = [
            {field: row.get(field, "") or "" for field in fieldnames} for row in reader
        ]
    return rows, fieldnames


def _write_queue(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _merged_fieldnames(existing: Iterable[str]) -> list[str]:
    fields = list(dict.fromkeys([*existing, *QUEUE_FIELDNAMES]))
    return fields


def _queue_hashes(rows: Iterable[dict[str, str]], *, salt: str) -> set[str]:
    hashes: set[str] = set()
    for row in rows:
        stored_hash = (row.get("email_hash") or "").strip()
        if stored_hash:
            hashes.add(stored_hash)
            continue
        raw_email = (row.get("email") or "").strip()
        if raw_email:
            try:
                hashes.add(email_hash(raw_email, salt=salt))
            except ValueError:
                continue
    return hashes


def _lead_from_row(row: dict[str, str]) -> OutreachLead:
    return OutreachLead(
        name=(row.get("name") or "").strip(),
        email=(row.get("email") or "").strip(),
        city=(row.get("city") or "").strip(),
        country=(row.get("country") or "").strip(),
        source_url=(row.get("source_url") or "").strip(),
        source_note=(row.get("source_note") or "").strip(),
    )


def _personalise_message_body(
    body: str,
    row: dict[str, str],
    *,
    language: str,
    locale: str,
) -> str:
    salutation = (
        (row.get("salutation") or "").strip()
        or _default_salutation_for_row(row, language=language, locale=locale)
        or "Buongiorno,"
    )
    personalized = body.replace("{salutation}", salutation)
    if "{interview_url}" not in personalized:
        return personalized
    interview_url = (row.get("interview_url") or "").strip()
    if not interview_url:
        raise ValueError(
            "Outreach template requires {interview_url}, but the queue row has "
            "no interview_url."
        )
    return personalized.replace("{interview_url}", interview_url)


def _ensure_interview_url(
    row: dict[str, str],
    *,
    message: OutreachMessage,
    campaign_id: str,
    interview_campaign_id: str,
    email_hash_value: str,
    language: str,
    locale: str,
    quota_key: str,
) -> str:
    if "{interview_url}" not in message.body:
        return ""
    if not interview_campaign_id:
        raise ValueError(
            "interview_campaign_id is required when outreach copy uses "
            "{interview_url}."
        )
    existing_url = (row.get("interview_url") or "").strip()
    if existing_url:
        existing_campaign_id = (row.get("interview_campaign_id") or "").strip()
        if existing_campaign_id != interview_campaign_id:
            raise ValueError(
                "Existing interview URL belongs to a missing or different "
                "interview campaign. Clear or revoke it before preparing a new "
                "campaign link."
            )
        return existing_url

    from modules.hosted_interviews.api import (
        PreparedInterviewRequest,
        create_prepared_interview,
    )

    token, record = create_prepared_interview(
        PreparedInterviewRequest.model_validate(
            build_campaign_interview_payload(
                interview_campaign_id,
                case_id=build_outreach_interview_case_id(campaign_id, email_hash_value),
                language=language,
                interviewee_role=outreach_interviewee_role(locale, quota_key),
            )
        ),
    )
    del token
    interview_url = str(record["public_url"])
    row["interview_url"] = interview_url
    row["interview_campaign_id"] = interview_campaign_id
    return interview_url


def _should_retain_recipient_email(message: OutreachMessage) -> bool:
    return False


def _record_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _default_salutation_for_lead(lead: OutreachLead) -> str:
    row = {
        "name": lead.name,
        "country": lead.country,
        "source_note": lead.source_note,
    }
    return _default_salutation_for_row(row, language="it", locale="italy")


def _default_salutation_for_row(
    row: Mapping[str, str],
    *,
    language: str,
    locale: str,
) -> str:
    if language != "it" and locale != "italy":
        return ""
    surname = _italian_professional_surname(
        row.get("name", ""),
        row.get("source_note", ""),
        row.get("country", ""),
    )
    if not surname:
        return ""
    return f"Gentile Dott. {surname},"


def _italian_professional_surname(
    name: str,
    source_note: str,
    country: str,
) -> str:
    if country.strip().casefold() not in {"italy", "italia"}:
        return ""
    normalized = " ".join(name.replace(",", " ").split()).strip()
    if not normalized:
        return ""
    lowered = normalized.casefold()
    source = source_note.casefold()
    organization_terms = {
        "&",
        "associazione",
        "associati",
        "commercialisti",
        "ordine",
        "odcec",
        "societa",
        "società",
        "spa",
        "s.p.a",
        "srl",
        "s.r.l",
        "studio",
    }
    if any(term in lowered for term in organization_terms):
        return ""
    if not any(marker in source for marker in {"albo", "cndcec", "odcec"}):
        return ""
    cleaned = re.sub(
        r"^(dott\.?|dottore|dott\.ssa|dottoressa|rag\.?|ragioniere)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    parts = cleaned.split()
    if len(parts) < 2:
        return ""
    surname_parts = [parts[0]]
    if parts[0].casefold() in {"da", "dal", "de", "del", "della", "di", "la", "lo"}:
        surname_parts = parts[:2]
    surname = " ".join(surname_parts).strip(" .")
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", surname):
        return ""
    return surname


def _write_batch(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _read_batch(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"Invalid batch record in {path} line {line_number}")
            records.append(payload)
    return records


def _ledger_record(record: Mapping[str, object]) -> dict[str, str]:
    return {
        "campaign_id": str(record["campaign_id"]),
        "interview_campaign_id": str(record.get("interview_campaign_id") or ""),
        "email_hash": str(record["email_hash"]),
        "status": "sent",
        "created_at": str(record.get("created_at") or ""),
        "sent_at": str(record["sent_at"]),
        "gmail_message_id": str(record["gmail_message_id"]),
        "gmail_sent_deleted_at": str(record.get("gmail_sent_deleted_at") or ""),
        "quota_day": str(record["quota_day"]),
        "locale": str(record["locale"]),
        "language": str(record["language"]),
        "quota_key": str(record["quota_key"]),
        "variant_id": str(record["variant_id"]),
        "country": str(record["country"]),
        "city": str(record["city"]),
        "source_url": str(record["source_url"]),
    }


def _append_ledger_records(
    ledger_path: Path, records: Iterable[dict[str, str]]
) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _quota_day(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.date()


def _iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
