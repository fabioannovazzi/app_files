from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.attribute_table_templates import build_attribute_tables_from_package

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "package_dir", type=Path, help="Retailer evidence package directory."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where attribute_tables/ should be written. Defaults to package_dir.",
    )
    parser.add_argument(
        "--table-key",
        action="append",
        default=None,
        help="Specific table template key to build. May be supplied more than once.",
    )
    args = parser.parse_args(argv)
    result = build_attribute_tables_from_package(
        args.package_dir,
        output_dir=args.output_dir,
        table_keys=args.table_key,
    )
    LOGGER.info("Wrote attribute table artifacts to %s", result["manifest_path"])
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
