"""Repository wrapper for the packaged Reporting Engine dataset profiler."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

__all__ = ["build_dataset_profile", "profile_dataset", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGED_PROFILER = (
    REPO_ROOT / "plugins" / "reporting-engine" / "scripts" / "profile_dataset.py"
)


def _load_packaged_profiler() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "reporting_engine_packaged_profile_dataset", PACKAGED_PROFILER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Cannot load Reporting Engine profiler: {PACKAGED_PROFILER}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_PROFILER = _load_packaged_profiler()
build_dataset_profile = _PROFILER.build_dataset_profile
profile_dataset = _PROFILER.profile_dataset
_profile_frame = _PROFILER._profile_frame


def main(argv: list[str] | None = None) -> int:
    """Delegate the CLI to the packaged profiler implementation."""

    return int(_PROFILER.main(argv))


def __getattr__(name: str) -> Any:
    """Expose private helpers used by focused repository tests."""

    return getattr(_PROFILER, name)


if __name__ == "__main__":
    raise SystemExit(main())
