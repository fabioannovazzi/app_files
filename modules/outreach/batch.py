from __future__ import annotations

"""Prepare deduplicated outreach batches without sending email."""

import csv
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Callable, Iterable, Mapping

from modules.hosted_interviews.campaigns import (
    build_campaign_interview_payload,
    build_outreach_interview_case_id,
    outreach_interviewee_role,
)

__all__ = [
    "DAILY_COUNTRY_LIMIT",
    "DAILY_LANGUAGE_LIMIT",
    "OutreachLead",
    "OutreachMessage",
    "PreparedOutreachEmail",
    "build_italian_commercialisti_message",
    "daily_country_usage",
    "daily_language_usage",
    "daily_quota_usage",
    "email_hash",
    "load_blocked_hashes",
    "load_leads_csv",
    "normalise_email",
    "normalise_language",
    "normalise_locale",
    "normalise_quota_key",
    "parse_outreach_template",
    "prepare_outreach_batch",
    "prepare_template_outreach_batch",
    "quota_daily_limit",
    "record_outreach_batch_sent",
    "scrub_raw_emails",
    "write_prepared_batch_jsonl",
]

LOGGER = logging.getLogger(__name__)

BLOCKING_STATUSES = frozenset(
    {"prepared", "drafted", "sent", "skipped", "unsubscribed"}
)
DAILY_COUNTRY_LIMIT = 10
DAILY_LANGUAGE_LIMIT = DAILY_COUNTRY_LIMIT
QUOTA_DAILY_LIMITS = {
    "italy-organization": 5,
}
QUOTA_STATUSES = frozenset({"prepared", "drafted", "sent"})
REQUIRED_LEAD_COLUMNS = frozenset({"name", "email", "city", "country", "source_url"})
ITALIAN_COMMERCIALISTI_VARIANT_IDS = ("it-a", "it-b", "it-c")
_HASH_NAMESPACE = "outreach-email-v1"
_LANGUAGE_ALIASES = {
    "it": "it",
    "ita": "it",
    "italian": "it",
    "italiano": "it",
    "en": "en",
    "eng": "en",
    "english": "en",
    "fr": "fr",
    "fra": "fr",
    "french": "fr",
    "de": "de",
    "deu": "de",
    "ger": "de",
    "german": "de",
}
_LOCALE_ALIASES = {
    "it": "italy",
    "ita": "italy",
    "italian": "italy",
    "italiano": "italy",
    "italia": "italy",
    "italy": "italy",
    "geneva": "geneva",
    "geneve": "geneva",
    "zurich": "zurich",
    "zuerich": "zurich",
    "us": "usa",
    "u-s": "usa",
    "usa": "usa",
    "u-s-a": "usa",
    "united-states": "usa",
    "united-states-of-america": "usa",
    "uk": "uk",
    "u-k": "uk",
    "gb": "uk",
    "great-britain": "uk",
    "britain": "uk",
    "united-kingdom": "uk",
    "england": "uk",
}
_QUOTA_KEY_ALIASES = {
    "it": "italy",
    "ita": "italy",
    "italia": "italy",
    "italy": "italy",
    "italy-odcec": "italy-organization",
    "italy-organization": "italy-organization",
    "italy-organizations": "italy-organization",
    "italian": "italy",
    "italiano": "italy",
    "odcec": "italy-organization",
    "geneva": "swiss-romande",
    "geneve": "swiss-romande",
    "romandie": "swiss-romande",
    "suisse-romande": "swiss-romande",
    "swiss-romande": "swiss-romande",
    "zurich": "swiss-german",
    "zuerich": "swiss-german",
    "deutschschweiz": "swiss-german",
    "german-switzerland": "swiss-german",
    "swiss-german": "swiss-german",
    "schweiz": "switzerland",
    "suisse": "switzerland",
    "swiss": "switzerland",
    "switzerland": "switzerland",
    "ch": "switzerland",
    "us": "usa",
    "u-s": "usa",
    "usa": "usa",
    "u-s-a": "usa",
    "united-states": "usa",
    "united-states-of-america": "usa",
    "uk": "uk",
    "u-k": "uk",
    "gb": "uk",
    "great-britain": "uk",
    "britain": "uk",
    "united-kingdom": "uk",
    "england": "uk",
}


