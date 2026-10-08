"""Locate Vera's already prepared shared runtime without importing optional dependencies."""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["main"]


def main() -> int:
    component = Path(__file__).resolve().parents[1]
    for root in (component.parent / "vera", component.parent.parent):
        if (root / "scripts/managed_python_runtime.py").is_file():
            sys.path.insert(0, str(root / "scripts"))
            from managed_python_runtime import activate_runtime, runtime_python

            target = activate_runtime(
                root,
                module="browser-automation",
                requirements=["requirements-agenzia.txt"],
            )
            if target is not None:
                sys.stdout.write(str(runtime_python(target)))
                return 0
    sys.stderr.write(
        "Complete Vera's managed Python setup before opening Agenzia acquisition.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
