#!/usr/bin/env python3
"""Calculate and render one reviewed Vera Management Control Pack."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        sys.path.insert(0, str(_vendor_root))
        break

from management_control_core import (  # noqa: E402
    PackContractError,
    build_management_pack,
    load_json,
    load_source_tables,
)
from management_delivery import write_pack_outputs  # noqa: E402
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run exact calculations and write the normal management-pack outputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="management-control-pack",
            input_paths=[*args.input, args.recipe],
            output_dir=args.output_dir,
        )
        tables = load_source_tables(args.input)
        recipe = load_json(args.recipe)
        pack = build_management_pack(tables, recipe)
    except (AssuranceContractError, PackContractError, OSError, ValueError) as exc:
        parser.error(str(exc))
    write_pack_outputs(
        pack, inputs=args.input, recipe_path=args.recipe, output_dir=args.output_dir
    )
    LOGGER.info("Wrote Management Control Pack with status %s.", pack["status"])
    return 0 if pack["status"] != "blocked" else 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
