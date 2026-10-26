from __future__ import annotations

import json
import re
from pathlib import Path
from zipfile import ZipFile

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
    assert "veraIncidents" not in note
    assert ("`luciaStudioArchive`" in note) == (product == "lucia")
    assert ("`mcp/workspace.cjs`" in note) == (product == "vera")
    assert "fabio@mparanza.com" in note
    assert 'Local review tokens (flagged as "Uses a credential")' in note
    assert "no inherited token or API-key variables" in note
    assert ("check-entries" in note) == (product == "vera")
    assert ("`secrets.token_urlsafe(32)`" in note) == (product != "clara")
    assert ("`secrets.token_urlsafe(24)`" in note) == (product == "clara")
    assert ("may include it in model context" in note) == (product == "vera")


@pytest.mark.parametrize("product", ["vera", "lucia", "clara"])
def test_packaged_reviewer_note_names_existing_token_files(product: str) -> None:
    root = Path(__file__).resolve().parents[2]
    directory = root / "plugin_packages" / product
    with ZipFile(directory / f"{product}-claude-plugin.zip") as archive:
        note = archive.read("REVIEW.md").decode()
        referenced_files = set(
            re.findall(r"`([^`\n]+/[^`\n]+\.(?:py|cjs|html|json))`", note)
        )
        assert referenced_files <= set(archive.namelist())
    assert note == (directory / "claude" / product / "REVIEW.md").read_text()
    assert len(note.splitlines()) <= 80
    assert 'Local review tokens (flagged as "Uses a credential")' in note


def test_reviewer_note_rejects_undescribed_remote_server() -> None:
    entries = {
        ".mcp.json": b'{"mcpServers":{"newRemote":{"url":"https://example.test"}}}'
    }
    with pytest.raises(ValueError, match="Unreviewed remote server"):
        _reviewer_note("vera", entries)


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_reviewer_note_rejects_retired_reporting_server(product: str) -> None:
    entries = {
        ".mcp.json": json.dumps(
            {
                "mcpServers": {
                    product
                    + "Incidents": {
                        "url": f"https://mparanza.com/mcp/{product}-incidents"
                    }
                }
            }
        ).encode()
    }
    with pytest.raises(ValueError, match="Unreviewed remote server"):
        _reviewer_note(product, entries)
