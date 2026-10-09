"""Resolve the already prepared shared runtime; never install dependencies."""

from __future__ import annotations

import sys
from pathlib import Path

from managed_python_runtime import activate_runtime, runtime_python

__all__ = ["main"]


def main() -> None:
    """Use the canonical recipe and readiness receipt before starting a workflow."""
    target = activate_runtime(Path(__file__).resolve().parents[1])
    if target is None:
        raise SystemExit(
            "Complete Vera's managed Python setup before opening the workspace"
        )
    sys.stdout.write(str(runtime_python(target)))


if __name__ == "__main__":
    main()
