from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins"
THEME_MARKER = "mparanza-plugin-icon-v1"


def test_all_plugin_icons_use_shared_theme_marker() -> None:
    icon_paths = sorted(PLUGIN_ROOT.glob("*/assets/icon.svg"))

    assert icon_paths
    for path in icon_paths:
        svg = path.read_text(encoding="utf-8")
        assert f'data-theme="{THEME_MARKER}"' in svg, path
        assert 'viewBox="0 0 64 64"' in svg, path
        if path.parent.parent.name in {"clara", "lucia", "vera"}:
            assert 'fill="#002060"' in svg, path
            assert 'fill="#171816"' not in svg, path
            assert all(
                color in svg for color in ("#0070C0", "#00B0F0", "#FFFFFF")
            ), path
        else:
            assert 'fill="#171816"' in svg, path


def test_plugin_icons_are_not_duplicated() -> None:
    icon_paths = sorted(PLUGIN_ROOT.glob("*/assets/icon.svg"))
    contents = [path.read_text(encoding="utf-8") for path in icon_paths]

    assert len(contents) == len(set(contents))


def test_lucia_icon_is_a_human_companion() -> None:
    svg = (PLUGIN_ROOT / "lucia" / "assets" / "icon.svg").read_text(encoding="utf-8")

    assert '<circle cx="32" cy="21" r="7.5" fill="#FFFFFF"/>' in svg
    assert 'd="M15 51c1.8-11.5 8.2-17 17-17s15.2 5.5 17 17z"' in svg
    assert 'd="M15 13h29l8 9v31H15z"' not in svg


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is required for MCP")
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_vera_sidebar_advertises_self_contained_icons_for_both_host_themes(
    theme: str,
) -> None:
    node = shutil.which("node")
    assert node is not None
    messages = (
        '{"jsonrpc":"2.0","id":1,"method":"initialize"}\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
    )

    result = subprocess.run(
        [node, str(PLUGIN_ROOT / "vera/mcp/workspace.cjs")],
        input=messages,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )

    initialized, listed = map(json.loads, result.stdout.splitlines())
    workspace = next(
        tool
        for tool in listed["result"]["tools"]
        if tool["name"] == "vera_workspace_open"
    )
    icons = workspace["icons"]
    assert [icon["theme"] for icon in icons] == ["light", "dark"]
    assert initialized["result"]["serverInfo"]["icons"] == icons
    assert workspace["_meta"]["openai/ui"]["entrypoints"] == [
        {"type": "global"},
        {"type": "thread"},
    ]
    icon = next(icon for icon in icons if icon["theme"] == theme)
    prefix, encoded = icon["src"].split(",", 1)
    assert prefix == "data:image/svg+xml;base64"
    assert icon["mimeType"] == "image/svg+xml"
    assert icon["sizes"] == ["any"]
    asset = PLUGIN_ROOT / "vera/assets" / f"sidebar-{theme}.svg"
    assert base64.b64decode(encoded) == asset.read_bytes()
