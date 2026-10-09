"""Source MCP over actual public helpers; fictional batches, never portal acceptance."""

from __future__ import annotations

import base64
import copy
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import workspace_module
from tests.test_browser_batch_review import entry, payload, review  # noqa: F401
from tests.test_browser_process_lifecycle import (  # noqa: F401
    description,
    host,
    lifecycle,
)

__all__ = []


def bind(tmp_path, row):
    config = tmp_path / "native-browser-bindings.json"
    config.write_text(
        json.dumps(
            {
                "tenant_id": "fictional-studio",
                "actor_id": "fictional-reviewer",
                "bindings": [row],
            }
        )
    )
    env = {
        **{k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ},
        "VERA_WORKSPACE_TENANT_ID": "fictional-studio",
        "VERA_WORKSPACE_ACTOR_ID": "fictional-reviewer",
        "VERA_WORKSPACE_ROLES": "REVIEWER",
        "VERA_WORKSPACE_PYTHON": sys.executable,
        "VERA_BROWSER_WORKSPACE_BINDINGS": str(config),
    }
    return env, config


@pytest.fixture
def batch(review, tmp_path):
    directory = tmp_path / "batch"
    review.save_review(directory, payload(), expected_revision=0)
    ledger = _load_customer_ledger()
    client = tmp_path / "fictional-client"
    client.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(client, client_id, "Fictional browser batch")
    row = {
        "work_ref": "fictional-batch",
        "kind": "batch",
        "directory": str(directory),
        "batch_id": "demo",
        "client_root": str(client),
        "client_id": client_id,
        "engagement_id": engagement["engagement_id"],
    }
    env, config = bind(tmp_path, row)
    return env, directory, client, config


PROGRAM = """
const selected=()=>payload(call('vera_workspace_browser_read',{work_ref:'fictional-batch',item_id:'invoice-1'}));
const authority=p=>({work_ref:p.work_ref,item_id:p.selection.id,revision:p.revision,source_ref:p.source_ref,review_ticket:p.review_ticket});
const save=(p,f)=>payload(call('vera_workspace_browser_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f}));
const prepare=(p,f,key)=>{const draft=save(p,f);return {...authority(p),expected_draft_revision:draft.draft_revision,fields:f,confirmed:true,idempotency_key:key};};
"""


def test_browser_native_first_draft_restores_literal_note_without_consent(
    batch, review
):
    env, directory, _, _ = batch
    before = review.read_review(directory)
    result = rpc_program(
        env,
        PROGRAM
        + "const p=selected(),f={decision:'',note:'  Literal unfinished note  '};save(p,f);const result=selected();",
    )
    assert result["fields"]["note"] == "  Literal unfinished note  "
    assert result["confirmation_restored"] is False
    assert result["draft_stale"] is False
    assert review.read_review(directory) == before


@pytest.mark.parametrize("decision", ["checked", "correction_requested"])
def test_browser_native_explicit_check_keeps_posted_entries_and_archive(
    batch, review, decision
):
    env, directory, client, _ = batch
    before = review.read_review(directory)["payload"]["entries"]
    archive = {
        str(p.relative_to(client)): p.read_bytes()
        for p in client.rglob("*")
        if p.is_file()
    }
    body = (
        PROGRAM
        + "const p=selected(),f={decision:"
        + json.dumps(decision)
        + ",note:'Actual fictional user review'},args=prepare(p,f,'review-1');const first=payload(call('vera_workspace_browser_review_commit',args)),retry=payload(call('vera_workspace_browser_review_commit',args)),changed=call('vera_workspace_browser_review_commit',{...args,fields:{...f,note:'changed'}});const result={first,retry,changed,after:selected()};"
    )
    result = rpc_program(env, body)
    recorded = review.read_review(directory)
    assert recorded["revision"] == 2
    assert recorded["payload"]["entries"] == before
    assert recorded["payload"]["reviews"][-1]["decision"] == decision
    assert result["first"]["record"] == result["retry"]["record"]
    assert result["changed"]["isError"] is True
    assert result["first"]["accounting_correction_executed"] is False
    assert result["first"]["browser_executed"] is False
    assert result["after"]["draft_stale"] is True
    assert {
        str(p.relative_to(client)): p.read_bytes()
        for p in client.rglob("*")
        if p.is_file()
    } == archive


