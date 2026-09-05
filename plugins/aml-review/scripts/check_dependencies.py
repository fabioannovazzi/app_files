"""AML review helpers use the Python standard library only."""

from __future__ import annotations

import argparse
import logging

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Report the absence of third-party runtime requirements."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements", choices=["requirements.txt"], default="requirements.txt"
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    logging.info("AML review: standard library only; no installation required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
