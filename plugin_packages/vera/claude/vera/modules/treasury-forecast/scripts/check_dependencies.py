"""Check the treasury workbook dependency without installing packages at runtime."""

from __future__ import annotations

import argparse
import importlib.metadata
import logging

__all__ = ["main"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements", choices=["requirements.txt"], default="requirements.txt"
    )
    parser.parse_args()
    version = importlib.metadata.version("openpyxl")
    parts = tuple(int(value) for value in version.split(".")[:2])
    if not (3, 1) <= parts < (4, 0):
        raise SystemExit("Use Vera's declared shared environment with openpyxl>=3.1,<4")
    logging.info("Treasury dependencies available: openpyxl %s", version)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
