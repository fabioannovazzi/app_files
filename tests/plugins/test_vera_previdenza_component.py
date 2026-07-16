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
    spec = importlib.util.spec_from_file_location("build_vera_previdenza", BUILD_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_vera_declares_previdenza_component_skill_and_mcp_route() -> None:
    components = json.loads((VERA_ROOT / "components.json").read_text(encoding="utf-8"))
    mcp = json.loads((VERA_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    routed_modules = {server["args"][-1] for server in mcp["mcpServers"].values()}

    assert "previdenza-inps" in components["plugins"]
    assert "previdenza-inps" in routed_modules
    assert (VERA_ROOT / "skills" / "previdenza-inps" / "SKILL.md").exists()


def test_vera_delegates_previdenza_dependency_check() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(VERA_ROOT / "scripts" / "check_dependencies.py"),
            "--module",
            "previdenza-inps",
        ],
        cwd=VERA_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_vera_zip_expected_entries_embed_previdenza_component() -> None:
    builder = _load_builder()
    bundle = next(bundle for bundle in builder.load_bundles() if bundle.name == "vera")

    entries = builder.expected_zip_entries(bundle)

    prefix = "vera-codex-plugin/plugins/vera/modules/previdenza-inps/"
    assert prefix + "skills/previdenza-inps/SKILL.md" in entries
    assert prefix + "scripts/inventory_case.py" in entries
    assert prefix + "mcp/server.cjs" in entries
