"""Check declared report dependencies without installing packages at runtime."""

from __future__ import annotations

import importlib.metadata
import logging

__all__ = ["main"]


def main() -> int:
    for package in ("jsonschema", "openpyxl", "python-docx", "reportlab"):
        logging.info("%s %s", package, importlib.metadata.version(package))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
