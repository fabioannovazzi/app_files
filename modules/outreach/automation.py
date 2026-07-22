from __future__ import annotations

"""Business-day outreach automation for approved regional batches."""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.hosted_interviews.campaigns import AI_ADOPTION_RESEARCH_CAMPAIGN_ID
from modules.outreach.batch import (
    DAILY_COUNTRY_LIMIT,
    daily_quota_usage,
    parse_outreach_template,
)
from modules.outreach.queue import prepare_queue_outreach_batch

__all__ = [
    "DEFAULT_AUTOMATION_TIMEZONE",
    "OutreachAutomationResult",
    "OutreachRegionConfig",
    "default_region_configs",
    "is_business_day",
    "load_holiday_dates",
    "prepare_daily_outreach",
    "prepare_region_batch",
]

LOGGER = logging.getLogger(__name__)

DEFAULT_AUTOMATION_TIMEZONE = "Europe/Paris"


@dataclass(frozen=True)
class OutreachRegionConfig:
    """Configuration for one market quota bucket."""

    key: str
    campaign_slug: str
    interview_campaign_id: str
    language: str
    locale: str
    quota_key: str
    template_path: Path
    candidates_path: Path
    output_slug: str
    holiday_path: Path | None = None
    timezone_name: str = DEFAULT_AUTOMATION_TIMEZONE
    limit: int = DAILY_COUNTRY_LIMIT


@dataclass(frozen=True)
class OutreachAutomationResult:
    """Outcome for one region in one daily automation run."""

    region_key: str
    quota_day: date
    status: str
    reason: str
    prepared_count: int
    batch_path: Path | None = None
    duplicate_count: int = 0
    shortage_count: int = 0


def default_region_configs(
    *,
    data_dir: Path = Path("data/outreach"),
    config_dir: Path = Path("config/outreach"),
) -> tuple[OutreachRegionConfig, ...]:
    """Return the approved regional outreach configurations."""

    holiday_dir = config_dir / "holidays"
    template_dir = config_dir / "templates"
    queue_dir = data_dir / "queues"
    return (
        OutreachRegionConfig(
            key="italy",
            campaign_slug="italy-commercialisti",
            interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
            language="it",
            locale="italy",
            quota_key="italy",
            template_path=template_dir / "italian_ai_research_interview.txt",
            candidates_path=queue_dir / "italy.csv",
            output_slug="italy_commercialisti",
            holiday_path=holiday_dir / "italy.txt",
        ),
        OutreachRegionConfig(
            key="italy-organization",
            campaign_slug="italy-odcec-organizations",
            interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
            language="it",
            locale="italy",
            quota_key="italy-organization",
            template_path=template_dir / "italian_odcec_ai_research_interview.txt",
            candidates_path=queue_dir / "italy-organization.csv",
            output_slug="italian_odcec_organizations",
            holiday_path=holiday_dir / "italy.txt",
            limit=5,
        ),
        OutreachRegionConfig(
            key="spain",
            campaign_slug="spain-accountants",
            interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
            language="es",
            locale="spain",
            quota_key="spain",
            template_path=template_dir / "spanish_ai_research_interview.txt",
            candidates_path=queue_dir / "spain.csv",
            output_slug="spain_accountants",
            holiday_path=holiday_dir / "spain.txt",
            timezone_name="Europe/Madrid",
        ),
        OutreachRegionConfig(
            key="swiss-romande",
            campaign_slug="swiss-romande-fiduciaires",
            interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
            language="fr",
            locale="swiss-romande",
            quota_key="swiss-romande",
            template_path=template_dir / "french_ai_research_interview.txt",
            candidates_path=queue_dir / "swiss-romande.csv",
            output_slug="swiss_romande_fiduciaires",
            holiday_path=holiday_dir / "swiss-romande.txt",
        ),
        OutreachRegionConfig(
            key="swiss-german",
            campaign_slug="swiss-german-treuhand",
            interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
            language="de",
            locale="swiss-german",
            quota_key="swiss-german",
            template_path=template_dir / "german_ai_research_interview.txt",
            candidates_path=queue_dir / "swiss-german.csv",
            output_slug="swiss_german_treuhand",
            holiday_path=holiday_dir / "swiss-german.txt",
        ),
        OutreachRegionConfig(
            key="uk",
            campaign_slug="uk-accountants",
            interview_campaign_id=AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
            language="en",
            locale="uk",
            quota_key="uk",
            template_path=template_dir / "english_ai_research_interview.txt",
            candidates_path=queue_dir / "uk.csv",
            output_slug="uk_accountants",
            holiday_path=holiday_dir / "uk.txt",
            timezone_name="Europe/London",
        ),
    )


