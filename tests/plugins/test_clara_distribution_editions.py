"""Exact-artifact checks for Clara's explicitly selected distribution edition."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.build_codex_plugin_zip import (
    build_chatgpt_upload,
    chatgpt_upload_entries,
    load_packages,
    verify_chatgpt_upload,
)
from scripts.clara_distribution import MARKETPLACE_WORKFLOWS


@pytest.fixture(scope="module")
def candidate(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    directory = tmp_path_factory.mktemp("clara-exact-package")
    package = next(item for item in load_packages() if item.plugin == "clara")
    archive = build_chatgpt_upload(
        package, directory / "clara.zip", edition="marketplace"
    )
    assert verify_chatgpt_upload(package, archive, edition="marketplace") == []
    installed = directory / "installed"
    with ZipFile(archive) as zipped:
        zipped.extractall(installed)
    return archive, installed


def test_reduced_inventory_exposes_only_implemented_local_workflows(candidate) -> None:
    _, installed = candidate
    public = {p.parent.name for p in (installed / "skills").glob("*/SKILL.md")}
    assert public == MARKETPLACE_WORKFLOWS | {"clara"}
    assert not list(installed.rglob(".mcp.json"))
    assert not list(installed.rglob("mcp.json"))
    assert not (installed / "assets/courses").exists()
    assert json.loads((installed / "components.json").read_text())["plugins"] == []
    for path in (installed / ".codex-plugin/plugin.json", installed / "plugin.json"):
        metadata = json.loads(path.read_text())
        assert "mcpServers" not in metadata
        assert "hooks" not in metadata
        assert "interview" not in metadata["description"].lower()
    assert (
        json.loads((installed / "distribution.json").read_text())[
            "requires_local_executor"
        ]
        is True
    )


def test_projection_keeps_engine_bytes_and_removes_dangling_routing(candidate) -> None:
    _, installed = candidate
    source = Path(__file__).resolve().parents[2] / "plugins/clara"
    for relative in (
        "skills/html-deck/scripts/build_html_deck.py",
        "skills/claim-basis-map/scripts/render_claim_basis_map.py",
        "scripts/validate_advisory_contract.py",
    ):
        assert (installed / relative).read_bytes() == (source / relative).read_bytes()
    for path in (installed / "skills").rglob("*.md"):
        text = path.read_text()
        assert "clara_incident_host_link" not in text
        assert "clara_report_open" not in text
        assert "../advisory-case-director/" not in text
        assert "../learn-with-clara/" not in text
        assert "modules/reporting-engine/scripts/" not in text


def test_full_projection_still_keeps_native_tools_and_all_workflows() -> None:
    package = next(item for item in load_packages() if item.plugin == "clara")
    entries = chatgpt_upload_entries(package)
    assert ".mcp.json" in entries and "mcp.json" in entries
    assert "skills/reporting-engine/SKILL.md" in entries
    assert "skills/learn-with-clara/SKILL.md" in entries
    assert b"clara_report_open" in entries["skills/reporting-engine/SKILL.md"]


def test_packaged_dependency_verification_terminates_without_recursive_setup(
    candidate,
) -> None:
    _, installed = candidate
    environment = dict(
        os.environ, PYTHONDONTWRITEBYTECODE="1", MPARANZA_INCIDENT_DELIVERY="local-only"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(installed / "scripts/check_dependencies.py"),
            "--managed-verify",
        ],
        cwd=installed,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "All Clara dependencies are available" in result.stderr


def test_packaged_integrity_rejects_changed_helper(candidate, tmp_path) -> None:
    archive, _ = candidate
    installed = tmp_path / "tampered"
    with ZipFile(archive) as zipped:
        zipped.extractall(installed)
    target = installed / "scripts/validate_advisory_contract.py"
    original_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    target.write_bytes(target.read_bytes() + b"\n# altered\n")
    assert hashlib.sha256(target.read_bytes()).hexdigest() != original_hash
    result = subprocess.run(
        [
            sys.executable,
            str(installed / "scripts/check_dependencies.py"),
            "--managed-verify",
        ],
        cwd=installed,
        env=dict(
            os.environ,
            PYTHONDONTWRITEBYTECODE="1",
            MPARANZA_INCIDENT_DELIVERY="local-only",
            MPARANZA_INCIDENT_STATE_DIR=str(tmp_path / "state"),
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0


def test_all_packaged_local_imports_resolve_without_full_clara(candidate) -> None:
    """Import presence is mechanical; catch the observed omitted-helper defect."""
    _, installed = candidate
    source = Path(__file__).resolve().parents[2] / "plugins/clara"
    source_modules = {p.stem for p in source.rglob("*.py")}
    missing = []
    for path in installed.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            modules = []
            if isinstance(node, ast.Import):
                modules = [item.name.split(".")[0] for item in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module.split(".")[0]]
            for module in modules:
                if module not in source_modules:
                    continue
                if not any(
                    (folder / f"{module}.py").is_file()
                    for folder in (path.parent, installed / "scripts")
                ):
                    missing.append(
                        f"{path.relative_to(installed)}:{node.lineno}: {module}"
                    )
    assert missing == []


def test_unused_case_normalizer_is_not_shipped_or_advertised(candidate) -> None:
    _, installed = candidate
    assert not (installed / "scripts/advisor_case_core.py").exists()
    assert not (installed / "scripts/normalize_legacy_pptx.py").exists()
    instructions = "\n".join(
        p.read_text() for p in (installed / "skills").rglob("*.md")
    )
    assert "normalize_legacy_pptx.py" not in instructions
    assert "advisor_case_core.py" not in instructions


@pytest.mark.parametrize(
    "script",
    [
        "scripts/validate_advisory_contract.py",
        "scripts/model_data_report.py",
        "scripts/workflow_usage.py",
        "skills/html-deck/scripts/init_html_deck.py",
        "skills/html-deck/scripts/build_layout_gallery.py",
        "skills/html-deck/scripts/compose_html_deck.py",
        "skills/html-deck/scripts/build_html_deck.py",
        "skills/html-deck/scripts/validate_html_deck.py",
        "skills/html-deck/scripts/browser_qa_html_deck.py",
        "skills/html-deck/scripts/inspect_html_deck.py",
        "skills/html-deck/scripts/validate_revision_map.py",
        "skills/html-deck/scripts/compare_html_deck_revision.py",
        "skills/claim-basis-map/scripts/render_claim_basis_map.py",
    ],
)
def test_packaged_script_imports_without_repository_paths(
    candidate, tmp_path, script
) -> None:
    _, installed = candidate
    # -I removes cwd, PYTHONPATH and user site; only this script's own directory
    # is restored. Helpers must resolve their remaining dependencies themselves.
    # Import under a non-CLI name: runtime provisioning is covered separately by
    # dependency verification and fresh-install acceptance, not this import probe.
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            "import runpy,sys; from pathlib import Path; p=sys.argv.pop(1); "
            "sys.path.insert(0,str(Path(p).parent)); "
            "runpy.run_path(p,run_name='packaged_import_probe'); "
            "print('packaged imports resolved')",
            str(installed / script),
        ],
        cwd=tmp_path,
        env=dict(os.environ, MPARANZA_INCIDENT_DELIVERY="local-only"),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "packaged imports resolved"


@pytest.mark.parametrize(
    "schema, expected",
    [
        ("legacy", "loaded"),
        ("vera.client_workflow_context.v2", "validated-invalid-context"),
    ],
)
def test_packaged_diagnostic_context_loads_its_lazy_library(
    candidate, tmp_path, schema, expected
) -> None:
    _, installed = candidate
    context = tmp_path / "context.json"
    context.write_text(json.dumps({"schema_version": schema}))
    program = (
        "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
        "from diagnostic_context import load_workflow_context\n"
        "try:\n load_workflow_context(Path(sys.argv[2]),workflow_id='html-deck'); print('loaded')\n"
        "except ValueError:\n print('validated-invalid-context')\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            program,
            str(installed / "scripts"),
            str(context),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
