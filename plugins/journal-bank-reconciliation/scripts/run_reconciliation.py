"""Run deterministic journal-to-bank reconciliation for Codex review."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from journal_bank_core import add_common_args, configure_logging, run_reconciliation

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run reconciliation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bank", type=Path, help="Bank statement file or folder.")
    parser.add_argument("journal", type=Path, help="Journal/ledger file or folder.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where reconciliation outputs will be written.",
    )
    parser.add_argument("--sample", type=Path, help="Optional sample movements file.")
    parser.add_argument("--recipe", type=Path, help="Optional recipe JSON.")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.0,
        help="Allowed absolute amount difference.",
    )
    parser.add_argument(
        "--date-window-days",
        type=int,
        default=7,
        help="Allowed date difference in calendar days.",
    )
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    result = run_reconciliation(
        args.bank,
        args.journal,
        args.output_dir,
        args.recipe,
        sample_path=args.sample,
        tolerance=args.tolerance,
        date_window_days=args.date_window_days,
        language=args.language,
        document_language=args.document_language,
    )
    LOGGER.info("matched=%s", result.matches.height)
    LOGGER.info("unmatched_bank=%s", result.unmatched_bank.height)
    LOGGER.info("unmatched_journal=%s", result.unmatched_journal.height)
    LOGGER.info("stage_counts=%s", result.audit["stage_counts"])
    LOGGER.info("wrote %s", args.output_dir / "journal_bank_reconciliation.xlsx")
    LOGGER.info("wrote %s", args.output_dir / "reconciliation_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
