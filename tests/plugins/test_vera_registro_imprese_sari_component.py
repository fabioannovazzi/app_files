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
        "build_vera_registro_imprese_sari", BUILD_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_vera_declares_registro_imprese_sari_component_skill_and_mcp_route() -> None:
    components = json.loads((VERA_ROOT / "components.json").read_text(encoding="utf-8"))
    mcp = json.loads((VERA_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    routed_modules = {server["args"][-1] for server in mcp["mcpServers"].values()}

    assert "registro-imprese-sari" in components["plugins"]
    assert "registro-imprese-sari" in routed_modules
    wrapper = VERA_ROOT / "skills" / "registro-imprese-sari" / "SKILL.md"
    assert wrapper.exists()
    wrapper_text = wrapper.read_text(encoding="utf-8")
    assert "modules/registro-imprese-sari" in wrapper_text
    assert "skills/registro-imprese-sari/SKILL.md" in wrapper_text


def test_vera_delegates_registro_imprese_sari_dependency_check() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(VERA_ROOT / "scripts" / "check_dependencies.py"),
            "--module",
            "registro-imprese-sari",
        ],
        cwd=VERA_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_vera_zip_expected_entries_embed_registro_imprese_sari_component() -> None:
    builder = _load_builder()
    bundle = next(bundle for bundle in builder.load_bundles() if bundle.name == "vera")

    entries = builder.expected_zip_entries(bundle)

    prefix = "vera-codex-plugin/plugins/vera/modules/registro-imprese-sari/"
    assert prefix + "skills/registro-imprese-sari/SKILL.md" in entries
    assert prefix + "scripts/sari_connector.py" in entries
    assert prefix + "scripts/register_official_source.py" in entries
    assert prefix + "scripts/inventory_case.py" in entries
    assert prefix + "scripts/validate_practice_case.py" in entries
    assert prefix + "scripts/package_practice.py" in entries
    assert prefix + "schemas/case_intake.schema.json" in entries
    assert prefix + "schemas/practice_plan.schema.json" in entries
    assert prefix + "mcp/server.cjs" in entries
    assert prefix + "assets/registro-imprese-sari-review-widget.html" in entries
