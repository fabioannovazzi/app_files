"""Check the discovery catalogue that the installed Vera MCP server actually uses."""

from __future__ import annotations

import json
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
