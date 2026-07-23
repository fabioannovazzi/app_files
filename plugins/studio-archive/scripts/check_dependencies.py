#!/usr/bin/env python3
"""Check Studio Archive core or optional OCR dependencies."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import re
import sqlite3
import sys
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PACKAGE_IMPORTS = {
    "huggingface-hub": "huggingface_hub",
    "numpy": "numpy",
    "openpyxl": "openpyxl",
    "paddleocr": "paddleocr",
    "paddlepaddle": "paddle",
    "paddlex": "paddlex",
    "pillow": "PIL",
    "pymupdf": "fitz",
    "pypdf": "pypdf",
    "python-docx": "docx",
}


def _requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def _fts5_available() -> bool:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE sample USING fts5(text)")
        connection.execute(
            "INSERT INTO sample(sample, rank) VALUES('secure-delete', 1)"
        )
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()
    return True


def main(argv: list[str] | None = None) -> int:
    """Return zero when selected dependencies and SQLite FTS5 are available."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Requirement file relative to the component root; repeat as needed.",
    )
    args = parser.parse_args(argv)
    component_root = Path(__file__).resolve().parents[1]
    selected = args.requirements or ["requirements.txt"]
    missing_files = [
        component_root / name
        for name in selected
        if not (component_root / name).is_file()
    ]
    if missing_files:
        for path in missing_files:
            LOGGER.error("Missing requirements file: %s", path)
        return 1
    if sys.version_info < (3, 11):
        LOGGER.error("Python 3.11 or newer is required.")
        return 1
    if not _fts5_available():
        LOGGER.error(
            "The active Python SQLite runtime does not provide FTS5 secure deletion."
        )
        return 1
    missing: list[tuple[str, str]] = []
    for requirement_name in selected:
        path = component_root / requirement_name
        for line in path.read_text(encoding="utf-8").splitlines():
            package = _requirement_name(line)
            if not package:
                continue
            module_name = PACKAGE_IMPORTS.get(package, package.replace("-", "_"))
            if importlib.util.find_spec(module_name) is None:
                missing.append((package, module_name))
    if missing:
        for package, module_name in missing:
            LOGGER.error("Missing dependency %s (import %s).", package, module_name)
        return 1
    LOGGER.info("Studio Archive dependencies and SQLite FTS5 are available.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