@pytest.mark.parametrize("variant", ["source", "entry", "cas", "consent", "empty_note"])
def test_browser_native_changed_selection_or_incomplete_review_refuses(
    batch, review, variant
):
    env, directory, _, _ = batch
    before = review.read_review(directory)
    change = {
        "source": "args.source_ref='wrong';",
        "entry": "args.item_id='invoice-2';",
        "cas": "args.expected_draft_revision='wrong';",
        "consent": "args.confirmed=false;",
        "empty_note": "args.fields.note='';",
    }[variant]
    result = rpc_program(
        env,
        PROGRAM
        + "const p=selected(),f={decision:'checked',note:'Actual fictional review'},args=prepare(p,f,'denied-1');"
        + change
        + "const result=call('vera_workspace_browser_review_commit',args);",
    )
    assert result["isError"] is True
    assert review.read_review(directory) == before


def test_browser_native_viewer_reads_complete_batch_and_refuses_draft(batch, review):
    env, directory, _, _ = batch
    env["VERA_WORKSPACE_ROLES"] = "VIEWER"
    result = rpc_program(
        env,
        PROGRAM
        + "const p=selected();const denied=call('vera_workspace_browser_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:{decision:'checked',note:'No authority'}});const result={p,denied};",
    )
    assert result["p"]["can_write"] is False
    assert result["p"]["data"]["record"] == review.read_review(directory)
    assert result["denied"]["isError"] is True


def test_browser_native_current_html_download_matches_unchanged_public_renderer(
    batch, review
):
    env, directory, _, _ = batch
    result = rpc_program(
        env,
        "const p=payload(call('vera_workspace_browser_setup',{work_ref:'fictional-batch'}));const result=payload(call('vera_workspace_browser_artifact',{work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref}));",
    )
    assert (
        base64.b64decode(result["base64"])
        == review.render_review(directory).read_bytes()
    )
    assert result["mime_type"] == "application/octet-stream"


@pytest.mark.parametrize("variant", ["client", "batch", "owner", "html", "history"])
def test_browser_native_foreign_or_altered_bound_records_refuse_private_projection(
    batch, variant
):
    env, directory, _, config = batch
    value = json.loads(config.read_bytes())
    if variant == "client":
        value["bindings"][0]["client_id"] = "client_222222222222222222222222"
    elif variant == "batch":
        value["bindings"][0]["batch_id"] = "foreign"
    elif variant == "owner":
        value["actor_id"] = "foreign"
    elif variant == "html":
        (directory / "review-0001.html").write_text("Changed fictional HTML")
    else:
        original = json.loads((directory / "review-0001.json").read_bytes())
        original["payload"]["scope"] = "Changed fictional scope"
        (directory / "review-0001.json").write_text(json.dumps(original))
    config.write_text(json.dumps(value))
    result = rpc_program(
        env,
        "const result=call('vera_workspace_browser_setup',{work_ref:'fictional-batch'});",
    )
    assert result["isError"] is True
    assert set(result["_meta"]["workspace"]) == {"error"}


def test_browser_native_private_stale_review_fields_require_explicit_discard(
    batch, review
):
    env, directory, _, _ = batch
    rpc_program(
        env,
        PROGRAM
        + "const p=selected();const result=save(p,{decision:'checked',note:'Previous note'});",
    )
    review.record_review(
        directory,
        entry_id="invoice-2",
        decision="correction_requested",
        note="Other fictional review",
        expected_revision=1,
    )
    result = rpc_program(
        env,
        PROGRAM
        + "const p=selected(),denied=call('vera_workspace_browser_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:{decision:'checked',note:'Stale'}});const cleared=payload(call('vera_workspace_browser_draft_clear',{...authority(p),expected_draft_revision:p.draft_revision,confirmed:true}));const result={p,denied,cleared,after:selected()};",
    )
    assert result["p"]["draft_stale"] is True
    assert result["denied"]["isError"] is True
    assert result["after"]["fields"] == {"decision": "", "note": ""}
    assert review.read_review(directory)["revision"] == 2


