from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "plugins" / "browser-automation"
SCRIPT = COMPONENT / "scripts" / "check_installation.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_browser_automation_installation_module", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _component_fixture(
    tmp_path: Path, *, plugin_name: str, version: str, bundled: bool
) -> Path:
    if bundled:
        plugin_root = tmp_path / "vera" / version
        component_root = plugin_root / "modules" / "browser-automation"
    else:
        plugin_root = tmp_path / "browser-automation"
        component_root = plugin_root
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"name": plugin_name, "version": version}), encoding="utf-8"
    )
    module = _load_module()
    for relative_path in module.REQUIRED_COMPONENT_PATHS:
        target = component_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")
    return component_root


@pytest.mark.parametrize("version", ["0.1.1", "8.4.2", "12.0.0-beta.1"])
def test_installed_vera_version_is_observed_not_pinned(
    tmp_path: Path, version: str
) -> None:
    module = _load_module()
    component_root = _component_fixture(
        tmp_path, plugin_name="vera", version=version, bundled=True
    )

    result = module.inspect_installation(component_root)

    assert result["status"] == "compatible"
    assert result["plugin"]["name"] == "vera"
    assert result["plugin"]["version"] == version
    assert Path(result["plugin"]["manifest_path"]) == (
        component_root.parent.parent / ".codex-plugin" / "plugin.json"
    )
    assert result["version_source"] == "active_plugin_manifest"


def test_standalone_browser_automation_manifest_is_resolved(tmp_path: Path) -> None:
    module = _load_module()
    component_root = _component_fixture(
        tmp_path,
        plugin_name="browser-automation",
        version="3.2.1",
        bundled=False,
    )

    result = module.inspect_installation(component_root)

    assert Path(result["plugin"]["manifest_path"]) == (
        component_root / ".codex-plugin" / "plugin.json"
    )


def test_installation_preflight_rejects_missing_contract_file(tmp_path: Path) -> None:
    module = _load_module()
    component_root = _component_fixture(
        tmp_path, plugin_name="vera", version="4.5.6", bundled=True
    )
    (component_root / "scripts" / "capability_runtime.mjs").unlink()

    with pytest.raises(ValueError, match="installation is incomplete"):
        module.inspect_installation(component_root)


def test_browser_automation_skills_forbid_historical_version_pins() -> None:
    module_skill = (COMPONENT / "skills" / "browser-automation" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    wrapper_skill = (
        ROOT / "plugins" / "vera" / "skills" / "browser-automation" / "SKILL.md"
    ).read_text(encoding="utf-8")
    normalized_module_skill = " ".join(module_skill.split())
    normalized_wrapper_skill = " ".join(wrapper_skill.split())

    assert "python scripts/check_installation.py" in module_skill
    assert (
        "A newer installed Vera version is the subject under test"
        in normalized_module_skill
    )
    assert "Never reject a newer installed Vera" in normalized_wrapper_skill
