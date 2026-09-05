#!/usr/bin/env python3
"""Check Vera module availability and delegate dependency checks."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

from managed_python_runtime import ensure_runtime, runtime_environment, runtime_python

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _registered_components() -> tuple[str, ...]:
    """Read the canonical component registry used to build Vera packages."""

    payload = json.loads((PLUGIN_ROOT / "components.json").read_text(encoding="utf-8"))
    components = payload.get("plugins")
    if (
        not isinstance(components, list)
        or not components
        or any(not isinstance(name, str) or not name for name in components)
    ):
        raise RuntimeError("Vera components.json has no valid plugins registry.")
    return tuple(components)


COMPONENTS = _registered_components()


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
    parser.add_argument("--requirements", action="append")
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
    for requirement in args.requirements or []:
        delegated_args = ["--requirements", requirement, *delegated_args]
    ready, target, detail = ensure_runtime(
        PLUGIN_ROOT,
        args.module,
        requirements=args.requirements,
    )
    if not ready:
        LOGGER.error("Vera managed Python runtime setup failed: %s", detail)
        return 1
    completed = subprocess.run(
        [str(runtime_python(target)), str(checker), *delegated_args],
        cwd=component_root,
        env=runtime_environment(target),
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
