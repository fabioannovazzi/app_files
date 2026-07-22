from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from modules.hosted_interviews.campaigns import AI_ADOPTION_RESEARCH_CAMPAIGN_ID
from modules.outreach import (
    DAILY_COUNTRY_LIMIT,
    OutreachLead,
    daily_quota_usage,
    email_hash,
    load_blocked_hashes,
    load_leads_csv,
    normalise_email,
    normalise_language,
    normalise_locale,
    normalise_quota_key,
    parse_outreach_template,
    prepare_outreach_batch,
    prepare_template_outreach_batch,
    quota_daily_limit,
    record_outreach_batch_sent,
    scrub_raw_emails,
    write_prepared_batch_jsonl,
)


def _lead(email: str, name: str = "Studio Test") -> OutreachLead:
    return OutreachLead(
        name=name,
        email=email,
        city="Roma",
        country="Italy",
        source_url="https://example.com",
    )


def test_normalise_email_accepts_display_name_and_lowercases() -> None:
    assert normalise_email("Studio <Info@Example.COM>") == "info@example.com"


@pytest.mark.parametrize(
    ("alias", "expected"),
    (("Italian", "it"), ("Spanish", "es"), ("Español", "es"), ("spa", "es")),
)
def test_normalise_language_maps_aliases(alias: str, expected: str) -> None:
    assert normalise_language(alias) == expected


def test_normalise_locale_maps_aliases() -> None:
    assert normalise_locale("United States") == "usa"
    assert normalise_locale("United Kingdom") == "uk"
    assert normalise_locale("España") == "spain"


def test_normalise_quota_key_keeps_swiss_market_bucket() -> None:
    assert normalise_quota_key("swiss-german") == "swiss-german"
    assert normalise_quota_key("United Kingdom") == "uk"
    assert normalise_quota_key("España") == "spain"


def test_normalise_quota_key_maps_organization_bucket() -> None:
    assert normalise_quota_key("odcec") == "italy-organization"
    assert normalise_quota_key("Italy Organizations") == "italy-organization"


def test_quota_daily_limit_uses_five_for_italy_organizations() -> None:
    assert quota_daily_limit("italy-organization") == 5
    assert quota_daily_limit("italy") == DAILY_COUNTRY_LIMIT


def test_email_hash_uses_salt_and_normalised_address() -> None:
    salted_hash = email_hash("Info@Example.com", salt="campaign")
    repeated_hash = email_hash("info@example.com", salt="campaign")
    unsalted_hash = email_hash("info@example.com")

    assert salted_hash == repeated_hash
    assert salted_hash != unsalted_hash


def test_load_leads_csv_requires_expected_columns(tmp_path: Path) -> None:
    path = tmp_path / "leads.csv"
    path.write_text("name,email,city,country\nStudio,info@example.com,Roma,Italy\n")

    with pytest.raises(ValueError, match="source_url"):
        load_leads_csv(path)