@dataclass(frozen=True)
class OutreachLead:
    """A public contact candidate for an outreach campaign."""

    name: str
    email: str
    city: str
    country: str
    source_url: str
    source_note: str = ""

    @property
    def normalised_email(self) -> str:
        """Return the lower-case mailbox used for dedupe checks."""

        return normalise_email(self.email)


@dataclass(frozen=True)
class OutreachMessage:
    """Subject and body for a prepared outreach email."""

    subject: str
    body: str
    variant_id: str


@dataclass(frozen=True)
class PreparedOutreachEmail:
    """A Gmail-ready email plus the non-reversible recipient hash."""

    lead: OutreachLead
    email_hash: str
    campaign_id: str
    interview_campaign_id: str
    locale: str
    language: str
    quota_key: str
    variant_id: str
    subject: str
    body: str

    def as_record(self) -> dict[str, object]:
        """Return a JSON-serialisable draft payload."""

        body = self.body.replace("{salutation}", "Buongiorno,")
        interview_url = ""
        if "{interview_url}" in body:
            interview_url = _create_campaign_interview_url(self)
            body = body.replace("{interview_url}", interview_url)
        record = {
            "campaign_id": self.campaign_id,
            "interview_campaign_id": self.interview_campaign_id,
            "email_hash": self.email_hash,
            "locale": self.locale,
            "language": self.language,
            "quota_key": self.quota_key,
            "variant_id": self.variant_id,
            "to": self.lead.normalised_email,
            "subject": self.subject,
            "body": body,
            "name": self.lead.name,
            "city": self.lead.city,
            "country": self.lead.country,
            "source_url": self.lead.source_url,
            "source_note": self.lead.source_note,
        }
        if interview_url:
            record["interview_url"] = interview_url
            record["retain_recipient_email"] = True
        return record


def normalise_email(value: str) -> str:
    """Return a canonical email address suitable for hashing."""

    _display_name, address = parseaddr(value.strip())
    cleaned = address.casefold()
    if not cleaned or "@" not in cleaned:
        raise ValueError(f"Invalid email address: {value!r}")
    local_part, domain = cleaned.rsplit("@", 1)
    if not local_part or "." not in domain:
        raise ValueError(f"Invalid email address: {value!r}")
    return cleaned


def normalise_language(value: str) -> str:
    """Return the compact language key used for message selection."""

    cleaned = value.strip().casefold().replace("_", "-")
    if not cleaned:
        raise ValueError("language is required")
    return _LANGUAGE_ALIASES.get(cleaned, cleaned)


def normalise_locale(value: str) -> str:
    """Return the compact locale key used as optional reporting metadata."""

    cleaned = value.strip().casefold().replace("_", "-").replace(" ", "-")
    if not cleaned:
        raise ValueError("locale is required")
    return _LOCALE_ALIASES.get(cleaned, cleaned)


def normalise_quota_key(value: str) -> str:
    """Return the country/market key used for the daily hard cap."""

    cleaned = value.strip().casefold().replace("_", "-").replace(" ", "-")
    if not cleaned:
        raise ValueError("quota key is required")
    return _QUOTA_KEY_ALIASES.get(cleaned, cleaned)


def quota_daily_limit(quota_key: str) -> int:
    """Return the hard daily limit for a normalized quota key."""

    return QUOTA_DAILY_LIMITS.get(
        normalise_quota_key(quota_key),
        DAILY_COUNTRY_LIMIT,
    )


def email_hash(email: str, *, salt: str = "") -> str:
    """Return the SHA-256 hash used to deduplicate recipients."""

    digest = hashlib.sha256()
    digest.update(_HASH_NAMESPACE.encode("utf-8"))
    digest.update(b"\0")
    digest.update(salt.encode("utf-8"))
    digest.update(b"\0")
    digest.update(normalise_email(email).encode("utf-8"))
    return digest.hexdigest()


