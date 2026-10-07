#!/usr/bin/env python3
"""Vera entrypoint for the shared managed Python runtime."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import runpy
import sys
from pathlib import Path

__all__ = ["main"]

prepare_execution_root = runpy.run_path(
    str(Path(__file__).with_name("verified_execution.py"))
)["prepare_execution_root"]


def _implementation_path() -> Path:
    return Path(__file__).with_name("_managed_python_runtime.py")


def _load_implementation():
    path = _implementation_path()
    spec = importlib.util.spec_from_file_location("vera_managed_python_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load managed Python runtime: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_IMPLEMENTATION = _load_implementation()
activate_runtime = _IMPLEMENTATION.activate_runtime
dependency_target = _IMPLEMENTATION.dependency_target
ensure_runtime = _IMPLEMENTATION.ensure_runtime
plugin_data_dir = _IMPLEMENTATION.plugin_data_dir
requirements_fingerprint = _IMPLEMENTATION.requirements_fingerprint
runtime_environment = _IMPLEMENTATION.runtime_environment
runtime_key = _IMPLEMENTATION.runtime_key
runtime_python = _IMPLEMENTATION.runtime_python
select_runtime = _IMPLEMENTATION.select_runtime


def main(argv: list[str] | None = None) -> int:
    """Run Vera's managed runtime CLI."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    # Only runtime options before its subcommand select the component. A helper
    # may itself have an unrelated --module option in its remaining arguments.
    prefix = arguments
    for index, argument in enumerate(arguments):
        if argument in {"run", "install", "status"}:
            prefix = arguments[:index]
            break
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--module")
    parser.add_argument("--requirements", action="append")
    selection, _ = parser.parse_known_args(prefix)
    root = Path(__file__).absolute().parents[1]
    try:
        root = prepare_execution_root(root, selection.module)
    except (OSError, ValueError) as error:
        logging.error("Vera installation verification failed: %s", error)
        return 1
    return _IMPLEMENTATION.main(root, arguments)


if __name__ == "__main__":
    raise SystemExit(main())
