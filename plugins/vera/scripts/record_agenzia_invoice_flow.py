#!/usr/bin/env python3
"""Run the embedded Studio Archive Agenzia recorder from Vera's runtime."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

__all__ = ["main"]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _implementation_path() -> Path:
    """Return the packaged or repository-source recorder implementation."""

    packaged = (
        PLUGIN_ROOT
        / "modules"
        / "studio-archive"
        / "scripts"
        / "record_agenzia_invoice_flow.py"
    )
    if packaged.is_file():
        return packaged
    return (
        PLUGIN_ROOT.parent
        / "studio-archive"
        / "scripts"
        / "record_agenzia_invoice_flow.py"
    )


def _load_implementation() -> ModuleType:
    """Load the recorder only after Vera has activated its managed runtime."""

    path = _implementation_path()
    if not path.is_file():
        raise RuntimeError(f"Agenzia recorder implementation not found: {path}")
    spec = importlib.util.spec_from_file_location("vera_agenzia_flow_recorder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Agenzia recorder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    """Delegate to the embedded recorder's public CLI."""

    implementation = _load_implementation()
    return int(implementation.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
