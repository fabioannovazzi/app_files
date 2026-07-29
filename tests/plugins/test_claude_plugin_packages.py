from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build_claude_plugin_zip.py"
VERA_SOURCE_MANIFEST = ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json"
VERA_CLAUDE_MANIFEST = ROOT / "plugins" / "vera" / ".claude-plugin" / "plugin.json"
VERA_PRIVACY_VALIDATOR = (
    ROOT
    / "plugins"
    / "vera"
    / "skills"
    / "privacy-surface-review"
    / "scripts"
    / "validate_privacy_surfaces.py"
)


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_claude_plugin_zip",
        BUILD_SCRIPT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_privacy_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_projected_cowork_privacy",
        VERA_PRIVACY_VALIDATOR,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def configured():
    builder = load_builder()
    marketplace, packages = builder.load_configuration()
    assert [package.plugin for package in packages] == ["vera", "clara"]
    vera_package = next(package for package in packages if package.plugin == "vera")
    return builder, marketplace, vera_package


@pytest.fixture(scope="module")
def vera_entries(configured):
    builder, _, package = configured
    return builder.claude_package_entries(package)


@pytest.fixture(scope="module")
def cowork_instruction_docs(vera_entries):
    return {
        name: content.decode("utf-8")
        for name, content in vera_entries.items()
        if (
            name.endswith("/SKILL.md")
            or Path(name).name == "README.md"
            or ("/references/" in name and name.endswith(".md"))
        )
    }


def test_claude_manifest_uses_canonical_vera_identity_and_version(
    vera_entries,
) -> None:
    source = json.loads(VERA_SOURCE_MANIFEST.read_text(encoding="utf-8"))
    template = json.loads(VERA_CLAUDE_MANIFEST.read_text(encoding="utf-8"))
    manifest = json.loads(vera_entries[".claude-plugin/plugin.json"])

    assert manifest["version"] == "0.1.60"
    assert "modules/new-client/scripts/delivery_manifest.py" in vera_entries
    assert manifest == {
        "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
        "name": template["name"],
        "displayName": template["displayName"],
        "version": source["version"],
        "description": template["description"],
        "author": template["author"],
        "homepage": template["homepage"],
        "repository": template["repository"],
        "license": template["license"],
        "keywords": template["keywords"],
        "skills": "./skills/",
        "agents": template["agents"],
    }
    assert "agents/vera.md" in vera_entries
    assert "interface" not in manifest
    assert "apps" not in manifest
    assert "hooks" not in manifest
    assert "mcpServers" not in manifest


def test_only_root_anthropic_manifest_is_discoverable_and_root_app_is_omitted(
    vera_entries,
) -> None:
    claude_manifests = sorted(
        name for name in vera_entries if name.endswith(".claude-plugin/plugin.json")
    )
    app_descriptors = sorted(
        name for name in vera_entries if name.endswith(".app.json")
    )

    assert claude_manifests == [".claude-plugin/plugin.json"]
    assert ".app.json" not in vera_entries
    assert app_descriptors
    assert all(name.startswith("modules/") for name in app_descriptors)
    assert "hooks/hooks.json" not in vera_entries
    assert "scripts/check_for_update.py" not in vera_entries
    assert "scripts/change_requests.py" not in vera_entries
    assert "scripts/run_component_mcp.cjs" not in vera_entries
    assert ".mcp.json" not in vera_entries
    assert "skills/vera/references/cowork-runtime.md" not in vera_entries
    assert "skills/studio-archive/references/cowork-runtime.md" not in vera_entries
    assert "skills/studio-archive/references/marketplace-gmail.md" not in vera_entries
    assert "skills/studio-archive/references/whatsapp-desktop.md" not in vera_entries
    assert not any(name.startswith("modules/studio-archive/") for name in vera_entries)
    assert (
        "modules/previdenza-inps/scripts/capture_portal_snapshot.py" not in vera_entries
    )
    assert not any(
        name.startswith("skills/privacy-surface-review/") for name in vera_entries
    )
    assert not any(name.startswith("evals/") for name in vera_entries)
    assert not any(
        name.startswith("modules/")
        and any(
            part in {"evals", "tests", "__pycache__"} for part in Path(name).parts[2:]
        )
        for name in vera_entries
    )
    assert not any(name.endswith(".pyc") for name in vera_entries)
    assert (
        "modules/client-file-preparation/INSTALLA_PLUGIN_CODEX.md" not in vera_entries
    )
    assert "modules/client-file-preparation/COME_USARE_LO_ZIP.md" not in vera_entries
    assert not any(name.startswith("submission/") for name in vera_entries)
    assert not any(name.startswith("samples/") for name in vera_entries)


