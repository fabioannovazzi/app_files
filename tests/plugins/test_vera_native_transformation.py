"""Source MCP with the actual synthetic store, never real professional acceptance."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys

import pytest

from tests.plugins.test_trasformazione import module  # noqa: F401
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program

__all__ = []


@pytest.fixture
def transformation(module, tmp_path):
    root = tmp_path / "synthetic-case"
    store = module.CaseStore(root)
    store.initialize("FICTIONAL-TR", "FICTIONAL_OPERATOR", "Only synthetic preparation")
    sources = root / "synthetic-inputs"
    sources.mkdir()
    source = sources / "source.txt"
    source.write_text("FICTIONAL SOURCE. Never legal authority.")
    store.import_evidence("E1", source, "Fictional", "line 1", "FICTIONAL_OPERATOR")
    store.put(
        "finding",
        {
            "id": "F1",
            "statement": "Complete fictional proposal",
            "category": "fact",
            "rationale": "Fictional source only",
            "alternatives": ["Acquire additional fictional facts"],
            "confidence": "synthetic_unverified",
            "dependencies": ["evidence:E1"],
        },
        "FICTIONAL_OPERATOR",
    )
    store.branch(
        "B1",
        "Fictional branch",
        "FICTIONAL_REVIEWER",
        "Review",
        ["finding:F1"],
        "FICTIONAL_OPERATOR",
    )
    config = tmp_path / "bindings.json"
    config.write_text(
        json.dumps(
            {
                "tenant_id": "fictional-tenant",
                "actor_id": "fictional-actor",
                "bindings": [
                    {
                        "work_ref": "fictional-transform",
                        "case_dir": str(root),
                        "case_id": "FICTIONAL-TR",
                        "synthetic_only": True,
                        "sources": [
                            {"source_ref": "fictional-source", "path": str(source)}
                        ],
                    }
                ],
            }
        )
    )
    env = {
        **{key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ},
        "VERA_WORKSPACE_TENANT_ID": "fictional-tenant",
        "VERA_WORKSPACE_ACTOR_ID": "fictional-actor",
        "VERA_WORKSPACE_ROLES": "REVIEWER",
        "VERA_WORKSPACE_PYTHON": sys.executable,
        "VERA_TRANSFORMATION_WORKSPACE_BINDINGS": str(config),
    }
    env.pop("VERA_WORKSPACE_BINDINGS", None)
    return env, store, source, config


PROGRAM = """
const setup=()=>payload(call('vera_workspace_transformation_setup',{work_ref:'fictional-transform'}));
const authority=p=>({work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref,review_ticket:p.review_ticket});
const fields=(operation='submit')=>({operation,actor:'FICTIONAL_OPERATOR',record_kind:'',record_json:'',branch_id:'B1',proposal_digest:'',decision:'',reason:''});
const save=(p,f)=>payload(call('vera_workspace_transformation_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f}));
const execute=(p,f,key)=>{const saved=save(p,f),args={...authority(p),expected_draft_revision:saved.draft_revision,fields:f,confirmed:true,idempotency_key:key};return {result:payload(call('vera_workspace_transformation_execute',args)),args};};
const clear=p=>payload(call('vera_workspace_transformation_draft_clear',{...authority(p),expected_draft_revision:p.draft_revision,confirmed:true}));
"""


def test_transformation_private_json_and_attribution_restore_without_consent(
    transformation,
):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields('put');f.record_kind='finding';f.record_json=' {\n  \"id\": \"unfinished\"\n} '.replace(/\n/g,'\\n');f.actor='  Literal synthetic actor  ';save(p,f);const result=setup();".replace(
            "\n", "\\n"
        ),
    )
    assert result["fields"]["actor"] == "  Literal synthetic actor  "
    assert "unfinished" in result["fields"]["record_json"]
    assert result["confirmation_restored"] is False
    assert result["data"]["state"] == before
    assert store.load() == before


def test_transformation_end_to_end_public_authoring_separate_review_and_export(
    transformation,
):
    env, store, _, _ = transformation
    result = rpc_program(
        env,
        PROGRAM
        + """
let p=setup();let f=fields('update_case');f.record_json=JSON.stringify({initial_form:'FICTIONAL SNC',final_form:'FICTIONAL SRL'});execute(p,f,'attributes');clear(setup());
p=setup();f=fields('import_evidence');f.record_json=JSON.stringify({id:'E2',source_ref:'fictional-source',origin:'Fictional',locator:'line 1'});execute(p,f,'import');clear(setup());
p=setup();f=fields('put');f.record_kind='calculation';f.record_json=JSON.stringify({id:'C1',operation:'allocation',args:{capital:'100',shares:['1/3','2/3']},dependencies:['evidence:E2']});execute(p,f,'calculation');clear(setup());
p=setup();f=fields('branch');f.branch_id='B2';f.record_json=JSON.stringify({title:'Fictional capital',owner:'FICTIONAL_REVIEWER',next_step:'Review',dependencies:['finding:F1','calculation:C1']});execute(p,f,'branch');clear(setup());
p=setup();f=fields('submit');f.branch_id='B2';execute(p,f,'submission');clear(setup());
p=setup();const submitted=p.data.state;f=fields('review');f.branch_id='B2';f.proposal_digest=p.data.state.branches.B2.proposal_digest;f.decision='approve';f.reason='FICTIONAL DECISION. Only synthetic preparation.';execute(p,f,'review');clear(setup());
p=setup();f=fields('export');execute(p,f,'export');const after=setup(),item=after.data.artifacts.find(r=>r.name.endsWith('/dossier.md')),artifact=payload(call('vera_workspace_transformation_artifact',{work_ref:after.work_ref,revision:after.revision,source_ref:after.source_ref,artifact_ref:item.name}));const result={submitted,after,artifact};
""",
    )
    assert result["submitted"]["decisions"] == []
    state = store.load()
    assert state["case"]["actual_date"] is None
    assert state["branches"]["B2"]["status"] == "approved_for_preparation"
    assert (
        state["branches"]["B2"]["calculations"]["calculation:C1"]["values"][
            "participant_1"
        ]["exact"]
        == "100/3"
    )
    assert state["decisions"][0]["scope"] == "synthetic_preparation_only"
    assert state["decisions"][0]["authenticated_signature"] is False
    assert len(state["decisions"]) == 1
    assert result["after"]["data"]["professional_validation"] is False
    assert b"dossier sintetico" in base64.b64decode(result["artifact"]["base64"])
    assert (
        hashlib.sha256(base64.b64decode(result["artifact"]["base64"])).hexdigest()
        == result["artifact"]["sha256"]
    )


def test_transformation_exact_retry_adds_only_one_public_revision(transformation):
    env, store, _, _ = transformation
    before = store.load()["revision"]
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),step=execute(p,fields(),'once'),retry=payload(call('vera_workspace_transformation_execute',step.args)),changed=call('vera_workspace_transformation_execute',{...step.args,fields:{...step.args.fields,actor:'Changed'}});const result={first:step.result,retry,changed};",
    )
    assert result["retry"]["result"] == result["first"]["result"]
    assert result["changed"]["isError"] is True
    assert store.load()["revision"] == before + 1
    assert store.load()["decisions"] == []


@pytest.mark.parametrize(
    "change",
    [
        "confirmed:false",
        "review_ticket:'forged.signature'",
        "source_ref:'f'.repeat(64)",
        "expected_draft_revision:'f'.repeat(64)",
    ],
)
def test_transformation_bad_authority_or_confirmation_refuses_before_history_write(
    transformation, change
):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields(),saved=save(p,f);const result=call('vera_workspace_transformation_execute',{...authority(p),fields:f,expected_draft_revision:saved.draft_revision,confirmed:true,idempotency_key:'refused',"
        + change
        + "});",
    )
    assert result["isError"] is True
    assert store.load() == before


def test_transformation_edited_proposal_refuses_old_native_scope(transformation):
    env, store, source, _ = transformation
    page = rpc_program(env, PROGRAM + "const result=setup();")
    source.write_text("FICTIONAL REVISED SOURCE")
    store.import_evidence(
        "E1", source, "Fictional changed", "line 1", "FICTIONAL_OPERATOR"
    )
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup();const old="
        + json.dumps(page)
        + ";const result=call('vera_workspace_transformation_draft_save',{...authority(p),revision:old.revision,source_ref:old.source_ref,expected_draft_revision:p.draft_revision,fields:fields()});",
    )
    assert result["isError"] is True
    assert store.load()["decisions"] == []


def test_transformation_public_failure_retains_intent_and_refuses_repeat(
    transformation,
):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields('review');f.proposal_digest=p.data.state.branches.B1.proposal_digest;f.decision='approve';f.reason='Fictional, not yet submitted';const saved=save(p,f),args={...authority(p),fields:f,expected_draft_revision:saved.draft_revision,confirmed:true,idempotency_key:'uncertain'};const first=call('vera_workspace_transformation_execute',args),again=call('vera_workspace_transformation_execute',args);const result={first,again,page:setup()};",
    )
    assert result["first"]["isError"] is True
    assert "Uncertain transformation write" in result["again"]["content"][0]["text"]
    assert result["page"]["pending_operations"] == ["uncertain"]
    assert store.load() == before


def test_transformation_viewer_reads_whole_case_and_cannot_write(transformation):
    env, store, _, _ = transformation
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": "VIEWER"},
        PROGRAM
        + "const p=setup();const result={page:p,write:call('vera_workspace_transformation_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:fields()})};",
    )
    assert result["page"]["data"]["state"] == store.load()
    assert result["page"]["can_write"] is False
    assert result["write"]["isError"] is True


@pytest.mark.parametrize("change", ["owner", "synthetic", "case_id"])
def test_transformation_wrong_owner_or_non_synthetic_binding_refuses(
    transformation, change
):
    env, _, _, config = transformation
    value = json.loads(config.read_bytes())
    if change == "owner":
        value["actor_id"] = "another-actor"
    elif change == "synthetic":
        value["bindings"][0]["synthetic_only"] = False
    else:
        value["bindings"][0]["case_id"] = "ANOTHER-CASE"
    config.write_text(json.dumps(value))
    result = rpc_program(
        env,
        "const result=call('vera_workspace_transformation_setup',{work_ref:'fictional-transform'});",
    )
    assert result["isError"] is True


def test_transformation_dossier_and_manifest_rewrite_refuse_public_replay(
    transformation,
):
    env, store, _, _ = transformation
    output = store.export()
    dossier = output / "dossier.md"
    dossier.write_text("FICTIONAL ALTERED DOSSIER")
    manifest = output / "manifest.json"
    value = json.loads(manifest.read_bytes())
    value["files"]["dossier.md"] = hashlib.sha256(dossier.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(value))
    result = rpc_program(
        env,
        "const result=call('vera_workspace_transformation_setup',{work_ref:'fictional-transform'});",
    )
    assert result["isError"] is True
    assert "differs from public replay" in result["content"][0]["text"]


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_transformation_linked_evidence_refuses_before_exposure(
    transformation, tmp_path, link_kind
):
    env, store, _, _ = transformation
    evidence = store.root / store.load()["records"]["evidence"]["E1"]["local_path"]
    original = tmp_path / "linked-source"
    evidence.rename(original)
    if link_kind == "symlink":
        evidence.symlink_to(original)
    else:
        os.link(original, evidence)
    result = rpc_program(
        env,
        "const result=call('vera_workspace_transformation_setup',{work_ref:'fictional-transform'});",
    )
    assert result["isError"] is True
    assert "link" in result["content"][0]["text"]


def test_transformation_metadata_app_only_and_missing_binding_fallback(transformation):
    env, _, _, _ = transformation
    env.pop("VERA_TRANSFORMATION_WORKSPACE_BINDINGS")
    result = rpc_program(
        env,
        "const definitions=service.handle({jsonrpc:'2.0',id:1,method:'tools/list'}).result.tools.filter(x=>x.name.startsWith('vera_workspace_transformation_'));const page=payload(call('vera_workspace_transformation_catalogue',{}));const result={definitions,page};",
    )
    assert {row["name"] for row in result["definitions"]} == {
        "vera_workspace_transformation_" + name
        for name in (
            "catalogue",
            "setup",
            "draft_save",
            "draft_clear",
            "execute",
            "artifact",
            "initial_setup",
            "initial_draft_save",
            "initial_draft_clear",
            "initial_create",
            "author_setup",
            "author_draft_save",
            "author_draft_clear",
            "author_request",
            "author_read",
            "author_adopt",
            "author_cancel",
            "author_message_prepare",
            "author_context",
            "author_stage",
        )
    }
    assert len(result["definitions"]) == 20
    assert {
        row["name"]: row["_meta"]["ui"]["visibility"]
        for row in result["definitions"]
        if "model" in row["_meta"]["ui"]["visibility"]
    } == {
        "vera_workspace_transformation_author_context": ["app", "model"],
        "vera_workspace_transformation_author_stage": ["app", "model"],
    }
    assert result["page"]["works"] == []
    assert result["page"]["configured"] is False
    assert result["page"]["workspace_scope"] == "synthetic_prototype"


def test_transformation_all_public_demo_exports_replay_and_selective_staleness_survive(
    module, tmp_path
):
    from demo import run_demo

    root = tmp_path / "synthetic-demo"
    run_demo(root)
    config = tmp_path / "demo-bindings.json"
    config.write_text(
        json.dumps(
            {
                "tenant_id": "fictional-demo",
                "actor_id": "fictional-demo",
                "bindings": [
                    {
                        "work_ref": "fictional-demo",
                        "case_dir": str(root),
                        "case_id": "DEMO-TR-001",
                        "synthetic_only": True,
                    }
                ],
            }
        )
    )
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "VERA_WORKSPACE_PYTHON": sys.executable,
        "VERA_WORKSPACE_TENANT_ID": "fictional-demo",
        "VERA_WORKSPACE_ACTOR_ID": "fictional-demo",
        "VERA_TRANSFORMATION_WORKSPACE_BINDINGS": str(config),
        "VERA_WORKSPACE_ROLES": "REVIEWER",
    }
    result = rpc_program(
        env,
        "const result=payload(call('vera_workspace_transformation_setup',{work_ref:'fictional-demo'}));",
    )
    assert len(result["data"]["exports"]) == 3
    assert result["data"]["state"]["branches"]["capital"]["status"] == "stale"
    assert (
        result["data"]["state"]["branches"]["creditors"]["status"]
        == "approved_for_preparation"
    )
    assert (
        result["data"]["state"]["records"]["source"]["S01"]["verification_status"]
        == "unverified"
    )


def test_transformation_tampered_receipt_refuses_projection_and_new_operation(
    transformation,
):
    env, store, _, _ = transformation
    rpc_program(
        env, PROGRAM + "execute(setup(),fields(),'retained');const result=setup();"
    )
    receipt = next(
        (store.root / ".native-workspace").glob("transformation-*/operations.json")
    )
    value = json.loads(receipt.read_bytes())
    value["retained"]["result"]["result"]["professional_validation"] = True
    receipt.write_text(json.dumps(value))
    before = store.load()
    result = rpc_program(
        env,
        "const result=call('vera_workspace_transformation_setup',{work_ref:'fictional-transform'});",
    )
    assert result["isError"] is True
    assert "receipt integrity mismatch" in result["content"][0]["text"]
    assert store.load() == before


def test_transformation_private_draft_cas_refuses_concurrent_edit(transformation):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields('put');f.record_kind='finding';save(p,f);const result=call('vera_workspace_transformation_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:{...f,actor:'Another window'}});",
    )
    assert result["isError"] is True
    assert "fields changed in another window" in result["content"][0]["text"]
    assert store.load() == before


def test_transformation_artifact_refuses_arbitrary_path_without_exposing_bytes(
    transformation,
):
    env, _, _, _ = transformation
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup();const result=call('vera_workspace_transformation_artifact',{work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref,artifact_ref:'../../bindings.json'});",
    )
    assert result["isError"] is True
    assert "Select an exact verified synthetic" in result["content"][0]["text"]
