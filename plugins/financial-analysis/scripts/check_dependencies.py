#!/usr/bin/env python3
"""Check the vendored Vera assurance dependency for Financial Analysis."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _activate_assurance() -> None:
    """Add the installed or source-tree assurance root to the import path."""

    candidates = (
        PLUGIN_ROOT / "vendor" / "modules",
        PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
    )
    for candidate in candidates:
        if (candidate / "vera_financial_analysis" / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    raise RuntimeError("Vera assurance module is unavailable.")


def main(argv: list[str] | None = None) -> int:
    """Validate the workflow's standard-library and vendored dependencies."""

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
    try:
        _activate_assurance()
        import vera_financial_analysis  # noqa: F401
    except (ImportError, RuntimeError) as exc:
        LOGGER.error("Missing dependency: %s", exc)
        return 1
    LOGGER.info("OK: Financial Analysis dependencies are available.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
