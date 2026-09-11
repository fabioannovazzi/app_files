#!/usr/bin/env python3
"""Inventory connectorless management-control exports without assigning roles."""

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
    build_inspection,
    load_source_tables,
    write_json,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Write bounded inspection, private control, and recipe skeleton."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="management-control-pack",
            input_paths=args.input,
            output_dir=args.output_dir,
        )
        tables = load_source_tables(args.input)
        inspection, control, recipe = build_inspection(tables)
    except (AssuranceContractError, PackContractError, OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "inspection.json", inspection)
    write_json(args.output_dir / "inspection_control.json", control)
    write_json(args.output_dir / "suggested_recipe.json", recipe)
    LOGGER.info(
        "Inspected %s tables; semantic source roles remain unassigned.", len(tables)
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
