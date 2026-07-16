"""Render a Codex-authored attribute report model as local HTML."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from attribute_reporting import ContractError, render_report

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Resolve evidence bindings and render the report draft."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        manifest = render_report(args.output_dir)
    except ContractError as exc:
        LOGGER.error("Render failed: %s", exc)
        return 1
    LOGGER.info(
        "Rendered %s for independent semantic review",
        manifest["draft_html"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
