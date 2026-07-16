from __future__ import annotations

"""Prepare weekday outreach batches for all configured regions."""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.outreach.automation import (
    DEFAULT_AUTOMATION_TIMEZONE,
    default_region_configs,
    prepare_daily_outreach,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run the business-day outreach automation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=Path("data/outreach"), type=Path)
    parser.add_argument("--config-dir", default=Path("config/outreach"), type=Path)
    parser.add_argument(
        "--ledger",
        default=Path("data/outreach/outreach_ledger.jsonl"),
        type=Path,
    )
    parser.add_argument(
        "--run-at",
        default="",
        help="Optional ISO datetime for tests or backfills. Defaults to now.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_AUTOMATION_TIMEZONE,
        help="Timezone used when --run-at is omitted.",
    )
    parser.add_argument(
        "--hash-salt-env",
        default="OUTREACH_HASH_SALT",
        help="Environment variable containing the stable hash salt used in prep.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    run_at = _parse_run_at(args.run_at, args.timezone)
    configs = default_region_configs(data_dir=args.data_dir, config_dir=args.config_dir)
    results = prepare_daily_outreach(
        configs,
        ledger_path=args.ledger,
        run_at=run_at,
        salt=os.environ.get(args.hash_salt_env, ""),
    )
    for result in results:
        LOGGER.info(
            "region=%s day=%s status=%s count=%s duplicates=%s shortage=%s "
            "reason=%s batch=%s",
            result.region_key,
            result.quota_day.isoformat(),
            result.status,
            result.prepared_count,
            result.duplicate_count,
            result.shortage_count,
            result.reason,
            result.batch_path or "",
        )
    return 0


def _parse_run_at(value: str, timezone_name: str) -> datetime:
    if not value:
        return datetime.now(ZoneInfo(timezone_name))
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