def test_browser_native_process_attempts_keep_public_unfinished_state(
    lifecycle, tmp_path
):
    store = lifecycle.ProcessStore(tmp_path / "processes")
    process = store.create(description())
    attempt = store.begin(process["process_id"], "teaching", host())
    row = {
        "work_ref": "fictional-process",
        "kind": "process",
        "directory": str(store.root),
        "process_id": process["process_id"],
    }
    env, _ = bind(tmp_path, row)
    result = rpc_program(
        env,
        "const result=payload(call('vera_workspace_browser_setup',{work_ref:'fictional-process'}));",
    )
    assert result["data"]["process"]["available_in_qualified_environment"] is False
    assert result["data"]["attempts"][0]["evidence"]["result"] == "unfinished"
    assert result["data"]["attempts"][0]["plan"]["attempt_id"] == attempt["attempt_id"]
    assert result["data"]["browser_executed"] is False
    assert "cr_status" not in result["data"]["process"]


@pytest.mark.parametrize("after_write", [False, True])
def test_browser_native_interruption_retains_intent_and_does_not_repeat_review(
    batch, monkeypatch, review, after_write
):
    env, directory, _, _ = batch
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    workspace = workspace_module()
    native = importlib.import_module("native_browser")
    actual_producer = native.producer

    def interrupted(module, row, action, **args):
        if action == "record_review":
            if after_write:
                actual_producer(module, row, action, **args)
            raise ValueError("Fictional producer transport interrupted")
        return actual_producer(module, row, action, **args)

    monkeypatch.setattr(native, "producer", interrupted)
    selected = {"work_ref": "fictional-batch", "item_id": "invoice-1"}
    page = workspace.dispatch("vera_workspace_browser_read", selected)
    grant = {**selected, **{k: page[k] for k in ("revision", "source_ref")}}
    fields = {"decision": "checked", "note": "Fictional explicit review"}
    draft = workspace.dispatch(
        "vera_workspace_browser_draft_save",
        {
            **grant,
            "expected_draft_revision": page["draft_revision"],
            "fields": fields,
        },
    )
    arguments = {
        **grant,
        "expected_draft_revision": draft["draft_revision"],
        "fields": fields,
        "confirmed": True,
        "idempotency_key": "interrupted-1",
    }
    with pytest.raises(ValueError, match="transport interrupted"):
        workspace.dispatch("vera_workspace_browser_review_commit", arguments)
    conserved = review.read_review(directory)
    reopened = workspace.dispatch("vera_workspace_browser_read", selected)
    with pytest.raises(ValueError, match="uncertain"):
        workspace.dispatch("vera_workspace_browser_review_commit", arguments)
    assert len(reopened["pending_operations"]) == 1
    assert len(conserved["payload"]["reviews"]) == (1 if after_write else 0)
    assert review.read_review(directory) == conserved


def test_browser_native_whole_batch_keeps_every_entry_and_all_history(batch, review):
    env, directory, _, _ = batch
    original = review.read_review(directory)
    complete = copy.deepcopy(original["payload"])
    complete["expected_items"] = 73
    complete["entries"] += [entry("unverified", f"whole-{n}") for n in range(71)]
    review.save_review(directory, complete, expected_revision=1)
    result = rpc_program(
        env,
        "const result=call('vera_workspace_browser_setup',{work_ref:'fictional-batch'});",
    )
    private = result["_meta"]["workspace"]["data"]
    assert len(private["record"]["payload"]["entries"]) == 73
    assert len(private["history"]) == 2
    assert private["history"][0] == original
    assert "Demo whole-70" not in json.dumps(result["content"])


def test_browser_native_completed_receipt_refuses_retry_after_later_public_review(
    batch, review
):
    env, directory, _, _ = batch
    result = rpc_program(
        env,
        PROGRAM
        + "const p=selected(),f={decision:'checked',note:'Actual fictional review'},args=prepare(p,f,'first-review');payload(call('vera_workspace_browser_review_commit',args));const again=selected();payload(call('vera_workspace_browser_draft_clear',{...authority(again),expected_draft_revision:again.draft_revision,confirmed:true}));const fresh=selected(),second=prepare(fresh,{decision:'correction_requested',note:'Separate later request'},'later-review');payload(call('vera_workspace_browser_review_commit',second));const result=call('vera_workspace_browser_review_commit',args);",
    )
    assert result["isError"] is True
    assert "advanced" in result["content"][0]["text"]
    assert len(review.read_review(directory)["payload"]["reviews"]) == 2
