#!/usr/bin/env python3
"""Check the archive-organization runtime contract."""

from __future__ import annotations

import argparse
import importlib.util
import re
from pathlib import Path

__all__ = ["main"]

PACKAGE_IMPORTS = {
    "google-api-core": "google.api_core",
    "google-api-python-client": "googleapiclient",
    "google-auth": "google.auth",
    "google-auth-oauthlib": "google_auth_oauthlib",
    "protobuf": "google.protobuf",
}


def _requirement_name(line: str) -> str:
    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def main() -> int:
    """Confirm required package files and Google Drive dependencies are present."""

    parser = argparse.ArgumentParser(
        description="Check archive-organization package files and requirements."
    )
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Requirements file under the plugin root; may be repeated.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    required = (
        root / "requirements.txt",
        root / "references" / "default-archive-policy.json",
        root / "scripts" / "archive_organization.py",
    )
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing required plugin files: {', '.join(missing)}")
    missing_dependencies: list[tuple[str, str]] = []
    for relative in args.requirements or ["requirements.txt"]:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise SystemExit("Requirements paths must stay inside the plugin root.")
        if not (root / candidate).is_file():
            raise SystemExit(f"Missing requirements file: {relative}")
        for line in (root / candidate).read_text(encoding="utf-8").splitlines():
            package = _requirement_name(line)
            if not package:
                continue
            module = PACKAGE_IMPORTS.get(package, package.replace("-", "_"))
            if importlib.util.find_spec(module) is None:
                missing_dependencies.append((package, module))
    if missing_dependencies:
        details = ", ".join(
            f"{package} (import {module})"
            for package, module in sorted(set(missing_dependencies))
        )
        raise SystemExit(f"Missing dependencies: {details}")
    print("OK: archive-organization dependencies are available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
