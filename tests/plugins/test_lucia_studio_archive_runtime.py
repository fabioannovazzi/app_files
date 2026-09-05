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

ROOT = Path(__file__).resolve().parents[2]
__all__: list[str] = []


@pytest.fixture()
def archive_runtime(tmp_path: Path):
    """Extract only Lucia and create one isolated synthetic engagement via MCP."""
    plugin = tmp_path / "lucia"
    with ZipFile(ROOT / "plugin_packages/lucia/lucia-claude-plugin.zip") as archive:
        archive.extractall(plugin)
    node = shutil.which("node")
    assert node, "Node.js is required for this runtime regression"
    server = json.loads((plugin / ".mcp.json").read_text())["mcpServers"][
        "luciaStudioArchive"
    ]
    environment = {
        **os.environ,
        **server["env"],
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(tmp_path / "state"),
        "VERA_STUDIO_ARCHIVE_PYTHON": sys.executable,
    }
    transcript = []

    def call(name: str, arguments: dict) -> dict:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        result = subprocess.run(
            [
                node,
                *[
                    arg.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin))
                    for arg in server["args"]
                ],
            ],
            input=json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            cwd=tmp_path,
            env=environment,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        response = json.loads(result.stdout)
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
