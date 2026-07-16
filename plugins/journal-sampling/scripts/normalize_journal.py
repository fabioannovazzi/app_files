"""Normalize journal files to deterministic canonical rows for Codex review."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from journal_sampling_core import add_common_args, configure_logging, normalize_path

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run journal normalization."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Journal file or folder to normalize.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where normalized_journal.csv and diagnostics will be written.",
    )
    parser.add_argument("--recipe", type=Path, help="Optional recipe JSON.")
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    result = normalize_path(
        args.input,
        args.output_dir,
        args.recipe,
        language=args.language,
        document_language=args.document_language,
    )
    LOGGER.info("normalized_rows=%s", result.frame.height)
    LOGGER.info("wrote %s", args.output_dir / "normalized_journal.csv")
    LOGGER.info("wrote %s", args.output_dir / "normalization_diagnostics.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
