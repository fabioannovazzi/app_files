#!/usr/bin/env python3
"""Render the installed product's prepared teaching materials locally."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__ = ["main"]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for candidate in (
    PLUGIN_ROOT / "vendor/modules",
    PLUGIN_ROOT.parent / "_shared/vendor/modules",
):
    if (candidate / "courseware/library.py").is_file():
        sys.path.insert(0, str(candidate))
        break
else:
    raise RuntimeError("The installed course library is missing; reinstall this plugin")

from courseware.library import main as _main
from local_onboarding import eligible_workflows


def main(argv: list[str] | None = None) -> int:
    """Use exactly the workflow membership enforced by the teaching runtime."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if (
        arguments
        and arguments[0] in {"render", "results"}
        and os.environ.get("MPARANZA_MANAGED_RUNTIME_VERIFY") != "1"
    ):
        # Listing/setup stay stdlib-only. Rendering uses the normal verified
        # launcher, which provisions declared dependencies and preserves host
        # permission failures instead of falling back to the system Python.
        return subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(PLUGIN_ROOT / "scripts/managed_python_runtime.py"),
                "run",
                "scripts/local_courses.py",
                *arguments,
            ],
            cwd=PLUGIN_ROOT,
            check=False,
        ).returncode
    return _main(PLUGIN_ROOT, eligible_workflows(), arguments)


if __name__ == "__main__":
    raise SystemExit(main())
