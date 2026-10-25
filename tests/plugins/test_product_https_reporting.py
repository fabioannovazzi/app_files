"""Built product distributions must not reintroduce remote MCP reporting."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


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
