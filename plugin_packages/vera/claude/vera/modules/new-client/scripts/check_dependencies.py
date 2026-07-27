from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from new_client_core import (  # noqa: E402
    ValidationError,
    load_json,
    load_source_registry,
)

__all__ = ["build_parser", "check_dependencies", "main"]

PLUGIN_ROOT = SCRIPT_DIR.parent


def check_dependencies(
    requirement_files: Sequence[Path] | None = None,
) -> dict[str, Any]:
    """Check the standard-library runtime and plugin-owned contract files."""

    issues: list[str] = []
    if sys.version_info < (3, 10):
        issues.append("Python 3.10 or newer is required.")
    selected_requirements = list(
        requirement_files or [PLUGIN_ROOT / "requirements.txt"]
    )
    for requirements_path in selected_requirements:
        resolved = requirements_path.expanduser().resolve()
        try:
            resolved.relative_to(PLUGIN_ROOT.resolve())
        except ValueError:
            issues.append(
                f"Requirements file must be under the plugin root: {requirements_path}"
            )
            continue
        if not resolved.is_file():
            issues.append(f"Missing requirements file: {resolved}")
    schema_path = PLUGIN_ROOT / "schemas" / "new_client_input.schema.json"
    source_registry_path = PLUGIN_ROOT / "references" / "source-registry.json"
    try:
        load_json(schema_path)
    except ValidationError as exc:
        issues.append(str(exc))
    try:
        load_source_registry(source_registry_path)
    except ValidationError as exc:
        issues.append(str(exc))
    return {
        "status": "ready" if not issues else "blocked",
        "python": sys.version.split()[0],
        "dependencies": "python_standard_library_only",
        "requirements": [path.as_posix() for path in selected_requirements],
        "issues": issues,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the repository-standard dependency-check parser."""

    parser = argparse.ArgumentParser(
        description="Check new-client runtime and contract dependencies."
    )
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Requirements file under the plugin root; repeat for multiple files.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print the dependency report as JSON."""

    args = build_parser().parse_args(argv)
    requirement_files = [PLUGIN_ROOT / value for value in args.requirements]
    result = check_dependencies(requirement_files or None)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
