"""Helpers for loading journal layout recipes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import yaml

from .model import LayoutConfig

_RECIPE_DIRS = [
    Path(__file__).resolve().parent / "recipes",
    Path(__file__).resolve().parents[3] / "config" / "recipes",
]

_DEFAULT_RECIPE = "journal_generic_v1"


def _discover_recipe_paths() -> Dict[str, Path]:
    """Map recipe names to their file paths."""

    paths: Dict[str, Path] = {}
    for base in _RECIPE_DIRS:
        if not base.exists():
            continue
        for f in base.iterdir():
            if f.suffix.lower() in {".yaml", ".yml", ".json"}:
                paths[f.stem] = f
    return paths


_RECIPE_PATHS = _discover_recipe_paths()
_RECIPE_CACHE: Dict[str, LayoutConfig] = {}


def load_layout(path: str | Path) -> LayoutConfig:
    """Load a layout configuration from YAML or JSON."""

    p = Path(path)
    data: dict[str, Any]
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text())
    else:
        data = yaml.safe_load(p.read_text())

    allowed = set(LayoutConfig.__dataclass_fields__)
    filtered = {k: v for k, v in data.items() if k in allowed}
    return LayoutConfig(**filtered)


def get_recipe(name: str) -> LayoutConfig:
    """Return the :class:`LayoutConfig` for ``name``.

    Unknown names fall back to the generic recipe so callers always receive a
    valid configuration.
    """

    path = _RECIPE_PATHS.get(name)
    if path is None:
        path = _RECIPE_PATHS.get(_DEFAULT_RECIPE)
        name = _DEFAULT_RECIPE
        if path is None:
            raise FileNotFoundError("default recipe not found")
    if name not in _RECIPE_CACHE:
        _RECIPE_CACHE[name] = load_layout(path)
    return _RECIPE_CACHE[name]
