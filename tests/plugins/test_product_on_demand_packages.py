"""Keep every host's public entry and private discovery catalogue aligned."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import build_claude_plugin_zip as cowork
from scripts import build_codex_plugin_zip as codex
from tests.plugins.test_product_on_demand_mcp import Session

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


@pytest.mark.parametrize("host", ["codex", "cowork"])
def test_chat_only_archive_pin_opens_native_incarico_and_preserves_default(
    tmp_path, monkeypatch, host
):
    """The packaged front door shares one pin without leaking it to another chat."""
    plugin = tmp_path / "plugin"
    for relative, content in _package_entries("vera", host).items():
        path = plugin / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    for name in (
        "CODEX_THREAD_ID",
        "VERA_STUDIO_ARCHIVE_SESSION_ID",
        "VERA_WORKSPACE_BINDINGS",
        "VERA_WORKSPACE_ACTOR_ID",
        "VERA_WORKSPACE_TENANT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in {
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(tmp_path / "first-chat-state"),
        "VERA_STUDIO_ARCHIVE_PROFILE_DIR": str(tmp_path / "profile"),
        "VERA_STUDIO_ARCHIVE_PYTHON": sys.executable,
        "VERA_WORKSPACE_PYTHON": sys.executable,
        "VERA_REPORTING_STATE_DIR": str(tmp_path / "reporting"),
        "MPARANZA_INCIDENT_STATE_DIR": str(tmp_path / "incidents"),
        "MPARANZA_INCIDENT_DEVICE_DIR": str(tmp_path / "device"),
        "MPARANZA_INCIDENT_DELIVERY": "local-only",
    }.items():
        monkeypatch.setenv(name, value)

    def call(session, name, arguments):
        reply = session.call(
            "tools/call", {"name": name, "arguments": arguments}, timeout=90
        )
        assert "error" not in reply, reply
        result = reply["result"]
        assert not result.get("isError"), result
        return result

    permanent, temporary = tmp_path / "Permanent", tmp_path / "Temporary"
    permanent.mkdir()
    temporary.mkdir()
    active = Session(plugin)
    try:
        call(
            active,
            "configure_studio_archive",
            {"archive_root": str(permanent), "make_studio_default": True},
        )
        original = call(
            active,
            "create_studio_archive_client",
            {"legal_name": "Permanent synthetic client"},
        )
        original_id = original["structuredContent"]["client"]["client_id"]
        defaults = {
            p: p.read_bytes()
            for p in (tmp_path / "profile").rglob("approved-archive.json")
        }
        assert defaults
        call(
            active,
            "configure_studio_archive",
            {"archive_root": str(temporary), "make_studio_default": False},
        )
        created = call(
            active,
            "create_studio_archive_client",
            {"legal_name": "Temporary synthetic client"},
        )
        cid = created["structuredContent"]["client"]["client_id"]
        created = call(
            active,
            "create_studio_client_engagement",
            {"client_id": cid, "engagement_label": "Document-only assignment"},
        )
        eid = created["structuredContent"]["engagement"]["engagement_id"]
        native = call(
            active, "vera_workspace_open", {"client_id": cid, "engagement_id": eid}
        )
        assert native["_meta"]["workspace"]["incarico"]["engagement_id"] == eid
        assert native["_meta"]["workspace"]["client_id"] == cid
        assert {p: p.read_bytes() for p in defaults} == defaults
        monkeypatch.setenv(
            "VERA_STUDIO_ARCHIVE_STATE_DIR", str(tmp_path / "second-chat-state")
        )
        other = Session(plugin)
        try:
            visible = call(other, "list_studio_archive_clients", {})[
                "structuredContent"
            ]["clients"]
            assert {row["client_id"] for row in visible} == {original_id}
        finally:
            other.close()
    finally:
        active.close()


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
        assert "luciaAssuranceRuntime" not in services
        assert not any(name.startswith("lucia_assurance_") for name in tools)
        assert {
            "start_check_entries_from_sample",
            "verify_studio_run_report",
        }.isdisjoint(tools)
        archive = next(
            service
            for service in catalog["services"]
            if service["name"] == "luciaStudioArchive"
        )
        by_name = {tool["name"]: tool for tool in archive["tools"]}
        assert {
            "search_studio_archive",
            "open_studio_archive_organization_item",
            "snapshot_studio_client_google_drive",
            "finalize_studio_client_workflow",
        } <= by_name.keys()
        assert all(
            "Vera" not in tool["title"] + tool["description"]
            for tool in by_name.values()
        )
        assert set(
            by_name["prepare_studio_client_workflow"]["inputSchema"]["properties"][
                "workflow_id"
            ]["enum"]
        ) == {"prompt-optimizer", "deep-research-validator", "apertura-pratica"}
        assert len(tools) == len(set(tools))
        assert services["luciaStudioArchive"]["env"]["LUCIA_ASSURANCE_HOST"] == "1"


@pytest.mark.parametrize("host", ["codex", "cowork"])
@pytest.mark.parametrize("product", ["vera", "lucia"])
def test_retired_answer_inspectors_are_absent_and_engines_remain(product, host):
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

    assert tool_names & panel_tools == (
        set() if product == "vera" else panel_tools - {"render_deep_research_review"}
    )
    assert "ui://widget/deep-research-review.html" not in json.dumps(catalog)
    assert "validate_prompt_optimizer_review" in tool_names
    assert "render_prompt_optimizer_review" not in tool_names
    assert "ui://widget/prompt-optimizer-review.html" not in json.dumps(catalog)
    assert entries["modules/deep-research-validator/scripts/package_validation.py"]
    assert entries["modules/deep-research-validator/scripts/research_record.py"]
    assert entries["modules/deep-research-validator/scripts/adversarial_opinion.py"]


@pytest.mark.parametrize("host", ["codex", "cowork"])
def test_archive_directory_and_agenda_are_distinct_in_model_tool_discovery(host):
    entries = _package_entries("vera", host)
    catalog = json.loads(entries["mcp-catalog.json"])
    labels = {"Lavori dello studio", "Agenda dello studio"}
    advertised = [
        tool
        for service in catalog["services"]
        for tool in service["tools"]
        if tool.get("title") in labels and "model" in tool["_meta"]["ui"]["visibility"]
    ]

    assert sorted((tool["title"], tool["name"]) for tool in advertised) == [
        ("Agenda dello studio", "vera_studio_work_panel_open"),
        ("Lavori dello studio", "vera_workspace_open"),
    ]
    assert all(not tool["inputSchema"].get("required") for tool in advertised)
    assert len({tool["_meta"]["ui"]["resourceUri"] for tool in advertised}) == 2


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

    # The preparations must reach the visible chat policy on every host,
    # including when users enter research directly.
    assert "before the first\nsubstantive source lookup" in policy
    assert "question I’ll answer" in policy and "sources\nI’ll consult" in policy
    for name in ("quesito-legale-fiscale", "legal-tax-answer-planner"):
        paths = [
            path
            for path in entries
            if path.startswith("skills/") and path.endswith(f"{name}/SKILL.md")
        ]
        assert len(paths) == 1
        assert "/references/opinion-delivery.md" in entries[paths[0]].decode()
    root = [
        path
        for path in entries
        if path in {"skills/vera/SKILL.md", "skills/mparanza-vera/SKILL.md"}
    ]
    assert len(root) == 1
    root_text = entries[root[0]].decode()
    assert (
        "Before opening a supplied authority"
        in root_text.partition("## Work continuity")[0]
    )
    assert "scripts/opinion_validation.py" in entries
    assert "verify <review-directory>" in policy