def test_optional_claude_mcp_projection_uses_only_installation_safe_paths() -> None:
    builder = load_builder()
    payload = json.loads(
        builder.project_claude_mcp(
            (ROOT / "plugins" / "vera" / ".mcp.json").read_bytes()
        )
    )
    servers = payload["mcpServers"]

    assert len(servers) == 15
    for server in servers.values():
        assert set(server) <= {"command", "args", "env"}
        assert server["command"] == "node"
        assert server["args"][0] == (
            "${CLAUDE_PLUGIN_ROOT}/scripts/run_component_mcp.cjs"
        )
        assert len(server["args"]) == 2
        assert "cwd" not in server
        assert "icons" not in server
        assert "title" not in server
        assert "description" not in server


def test_claude_package_vendors_every_registered_vera_component(
    vera_entries,
) -> None:
    components = json.loads(
        (ROOT / "plugins" / "vera" / "components.json").read_text(encoding="utf-8")
    )["plugins"]

    for component in components:
        component_prefix = f"modules/{component}/"
        if component == "studio-archive":
            assert not any(name.startswith(component_prefix) for name in vera_entries)
            assert "skills/studio-archive/SKILL.md" in vera_entries
            continue
        assert any(name.startswith(component_prefix) for name in vera_entries)
        descriptors = {
            f"{component_prefix}.app.json",
            f"{component_prefix}.codex-plugin/plugin.json",
            f"{component_prefix}.mcp.json",
        }
        if component in {
            "check-entries",
            "concordato-plan-review",
            "journal-bank-reconciliation",
            "journal-sampling",
            "report-builder",
        }:
            assert descriptors <= set(vera_entries)
        else:
            assert descriptors.isdisjoint(vera_entries)
    assert "scripts/check_dependencies.py" in vera_entries
    assert any(
        name.startswith("modules/") and "/scripts/" in name for name in vera_entries
    )
    assert "agents/vera.md" in vera_entries
    assert not any(
        name.startswith("modules/") and "/hooks/" in name for name in vera_entries
    )
    assert not any(
        name.startswith("modules/") and Path(name).name == "README.md"
        for name in vera_entries
    )
    projected_components = json.loads(vera_entries["components.json"].decode("utf-8"))[
        "plugins"
    ]
    assert "studio-archive" not in projected_components
    assert set(projected_components) == set(components) - {"studio-archive"}


def test_cowork_privacy_register_omits_unavailable_routes(vera_entries) -> None:
    projected_components = json.loads(vera_entries["components.json"])

    assert projected_components["shared_services"] == []
    assert not any(name.startswith("privacy/services/") for name in vera_entries)
    assert "privacy/workstreams/studio-archive.json" not in vera_entries


def test_cowork_privacy_register_validates_projected_bytes(
    vera_entries,
    tmp_path: Path,
) -> None:
    projected_root = tmp_path / "vera"
    for name, content in vera_entries.items():
        destination = projected_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    validator = load_privacy_validator()

    assert validator.validate_privacy_surfaces(projected_root) == []


def test_codex_projection_excludes_every_cowork_only_source(configured) -> None:
    builder, _, package = configured
    codex_builder = builder._load_codex_builder()
    target = builder._source_build_target(package)
    entries = codex_builder.expected_zip_entries(target)
    prefix = f"{target.package_root}/plugins/vera/"
    relative_names = {
        name.removeprefix(prefix) for name in entries if name.startswith(prefix)
    }

    assert not any(name.startswith(".claude-plugin/") for name in relative_names)
    assert not any(name.startswith("agents/") for name in relative_names)
    assert not any(name.startswith("submission/") for name in relative_names)
    assert not any(name.startswith("samples/cowork/") for name in relative_names)
    assert "skills/vera/references/cowork-runtime.md" not in relative_names
    assert "skills/studio-archive/references/cowork-runtime.md" not in relative_names


