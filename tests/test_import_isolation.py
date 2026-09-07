from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

__all__ = []


@pytest.mark.parametrize("inside_plugin_tree", [True, False])
def test_setup_classifies_symlinked_modules_by_resolved_location(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    inside_plugin_tree: bool,
) -> None:
    hooks = request.config.pluginmanager.getplugin(
        str(Path(__file__).with_name("conftest.py"))
    )
    repository = tmp_path / "repository"
    plugins = repository / "plugins"
    plugins.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    target = (plugins if inside_plugin_tree else external) / "source.py"
    target.write_text("value = 1\n")
    alias = tmp_path / "alias.py"
    alias.symlink_to(target)
    module = ModuleType("synthetic_module")
    module.__file__ = str(alias)
    runtime = SimpleNamespace(modules={module.__name__: module}, path=[])
    monkeypatch.setattr(hooks, "ROOT", repository)
    monkeypatch.setattr(hooks, "sys", runtime)
    monkeypatch.setattr(hooks, "_CANONICAL_MODULES", {})
    monkeypatch.setattr(hooks, "_RUNTIME_IMPORT_SNAPSHOTS", {})

    hooks.pytest_runtest_setup(SimpleNamespace(nodeid="synthetic_test"))

    assert (module.__name__ in runtime.modules) is not inside_plugin_tree
