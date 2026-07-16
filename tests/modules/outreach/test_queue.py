from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from modules.hosted_interviews.campaigns import (
    AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
    COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID,
)
from modules.outreach import OutreachMessage, email_hash
from modules.outreach.queue import (
    eligible_queue_status,
    prepare_queue_outreach_batch,
    record_queue_batch_sent,
)


def test_eligible_queue_status_accepts_blank_and_queued_only() -> None:
    assert eligible_queue_status("") is True
    assert eligible_queue_status(" queued ") is True
    assert eligible_queue_status("sent") is False
    assert eligible_queue_status("prepared") is False


def test_prepare_queue_outreach_batch_sends_available_rows_without_ledger_reservation(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "queue.csv"
    batch_path = tmp_path / "batch.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    _write_queue(
        queue_path,
        [
            _queue_row("Firm A", "info-a@example.com", ""),
            _queue_row("Firm B", "info-b@example.com", "queued"),
        ],
    )

    result = prepare_queue_outreach_batch(
        queue_path,
        batch_path,
        ledger_path=ledger_path,
        campaign_id="uk-accountants-2026-06-01",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="en",
        locale="uk",
        quota_key="uk",
        message=_message(),
        run_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        limit=10,
    )

    records = [json.loads(line) for line in batch_path.read_text().splitlines()]
    rows = _read_queue(queue_path)
    assert result.prepared_count == 2
    assert result.shortage_count == 8
    assert [record["to"] for record in records] == [
        "info-a@example.com",
        "info-b@example.com",
    ]
    assert [row["status"] for row in rows] == ["prepared", "prepared"]
    assert not ledger_path.exists()


def test_prepare_queue_outreach_batch_blocks_duplicate_hash_and_scrubs_email(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "queue.csv"
    batch_path = tmp_path / "batch.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    duplicate_email = "duplicate@example.com"
    ledger_path.write_text(
        json.dumps({"email_hash": email_hash(duplicate_email), "status": "sent"})
        + "\n",
        encoding="utf-8",
    )
    _write_queue(
        queue_path,
        [
            _queue_row("Already Sent", duplicate_email, "queued"),
            _queue_row("New Firm", "new@example.com", "queued"),
        ],
    )

    result = prepare_queue_outreach_batch(
        queue_path,
        batch_path,
        ledger_path=ledger_path,
        campaign_id="uk-accountants-2026-06-01",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="en",
        locale="uk",
        quota_key="uk",
        message=_message(),
        run_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        limit=10,
    )

    rows = _read_queue(queue_path)
    records = [json.loads(line) for line in batch_path.read_text().splitlines()]
    assert result.prepared_count == 1
    assert result.duplicate_count == 1
    assert rows[0]["status"] == "blocked_duplicate"
    assert rows[0]["email"] == ""
    assert rows[0]["last_error"] == "duplicate-email-hash"
    assert records[0]["to"] == "new@example.com"


def test_prepare_queue_outreach_batch_uses_organization_daily_limit(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "queue.csv"
    batch_path = tmp_path / "batch.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "email_hash": email_hash(f"old{index}@example.com"),
                    "status": "sent",
                    "quota_key": "italy-organization",
                    "quota_day": "2026-05-29",
                }
            )
            for index in range(4)
        )
        + "\n",
        encoding="utf-8",
    )
    _write_queue(
        queue_path,
        [
            _queue_row("ODCEC A", "ordine-a@example.com", "queued"),
            _queue_row("ODCEC B", "ordine-b@example.com", "queued"),
        ],
    )

    result = prepare_queue_outreach_batch(
        queue_path,
        batch_path,
        ledger_path=ledger_path,
        campaign_id="italy-odcec-2026-05-29",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="it",
        locale="italy",
        quota_key="odcec",
        message=_message(),
        run_at=datetime(2026, 5, 29, 8, 0, tzinfo=timezone.utc),
        limit=5,
    )

    records = [json.loads(line) for line in batch_path.read_text().splitlines()]
    assert result.prepared_count == 1
    assert result.shortage_count == 0
    assert records[0]["quota_key"] == "italy-organization"


