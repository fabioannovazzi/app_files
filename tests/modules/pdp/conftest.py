from __future__ import annotations

import sys
from pathlib import Path


def _ensure_repo_root_first() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    root_str = str(repo_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    to_remove = [
        key for key in sys.modules if key == "modules" or key.startswith("modules.")
    ]
    for name in to_remove:
        sys.modules.pop(name, None)
    import importlib

    importlib.invalidate_caches()
    importlib.import_module("modules")


_ensure_repo_root_first()
