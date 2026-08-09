#!/usr/bin/env python3
"""Check runtime dependencies for Presenza digitale dello studio."""

from __future__ import annotations

import argparse
import importlib.util
import logging
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """Return zero when required Python packages are importable."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        type=Path,
        default=PLUGIN_ROOT / "requirements.txt",
    )
    args = parser.parse_args(argv)
    if not args.requirements.is_file():
        LOGGER.error("MISSING_REQUIREMENTS_FILE: %s", args.requirements)
        return 1
    missing = [
        name for name in ("jsonschema",) if importlib.util.find_spec(name) is None
    ]
    if missing:
        LOGGER.error("Missing requirements: %s", ", ".join(missing))
        return 1
    LOGGER.info("Presenza digitale dello studio dependencies are ready.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
