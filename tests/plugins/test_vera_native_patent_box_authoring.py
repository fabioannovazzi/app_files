"""Real source MCP, fictional Archive; complete public preflight without model/host claims."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_patent_box import (
    owned_patent_box,
    program,
    public_files,
)

__all__ = []


def author_program(fixture):
    return (
        program(fixture)
        + """
const authorSetup=()=>payload(call('vera_workspace_patent_box_author_setup',{work_ref:workRef}));
const authorScope=p=>({work_ref:workRef,revision:p.revision,source_ref:p.source_ref});
const authorWrite=p=>({...authorScope(p),review_ticket:p.review_ticket});
const requested=(task='propose',input_ids)=>{
 const page=authorSetup();const fields={task,question:'  FICTIONAL complete preparation; keep unsupported decisions open.  ',input_ids:input_ids||page.sources.map(s=>s.input_id),record_refs:Object.keys(page.records)};
 const saved=payload(call('vera_workspace_patent_box_author_draft_save',{...authorWrite(page),expected_draft_revision:page.draft_revision,fields}));
 const args={...authorWrite(page),expected_draft_revision:saved.draft_revision,fields,confirmed:true,idempotency_key:'fictional-'+task+'-request'};
 const mandate=payload(call('vera_workspace_patent_box_author_request',args));
 const scope={...authorScope(page),grant_ref:mandate.grant_ref};return {page,fields,mandate,args,scope};
};
const modelPayload=result=>{if(result.isError)throw new Error(result.content[0].text);return result.structuredContent;};
const context=(scope,key='fictional-context')=>modelPayload(call('vera_workspace_patent_box_author_context',{...scope,idempotency_key:key}));
const metadata={runtime_profile:'openai-codex',provider:'FICTIONAL_TEST_TRANSPORT',model:'NO_MODEL_EXECUTED',template_ref:'fixture-v1',model_session_ref:'fictional-test-session'};
"""
    )


def test_patent_box_author_question_private_cas_and_no_restored_confirmation(
    owned_patent_box,
):
    fixture = owned_patent_box()
    before = public_files(fixture)
    result = rpc_program(
        fixture[0],
        author_program(fixture)
        + """
const page=authorSetup(),fields={task:'',question:'  literal unfinished  ',input_ids:[],record_refs:[]};
const saved=payload(call('vera_workspace_patent_box_author_draft_save',{...authorWrite(page),expected_draft_revision:page.draft_revision,fields}));
const stale=call('vera_workspace_patent_box_author_draft_save',{...authorWrite(page),expected_draft_revision:page.draft_revision,fields});
const reopened=authorSetup();const refused=call('vera_workspace_patent_box_author_request',{...authorWrite(reopened),expected_draft_revision:reopened.draft_revision,fields,idempotency_key:'no-consent'});
const result={saved,stale,reopened,refused};
""",
    )
    assert result["reopened"]["fields"]["question"] == "  literal unfinished  "
    assert result["reopened"]["confirmation_restored"] is False
    assert result["stale"]["isError"] is True
    assert result["refused"]["isError"] is True
    assert public_files(fixture) == before


def test_patent_box_author_whole_proposal_stage_adopt_then_explicit_public_execution(
    owned_patent_box,
):
    fixture = owned_patent_box()
    before = public_files(fixture)
    result = rpc_program(
        fixture[0],
        author_program(fixture)
        + f"const body={json.dumps(fixture[1]['proposal'])};\n"
        + """
