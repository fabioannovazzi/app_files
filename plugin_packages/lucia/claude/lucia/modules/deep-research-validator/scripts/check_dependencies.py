"""Check runtime dependencies for the Deep Research Validator plugin."""

from __future__ import annotations

import importlib.util
import argparse
import re
import sys
from pathlib import Path

__all__ = ["main"]

PACKAGE_IMPORTS: dict[str, str] = {}


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def _import_name(package_name: str) -> str:
    return PACKAGE_IMPORTS.get(package_name.lower(), package_name.replace("-", "_"))


def _required_modules_from_requirements(path: Path) -> list[str]:
    modules: list[str] = []
    if not path.exists():
        return modules
    for line in path.read_text(encoding="utf-8").splitlines():
        package = _requirement_name(line)
        if package:
            modules.append(_import_name(package))
    return modules


def _selected_requirement_files(explicit_files: list[str]) -> list[Path]:
    root = plugin_root()
    if explicit_files:
        files = [root / name for name in explicit_files]
    else:
        files = [root / "requirements.txt"]
    return [path for path in files if path.exists()]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the Deep Research Validator plugin dependencies."
    )
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Specific requirements file under the plugin root. May be passed more than once.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Return 0 when required dependencies are importable."""

    args = _parse_args(argv)
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required.", file=sys.stderr)
        return 1

    requirement_files = _selected_requirement_files(args.requirements)
    if args.requirements and not requirement_files:
        print("MISSING_REQUIREMENTS_FILE: no requested requirements file found")
        return 1
    missing: list[str] = []
    for requirements_file in requirement_files:
        for module_name in _required_modules_from_requirements(requirements_file):
            if importlib.util.find_spec(module_name) is None:
                missing.append(module_name)

    if missing:
        print(
            "Missing required modules: " + ", ".join(sorted(missing)),
            file=sys.stderr,
        )
        print(
            "Install from requirements.txt before running plugin scripts.",
            file=sys.stderr,
        )
        return 1

    print("Deep Research Validator dependency check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
