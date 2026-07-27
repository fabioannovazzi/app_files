"""Import a Clara update package into this local workspace."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from advisor_case_core import import_case_update

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run deterministic append-only case-update import."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = import_case_update(args.case_dir, args.package)
    LOGGER.info("Imported exchange: %s", result.exchange_id)
    LOGGER.info(
        "Added %s material(s), %s judgement entrie(s), %s open question(s); "
        "skipped %s duplicate(s); logged %s conflict(s).",
        result.imported_material_count,
        result.imported_judgement_count,
        result.imported_open_question_count,
        result.skipped_count,
        result.conflict_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