def parse_outreach_template(path: Path) -> OutreachMessage:
    """Load an approved outreach template with a localized subject line."""

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Outreach template is empty: {path}")
    lines = text.splitlines()
    first_line = lines[0].strip()
    label, separator, subject = first_line.partition(":")
    if not separator:
        raise ValueError(f"Template first line must contain a subject: {path}")
    if label.strip().casefold() not in {"subject", "oggetto", "objet"}:
        raise ValueError(f"Unsupported template subject label: {label!r}")
    cleaned_subject = subject.strip()
    if not cleaned_subject:
        raise ValueError(f"Template subject is empty: {path}")
    body = "\n".join(lines[1:]).lstrip()
    if not body:
        raise ValueError(f"Template body is empty: {path}")
    return OutreachMessage(
        subject=cleaned_subject,
        body=body,
        variant_id=f"template:{path.stem}",
    )


def load_leads_csv(path: Path) -> list[OutreachLead]:
    """Read outreach leads from a CSV file."""

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Lead CSV has no header row: {path}")
        missing_columns = REQUIRED_LEAD_COLUMNS.difference(reader.fieldnames)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Lead CSV is missing required columns: {missing}")
        leads = [
            OutreachLead(
                name=_required_cell(row, "name"),
                email=_required_cell(row, "email"),
                city=_required_cell(row, "city"),
                country=_required_cell(row, "country"),
                source_url=_required_cell(row, "source_url"),
                source_note=(
                    (row["source_note"] or "").strip() if "source_note" in row else ""
                ),
            )
            for row in reader
        ]
    for lead in leads:
        normalise_email(lead.email)
    return leads


def load_blocked_hashes(
    ledger_path: Path,
    *,
    blocking_statuses: Iterable[str] = BLOCKING_STATUSES,
) -> set[str]:
    """Load hashes already used by statuses that should block recontacting."""

    if not ledger_path.exists():
        return set()

    statuses = set(blocking_statuses)
    blocked_hashes: set[str] = set()
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in ledger {ledger_path} line {line_number}"
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(
                    f"Invalid ledger record in {ledger_path} line {line_number}"
                )
            status_value = payload["status"] if "status" in payload else ""
            hash_value = payload["email_hash"] if "email_hash" in payload else ""
            if str(status_value) in statuses and hash_value:
                blocked_hashes.add(str(hash_value))
    return blocked_hashes


def daily_language_usage(
    ledger_path: Path,
    *,
    language: str,
    quota_day: date,
    quota_statuses: Iterable[str] = QUOTA_STATUSES,
) -> int:
    """Count ledger entries that reserve a daily slot for a language."""

    if not ledger_path.exists():
        return 0

    normalised_language = normalise_language(language)
    statuses = set(quota_statuses)
    used_slots = 0
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            record = _load_ledger_record(ledger_path, line_number, stripped)
            status_value = str(record["status"]) if "status" in record else ""
            if status_value not in statuses:
                continue
            if _record_language(record) != normalised_language:
                continue
            if _record_day(record) != quota_day:
                continue
            used_slots += 1
    return used_slots


def daily_quota_usage(
    ledger_path: Path,
    *,
    quota_key: str,
    quota_day: date,
    quota_statuses: Iterable[str] = QUOTA_STATUSES,
) -> int:
    """Count ledger entries that reserve a daily slot for a country/market."""

    if not ledger_path.exists():
        return 0

    normalised_quota_key = normalise_quota_key(quota_key)
    statuses = set(quota_statuses)
    used_slots = 0
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            record = _load_ledger_record(ledger_path, line_number, stripped)
            status_value = str(record["status"]) if "status" in record else ""
            if status_value not in statuses:
                continue
            if _record_quota_key(record) != normalised_quota_key:
                continue
            if _record_day(record) != quota_day:
                continue
            used_slots += 1
    return used_slots


def daily_country_usage(
    ledger_path: Path,
    *,
    country: str,
    quota_day: date,
    quota_statuses: Iterable[str] = QUOTA_STATUSES,
) -> int:
    """Count ledger entries that reserve a daily slot for a country."""

    return daily_quota_usage(
        ledger_path,
        quota_key=country,
        quota_day=quota_day,
        quota_statuses=quota_statuses,
    )


