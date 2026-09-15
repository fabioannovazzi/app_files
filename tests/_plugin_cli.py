"""Run workflow CLI contracts with the test environment's declared dependencies."""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["workflow_cli"]


def workflow_cli(script: Path) -> list[str]:
    """Call the public main function; packaged startup has separate runtime tests."""
    return [
        sys.executable,
        "-c",
        "import importlib,sys; from pathlib import Path; script=Path(sys.argv[1]); "
        "sys.path.insert(0,str(script.parent)); sys.argv=sys.argv[1:]; "
        "raise SystemExit(importlib.import_module(script.stem).main())",
        str(script),
    ]
