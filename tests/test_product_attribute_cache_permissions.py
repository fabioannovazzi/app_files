from pathlib import Path

import importlib
import sys
import types

import pytest


def _import_pac():
    if "src.product_attribute_cache" in sys.modules:
        del sys.modules["src.product_attribute_cache"]
    if "modules.add_attributes" in sys.modules:
        del sys.modules["modules.add_attributes"]
    if "modules.add_attributes.normalization" in sys.modules:
        del sys.modules["modules.add_attributes.normalization"]

    add_attrs_pkg = types.ModuleType("modules.add_attributes")
    add_attrs_pkg.__path__ = []  # type: ignore[attr-defined]
    normalization_mod = types.ModuleType("modules.add_attributes.normalization")
    normalization_mod.normalize_product_key = lambda value: str(value).strip().lower()
    sys.modules["modules.add_attributes"] = add_attrs_pkg
    sys.modules["modules.add_attributes.normalization"] = normalization_mod

    return importlib.import_module("src.product_attribute_cache")


def test_get_cache_dir_returns_writable_default(monkeypatch, tmp_path):
    pac = _import_pac()

    def fake_get_cache_dir(subdir: str):
        return tmp_path / "caches" / subdir

    monkeypatch.setattr(pac, "get_cache_dir", fake_get_cache_dir)
    cache_dir = pac._get_cache_dir()
    assert cache_dir == fake_get_cache_dir("product_attribute_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    test_file = cache_dir / "test.json"
    test_file.write_text("{}", encoding="utf-8")
    assert test_file.exists()


def test_get_cache_dir_raises_when_default_unwritable(monkeypatch, tmp_path):
    pac = _import_pac()
    ro_dir = tmp_path / "ro"

    def fake_get_cache_dir(subdir: str):
        path = ro_dir / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(pac, "get_cache_dir", fake_get_cache_dir)

    original_mkdir = pac.Path.mkdir

    def mock_mkdir(self, *args, **kwargs):
        if self == ro_dir / "product_attribute_cache":
            raise PermissionError("denied")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(pac.Path, "mkdir", mock_mkdir)

    with pytest.raises(PermissionError):
        pac._get_cache_dir()


def test_save_cache_permission_error(monkeypatch):
    pac = _import_pac()

    original_replace = pac.Path.replace

    def mock_replace(self, target):
        if self == pac.CACHE_FILE.with_suffix(".json.tmp"):
            raise PermissionError("denied")
        return original_replace(self, target)

    monkeypatch.setattr(pac.Path, "replace", mock_replace)
    with __import__("pytest").raises(PermissionError):
        pac.save_cache({"a": {"b": {"c": "d"}}})


def test_load_cache_permission_error(monkeypatch, tmp_path):
    pac = _import_pac()
    cache_file = tmp_path / "product_attributes.json"
    cache_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pac, "CACHE_FILE", cache_file)

    original_read_text = pac.Path.read_text

    def mock_read_text(self, *args, **kwargs):
        if self == cache_file:
            raise PermissionError("denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(pac.Path, "read_text", mock_read_text)
    with __import__("pytest").raises(PermissionError):
        pac.load_cache()


def test_save_cache_retries_replace_on_permission_error(monkeypatch, tmp_path):
    pac = _import_pac()
    cache_file = tmp_path / "product_attributes.json"
    monkeypatch.setattr(pac, "CACHE_FILE", cache_file)

    original_replace = pac.Path.replace
    attempts = {"count": 0}

    def mock_replace(self, target):
        if self == cache_file.with_suffix(".json.tmp") and attempts["count"] < 2:
            attempts["count"] += 1
            raise PermissionError("locked")
        return original_replace(self, target)

    monkeypatch.setattr(pac.Path, "replace", mock_replace)

    pac.save_cache({"beauty": {"": {"lipstick": {"finish": "matte"}}}})

    assert attempts["count"] == 2
    data = pac.load_cache()
    assert data["beauty"][""]["lipstick"]["finish"] == "matte"
