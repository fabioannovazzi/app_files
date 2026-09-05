#!/usr/bin/env python3
"""Run the shared Business Planning workflow with Clara as visible owner."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        sys.path.insert(0, str(_vendor_root))
        break
from planning_cli import run  # noqa: E402

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Keep Clara's case workspace boundary and shared authoritative compiler."""
    return run("Clara", argv)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
