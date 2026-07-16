"""Validate an independent Codex mapping review against exact content pins."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from attribute_reporting import ContractError, validate_mapping_review

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Write a deterministic validation receipt without judging semantics."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("validated_mappings", type=Path)
    parser.add_argument("mapping_review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = validate_mapping_review(
            args.tasks,
            args.decisions,
            args.validated_mappings,
            args.mapping_review,
            args.output,
        )
    except ContractError as exc:
        LOGGER.error("Mapping review validation failed: %s", exc)
        return 1
    LOGGER.info("Mapping review status: %s", result["review_state"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
