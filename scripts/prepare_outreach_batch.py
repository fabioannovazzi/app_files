from __future__ import annotations

"""Prepare a deduplicated outreach batch from a CSV lead list."""

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.outreach import (
    load_leads_csv,
    prepare_outreach_batch,
    write_prepared_batch_jsonl,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run the outreach batch preparation CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument(
        "--interview-campaign-id",
        required=True,
        help="Exact versioned interview brief ID, separate from the outreach batch ID.",
    )
    parser.add_argument(
        "--locale",
        default="",
        help="Optional reporting key, for example italy, geneva, zurich, or usa.",
    )
    parser.add_argument(
        "--quota-key",
        default="",
        help="Daily quota country/market key, for example italy, switzerland, or usa.",
    )
    parser.add_argument(
        "--language",
        required=True,
        help="Message language key, for example it, en, fr, or de.",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--status", default="prepared")
    parser.add_argument(
        "--hash-salt-env",
        default="OUTREACH_HASH_SALT",
        help="Environment variable containing an optional stable hash salt.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    leads = load_leads_csv(args.candidates)
    prepared = prepare_outreach_batch(
        leads,
        ledger_path=args.ledger,
        campaign_id=args.campaign_id,
        interview_campaign_id=args.interview_campaign_id,
        language=args.language,
        limit=args.limit,
        locale=args.locale or None,
        quota_key=args.quota_key or None,
        salt=os.environ.get(args.hash_salt_env, ""),
        status=args.status,
    )
    write_prepared_batch_jsonl(args.out, prepared)
    LOGGER.info("Prepared %s outreach emails in %s", len(prepared), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
