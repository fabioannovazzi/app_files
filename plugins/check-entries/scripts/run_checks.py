"""Run deterministic entry-vs-support checks for Codex review."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from check_entries_core import add_common_args, configure_logging, run_entry_checks

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run deterministic entry checks."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path, help="Journal/sample-entry file.")
    parser.add_argument(
        "support",
        type=Path,
        help="FatturaPA ZIP/XML, authorized connector export, or supporting PDF folder.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where check outputs will be written.",
    )
    parser.add_argument("--recipe", type=Path, help="Optional recipe JSON.")
    parser.add_argument(
        "--amount-tolerance",
        type=float,
        default=0.0,
        help="Allowed absolute amount difference.",
    )
    parser.add_argument(
        "--date-window-days",
        type=int,
        default=0,
        help="Allowed date difference in calendar days.",
    )
    parser.add_argument(
        "--connector-name",
        help="Authorized system that produced the local export; no credentials are accepted.",
    )
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    result = run_entry_checks(
        args.journal,
        args.support,
        args.output_dir,
        args.recipe,
        amount_tolerance=args.amount_tolerance,
        date_window_days=args.date_window_days,
        language=args.language,
        document_language=args.document_language,
        connector_name=args.connector_name,
    )
    LOGGER.info("checked_rows=%s", result.frame.height)
    LOGGER.info("status_counts=%s", result.audit["status_counts"])
    LOGGER.info("wrote %s", args.output_dir / "check_results.csv")
    LOGGER.info("wrote %s", args.output_dir / "check_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
