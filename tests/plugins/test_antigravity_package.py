"""The public Antigravity ZIP must retain its source bytes and exact version."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest


def builder_case(tmp_path: Path, monkeypatch):
    """Provide a small package and replace process startup with a local stub."""
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    builder = importlib.import_module("build_antigravity_plugin")
    entries = {
        "vera/.codex-plugin/plugin.json": b'{"name":"vera","version":"0.1.333"}',
        "vera/skills/vera/SKILL.md": b"source skill",
        "vera/mcp_config.json": b'{"mcpServers":{"test":{"command":"node"}}}',
    }
    monkeypatch.setattr(builder, "package_entries", lambda product: entries)
    monkeypatch.setattr(builder, "verify_packaged_mcp", lambda *args, **kwargs: [])
    output = tmp_path / "vera.zip"
    metadata = tmp_path / "vera.json"
    builder.build_package(output, metadata)
    return builder, output, metadata


def test_rebuild_produces_identical_download_and_matching_version(
    tmp_path, monkeypatch
):
    builder, output, metadata = builder_case(tmp_path, monkeypatch)
    previous = output.read_bytes()

    builder.build_package(output, metadata)

    assert output.read_bytes() == previous
    assert json.loads(metadata.read_text()) == {"name": "vera", "version": "0.1.333"}


def test_check_rejects_modified_skill_even_with_same_version(tmp_path, monkeypatch):
    builder, output, metadata = builder_case(tmp_path, monkeypatch)
    with ZipFile(output) as archive:
        manifest = archive.read("vera/.codex-plugin/plugin.json")
        mcp_config = archive.read("vera/mcp_config.json")
    with ZipFile(output, "w") as archive:
        archive.writestr("vera/.codex-plugin/plugin.json", manifest)
        archive.writestr("vera/mcp_config.json", mcp_config)
        archive.writestr("vera/skills/vera/SKILL.md", "stale skill")

    with pytest.raises(ValueError, match="verification failed"):
        builder.verify_package(output, metadata)


def test_check_rejects_incorrect_website_version(tmp_path, monkeypatch):
    builder, output, metadata = builder_case(tmp_path, monkeypatch)
    metadata.write_text('{"name":"vera","version":"0.1.268"}')

    with pytest.raises(ValueError, match="download version does not match"):
        builder.verify_package(output, metadata)


def test_check_exercises_antigravity_config_and_rejects_broken_server(
    tmp_path, monkeypatch
):
    builder, output, metadata = builder_case(tmp_path, monkeypatch)

    def broken_server(path, roots, config_name):
        assert config_name == "mcp_config.json"
        return ["server failed to start"]

    monkeypatch.setattr(builder, "verify_packaged_mcp", broken_server)

    with pytest.raises(ValueError, match="server failed to start"):
        builder.verify_package(output, metadata)


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_projection_keeps_canonical_skills_agent_and_host_configuration(
    product, monkeypatch
):
    """Each host package must carry the product's own source and runnable paths."""
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    builder = importlib.import_module("build_antigravity_plugin")
    root = Path(__file__).resolve().parents[2]

    entries = builder.package_entries(product)

    assert json.loads(entries[f"{product}/plugin.json"])["name"] == product
    assert (
        entries[f"{product}/skills/{product}/SKILL.md"]
        == (root / f"plugins/{product}/skills/{product}/SKILL.md").read_bytes()
    )
    assert (
        entries[f"{product}/agents/{product}.md"]
        == (root / f"plugins/{product}/agents/{product}.md").read_bytes()
    )
    assert f"{product}/.app.json" not in entries
    assert f"{product}/hooks/hooks.json" not in entries
    assert f"{product}/.mcp.json" not in entries
    assert (
        f"agy --agent {product}"
        in entries[f"{product}/LEGGIMI_ANTIGRAVITY.txt"].decode()
    )
    source_config = root / f"plugins/{product}/.mcp.json"
    expected_servers = (
        json.loads(source_config.read_text())["mcpServers"]
        if source_config.exists()
        else {}
    )
    packaged_servers = json.loads(entries[f"{product}/mcp_config.json"])["mcpServers"]
    assert packaged_servers == {
        name: {key: value for key, value in config.items() if key in builder.MCP_FIELDS}
        for name, config in expected_servers.items()
    }


@pytest.mark.parametrize("product", ["clara", "lucia"])
def test_product_pages_offer_download_metadata_and_installation_guide(product):
    from bs4 import BeautifulSoup

    root = Path(__file__).resolve().parents[2] / "static/shared" / product
    page = BeautifulSoup((root / "index.html").read_text(), "html.parser")
    guide = BeautifulSoup((root / "antigravity/index.html").read_text(), "html.parser")

    assert (
        page.select_one('[data-i18n="install.antigravity.download"]')["href"]
        == f"downloads/{product}-antigravity-plugin.zip"
    )
    assert page.select_one("[data-antigravity-guide-link]")["href"].startswith(
        "antigravity/index.html?lang="
    )
    assert page.select_one("[data-antigravity-version]") is not None
    assert (
        guide.select_one('[data-copy="download"]')["href"]
        == f"../downloads/{product}-antigravity-plugin.zip"
    )
    assert f"~/.gemini/config/plugins/{product}" in guide.select_one("textarea").text
    assert f"agy --agent {product}" in guide.get_text()


def test_clara_projection_preserves_deck_support_files(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    builder = importlib.import_module("build_antigravity_plugin")
    root = Path(__file__).resolve().parents[2]

    entries = builder.package_entries("clara")

    assert (
        entries["clara/docs/specs/pptx_templates/ag-style-spec.md"]
        == (root / "docs/specs/pptx_templates/ag-style-spec.md").read_bytes()
    )
    assert (
        entries["clara/.agents/skills/advisory-output-shaper/SKILL.md"]
        == (root / ".agents/skills/advisory-output-shaper/SKILL.md").read_bytes()
    )