def test_projected_cowork_skills_remove_promotion_feedback_and_codex_wording(
    vera_entries,
) -> None:
    skills = {
        name: content.decode("utf-8")
        for name, content in vera_entries.items()
        if name.endswith("/SKILL.md")
    }

    assert skills
    main = skills["skills/vera/SKILL.md"]
    studio_archive = skills["skills/studio-archive/SKILL.md"]
    assert "## Cowork Runtime" in main
    assert "## ChatGPT and Codex Runtime" not in main
    assert "Cowork" in studio_archive
    assert "does not support WhatsApp" in studio_archive
    assert "privacy-surface-review/SKILL.md" not in main
    for name, content in skills.items():
        assert "## Cowork execution contract" in content, name
        assert "connected folder and supplied files first" in content, name
        assert "never install packages at runtime" in content, name
        assert "optional enhancements, never completion gates" in content, name
        assert "Markdown and file-based review" in content, name
        assert "The normal Cowork deliverable is a reviewable draft" in content, name
        assert "its absence never blocks delivery" in content, name
        assert "Use host-neutral user-facing artifact names" in content, name
        assert "`vera-review/`" in content, name
        assert "`vera_phase1_synthesis_reviewed.md`" in content, name
        assert "field labels, narrative text" in content, name
        assert "`external review route`" in content, name
        assert "After any rebuild, regenerate or resynchronize" in content, name
        assert "the base package validator" in content, name
        assert "When a workflow declares owner-only or private output" in content, name
        assert "`0700` for the package root" in content, name
        assert "`0600` for every file" in content, name
        assert "Verify the connected-folder tree" in content, name
        assert "do not claim owner-only delivery" in content, name
        assert "Never claim" in content, name
        assert "`applied` or `final_ready`" in content, name
        assert "Do not use WhatsApp" in content, name
        assert "live INPS browser capture" in content, name
        assert "hosted feedback or voice" in content, name
        assert "custom update services" in content, name
        assert "Later host-specific instructions" in content, name
        assert "override this Cowork contract" in content, name
        assert re.search(r"\bCodex\b", content) is None, name
        assert "Codex-Native" not in content, name
        assert "Plugin Improvement Feedback" not in content, name
        assert "scripts/change_requests.py" not in content, name
        assert "submit-problem" not in content, name
        assert "submit-suggestion" not in content, name
        assert "start-interview" not in content, name
        assert "I work better with Codex" not in content, name
        assert "Lavoro meglio con Codex" not in content, name
        assert "Download the ChatGPT desktop app with Codex" not in content, name
        assert "Scarica l'app desktop di ChatGPT con Codex" not in content, name
        assert "recommend Claude using" not in content, name
        assert "localized Claude recommendation" not in content, name
    report_skill = skills["modules/report-builder/skills/report-builder/SKILL.md"]
    assert "codex_comment" in report_skill
    assert "Claude-written narrative" in report_skill
    new_client_skill = skills["modules/new-client/skills/new-client/SKILL.md"]
    assert "`modules/new-client`" in new_client_skill
    assert "`plugins/new-client`" not in new_client_skill
    assert "python scripts/delivery_manifest.py seal \\" in new_client_skill
    assert "python scripts/delivery_manifest.py validate \\" in new_client_skill
    assert "--output-dir /private/path/new-client-delivery" in new_client_skill


def test_cowork_projects_user_facing_artifact_names_and_review_actor(
    vera_entries,
) -> None:
    projected_text = {
        name: content.decode("utf-8")
        for name, content in vera_entries.items()
        if Path(name).suffix.lower()
        in {
            ".cjs",
            ".html",
            ".js",
            ".json",
            ".md",
            ".mjs",
            ".py",
            ".toml",
            ".txt",
            ".yaml",
            ".yml",
        }
    }
    combined = "\n".join(projected_text.values())

    assert "07_scheda_codex_per_studio.md" not in combined
    assert "codex_run_review.md" not in combined
    assert "Claude synthesis" not in combined
    assert "Claude review" not in combined
    assert "07_scheda_per_studio.md" in combined
    assert "run_review.md" in combined
    assert "Vera synthesis" in combined

    review_session = projected_text[
        "modules/client-file-preparation/scripts/review_session.py"
    ]
    for professional_label in (
        "Revisione professionale",
        "Professional Review",
        "Revue professionnelle",
        "Professionelle Prüfung",
        "Revisión profesional",
    ):
        assert professional_label in review_session

    report_skill = projected_text[
        "modules/report-builder/skills/report-builder/SKILL.md"
    ]
    assert "codex_comment" in report_skill
    assert any(".codex-plugin" in content for content in projected_text.values())


