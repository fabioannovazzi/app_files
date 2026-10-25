"""Built product distributions must not reintroduce remote MCP reporting."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("product", ("vera", "clara", "lucia"))
def test_public_upload_discovers_local_tools_from_portable_manifest(product):
    """Portable ingestion must find the same executable services as native clients."""
    with ZipFile(
        ROOT / "plugin_packages" / product / f"{product}-chatgpt-upload.zip"
    ) as archive:
        manifest = json.loads(archive.read("plugin.json"))
        legacy = json.loads(archive.read(".codex-plugin/plugin.json"))
        mcp = json.loads(archive.read("mcp.json"))
        native = json.loads(archive.read(".mcp.json"))["mcpServers"]

    assert (
        manifest["$schema"]
        == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    )
    assert manifest["name"] == product
    assert manifest["version"] == legacy["version"]
    assert not {"interface", "skills", "mcpServers", "apps", "hooks"} & manifest.keys()
    assert manifest["extensions"]["com.openai"]["interface"] == legacy["interface"]
    assert manifest["extensions"]["com.openai"]["requires_local_executor"] is True
    assert mcp["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    assert mcp["mcpServers"].keys() == native.keys()
    assert all(server["type"] == "stdio" for server in mcp["mcpServers"].values())
    assert all(server["command"] == "node" for server in mcp["mcpServers"].values())
    assert all(
        server["cwd"] == "${PLUGIN_ROOT}" for server in mcp["mcpServers"].values()
    )
    assert all("url" not in server for server in mcp["mcpServers"].values())
    assert "CLAUDE_PLUGIN_ROOT" not in json.dumps(mcp)
    assert "CODEX_PLUGIN_ROOT" not in json.dumps(mcp)


@pytest.mark.parametrize("product", ("clara", "lucia"))
def test_marketplace_preparation_preserves_known_metadata_without_inventing_review(
    product,
):
    with ZipFile(
        ROOT / "plugin_packages" / product / f"{product}-chatgpt-upload.zip"
    ) as archive:
        manifest = json.loads(archive.read("plugin.json"))
        legacy = json.loads(archive.read(".codex-plugin/plugin.json"))
        declared = json.loads(archive.read("submission/openai.json"))

    openai = manifest["extensions"]["com.openai"]
    assert openai["review"] == declared["review"]
    assert openai["publication"] == declared["publication"]
    assert legacy["extensions"]["com.openai"]["review"] == openai["review"]
    assert openai["publication"]["release_notes"]
    assert "demo_recording_url" not in openai["review"]
    assert "countries" not in openai["publication"]


@pytest.mark.parametrize("product", ("vera", "clara", "lucia"))
def test_public_upload_omits_app_bindings_without_changing_local_mcp(product):
    source = ROOT / "plugins" / product
    with ZipFile(
        ROOT / "plugin_packages" / product / f"{product}-chatgpt-upload.zip"
    ) as archive:
        manifests = [
            json.loads(archive.read(name))
            for name in archive.namelist()
            if name.endswith(".codex-plugin/plugin.json")
        ]
        assert ".app.json" not in archive.namelist()
        assert manifests
        assert all(manifest.get("apps") is None for manifest in manifests)
        assert all(
            manifest.get("extensions", {}).get("com.openai", {}).get("apps") is None
            for manifest in manifests
        )
        assert archive.read(".mcp.json") == (source / ".mcp.json").read_bytes()
    assert (
        json.loads((source / ".codex-plugin/plugin.json").read_bytes())["apps"]
        == "./.app.json"
    )
    assert json.loads((source / ".app.json").read_bytes()) == {"apps": {}}


@pytest.mark.parametrize("product", ("vera", "clara", "lucia"))
@pytest.mark.parametrize("host", ("codex", "chatgpt", "cowork", "antigravity"))
def test_actual_package_keeps_local_reporting_and_has_no_remote_mcp(product, host):
    archives = {
        "codex": f"plugin_packages/{product}/{product}-plugin.zip",
        "chatgpt": f"plugin_packages/{product}/{product}-chatgpt-upload.zip",
        "cowork": f"plugin_packages/{product}/{product}-claude-plugin.zip",
        "antigravity": f"static/shared/{product}/downloads/{product}-antigravity-plugin.zip",
    }

    with ZipFile(ROOT / archives[host]) as archive:
        configurations = {
            name: json.loads(archive.read(name))["mcpServers"]
            for name in archive.namelist()
            if name.endswith((".mcp.json", "mcp_config.json"))
        }
        local_reporting = {
            name: server
            for configuration in configurations.values()
            for name, server in configuration.items()
            if name == product + "IncidentHost"
        }
        remote = {
            name: server
            for configuration in configurations.values()
            for name, server in configuration.items()
            if "url" in server or "serverUrl" in server
        }
        schemas = [
            name
            for name in archive.namelist()
            if name.endswith("/scripts/incident_tool_schemas.json")
            or name == "scripts/incident_tool_schemas.json"
        ]
        assert configurations
        assert remote == {}
        assert set(local_reporting) == {product + "IncidentHost"}
        assert local_reporting[product + "IncidentHost"]["command"] == "node"
        assert len(schemas) == 1
        operations = {tool["name"] for tool in json.loads(archive.read(schemas[0]))}
        assert operations == {
            "vera_incident_register",
            "vera_incident_report",
            "vera_incident_status",
            "vera_incident_progress",
            "vera_incident_outcome",
            "vera_workflow_stamp",
        }
        if product == "vera":
            router = next(
                name
                for name in archive.namelist()
                if name.endswith(
                    ("skills/vera/SKILL.md", "skills/mparanza-vera/SKILL.md")
                )
            )
            instructions = archive.read(router).decode()
            assert "anonymous connector identity" not in instructions
            assert "do not pass credentials to local tools" in instructions
            assert "https://mparanza.com/vera/incident-recovery" in instructions
