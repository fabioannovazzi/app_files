"""Exercise Lucia's packaged engagement dependency without sibling plugins."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.plugins.test_product_on_demand_mcp import Session

ROOT = Path(__file__).resolve().parents[2]
__all__: list[str] = []


@pytest.fixture(params=["cowork_mcp", "codex_mcp", "codex_cli"])
def archive_runtime(tmp_path: Path, request, monkeypatch):
    """Exercise the supported Archive entry points from extracted host packages."""
    cli = request.param == "codex_cli"
    cowork = request.param == "cowork_mcp"
    filename = "lucia-claude-plugin.zip" if cowork else "lucia-plugin.zip"
    extracted = tmp_path / "package"
    with ZipFile(ROOT / "plugin_packages/lucia" / filename) as archive:
        archive.extractall(extracted)
    plugin = extracted if cowork else extracted / "lucia-codex-plugin/plugins/lucia"
    settings = {
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(tmp_path / "state"),
        "VERA_STUDIO_ARCHIVE_SESSION_ID": str(tmp_path),
        "VERA_STUDIO_ARCHIVE_PYTHON": sys.executable,
        "MPARANZA_INCIDENT_STATE_DIR": str(tmp_path / "incident-state"),
        "MPARANZA_INCIDENT_DELIVERY": "local-only",
    }
    environment = {**os.environ, **settings}
    if not cli:
        assert shutil.which("node"), "Node.js is required for packaged MCP tests"
        for key, value in settings.items():
            monkeypatch.setenv(key, value)
        session = Session(plugin)
        request.addfinalizer(session.close)
    transcript = []

    def call(name: str, arguments: dict) -> dict:
        if cli:
            commands = {
                "configure_studio_archive": "configure",
                "create_studio_archive_client": "create-client",
                "create_studio_client_engagement": "create-engagement",
                "import_studio_client_document": "import-document",
                "prepare_studio_client_workflow": "prepare-workflow",
                "start_studio_client_workflow": "start-workflow",
                "finalize_studio_client_workflow": "finalize-workflow",
                "complete_studio_client_workflow": "complete-workflow",
            }
            command = [
                sys.executable,
                str(plugin / "scripts/lucia_studio_archive.py"),
                commands[name],
            ]
            for key, value in arguments.items():
                if key == "input_ids":
                    for identifier in value:
                        command.extend(["--input-id", identifier])
                elif key == "artifacts":
                    command.extend(["--artifacts-json", json.dumps(value)])
                else:
                    command.extend(["--" + key.replace("_", "-"), str(value)])
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=tmp_path,
                env=environment,
                timeout=30,
                check=False,
            )
            assert result.returncode == 0, result.stderr
            payload = json.loads(result.stdout)
            transcript.append({"command": command, "result": payload})
            (tmp_path / "cli-transcript.json").write_text(
                json.dumps(transcript, indent=2)
            )
            return payload
        request = {"name": name, "arguments": arguments}
        response = session.call("tools/call", request, timeout=60)
        transcript.append({"request": request, "response": response})
        (tmp_path / "mcp-transcript.json").write_text(json.dumps(transcript, indent=2))
        assert "error" not in response, response
        assert not response["result"].get("isError"), response
        return response["result"]["structuredContent"]

    archive_root = tmp_path / "clients"
    archive_root.mkdir()
    call("configure_studio_archive", {"archive_root": str(archive_root)})
    client = call(
        "create_studio_archive_client", {"legal_name": "Cliente Sintetico Lucia"}
    )
    client_id = client["client"]["client_id"]
    engagement = call(
        "create_studio_client_engagement",
        {"client_id": client_id, "engagement_label": "Locazione sintetica"},
    )
    question = tmp_path / "question.txt"
    question.write_text(
        "Quali documenti servono per esaminare un contratto di locazione italiano?"
    )
    engagement_id = engagement["engagement"]["engagement_id"]
    imported = call(
        "import_studio_client_document",
        {
            "client_id": client_id,
            "engagement_id": engagement_id,
            "source_path": str(question),
            "role": "source",
        },
    )
    return plugin, call, client_id, engagement_id, imported, question


@pytest.mark.parametrize(
    ("context_contents", "expected_error"),
    [
        (None, "client engagement context file is unavailable"),
        ("", "client engagement context file is unreadable"),
    ],
)
def test_packaged_question_inspection_requires_real_started_engagement(
    archive_runtime, tmp_path: Path, context_contents: str | None, expected_error: str
):
    plugin, call, client_id, engagement_id, imported, question = archive_runtime
    script = plugin / "modules/prompt-optimizer/scripts/inspect_question.py"
    if context_contents is not None:
        (tmp_path / "missing.json").write_text(context_contents)
    missing = subprocess.run(
        [
            sys.executable,
            str(script),
            str(question),
            "--output-dir",
            str(tmp_path / "bad-output"),
            "--client-engagement",
            str(tmp_path / "missing.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 2
    assert expected_error in missing.stderr
    prepared = call(
        "prepare_studio_client_workflow",
        {
            "engagement_id": engagement_id,
            "workflow_id": "prompt-optimizer",
            "input_ids": [imported["input_id"]],
        },
    )
    call(
        "start_studio_client_workflow",
        {
            "client_id": client_id,
            "engagement_id": engagement_id,
            "run_id": prepared["run"]["run_id"],
        },
    )
    context = prepared["client_engagement"]
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            context["input_bindings"][0]["path"],
            "--output-dir",
            context["output_dir"],
            "--client-engagement",
            prepared["client_engagement_path"],
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (Path(context["output_dir"]) / "question_inventory.json").is_file()


def test_packaged_matter_opening_starts_in_real_archive_run(archive_runtime) -> None:
    plugin, call, client_id, engagement_id, imported, _ = archive_runtime
    prepared = call(
        "prepare_studio_client_workflow",
        {
            "engagement_id": engagement_id,
            "workflow_id": "apertura-pratica",
            "input_ids": [imported["input_id"]],
        },
    )
    call(
        "start_studio_client_workflow",
        {
            "client_id": client_id,
            "engagement_id": engagement_id,
            "run_id": prepared["run"]["run_id"],
        },
    )
    output = Path(prepared["client_engagement"]["output_dir"]) / "matter-opening"
    result = subprocess.run(
        [
            sys.executable,
            str(plugin / "modules/apertura-pratica/scripts/initialize_workspace.py"),
            str(output),
            "--opening-mode",
            "new_client_new_matter",
            "--client-reference",
            client_id,
            "--matter-reference",
            engagement_id,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (output / "matter_intake.json").is_file()
    run = {
        "client_id": client_id,
        "engagement_id": engagement_id,
        "run_id": prepared["run"]["run_id"],
    }
    # Declare the real outputs of the initialized matter; no invented report or receipt.
    artifacts = [
        {
            "artifact_id": f"matter.file{index}",
            "path": f"matter-opening/{file.relative_to(output).as_posix()}",
            "purpose": "Synthetic matter-opening record",
            "audience": "review",
            "media_type": (
                "application/json" if file.suffix == ".json" else "text/plain"
            ),
        }
        for index, file in enumerate(sorted(output.rglob("*")))
        if file.is_file()
    ]
    sealed = call("finalize_studio_client_workflow", {**run, "artifacts": artifacts})
    assert sealed["run"]["status"] == "ready_for_review"
    completed = call("complete_studio_client_workflow", run)
    assert completed["run"]["status"] == "completed"


def test_packaged_archive_prepares_answer_review_for_the_selected_matter(
    archive_runtime,
):
    _, call, _, engagement_id, imported, _ = archive_runtime
    result = call(
        "prepare_studio_client_workflow",
        {
            "engagement_id": engagement_id,
            "workflow_id": "deep-research-validator",
            "input_ids": [imported["input_id"]],
        },
    )
    assert result["run"]["workflow_id"] == "deep-research-validator"
    assert result["client_engagement"]["engagement_id"] == engagement_id


@pytest.mark.parametrize("product_zip", ["lucia-plugin.zip", "lucia-claude-plugin.zip"])
def test_packaged_mcp_rejects_accounting_before_creating_any_run(
    tmp_path, monkeypatch, product_zip
):
    with ZipFile(ROOT / "plugin_packages/lucia" / product_zip) as archive:
        archive.extractall(tmp_path / "package")
    root = next((tmp_path / "package").rglob("scripts/on_demand_mcp.cjs")).parent.parent
    state = tmp_path / "state"
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_STATE_DIR", str(state))
    session = Session(root)
    try:
        names = {t["name"] for t in session.call("tools/list")["result"]["tools"]}
        excluded = {
            "start_check_entries_from_sample",
            "verify_studio_run_report",
            "lucia_assurance_prepare_studio_client_workflow",
        }
        assert names.isdisjoint(excluded)
        for name in excluded:
            reply = session.call("tools/call", {"name": name, "arguments": {}})
            assert reply["error"]["message"].startswith(
                "Unknown lucia method or target"
            )
        reply = session.call(
            "tools/call",
            {
                "name": "prepare_studio_client_workflow",
                "arguments": {
                    "engagement_id": "eng_" + "1" * 24,
                    "workflow_id": "lipe",
                    "input_ids": ["sample"],
                },
            },
        )
        assert reply["error"]["message"] == "Workflow not available in Lucia."
        assert not state.exists()
    finally:
        session.close()


@pytest.mark.parametrize(
    "command",
    [
        ["start-check-entries-from-sample"],
        ["verify-run-report"],
        ["prepare-workflow", "--engagement-id", "synthetic", "--workflow-id=lipe"],
    ],
)
def test_lucia_archive_cli_refuses_unavailable_commands_before_access(
    tmp_path, command
):
    state = tmp_path / "state"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins/lucia/scripts/lucia_studio_archive.py"),
            *command,
        ],
        env={**os.environ, "VERA_STUDIO_ARCHIVE_STATE_DIR": str(state)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert not state.exists()
