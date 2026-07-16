from __future__ import annotations

import sys
import types
from pathlib import Path


def _ensure_repo_root_first() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    root_str = str(repo_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    to_remove = [key for key in sys.modules if key == "modules" or key.startswith("modules.")]
    for name in to_remove:
        sys.modules.pop(name, None)
    import importlib

    importlib.invalidate_caches()
    _install_slides_api_stub()
    importlib.import_module("modules")


def _install_slides_api_stub() -> None:
    """Stub the slides API so PDP tests avoid OCR-heavy import side effects."""
    if "modules.slides.api" in sys.modules:
        return
    from fastapi import APIRouter

    stub = types.ModuleType("modules.slides.api")
    stub.router = APIRouter()
    stub.site_router = APIRouter()
    stub.get_storage = lambda: None
    stub.is_any_ocr_running = lambda: False
    sys.modules["modules.slides.api"] = stub


_ensure_repo_root_first()
