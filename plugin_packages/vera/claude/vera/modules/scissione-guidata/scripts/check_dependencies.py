"""Check the supported runtime; scissione uses the standard library only."""

from __future__ import annotations

import argparse
import logging
import sys

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Require Vera's managed CPython 3.12 without installing packages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements", choices=["requirements.txt"], default="requirements.txt"
    )
    parser.parse_args(argv)
    if sys.version_info[:2] != (3, 12):
        logging.error("Use Vera's managed Python 3.12 environment")
        return 2
    logging.info("Scissione dependencies available: Python 3.12 standard library")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
