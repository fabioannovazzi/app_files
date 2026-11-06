"""Mechanical edition boundaries: no unavailable workflows or registrations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from scripts import build_codex_plugin_zip as builder
from scripts.lucia_distribution import MARKETPLACE_WORKFLOWS


@pytest.fixture(scope="module")
def marketplace():
    package = next(p for p in builder.load_packages() if p.plugin == "lucia")
    return builder.chatgpt_upload_entries(package, edition="marketplace")


def test_marketplace_exposes_only_retained_skills_and_no_registrations(marketplace):
    skills = {
        name.split("/")[1]
        for name in marketplace
        if name.startswith("skills/") and name.endswith("/SKILL.md")
    }
    assert skills == MARKETPLACE_WORKFLOWS | {"lucia"}
    assert not any(
        "mcp" in name.lower() for name in marketplace if not name.startswith("privacy/")
    )
    assert not any(name.endswith(".app.json") for name in marketplace)
    assert json.loads(marketplace["components.json"])["plugins"] == []
    manifest = json.loads(marketplace[".codex-plugin/plugin.json"])
    assert not {"mcpServers", "hooks", "apps"} & manifest.keys()
    assert manifest["requires_local_executor"] is True
    portable = json.loads(marketplace["plugin.json"])
    assert portable["extensions"]["com.openai"]["requires_local_executor"] is True


def test_marketplace_routes_and_reporting_do_not_call_absent_native_tools(marketplace):
    instructions = "\n".join(
        value.decode()
        for path, value in marketplace.items()
        if path.startswith("skills/")
        and path.endswith(".md")
        and "/upstream/" not in path
    )
    assert "lucia_incident_host_link" not in instructions
    assert "lucia_method_open" not in instructions
    assert "lucia_workflow_usage" not in instructions
    assert "../metodo-studio/SKILL.md" not in instructions
    assert "../posizioni-negoziali/SKILL.md" not in instructions
    assert "scripts/workflow_usage.py build-report" in instructions
    assert "scripts/legal_documents.py" in instructions


def test_marketplace_keeps_current_document_engine_bytes(marketplace):
    assert (
        marketplace["scripts/legal_documents.py"]
        == (ROOT / "plugins/lucia/scripts/legal_documents.py").read_bytes()
    )
    assert (
        marketplace["scripts/legal_proofreading.py"]
        == (ROOT / "plugins/lucia/scripts/legal_proofreading.py").read_bytes()
    )
    assert (
        marketplace["scripts/legal_matter.py"]
        == (ROOT / "plugins/lucia/scripts/legal_matter.py").read_bytes()
    )


def test_marketplace_privacy_registry_covers_exact_exposed_scope(marketplace):
    registry = json.loads(marketplace["privacy/registry.json"])
    assert set(registry["workstreams"]) == MARKETPLACE_WORKFLOWS | {"lucia"}
    assert "on-demand-mcp" not in registry["services"]
    assert "prepared-course-files" not in registry["services"]
    assert (
        set(json.loads(marketplace["usage/pipelines.json"])["pipelines"])
        == MARKETPLACE_WORKFLOWS
    )


def test_reduced_edition_cannot_silently_strip_clara():
    package = next(p for p in builder.load_packages() if p.plugin == "clara")
    with pytest.raises(ValueError, match="Lucia-specific"):
        builder.chatgpt_upload_entries(package, edition="marketplace")


def test_marketplace_relative_skill_routes_resolve_to_packaged_skills(marketplace):
    import re

    for name, content in marketplace.items():
        if (
            not name.startswith("skills/")
            or not name.endswith(".md")
            or "/upstream/" in name
        ):
            continue
        for target in re.findall(r"`((?:\.\./)+[^`]+/SKILL\.md)`", content.decode()):
            resolved = (
                (Path("/package") / Path(name).parent / target)
                .resolve()
                .relative_to("/package")
                .as_posix()
            )
            assert resolved in marketplace, f"{name} routes to missing {resolved}"


def test_lucia_full_omits_unusable_development_and_vera_only_drivers():
    package = next(p for p in builder.load_packages() if p.plugin == "lucia")
    entries = builder.source_zip_entries(package)
    assert not any("/modules/apertura-pratica/tests/" in name for name in entries)
    assert not any(name.endswith("/open_items_source_preflight.py") for name in entries)
    assert not any(name.endswith("/reconcile_open_items.py") for name in entries)
    assert any(name.endswith("/scripts/lucia_studio_archive.py") for name in entries)
    assert any(name.endswith("/scripts/studio_archive.py") for name in entries)


def test_reduced_instructions_preserve_local_usage_and_new_run_contract(marketplace):
    usage = marketplace["skills/lucia/references/workflow-usage.md"].decode()
    assert "MPARANZA_INCIDENT_DELIVERY=local-only" in usage
    assert "start, record and" in usage
    workflow = marketplace[
        "skills/revisione-contratti/references/document-workflow.md"
    ].decode()
    assert "Do not create the run directory before prepare" in workflow
