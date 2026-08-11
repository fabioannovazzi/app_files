from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
LUCIA_ROOT = ROOT / "plugins" / "lucia"
LUCIA_ZIP = ROOT / "plugin_packages" / "lucia" / "lucia-plugin.zip"
VERA_ZIP = ROOT / "plugin_packages" / "vera" / "vera-plugin.zip"
PUBLIC_WORKFLOWS = {"prompt-optimizer", "deep-research-validator"}


def _json(path: Path) -> dict[str, object]:
    """Read one JSON object from the repository."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _component_entries(
    archive: ZipFile,
    *,
    package_root: str,
    plugin: str,
    component: str,
) -> dict[str, bytes]:
    """Return component files keyed by package-independent relative path."""

    prefix = f"{package_root}/plugins/{plugin}/modules/{component}/"
    return {
        name.removeprefix(prefix): archive.read(name)
        for name in archive.namelist()
        if name.startswith(prefix) and not name.endswith("/")
    }


def _node_executable() -> str | None:
    """Return an available Node runtime for the MCP smoke test."""

    system_node = shutil.which("node")
    if system_node:
        return system_node
    bundled = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    )
    return str(bundled) if bundled.is_file() else None


def _javascript_string_values(source: str, key: str) -> list[str]:
    """Return decoded values assigned to one quoted JavaScript object key."""

    pattern = rf'"{re.escape(key)}":\s*"((?:\\.|[^"\\])*)"'
    return [json.loads(f'"{value}"') for value in re.findall(pattern, source)]


def test_lucia_manifest_is_italian_and_does_not_freeze_catalog_size() -> None:
    manifest = _json(LUCIA_ROOT / ".codex-plugin" / "plugin.json")
    interface = manifest["interface"]

    assert manifest["name"] == "lucia"
    assert manifest["version"] == "0.1.1"
    assert interface["displayName"] == "Lucia"
    assert interface["developerName"] == "Fabio Annovazzi · Mparanza"
    assert interface["shortDescription"] == "Assistente AI x avvocati"
    assert len(interface["defaultPrompt"]) == 3
    assert all(len(prompt) <= 128 for prompt in interface["defaultPrompt"])
    assert "avvocati indipendenti" in interface["longDescription"]
    assert "Lucia mostra fonti" in interface["longDescription"]
    assert "esattamente due" not in interface["longDescription"]
    assert "prima versione" not in interface["longDescription"]


def test_lucia_current_catalog_has_two_public_workflows_and_one_hidden_runtime() -> (
    None
):
    components = _json(LUCIA_ROOT / "components.json")
    roles = components["workflow_roles"]
    skill_names = {
        path.parent.name for path in (LUCIA_ROOT / "skills").glob("*/SKILL.md")
    }
    cards = _json(LUCIA_ROOT / "marketplace_skill_instructions.json")["skills"]

    assert set(components["plugins"]) == PUBLIC_WORKFLOWS | {"studio-archive"}
    assert {
        name for name, role in roles.items() if role["kind"] == "public_workflow"
    } == (PUBLIC_WORKFLOWS)
    assert roles["studio-archive"] == {
        "kind": "internal_runtime",
        "supports": ["prompt-optimizer", "deep-research-validator"],
    }
    assert skill_names == PUBLIC_WORKFLOWS | {"lucia"}
    assert set(cards) == PUBLIC_WORKFLOWS | {"lucia"}
    assert "studio-archive" not in cards


@pytest.mark.parametrize("workflow", sorted(PUBLIC_WORKFLOWS))
def test_lucia_wrappers_resolve_canonical_shared_component(workflow: str) -> None:
    wrapper = (LUCIA_ROOT / "skills" / workflow / "SKILL.md").read_text(
        encoding="utf-8"
    )
    normalized_wrapper = " ".join(wrapper.split())

    assert f"../../modules/{workflow}" in wrapper
    assert f"../../../{workflow}" in wrapper
    assert f"`skills/{workflow}/SKILL.md`" in wrapper
    assert "Do not paraphrase, shorten, fork, or replace" in normalized_wrapper
    assert "deliverables are in Italian" in wrapper


@pytest.mark.parametrize("component", sorted(PUBLIC_WORKFLOWS))
def test_lucia_and_vera_package_the_same_assurance_component_bytes(
    component: str,
) -> None:
    with ZipFile(VERA_ZIP) as vera_archive, ZipFile(LUCIA_ZIP) as lucia_archive:
        vera_entries = _component_entries(
            vera_archive,
            package_root="vera-codex-plugin",
            plugin="vera",
            component=component,
        )
        lucia_entries = _component_entries(
            lucia_archive,
            package_root="lucia-codex-plugin",
            plugin="lucia",
            component=component,
        )

    assert vera_entries
    assert lucia_entries == vera_entries


def test_lucia_private_runtime_exposes_no_archive_or_communication_tools() -> None:
    node = _node_executable()
    if node is None:
        pytest.skip("Node is unavailable for the MCP smoke test")
    requests = "\n".join(
        (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                }
            ),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "search_studio_archive",
                        "arguments": {"query": "x", "scope_id": "all"},
                    },
                }
            ),
        )
    )

    completed = subprocess.run(
        [node, str(LUCIA_ROOT / "scripts" / "assurance_runtime_mcp.cjs")],
        cwd=LUCIA_ROOT,
        input=f"{requests}\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    responses = {
        payload["id"]: payload
        for line in completed.stdout.splitlines()
        for payload in [json.loads(line)]
        if "id" in payload
    }
    listed_tools = responses[2]["result"]["tools"]
    listed_names = {tool["name"] for tool in listed_tools}
    prepare_tool = next(
        tool
        for tool in listed_tools
        if tool["name"] == "prepare_studio_client_workflow"
    )

    assert completed.returncode == 0, completed.stderr
    assert responses[1]["result"]["serverInfo"]["name"] == ("lucia-assurance-runtime")
    assert responses[3]["error"]["message"] == "Tool not available in Lucia."
    assert {
        "search_studio_archive",
        "open_studio_archive_source",
        "plan_studio_archive_gmail_search",
        "match_studio_archive_email",
        "bind_studio_client_google_drive",
        "snapshot_studio_client_google_drive",
        "open_studio_google_drive_source",
    }.isdisjoint(listed_names)
    assert set(prepare_tool["inputSchema"]["properties"]["workflow_id"]["enum"]) == (
        PUBLIC_WORKFLOWS
    )


def test_lucia_submission_fixture_has_five_positive_and_three_negative_cases() -> None:
    submission = _json(LUCIA_ROOT / "evals" / "submission_cases.json")
    triggers = _json(LUCIA_ROOT / "evals" / "trigger_fixtures.json")

    assert len(submission["positive"]) == 5
    assert len(submission["negative"]) == 3
    assert len(triggers["should_trigger"]) >= 5
    assert len(triggers["should_not_trigger"]) >= 3


def test_lucia_marketplace_cards_use_vera_canonical_assurance_copy() -> None:
    lucia_cards = _json(LUCIA_ROOT / "marketplace_skill_instructions.json")["skills"]
    vera_cards = _json(
        ROOT / "plugins" / "vera" / "marketplace_skill_instructions.json"
    )["skills"]

    for workflow in PUBLIC_WORKFLOWS:
        for field in ("display_name", "short_description", "default_prompt"):
            assert lucia_cards[workflow][field] == vera_cards[workflow][field]
        assert lucia_cards[workflow]["instructions"] == vera_cards[workflow][
            "instructions"
        ].replace("Vera", "Lucia")


def test_lucia_chatgpt_upload_matches_current_public_catalog() -> None:
    upload = ROOT / "plugin_packages" / "lucia" / "lucia-chatgpt-upload.zip"

    with ZipFile(upload) as archive:
        names = set(archive.namelist())
        components = json.loads(archive.read("components.json"))

    assert set(components["plugins"]) == PUBLIC_WORKFLOWS
    assert set(components["workflow_roles"]) == PUBLIC_WORKFLOWS
    assert not any(name.startswith("modules/studio-archive/") for name in names)
    assert any(name.startswith("modules/prompt-optimizer/") for name in names)
    assert any(name.startswith("modules/deep-research-validator/") for name in names)


def test_lucia_public_page_uses_vera_canonical_assurance_copy() -> None:
    page = (ROOT / "static" / "shared" / "lucia" / "index.html").read_text(
        encoding="utf-8"
    )
    stylesheet = (ROOT / "static" / "shared" / "lucia" / "lucia-page.css").read_text(
        encoding="utf-8"
    )

    assert '<html lang="it">' in page
    assert 'href="../product-navigation.css?v=' in page
    assert 'src="../product-navigation.js?v=' in page
    assert 'class="hero-install"' in page
    assert 'class="section-block" id="core"' in page
    assert 'class="workstreams"' in page
    assert 'class="module-directory"' in page
    assert page.count('class="module-row"') == len(PUBLIC_WORKFLOWS)
    assert 'class="assurance-sequence"' in page
    assert 'class="data-position__facts"' in page
    assert 'data-language-summary' in page
    for lang in ("it", "en", "fr", "de", "es"):
        assert f'hreflang="{lang}"' in page
        assert f'data-lang="{lang}"' in page
    assert "Prompt Optimizer" in page
    assert "Deep Research Validator" in page
    assert "Ottimizza prompt" in page
    assert (
        "Trasforma un quesito legale, fiscale o di conformità in una ricerca con "
        "perimetro, fonti e verifiche definite."
    ) in page
    assert "Valida Deep Research" in page
    assert (
        "Controlla le affermazioni rispetto alle fonti citate e prepara il "
        "materiale consolidato."
    ) in page
    assert "Solo due" not in page
    assert "I due percorsi" not in page
    assert (
        "github.com/fabioannovazzi/app_files/tree/agent/lucia-public-page/plugins/lucia"
        in page
    )
    assert 'href="https://mparanza.com/support"' in page
    assert 'href="lucia-page.css?v=' in page
    assert 'src="icon.svg"' in page
    for selector in (
        ".hero-install",
        ".section-block",
        ".section-head",
        ".workstreams",
        ".module-directory",
        ".module-row",
        ".assurance-sequence",
    ):
        assert selector in stylesheet
    for color in ("#002060", "#0070c0", "#00b0f0", "#ffffff"):
        assert color in stylesheet
    assert "gradient" not in stylesheet
    assert "box-shadow" not in stylesheet


def test_lucia_public_page_matches_vera_function_copy_in_every_language() -> None:
    lucia_page = (ROOT / "static" / "shared" / "lucia" / "index.html").read_text(
        encoding="utf-8"
    )
    vera_page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    for key in (
        "module.prompt.title",
        "module.prompt",
        "module.research.title",
        "module.research",
    ):
        lucia_values = _javascript_string_values(lucia_page, key)
        vera_values = _javascript_string_values(vera_page, key)
        assert len(lucia_values) == 5
        assert lucia_values == vera_values


def test_lucia_marketplace_long_description_matches_manifest() -> None:
    manifest = _json(LUCIA_ROOT / ".codex-plugin" / "plugin.json")
    approved = (
        (ROOT / "docs" / "marketplace_copy" / "lucia-long-description.txt")
        .read_text(encoding="utf-8")
        .strip()
    )

    assert manifest["interface"]["longDescription"] == approved
    assert len(approved.split("\n\n")) == 3
    assert len(approved.split()) <= 120
