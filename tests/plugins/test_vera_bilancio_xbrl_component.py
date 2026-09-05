from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERA_ROOT = ROOT / "plugins" / "vera"
BUILD_SCRIPT = ROOT / "scripts" / "build_codex_plugin_zip.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_vera_bilancio_xbrl", BUILD_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_vera_declares_bilancio_xbrl_skill_and_mcp_route() -> None:
    components = json.loads((VERA_ROOT / "components.json").read_text(encoding="utf-8"))
    mcp = json.loads((VERA_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    routed_modules = {server["args"][-1] for server in mcp["mcpServers"].values()}

    assert "bilancio-xbrl-it" in components["plugins"]
    assert "bilancio-xbrl-it" in routed_modules
    assert (VERA_ROOT / "skills" / "bilancio-xbrl-it" / "SKILL.md").is_file()


@pytest.mark.parametrize(
    "component_name",
    [
        "bilancio-xbrl-it",
        "previdenza-inps",
        "registro-imprese-sari",
        "client-file-preparation",
        "new-client",
    ],
)
def test_vera_delegates_component_dependency_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    component_name: str,
) -> None:
    monkeypatch.syspath_prepend(str(VERA_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "vera_bilancio_dependency_checker",
        VERA_ROOT / "scripts" / "check_dependencies.py",
    )
    assert spec and spec.loader
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    target = tmp_path / "runtime"
    python = target / "bin" / "python"
    ensure = Mock(return_value=(True, target, "ready"))
    run = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(checker, "ensure_runtime", ensure)
    monkeypatch.setattr(checker, "runtime_python", lambda target: python)
    monkeypatch.setattr(
        checker, "runtime_environment", lambda target: {"TEST_RUNTIME": "1"}
    )
    monkeypatch.setattr(checker.subprocess, "run", run)

    result = checker.main(["--module", component_name])

    assert result == 0
    ensure.assert_called_once_with(VERA_ROOT, component_name, requirements=None)
    component = ROOT / "plugins" / component_name
    run.assert_called_once_with(
        [str(python), str(component / "scripts" / "check_dependencies.py")],
        cwd=component,
        env={"TEST_RUNTIME": "1"},
        check=False,
    )


def test_vera_zip_expected_entries_embed_bilancio_xbrl_component() -> None:
    builder = _load_builder()
    bundle = next(bundle for bundle in builder.load_bundles() if bundle.name == "vera")

    entries = builder.expected_zip_entries(bundle)

    prefix = "vera-codex-plugin/plugins/vera/modules/bilancio-xbrl-it/"
    assert prefix + "skills/bilancio-xbrl-it/SKILL.md" in entries
    assert prefix + "scripts/xbrl_case.py" in entries
    assert prefix + "mcp/server.cjs" in entries


def test_vera_chatgpt_bilancio_skill_routes_to_complete_module_workflow() -> None:
    builder = _load_builder()
    bundle = next(bundle for bundle in builder.load_bundles() if bundle.name == "vera")

    entries = builder.chatgpt_upload_entries(bundle)
    router = entries["skills/vera/SKILL.md"].decode("utf-8")
    wrapper = entries["skills/bilancio-xbrl-it/SKILL.md"].decode("utf-8")
    skill = entries["modules/bilancio-xbrl-it/skills/bilancio-xbrl-it/SKILL.md"].decode(
        "utf-8"
    )

    assert "../<skill-name>/SKILL.md" in router
    assert "../../modules/bilancio-xbrl-it" in wrapper
    assert "skills/bilancio-xbrl-it/WORKFLOW.md" not in entries
    assert "skills/bilancio-xbrl-it/SKILL.md" in entries
    assert "# Bilancio intelligente" in skill
    assert "scripts/check_dependencies.py" in skill


def test_bilancio_xbrl_icon_uses_shared_theme_and_is_unique() -> None:
    icon_path = ROOT / "plugins" / "bilancio-xbrl-it" / "assets" / "icon.svg"
    icon = icon_path.read_text(encoding="utf-8")
    other_icons = [
        path.read_text(encoding="utf-8")
        for path in (ROOT / "plugins").glob("*/assets/icon.svg")
        if path != icon_path
    ]

    assert 'data-theme="mparanza-plugin-icon-v1"' in icon
    assert 'viewBox="0 0 64 64"' in icon
    assert 'fill="#171816"' in icon
    assert icon not in other_icons
