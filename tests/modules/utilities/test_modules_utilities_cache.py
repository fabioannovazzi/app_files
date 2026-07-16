from __future__ import annotations

from pathlib import Path

from modules.utilities import cache as cache_mod
from modules.utilities.cache import get_cache_dir


def test_get_cache_dir_uses_project_caches(monkeypatch, tmp_path):
    project_root = tmp_path / "repo"
    caches_root = project_root / "caches"
    monkeypatch.setattr(cache_mod, "_discover_project_caches_root", lambda: caches_root)
    path = get_cache_dir("demo")
    assert path == caches_root / "demo"
    assert path.exists()


def test_get_cache_dir_falls_back_to_cwd(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_mod, "_discover_project_caches_root", lambda: None)
    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: tmp_path))
    path = get_cache_dir("demo")
    assert path == tmp_path / "caches" / "demo"
    assert path.exists()


def test_get_cache_dir_ignores_env_overrides(monkeypatch, tmp_path):
    caches_root = tmp_path / "caches"
    monkeypatch.setattr(cache_mod, "_discover_project_caches_root", lambda: caches_root)
    monkeypatch.setenv("APP_CACHE_ROOT", str(tmp_path / "ignored_app_cache"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "ignored_xdg"))
    path = get_cache_dir("demo")
    assert path == caches_root / "demo"
    assert path.exists()
