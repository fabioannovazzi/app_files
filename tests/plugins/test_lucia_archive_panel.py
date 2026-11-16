"""The panel keeps private listings local and survives backend read failures."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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
    component = server.parent.parent
    shutil.copytree(ROOT / "plugins/studio-archive/assets", component / "assets")
    shutil.copyfile(
        ROOT / "plugins/studio-archive/mcp/archive_panel.cjs",
        server.parent / "archive_panel.cjs",
    )
    (component / "scripts").mkdir()
    shutil.copyfile(
        ROOT / "plugins/studio-archive/scripts/archive_panel.py",
        component / "scripts/archive_panel.py",
    )
    (component / "scripts/archive_core.py").write_text(FAKE_CORE)
    server.write_text(
        """
const readline = require('node:readline');
readline.createInterface({input:process.stdin}).on('line', line => {
  const m=JSON.parse(line);
  let result={};
  if(m.method==='initialize') result={serverInfo:{name:'vera-studio-archive'},capabilities:{},instructions:'Archive Organization uses the complete projected inventory'};
  else if(m.method==='tools/list') result={tools:[{name:'studio_archive_status'}]};
  else if(process.env.TEST_ARCHIVE_ERROR) result={isError:true,content:[{type:'text',text:'private-path /secret'}]};
  else if(m.params?.name==='get_studio_incarico') result={structuredContent:{purpose:'Synthetic assignment',documents:[{name:'Source.txt',reference:{input_id:'input-one'},secret:'not-projected'}],results:[],deliverables:[{versions:[{label:'Opinion',revision:2,primary_format:'docx',formats:[{name:'opinion.docx',format:'docx',reference:{entry_key:'opinion',revision:2,format:'docx'},available:true}]}]}],conversations:[{title:'Existing discussion',url:'codex://threads/synthetic',secret:'not-projected'}],document_issues:[]}};
  else if(m.params?.name==='read_studio_incarico_document') result={structuredContent:{name:'Source.txt',path:'/synthetic/Source.txt',preview:JSON.stringify(m.params.arguments),secret:'not-projected'}};
  else result={structuredContent:{configured:true,clients:[{client_id:'c1',display_name:'Synthetic client',registration_status:'registered',product_has_work:true,email:'private@example.test'},{client_id:'foreign',display_name:'Other product only',registration_status:'registered',product_has_work:false}],engagements:[{engagement_id:'e1',label:'Synthetic practice',status:'open',sources:['private-source']}]}};
  process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:m.id,result})+'\\n');
});
"""
    )
    return plugin


def call(panel, method, params=None, *, failed=False, panel_only=True):
    env = {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_PYTHON": sys.executable,
        "LUCIA_ARCHIVE_PANEL_ONLY": "1" if panel_only else "0",
    }
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
    assert result.get("isError")
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize("product", ["lucia", "clara"])
def test_panel_clients_are_only_in_private_metadata(panel, monkeypatch, product):
    if product == "clara":
        shutil.copyfile(
            ROOT / "plugins/clara/scripts/studio_archive_mcp.cjs",
            panel / "scripts/studio_archive_mcp.cjs",
        )
        monkeypatch.setenv("CLARA_ARCHIVE_PANEL_ONLY", "1")
    result = call(panel, "tools/call", {"name": f"{product}_archive_open"})
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
        (
            True,
            [
                "lucia_archive_open",
                "lucia_archive_list_matters",
                "lucia_archive_read_matter",
                "lucia_archive_read_document",
                "lucia_archive_search",
                "lucia_archive_source",
                "lucia_archive_setup",
            ],
        ),
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
    asset = panel / "modules/studio-archive/assets/archive-ui.js"
    asset.write_text(
        asset.read_text(encoding="utf-8") + "\n<!-- changed view -->\n",
        encoding="utf-8",
    )

    current = call(panel, "resources/list")["resources"][0]["uri"]

    assert current != original
    assert (
        current == call(panel, "tools/list")["tools"][0]["_meta"]["ui"]["resourceUri"]
    )


def test_matter_contents_and_chat_links_remain_app_only(panel):
    result = call(
        panel,
        "tools/call",
        {
            "name": "lucia_archive_read_matter",
            "arguments": {"client_id": "c1", "engagement_id": "e1"},
        },
    )
    matter = result["_meta"]["archive"]
    assert matter["documents"][0]["reference"] == {"input_id": "input-one"}
    assert matter["conversations"] == [
        {"title": "Existing discussion", "url": "codex://threads/synthetic"}
    ]
    assert matter["deliverables"][0]["versions"][0]["formats"][0]["available"] is True
    assert "not-projected" not in json.dumps(result)
    assert "Source.txt" not in json.dumps(result["content"])


def test_document_request_preserves_exact_scope_and_reference(panel):
    selection = {
        "client_id": "c1",
        "engagement_id": "e1",
        "reference": {"entry_key": "opinion", "revision": 2, "format": "docx"},
    }
    result = call(
        panel,
        "tools/call",
        {"name": "lucia_archive_read_document", "arguments": selection},
    )
    document = result["_meta"]["archive"]
    assert json.loads(document["preview"]) == selection
    assert document["path"] == "/synthetic/Source.txt"
    assert "/synthetic" not in json.dumps(result["content"])
    assert "not-projected" not in json.dumps(result)


def test_failed_document_verification_returns_no_path_or_preview(panel):
    result = call(
        panel,
        "tools/call",
        {
            "name": "lucia_archive_read_document",
            "arguments": {
                "client_id": "c1",
                "engagement_id": "e1",
                "reference": {"input_id": "input-one"},
            },
        },
        failed=True,
    )
    assert result["_meta"]["archive"] == {"error": "archive_unavailable"}
    assert "secret" not in json.dumps(result)


FAKE_CORE = r"""import os, json
from types import SimpleNamespace
class ArchiveError(ValueError): pass
def list_studio_clients(**kwargs):
 if os.environ.get("TEST_ARCHIVE_ERROR"): raise ArchiveError("private-path /secret")
 return {"configured":True,"clients":[{"client_id":"c1","display_name":"Synthetic client","registration_status":"registered","product_has_work":True,"email":"private@example.test"},{"client_id":"foreign","display_name":"Other product only","product_has_work":False}]}