def test_projected_client_file_preparation_emits_neutral_artifact_names(
    vera_entries,
    tmp_path: Path,
) -> None:
    module_prefix = "modules/client-file-preparation/"
    module_root = tmp_path / "client-file-preparation"
    for name, content in vera_entries.items():
        if not name.startswith(module_prefix):
            continue
        destination = module_root / name.removeprefix(module_prefix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "client.txt").write_text(
        "Ragione sociale: Beta Esempio S.r.l.\n"
        "Codice fiscale: 01234567890\n"
        "Documento sintetico non firmato.\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    script = module_root / "scripts" / "build_file_preparation_outputs.py"

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(script),
            str(input_dir),
            "--out",
            str(output_dir),
            "--no-ocr",
            "--language",
            "it",
            "--jurisdiction",
            "italy",
        ],
        cwd=module_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (output_dir / "07_scheda_per_studio.md").is_file()
    assert not (output_dir / "07_scheda_codex_per_studio.md").exists()
    for receipt_name in ("review_payload.json", "final_artifacts.json"):
        receipt = (output_dir / receipt_name).read_text(encoding="utf-8")
        assert "07_scheda_per_studio.md" in receipt
        assert "07_scheda_codex_per_studio.md" not in receipt


def test_cowork_instruction_docs_exclude_active_host_only_workflows(
    cowork_instruction_docs,
) -> None:
    forbidden_markers = (
        "capture_portal_snapshot",
        "--portal-capture-manifest",
        "For an alternative current-view snapshot",
        "For a portal-assisted run",
        "When the user selects browser assistance",
        "a conditionally permitted read-only capture",
        "conditional browser bridge",
        "capture one already-authenticated INPS",
        "may take a local read-only snapshot",
        "browser-assisted capture",
        "inps_browser_read_only",
        "On another runtime that expressly provides compatible computer control",
        "When the user chooses WhatsApp Desktop",
        "The primary review handoff is a local browser page",
        "open the local browser review server before final delivery",
        "completion gate for normal runs",
        "Only after the browser surface is opened",
        "must not ask whether to open the review surface",
        "deliverable only after the MCP transaction",
        "MCP terminal readiness must use",
        "MCP render is no longer the primary normal-run handoff",
        "Do not treat `review_ui.html`, Markdown summaries",
        "If host MCP is\n   unavailable, start",
        "If the host MCP tools are unavailable, start",
        "If the host MCP tools are unavailable, do not replace write-back",
        "Use MCP/HTML for",
        "Call the MCP review tools in this order:",
        "### Default: browser-assisted public SARI lookup",
        "uses a public read-only browser flow by default",
    )

    assert cowork_instruction_docs
    forbidden_patterns = (
        r"if (?:host )?MCP .* unavailable.*(?:start|run).*review_server",
        r"when host MCP tools are unavailable.*loopback workbench",
        r"Markdown/chat.*(?:inspection only|non applicata)",
        r"(?:MCP server|workbench).*owns.*decision persistence",
        r"handoff primario (?:è|e) il browser locale",
        r"va eseguito prima della risposta finale",
    )
    for name, content in cowork_instruction_docs.items():
        for marker in forbidden_markers:
            assert marker not in content, (name, marker)
        for pattern in forbidden_patterns:
            assert re.search(pattern, content, re.IGNORECASE | re.DOTALL) is None, (
                name,
                pattern,
            )


