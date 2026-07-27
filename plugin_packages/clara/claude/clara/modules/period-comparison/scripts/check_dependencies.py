"""Dependency checker for the period-comparison plugin."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import re
import sys
import warnings
from pathlib import Path

__all__ = ["main"]

REQUIRED_MODULES = ("polars", "plotly", "PIL", "docx", "openpyxl")
PACKAGE_IMPORTS = {
    "pillow": "PIL",
    "python-docx": "docx",
}


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def import_name(package_name: str) -> str:
    return PACKAGE_IMPORTS.get(package_name.lower(), package_name.replace("-", "_"))


def modules_from_requirements(requirement_files: list[Path]) -> list[str]:
    modules: list[str] = []
    for requirements_file in requirement_files:
        for line in requirements_file.read_text(encoding="utf-8").splitlines():
            package = requirement_name(line)
            if package:
                modules.append(import_name(package))
    return modules


def selected_requirement_files(explicit_files: list[str]) -> list[Path]:
    root = plugin_root()
    if explicit_files:
        files = [root / name for name in explicit_files]
    else:
        files = [root / "requirements.txt"]
    return [path for path in files if path.exists()]


def collect_import_warnings(module_name: str) -> list[str]:
    """Import one module and return warning messages raised during import."""

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module(module_name)
    return [f"{warning.category.__name__}: {warning.message}" for warning in caught]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check runtime dependencies for the period-comparison plugin."
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Specific requirements file under the plugin root. May be passed more than once.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Check runtime imports and write a small JSON diagnostic when requested."""

    args = parse_args(argv or sys.argv[1:])
    requirement_files = selected_requirement_files(args.requirements)
    if args.requirements and not requirement_files:
        print("MISSING_REQUIREMENTS_FILE: no requested requirements file found")
        return 1
    required_modules = (
        tuple(modules_from_requirements(requirement_files))
        if args.requirements
        else REQUIRED_MODULES
    )

    missing: list[str] = []
    import_warnings: dict[str, list[str]] = {}
    for module_name in required_modules:
        if importlib.util.find_spec(module_name) is None:
            missing.append(f"{module_name}: module not found")
            continue
        try:
            import_warnings[module_name] = collect_import_warnings(module_name)
        except Exception as exc:
            missing.append(f"{module_name}: {type(exc).__name__}: {exc}")

    payload = {
        "status": "ok" if not missing else "missing_dependencies",
        "required_modules": list(required_modules),
        "missing": missing,
        "warnings": import_warnings,
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
