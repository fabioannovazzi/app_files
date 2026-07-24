from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from zipfile import ZipFile

import pytest

__all__ = [
    "test_local_package_exposes_codex_desktop_runtime_contract",
    "test_extracted_local_package_dependency_checker_starts",
    "test_public_chatgpt_skill_projection_continues_with_codex_recommendation",
]

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build_codex_plugin_zip.py"
PLUGIN_NAMES = ("clara", "vera")


def load_builder() -> ModuleType:
    """Load the plugin package builder without invoking its CLI."""

    spec = importlib.util.spec_from_file_location(
        "desktop_acceptance_build_codex_plugin_zip",
        BUILD_SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configured_target(builder: ModuleType, plugin_name: str) -> Any:
    """Return one configured local package or bundle by public plugin name."""

    targets = {package.plugin: package for package in builder.load_packages()}
    targets.update({bundle.name: bundle for bundle in builder.load_bundles()})
    return targets[plugin_name]


@pytest.mark.parametrize(
    ("plugin_name", "expected_runtime_configs", "expected_manifest_configs"),
    (
        ("clara", frozenset(), {}),
        (
            "vera",
            frozenset({".app.json", ".mcp.json"}),
            {"apps": "./.app.json", "mcpServers": "./.mcp.json"},
        ),
    ),
)
def test_local_package_exposes_codex_desktop_runtime_contract(
    plugin_name: str,
    expected_runtime_configs: frozenset[str],
    expected_manifest_configs: dict[str, str],
) -> None:
    builder = load_builder()
    target = configured_target(builder, plugin_name)
    package_root = f"{target.package_root}/plugins/{plugin_name}"
    marketplace_path = f"{target.package_root}/.agents/plugins/marketplace.json"
    manifest_path = f"{package_root}/.codex-plugin/plugin.json"
    required_entries = {
        marketplace_path,
        manifest_path,
        f"{package_root}/skills/{plugin_name}/SKILL.md",
        f"{package_root}/hooks/hooks.json",
        f"{package_root}/requirements.txt",
        f"{package_root}/scripts/check_dependencies.py",
    }

    with ZipFile(target.output_zip) as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
        manifest = json.loads(archive.read(manifest_path))
        marketplace = json.loads(archive.read(marketplace_path))

    runtime_configs = {
        name for name in (".app.json", ".mcp.json") if f"{package_root}/{name}" in names
    }
    manifest_configs = {
        name: manifest[name] for name in ("apps", "mcpServers") if name in manifest
    }

    assert required_entries <= names
    assert manifest["name"] == plugin_name
    assert manifest["skills"] == "./skills/"
    assert manifest["hooks"] == "./hooks/hooks.json"
    assert runtime_configs == expected_runtime_configs
    assert manifest_configs == expected_manifest_configs
    assert len(marketplace["plugins"]) == 1
    assert marketplace["plugins"][0]["name"] == plugin_name
    assert marketplace["plugins"][0]["source"]["path"] == f"./plugins/{plugin_name}"


@pytest.mark.parametrize("plugin_name", PLUGIN_NAMES)
def test_extracted_local_package_dependency_checker_starts(
    plugin_name: str,
    tmp_path: Path,
) -> None:
    builder = load_builder()
    target = configured_target(builder, plugin_name)

    with ZipFile(target.output_zip) as archive:
        archive.extractall(tmp_path)

    plugin_root = tmp_path / target.package_root / "plugins" / plugin_name
    checker = plugin_root / "scripts" / "check_dependencies.py"

    completed = subprocess.run(
        [sys.executable, str(checker), "--help"],
        cwd=plugin_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.lower()
    assert plugin_name in completed.stdout.lower()


@pytest.mark.parametrize("plugin_name", PLUGIN_NAMES)
def test_public_chatgpt_skill_projection_continues_with_codex_recommendation(
    plugin_name: str,
) -> None:
    builder = load_builder()
    target = configured_target(builder, plugin_name)

    entries = builder.chatgpt_upload_entries(target)

    public_skills = {
        name: content.decode("utf-8")
        for name, content in entries.items()
        if name.endswith("/SKILL.md")
    }
    assert public_skills
    assert all(
        builder.has_chatgpt_runtime_contract(content)
        for content in public_skills.values()
    )
    assert all(
        "We can continue here in ChatGPT now." in content
        for content in public_skills.values()
    )
    if plugin_name == "vera":
        assert all(
            "Possiamo continuare qui in ChatGPT." in content
            for content in public_skills.values()
        )
