"""Prepare exact content pins for an independent Codex mapping review."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from attribute_reporting import ContractError, create_mapping_review_template

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Write the review scaffold that a different Codex agent completes."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("validated_mappings", type=Path)
    parser.add_argument("--reviewer-agent-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = create_mapping_review_template(
            args.tasks,
            args.decisions,
            args.validated_mappings,
            args.output,
            reviewer_agent_id=args.reviewer_agent_id,
        )
    except ContractError as exc:
        LOGGER.error("Mapping review preparation failed: %s", exc)
        return 1
    LOGGER.info("Prepared mapping review for %s tasks", len(result["task_reviews"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
