from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

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


def test_vera_delegates_bilancio_xbrl_dependency_check() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(VERA_ROOT / "scripts" / "check_dependencies.py"),
            "--module",
            "bilancio-xbrl-it",
        ],
        cwd=VERA_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_vera_zip_expected_entries_embed_bilancio_xbrl_component() -> None:
    builder = _load_builder()
    bundle = next(bundle for bundle in builder.load_bundles() if bundle.name == "vera")

    entries = builder.expected_zip_entries(bundle)

    prefix = "vera-codex-plugin/plugins/vera/modules/bilancio-xbrl-it/"
    assert prefix + "skills/bilancio-xbrl-it/SKILL.md" in entries
    assert prefix + "scripts/xbrl_case.py" in entries
    assert prefix + "mcp/server.cjs" in entries


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