def test_prepare_queue_outreach_batch_personalizes_salutation(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "queue.csv"
    batch_path = tmp_path / "batch.jsonl"
    _write_queue(
        queue_path,
        [
            {
                **_queue_row("Example Recipient", "recipient@example.com", "queued"),
                "country": "Italy",
                "source_note": "odcec-firenze-albo-pdf",
            }
        ],
    )

    prepare_queue_outreach_batch(
        queue_path,
        batch_path,
        ledger_path=tmp_path / "ledger.jsonl",
        campaign_id="italy-odcec-2026-06-01",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="it",
        locale="italy",
        quota_key="italy-organization",
        message=OutreachMessage(
            subject="AI e lavoro su file",
            body="{salutation}\n\nCorpo del messaggio",
            variant_id="template:odcec",
        ),
        run_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        limit=5,
    )

    record = json.loads(batch_path.read_text())
    assert record["body"].startswith("Gentile Dott. Example,")


def test_prepare_queue_outreach_batch_uses_buongiorno_without_usable_name(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "queue.csv"
    batch_path = tmp_path / "batch.jsonl"
    _write_queue(
        queue_path,
        [
            {
                **_queue_row("", "segreteria@example.com", "queued"),
                "country": "Italy",
                "source_note": "odcec-firenze-albo-pdf",
            }
        ],
    )

    prepare_queue_outreach_batch(
        queue_path,
        batch_path,
        ledger_path=tmp_path / "ledger.jsonl",
        campaign_id="italy-odcec-2026-06-01",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="it",
        locale="italy",
        quota_key="italy-organization",
        message=OutreachMessage(
            subject="AI e lavoro su file",
            body="{salutation}\n\nCorpo del messaggio",
            variant_id="template:odcec",
        ),
        run_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        limit=5,
    )

    record = json.loads(batch_path.read_text())
    assert record["body"].startswith("Buongiorno,")


def test_record_queue_batch_sent_appends_ledger_and_scrubs_raw_recipients(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "queue.csv"
    batch_path = tmp_path / "batch.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    _write_queue(queue_path, [_queue_row("Firm A", "info-a@example.com", "queued")])
    prepare_queue_outreach_batch(
        queue_path,
        batch_path,
        ledger_path=ledger_path,
        campaign_id="uk-accountants-2026-06-01",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="en",
        locale="uk",
        quota_key="uk",
        message=_message(),
        run_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        limit=10,
    )
    digest = email_hash("info-a@example.com")

    sent_count = record_queue_batch_sent(
        batch_path,
        queue_path,
        ledger_path=ledger_path,
        gmail_message_ids={digest: "gmail-123"},
        sent_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        gmail_sent_deleted_at=datetime(2026, 6, 1, 9, 1, tzinfo=timezone.utc),
    )

    queue_row = _read_queue(queue_path)[0]
    batch_record = json.loads(batch_path.read_text())
    ledger_record = json.loads(ledger_path.read_text())
    assert sent_count == 1
    assert queue_row["status"] == "sent"
    assert queue_row["email"] == ""
    assert queue_row["gmail_message_id"] == "gmail-123"
    assert "to" not in batch_record
    assert batch_record["recipient_deleted"] is True
    assert ledger_record["status"] == "sent"
    assert ledger_record["email_hash"] == digest
    assert ledger_record["gmail_sent_deleted_at"] == "2026-06-01T09:01:00+00:00"
    assert "product_url" not in batch_record
    assert "product_url" not in ledger_record


def test_research_interview_batch_scrubs_email_after_gmail_sent_deletion(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "queue.csv"
    batch_path = tmp_path / "batch.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    _write_queue(
        queue_path,
        [
            {
                **_queue_row("Firm A", "info-a@example.com", "queued"),
                "interview_url": "https://mparanza.com/case-notes/interview/test",
                "interview_campaign_id": AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
            }
        ],
    )
    message = OutreachMessage(
        subject="Research on AI use in accounting firms",
        body=("Good morning,\n\n" "Please participate here:\n" "{interview_url}\n"),
        variant_id="template:ai-research",
    )
    prepare_queue_outreach_batch(
        queue_path,
        batch_path,
        ledger_path=ledger_path,
        campaign_id="uk-accountants-2026-06-01",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="en",
        locale="uk",
        quota_key="uk",
        message=message,
        run_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        limit=10,
    )
    digest = email_hash("info-a@example.com")

    record_queue_batch_sent(
        batch_path,
        queue_path,
        ledger_path=ledger_path,
        gmail_message_ids={digest: "gmail-123"},
        sent_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        gmail_sent_deleted_at=datetime(2026, 6, 1, 9, 1, tzinfo=timezone.utc),
    )

    queue_row = _read_queue(queue_path)[0]
    batch_record = json.loads(batch_path.read_text())
    assert queue_row["email"] == ""
    assert "to" not in batch_record
    assert batch_record["recipient_deleted"] is True
    assert batch_record["retain_recipient_email"] is False
    assert batch_record["gmail_sent_deleted_at"] == "2026-06-01T09:01:00+00:00"


def test_prepare_queue_outreach_batch_generates_distinct_interview_urls(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "hosted"))
    queue_path = tmp_path / "queue.csv"
    batch_path = tmp_path / "batch.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    _write_queue(
        queue_path,
        [
            _queue_row("Firm A", "info-a@example.com", "queued"),
            _queue_row("Firm B", "info-b@example.com", "queued"),
        ],
    )
    message = OutreachMessage(
        subject="Research on AI use in accounting firms",
        body=("Good morning,\n\n" "Please participate here:\n" "{interview_url}\n"),
        variant_id="template:ai-research",
    )

    prepare_queue_outreach_batch(
        queue_path,
        batch_path,
        ledger_path=ledger_path,
        campaign_id="uk-accountants-2026-06-01",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="en",
        locale="uk",
        quota_key="uk",
        message=message,
        run_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        limit=10,
    )

    rows = _read_queue(queue_path)
    records = [json.loads(line) for line in batch_path.read_text().splitlines()]
    urls = [record["interview_url"] for record in records]
    assert len(urls) == 2
    assert len(set(urls)) == 2
    assert all(
        url.startswith("https://mparanza.com/case-notes/interview/") for url in urls
    )
    assert [row["interview_url"] for row in rows] == urls
    assert [row["interview_campaign_id"] for row in rows] == [
        AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
    ]
    assert all(url in record["body"] for url, record in zip(urls, records))
    assert [record["retain_recipient_email"] for record in records] == [False, False]
    assert [record["interview_campaign_id"] for record in records] == [
        AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
    ]
    hosted_records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "hosted" / "sessions").glob("*/interview.json")
    ]
    assert len(hosted_records) == 2
    assert {
        hosted_record["interview_campaign_id"] for hosted_record in hosted_records
    } == {AI_ADOPTION_RESEARCH_CAMPAIGN_ID}


