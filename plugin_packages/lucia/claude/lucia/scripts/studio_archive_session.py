"""Run Cowork archive commands with an explicit, task-scoped configuration."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

__all__ = ["main"]
ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """Validate package access before starting the managed runtime."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True, type=UUID)
    parser.add_argument("command", help="diagnose, check, or a Studio Archive command")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    component = ROOT / "modules" / "studio-archive"
    if not component.is_dir() and (ROOT / ".codex-plugin/plugin.json").is_file():
        component = ROOT.parent / "studio-archive"
    required = (
        ROOT / "components.json",
        ROOT / "scripts/managed_python_runtime.py",
        ROOT / "scripts/check_dependencies.py",
        component / "scripts/studio_archive.py",
    )
    # Presence and readability are mechanical gates, not semantic judgments.
    try:
        for path in required:
            with path.open("rb") as handle:
                handle.read(1)
    except OSError as error:
        sys.stderr.write(
            "archive_package_unreadable: the selected interpreter cannot read the "
            f"Vera package ({type(error).__name__}). Select the installed plugin's "
            "actual accessible root; do not create another archive.\n"
        )
        return 2
    if args.command == "diagnose":
        sys.stdout.write(
            json.dumps({"package_readable": True, "runtime_checked": False}) + "\n"
        )
        return 0
    environment = dict(os.environ)
    environment["VERA_STUDIO_ARCHIVE_SESSION_ID"] = str(args.session_id)
    if args.command == "check":
        command = [
            str(ROOT / "scripts/check_dependencies.py"),
            "--module",
            "studio-archive",
        ]
    else:
        command = [
            str(ROOT / "scripts/managed_python_runtime.py"),
            "--module",
            "studio-archive",
            "run",
            "scripts/studio_archive.py",
            args.command,
        ]
    completed = subprocess.run(
        [sys.executable, *command, *args.arguments],
        cwd=ROOT,
        env=environment,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
