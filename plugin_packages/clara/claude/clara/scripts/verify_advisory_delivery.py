"""Verify a reviewed Markdown, Word or HTML deliverable against its current case."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from advisory_delivery import AdvisoryDeliveryError, verify_advisory_delivery

__all__ = ["main"]
LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Report shared readiness without modifying reviewed inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("validation_audit", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        receipt = verify_advisory_delivery(
            args.case_dir, args.artifact, args.validation_audit
        )
    except (AdvisoryDeliveryError, OSError, ValueError) as exc:
        LOGGER.error("Delivery verification failed: %s", exc)
        return 2
    LOGGER.info(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
