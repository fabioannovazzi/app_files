"""Real public ESG mutations, source authorization and separately human decisions."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_esg_foundation import bind_request, case  # noqa: F401
from tests.plugins.test_vera_native_archive_closure import (
    declare_all,
)
from tests.plugins.test_vera_native_archive_closure import setup as closure_setup
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import archive_cli
from tests.plugins.test_vera_native_workspace import configure

__all__ = []


@pytest.fixture
def authoring(case, monkeypatch, tmp_path):
    binding = {
        "work_ref": "fictional-esg-author",
        "client_root": str(case.root),
        "client_id": case.client,
        "engagement_id": case.engagement,
        "run_id": case.prepared["run"]["run_id"],
        "workflow_id": "esg-reporting-assurance",
    }
    configure(monkeypatch, tmp_path, [binding])
    return case, binding


@pytest.fixture
def registered_authoring(authoring, tmp_path, monkeypatch):
    """Exercise closure through the actual studio registry, rather than pilot bindings."""
    fixture, binding = authoring
    env = {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-native-esg-author",
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(
            tmp_path.parent / ("esg-state-" + tmp_path.name)
        ),
    }
    env.pop("VERA_WORKSPACE_BINDINGS")
    archive_cli(env, "configure", "--archive-root", str(fixture.root.parent))
    monkeypatch.delenv("VERA_WORKSPACE_BINDINGS")
    for name in ("VERA_STUDIO_ARCHIVE_SESSION_ID", "VERA_STUDIO_ARCHIVE_STATE_DIR"):
        monkeypatch.setenv(name, env[name])
    return fixture, {
        **binding,
        "work_ref": "studio-"
        + "_".join(
            binding[k].split("_", 1)[1]
            for k in ("client_id", "engagement_id", "run_id")
        ),
    }


def prelude(fixture):
    """Keep app-only tickets in one actual MCP process, never forge the signature."""
    return f"""
const work={{work_ref:{json.dumps(fixture[1]['work_ref'])}}};
const modelPayload=result=>{{if(result.isError)throw new Error(result.content[0].text);return result.structuredContent;}};
const fields={{question:'Interpret the supplied fictional zero with its limits.',command:'bind_evidence',input_ids:[{json.dumps(fixture[0].receipt['input_id'])}],previous_run_id:''}};
const authority=p=>({{...work,revision:p.revision,review_ticket:p.review_ticket,expected_draft_revision:p.draft_revision}});
const setup=()=>payload(call('vera_workspace_esg_author_setup',work));
const mandate=(chosen,key)=>{{
 let page=setup();payload(call('vera_workspace_esg_author_draft_save',{{...authority(page),fields:chosen}}));
 page=setup();return payload(call('vera_workspace_esg_author_request',{{...authority(page),fields:chosen,confirmed:true,idempotency_key:key}}));
}};
const read=(g,c)=>payload(call('vera_workspace_esg_author_read',{{...work,grant_ref:g,...(c?{{case_ref:c}}:{{}})}}));
const stage=(g,proposal,key)=>{{const page=read(g);return call('vera_workspace_esg_author_stage',{{...work,grant_ref:g,revision:page.revision,proposal,idempotency_key:key}});}};
const conserve=(g,c,key)=>{{const page=read(g,c);const args={{...work,grant_ref:g,case_ref:c,revision:page.revision,source_ref:page.source_ref,item_id:c,review_ticket:page.review_ticket,confirmed:true,idempotency_key:key}};return {{first:payload(call('vera_workspace_esg_author_publish',args)),retry:payload(call('vera_workspace_esg_author_publish',args))}};}};
"""


def body(fixture):
    request = bind_request(fixture[0])
    return {
        k: v
        for k, v in request.items()
        if k not in {"idempotency_key", "expected_state_sha256"}
    }


def test_esg_private_partial_draft_is_recoverable_without_grant_or_public_write(
    authoring,
):
    before = (authoring[0].output / "esg_state.json").read_bytes()
    result = rpc_program(
        os.environ.copy(),
        prelude(authoring)
        + """