def test_prepare_outreach_batch_skips_existing_hashes_and_writes_ledger(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    duplicate_hash = email_hash("info@example.com")
    ledger_path.write_text(
        json.dumps({"email_hash": duplicate_hash, "status": "sent"}) + "\n"
    )
    leads = [
        _lead("info@example.com", name="Already Sent"),
        _lead("nuovo@example.com", name="New Studio"),
    ]

    prepared = prepare_outreach_batch(
        leads,
        ledger_path=ledger_path,
        campaign_id="italy-commercialisti-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=10,
        created_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )

    assert [item.lead.name for item in prepared] == ["New Studio"]
    ledger_lines = ledger_path.read_text().splitlines()
    assert len(ledger_lines) == 2
    new_record = json.loads(ledger_lines[1])
    assert new_record["email_hash"] == email_hash("nuovo@example.com")
    assert new_record["status"] == "prepared"
    assert new_record["locale"] == "italy"
    assert new_record["language"] == "it"
    assert new_record["quota_key"] == "italy"
    assert new_record["variant_id"] == "it-a"
    assert new_record["interview_campaign_id"] == AI_ADOPTION_RESEARCH_CAMPAIGN_ID


def test_prepare_outreach_batch_caps_daily_market_quota(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    existing_records = [
        json.dumps(
            {
                "email_hash": email_hash(f"old{index}@example.com"),
                "status": "sent",
                "locale": "italy",
                "language": "it",
                "quota_key": "italy",
                "created_at": "2026-05-28T07:00:00+00:00",
            }
        )
        for index in range(DAILY_COUNTRY_LIMIT - 1)
    ]
    ledger_path.write_text("\n".join(existing_records) + "\n")
    leads = [_lead(f"new{index}@example.com") for index in range(3)]

    prepared = prepare_outreach_batch(
        leads,
        ledger_path=ledger_path,
        campaign_id="italy-commercialisti-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=3,
        created_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )

    assert len(prepared) == 1
    assert (
        daily_quota_usage(
            ledger_path,
            quota_key="italy",
            quota_day=datetime(2026, 5, 28, tzinfo=timezone.utc).date(),
        )
        == DAILY_COUNTRY_LIMIT
    )


def test_prepare_outreach_batch_refuses_exhausted_market_day(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    existing_records = [
        json.dumps(
            {
                "email_hash": email_hash(f"old{index}@example.com"),
                "status": "prepared",
                "locale": "italy",
                "language": "it",
                "quota_key": "italy",
                "quota_day": "2026-05-28",
            }
        )
        for index in range(DAILY_COUNTRY_LIMIT)
    ]
    ledger_path.write_text("\n".join(existing_records) + "\n")

    prepared = prepare_outreach_batch(
        [_lead("new@example.com")],
        ledger_path=ledger_path,
        campaign_id="italy-commercialisti-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=1,
        created_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )

    assert prepared == []


def test_prepare_outreach_batch_refuses_same_market_with_different_copy_language(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    existing_records = [
        json.dumps(
            {
                "email_hash": email_hash(f"swiss{index}@example.com"),
                "status": "sent",
                "locale": "swiss-german",
                "language": "en",
                "quota_key": "swiss-german",
                "quota_day": "2026-05-28",
            }
        )
        for index in range(DAILY_COUNTRY_LIMIT)
    ]
    ledger_path.write_text("\n".join(existing_records) + "\n")

    prepared = prepare_outreach_batch(
        [_lead("zurich@example.com")],
        ledger_path=ledger_path,
        campaign_id="swiss-german-treuhand-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="swiss-german",
        language="de",
        quota_key="swiss-german",
        limit=1,
        created_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )

    assert prepared == []


def test_prepare_outreach_batch_caps_organization_quota_at_five(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    existing_records = [
        json.dumps(
            {
                "email_hash": email_hash(f"ordine{index}@example.com"),
                "status": "sent",
                "locale": "italy",
                "language": "it",
                "quota_key": "italy-organization",
                "quota_day": "2026-05-29",
            }
        )
        for index in range(4)
    ]
    ledger_path.write_text("\n".join(existing_records) + "\n")

    prepared = prepare_template_outreach_batch(
        [_lead(f"new-ordine{index}@example.com") for index in range(3)],
        ledger_path=ledger_path,
        campaign_id="italy-odcec-2026-05-29",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="it",
        locale="italy",
        quota_key="odcec",
        limit=3,
        message=parse_outreach_template(
            _write_template(tmp_path, "Oggetto: AI\n\nBuongiorno\n")
        ),
        created_at=datetime(2026, 5, 29, tzinfo=timezone.utc),
    )

    assert len(prepared) == 1
    assert prepared[0].quota_key == "italy-organization"


def test_prepare_outreach_batch_allows_same_copy_language_for_different_market(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    existing_records = [
        json.dumps(
            {
                "email_hash": email_hash(f"swiss{index}@example.com"),
                "status": "sent",
                "locale": "swiss-german",
                "language": "en",
                "quota_key": "swiss-german",
                "quota_day": "2026-05-28",
            }
        )
        for index in range(DAILY_COUNTRY_LIMIT)
    ]
    ledger_path.write_text("\n".join(existing_records) + "\n")

    prepared = prepare_outreach_batch(
        [_lead("usa@example.com")],
        ledger_path=ledger_path,
        campaign_id="usa-accounting-en-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="usa",
        language="en",
        quota_key="usa",
        limit=1,
        created_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )

    assert len(prepared) == 1
    assert prepared[0].language == "en"
    assert prepared[0].quota_key == "usa"


def test_prepare_outreach_batch_rejects_limit_above_daily_language_limit(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        prepare_outreach_batch(
            [_lead("info@example.com")],
            ledger_path=tmp_path / "ledger.jsonl",
            campaign_id="italy-commercialisti-2026-05",
            interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
            locale="italy",
            language="it",
            limit=99,
        )


def test_prepare_outreach_batch_rejects_limit_above_organization_limit(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="between 1 and 5"):
        prepare_template_outreach_batch(
            [_lead("ordine@example.com")],
            ledger_path=tmp_path / "ledger.jsonl",
            campaign_id="italy-odcec-2026-05-29",
            interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
            language="it",
            locale="italy",
            quota_key="italy-organization",
            limit=6,
            message=parse_outreach_template(
                _write_template(tmp_path, "Oggetto: AI\n\nBuongiorno\n")
            ),
        )


def test_prepare_outreach_batch_tracks_message_variants(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    leads = [_lead(f"new{index}@example.com") for index in range(4)]

    prepared = prepare_outreach_batch(
        leads,
        ledger_path=ledger_path,
        campaign_id="italy-commercialisti-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=4,
        created_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )

    assert [item.variant_id for item in prepared] == ["it-a", "it-b", "it-c", "it-a"]
    assert len({item.body for item in prepared[:3]}) == 3


def test_load_blocked_hashes_ignores_nonblocking_status(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    failed_hash = email_hash("failed@example.com")
    sent_hash = email_hash("sent@example.com")
    ledger_path.write_text(
        "\n".join(
            [
                json.dumps({"email_hash": failed_hash, "status": "failed"}),
                json.dumps({"email_hash": sent_hash, "status": "sent"}),
            ]
        )
    )

    assert load_blocked_hashes(ledger_path) == {sent_hash}


def test_write_prepared_batch_jsonl_contains_gmail_ready_payload(
    tmp_path: Path, monkeypatch
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    out_path = tmp_path / "batch.jsonl"
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "hosted"))
    prepared = prepare_outreach_batch(
        [_lead("info@example.com")],
        ledger_path=ledger_path,
        campaign_id="italy-commercialisti-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=1,
    )

    write_prepared_batch_jsonl(out_path, prepared)

    payload = json.loads(out_path.read_text().strip())
    hosted_record_path = next(
        (tmp_path / "hosted" / "sessions").glob("*/interview.json")
    )
    hosted_record = json.loads(hosted_record_path.read_text(encoding="utf-8"))
    assert payload["to"] == "info@example.com"
    assert payload["locale"] == "italy"
    assert payload["language"] == "it"
    assert payload["variant_id"] == "it-a"
    assert "product_url" not in payload
    assert payload["subject"] == "Ricerca sull'uso dell'AI negli studi professionali"
    assert "interviste brevi" in payload["body"]
    assert "https://mparanza.com/case-notes/interview/" in payload["body"]
    assert payload["interview_url"] in payload["body"]
    assert payload["retain_recipient_email"] is True
    assert payload["interview_campaign_id"] == AI_ADOPTION_RESEARCH_CAMPAIGN_ID
    assert hosted_record["interview_campaign_id"] == AI_ADOPTION_RESEARCH_CAMPAIGN_ID
    assert "Adoption barriers inside the firm" in hosted_record["priority_topics"]
    assert "plugin" not in payload["body"].casefold()
    assert "beta" not in payload["body"].casefold()


def test_write_prepared_batch_jsonl_generates_one_interview_url_per_recipient(
    tmp_path: Path, monkeypatch
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    out_path = tmp_path / "batch.jsonl"
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "hosted"))
    prepared = prepare_outreach_batch(
        [_lead("first@example.com"), _lead("second@example.com")],
        ledger_path=ledger_path,
        campaign_id="italy-commercialisti-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=2,
    )

    write_prepared_batch_jsonl(out_path, prepared)

    records = [json.loads(line) for line in out_path.read_text().splitlines()]
    urls = [record["interview_url"] for record in records]
    assert len(urls) == 2
    assert len(set(urls)) == 2
    assert all(url in record["body"] for url, record in zip(urls, records))


def test_parse_outreach_template_accepts_localized_subject(tmp_path: Path) -> None:
    template_path = tmp_path / "template.txt"
    template_path.write_text(
        "Oggetto: Ricerca sull'uso dell'AI negli studi professionali\n\n"
        "Buongiorno,\n\n"
        "Partecipa qui: {interview_url}\n",
        encoding="utf-8",
    )

    message = parse_outreach_template(template_path)

    assert message.subject == "Ricerca sull'uso dell'AI negli studi professionali"
    assert message.body.startswith("Buongiorno,")
    assert message.variant_id == "template:template"


def test_parse_outreach_template_accepts_spanish_subject(tmp_path: Path) -> None:
    template_path = tmp_path / "template.txt"
    template_path.write_text(
        "Asunto: Investigación sobre el uso de la IA\n\n"
        "Buenos días:\n\n"
        "Participe aquí: {interview_url}\n",
        encoding="utf-8",
    )

    message = parse_outreach_template(template_path)

    assert message.subject == "Investigación sobre el uso de la IA"
    assert message.body.startswith("Buenos días:")


def test_prepare_template_outreach_batch_uses_approved_message(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    message = parse_outreach_template(
        _write_template(
            tmp_path,
            "Subject: Research on AI use in accounting firms\n\n"
            "Good morning,\n\n"
            "I am collecting short interviews about AI use in daily work.\n\n"
            "Best regards,\n"
            "Example Advisor\n",
        )
    )

    prepared = prepare_template_outreach_batch(
        [_lead("info@example.com")],
        ledger_path=ledger_path,
        campaign_id="uk-accountants-2026-05-29",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="en",
        locale="uk",
        quota_key="uk",
        limit=1,
        message=message,
        created_at=datetime(2026, 5, 29, tzinfo=timezone.utc),
    )

    assert len(prepared) == 1
    assert prepared[0].subject == "Research on AI use in accounting firms"
    assert prepared[0].body == message.body
    assert prepared[0].variant_id == "template:approved"
    ledger_record = json.loads(ledger_path.read_text())
    assert ledger_record["quota_key"] == "uk"
    assert "product_url" not in ledger_record


def test_prepare_template_outreach_batch_allows_no_link_in_body(
    tmp_path: Path,
) -> None:
    message = parse_outreach_template(
        _write_template(tmp_path, "Subject: Missing link\n\nGood morning\n")
    )

    prepared = prepare_template_outreach_batch(
        [_lead("info@example.com")],
        ledger_path=tmp_path / "ledger.jsonl",
        campaign_id="uk-accountants-2026-05-29",
        language="en",
        locale="uk",
        quota_key="uk",
        limit=1,
        message=message,
    )

    assert "product_url" not in prepared[0].as_record()
    assert prepared[0].interview_campaign_id == ""


def test_write_prepared_template_batch_requires_campaign_id_for_interview_link(
    tmp_path: Path,
) -> None:
    message = parse_outreach_template(
        _write_template(
            tmp_path,
            "Subject: Interview invitation\n\n" "Good morning\n\n" "{interview_url}\n",
        )
    )
    prepared = prepare_template_outreach_batch(
        [_lead("info@example.com")],
        ledger_path=tmp_path / "ledger.jsonl",
        campaign_id="uk-accountants-2026-05-29",
        language="en",
        locale="uk",
        quota_key="uk",
        limit=1,
        message=message,
    )

    with pytest.raises(ValueError, match="interview_campaign_id is required"):
        write_prepared_batch_jsonl(tmp_path / "batch.jsonl", prepared)


def test_scrub_raw_emails_deletes_csv_email_only_after_hash_recorded(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    csv_path = tmp_path / "leads.csv"
    prepare_outreach_batch(
        [_lead("info@example.com")],
        ledger_path=ledger_path,
        campaign_id="italy-commercialisti-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=1,
    )
    csv_path.write_text(
        "name,email,city,country,source_url\n"
        "Studio,info@example.com,Roma,Italy,https://example.com\n"
    )

    scrubbed_count = scrub_raw_emails(csv_path, ledger_path=ledger_path)

    assert scrubbed_count == 1
    assert "info@example.com" not in csv_path.read_text()


def test_record_outreach_batch_sent_updates_ledger_and_blocks_reuse(
    tmp_path: Path, monkeypatch
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    batch_path = tmp_path / "batch.jsonl"
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "hosted"))
    prepared = prepare_outreach_batch(
        [_lead("info@example.com")],
        ledger_path=ledger_path,
        campaign_id="italy-commercialisti-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=1,
        created_at=datetime(2026, 5, 29, tzinfo=timezone.utc),
    )
    write_prepared_batch_jsonl(batch_path, prepared)

    sent_count = record_outreach_batch_sent(
        batch_path,
        ledger_path=ledger_path,
        gmail_message_ids={prepared[0].email_hash: "gmail-123"},
        sent_at=datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc),
        gmail_sent_deleted_at=datetime(2026, 5, 29, 10, 1, tzinfo=timezone.utc),
    )
    repeated = prepare_outreach_batch(
        [_lead("info@example.com")],
        ledger_path=ledger_path,
        campaign_id="italy-commercialisti-2026-05-second",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=1,
        created_at=datetime(2026, 5, 29, 10, 2, tzinfo=timezone.utc),
    )

    ledger_record = json.loads(ledger_path.read_text())
    batch_record = json.loads(batch_path.read_text())
    assert sent_count == 1
    assert ledger_record["email_hash"] == prepared[0].email_hash
    assert ledger_record["status"] == "sent"
    assert ledger_record["gmail_message_id"] == "gmail-123"
    assert ledger_record["gmail_sent_deleted_at"] == "2026-05-29T10:01:00+00:00"
    assert batch_record["status"] == "sent"
    assert batch_record["gmail_message_id"] == "gmail-123"
    assert repeated == []


def test_record_outreach_batch_sent_requires_existing_ledger_hash(
    tmp_path: Path, monkeypatch
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    batch_path = tmp_path / "batch.jsonl"
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "hosted"))
    prepared = prepare_outreach_batch(
        [_lead("info@example.com")],
        ledger_path=tmp_path / "other-ledger.jsonl",
        campaign_id="italy-commercialisti-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=1,
        created_at=datetime(2026, 5, 29, tzinfo=timezone.utc),
    )
    write_prepared_batch_jsonl(batch_path, prepared)
    ledger_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="hashes are not recorded"):
        record_outreach_batch_sent(
            batch_path,
            ledger_path=ledger_path,
            gmail_message_ids={prepared[0].email_hash: "gmail-123"},
        )


def test_scrub_raw_emails_refuses_to_delete_unrecorded_csv_email(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    csv_path = tmp_path / "leads.csv"
    ledger_path.write_text("")
    csv_path.write_text(
        "name,email,city,country,source_url\n"
        "Studio,info@example.com,Roma,Italy,https://example.com\n"
    )

    with pytest.raises(ValueError, match="hash is not recorded"):
        scrub_raw_emails(csv_path, ledger_path=ledger_path)

    assert "info@example.com" in csv_path.read_text()


def test_scrub_raw_emails_removes_jsonl_to_field_after_hash_recorded(
    tmp_path: Path, monkeypatch
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    out_path = tmp_path / "batch.jsonl"
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "hosted"))
    prepared = prepare_outreach_batch(
        [_lead("info@example.com")],
        ledger_path=ledger_path,
        campaign_id="italy-commercialisti-2026-05",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        locale="italy",
        language="it",
        limit=1,
    )
    write_prepared_batch_jsonl(out_path, prepared)

    scrubbed_count = scrub_raw_emails(out_path, ledger_path=ledger_path)

    payload = json.loads(out_path.read_text().strip())
    assert scrubbed_count == 1
    assert "to" not in payload
    assert payload["recipient_deleted"] is True


def _write_template(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "approved.txt"
    path.write_text(text, encoding="utf-8")
    return path
