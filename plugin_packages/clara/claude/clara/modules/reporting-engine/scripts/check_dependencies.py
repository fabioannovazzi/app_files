"""Check Python dependencies declared by the Reporting Engine component."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import re
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)

PACKAGE_IMPORTS = {
    "matplotlib-venn": "matplotlib_venn",
    "opencv-python": "cv2",
    "pillow": "PIL",
    "python-dateutil": "dateutil",
    "python-docx": "docx",
    "scikit-learn": "sklearn",
}


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    package = re.split(r"\s*(?:===|==|~=|!=|>=|<=|>|<|@|;)\s*", cleaned, 1)[0]
    return package.split("[", 1)[0].strip().lower()


def _import_name(package: str) -> str:
    return PACKAGE_IMPORTS.get(package, package.replace("-", "_"))


def main(argv: list[str] | None = None) -> int:
    """Check declared imports without installing anything."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Specific requirements file under the plugin root; repeat as needed.",
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Also check requirements-render.txt.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = _plugin_root()
    files = (
        [root / value for value in args.requirements]
        if args.requirements
        else [root / "requirements.txt"]
    )
    if args.include_optional:
        files.append(root / "requirements-render.txt")
    missing_files = [path for path in files if not path.is_file()]
    if missing_files:
        for path in missing_files:
            LOGGER.error("Missing requirements file: %s", path)
        return 1
    missing: list[tuple[str, str]] = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            package = _requirement_name(line)
            if not package:
                continue
            module = _import_name(package)
            if importlib.util.find_spec(module) is None:
                missing.append((package, module))
    if missing:
        for package, module in missing:
            LOGGER.error("Missing dependency: %s (import %s)", package, module)
        return 1
    LOGGER.info("All selected Reporting Engine dependencies are importable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
