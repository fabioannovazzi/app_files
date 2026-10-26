"""Keep every host's public entry and private discovery catalogue aligned."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_claude_plugin_zip as cowork
from scripts import build_codex_plugin_zip as codex

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("host", ["codex", "cowork"])
def test_product_package_preserves_tools_behind_one_shared_entry(product, host):
    if host == "codex":
        package = codex.select_packages(
            codex.load_packages(), codex.load_bundles(), [product]
        )[0]
        prefix = f"{package.package_root}/plugins/{product}/"
        entries = {
            name.removeprefix(prefix): content
            for name, content in codex.expected_zip_entries(package).items()
            if name.startswith(prefix)
        }
    else:
        _, packages = cowork.load_configuration()
        package = next(p for p in packages if p.plugin == product)
        entries = cowork.claude_package_entries(package)
    servers = json.loads(entries[".mcp.json"])["mcpServers"]
    services = json.loads(entries["mcp-services.json"])["mcpServers"]
    catalog = json.loads(entries["mcp-catalog.json"])
    source = json.loads((ROOT / f"plugins/{product}/mcp-services.json").read_text())[
        "mcpServers"
    ]

    assert set(servers) == {product}
    assert servers[product]["command"] == "node"
    assert servers[product]["args"][0].endswith("/scripts/on_demand_mcp.cjs")
    assert set(services) == set(source) - (
        {"courseChats"} if host == "cowork" else set()
    )
    assert catalog["product"] == product
    assert {service["name"] for service in catalog["services"]} == set(services)
    assert all(service["tools"] for service in catalog["services"])
    for helper in (
        "on_demand_mcp.cjs",
        "mcp_service_client.cjs",
        "verify_mcp_package.cjs",
    ):
        assert (
            entries[f"scripts/{helper}"]
            == (ROOT / "plugins/vera/scripts" / helper).read_bytes()
        )
    if product == "lucia":
        tools = [
            tool["name"] for service in catalog["services"] for tool in service["tools"]
        ]
        assert "studio_archive_status" in tools
        assert "lucia_assurance_studio_archive_status" in tools
        assert len(tools) == len(set(tools))
        assert services["luciaStudioArchive"]["env"]["LUCIA_ASSURANCE_HOST"] == "1"