const initial=setup();fields.question='Unfinished literal question';fields.command='';
const saved=call('vera_workspace_esg_author_draft_save',{...authority(initial),fields});
const result={initial,saved,reopened:setup(),stale:call('vera_workspace_esg_author_draft_save',{...authority(initial),fields})};
""",
    )
    assert result["initial"]["fields"] == {
        "question": "",
        "command": "",
        "input_ids": [],
        "previous_run_id": "",
    }
    assert result["reopened"]["fields"]["question"] == "Unfinished literal question"
    assert result["reopened"]["grants"] == []
    assert result["stale"]["isError"] is True
    assert "fields" not in result["saved"]["structuredContent"]
    assert (authoring[0].output / "esg_state.json").read_bytes() == before


@pytest.mark.parametrize(
    "command", ["start_case", "bind_evidence", "register_source", "build_deliverables"]
)
def test_esg_whole_proposal_previews_privately_then_actual_public_execute_and_exact_retry(
    authoring, command
):
    fixture = authoring[0]
    proposal = body(authoring)
    expected_state_sha256 = fixture.result["state_sha256"]
    if command == "start_case":
        (fixture.output / "esg_state.json").unlink()
        expected_state_sha256 = None
        proposal = {
            "case_id": fixture.request["case_id"],
            "record": fixture.request["record"],
        }
    elif command == "register_source":
        proposal = {
            "id": "fictional-source",
            "record": {
                "title": "Unqualified fictional reference",
                "publisher": "Fictional publisher",
                "url": "https://example.invalid/esg",
                "version": "fictional-2026",
                "applicability_period": {"start": "2026-01-01", "end": "2026-12-31"},
                "review_status": "unverified_seed",
                "catalogue_complete": False,
                "legal_review_approved": False,
                "locator": "Synthetic page",
                "rationale": "Needs source qualification",
            },
        }
    elif command == "build_deliverables":
        proposal = {
            "id": "native-partial",
            "dependencies": [fixture.result["reference"]],
            "claim": "partial_draft",
            "title": "Fictional partial memo",
            "content": "The supplied case is partial. Missing evidence remains missing.",
        }
    before = {p.name: p.read_bytes() for p in fixture.output.iterdir()}
    result = rpc_program(
        os.environ.copy(),
        prelude(authoring)
        + f"""
fields.command={json.dumps(command)};
const grant=mandate(fields,'human-question');
const view=read(grant.grant_ref);
const context=call('vera_workspace_esg_author_context',{{...work,grant_ref:grant.grant_ref,revision:view.revision}});
const staged=modelPayload(stage(grant.grant_ref,{json.dumps(proposal)},'model-proposal'));
const beforePublication=setup();
const page=read(grant.grant_ref,staged.case_ref);
const result={{grant,context,page,beforePublication,publication:conserve(grant.grant_ref,staged.case_ref,'actual-publication'),after:setup()}};
""",
    )
    published = result["publication"]["first"]
    assert published == result["publication"]["retry"]
    assert published["reference"] == result["page"]["preview"]["reference"]
    assert published["professional_confirmation_recorded"] is False
    assert result["after"]["grants"][0]["status"] == "conserved"
    assert result["beforePublication"]["state_sha256"] == expected_state_sha256
    context = result["context"]["structuredContent"]
    assert context["actual_model_reads_verified"] is False
    assert len(context["sources"]) == 1
    assert Path(context["skill_path"]).is_file()
    assert Path(context["proposal_contract_path"]).is_file()
    assert "fields" not in context
    assert "_meta" not in result["context"]
    state = json.loads((fixture.output / "esg_state.json").read_bytes())
    assert (
        state["objects"][-1]["record"] == result["page"]["preview"]["object"]["record"]
    )
    for artifact in published["files"]:
        assert (
            hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest()
            == artifact["sha256"]
        )
    receipt_path = next(
        Path(f["path"])
        for f in published["files"]
        if f["name"].startswith("esg-native-receipt-")
    )
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt["identity_authenticated"] is False
    assert receipt["professional_confirmation_recorded"] is False
    assert receipt["reference"] == published["reference"]
    assert {
        p.name: p.read_bytes()
        for p in fixture.output.iterdir()
        if p.name in before and p.name != "esg_state.json"
    } == {k: v for k, v in before.items() if k != "esg_state.json"}
    if command == "bind_evidence":
        assert state["objects"][-1]["record"]["excerpt"] == "0"
        assert state["objects"][-1]["record"]["observation"]["value"] == "0"
    if command == "register_source":
        assert state["objects"][-1]["record"]["legal_review_approved"] is False
    if command == "build_deliverables":
        assert any(f["name"].endswith(".md") for f in published["files"])


@pytest.mark.parametrize("outcome", ["approved", "rejected", "noted"])
def test_esg_actual_named_human_decision_is_private_until_separate_exact_commit(
    authoring, outcome
):
    fixture = authoring[0]
    evidence = fixture.esg.execute(
        fixture.context, "bind_evidence", bind_request(fixture)
    )
    fields = {
        "id": "native-human-review",
        "type": "scope",
        "decided_by": "Actual fictional reviewer",
        "decided_on": "2026-10-08",
        "outcome": outcome,
        "decision": "The fictional mapping has been personally reviewed.",
        "rationale": "Compared the exact registered CSV cell. Coverage remains partial.",
        "dependency_refs": [evidence["reference"]["sha256"]],
    }
    result = rpc_program(
        os.environ.copy(),
        prelude(authoring)
        + f"""
