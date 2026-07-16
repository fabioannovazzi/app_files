from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.hosted_interviews.campaigns import AI_ADOPTION_RESEARCH_CAMPAIGN_ID
from modules.outreach.automation import (
    OutreachRegionConfig,
    default_region_configs,
    is_business_day,
    load_holiday_dates,
    prepare_daily_outreach,
    prepare_region_batch,
)


def test_is_business_day_skips_weekends_and_holidays() -> None:
    holiday = datetime(2026, 6, 2).date()

    assert is_business_day(datetime(2026, 6, 1).date(), {holiday}) is True
    assert is_business_day(holiday, {holiday}) is False
    assert is_business_day(datetime(2026, 6, 6).date(), set()) is False


def test_load_holiday_dates_ignores_blank_lines_and_comments(tmp_path: Path) -> None:
    path = tmp_path / "holidays.txt"
    path.write_text("# comment\n\n2026-01-01 # New Year\n", encoding="utf-8")

    assert load_holiday_dates(path) == {datetime(2026, 1, 1).date()}


def test_default_region_configs_include_odcec_organization_track() -> None:
    configs = {
        config.key: config
        for config in default_region_configs(
            data_dir=Path("data/outreach"),
            config_dir=Path("config/outreach"),
        )
    }

    config = configs["italy-organization"]
    assert config.quota_key == "italy-organization"
    assert config.candidates_path == Path("data/outreach/queues/italy-organization.csv")
    assert config.limit == 5
    assert config.interview_campaign_id == AI_ADOPTION_RESEARCH_CAMPAIGN_ID


def test_default_region_configs_use_german_for_swiss_german_track() -> None:
    configs = {
        config.key: config
        for config in default_region_configs(
            data_dir=Path("data/outreach"),
            config_dir=Path("config/outreach"),
        )
    }

    config = configs["swiss-german"]
    assert config.language == "de"
    assert config.template_path == Path(
        "config/outreach/templates/german_ai_research_interview.txt"
    )


def test_prepare_region_batch_skips_non_business_day(tmp_path: Path) -> None:
    config = _region_config(tmp_path)

    result = prepare_region_batch(
        config,
        ledger_path=tmp_path / "ledger.jsonl",
        run_at=datetime(2026, 5, 30, 8, 0, tzinfo=ZoneInfo("Europe/Paris")),
    )

    assert result.status == "skipped"
    assert result.reason == "non-business-day"
    assert result.prepared_count == 0


def test_prepare_region_batch_uses_template_and_quota_key(
    tmp_path: Path, monkeypatch
) -> None:
    config = _region_config(tmp_path)
    ledger_path = tmp_path / "ledger.jsonl"
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "hosted"))

    result = prepare_region_batch(
        config,
        ledger_path=ledger_path,
        run_at=datetime(2026, 6, 1, 8, 0, tzinfo=ZoneInfo("Europe/Paris")),
    )

    assert result.status == "prepared"
    assert result.reason == "prepared-partial"
    assert result.prepared_count == 2
    assert result.shortage_count == 8
    assert result.batch_path is not None
    records = [json.loads(line) for line in result.batch_path.read_text().splitlines()]
    hosted_records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "hosted" / "sessions").glob("*/interview.json")
    ]
    assert [record["quota_key"] for record in records] == ["uk", "uk"]
    assert [record["interview_campaign_id"] for record in records] == [
        AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
    ]
    assert len(hosted_records) == 2
    assert {
        hosted_record["interview_campaign_id"] for hosted_record in hosted_records
    } == {AI_ADOPTION_RESEARCH_CAMPAIGN_ID}
    assert records[0]["subject"] == "Research on AI use in accounting firms"
    assert "short AI adoption interview" in records[0]["body"]
    assert "https://mparanza.com/case-notes/interview/" in records[0]["body"]
    assert records[0]["interview_url"] in records[0]["body"]
    assert records[0]["interview_url"] != records[1]["interview_url"]
    assert "plugin" not in records[0]["body"].casefold()
    assert "beta" not in records[0]["body"].casefold()
    assert not ledger_path.exists()


def test_prepare_daily_outreach_does_not_catch_up_after_weekend(
    tmp_path: Path, monkeypatch
) -> None:
    configs = (_region_config(tmp_path),)
    ledger_path = tmp_path / "ledger.jsonl"
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "hosted"))
    saturday_results = prepare_daily_outreach(
        configs,
        ledger_path=ledger_path,
        run_at=datetime(2026, 5, 30, 8, 0, tzinfo=ZoneInfo("Europe/Paris")),
    )
    monday_results = prepare_daily_outreach(
        configs,
        ledger_path=ledger_path,
        run_at=datetime(2026, 6, 1, 8, 0, tzinfo=ZoneInfo("Europe/Paris")),
    )

    assert saturday_results[0].status == "skipped"
    assert monday_results[0].prepared_count == 2


def _region_config(tmp_path: Path) -> OutreachRegionConfig:
    data_dir = tmp_path / "data" / "outreach"
    queue_dir = data_dir / "queues"
    queue_dir.mkdir(parents=True)
    template_path = data_dir / "english.txt"
    template_path.write_text(
        "Subject: Research on AI use in accounting firms\n\n"
        "Good morning,\n\n"
        "I am collecting short AI adoption interviews.\n\n"
        "{interview_url}\n",
        encoding="utf-8",
    )
    candidates_path = queue_dir / "uk.csv"
    candidates_path.write_text(
        "name,email,city,country,source_url\n"
        "Firm A,info-a@example.com,London,United Kingdom,https://example.com/a\n"
        "Firm B,info-b@example.com,London,United Kingdom,https://example.com/b\n",
        encoding="utf-8",
    )
    return OutreachRegionConfig(
        key="uk",
        campaign_slug="uk-accountants",
        interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        language="en",
        locale="uk",
        quota_key="uk",
        template_path=template_path,
        candidates_path=candidates_path,
        output_slug="uk_accountants",
        timezone_name="Europe/London",
    )
