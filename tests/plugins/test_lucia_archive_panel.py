"""The panel keeps private listings local and survives backend read failures."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def panel(tmp_path):
    plugin = tmp_path / "lucia"
    shutil.copytree(ROOT / "plugins/lucia/assets", plugin / "assets")
    (plugin / "scripts").mkdir()
    shutil.copyfile(
        ROOT / "plugins/lucia/scripts/studio_archive_mcp.cjs",
        plugin / "scripts/studio_archive_mcp.cjs",
    )
    (plugin / "components.json").write_text(
        json.dumps({"workflow_roles": {"studio-archive": {"supports": []}}})
    )
    server = plugin / "modules/studio-archive/mcp/server.cjs"
    server.parent.mkdir(parents=True)
    server.write_text(
        """
const readline = require('node:readline');
readline.createInterface({input:process.stdin}).on('line', line => {
  const m=JSON.parse(line);
  let result={};
  if(m.method==='initialize') result={serverInfo:{name:'vera-studio-archive'},capabilities:{},instructions:'Archive Organization uses the complete projected inventory'};
  else if(m.method==='tools/list') result={tools:[{name:'studio_archive_status'}]};
  else if(process.env.TEST_ARCHIVE_ERROR) result={isError:true,content:[{type:'text',text:'private-path /secret'}]};
  else result={structuredContent:{configured:true,clients:[{client_id:'c1',display_name:'Synthetic client',registration_status:'registered',email:'private@example.test'}],engagements:[{engagement_id:'e1',label:'Synthetic practice',status:'open',sources:['private-source']}]}};
  process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:m.id,result})+'\\n');
});
"""
    )
    return plugin


def call(panel, method, params=None, *, failed=False, panel_only=True):
    env = {**os.environ, "LUCIA_ARCHIVE_PANEL_ONLY": "1" if panel_only else "0"}
    if failed:
        env["TEST_ARCHIVE_ERROR"] = "1"
    request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    result = subprocess.run(
        ["node", str(panel / "scripts/studio_archive_mcp.cjs")],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=10,
        check=True,
    )
    return json.loads(result.stdout)["result"]


def test_panel_read_failure_keeps_resource_renderable_without_private_error(panel):
    result = call(panel, "tools/call", {"name": "lucia_archive_open"}, failed=True)
    assert result["_meta"]["archive"] == {"error": "archive_unavailable"}
    assert not result.get("isError")
    assert "secret" not in json.dumps(result)


def test_panel_clients_are_only_in_private_metadata(panel):
    result = call(panel, "tools/call", {"name": "lucia_archive_open"})
    assert result["_meta"]["archive"]["clients"] == [
        {
            "client_id": "c1",
            "display_name": "Synthetic client",
            "registration_status": "registered",
        }
    ]
    assert "Synthetic client" not in json.dumps(result["content"])
    assert "private@example.test" not in json.dumps(result)


def test_panel_practices_do_not_expose_source_documents(panel):
    result = call(
        panel,
        "tools/call",
        {"name": "lucia_archive_list_matters", "arguments": {"client_id": "c1"}},
    )
    assert result["_meta"]["archive"]["engagements"] == [
        {"engagement_id": "e1", "label": "Synthetic practice", "status": "open"}
    ]
    assert "private-source" not in json.dumps(result)


def test_panel_resource_embeds_local_fonts(panel):
    result = call(
        panel,
        "resources/read",
        {"uri": call(panel, "resources/list")["resources"][0]["uri"]},
    )
    assert "__FONT__" not in result["contents"][0]["text"]
    assert "data:font/ttf;base64," in result["contents"][0]["text"]


@pytest.mark.parametrize(
    "panel_only,expected",
    [
        (True, ["lucia_archive_open", "lucia_archive_list_matters"]),
        (False, ["studio_archive_status"]),
    ],
)
def test_same_runtime_exposes_separate_panel_and_chat_tools(
    panel, panel_only, expected
):
    result = call(panel, "tools/list", panel_only=panel_only)
    assert [tool["name"] for tool in result["tools"]] == expected


def test_changed_panel_bytes_get_a_new_resource_address(panel):
    original = call(panel, "resources/list")["resources"][0]["uri"]
    asset = panel / "assets/studio-archive.html"
    asset.write_text(
        asset.read_text(encoding="utf-8") + "\n<!-- changed view -->\n",
        encoding="utf-8",
    )

    current = call(panel, "resources/list")["resources"][0]["uri"]

    assert current != original
    assert (
        current == call(panel, "tools/list")["tools"][0]["_meta"]["ui"]["resourceUri"]
    )
