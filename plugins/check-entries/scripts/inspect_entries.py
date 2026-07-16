"""Inspect journal entries and support PDFs for deterministic Codex review."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from check_entries_core import add_common_args, configure_logging, inspect_entries

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run check-entries inspection."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path, help="Journal/sample-entry file.")
    parser.add_argument("pdfs", type=Path, help="Supporting PDF file or folder.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where inspection.json and suggested_recipe.json will be written.",
    )
    parser.add_argument("--recipe", type=Path, help="Optional existing recipe JSON.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    result = inspect_entries(
        args.journal,
        args.pdfs,
        args.output_dir,
        args.recipe,
        language=args.language,
        document_language=args.document_language,
    )
    LOGGER.info("journal_rows=%s", result.journal["row_count"])
    LOGGER.info("support_pdfs=%s", len(result.pdfs))
    LOGGER.info("wrote %s", args.output_dir / "inspection.json")
    LOGGER.info("wrote %s", args.output_dir / "suggested_recipe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
