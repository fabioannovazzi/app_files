"""Release packages retain source MCP capabilities on both OpenAI surfaces."""

from __future__ import annotations

import json

import pytest

from tests.plugins.test_codex_plugin_packages import load_builder

__all__: list[str] = []


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("surface", ["download", "upload"])
def test_package_preserves_source_mcp_capabilities(product, surface):
    """Prevent shipping fewer MCP tools than the source plugin exposes."""
    builder = load_builder()
    target = next(
        target
        for target in [*builder.load_bundles(), *builder.load_packages()]
        if target.target_name == product
    )
    prefix = f"{target.package_root}/plugins/{product}/"
    source = {
        name.removeprefix(prefix): content
        for name, content in builder.source_zip_entries(target).items()
        if name.startswith(prefix)
    }
    if surface == "download":
        entries = {
            name.removeprefix(prefix): content
            for name, content in builder.expected_zip_entries(target).items()
            if name.startswith(prefix)
        }
    else:
        entries = builder.chatgpt_upload_entries(target)

    mcp_files = {
        name: content
        for name, content in source.items()
        if name.endswith((".mcp.json", ".app.json")) or "mcp" in name.split("/")
    }
    assert mcp_files
    assert {name: entries[name] for name in mcp_files} == mcp_files
    servers = json.loads(entries[".mcp.json"])["mcpServers"]
    assert any(server.get("command") == "node" for server in servers.values())
    assert f"{product}Incidents" not in servers
    assert all(
        "url" not in server and "serverUrl" not in server for server in servers.values()
    )
    source_declarations = {
        name: {
            key: value
            for key, value in json.loads(content).items()
            if key in {"mcpServers", "apps"}
        }
        for name, content in source.items()
        if name.endswith(".codex-plugin/plugin.json")
    }
    assert {
        name: {
            key: value
            for key, value in json.loads(entries[name]).items()
            if key in {"mcpServers", "apps"}
        }
        for name in source_declarations
    } == source_declarations
    assert not any(name.endswith("scripts/review_mcp_server.cjs") for name in entries)
