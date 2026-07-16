"""Check Python dependencies declared by this Codex plugin."""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

PACKAGE_IMPORTS: dict[str, str] = {}


def plugin_root() -> Path:
    """Return the plugin root directory."""

    return Path(__file__).resolve().parents[1]


def requirement_name(line: str) -> str:
    """Return the package name from one requirements.txt line."""

    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def import_name(package_name: str) -> str:
    """Return the import module name for a package name."""

    return PACKAGE_IMPORTS.get(package_name.lower(), package_name.replace("-", "_"))


def selected_requirement_files(explicit_files: list[str]) -> list[Path]:
    """Return requirement files to check."""

    root = plugin_root()
    files = (
        [root / name for name in explicit_files]
        if explicit_files
        else [root / "requirements.txt"]
    )
    return [path for path in files if path.exists()]


def main() -> int:
    """Run dependency checks."""

    parser = argparse.ArgumentParser(
        description="Check this Codex plugin's Python dependencies."
    )
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Specific requirements file under the plugin root. May be passed more than once.",
    )
    args = parser.parse_args()

    files = selected_requirement_files(args.requirements)
    if not files:
        print(
            "MISSING_REQUIREMENTS_FILE: no requirements file found in this plugin package"
        )
        return 1

    if sys.version_info < (3, 10):
        print("UNSUPPORTED_PYTHON: Python 3.10 or newer is required")
        return 1

    missing: list[tuple[str, str, str]] = []
    for requirements_file in files:
        for line in requirements_file.read_text(encoding="utf-8").splitlines():
            package = requirement_name(line)
            if not package:
                continue
            module_name = import_name(package)
            if importlib.util.find_spec(module_name) is None:
                missing.append((requirements_file.name, package, module_name))

    if missing:
        print("MISSING_DEPENDENCIES")
        for source_file, package, module_name in missing:
            print(f"- {package} ({module_name}) from {source_file}")
        install_files = " ".join(f"-r {path.name}" for path in files)
        print(
            f"Suggested install from plugin directory: python -m pip install {install_files}"
        )
        return 1

    print("OK: all selected plugin dependencies are importable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
