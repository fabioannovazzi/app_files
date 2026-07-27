"""Export a Clara update package for another local workspace."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from advisor_case_core import export_case_update

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run deterministic case-update export."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--exporter", default="")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = export_case_update(
        args.case_dir,
        package_path=args.out,
        exporter=args.exporter,
    )
    LOGGER.info("Exported case update: %s", result.package_path)
    LOGGER.info(
        "Included %s material(s), %s judgement entrie(s), %s open question(s), %s file(s).",
        result.material_count,
        result.judgement_count,
        result.open_question_count,
        result.included_file_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