def test_prepare_queue_outreach_batch_rejects_cross_campaign_url_reuse(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "queue.csv"
    batch_path = tmp_path / "batch.jsonl"
    existing_url = "https://mparanza.com/case-notes/interview/existing"
    _write_queue(
        queue_path,
        [
            {
                **_queue_row("Firm A", "info-a@example.com", "queued"),
                "interview_url": existing_url,
                "interview_campaign_id": AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
            }
        ],
    )
    message = OutreachMessage(
        subject="Commercialisti AI needs",
        body="Good morning,\n\n{interview_url}\n",
        variant_id="template:ai-needs",
    )

    with pytest.raises(ValueError, match="different interview campaign"):
        prepare_queue_outreach_batch(
            queue_path,
            batch_path,
            ledger_path=tmp_path / "ledger.jsonl",
            campaign_id="commercialisti-participants-2026-07-12",
            interview_campaign_id=COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID,
            language="it",
            locale="italy",
            quota_key="italy",
            message=message,
            run_at=datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc),
            limit=10,
        )

    assert _read_queue(queue_path)[0]["interview_url"] == existing_url
    assert not batch_path.exists()


def _message() -> OutreachMessage:
    return OutreachMessage(
        subject="Research on AI use in accounting firms",
        body=(
            "Good morning,\n\n"
            "I am collecting short interviews about how AI is used in daily work.\n\n"
            "Best regards,\nResearch Team"
        ),
        variant_id="template:approved",
    )


def _queue_row(name: str, email: str, status: str) -> dict[str, str]:
    return {
        "name": name,
        "email": email,
        "salutation": "",
        "city": "London",
        "country": "United Kingdom",
        "source_url": "https://example.com/source",
        "source_note": "public-directory",
        "status": status,
        "email_hash": "",
        "sent_at": "",
        "gmail_message_id": "",
        "gmail_sent_deleted_at": "",
        "last_error": "",
    }


def _write_queue(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_queue(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
