"""Inspect a sales variance CSV/XLSX file and suggest deterministic mappings."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from variance_core import add_common_args, configure_logging, inspect_variance_inputs

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run variance input inspection."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path, help="CSV/XLSX sales file.")
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

    result = inspect_variance_inputs(
        args.input_file,
        args.output_dir,
        args.recipe,
        language=args.language,
    )
    LOGGER.info("input_rows=%s", result.payload["row_count"])
    LOGGER.info("warnings=%s", len(result.payload["warnings"]))
    LOGGER.info("wrote %s", args.output_dir / "inspection.json")
    LOGGER.info("wrote %s", args.output_dir / "suggested_recipe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
