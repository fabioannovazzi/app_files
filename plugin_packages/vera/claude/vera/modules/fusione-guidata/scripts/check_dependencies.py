"""Check the standard-library runtime used by the merger case foundation."""

from __future__ import annotations

import logging
import sqlite3
import sys

__all__ = ["main"]


def main() -> int:
    if sys.version_info < (3, 12):
        logging.error("Fusione guidata uses Vera's managed Python 3.12 or newer.")
        return 1
    with sqlite3.connect(":memory:") as db:
        db.execute("SELECT 1").fetchone()
    logging.info("Fusione: Python and SQLite are available; no additional packages.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