def get_studio_client_folder(client_id): return {"client_folder":{"client_root":"/synthetic"}}
ledger=SimpleNamespace(inspect_engagements=lambda *args:{"engagements":[{"engagement_id":"e1","label":"Synthetic practice","status":"open","sources":["private-source"]}],"blocked_engagements":[]})
def get_studio_incarico(*args):
 return {"client_id":"c1","engagement_id":"e1","purpose":"Synthetic assignment","documents":[{"name":"Source.txt","reference":{"input_id":"input-one"},"secret":"not-projected"}],"results":[],"deliverables":[{"versions":[{"label":"Opinion","revision":2,"issued_at":"2026-11-16","primary_format":"docx","formats":[{"name":"opinion.docx","format":"docx","reference":{"entry_key":"opinion","revision":2,"format":"docx"},"available":True}]}]}],"conversations":[{"title":"Existing discussion","url":"codex://threads/synthetic","secret":"not-projected"}],"document_issues":[]}
def read_studio_incarico_document(client_id,engagement_id,reference):
 return {"name":"Source.txt","path":"/synthetic/Source.txt","preview":json.dumps(dict(client_id=client_id,engagement_id=engagement_id,reference=reference)),"secret":"not-projected"}
"""


def test_shared_ui_opens_exact_revisions_and_existing_chats():
    completed = subprocess.run(
        [
            "node",
            str(ROOT / "tests/plugins/shared_archive_ui.cjs"),
            str(ROOT / "plugins/studio-archive/assets/archive-ui.js"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("asset", ["archive.css", "archive-ui.js", "archive-host.js"])
def test_each_shared_asset_invalidates_cached_panel(panel, asset):
    before = call(panel, "resources/list")["resources"][0]["uri"]
    path = panel / "modules/studio-archive/assets" / asset
    path.write_text(path.read_text() + "\n/* shared change */\n")
    assert call(panel, "resources/list")["resources"][0]["uri"] != before
