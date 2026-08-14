from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build_claude_plugin_zip.py"
CLARA_SOURCE_MANIFEST = ROOT / "plugins" / "clara" / ".codex-plugin" / "plugin.json"
CLARA_CLAUDE_MANIFEST = ROOT / "plugins" / "clara" / ".claude-plugin" / "plugin.json"
EXPECTED_ROOT_SKILLS = {
    "attribute-reporting",
    "brand-fit",
    "claim-basis-map",
    "clara",
    "html-deck",
    "reporting-engine",
    "research-video",
}


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_clara_claude_plugin_zip",
        BUILD_SCRIPT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def configured_clara():
    builder = load_builder()
    marketplace, packages = builder.load_configuration()
    package = next(package for package in packages if package.plugin == "clara")
    return builder, marketplace, packages, package


@pytest.fixture(scope="module")
def clara_entries(configured_clara):
    builder, _, _, package = configured_clara
    return builder.claude_package_entries(package)


def test_clara_manifest_matches_canonical_identity_and_listing(clara_entries) -> None:
    source = json.loads(CLARA_SOURCE_MANIFEST.read_text(encoding="utf-8"))
    template = json.loads(CLARA_CLAUDE_MANIFEST.read_text(encoding="utf-8"))
    manifest = json.loads(clara_entries[".claude-plugin/plugin.json"])

    assert source["version"] == "0.1.150"
    assert template["version"] == manifest["version"] == "0.1.134"
    assert manifest["name"] == "clara"
    assert manifest["displayName"] == "Clara"
    assert manifest["homepage"].endswith("/clara/index.html?lang=en")
    assert manifest["description"].startswith("AI companion for consultants.")
    assert manifest["skills"] == "./skills/"
    assert manifest["agents"] == ["./agents/clara.md"]
    assert "interface" not in manifest
    assert manifest["hooks"] == "./hooks/hooks.json"
    assert "mcpServers" not in manifest


def test_clara_package_uses_claude_archive_name(configured_clara) -> None:
    _, _, _, package = configured_clara

    assert package.output_zip.name == "clara-claude-plugin.zip"


def test_clara_cowork_includes_claude_agent(clara_entries) -> None:
    agent = clara_entries["agents/clara.md"].decode("utf-8")

    assert "You are Clara" in agent
    assert "connected folder" in agent


def test_clara_cowork_retains_specialist_runtime_files(clara_entries) -> None:
    required_runtime_files = {
        "skills/claim-basis-map/scripts/render_claim_basis_map.py",
        "skills/html-deck/assets/deck-engine/deck.css",
        "skills/html-deck/scripts/build_html_deck.py",
        "skills/html-deck/scripts/validate_html_deck.py",
        "skills/research-video/scripts/research_video.py",
    }

    assert required_runtime_files <= set(clara_entries)
    assert not any("mcp" in Path(name).parts for name in clara_entries)


def test_clara_cowork_exposes_only_reviewed_root_skills(clara_entries) -> None:
    root_skills = {
        Path(name).parts[1]
        for name in clara_entries
        if name.startswith("skills/")
        and name.endswith("/SKILL.md")
        and len(Path(name).parts) == 3
    }

    assert root_skills == EXPECTED_ROOT_SKILLS
    for omitted in (
        "beautify-deck",
        "deck-correction",
        "interview",
        "privacy-surface-review",
        "transcribe",
    ):
        assert not any(name.startswith(f"skills/{omitted}/") for name in clara_entries)


def test_clara_cowork_includes_reviewed_feedback_and_omits_other_host_paths(
    clara_entries,
) -> None:
    forbidden_exact = {
        "scripts/check_for_update.py",
        "scripts/launch_hosted_voice.py",
        "scripts/manage_hosted_interview.py",
        "scripts/upload_hosted_audio.py",
    }

    assert forbidden_exact.isdisjoint(clara_entries)
    assert "scripts/change_requests.py" in clara_entries
    assert "scripts/check_change_requests.py" in clara_entries
    assert not any(name.startswith("privacy/") for name in clara_entries)
    assert not any(name.endswith("/agents/openai.yaml") for name in clara_entries)
    assert not any(".codex-plugin/" in name for name in clara_entries)
    assert not any(
        name.endswith((".app.json", ".mcp.json", ".pyc")) for name in clara_entries
    )
    assert not any("beautify" in name.lower() for name in clara_entries)


