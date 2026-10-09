"""Actual owned Archive and public grant producer; fictional model outputs only."""

from __future__ import annotations

import hashlib
import json

import pytest

from tests.plugins.test_bandi_agevolazioni_plugin import _model_output, _recommendation
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_bandi import (  # noqa: F401
    output_bytes,
    owned_bandi,
)

__all__ = []

TASKS = [
    "WORKFLOW_GUIDANCE",
    "SOURCE_INTERPRETATION",
    "REQUIREMENT_DRAFTING",
    "EVIDENCE_MAPPING",
    "ASSESSMENT_REASONING",
    "COST_CLASSIFICATION",
    "FORM_PORTAL_GUIDANCE",
    "NARRATIVE_DRAFTING",
    "CONSISTENCY_REVIEW",
    "MISSING_INFO_RED_FLAGS",
    "AUTHORITY_SIMULATION",
]


def program(fixture, *, task="WORKFLOW_GUIDANCE", raw_ids=()):
    """Use actual signed app scope; model tools return complete structured content."""
    return f"""
const identity={{work_ref:{json.dumps(fixture[1]['work_ref'])}}};
const setup=()=>payload(call('vera_workspace_bandi_author_setup',identity));
const authority=p=>({{...identity,revision:p.revision,source_ref:p.source_ref,review_ticket:p.review_ticket}});
const model=r=>{{if(r.isError)throw new Error(r.content[0].text);return r.structuredContent;}};
const taskFields={{task:{json.dumps(task)},subject_ids:['SRC-CALL-001'],model_session_ref:'FICTIONAL-SEPARATE-SESSION-001',raw_source_ids:{json.dumps(list(raw_ids))}}};
const initial=setup();
const saved=payload(call('vera_workspace_bandi_author_draft_save',{{...authority(initial),expected_draft_revision:initial.draft_revision,fields:taskFields}}));
const requestArgs={{...authority(initial),fields:taskFields,expected_draft_revision:saved.draft_revision,confirmed:true,fresh_session_confirmed:true,idempotency_key:'fictional-task-request'}};
"""


def requested(fixture, **kwargs):
    return (
        program(fixture, **kwargs)
        + """
const mandate=payload(call('vera_workspace_bandi_author_request',requestArgs));
const grantScope=p=>({work_ref:identity.work_ref,grant_ref:mandate.grant_ref,revision:p.revision,source_ref:p.source_ref});
"""
    )


def staged(fixture, *, proposal=None, **kwargs):
    response = proposal or _model_output(_recommendation())
    return (
        requested(fixture, **kwargs)
        + f"""
const stageArgs={{...grantScope(setup()),proposal:{json.dumps(response)},metadata:{{provider:'fictional-no-provider-call',model:'fictional-no-model-run',prompt_template_version:'bandi-intelligence-v2'}},idempotency_key:'fictional-private-stage'}};
const staged=model(call('vera_workspace_bandi_author_stage',stageArgs));
"""
    )


def recorded(fixture, **kwargs):
    return (
        staged(fixture, **kwargs)
        + """
const recordArgs={...authority(setup()),grant_ref:mandate.grant_ref,stage_ref:staged.stage_ref,confirmed:true,idempotency_key:'fictional-public-record'};
const recorded=payload(call('vera_workspace_bandi_author_record',recordArgs));
"""
    )