const chosen={json.dumps(fields)};
const decisionSetup=()=>payload(call('vera_workspace_esg_author_decision_setup',work));
const decisionArgs=p=>({{...authority(p),source_ref:p.state_sha256,item_id:'esg-decision',fields:chosen}});
const initial=decisionSetup();
const unsaved=call('vera_workspace_esg_author_decision_commit',{{...decisionArgs(initial),confirmed:true,idempotency_key:'unsaved'}});
payload(call('vera_workspace_esg_author_decision_draft_save',decisionArgs(initial)));
const reopened=decisionSetup();
const preview=payload(call('vera_workspace_esg_author_decision_preview',decisionArgs(reopened)));
const grant=mandate(fields,'unrelated-model-question');
const grantView=read(grant.grant_ref);
const context=call('vera_workspace_esg_author_context',{{...work,grant_ref:grant.grant_ref,revision:grantView.revision}});
const fresh=decisionSetup(),commit={{...decisionArgs(fresh),confirmed:true,idempotency_key:'actual-human-decision'}};
const first=payload(call('vera_workspace_esg_author_decision_commit',commit));
const result={{initial,unsaved,reopened,preview,context,first,retry:payload(call('vera_workspace_esg_author_decision_commit',commit)),after:decisionSetup()}};
""",
    )
    assert result["unsaved"]["isError"] is True
    assert result["initial"]["fields"]["outcome"] == ""
    assert result["initial"]["fields"]["decided_by"] == ""
    assert result["initial"]["fields"]["decided_on"] == ""
    assert result["reopened"]["fields"] == fields
    assert result["preview"]["preview"]["object"]["record"]["outcome"] == outcome
    assert fields["decision"] not in json.dumps(result["context"])
    assert result["first"] == result["retry"]
    assert result["first"]["professional_confirmation_recorded"] is True
    assert result["first"]["identity_authenticated"] is False
    public = fixture.esg.resume_case(fixture.context)
    assert public["objects"][-1]["record"]["decided_by"] == fields["decided_by"]
    assert public["objects"][-1]["record"]["outcome"] == outcome
    state = json.loads((fixture.output / "esg_state.json").read_bytes())
    assert state["objects"][-1]["dependencies"] == [
        fixture.result["reference"],
        evidence["reference"],
    ]
    assert result["after"]["fields"]["outcome"] == ""


def test_esg_model_cannot_assign_decisions_or_override_server_scope(authoring):
    proposal = body(authoring)
    before = (authoring[0].output / "esg_state.json").read_bytes()
    result = rpc_program(
        os.environ.copy(),
        prelude(authoring)
        + f"""
const grant=mandate(fields,'human-question');
const overrides=stage(grant.grant_ref,{{...{json.dumps(proposal)},idempotency_key:'model-owned'}},'bad-stage');
fields.command='record_decision';const page=setup();
const decision=call('vera_workspace_esg_author_draft_save',{{...authority(page),fields}});
const result={{overrides,decision,after:read(grant.grant_ref)}};
""",
    )
    assert result["overrides"]["isError"] is True
    assert result["decision"]["isError"] is True
    assert result["after"]["proposals"] == []
    assert (authoring[0].output / "esg_state.json").read_bytes() == before


def test_esg_obsolete_open_mandate_keeps_whole_proposal_consultable_and_cancellable(
    authoring,
):
    proposal = body(authoring)
    result = rpc_program(
        os.environ.copy(),
        prelude(authoring)
        + f"""
