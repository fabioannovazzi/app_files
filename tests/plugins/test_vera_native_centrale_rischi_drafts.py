"""CR source and question drafts stay private, exact and recoverable before authorization."""

from __future__ import annotations

import json

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_centrale_rischi import INSPECT, cr_run

__all__ = []

INTAKE = """
const intakeScope={work_ref:'fictional-cr',kind:'intake'};
const initialDraft=payload(call('vera_workspace_cr_draft_read',intakeScope));
const draftWrite=(exact,current,fields)=>({...exact,revision:current.revision,item_id:current.selection.id,review_ticket:current.review_ticket,expected_draft_revision:current.draft_revision,fields});
"""


def test_cr_intake_draft_reopens_exact_choices_without_inspection_or_confirmation(
    cr_run,
):
    env, output, _ = cr_run
    result = rpc_program(
        env,
        INTAKE
        + """
const setup=payload(call('vera_workspace_cr_setup',{work_ref:'fictional-cr'}));
const fields={input_ids:[setup.items[0].id],offset:30};
const saved=payload(call('vera_workspace_cr_draft_save',draftWrite(intakeScope,initialDraft,fields)));
const reopened=payload(call('vera_workspace_cr_draft_read',intakeScope));
const stale=call('vera_workspace_cr_draft_save',draftWrite(intakeScope,initialDraft,{input_ids:[],offset:0}));
const result={fields,saved,reopened,stale};
""",
    )
    assert result["reopened"]["fields"] == result["fields"]
    assert result["saved"]["model_grant_issued"] is False
    assert result["stale"]["isError"] is True
    assert "confirmed" not in result["reopened"]["fields"]
    assert list(output.glob("cr-*")) == []
    assert list((output.parent / ".native-workspace").glob("cr-grant-*.json")) == []


@pytest.mark.parametrize("cr_run", ["extended"], indirect=True)
def test_cr_literal_questions_and_navigation_recover_per_exact_page_without_grants(
    cr_run,
):
    env, output, _ = cr_run
    result = rpc_program(
        env,
        INSPECT
        + INTAKE
        + """
const navScope={work_ref:exact.work_ref,kind:'navigation',source_ref:inspected.source_ref};
const nav=payload(call('vera_workspace_cr_draft_read',navScope));
const first={table_id:context.context.tables[0].table_id,kind:'values',column:'Durata originaria',offset:0};
const last={...first,offset:30};
const pageScope=selector=>({work_ref:exact.work_ref,kind:'question',source_ref:inspected.source_ref,source_selector:selector});
const firstDraft=payload(call('vera_workspace_cr_draft_read',pageScope(first)));
const lastDraft=payload(call('vera_workspace_cr_draft_read',pageScope(last)));
const literal='Domanda fittizia Ω: __proto__ e valori ancora ignoti.  \\n';
payload(call('vera_workspace_cr_draft_save',draftWrite(pageScope(first),firstDraft,{question:'Prima pagina'})));
payload(call('vera_workspace_cr_draft_save',draftWrite(pageScope(last),lastDraft,{question:literal})));
payload(call('vera_workspace_cr_draft_save',draftWrite(navScope,nav,{source_selector:last})));
const restoredNav=payload(call('vera_workspace_cr_draft_read',navScope));
const restoredPage=payload(call('vera_workspace_cr_source',{work_ref:exact.work_ref,source_ref:inspected.source_ref,source_selector:restoredNav.fields.source_selector}));
const unselectedScope={work_ref:exact.work_ref,kind:'question',source_ref:inspected.source_ref};
const result={literal,restoredNav,restoredPage,first:payload(call('vera_workspace_cr_draft_read',pageScope(first))),last:payload(call('vera_workspace_cr_draft_read',pageScope(last))),unselected:payload(call('vera_workspace_cr_draft_read',unselectedScope))};
""",
    )
    assert result["last"]["fields"]["question"] == result["literal"]
    assert result["first"]["fields"]["question"] == "Prima pagina"
    assert result["unselected"]["fields"]["question"] == ""
    assert result["restoredPage"]["source"]["page"]["offset"] == 30
    assert len(result["restoredPage"]["source"]["page"]["entries"]) == 4
    assert len(list(output.glob("cr-*"))) == 1
    assert len(list((output.parent / ".native-workspace").glob("cr-grant-*.json"))) == 1