const request=requested();const ctx=context(request.scope);
const source=modelPayload(call('vera_workspace_patent_box_author_source',{...request.scope,input_id:request.page.sources[0].input_id,idempotency_key:'fictional-source'}));
const stageArgs={...request.scope,body,metadata,idempotency_key:'fictional-stage'};
const stage=modelPayload(call('vera_workspace_patent_box_author_stage',stageArgs));
const preview=payload(call('vera_workspace_patent_box_author_read',{...request.scope,stage_ref:stage.stage_ref}));
const page=authorSetup(),producer=setup('propose');
const adoptArgs={...authorWrite(page),grant_ref:request.mandate.grant_ref,stage_ref:stage.stage_ref,selected_stage_ref:stage.stage_ref,expected_producer_draft_revision:producer.draft_revision,replace_fields_confirmed:true,confirmed:true,idempotency_key:'fictional-adopt'};
const adopted=payload(call('vera_workspace_patent_box_author_adopt',adoptArgs));
const exactRetry=payload(call('vera_workspace_patent_box_author_adopt',adoptArgs));
const typed=setup('propose');
const executed=payload(call('vera_workspace_patent_box_execute',{...authority(typed),fields:typed.fields,confirmed:true,idempotency_key:'fictional-publish-after-adoption'}));
const result={ctx,source,stage,preview,adopted,exactRetry,typed,executed};
""",
    )
    assert result["ctx"]["session"]["run_id"] == fixture[1]["binding"]["run_id"]
    assert all("selected_path" not in x for x in result["ctx"]["session"]["inputs"])
    assert result["source"]["text_returned"] is True
    assert result["source"]["actual_host_read_verified"] is False
    assert result["preview"]["body"] == fixture[1]["proposal"]
    assert result["preview"]["metadata"]["model"] == "NO_MODEL_EXECUTED"
    assert result["preview"]["reads"][0]["provider_telemetry"] == "not_measurable"
    assert result["adopted"] == result["exactRetry"]
    assert result["adopted"]["public_outputs_written"] is False
    assert result["typed"]["fields"] == {"proposal": fixture[1]["proposal"]}
    assert result["typed"]["confirmation_restored"] is False
    assert (
        result["executed"]["public_result"]["proposal_digest"]
        == result["preview"]["preview"]["prospective_digest"]
    )
    assert before.items() <= public_files(fixture).items()
    assert not any(k.startswith("decision_") for k in public_files(fixture))


def test_patent_box_author_normalization_preflight_uses_complete_existing_tables(
    owned_patent_box,
):
    fixture = owned_patent_box("normalized")
    before = public_files(fixture)
    result = rpc_program(
        fixture[0],
        author_program(fixture)
        + f"const body={json.dumps(fixture[1]['plan'])};\n"
        + """
const request=requested('normalize_ledger');const ctx=context(request.scope);
const stage=modelPayload(call('vera_workspace_patent_box_author_stage',{...request.scope,body,metadata,idempotency_key:'fictional-normalization-stage'}));
const preview=payload(call('vera_workspace_patent_box_author_read',{...request.scope,stage_ref:stage.stage_ref}));
const producer=setup('normalize_ledger'),page=authorSetup();
const adopted=payload(call('vera_workspace_patent_box_author_adopt',{...authorWrite(page),grant_ref:request.mandate.grant_ref,stage_ref:stage.stage_ref,selected_stage_ref:stage.stage_ref,expected_producer_draft_revision:producer.draft_revision,replace_fields_confirmed:true,confirmed:true,idempotency_key:'fictional-normalization-adopt'}));
const typed=setup('normalize_ledger');
const executed=payload(call('vera_workspace_patent_box_execute',{...authority(typed),fields:typed.fields,confirmed:true,idempotency_key:'fictional-normalization-public'}));
const result={ctx,preview,adopted,executed};
""",
    )
    assert result["preview"]["body"] == fixture[1]["plan"]
    assert (
        result["preview"]["preview"]["normalization"]
        == result["executed"]["public_result"]
    )
    assert result["preview"]["preview"]["public_outputs_written"] is False
    assert before.items() <= public_files(fixture).items()


@pytest.mark.parametrize(
    "fault", ["run_id", "cost_population", "evidence", "missing_read", "provenance"]
)
def test_patent_box_author_rejects_invalid_whole_proposal_without_public_or_pending_write(
    owned_patent_box, fault
):
    fixture = owned_patent_box()
    before = public_files(fixture)
    changes = {
        "run_id": "body.case.case_id='another-run';",
        "cost_population": "body.case.costs[0].book_amount='1.00';",
        "evidence": "body.case.evidence=[];",
        "missing_read": "",
        "provenance": "delete metadata.model_session_ref;",
    }
    read = "" if fault == "missing_read" else "context(request.scope);"
    result = rpc_program(
        fixture[0],
        author_program(fixture)
        + f"const body={json.dumps(fixture[1]['proposal'])};\n"
        + "const request=requested();"
        + read
        + changes[fault]
        + """