@pytest.mark.parametrize("task", TASKS)
def test_all_public_tasks_preserve_exact_packet_and_private_proposals(
    owned_bandi, task
):
    fixture = owned_bandi()
    before = output_bytes(fixture[2])
    result = rpc_program(
        fixture[0],
        staged(fixture, task=task)
        + """
const current=setup();
const context=model(call('vera_workspace_bandi_author_context',grantScope(current)));
const preview=payload(call('vera_workspace_bandi_author_read',{...grantScope(current),stage_ref:staged.stage_ref}));
const result={initial,staged,context,preview,current};
""",
    )
    packet = result["context"]["packet"]
    expected = hashlib.sha256(
        json.dumps(
            packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    assert result["context"]["packet_sha256"] == expected
    assert packet["task"] == task
    assert result["initial"]["tasks"] == TASKS
    assert result["preview"]["proposal"] == _model_output(_recommendation())
    assert result["staged"]["public_case_changed"] is False
    assert result["current"]["confirmation_restored"] is False
    assert result["context"]["actual_model_reads_verified"] is False
    assert output_bytes(fixture[2]) == before


@pytest.mark.parametrize("missing", ["confirmed", "fresh_session_confirmed"])
def test_task_authorization_requires_each_renewed_confirmation(owned_bandi, missing):
    fixture = owned_bandi()
    before = output_bytes(fixture[2])
    result = rpc_program(
        fixture[0],
        program(fixture)
        + f"""
const args={{...requestArgs}};delete args[{json.dumps(missing)}];
const result=call('vera_workspace_bandi_author_request',args);
""",
    )
    assert result["isError"] is True
    assert output_bytes(fixture[2]) == before


@pytest.mark.parametrize("decision", ["accepted", "returned", "rejected"])
def test_separate_public_registration_disposition_and_exact_retries(
    owned_bandi, decision
):
    fixture = owned_bandi()
    before = output_bytes(fixture[2])
    result = rpc_program(
        fixture[0],
        recorded(fixture)
        + f"""
const stageRetry=model(call('vera_workspace_bandi_author_stage',stageArgs));
const recordRetry=payload(call('vera_workspace_bandi_author_record',recordArgs));
const args={{...authority(setup()),grant_ref:mandate.grant_ref,fields:{{decision:{json.dumps(decision)},reviewer_id:'fictional-reviewer',reviewer_role:'fictional-commercialista',notes:'Explicit fixture disposition; no filing approval.'}},confirmed:true,idempotency_key:'fictional-public-decision'}};
const decided=payload(call('vera_workspace_bandi_author_decide',args));
const retry=payload(call('vera_workspace_bandi_author_decide',args));
const result={{recorded,recordRetry,staged,stageRetry,decided,retry,current:setup()}};
""",
    )
    assert result["recorded"]["status"] == "MODEL_SUGGESTED"
    assert result["recorded"] == result["recordRetry"]
    assert result["staged"] == result["stageRetry"]
    assert result["decided"] == result["retry"]
    assert result["decided"]["status"] == decision.upper()
    assert result["current"]["grants"][0]["status"] == "decided"
    assert json.loads(
        (fixture[2] / "application_workbench.json").read_text()
    ) == json.loads(before["application_workbench.json"])
    assert (fixture[2] / "case_intake.json").read_bytes() == before["case_intake.json"]
    assert (fixture[2] / "source_register.json").read_bytes() == before[
        "source_register.json"
    ]


def test_source_task_reads_only_explicit_original_and_omits_private_project(
    owned_bandi,
):
    fixture = owned_bandi()
    result = rpc_program(
        fixture[0],
        requested(fixture, task="SOURCE_INTERPRETATION", raw_ids=["SRC-CALL-001"])
        + """
const mandateScope=grantScope(setup());
const context=model(call('vera_workspace_bandi_author_context',mandateScope));
const source=model(call('vera_workspace_bandi_author_source',{...mandateScope,source_id:'SRC-CALL-001'}));
const denied=call('vera_workspace_bandi_author_source',{...mandateScope,source_id:'SRC-OTHER-001'});
const result={context,source,denied};
""",
    )
    assert "project" not in result["context"]["packet"]["case_context"]
    assert "professional_question" not in result["context"]["packet"]["case_context"]
    assert result["source"]["untrusted_evidence"] is True
    assert (
        hashlib.sha256(result["source"]["content"].encode()).hexdigest()
        == result["source"]["sha256"]
    )
    assert result["denied"]["isError"] is True


def test_structured_task_refuses_raw_original_selection(owned_bandi):
    fixture = owned_bandi()
    result = rpc_program(
        fixture[0],
        program(fixture, raw_ids=["SRC-CALL-001"])
        + """
const result=call('vera_workspace_bandi_author_request',requestArgs);
""",
    )
    assert result["isError"] is True
    assert "data boundary" in result["content"][0]["text"]


def test_cancel_retains_private_evidence_and_rejects_session_reuse(owned_bandi):
    fixture = owned_bandi()
    before = output_bytes(fixture[2])
    result = rpc_program(
        fixture[0],
        requested(fixture)
        + """
const current=setup();
const args={...authority(current),grant_ref:mandate.grant_ref,confirmed:true,idempotency_key:'fictional-cancel'};
const cancelled=payload(call('vera_workspace_bandi_author_cancel',args));
const retry=payload(call('vera_workspace_bandi_author_cancel',args));
const page=setup();
const reSaved=payload(call('vera_workspace_bandi_author_draft_save',{...authority(page),expected_draft_revision:page.draft_revision,fields:taskFields}));
const reused=call('vera_workspace_bandi_author_request',{...requestArgs,...authority(page),expected_draft_revision:reSaved.draft_revision,idempotency_key:'fictional-reused-session'});
const result={cancelled,retry,reused,page};
""",
    )
    assert result["cancelled"] == result["retry"]
    assert result["page"]["grants"][0]["status"] == "cancelled"
    assert result["reused"]["isError"] is True
    assert "already authorized" in result["reused"]["content"][0]["text"]
    assert output_bytes(fixture[2]) == before


def test_pending_mandate_blocks_archive_closure_and_viewer_model_access(owned_bandi):
    fixture = owned_bandi()
    result = rpc_program(
        fixture[0],
        requested(fixture)
        + f"""
const mandateScope=grantScope(setup());
const closure=call('vera_workspace_archive_closure',{json.dumps({k:fixture[1][k] for k in ('client_id','engagement_id','run_id')})});
process.env.VERA_WORKSPACE_ROLES='VIEWER';
const denied=call('vera_workspace_bandi_author_context',mandateScope);
const result={{closure,denied}};
""",
    )
    assert result["closure"]["isError"] is True
    assert "contributions require" in result["closure"]["content"][0]["text"]
    assert result["denied"]["isError"] is True


def test_explicit_stale_transition_preserves_changed_case_and_suggestion(owned_bandi):
    fixture = owned_bandi()
    result = rpc_program(
        fixture[0],
        recorded(fixture)
        + f"""
const fs=require('node:fs');
const path={json.dumps(str(fixture[2] / 'case_intake.json'))};
const intake=JSON.parse(fs.readFileSync(path,'utf8'));intake.reference_date='2026-10-09';fs.writeFileSync(path,JSON.stringify(intake,null,2)+'\\n');
const before=fs.readFileSync(path,'utf8');
const fields={{decision:'returned',reviewer_id:'fictional-reviewer',reviewer_role:'fictional-commercialista',notes:'Recognize changed inputs, no substantive decision.'}};
const args={{...authority(setup()),grant_ref:mandate.grant_ref,fields,confirmed:true,idempotency_key:'fictional-expire'}};
const refused=call('vera_workspace_bandi_author_decide',args);
const expired=payload(call('vera_workspace_bandi_author_expire',args));
const retry=payload(call('vera_workspace_bandi_author_expire',args));
const result={{refused,expired,retry,casePreserved:fs.readFileSync(path,'utf8')===before,current:setup()}};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["expired"]["status"] == "STALE"
    assert result["expired"]["decision"] is None
    assert result["retry"] == result["expired"]
    assert result["casePreserved"] is True
    assert result["current"]["grants"][0]["status"] == "stale"


def test_changed_immutable_packet_refuses_preview_and_archive_closure(owned_bandi):
    fixture = owned_bandi()
    private = fixture[2].parent / ".native-workspace"
    result = rpc_program(
        fixture[0],
        requested(fixture)
        + f"""
const mandateScope=grantScope(setup());
const fs=require('node:fs'),path=require('node:path'),base={json.dumps(str(private))};
const actor=fs.readdirSync(base).find(name=>name.startsWith('bandi-author-'));
fs.appendFileSync(path.join(base,actor,mandate.grant_ref,'packet.json'),' ');
const read=call('vera_workspace_bandi_author_context',mandateScope);
const closure=call('vera_workspace_archive_closure',{json.dumps({k:fixture[1][k] for k in ('client_id','engagement_id','run_id')})});
const result={{read,closure}};
""",
    )
    assert result["read"]["isError"] is True
    assert "packet changed" in result["read"]["content"][0]["text"]
    assert result["closure"]["isError"] is True
