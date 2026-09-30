"""Check declared ESG schema validation dependency without runtime installation."""

from __future__ import annotations

import argparse
import importlib.metadata
import logging

__all__ = ["main"]


def main() -> int:
    """Check the component's one declared dependency set in the managed runtime."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements", choices=["requirements.txt"], default="requirements.txt"
    )
    parser.parse_args()
    version = importlib.metadata.version("jsonschema")
    parts = tuple(int(part) for part in version.split(".")[:2])
    if not (4, 23) <= parts < (5, 0):
        raise SystemExit("Use Vera's managed environment with jsonschema>=4.23,<5")
    logging.info("ESG schema validation available: %s", version)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