const old=mandate(fields,'old-question'),oldStage=modelPayload(stage(old.grant_ref,{json.dumps(proposal)},'old-stage'));
const newer=mandate(fields,'new-question'),newStage=modelPayload(stage(newer.grant_ref,{json.dumps(proposal)},'new-stage'));
conserve(newer.grant_ref,newStage.case_ref,'new-publication');
const page=read(old.grant_ref,oldStage.case_ref);
const refused=call('vera_workspace_esg_author_context',{{...work,grant_ref:old.grant_ref,revision:page.revision}});
const cancelled=payload(call('vera_workspace_esg_author_cancel',{{...work,grant_ref:old.grant_ref,case_ref:oldStage.case_ref,revision:page.revision,source_ref:page.source_ref,item_id:oldStage.case_ref,review_ticket:page.review_ticket,confirmed:true,idempotency_key:'obsolete-cancel'}}));
const result={{page,refused,cancelled,after:read(old.grant_ref,oldStage.case_ref)}};
""",
    )
    assert result["page"]["obsolete"] is True
    assert result["page"]["proposal"]["observation"]["value"] == "0"
    assert result["refused"]["isError"] is True
    assert result["cancelled"]["status"] == "cancelled"
    assert result["after"]["preview"] == result["page"]["preview"]


def test_esg_open_mandate_blocks_real_archive_closure_until_cancelled(
    registered_authoring,
):
    fixture, binding = registered_authoring
    write_no_model_report(fixture.output, binding["workflow_id"], binding["run_id"])
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        prelude(registered_authoring)
        + f"""
const selected={json.dumps(selected)},grant=mandate(fields,'closure-question');
const blocked=call('vera_workspace_archive_closure',selected);
const page=read(grant.grant_ref);
payload(call('vera_workspace_esg_author_cancel',{{...work,grant_ref:grant.grant_ref,revision:page.revision,source_ref:page.source_ref,review_ticket:page.review_ticket,confirmed:true,idempotency_key:'closure-cancel'}}));
const result={{blocked,after:payload(call('vera_workspace_archive_closure',selected))}};
""",
    )
    assert result["blocked"]["isError"] is True
    assert "ESG source preparation" in result["blocked"]["content"][0]["text"]
    assert result["after"]["status"] == "running"
    assert result["after"]["report"]["valid"] is True


def test_esg_viewer_cannot_save_or_authorize_literal_fields(authoring, monkeypatch):
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "VIEWER")
    before = (authoring[0].output / "esg_state.json").read_bytes()
    result = rpc_program(
        os.environ.copy(),
        prelude(authoring)
        + """
const page=setup();const result={page,save:call('vera_workspace_esg_author_draft_save',{...authority(page),fields})};
""",
    )
    assert result["page"]["can_write"] is False
    assert result["save"]["isError"] is True
    assert (authoring[0].output / "esg_state.json").read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        "review_ticket:'forged.signature'",
        "confirmed:false",
        "expected_draft_revision:'f'.repeat(64)",
        "revision:'f'.repeat(64)",
        "fields:{...fields,input_ids:['foreign-source']}",
    ],
)
def test_esg_forged_or_changed_question_confirmation_cannot_issue_grant(
    authoring, change
):
    before = (authoring[0].output / "esg_state.json").read_bytes()
    result = rpc_program(
        os.environ.copy(),
        prelude(authoring)
        + f"""
let page=setup();payload(call('vera_workspace_esg_author_draft_save',{{...authority(page),fields}}));page=setup();
const refused=call('vera_workspace_esg_author_request',{{...authority(page),fields,confirmed:true,idempotency_key:'invalid-confirmation',{change}}});
const result={{refused,after:setup()}};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["after"]["grants"] == []
    assert (authoring[0].output / "esg_state.json").read_bytes() == before


def test_esg_model_cannot_bind_an_ungranted_original(authoring):
    proposal = {**body(authoring), "input_id": "foreign-original"}
    before = (authoring[0].output / "esg_state.json").read_bytes()
    result = rpc_program(
        os.environ.copy(),
        prelude(authoring)
        + f"""
const grant=mandate(fields,'grant-one-original');
const refused=stage(grant.grant_ref,{json.dumps(proposal)},'foreign-original-stage');
const result={{refused,after:read(grant.grant_ref)}};
""",
    )
    assert result["refused"]["isError"] is True
    assert "not granted" in result["refused"]["content"][0]["text"]
    assert result["after"]["proposals"] == []
    assert (authoring[0].output / "esg_state.json").read_bytes() == before


