"""Check the discovery catalogue that the installed Vera MCP server actually uses."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

__all__: list[str] = []


def test_codex_package_exposes_one_pipeline_editor_and_only_distinct_companion_tasks():
    archive = (
        Path(__file__).resolve().parents[2] / "plugin_packages/vera/vera-plugin.zip"
    )
    review = "ui://vera/workspace-v1.html"
    expected = {
        "veraNativeWorkspace": review,
        "courseChats": "ui://vera/course-chats-v1.html",
        "researchSources": "ui://vera/research-sources.html",
        "studioWork": "ui://vera/studio-work-v1.html",
        "agenziaAcquisition": "ui://vera/agenzia-acquisition-v1.html",
    }
    with ZipFile(archive) as package:
        catalog = json.loads(
            package.read("vera-codex-plugin/plugins/vera/mcp-catalog.json")
        )
    services = catalog["services"]
    urls = [
        (service["name"], entry["uri"])
        for service in services
        for entry in service["resources"]
        if entry["uri"].startswith("ui://")
    ]
    assert sorted(urls) == sorted(expected.items())
    bound = {
        t["name"]
        for service in services
        for t in service["tools"]
        if review
        in {
            t.get("_meta", {}).get("ui", {}).get("resourceUri"),
            t.get("_meta", {}).get("openai/outputTemplate"),
            t.get("_meta", {}).get("ui/resourceUri"),
        }
    }
    assert bound == {"vera_workspace_open", "vera_open_review"}
    assert not [
        t["name"]
        for service in services
        for t in service["tools"]
        if t["name"].startswith("render_") and t["name"].endswith("_review")
    ]
    # A discovery entry alone did not make the three auxiliary interfaces open
    # in Desktop. Exercise their actual resource responses and app handshake.
    node = shutil.which("node")
    assert node is not None, "Node is required for packaged MCP resources"
    with tempfile.TemporaryDirectory(prefix="vera-app-displays-") as directory:
        with ZipFile(archive) as package:
            package.extractall(directory)
        root = Path(directory) / "vera-codex-plugin/plugins/vera"
        for entry, uri in (
            ("scripts/course_chat_mcp.cjs", expected["courseChats"]),
            ("mcp/research-sources.cjs", expected["researchSources"]),
            (
                "modules/browser-automation/mcp/server.cjs",
                expected["agenziaAcquisition"],
            ),
        ):
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "resources/read",
                "params": {"uri": uri},
            }
            result = subprocess.run(
                [node, str(root / entry)],
                input=json.dumps(request) + "\n",
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
                cwd=root,
            )
            resource = json.loads(result.stdout)["result"]["contents"][0]
            display = resource["_meta"]["openai/ui"]
            assert display["preferredDisplayMode"] == "fullscreen", uri
            assert "fullscreen" in display["availableDisplayModes"], uri
            assert re.search(
                r'appCapabilities:\s*\{[^}]*availableDisplayModes:\s*\[[^\]]*"fullscreen"',
                resource["text"],
            ), uri
