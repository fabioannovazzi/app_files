"""Resolve the installed product from its packaged manifest, never caller text."""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["product_name", "installed_reference_path"]


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


def installed_reference_path(reference: str, root: Path | None = None) -> str:
    """Resolve a known reference by file presence, not an assumed host layout."""
    root = root or Path(__file__).resolve().parents[1]
    if reference not in {"workflow-usage.md", "incident-recovery.md"}:
        raise ValueError("Unsupported reporting reference")
    product = product_name(root)
    candidates = [
        root / "skills" / skill / "references" / reference
        for skill in (product, f"mparanza-{product}")
    ]
    existing = [path for path in candidates if path.is_file()]
    if len(existing) != 1:
        raise ValueError("Installed reporting reference is missing or ambiguous")
    return existing[0].relative_to(root).as_posix()