def load_holiday_dates(path: Path | None) -> set[date]:
    """Load holiday dates from a newline-delimited YYYY-MM-DD file."""

    if path is None or not path.exists():
        return set()

    holiday_dates: set[date] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            try:
                holiday_dates.add(date.fromisoformat(line))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid holiday date in {path} line {line_number}: {line!r}"
                ) from exc
    return holiday_dates


def is_business_day(day: date, holiday_dates: set[date]) -> bool:
    """Return true when a day is Monday-Friday and not a configured holiday."""

    return day.weekday() < 5 and day not in holiday_dates


def prepare_daily_outreach(
    configs: tuple[OutreachRegionConfig, ...],
    *,
    ledger_path: Path,
    run_at: datetime,
    salt: str = "",
) -> list[OutreachAutomationResult]:
    """Prepare approved batches for every configured business-day region."""

    return [
        prepare_region_batch(
            config,
            ledger_path=ledger_path,
            run_at=run_at,
            salt=salt,
        )
        for config in configs
    ]


def prepare_region_batch(
    config: OutreachRegionConfig,
    *,
    ledger_path: Path,
    run_at: datetime,
    salt: str = "",
) -> OutreachAutomationResult:
    """Prepare one region's batch when business-day and input checks pass."""

    quota_day = _local_quota_day(run_at, config.timezone_name)
    holidays = load_holiday_dates(config.holiday_path)
    if not is_business_day(quota_day, holidays):
        return OutreachAutomationResult(
            region_key=config.key,
            quota_day=quota_day,
            status="skipped",
            reason="non-business-day",
            prepared_count=0,
        )

    if not config.template_path.exists():
        return OutreachAutomationResult(
            region_key=config.key,
            quota_day=quota_day,
            status="skipped",
            reason=f"missing-template:{config.template_path}",
            prepared_count=0,
        )
    if not config.candidates_path.exists():
        return OutreachAutomationResult(
            region_key=config.key,
            quota_day=quota_day,
            status="skipped",
            reason=f"missing-queue:{config.candidates_path}",
            prepared_count=0,
        )

    message = parse_outreach_template(config.template_path)
    campaign_id = f"{config.campaign_slug}-{quota_day.isoformat()}"
    batch_path = _batch_path(config, quota_day)
    local_run_at = _local_run_at(run_at, config.timezone_name)
    batch_result = prepare_queue_outreach_batch(
        config.candidates_path,
        batch_path,
        ledger_path=ledger_path,
        campaign_id=campaign_id,
        interview_campaign_id=config.interview_campaign_id,
        language=config.language,
        locale=config.locale,
        quota_key=config.quota_key,
        message=message,
        run_at=local_run_at,
        limit=config.limit,
        salt=salt,
    )
    if batch_result.prepared_count == 0:
        used_slots = daily_quota_usage(
            ledger_path,
            quota_key=config.quota_key,
            quota_day=quota_day,
        )
        reason = (
            "quota-exhausted"
            if used_slots >= config.limit
            else "no-sendable-queued-leads"
        )
        return OutreachAutomationResult(
            region_key=config.key,
            quota_day=quota_day,
            status="skipped",
            reason=reason,
            prepared_count=0,
            batch_path=batch_result.batch_path,
            duplicate_count=batch_result.duplicate_count,
            shortage_count=batch_result.shortage_count,
        )

    LOGGER.info(
        "Prepared %s outreach emails for %s in %s",
        batch_result.prepared_count,
        config.key,
        batch_path,
    )
    return OutreachAutomationResult(
        region_key=config.key,
        quota_day=quota_day,
        status="prepared",
        reason=("prepared-partial" if batch_result.shortage_count else "prepared"),
        prepared_count=batch_result.prepared_count,
        batch_path=batch_path,
        duplicate_count=batch_result.duplicate_count,
        shortage_count=batch_result.shortage_count,
    )


def _local_quota_day(run_at: datetime, timezone_name: str) -> date:
    return _local_run_at(run_at, timezone_name).date()


def _local_run_at(run_at: datetime, timezone_name: str) -> datetime:
    timezone = ZoneInfo(timezone_name)
    if run_at.tzinfo is None:
        return run_at.replace(tzinfo=timezone)
    return run_at.astimezone(timezone)


def _batch_path(config: OutreachRegionConfig, quota_day: date) -> Path:
    return (
        config.candidates_path.parent.parent
        / f"{config.output_slug}_batch_{quota_day.isoformat()}_pending.jsonl"
    )
