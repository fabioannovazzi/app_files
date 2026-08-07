"""Check the standard-library runtime required by Bandi e agevolazioni."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import re
import sys
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def main(argv: list[str] | None = None) -> int:
    """Return success when the supported Python runtime is available."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Requirements file under the plugin root; repeat for multiple files.",
    )
    args = parser.parse_args(argv)
    plugin_root = Path(__file__).resolve().parents[1]
    selected = args.requirements or ["requirements.txt"]
    requirement_files = [plugin_root / name for name in selected]
    missing_files = [path for path in requirement_files if not path.is_file()]
    if missing_files:
        for name in missing_files:
            LOGGER.error("Missing requirements file: %s", name)
        return 1
    if sys.version_info < (3, 10):
        LOGGER.error("Python 3.10 or newer is required")
        return 1
    missing_packages: list[str] = []
    for requirements_file in requirement_files:
        for line in requirements_file.read_text(encoding="utf-8").splitlines():
            package = _requirement_name(line)
            if package and importlib.util.find_spec(package.replace("-", "_")) is None:
                missing_packages.append(package)
    if missing_packages:
        LOGGER.error("Missing dependencies: %s", ", ".join(sorted(missing_packages)))
        LOGGER.error("Do not install at runtime; update the environment explicitly.")
        return 1
    LOGGER.info("OK: all selected plugin dependencies are importable")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