def test_cr_question_draft_explicit_empty_save_advances_generation_and_refuses_replay(
    cr_run,
):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        INSPECT
        + INTAKE
        + """
const questionScope={work_ref:exact.work_ref,kind:'question',source_ref:inspected.source_ref};
const read=()=>payload(call('vera_workspace_cr_draft_read',questionScope));
const empty=read();
payload(call('vera_workspace_cr_draft_save',draftWrite(questionScope,empty,{question:'Da discutere'})));
const written=read();
payload(call('vera_workspace_cr_draft_save',draftWrite(questionScope,written,{question:''})));
const cleared=read();
const replay=call('vera_workspace_cr_draft_save',draftWrite(questionScope,written,{question:'Ripristino non autorizzato'}));
const result={empty,cleared,replay};
""",
    )
    assert result["cleared"]["fields"]["question"] == ""
    assert result["cleared"]["draft_revision"] != result["empty"]["draft_revision"]
    assert result["replay"]["isError"] is True


@pytest.mark.parametrize(
    "fields",
    [
        {"input_ids": ["foreign"], "offset": 0},
        {"input_ids": [], "offset": True},
        {"input_ids": [], "offset": -1},
        {"input_ids": [], "offset": 0, "confirmed": True},
    ],
)
def test_cr_intake_draft_refuses_invalid_ids_coordinates_and_manufactured_confirmation(
    cr_run, fields
):
    env, output, _ = cr_run
    result = rpc_program(
        env,
        INTAKE
        + f"const result={{refused:call('vera_workspace_cr_draft_save',draftWrite(intakeScope,initialDraft,{json.dumps(fields)}))}};",
    )
    assert result["refused"]["isError"] is True
    assert (
        list((output.parent / ".native-workspace").glob("cr-local-draft-*.json")) == []
    )


@pytest.mark.parametrize("question", [123, "x" * 4001])
def test_cr_question_draft_refuses_nonliteral_or_over_contract_question(
    cr_run, question
):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        INSPECT
        + INTAKE
        + f"""
const questionScope={{work_ref:exact.work_ref,kind:'question',source_ref:inspected.source_ref}};
const draft=payload(call('vera_workspace_cr_draft_read',questionScope));
const result={{refused:call('vera_workspace_cr_draft_save',draftWrite(questionScope,draft,{{question:{json.dumps(question)}}})),reopened:payload(call('vera_workspace_cr_draft_read',questionScope))}};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["reopened"]["fields"]["question"] == ""


def test_cr_question_signed_selection_cannot_be_reused_for_other_page(cr_run):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        INSPECT
        + INTAKE
        + """
const questionScope={work_ref:exact.work_ref,kind:'question',source_ref:inspected.source_ref};
const draft=payload(call('vera_workspace_cr_draft_read',questionScope));
const source_selector={table_id:context.context.tables[0].table_id,kind:'rows',column:'',offset:0};
const refused=call('vera_workspace_cr_draft_save',{...draftWrite(questionScope,draft,{question:'Altra pagina'}),source_selector});
const result={refused,reopened:payload(call('vera_workspace_cr_draft_read',questionScope))};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["reopened"]["fields"]["question"] == ""


def test_cr_draft_viewer_can_read_but_cannot_save(cr_run):
    env, _, _ = cr_run
    viewer = {**env, "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        viewer,
        INTAKE
        + "const result={initialDraft,refused:call('vera_workspace_cr_draft_save',draftWrite(intakeScope,initialDraft,{input_ids:[],offset:0}))};",
    )
    assert result["initialDraft"]["can_write"] is False
    assert result["refused"]["isError"] is True


