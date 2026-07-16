"""Run deterministic journal sampling from canonical normalized rows."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from journal_sampling_core import (
    add_common_args,
    comma_list,
    configure_logging,
    run_sample,
)

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run sampling."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "normalized_csv", type=Path, help="normalized_journal.csv path."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where journal_sample.* and sampling_audit.json will be written.",
    )
    parser.add_argument(
        "--method",
        default="random",
        choices=["random", "systematic", "stratified", "mus"],
        help="Deterministic sampling method.",
    )
    parser.add_argument("--size", type=int, default=25, help="Requested sample size.")
    parser.add_argument(
        "--group-column",
        default="account",
        help="Group column for stratified sampling.",
    )
    parser.add_argument(
        "--include-accounts", help="Comma-separated account allow-list."
    )
    parser.add_argument(
        "--exclude-accounts", help="Comma-separated account block-list."
    )
    parser.add_argument("--date-start", help="Inclusive ISO date lower bound.")
    parser.add_argument("--date-end", help="Inclusive ISO date upper bound.")
    parser.add_argument("--min-abs", type=float, help="Minimum absolute amount.")
    parser.add_argument("--keyword", help="Case-insensitive line-description filter.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    result = run_sample(
        args.normalized_csv,
        args.output_dir,
        method=args.method,
        size=args.size,
        group_column=args.group_column,
        include_accounts=comma_list(args.include_accounts),
        exclude_accounts=comma_list(args.exclude_accounts),
        date_start=args.date_start,
        date_end=args.date_end,
        min_abs=args.min_abs,
        keyword=args.keyword,
        language=args.language,
    )
    LOGGER.info("sample_rows=%s", result.frame.height)
    LOGGER.info("wrote %s", args.output_dir / "journal_sample.csv")
    LOGGER.info("wrote %s", args.output_dir / "sampling_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
