from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests_tagging_stub import ensure_tagging_stub  # isort: skip

__all__ = []


def _ensure_jinja_stub() -> None:
    """Provide a minimal jinja2 stub so module imports remain self-contained."""

    if "jinja2" in sys.modules:
        return
    jinja2_stub = types.ModuleType("jinja2")

    def pass_context(func: Callable[..., object]) -> Callable[..., object]:
        return func

    class FileSystemLoader:
        def __init__(self, directory: object) -> None:
            self.directory = directory

    class _Template:
        def render(self, context: dict[str, object]) -> str:
            payload = {
                "preview_styles": context.get("preview_styles", []),
                "preview_scripts": context.get("preview_scripts", []),
                "preview_allowlist": context.get("preview_allowlist", []),
            }
            return (
                '<script id="slidesEditorBootstrap" type="application/json">'
                f"{json.dumps(payload)}"
                "</script>"
            )

    class Environment:
        def __init__(self, **_: object) -> None:
            self.globals: dict[str, object] = {}

        def get_template(self, _name: str) -> _Template:
            return _Template()

    jinja2_stub.pass_context = pass_context
    jinja2_stub.FileSystemLoader = FileSystemLoader
    jinja2_stub.Environment = Environment
    sys.modules["jinja2"] = jinja2_stub


_ensure_jinja_stub()
ensure_tagging_stub()
