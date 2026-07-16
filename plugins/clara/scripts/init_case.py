"""Initialize a Clara case folder."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from advisor_case_core import initialize_case

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run case initialization."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--client", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--audience", default="Decision maker")
    parser.add_argument("--language", default="it", choices=["it", "en", "fr", "de"])
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    initialize_case(
        args.case_dir,
        client=args.client,
        project=args.project,
        objective=args.objective,
        audience=args.audience,
        output_language=args.language,
        overwrite=args.overwrite,
    )
    LOGGER.info("Case workspace ready: %s", args.case_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