def test_cr_draft_save_uncertain_public_write_preserves_previous_selection(cr_run):
    env, output, _ = cr_run
    fixture = rpc_program(
        env,
        INTAKE
        + """
const setup=payload(call('vera_workspace_cr_setup',{work_ref:'fictional-cr'}));
payload(call('vera_workspace_cr_draft_save',draftWrite(intakeScope,initialDraft,{input_ids:[setup.items[0].id],offset:0})));
const current=payload(call('vera_workspace_cr_draft_read',intakeScope));
const result={write:draftWrite(intakeScope,current,{input_ids:[],offset:0})};
""",
    )
    private = output.parent / ".native-workspace"
    path = next(private.glob("cr-local-draft-*.json"))
    before = path.read_bytes()
    (private / ("cr-request-" + "a" * 64 + ".json")).write_text("{}")
    result = rpc_program(
        env,
        f"const result=call('vera_workspace_cr_draft_save',{json.dumps(fixture['write'])});",
    )
    assert result["isError"] is True
    assert path.read_bytes() == before


def test_cr_intake_draft_ticket_does_not_authorize_public_inspection(cr_run):
    env, output, _ = cr_run
    result = rpc_program(
        env,
        INTAKE
        + """
const setup=payload(call('vera_workspace_cr_setup',{work_ref:'fictional-cr'}));
const refused=call('vera_workspace_cr_inspect',{work_ref:intakeScope.work_ref,revision:initialDraft.revision,review_ticket:initialDraft.review_ticket,input_ids:[setup.items[0].id],confirmed:true,human_reviewed:true,idempotency_key:'draft-is-not-inspection'});
const result={refused};
""",
    )
    assert result["refused"]["isError"] is True
    assert list(output.glob("cr-*")) == []


@pytest.mark.parametrize("change", ["owner", "inputs", "implementation"])
def test_cr_changed_draft_scope_refuses_recovery_without_adoption(cr_run, change):
    env, output, _ = cr_run
    rpc_program(
        env,
        INTAKE
        + "payload(call('vera_workspace_cr_draft_save',draftWrite(intakeScope,initialDraft,{input_ids:[],offset:0})));const result={saved:true};",
    )
    path = next((output.parent / ".native-workspace").glob("cr-local-draft-*.json"))
    record = json.loads(path.read_text())
    record[change] = "foreign"
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    result = rpc_program(
        env,
        "const result=call('vera_workspace_cr_draft_read',{work_ref:'fictional-cr',kind:'intake'});",
    )
    assert result["isError"] is True
    assert path.read_bytes() == before


def test_cr_local_drafts_are_app_only_and_do_not_expose_unissued_questions(cr_run):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        INSPECT
        + INTAKE
        + """
const questionScope={work_ref:exact.work_ref,kind:'question',source_ref:inspected.source_ref};
const questionDraft=payload(call('vera_workspace_cr_draft_read',questionScope));
payload(call('vera_workspace_cr_draft_save',draftWrite(questionScope,questionDraft,{question:'Domanda ancora privata, non autorizzata'})));
const declarations=service.handle({jsonrpc:'2.0',id:2,method:'tools/list'}).result.tools.filter(t=>['vera_workspace_cr_draft_read','vera_workspace_cr_draft_save'].includes(t.name));
const result={declarations,modelContext:model('vera_workspace_cr_model_context',exact)};
""",
    )
    assert len(result["declarations"]) == 2
    assert all(
        v["_meta"]["ui"]["visibility"] == ["app"] for v in result["declarations"]
    )
    assert result["modelContext"]["question"] == "Spiega le esposizioni fittizie.  "
    assert "Domanda ancora privata" not in json.dumps(result["modelContext"])
