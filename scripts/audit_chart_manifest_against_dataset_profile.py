"""Repository wrapper for packaged mechanical compatibility checks."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

__all__ = [
    "audit_manifest_against_dataset_profile",
    "check_capability_compatibility",
    "check_profile_compatibility",
    "main",
]

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGED_CHECKER = (
    REPO_ROOT
    / "plugins"
    / "clara"
    / "modules"
    / "reporting-engine"
    / "scripts"
    / "check_compatibility.py"
)


def _load_packaged_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "reporting_engine_packaged_check_compatibility", PACKAGED_CHECKER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Cannot load Reporting Engine compatibility checker: {PACKAGED_CHECKER}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_CHECKER = _load_packaged_checker()
audit_manifest_against_dataset_profile = _CHECKER.audit_manifest_against_dataset_profile
check_capability_compatibility = _CHECKER.check_capability_compatibility
check_profile_compatibility = _CHECKER.check_profile_compatibility


def main(argv: list[str] | None = None) -> int:
    """Delegate the CLI to the packaged compatibility checker."""

    return int(_CHECKER.main(argv))


def __getattr__(name: str) -> Any:
    """Expose packaged helpers for repository diagnostics."""

    return getattr(_CHECKER, name)


if __name__ == "__main__":
    raise SystemExit(main())
