#!/usr/bin/env python3
"""Check Vera module availability and delegate dependency checks."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = (
    "audit-reconciliation",
    "client-intake",
    "client-onboarding",
    "journal-sampling",
    "check-entries",
    "journal-bank-reconciliation",
    "report-builder",
    "concordato-plan-review",
    "prompt-optimizer",
    "deep-research-validator",
    "previdenza-inps",
    "registro-imprese-sari",
)


def _component_root(name: str) -> Path:
    """Return the packaged or repo-source root for one component."""

    packaged = PLUGIN_ROOT / "modules" / name
    if packaged.is_dir():
        return packaged
    return PLUGIN_ROOT.parent / name


def main(argv: list[str] | None = None) -> int:
    """Validate all components or run one component dependency checker."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", choices=COMPONENTS)
    parser.add_argument("--requirements", type=Path)
    args, remaining = parser.parse_known_args(argv)

    missing = [name for name in COMPONENTS if not _component_root(name).is_dir()]
    if missing:
        LOGGER.error("Missing Vera modules: %s", ", ".join(missing))
        return 1
    if args.module is None:
        LOGGER.info("All %s Vera modules are available.", len(COMPONENTS))
        return 0

    component_root = _component_root(args.module)
    checker = component_root / "scripts" / "check_dependencies.py"
    if not checker.exists():
        LOGGER.error("Dependency checker not found for %s: %s", args.module, checker)
        return 1
    delegated_args = list(remaining)
    if args.requirements is not None:
        delegated_args = ["--requirements", str(args.requirements), *delegated_args]
    completed = subprocess.run(
        [sys.executable, str(checker), *delegated_args],
        cwd=component_root,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
