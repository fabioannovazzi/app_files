from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path


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


def test_save_cache_merges_updates(tmp_path: Path, monkeypatch):
    pac = _import_pac()
    cache_path = tmp_path / "product_attributes.json"
    monkeypatch.setattr(pac, "CACHE_FILE", cache_path)

    pac.save_cache({"beauty": {"": {"lipstick": {"finish": "matte"}}}})
    pac.save_cache({"beauty": {"": {"lipstick": {"shade": "red"}}}})

    data = pac.load_cache()
    entry = data["beauty"][""]["lipstick"]
    assert entry["finish"] == "matte"
    assert entry["shade"] == "red"
