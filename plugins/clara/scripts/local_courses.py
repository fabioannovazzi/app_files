#!/usr/bin/env python3
"""Render the installed product's prepared teaching materials locally."""

from __future__ import annotations

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
from desktop_teaching.onboarding import eligible_workflows


def main(argv: list[str] | None = None) -> int:
    """Use exactly the workflow membership enforced by the teaching runtime."""
    return _main(PLUGIN_ROOT, eligible_workflows(PLUGIN_ROOT), argv)


if __name__ == "__main__":
    raise SystemExit(main())