def test_esg_changed_whole_proposal_refuses_publication_and_keeps_public_state(
    authoring,
):
    proposal = body(authoring)
    before = (authoring[0].output / "esg_state.json").read_bytes()
    staged = rpc_program(
        os.environ.copy(),
        prelude(authoring)
        + f"""
const grant=mandate(fields,'whole-integrity-question');
const staged=modelPayload(stage(grant.grant_ref,{json.dumps(proposal)},'whole-integrity-stage'));
const result={{grant,staged}};
""",
    )
    path = (
        authoring[0].output.parent
        / ".native-workspace"
        / staged["staged"]["case_ref"]
        / "request.json"
    )
    value = json.loads(path.read_bytes())
    value["observation"][
        "rationale"
    ] = "Altered outside the complete conserved proposal"
    path.write_text(json.dumps(value))
    result = rpc_program(
        os.environ.copy(),
        prelude(authoring)
        + f"""
const result=call('vera_workspace_esg_author_read',{{...work,grant_ref:{json.dumps(staged['grant']['grant_ref'])},case_ref:{json.dumps(staged['staged']['case_ref'])}}});
""",
    )
    assert result["isError"] is True
    assert "proposal changed" in result["content"][0]["text"]
    assert (authoring[0].output / "esg_state.json").read_bytes() == before


def test_esg_native_public_receipts_are_all_declared_before_real_archive_completion(
    registered_authoring,
):
    fixture, binding = registered_authoring
    published = rpc_program(
        os.environ.copy(),
        prelude(registered_authoring)
        + f"""
const grant=mandate(fields,'archive-public-question');
const staged=modelPayload(stage(grant.grant_ref,{json.dumps(body(registered_authoring))},'archive-public-stage'));
const result=conserve(grant.grant_ref,staged.case_ref,'archive-public-conservation');
""",
    )
    write_no_model_report(fixture.output, binding["workflow_id"], binding["run_id"])
    before = {p.name: p.read_bytes() for p in fixture.output.iterdir()}
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        closure_setup(selected)
        + declare_all()
        + """
const finalized=payload(call('vera_workspace_archive_finalize',seal));
const ready=read();
const completed=payload(call('vera_workspace_archive_complete',{...authority(ready),human_reviewed:true,idempotency_key:'actual-fictional-esg-close'}));
const result={finalized,completed};
""",
    )
    manifest = fixture.ledger.validate_run_artifacts(
        fixture.root, fixture.engagement, binding["run_id"]
    )
    assert published["first"] == published["retry"]
    assert result["completed"]["status"] == "completed"
    assert result["completed"]["professional_approval"] is False
    assert {r["path"] for r in manifest["artifacts"]} == set(before)
    assert {p.name: p.read_bytes() for p in fixture.output.iterdir()} == before


def test_esg_explicit_same_engagement_predecessor_carries_exact_history_without_mutation(
    authoring, monkeypatch, tmp_path
):
    fixture, binding = authoring
    fixture.esg.execute(fixture.context, "bind_evidence", bind_request(fixture))
    before = {p.name: p.read_bytes() for p in fixture.output.iterdir()}
    prepared = fixture.ledger.prepare_run(
        fixture.root,
        fixture.client,
        fixture.engagement,
        binding["workflow_id"],
        "development",
        input_ids=[fixture.receipt["input_id"]],
    )
    fixture.ledger.start_run(
        fixture.root, fixture.engagement, prepared["run"]["run_id"]
    )
    successor_binding = {
        **binding,
        "work_ref": "fictional-successor",
        "run_id": prepared["run"]["run_id"],
    }
    configure(monkeypatch, tmp_path, [successor_binding])
    successor = (fixture, successor_binding)
    proposal = {
        "case_id": fixture.request["case_id"],
        "record": fixture.request["record"],
    }
    result = rpc_program(
        os.environ.copy(),
        prelude(successor)
        + f"""
fields.command='start_case';fields.previous_run_id={json.dumps(binding['run_id'])};
const grant=mandate(fields,'explicit-predecessor');
const view=read(grant.grant_ref);
const context=call('vera_workspace_esg_author_context',{{...work,grant_ref:grant.grant_ref,revision:view.revision}});
const staged=modelPayload(stage(grant.grant_ref,{json.dumps(proposal)},'predecessor-stage'));
const result={{context,published:conserve(grant.grant_ref,staged.case_ref,'predecessor-publication')}};
""",
    )
    assert (
        result["context"]["structuredContent"]["previous_case"]["run_id"]
        == binding["run_id"]
    )
    assert {p.name: p.read_bytes() for p in fixture.output.iterdir()} == before
    state = json.loads((Path(prepared["output_dir"]) / "esg_state.json").read_bytes())
    old = json.loads(before["esg_state.json"])
    assert state["objects"] == old["objects"]
    assert state["previous_run_id"] == binding["run_id"]
    assert result["published"]["first"]["professional_confirmation_recorded"] is False
