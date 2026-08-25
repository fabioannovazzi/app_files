#!/usr/bin/env python3
"""Check declared Centrale Rischi Review dependencies."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """Validate the exact published runtime requirements."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        type=Path,
        default=PLUGIN_ROOT / "requirements.txt",
    )
    args = parser.parse_args(argv)
    if not args.requirements.is_file():
        LOGGER.error("Requirements file not found: %s", args.requirements)
        return 1
    if importlib.util.find_spec("openpyxl") is None:
        LOGGER.error("Missing dependency: openpyxl")
        return 1
    for candidate in (
        PLUGIN_ROOT / "vendor" / "modules",
        PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
    ):
        if (candidate / "vera_assurance" / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            break
    try:
        import vera_assurance  # noqa: F401
    except ImportError:
        LOGGER.error("Missing dependency: vera_assurance")
        return 1
    LOGGER.info("OK: Centrale Rischi Review dependencies are available.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
