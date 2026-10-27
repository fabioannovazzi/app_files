"""Keep every host's public entry and private discovery catalogue aligned."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_claude_plugin_zip as cowork
from scripts import build_codex_plugin_zip as codex

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


def _package_entries(product, host):
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
    return entries


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("host", ["codex", "cowork"])
def test_product_package_preserves_tools_behind_one_shared_entry(product, host):
    entries = _package_entries(product, host)
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


@pytest.mark.parametrize("host", ["codex", "cowork"])
@pytest.mark.parametrize("product", ["vera", "lucia"])
def test_answer_panel_removed_only_from_vera_discovery(product, host):
    entries = _package_entries(product, host)
    catalog = json.loads(entries["mcp-catalog.json"])
    tool_names = {
        tool["name"] for service in catalog["services"] for tool in service["tools"]
    }
    panel_tools = {
        "validate_deep_research_review",
        "render_deep_research_review",
        "save_deep_research_decisions",
        "apply_deep_research_decisions",
    }

    assert tool_names & panel_tools == (set() if product == "vera" else panel_tools)
    assert ("ui://widget/deep-research-review.html" in json.dumps(catalog)) == (
        product == "lucia"
    )
    assert "render_prompt_optimizer_review" in tool_names
    assert entries["modules/deep-research-validator/scripts/package_validation.py"]
    assert entries["modules/deep-research-validator/scripts/research_record.py"]
    assert entries["modules/deep-research-validator/scripts/adversarial_opinion.py"]


@pytest.mark.parametrize("host", ["codex", "cowork", "chatgpt"])
def test_every_vera_opinion_entry_keeps_delivery_policy_in_package(host):
    if host == "chatgpt":
        package = codex.select_packages(
            codex.load_packages(), codex.load_bundles(), ["vera"]
        )[0]
        entries = codex.chatgpt_upload_entries(package)
    else:
        entries = _package_entries("vera", host)
    # Cowork may rename registered skill folders while preserving relative links.
    policy_paths = [p for p in entries if p.endswith("/references/opinion-delivery.md")]
    assert len(policy_paths) == 1
    policy = entries[policy_paths[0]].decode()
    assert "Do not create, open or recreate an answer-review panel" in policy
    for skill in (
        "deep-research",
        "legal-tax-answer-review",
        "adversarial-opinion",
    ):
        matches = [
            p
            for p in entries
            if p.startswith("skills/") and p.endswith(f"{skill}/SKILL.md")
        ]
        assert len(matches) == 1
        text = entries[matches[0]].decode()
        assert "/references/opinion-delivery.md" in text
        assert "replaces all shared panel and review-queue handoffs" in text
