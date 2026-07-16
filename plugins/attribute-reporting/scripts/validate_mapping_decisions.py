"""Validate Codex mapping decisions against a pinned taxonomy snapshot."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from attribute_reporting import ContractError, validate_mapping_decisions

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Validate and normalize mapping decisions."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = validate_mapping_decisions(args.tasks, args.decisions, args.output)
    except ContractError as exc:
        LOGGER.error("Mapping validation failed: %s", exc)
        return 1
    LOGGER.info("Validated %s Codex mapping decisions", result["mapping_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
