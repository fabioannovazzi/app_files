"""Resolve the installed product from its packaged manifest, never caller text."""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["product_name"]


def product_name(root: Path | None = None) -> str:
    """Return one supported, immutable package namespace."""
    root = root or Path(__file__).resolve().parents[1]
    for relative in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        path = root / relative
        if path.is_file():
            metadata = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict) or "name" not in metadata:
                raise ValueError("Installed product manifest is invalid")
            name = metadata["name"]
            if name not in {"vera", "clara", "lucia"}:
                raise ValueError("Unsupported reporting product")
            return name
    raise ValueError("Installed product manifest is unavailable")