def test_clara_cowork_bootstraps_declared_python_dependencies(
    clara_entries,
) -> None:
    hooks = json.loads(clara_entries["hooks/hooks.json"])
    command_hooks = hooks["hooks"]["SessionStart"][0]["hooks"]

    assert command_hooks == [
        {
            "type": "command",
            "command": (
                'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/'
                'bootstrap_python_dependencies.py"'
            ),
            "timeout": 240,
        },
        {
            "type": "command",
            "command": (
                'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_change_requests.py"'
            ),
            "timeout": 10,
        },
    ]
    assert "scripts/bootstrap_python_dependencies.py" in clara_entries
    requirements = clara_entries["requirements.txt"].decode("utf-8")
    assert "-r modules/reporting-engine/requirements.txt" in requirements
    reporting_requirements = clara_entries[
        "modules/reporting-engine/requirements.txt"
    ].decode("utf-8")
    assert "polars>=1.0" in reporting_requirements


def test_clara_cowork_vendors_every_registered_analysis_component(
    clara_entries,
) -> None:
    components = json.loads(
        (ROOT / "plugins" / "clara" / "components.json").read_text(encoding="utf-8")
    )["plugins"]

    for component in components:
        assert any(
            name.startswith(f"modules/{component}/") for name in clara_entries
        ), component


def test_clara_cowork_instructions_are_host_neutral(clara_entries) -> None:
    instruction_docs = {
        name: content.decode("utf-8")
        for name, content in clara_entries.items()
        if (
            name.endswith("/SKILL.md")
            or Path(name).name == "README.md"
            or ("/references/" in name and name.endswith(".md"))
        )
    }
    combined = "\n".join(instruction_docs.values())

    assert (
        "This package is for Claude Cowork" in instruction_docs["skills/clara/SKILL.md"]
    )
    assert "image-generation capability" in instruction_docs["skills/clara/SKILL.md"]
    assert "## Plugin Improvement Feedback" in instruction_docs["skills/clara/SKILL.md"]
    assert "If the occurred time" in instruction_docs["skills/clara/SKILL.md"]
    assert "submit-problem" in instruction_docs["skills/clara/SKILL.md"]
    assert "Professional capability gap" in instruction_docs["skills/clara/SKILL.md"]
    assert (
        "Clara workflow: clara:<specialist-skill>"
        in instruction_docs["skills/clara/SKILL.md"]
    )
    assert "skills/clara/references/workflow-catalog.md" not in clara_entries
    for marker in (
        "ChatGPT",
        "Codex",
        "OpenAI",
        "developers.openai.com",
        "beautify-deck",
        "Beautify Deck",
        "`deck-correction`",
        "`interview`",
        "`transcribe`",
    ):
        assert marker not in combined


def test_clara_cowork_directory_and_zip_are_deterministic(
    configured_clara,
    tmp_path: Path,
) -> None:
    builder, _, _, package = configured_clara
    isolated = replace(
        package,
        output_directory=tmp_path / "clara",
        output_zip=tmp_path / "clara-claude-plugin.zip",
    )

    builder.build_package(isolated)
    first_zip = isolated.output_zip.read_bytes()
    builder.build_package(isolated)

    assert isolated.output_zip.read_bytes() == first_zip
    assert builder.verify_package(isolated) == []
    with ZipFile(isolated.output_zip) as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
        assert archive.testzip() is None
    assert names == set(builder.claude_package_entries(isolated))


def test_marketplace_catalog_contains_configured_plugins(configured_clara) -> None:
    builder, marketplace, packages, package = configured_clara
    catalog = json.loads(builder.catalog_payload(marketplace, packages))
    entries = {entry["name"]: entry for entry in catalog["plugins"]}

    assert set(entries) == {"clara", "lucia", "vera"}
    assert entries["clara"]["source"] == "./plugin_packages/clara/claude/clara"
    assert entries["clara"]["version"] == "0.1.134"
    assert entries["clara"]["strict"] is True
    assert "version" not in catalog
    assert builder.verify_package(package) == []
