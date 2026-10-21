#!/usr/bin/env python3
"""Check Vera module availability and delegate dependency checks."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from managed_python_runtime import ensure_runtime, run_verified_helper
from verified_execution import (
    prepare_execution_root,
    release_execution_root,
    report_preparation_failure,
)

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
        report_preparation_failure(
            PLUGIN_ROOT,
            args.module,
            ValueError("Missing packaged Vera components"),
            stage="dependency-setup",
            technical_code="runtime.missing-components",
            technical_type="MissingComponents",
        )
        return 1
    if args.module is None:
        LOGGER.info("All %s Vera modules are available.", len(COMPONENTS))
        return 0

    try:
        execution_root = prepare_execution_root(PLUGIN_ROOT, args.module)
    except (OSError, ValueError) as error:
        LOGGER.error("Vera installation verification failed: %s", error)
        report_preparation_failure(PLUGIN_ROOT, args.module, error)
        return 1
    try:
        component_root = (
            execution_root / "modules" / args.module
            if execution_root != PLUGIN_ROOT
            else _component_root(args.module)
        )
        checker = component_root / "scripts" / "check_dependencies.py"
        if not checker.exists():
            LOGGER.error(
                "Dependency checker not found for %s: %s", args.module, checker
            )
            report_preparation_failure(
                PLUGIN_ROOT,
                args.module,
                ValueError("Published dependency checker is missing"),
                stage="dependency-setup",
                technical_code="runtime.missing-checker",
                technical_type="MissingDependencyChecker",
            )
            return 1
        delegated_args = list(remaining)
        for requirement in args.requirements or []:
            delegated_args = ["--requirements", requirement, *delegated_args]
        ready, target, detail = ensure_runtime(
            execution_root,
            args.module,
            requirements=args.requirements,
        )
        if not ready and detail.startswith(
            "Shared runtime update requires the base Python interpreter"
        ):
            # An activated host hook may put the managed venv first on PATH.
            # Re-enter this same verified checker under its recorded base interpreter;
            # keep the shared runtime's prohibition on self-updating intact.
            base = Path(getattr(sys, "_base_executable", sys.executable))
            if base.is_file() and base.absolute() != Path(sys.executable).absolute():
                completed = subprocess.run(
                    [
                        str(base),
                        str(execution_root / "scripts/check_dependencies.py"),
                        *(sys.argv[1:] if argv is None else argv),
                    ],
                    cwd=execution_root,
                    check=False,
                )
                return completed.returncode
        if not ready:
            from operational_incidents import report_failure

            if not os.environ.get("MPARANZA_INCIDENT_RECOVERY_ACTIVE"):
                report_failure(
                    args.module,
                    "dependency-setup",
                    detail,
                    capture_state="complete",
                    technical_diagnostics=[
                        {
                            "component": "vera-runtime",
                            "stage": "dependency-setup",
                            "error_type": "RuntimeSetupError",
                            "error_code": "runtime.setup-failed",
                            "message": detail,
                            "evidence_source": "observed-tool-result",
                        }
                    ],
                )
            LOGGER.error("Vera managed Python runtime setup failed: %s", detail)
            return 1
        # The actual selector resolves this relative path under the selected component,
        # not this top-level Vera checker (covered by a real-process regression).
        runtime_args = ["--module", args.module]
        for requirement in args.requirements or []:
            runtime_args.extend(["--requirements", requirement])
        return run_verified_helper(
            execution_root,
            [*runtime_args, "run", "scripts/check_dependencies.py", *delegated_args],
            args.module,
        )
    finally:
        release_execution_root(execution_root)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
