"""Check Python dependencies declared by Apertura pratica."""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path


def _requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Requirements file under the plugin root; repeat when needed.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = (
        [root / item for item in args.requirements]
        if args.requirements
        else [root / "requirements.txt"]
    )
    if not files or any(not path.is_file() for path in files):
        sys.stdout.write("MISSING_REQUIREMENTS_FILE\n")
        return 1
    missing: list[str] = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            package = _requirement_name(line)
            if package and importlib.util.find_spec(package.replace("-", "_")) is None:
                missing.append(package)
    if missing:
        sys.stdout.write(
            "MISSING_DEPENDENCIES\n" + "\n".join(sorted(set(missing))) + "\n"
        )
        return 1
    sys.stdout.write("OK: all selected plugin dependencies are importable\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