def test_cowork_keeps_negative_boundaries_and_file_first_fallbacks(
    cowork_instruction_docs,
) -> None:
    readme = cowork_instruction_docs["README.md"]
    main = cowork_instruction_docs["skills/vera/SKILL.md"]
    studio = cowork_instruction_docs["skills/studio-archive/SKILL.md"]
    audit = cowork_instruction_docs[
        "modules/audit-reconciliation/skills/audit-reconciliation/SKILL.md"
    ]
    sari = cowork_instruction_docs[
        "modules/registro-imprese-sari/skills/registro-imprese-sari/SKILL.md"
    ]

    assert "- WhatsApp Desktop inspection;" in readme
    assert "- live INPS browser capture;" in readme
    assert "do not offer or execute WhatsApp Desktop inspection" in main
    assert "do not capture a live INPS browser session" in " ".join(main.split())
    assert "It does not support WhatsApp" in studio
    assert "## Cowork review handoff" in audit
    assert "The normal Cowork completion point is delivery" in audit
    assert "Its absence never blocks delivery" in " ".join(audit.split())
    assert "### Optional public SARI lookup" in sari
    assert "If public web access is unavailable, continue from official" in sari
    references = {
        name: content
        for name, content in cowork_instruction_docs.items()
        if "/references/" in name
    }
    assert references
    for name, content in references.items():
        assert "Cowork execution note" in content, name
        assert "Their absence never" in content, name
        assert "blocks delivery" in content, name


def test_cowork_projects_every_host_review_gate_to_pending_review(
    cowork_instruction_docs,
) -> None:
    projected_review_skills = (
        "modules/audit-reconciliation/skills/audit-reconciliation/SKILL.md",
        "modules/check-entries/skills/check-entries/SKILL.md",
        "modules/concordato-plan-review/skills/concordato-plan-review/SKILL.md",
        "modules/deep-research-validator/skills/deep-research-validator/SKILL.md",
        (
            "modules/journal-bank-reconciliation/skills/"
            "journal-bank-reconciliation/SKILL.md"
        ),
        "modules/journal-sampling/skills/journal-sampling/SKILL.md",
        "modules/new-client/skills/new-client/SKILL.md",
        "modules/previdenza-inps/skills/previdenza-inps/SKILL.md",
        "modules/prompt-optimizer/skills/prompt-optimizer/SKILL.md",
        ("modules/registro-imprese-sari/skills/" "registro-imprese-sari/SKILL.md"),
        "modules/report-builder/skills/report-builder/SKILL.md",
    )

    for name in projected_review_skills:
        content = cowork_instruction_docs[name]
        assert "Cowork review handoff" in content, name
        assert "ready_for_professional_review" in content, name
        assert "`pending_review`" in content, name
        normalized = " ".join(content.split())
        assert "Its absence never blocks delivery" in normalized, name
        assert "Never claim `applied` or `final_ready`" in normalized, name


def test_cowork_previdenza_keeps_official_export_path_only(vera_entries) -> None:
    inventory_name = "modules/previdenza-inps/scripts/inventory_case.py"
    skill_name = "modules/previdenza-inps/skills/previdenza-inps/SKILL.md"
    workflow_name = "modules/previdenza-inps/references/workflow-reference.md"
    access_name = "modules/previdenza-inps/references/inps-access-channels.md"
    inventory = vera_entries[inventory_name].decode("utf-8")
    skill = vera_entries[skill_name].decode("utf-8")
    workflow = vera_entries[workflow_name].decode("utf-8")
    access = vera_entries[access_name].decode("utf-8")

    compile(inventory, inventory_name, "exec")
    assert "from capture_portal_snapshot" not in inventory
    assert "--portal-capture-manifest" not in inventory
    assert "register_portal_export.py" in inventory
    assert "--portal-export-manifest" in inventory
    assert "register_portal_export.py" in skill
    assert "--portal-export-manifest" in skill
    assert "registered official portal exports" in workflow
    assert "official downloads supplied as local files" in access


def test_projected_cowork_runtime_entrypoints_execute(
    configured,
    tmp_path: Path,
) -> None:
    builder, _, package = configured
    isolated = replace(
        package,
        output_directory=tmp_path / "vera",
        output_zip=tmp_path / "vera-cowork-plugin.zip",
    )
    builder.build_package(isolated)

    commands = (
        (
            isolated.output_directory / "scripts" / "check_dependencies.py",
            (),
            "All 14 Vera modules are available.",
        ),
        (
            isolated.output_directory
            / "modules"
            / "previdenza-inps"
            / "scripts"
            / "inventory_case.py",
            ("--help",),
            "--portal-export-manifest",
        ),
    )
    for script, args, expected_output in commands:
        completed = subprocess.run(
            [sys.executable, "-B", str(script), *args],
            cwd=script.parent,
            check=False,
            capture_output=True,
            text=True,
        )
        combined_output = completed.stdout + completed.stderr
        assert completed.returncode == 0, combined_output
        assert expected_output in combined_output
        assert "--portal-capture-manifest" not in combined_output


