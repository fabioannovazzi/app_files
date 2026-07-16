"""Check dependencies declared by the Registro Imprese e SARI plugin."""

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
    "paddleocr": "paddleocr",
    "paddlepaddle": "paddle",
    "paddlex": "paddlex",
    "pypdf": "pypdf",
}


def _requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def main(argv: list[str] | None = None) -> int:
    """Report missing core or explicitly requested optional dependencies."""

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
        for path in missing_files:
            LOGGER.error("Missing requirements file: %s", path)
        return 1
    if sys.version_info < (3, 10):
        LOGGER.error("Python 3.10 or newer is required")
        return 1

    missing: list[tuple[str, str, str]] = []
    for requirements_file in requirement_files:
        for line in requirements_file.read_text(encoding="utf-8").splitlines():
            package = _requirement_name(line)
            if not package:
                continue
            module = PACKAGE_IMPORTS.get(package, package.replace("-", "_"))
            if importlib.util.find_spec(module) is None:
                missing.append((requirements_file.name, package, module))
    if missing:
        LOGGER.error("Missing dependencies:")
        for source, package, module in missing:
            LOGGER.error("- %s (%s) from %s", package, module, source)
        LOGGER.error("Do not install at runtime; update the environment explicitly.")
        return 1
    LOGGER.info("OK: all selected plugin dependencies are importable")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