const refused=call('vera_workspace_patent_box_author_stage',{...request.scope,body,metadata,idempotency_key:'invalid-stage'});const reopened=authorSetup();const result={refused,reopened};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["reopened"]["can_write"] is True
    assert public_files(fixture) == before


def test_patent_box_author_unselected_original_refused_and_cancellation_preserves_receipts(
    owned_patent_box,
):
    fixture = owned_patent_box()
    before = public_files(fixture)
    result = rpc_program(
        fixture[0],
        author_program(fixture)
        + """
const initial=authorSetup();const request=requested('propose',[initial.sources[0].input_id]);context(request.scope);
const refused=call('vera_workspace_patent_box_author_source',{...request.scope,input_id:initial.sources[1].input_id,idempotency_key:'wrong-source'});
const page=authorSetup();const cancelled=payload(call('vera_workspace_patent_box_author_cancel',{...authorWrite(page),grant_ref:request.mandate.grant_ref,confirmed:true,idempotency_key:'fictional-cancel'}));
const closed=call('vera_workspace_patent_box_author_context',{...request.scope,idempotency_key:'fictional-context'});
const reread=payload(call('vera_workspace_patent_box_author_read',{...request.scope,stage_ref:''}));
const result={refused,cancelled,closed,reread};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["cancelled"]["status"] == "cancelled"
    assert result["closed"]["isError"] is True
    assert len(result["reread"]["reads"]) == 1
    assert public_files(fixture) == before


def test_patent_box_author_open_mandate_blocks_public_execution(owned_patent_box):
    fixture = owned_patent_box()
    before = public_files(fixture)
    result = rpc_program(
        fixture[0],
        author_program(fixture)
        + """
const request=requested();const refused=call('vera_workspace_patent_box_execute',{...authority(setup('calculate')),fields:{digest:'0'.repeat(64)},confirmed:true,idempotency_key:'during-open-mandate'});const result={refused};
""",
    )
    assert result["refused"]["isError"] is True
    assert "mandate" in result["refused"]["content"][0]["text"]
    assert public_files(fixture) == before


def test_patent_box_author_wrong_actor_and_viewer_cannot_reuse_mandate(
    owned_patent_box,
):
    fixture = owned_patent_box()
    request = rpc_program(
        fixture[0],
        author_program(fixture)
        + "const request=requested();context(request.scope);const result=request.scope;",
    )
    program_read = (
        "const result=call('vera_workspace_patent_box_author_context',"
        + json.dumps({**request, "idempotency_key": "fictional-context"})
        + ");"
    )
    viewer = rpc_program({**fixture[0], "VERA_WORKSPACE_ROLES": "VIEWER"}, program_read)
    other = rpc_program(
        {**fixture[0], "VERA_WORKSPACE_ACTOR_ID": "different-fictional-reviewer"},
        program_read,
    )
    assert viewer["isError"] is True
    assert other["isError"] is True


def test_patent_box_author_changed_public_scope_and_private_packet_refuse_model_read(
    owned_patent_box,
):
    fixture = owned_patent_box()
    request = rpc_program(
        fixture[0],
        author_program(fixture)
        + "const request=requested();context(request.scope);const result=request.scope;",
    )
    output = Path(fixture[1]["output"])
    private = output.parent / ".native-workspace"
    packet = next(private.glob("patent-box-author-*/mandate-*/read-*.json"))
    packet.write_text(packet.read_text() + " ")
    result = rpc_program(
        fixture[0],
        "const result=call('vera_workspace_patent_box_author_context',"
        + json.dumps({**request, "idempotency_key": "fictional-context"})
        + ");",
    )
    assert result["isError"] is True
    assert "receipt changed" in result["content"][0]["text"]


def test_patent_box_author_tools_have_three_model_routes_and_app_only_adoption(
    owned_patent_box,
):
    fixture = owned_patent_box()
    result = rpc_program(
        fixture[0],
        "const result=require('./plugins/vera/mcp/workspace.cjs').handle({jsonrpc:'2.0',id:2,method:'tools/list'}).result.tools.filter(t=>t.name.startsWith('vera_workspace_patent_box_author_'));",
    )
    assert len(result) == 10
    assert {
        r["name"].removeprefix("vera_workspace_patent_box_author_")
        for r in result
        if r["_meta"]["ui"]["visibility"] == ["app", "model"]
    } == {"context", "source", "stage"}
    assert next(r for r in result if r["name"].endswith("_adopt"))["_meta"]["ui"][
        "visibility"
    ] == ["app"]


def test_patent_box_author_whole_large_proposal_is_not_cut_to_old_envelope(
    owned_patent_box,
):
    fixture = owned_patent_box()
    before = public_files(fixture)
    result = rpc_program(
        fixture[0],
        author_program(fixture)
        + f"const body={json.dumps(fixture[1]['proposal'])};\n"
        + """
const request=requested();context(request.scope);body.narratives[0].text='FICTIONAL located complete narrative. '.repeat(5000);
const stage=modelPayload(call('vera_workspace_patent_box_author_stage',{...request.scope,body,metadata,idempotency_key:'fictional-large-stage'}));
const read=payload(call('vera_workspace_patent_box_author_read',{...request.scope,stage_ref:stage.stage_ref}));
const result={bytes:Buffer.byteLength(JSON.stringify(body)),original:body.narratives[0].text,read:read.body.narratives[0].text};
""",
    )
    assert result["bytes"] > 128000
    assert result["read"] == result["original"]
    assert public_files(fixture) == before


def test_patent_box_author_changed_public_bytes_require_new_mandate_and_allow_explicit_cancel(
    owned_patent_box,
):
    fixture = owned_patent_box()
    request = rpc_program(
        fixture[0],
        author_program(fixture)
        + "const request=requested();context(request.scope);const result=request.scope;",
    )
    (Path(fixture[1]["output"]) / "ordinary_specialist_note.md").write_text(
        "Changed fictional public scope"
    )
    result = rpc_program(
        fixture[0],
        author_program(fixture)
        + f"const original={json.dumps(request)};\n"
        + """
const page=authorSetup();const obsolete=call('vera_workspace_patent_box_author_context',{...original,idempotency_key:'fictional-context'});
const read=payload(call('vera_workspace_patent_box_author_read',{...authorScope(page),grant_ref:original.grant_ref,stage_ref:''}));
const cancelled=payload(call('vera_workspace_patent_box_author_cancel',{...authorWrite(page),grant_ref:original.grant_ref,confirmed:true,idempotency_key:'fictional-stale-cancel'}));const result={obsolete,read,cancelled};
""",
    )
    assert result["obsolete"]["isError"] is True
    assert result["read"]["obsolete"] is True
    assert result["cancelled"]["status"] == "cancelled"


def test_patent_box_author_open_mandate_blocks_actual_archive_closure(owned_patent_box):
    fixture = owned_patent_box()
    binding = {
        k: fixture[1]["binding"][k] for k in ("client_id", "engagement_id", "run_id")
    }
    result = rpc_program(
        fixture[0],
        author_program(fixture)
        + f"const binding={json.dumps(binding)};\n"
        + """
const request=requested();const result=call('vera_workspace_archive_closure',binding);
""",
    )
    assert result["isError"] is True
    assert (
        "model mandate requires disposition or recovery before closure"
        in result["content"][0]["text"]
    )