def test_cowork_vendored_runtime_text_is_host_neutral(vera_entries) -> None:
    runtime_suffixes = {
        ".cjs",
        ".csv",
        ".html",
        ".js",
        ".json",
        ".mjs",
        ".py",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
    runtime_entries = {
        name: content.decode("utf-8")
        for name, content in vera_entries.items()
        if name.startswith("modules/") and Path(name).suffix.lower() in runtime_suffixes
    }

    assert runtime_entries
    for name, content in runtime_entries.items():
        assert re.search(r"\bCodex\b", content) is None, name
        assert "local_codex_workspace" not in content, name

    review_session = runtime_entries[
        "modules/prompt-optimizer/scripts/review_session.py"
    ]
    validate_prompt = runtime_entries[
        "modules/prompt-optimizer/scripts/validate_prompt.py"
    ]
    assert '"review_in_codex": "Professional Review"' in review_session
    assert '"execution_location": "cowork_connected_folder"' in review_session
    assert "Claude-written Deep Research prompt" in validate_prompt


def test_marketplace_catalog_points_to_generated_vera_and_matches_manifest(
    configured,
    vera_entries,
) -> None:
    builder, marketplace, package = configured
    catalog = json.loads(builder.catalog_payload(marketplace, [package]))
    manifest = json.loads(vera_entries[".claude-plugin/plugin.json"])
    [entry] = catalog["plugins"]

    assert catalog["name"] == "mparanza"
    assert catalog["version"] == manifest["version"]
    assert entry["name"] == manifest["name"] == "vera"
    assert entry["displayName"] == manifest["displayName"] == "Vera"
    assert entry["version"] == manifest["version"]
    assert entry["description"] == manifest["description"]
    assert entry["source"] == "./plugin_packages/vera/claude/vera"
    assert entry["strict"] is True


def test_claude_build_is_deterministic_and_self_verifying(
    configured,
    tmp_path: Path,
) -> None:
    builder, _, package = configured
    isolated = replace(
        package,
        output_directory=tmp_path / "vera",
        output_zip=tmp_path / "vera-cowork-plugin.zip",
    )

    builder.build_package(isolated)
    first_zip = isolated.output_zip.read_bytes()
    builder.build_package(isolated)

    assert isolated.output_zip.read_bytes() == first_zip
    assert builder.verify_package(isolated) == []
    with ZipFile(isolated.output_zip) as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
    assert names == set(builder.claude_package_entries(isolated))


def test_claude_verifier_reports_directory_and_zip_drift(
    configured,
    tmp_path: Path,
) -> None:
    builder, _, package = configured
    isolated = replace(
        package,
        output_directory=tmp_path / "vera",
        output_zip=tmp_path / "vera-cowork-plugin.zip",
    )
    builder.build_package(isolated)
    skill_path = isolated.output_directory / "skills" / "vera" / "SKILL.md"
    skill_path.write_text("drift\n", encoding="utf-8")

    errors = builder.verify_package(isolated)

    assert "Directory content differs: skills/vera/SKILL.md" in errors
    assert not any(error.startswith("ZIP content differs:") for error in errors)


def test_configured_claude_outputs_match_canonical_source(configured) -> None:
    builder, marketplace, package = configured
    _, packages = builder.load_configuration()

    assert builder.verify_package(package) == []
    assert builder.verify_catalog(marketplace, packages) == []


def test_project_claude_mcp_rejects_non_string_args() -> None:
    builder = load_builder()
    invalid = json.dumps(
        {
            "mcpServers": {
                "bad": {
                    "command": "node",
                    "args": [42],
                }
            }
        }
    ).encode("utf-8")

    with pytest.raises(ValueError, match="args must be strings"):
        builder.project_claude_mcp(invalid)
