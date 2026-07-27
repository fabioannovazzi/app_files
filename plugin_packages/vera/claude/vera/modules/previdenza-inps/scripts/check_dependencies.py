#!/usr/bin/env python3
"""Check Python dependencies declared by the Previdenza INPS plugin."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import re
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
    "pypdf": "pypdf",
    "pymupdf": "fitz",
    "python-docx": "docx",
}


def _requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def main(argv: list[str] | None = None) -> int:
    """Return zero when every declared runtime dependency is importable."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Requirement file relative to the plugin root; repeat when needed.",
    )
    args = parser.parse_args(argv)
    plugin_root = Path(__file__).resolve().parents[1]
    selected = args.requirements or ["requirements.txt"]
    files = [plugin_root / name for name in selected]
    missing_files = [path for path in files if not path.is_file()]
    if missing_files:
        for path in missing_files:
            LOGGER.error("Missing requirements file: %s", path)
        return 1
    if sys.version_info < (3, 10):
        LOGGER.error("Python 3.10 or newer is required.")
        return 1
    missing: list[tuple[str, str]] = []
    for path in files:
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
    LOGGER.info("All Previdenza INPS dependencies are importable.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