def build_italian_commercialisti_message(
    _lead: OutreachLead,
    *,
    variant_id: str = ITALIAN_COMMERCIALISTI_VARIANT_IDS[0],
) -> OutreachMessage:
    """Build one Italian commercialisti outreach message variant."""

    if variant_id == "it-a":
        return OutreachMessage(
            subject="Ricerca sull'uso dell'AI negli studi professionali",
            variant_id=variant_id,
            body=(
                "{salutation}\n\n"
                "Sto raccogliendo interviste brevi con commercialisti e studi "
                "professionali su come l'intelligenza artificiale viene usata "
                "davvero nel lavoro quotidiano.\n\n"
                "Non e' un messaggio commerciale. L'intervista dura circa 10 minuti "
                "ed e' condotta da un intervistatore AI. Al termine della "
                "raccolta condividero' una sintesi comparativa dei risultati.\n\n"
                "Se le interessa partecipare, puo' aprire questo link:\n"
                "{interview_url}\n\n"
                "Cordialmente,\n"
                "Mparanza"
            ),
        )
    if variant_id == "it-b":
        return OutreachMessage(
            subject="Intervista sull'AI negli studi professionali",
            variant_id=variant_id,
            body=(
                "{salutation}\n\n"
                "Sto preparando una raccolta di interviste con professionisti "
                "contabili in diversi Paesi per capire dove l'AI e' gia' utile, "
                "dove non e' affidabile e quali timori restano aperti.\n\n"
                "La partecipazione richiede circa 10 minuti. L'intervista e' "
                "condotta da un intervistatore AI e servira' per una sintesi "
                "comparativa che condividero' a fine raccolta.\n\n"
                "Il link per partecipare e':\n"
                "{interview_url}\n\n"
                "Cordialmente,\n"
                "Mparanza"
            ),
        )
    if variant_id == "it-c":
        return OutreachMessage(
            subject="Come gli studi stanno usando l'AI?",
            variant_id=variant_id,
            body=(
                "{salutation}\n\n"
                "Vorrei raccogliere il punto di vista di commercialisti e studi "
                "professionali sull'uso reale dell'AI: attivita' gia' supportate, "
                "limiti pratici, riservatezza, affidabilita' e impatto sul lavoro "
                "dello studio.\n\n"
                "L'intervista dura circa 10 minuti, puo' essere fatta in italiano "
                "ed e' condotta da un intervistatore AI. Condividero' poi una "
                "sintesi comparativa dei risultati.\n\n"
                "Per partecipare:\n"
                "{interview_url}\n\n"
                "Cordialmente,\n"
                "Mparanza"
            ),
        )
    raise ValueError(f"Unsupported Italian message variant: {variant_id}")


def _create_campaign_interview_url(item: PreparedOutreachEmail) -> str:
    from modules.hosted_interviews.api import (
        PreparedInterviewRequest,
        create_prepared_interview,
    )

    if not item.interview_campaign_id:
        raise ValueError(
            "interview_campaign_id is required when outreach copy uses "
            "{interview_url}."
        )
    _token, record = create_prepared_interview(
        PreparedInterviewRequest.model_validate(
            build_campaign_interview_payload(
                item.interview_campaign_id,
                case_id=build_outreach_interview_case_id(
                    item.campaign_id, item.email_hash
                ),
                language=item.language,
                interviewee_role=outreach_interviewee_role(item.locale, item.quota_key),
            )
        ),
    )
    return str(record["public_url"])


def prepare_outreach_batch(
    leads: Iterable[OutreachLead],
    *,
    ledger_path: Path,
    campaign_id: str,
    interview_campaign_id: str,
    language: str,
    limit: int,
    locale: str | None = None,
    quota_key: str | None = None,
    salt: str = "",
    status: str = "prepared",
    created_at: datetime | None = None,
) -> list[PreparedOutreachEmail]:
    """Prepare a deduplicated batch and append hash records to the ledger."""

    return _prepare_outreach_batch(
        leads,
        ledger_path=ledger_path,
        campaign_id=campaign_id,
        interview_campaign_id=interview_campaign_id,
        language=language,
        limit=limit,
        message_for_lead=lambda lead, index: build_italian_commercialisti_message(
            lead,
            variant_id=ITALIAN_COMMERCIALISTI_VARIANT_IDS[
                index % len(ITALIAN_COMMERCIALISTI_VARIANT_IDS)
            ],
        ),
        locale=locale,
        quota_key=quota_key,
        salt=salt,
        status=status,
        created_at=created_at,
    )


