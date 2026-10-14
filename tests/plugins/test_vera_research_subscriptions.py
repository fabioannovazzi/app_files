"""Subscription-state and transport regressions, not live publisher acceptance."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.plugins.test_bilancio_native_workspace import NODE

__all__ = []
ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "plugins/vera/mcp/research-sources.cjs"


def run_node(tmp_path: Path, program: str) -> dict:
    """Exercise the public MCP service with an isolated fictional OS profile."""
    completed = subprocess.run(
        [NODE, "-e", "const server=require(process.argv[1]);" + program, str(SERVER)],
        env={**os.environ, "MPARANZA_RESEARCH_HOME": str(tmp_path / "profile")},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


SETUP = """
const call=(action,args={})=>server.call('vera_research_sources_'+action,args)._meta.researchSources;
const connect=()=>call('configure',{provider_id:'eutekne',revision:call('state').revision,enabled:true,user_authorized:true});
const request=()=>call('request',{provider_id:'eutekne',revision:call('state').revision});
const observation=p=>({provider_id:'eutekne',revision:p.revision,request_id:p.handoff.request_id,result:'document_read',route:'browser',tool_name:'fictional_host_browser',source_url:'https://www.eutekne.it/fictional/document?session=do-not-retain#private',source_title:'Explicitly fictional subscriber document'});
"""


def test_missing_subscription_register_keeps_both_sources_disabled_without_writes(
    tmp_path,
):
    result = run_node(
        tmp_path, SETUP + "process.stdout.write(JSON.stringify(call('state')));"
    )
    assert result["revision"] == 0
    assert result["optional"] is True
    assert [p["enabled"] for p in result["providers"]] == [False, False]
    assert not (tmp_path / "profile").exists()


def test_connection_choice_persists_across_processes_without_claiming_access(tmp_path):
    run_node(tmp_path, SETUP + "process.stdout.write(JSON.stringify(connect()));")

    result = run_node(
        tmp_path, SETUP + "process.stdout.write(JSON.stringify(call('state')));"
    )

    assert result["providers"][0]["enabled"] is True
    assert result["providers"][0]["last_check"] is None
    assert result["providers"][0]["pending"] is None
    assert result["providers"][1]["enabled"] is False


@pytest.mark.parametrize("authorized", [False, None, "true"])
def test_connection_refuses_missing_explicit_user_authorisation(tmp_path, authorized):
    value = json.dumps(authorized)
    result = run_node(
        tmp_path,
        SETUP
        + f"let error;try{{call('configure',{{provider_id:'eutekne',revision:0,enabled:true,user_authorized:{value}}});}}catch(e){{error=e.message;}}process.stdout.write(JSON.stringify({{error,state:call('state')}}));",
    )
    assert "explicit" in result["error"]
    assert result["state"]["revision"] == 0


def test_access_request_is_pending_and_does_not_establish_document_access(tmp_path):
    result = run_node(
        tmp_path, SETUP + "connect();process.stdout.write(JSON.stringify(request()));"
    )
    assert (
        result["providers"][0]["pending"]["request_id"]
        == result["handoff"]["request_id"]
    )
    assert result["providers"][0]["last_check"] is None
    assert "subscriber document" in result["handoff"]["prompt"]


def test_recorded_document_read_preserves_attribution_and_removes_url_session_data(
    tmp_path,
):
    result = run_node(
        tmp_path,
        SETUP
        + "connect();const pending=request();process.stdout.write(JSON.stringify(call('record',observation(pending))));",
    )
    check = result["providers"][0]["last_check"]
    assert check["result"] == "document_read"
    assert check["basis"] == "host_observation_reported"
    assert check["source_url"] == "https://www.eutekne.it/fictional/document"
    assert result["providers"][0]["pending"] is None
    raw = (tmp_path / "profile/subscriptions.json").read_text()
    assert "do-not-retain" not in raw


@pytest.mark.parametrize("outcome", ["login_required", "unavailable"])
def test_failed_access_records_the_actual_limit_without_a_document(tmp_path, outcome):
    result = run_node(
        tmp_path,
        SETUP
        + f"connect();const p=request(),args=observation(p);delete args.source_url;delete args.source_title;args.result='{outcome}';process.stdout.write(JSON.stringify(call('record',args)));",
    )
    check = result["providers"][0]["last_check"]
    assert check["result"] == outcome
    assert "source_url" not in check


def test_missing_host_tools_are_reported_without_inventing_a_provider_call(tmp_path):
    result = run_node(
        tmp_path,
        SETUP
        + "connect();const p=request(),args=observation(p);delete args.source_url;delete args.source_title;args.result='unavailable';args.route='none';args.tool_name=null;call('record',args);process.stdout.write(JSON.stringify(call('state')));",
    )
    check = result["providers"][0]["last_check"]
    assert check["result"] == "unavailable"
    assert check["route"] == "none"
    assert check["tool_name"] is None
    assert result["providers"][0]["pending"] is None


def test_one_fiscale_connected_tool_observation_uses_the_same_research_register(
    tmp_path,
):
    result = run_node(
        tmp_path,
        SETUP
        + "call('configure',{provider_id:'one-fiscale',revision:0,enabled:true,user_authorized:true});const p=call('request',{provider_id:'one-fiscale',revision:1});call('record',{...observation(p),provider_id:'one-fiscale',route:'connector',source_url:'https://onefiscale.wolterskluwer.it/fictional/document'});process.stdout.write(JSON.stringify(call('state')));",
    )
    assert result["providers"][0]["enabled"] is False
    assert result["providers"][1]["last_check"]["route"] == "connector"
    assert result["providers"][1]["last_check"]["result"] == "document_read"


@pytest.mark.parametrize(
    "url",
    [
        "http://eutekne.it/document",
        "https://user:secret@eutekne.it/document",
    ],
)
def test_access_observation_refuses_plaintext_or_credential_bearing_source_urls(
    tmp_path, url
):
    result = run_node(
        tmp_path,
        SETUP
        + f"connect();const p=request(),args=observation(p);args.source_url={json.dumps(url)};let error;try{{call('record',args);}}catch(e){{error=e.message;}}process.stdout.write(JSON.stringify({{error,state:call('state')}}));",
    )
    assert "HTTPS document URL" in result["error"]
    assert result["state"]["providers"][0]["last_check"] is None


def test_disconnect_cancels_inflight_check_and_stale_result_cannot_reenable_it(
    tmp_path,
):
    result = run_node(
        tmp_path,
        SETUP
        + "connect();const p=request();call('configure',{provider_id:'eutekne',revision:p.revision,enabled:false,user_authorized:true});let error;try{call('record',{...observation(p),revision:call('state').revision});}catch(e){error=e.message;}process.stdout.write(JSON.stringify({error,state:call('state')}));",
    )
    assert "disconnected" in result["error"]
    assert result["state"]["providers"][0]["enabled"] is False
    assert result["state"]["providers"][0]["last_check"] is None
    assert result["state"]["providers"][0]["pending"] is None


def test_stale_connection_update_preserves_newer_user_choice(tmp_path):
    result = run_node(
        tmp_path,
        SETUP
        + "connect();let error;try{call('configure',{provider_id:'eutekne',revision:0,enabled:false,user_authorized:true});}catch(e){error=e.message;}process.stdout.write(JSON.stringify({error,state:call('state')}));",
    )
    assert "changed" in result["error"]
    assert result["state"]["providers"][0]["enabled"] is True


@pytest.mark.parametrize("field", ["password", "cookie", "token", "storage_path"])
def test_register_rejects_credential_and_storage_arguments(tmp_path, field):
    result = run_node(
        tmp_path,
        SETUP
        + f"let error;try{{call('configure',{{provider_id:'eutekne',revision:0,enabled:true,user_authorized:true,{field}:'never-store-this'}});}}catch(e){{error=e.message;}}process.stdout.write(JSON.stringify({{error}}));",
    )
    assert "arguments" in result["error"]
    assert not (tmp_path / "profile/subscriptions.json").exists()


def test_corrupt_register_is_preserved_instead_of_reset(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir()
    file = directory / "subscriptions.json"
    file.write_text("broken JSON")
    file.chmod(0o600)

    result = run_node(
        tmp_path,
        SETUP
        + "let error;try{call('state');}catch(e){error=e.message;}process.stdout.write(JSON.stringify({error}));",
    )

    assert "preserve" in result["error"]
    assert file.read_text() == "broken JSON"


def test_symlink_storage_cannot_redirect_subscription_writes(tmp_path):
    target = tmp_path / "other"
    target.mkdir()
    (tmp_path / "profile").symlink_to(target, target_is_directory=True)

    result = run_node(
        tmp_path,
        SETUP
        + "let error;try{connect();}catch(e){error=e.message;}process.stdout.write(JSON.stringify({error}));",
    )

    assert "real directories" in result["error"]
    assert list(target.iterdir()) == []


def test_failed_temporary_write_releases_lock_without_masking_the_storage_error(
    tmp_path,
):
    result = run_node(
        tmp_path,
        SETUP
        + "const fs=require('node:fs'),original=fs.writeFileSync;fs.writeFileSync=()=>{throw new Error('Fictional disk write refused');};let error;try{connect();}catch(e){error=e.message;}finally{fs.writeFileSync=original;}process.stdout.write(JSON.stringify({error}));",
    )
    assert result["error"] == "Fictional disk write refused"
    assert not (tmp_path / "profile/write.lock").exists()
    assert not (tmp_path / "profile/subscriptions.json").exists()


def test_mcp_protocol_advertises_panel_and_loads_self_contained_resource(tmp_path):
    result = run_node(
        tmp_path,
        "const init=server.handle({method:'initialize'}),tools=server.handle({method:'tools/list'}).tools,resource=server.resource().contents[0];process.stdout.write(JSON.stringify({init,tools,html:resource.text,mime:resource.mimeType}));",
    )
    assert result["init"]["capabilities"]["resources"] == {}
    assert result["mime"] == "text/html;profile=mcp-app"
    assert "/*__JS__*/" not in result["html"]
    assert "__FONT__" not in result["html"]
    assert "base64," in result["html"]
    record = next(t for t in result["tools"] if t["name"].endswith("_record"))
    assert record["_meta"]["ui"]["visibility"] == ["model"]
    state = next(t for t in result["tools"] if t["name"].endswith("_state"))
    assert "app" in state["_meta"]["ui"]["visibility"]


def test_cli_and_mcp_share_the_same_register(tmp_path):
    run_node(tmp_path, SETUP + "process.stdout.write(JSON.stringify(connect()));")

    completed = subprocess.run(
        [NODE, str(SERVER), "--state"],
        env={**os.environ, "MPARANZA_RESEARCH_HOME": str(tmp_path / "profile")},
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(completed.stdout)["providers"][0]["enabled"] is True


def test_vera_research_entries_include_saved_subscriptions_without_a_second_method():
    root = ROOT / "plugins/vera"
    assert (
        "researchSources" in json.loads((root / ".mcp.json").read_text())["mcpServers"]
    )
    for name in (
        "quesito-legale-fiscale",
        "legal-tax-answer-planner",
        "deep-research",
        "legal-tax-answer-review",
        "adversarial-opinion",
    ):
        assert (
            "references/research-subscriptions.md"
            in (root / f"skills/{name}/SKILL.md").read_text()
        )
    reference = (root / "skills/vera/references/research-subscriptions.md").read_text()
    assert "single shared" in reference
    assert "No API is required for the browser" in reference
    assert "Retain only permitted" in reference
    course = json.loads(
        (root / "assets/courses/quesito-legale-fiscale/course.json").read_text()
    )
    assert "skills/vera/references/research-subscriptions.md" in [
        s["path"] for s in course["sources"]
    ]


def test_stdio_transport_keeps_panel_state_and_errors_in_mcp_envelopes(tmp_path):
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "vera_research_sources_state", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "vera_research_sources_request",
                "arguments": {"provider_id": "eutekne", "revision": 0},
            },
        },
    ]
    completed = subprocess.run(
        [NODE, str(SERVER), "--stdio"],
        input="\n".join(json.dumps(r) for r in requests) + "\n",
        env={**os.environ, "MPARANZA_RESEARCH_HOME": str(tmp_path / "profile")},
        capture_output=True,
        text=True,
        check=True,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [r["id"] for r in responses] == [1, 2, 3]
    assert responses[1]["result"]["_meta"]["researchSources"]["revision"] == 0
    assert responses[2]["result"]["isError"] is True
    assert "not been authorised" in responses[2]["result"]["content"][0]["text"]


@pytest.mark.parametrize(
    "archive",
    [
        "plugin_packages/vera/vera-plugin.zip",
        "plugin_packages/vera/vera-chatgpt-upload.zip",
        "plugin_packages/vera/vera-claude-plugin.zip",
        "static/shared/vera/downloads/vera-antigravity-plugin.zip",
    ],
)
def test_shipped_archives_execute_the_subscription_cli_and_render_the_panel(
    tmp_path, archive
):
    suffix = "scripts/research-sources.cjs"
    files = [
        suffix,
        "scripts/research-subscriptions-store.cjs",
        "ui/research-sources.html",
        "ui/research-sources.js",
        "ui/research-sources.css",
        "ui/custom_select.js",
        "ui/workspace.css",
        "ui/InstrumentSans-Regular.ttf",
    ]
    with ZipFile(ROOT / archive) as package:
        matches = [n for n in package.namelist() if n.endswith(suffix)]
        assert len(matches) == 1
        prefix = matches[0].removesuffix(suffix)
        for name in files:
            destination = tmp_path / "package" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(package.read(prefix + name))
    script = tmp_path / "package" / suffix
    completed = subprocess.run(
        [
            NODE,
            "-e",
            "const service=require(process.argv[1]);const p=service.call('vera_research_sources_state').structuredContent;service.call('vera_research_sources_configure',{provider_id:'one-fiscale',revision:p.revision,enabled:true,user_authorized:true});const resource=service.resource().contents[0];process.stdout.write(JSON.stringify({state:service.call('vera_research_sources_state').structuredContent,html:resource.text}));",
            str(script),
        ],
        env={**os.environ, "MPARANZA_RESEARCH_HOME": str(tmp_path / "profile")},
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["state"]["providers"][1]["enabled"] is True
    assert result["state"]["providers"][1]["last_check"] is None
    assert "VeraResearchSources" in result["html"]
    assert "/*__SELECT_JS__*/" not in result["html"]


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("field", ["work", "modelData"])
def test_question_page_qualifies_subscription_use_as_vera_specific_in_every_locale(
    language, field
):
    source = (ROOT / "static/shared/product-function-pages.js").read_text()
    start = source.index('    "quesito-legale-fiscale": {')
    end = source.index('\n    "', start + 10)
    section = re.search(
        r"(?ms)^        " + language + r": \{(.*?)(?=^        \},)", source[start:end]
    ).group(1)

    value = json.loads(
        re.search(r"(?m)^          " + field + r': ("(?:[^"\\]|\\.)*")', section).group(
            1
        )
    )

    assert "Eutekne" in value
    assert "FISCALE" in value
    assert "Vera" in value
