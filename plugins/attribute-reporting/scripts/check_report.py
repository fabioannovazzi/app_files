"""Finalize an attribute report with a direct correctness verdict."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from attribute_reporting import ContractError, finalize_report

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run mechanical and semantic-review contract checks."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = finalize_report(args.output_dir)
    except ContractError as exc:
        LOGGER.error("Correctness check failed to run: %s", exc)
        return 1
    LOGGER.info("Correctness verdict: %s", result["label"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
