"""Inspect bank and journal inputs for deterministic Codex reconciliation."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from journal_bank_core import add_common_args, configure_logging, inspect_inputs

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run input inspection."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bank", type=Path, help="Bank statement file or folder.")
    parser.add_argument("journal", type=Path, help="Journal/ledger file or folder.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where inspection.json and suggested_recipe.json will be written.",
    )
    parser.add_argument("--sample", type=Path, help="Optional sample movements file.")
    parser.add_argument("--recipe", type=Path, help="Optional existing recipe JSON.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    result = inspect_inputs(
        args.bank,
        args.journal,
        args.output_dir,
        args.recipe,
        sample_path=args.sample,
        language=args.language,
        document_language=args.document_language,
    )
    LOGGER.info("bank_rows=%s", result.bank["row_count"])
    LOGGER.info("journal_rows=%s", result.journal["row_count"])
    LOGGER.info("sample_movements=%s", result.sample["movement_count"])
    LOGGER.info("wrote %s", args.output_dir / "inspection.json")
    LOGGER.info("wrote %s", args.output_dir / "suggested_recipe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
