#!/usr/bin/env python3
"""Check declared Bilancio XBRL Italia runtime dependencies."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import re
import sys
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
REQUIRED = {
    "arelle-release": "arelle",
    "defusedxml": "defusedxml",
    "lxml": "lxml",
    "openpyxl": "openpyxl",
}


def _requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def _required_imports(requirement_files: list[Path]) -> dict[str, str]:
    required: dict[str, str] = {}
    for requirement_file in requirement_files:
        if not requirement_file.is_file() or requirement_file.is_symlink():
            raise ValueError(
                f"Requirements file is not a regular file: {requirement_file}"
            )
        for line in requirement_file.read_text(encoding="utf-8").splitlines():
            package = _requirement_name(line)
            if package:
                required[package] = REQUIRED.get(package, package.replace("-", "_"))
    return required


def main(argv: list[str] | None = None) -> int:
    """Return zero when the pinned runtime is available."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Requirements file relative to the plugin root; may be repeated.",
    )
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        LOGGER.error("Python 3.11 or newer is required")
        return 1
    plugin_root = Path(__file__).resolve().parents[1]
    requirement_files = (
        [plugin_root / value for value in args.requirements]
        if args.requirements
        else [plugin_root / "requirements.txt"]
    )
    try:
        required = _required_imports(requirement_files)
    except (OSError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
    missing = [
        package
        for package, module in required.items()
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        LOGGER.error("Missing declared dependencies: %s", ", ".join(missing))
        return 1
    LOGGER.info("All Bilancio XBRL Italia dependencies are importable.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