def prepare_template_outreach_batch(
    leads: Iterable[OutreachLead],
    *,
    ledger_path: Path,
    campaign_id: str,
    interview_campaign_id: str = "",
    language: str,
    limit: int,
    message: OutreachMessage,
    locale: str | None = None,
    quota_key: str | None = None,
    salt: str = "",
    status: str = "prepared",
    created_at: datetime | None = None,
) -> list[PreparedOutreachEmail]:
    """Prepare a deduplicated batch using a pre-approved message template."""

    return _prepare_outreach_batch(
        leads,
        ledger_path=ledger_path,
        campaign_id=campaign_id,
        interview_campaign_id=interview_campaign_id,
        language=language,
        limit=limit,
        message_for_lead=lambda _lead, _index: message,
        locale=locale,
        quota_key=quota_key,
        salt=salt,
        status=status,
        created_at=created_at,
    )


def _prepare_outreach_batch(
    leads: Iterable[OutreachLead],
    *,
    ledger_path: Path,
    campaign_id: str,
    interview_campaign_id: str,
    language: str,
    limit: int,
    message_for_lead: Callable[[OutreachLead, int], OutreachMessage],
    locale: str | None,
    quota_key: str | None,
    salt: str,
    status: str,
    created_at: datetime | None,
) -> list[PreparedOutreachEmail]:
    """Prepare a deduplicated batch and append hash records to the ledger."""

    normalised_locale = normalise_locale(locale) if locale else ""
    normalised_language = normalise_language(language)
    normalised_quota_key = normalise_quota_key(
        quota_key or normalised_locale or normalised_language
    )
    quota_limit = quota_daily_limit(normalised_quota_key)
    if limit < 1 or limit > quota_limit:
        raise ValueError(f"limit must be between 1 and {quota_limit}")

    timestamp_value = created_at or datetime.now(timezone.utc)
    quota_day = timestamp_value.date()
    used_slots = daily_quota_usage(
        ledger_path,
        quota_key=normalised_quota_key,
        quota_day=quota_day,
    )
    remaining_slots = quota_limit - used_slots
    if remaining_slots <= 0:
        LOGGER.warning(
            "Daily outreach quota is exhausted for quota_key=%s day=%s",
            normalised_quota_key,
            quota_day.isoformat(),
        )
        return []
    if limit > remaining_slots:
        LOGGER.warning(
            "Capping outreach batch from %s to %s for quota_key=%s day=%s",
            limit,
            remaining_slots,
            normalised_quota_key,
            quota_day.isoformat(),
        )
    allowed_count = min(limit, remaining_slots)
    blocked_hashes = load_blocked_hashes(ledger_path)
    timestamp = timestamp_value.isoformat()
    prepared: list[PreparedOutreachEmail] = []
    seen_in_batch: set[str] = set()

    for lead in leads:
        digest = email_hash(lead.email, salt=salt)
        if digest in blocked_hashes or digest in seen_in_batch:
            LOGGER.info("Skipping already prepared recipient hash %s", digest)
            continue
        message = message_for_lead(lead, len(prepared))
        prepared.append(
            PreparedOutreachEmail(
                lead=lead,
                email_hash=digest,
                campaign_id=campaign_id,
                interview_campaign_id=interview_campaign_id,
                locale=normalised_locale,
                language=normalised_language,
                quota_key=normalised_quota_key,
                variant_id=message.variant_id,
                subject=message.subject,
                body=message.body,
            )
        )
        seen_in_batch.add(digest)
        if len(prepared) == allowed_count:
            break

    if prepared:
        _append_ledger_records(
            ledger_path,
            [
                {
                    "campaign_id": item.campaign_id,
                    "interview_campaign_id": item.interview_campaign_id,
                    "email_hash": item.email_hash,
                    "status": status,
                    "created_at": timestamp,
                    "quota_day": quota_day.isoformat(),
                    "locale": item.locale,
                    "language": item.language,
                    "quota_key": item.quota_key,
                    "variant_id": item.variant_id,
                    "country": item.lead.country,
                    "city": item.lead.city,
                    "source_url": item.lead.source_url,
                }
                for item in prepared
            ],
        )

    return prepared


