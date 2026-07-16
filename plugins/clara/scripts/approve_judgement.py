"""Mark one judgement entry for client-pack inclusion or exclusion."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from advisor_case_core import JUDGEMENT_STATUSES, set_judgement_status

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run judgement status update."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("entry_id")
    parser.add_argument("--status", required=True, choices=sorted(JUDGEMENT_STATUSES))
    parser.add_argument(
        "--reviewer",
        "--recorded-by",
        dest="reviewer",
        default="",
        help="Name recorded in the audit log; for solo work, use the advisor name.",
    )
    parser.add_argument("--review-note", default="")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    entry = set_judgement_status(
        args.case_dir,
        args.entry_id,
        status=args.status,
        reviewer=args.reviewer,
        review_note=args.review_note,
    )
    LOGGER.info("Judgement %s recorded as %s.", entry["id"], entry["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
