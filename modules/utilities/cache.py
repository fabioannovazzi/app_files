from __future__ import annotations

from pathlib import Path

__all__ = ["get_cache_dir", "get_cache_root", "get_cache_path"]


def _discover_project_caches_root() -> Path | None:
    """Return `<repo-root>/caches` if the repo root is discoverable.

    We walk up from this file looking for a plausible repository root (presence
    of `.git` or `pyproject.toml`). When found, we always return the sibling
    `caches/` path so the cache location is consistent for the project.
    """
    here = Path(__file__).resolve()
    for parent in list(here.parents):
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent / "caches"
    return None


def get_cache_root() -> Path:
    """Return the base directory under which caches are stored.

    Precedence:
    - `<repo-root>/caches` (if discoverable)
    - `<cwd>/caches` (fallback when a repo root cannot be found)
    The directory is created if missing.
    """
    root = _discover_project_caches_root() or (Path.cwd() / "caches")
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_cache_dir(*parts: str) -> Path:
    """Return a cache directory path under the cache root.

    Use this for directories (e.g. `get_cache_dir("page_cache")`). For file
    paths, prefer ``get_cache_path("name.json")`` to avoid creating a
    directory named after the file.
    """
    root = get_cache_root()
    path = root.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_cache_path(name: str) -> Path:
    """Return a cache file path under the cache root without creating the file.

    Example: ``get_cache_path("alias_index.json")`` -> `<root>/alias_index.json`.
    The parent directory is ensured to exist when you call ``write_text`` etc.
    """
    return get_cache_root() / name
