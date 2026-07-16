"""Inspect journal files and write deterministic parser diagnostics for Codex."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from journal_sampling_core import add_common_args, configure_logging, inspect_path

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run journal inspection."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Journal file or folder to inspect.")
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

    result = inspect_path(
        args.input,
        args.output_dir,
        args.recipe,
        language=args.language,
        document_language=args.document_language,
    )
    LOGGER.info(
        "inspected_files=%s total_rows=%s", len(result.files), result.total_rows
    )
    LOGGER.info("wrote %s", args.output_dir / "inspection.json")
    LOGGER.info("wrote %s", args.output_dir / "suggested_recipe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
