from __future__ import annotations

import json

import pytest

from scripts.build_claude_plugin_zip import _reviewer_note


@pytest.mark.parametrize("product", ["vera", "lucia", "clara"])
def test_reviewer_note_lists_only_declared_servers_and_existing_fonts(
    product: str,
) -> None:
    entries = {"skills/example/SKILL.md": b"example"}
    if product == "vera":
        entries[".mcp.json"] = json.dumps(
            {
                "mcpServers": {
                    "veraNativeWorkspace": {"command": "node"},
                    "veraIncidents": {"url": "https://mparanza.com/mcp/vera-incidents"},
                }
            }
        ).encode()
        entries["mcp/workspace.cjs"] = b"font widget"
    elif product == "lucia":
        entries[".mcp.json"] = json.dumps(
            {
                "mcpServers": {
                    "luciaStudioArchive": {"command": "node"},
                }
            }
        ).encode()
    note = _reviewer_note(product, entries).decode()
    assert len(note.splitlines()) <= 80
    assert f"https://mparanza.com/static/shared/courses/{product}/" in note
    assert "25 MiB" in note
    assert "temporary file" in note
    assert "1 top-level" in note
    assert ("`veraIncidents`" in note) == (product == "vera")
    assert ("`luciaStudioArchive`" in note) == (product == "lucia")
    assert ("`mcp/workspace.cjs`" in note) == (product == "vera")
    assert "fabio@mparanza.com" in note


def test_reviewer_note_rejects_undescribed_remote_server() -> None:
    entries = {
        ".mcp.json": b'{"mcpServers":{"newRemote":{"url":"https://example.test"}}}'
    }
    with pytest.raises(ValueError, match="Unreviewed remote server"):
        _reviewer_note("vera", entries)