def write_prepared_batch_jsonl(
    path: Path, items: Iterable[PreparedOutreachEmail]
) -> None:
    """Write Gmail-ready draft payloads as JSON Lines."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item.as_record(), ensure_ascii=False))
            handle.write("\n")


def record_outreach_batch_sent(
    batch_path: Path,
    *,
    ledger_path: Path,
    gmail_message_ids: Mapping[str, str],
    sent_at: datetime | None = None,
    gmail_sent_deleted_at: datetime | None = None,
) -> int:
    """Mark a prepared batch as sent after Gmail returns message IDs."""

    sent_timestamp = _iso_timestamp(sent_at or datetime.now(timezone.utc))
    deleted_timestamp = (
        _iso_timestamp(gmail_sent_deleted_at) if gmail_sent_deleted_at else ""
    )
    batch_records: list[dict[str, object]] = []
    sent_updates: dict[tuple[str, str], dict[str, str]] = {}

    with batch_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            record = _load_ledger_record(batch_path, line_number, stripped)
            campaign_id = str(record["campaign_id"]) if "campaign_id" in record else ""
            email_hash_value = (
                str(record["email_hash"]) if "email_hash" in record else ""
            )
            if not campaign_id or not email_hash_value:
                raise ValueError(
                    f"Batch record in {batch_path} line {line_number} must include "
                    "campaign_id and email_hash"
                )
            gmail_message_id = (gmail_message_ids.get(email_hash_value) or "").strip()
            if not gmail_message_id:
                raise ValueError(
                    "Missing Gmail message ID for sent outreach hash "
                    f"{email_hash_value}"
                )
            record["status"] = "sent"
            record["gmail_message_id"] = gmail_message_id
            record["sent_at"] = sent_timestamp
            if deleted_timestamp:
                record["gmail_sent_deleted_at"] = deleted_timestamp
            batch_records.append(record)
            sent_updates[(campaign_id, email_hash_value)] = {
                "gmail_message_id": gmail_message_id,
                "sent_at": sent_timestamp,
                "gmail_sent_deleted_at": deleted_timestamp,
            }

    if not sent_updates:
        return 0

    _mark_ledger_records_sent(ledger_path, sent_updates)
    with batch_path.open("w", encoding="utf-8") as handle:
        for record in batch_records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return len(sent_updates)


def scrub_raw_emails(path: Path, *, ledger_path: Path, salt: str = "") -> int:
    """Delete raw outreach email addresses after their hashes are recorded."""

    if path.suffix.casefold() == ".csv":
        return _scrub_csv_emails(path, ledger_path=ledger_path, salt=salt)
    if path.suffix.casefold() == ".jsonl":
        return _scrub_jsonl_recipients(path, ledger_path=ledger_path, salt=salt)
    raise ValueError(f"Unsupported outreach scrub file type: {path}")


def _required_cell(row: dict[str, str], column: str) -> str:
    value = (row[column] or "").strip()
    if not value:
        raise ValueError(f"Lead CSV row is missing {column!r}")
    return value


def _load_ledger_record(
    ledger_path: Path, line_number: int, stripped: str
) -> dict[str, object]:
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in ledger {ledger_path} line {line_number}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid ledger record in {ledger_path} line {line_number}")
    return payload


def _scrub_csv_emails(path: Path, *, ledger_path: Path, salt: str) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Lead CSV has no header row: {path}")
        if "email" not in reader.fieldnames:
            raise ValueError(f"Lead CSV has no email column: {path}")
        rows = list(reader)
        fieldnames = list(reader.fieldnames)

    scrubbed_count = 0
    for row in rows:
        raw_email = (row.get("email") or "").strip()
        if not raw_email:
            continue
        _ensure_hash_recorded(raw_email, ledger_path=ledger_path, salt=salt)
        row["email"] = ""
        scrubbed_count += 1

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return scrubbed_count


def _scrub_jsonl_recipients(path: Path, *, ledger_path: Path, salt: str) -> int:
    records: list[dict[str, object]] = []
    scrubbed_count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            record = _load_ledger_record(path, line_number, stripped)
            raw_email = str(record["to"]) if "to" in record else ""
            if raw_email:
                digest = email_hash(raw_email, salt=salt)
                recorded_hash = (
                    str(record["email_hash"]) if "email_hash" in record else ""
                )
                if recorded_hash and recorded_hash != digest:
                    raise ValueError(
                        f"Recipient hash mismatch in {path} line {line_number}"
                    )
                _ensure_hash_recorded(raw_email, ledger_path=ledger_path, salt=salt)
                del record["to"]
                record["recipient_deleted"] = True
                scrubbed_count += 1
            records.append(record)

    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return scrubbed_count


def _ensure_hash_recorded(raw_email: str, *, ledger_path: Path, salt: str) -> None:
    digest = email_hash(raw_email, salt=salt)
    if digest not in load_blocked_hashes(ledger_path):
        raise ValueError(
            "Refusing to delete raw email because its hash is not recorded "
            f"in the outreach ledger: {ledger_path}"
        )


def _mark_ledger_records_sent(
    ledger_path: Path,
    sent_updates: Mapping[tuple[str, str], Mapping[str, str]],
) -> None:
    if not ledger_path.exists():
        raise ValueError(f"Outreach ledger does not exist: {ledger_path}")

    ledger_records: list[dict[str, object]] = []
    found_keys: set[tuple[str, str]] = set()
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            record = _load_ledger_record(ledger_path, line_number, stripped)
            campaign_id = str(record["campaign_id"]) if "campaign_id" in record else ""
            email_hash_value = (
                str(record["email_hash"]) if "email_hash" in record else ""
            )
            key = (campaign_id, email_hash_value)
            update = sent_updates.get(key)
            if update is not None:
                record["status"] = "sent"
                record["gmail_message_id"] = update["gmail_message_id"]
                record["sent_at"] = update["sent_at"]
                deleted_at = update["gmail_sent_deleted_at"]
                if deleted_at:
                    record["gmail_sent_deleted_at"] = deleted_at
                found_keys.add(key)
            ledger_records.append(record)

    missing_keys = set(sent_updates).difference(found_keys)
    if missing_keys:
        missing = ", ".join(
            f"{campaign_id}:{email_hash_value}"
            for campaign_id, email_hash_value in sorted(missing_keys)
        )
        raise ValueError(
            "Cannot mark outreach as sent because hashes are not recorded in "
            f"the ledger: {missing}"
        )

    with ledger_path.open("w", encoding="utf-8") as handle:
        for record in ledger_records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _record_language(record: dict[str, object]) -> str:
    language = str(record["language"]) if "language" in record else ""
    if language:
        return normalise_language(language)
    campaign_id = str(record["campaign_id"]) if "campaign_id" in record else ""
    country = str(record["country"]) if "country" in record else ""
    city = str(record["city"]) if "city" in record else ""
    if campaign_id.startswith("italy-") or country.casefold() in {"italy", "italia"}:
        return "it"
    if city:
        city_locale = normalise_locale(city)
        if city_locale == "geneva":
            return "fr"
        if city_locale == "zurich":
            return "de"
    country_locale = normalise_locale(country) if country else ""
    if country_locale == "usa":
        return "en"
    if campaign_id:
        prefix = campaign_id.split("-", 1)[0]
        if prefix in {"it", "fr", "de", "en"}:
            return normalise_language(prefix)
    return ""


def _record_quota_key(record: dict[str, object]) -> str:
    quota_key = str(record["quota_key"]) if "quota_key" in record else ""
    if quota_key:
        return normalise_quota_key(quota_key)
    locale = str(record["locale"]) if "locale" in record else ""
    if locale:
        return normalise_quota_key(locale)
    country = str(record["country"]) if "country" in record else ""
    if country:
        return normalise_quota_key(country)
    campaign_id = str(record["campaign_id"]) if "campaign_id" in record else ""
    if campaign_id.startswith("italy-"):
        return "italy"
    if campaign_id.startswith("swiss-") or "switzerland" in campaign_id:
        return "switzerland"
    if campaign_id.startswith("usa-") or campaign_id.startswith("us-"):
        return "usa"
    if campaign_id.startswith("uk-") or "united-kingdom" in campaign_id:
        return "uk"
    return _record_language(record)


def _record_day(record: dict[str, object]) -> date | None:
    quota_day = str(record["quota_day"]) if "quota_day" in record else ""
    if quota_day:
        return date.fromisoformat(quota_day)
    created_at = str(record["created_at"]) if "created_at" in record else ""
    if not created_at:
        return None
    return datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()


def _append_ledger_records(
    ledger_path: Path, records: Iterable[dict[str, str]]
) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
