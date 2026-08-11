#!/usr/bin/env python3
"""Clara entrypoint for the shared managed Python runtime."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

__all__ = ["main"]


def _implementation_path() -> Path:
    return Path(__file__).with_name("_managed_python_runtime.py")


def _load_implementation():
    path = _implementation_path()
    spec = importlib.util.spec_from_file_location("clara_managed_python_runtime", path)
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
    """Run Clara's managed runtime CLI."""

    return _IMPLEMENTATION.main(Path(__file__).resolve().parents[1], argv)


if __name__ == "__main__":
    raise SystemExit(main())
