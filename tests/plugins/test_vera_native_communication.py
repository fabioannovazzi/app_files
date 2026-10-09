"""Actual communication engines and source MCP; all cases are fictional."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tests.plugins._native_review_tickets import assert_same_retained_response
from tests.plugins.test_comunicazione_professionale import (
    _prepared_no_publication_package,
    _recorded_publish_run,
)
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program

__all__ = []


@pytest.fixture
def communication(tmp_path):
    workspace, run, contribution = _recorded_publish_run(
        tmp_path,
        channels=["client_email"],
        visual_requested=False,
        include_history=False,
    )
    return connect(tmp_path, workspace, run)


def connect(base: Path, workspace: Path, run: Path):
    bindings = base / "native-communications.json"
    bindings.write_text(
        json.dumps(
            {
                "tenant_id": "fictional-communication-tenant",
                "actor_id": "fictional-reviewer",
                "bindings": [
                    {
                        "work_ref": "communication-fictional",
                        "workspace": str(workspace),
                        "workspace_id": "studio-aurora",
                        "run_id": run.name,
                    }
                ],
            }
        )
    )
    env = {
        **os.environ,
        "VERA_WORKSPACE_TENANT_ID": "fictional-communication-tenant",
        "VERA_WORKSPACE_ACTOR_ID": "fictional-reviewer",
        "VERA_WORKSPACE_ROLES": "REVIEWER",
        "VERA_WORKSPACE_PYTHON": sys.executable,
        "VERA_COMMUNICATION_WORKSPACE_BINDINGS": str(bindings),
    }
    env.pop("VERA_WORKSPACE_BINDINGS", None)
    return env, workspace, run


PROGRAM = """
const setup=()=>payload(call('vera_workspace_communication_setup',{work_ref:'communication-fictional'}));
const authority=p=>({work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref,review_ticket:p.review_ticket});
const save=(p,fields)=>payload(call('vera_workspace_communication_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields}));
const fields=(p,operation='semantic_review')=>({operation,reviewer:'FICTIONAL_PROFESSIONAL',decisions:Object.fromEntries(p.data.workbench.required_review_scopes.map(scope=>[scope,{decision:'accepted',note:'Fictional operator decision; not a real professional review.'}])),decision:'',note:''});
const execute=(p,field,key)=>{const saved=save(p,field),args={...authority(p),expected_draft_revision:saved.draft_revision,fields:field,confirmed:true,quality_checklist_confirmed:false,idempotency_key:key};return {result:payload(call('vera_workspace_communication_execute',args)),args};};
"""


def test_communication_private_literal_fields_restore_without_review_or_consent(
    communication,
):
    env, _, run = communication
    before = (run / "review_log.json").read_bytes()
    result = rpc_program(
        env,
        PROGRAM
        + """
const page=setup(),f=fields(page);f.reviewer='  literal reviewer  ';f.decisions={};
const saved=save(page,f),stale=call('vera_workspace_communication_draft_save',{...authority(page),expected_draft_revision:page.draft_revision,fields:f}),restored=setup();
const result={saved,stale,restored};
""",
    )
    assert result["restored"]["fields"]["reviewer"] == "  literal reviewer  "
    assert result["restored"]["confirmation_restored"] is False
    assert result["stale"]["isError"] is True
    assert (run / "review_log.json").read_bytes() == before


def test_communication_semantic_matrix_consumed_by_real_public_recorder_and_exact_retry(
    communication,
):
    env, _, run = communication
    result = rpc_program(
        env,
        PROGRAM
        + """
const page=setup(),f=fields(page),step=execute(page,f,'fictional-semantic');
const retry=payload(call('vera_workspace_communication_execute',step.args));
const changed=call('vera_workspace_communication_execute',{...step.args,fields:{...f,reviewer:'changed'}});
const current=setup();const result={page,step:step.result,retry,changed,current};
""",
    )
    events = json.loads((run / "review_log.json").read_text())["events"]
    scopes = result["page"]["data"]["workbench"]["required_review_scopes"]
    assert [event["scope"] for event in events] == scopes
    assert len({event["review_session_id"] for event in events}) == 1
    assert_same_retained_response(result["step"], result["retry"])
    assert result["changed"]["isError"] is True
    assert result["current"]["draft_stale"] is True
    assert result["step"]["sent_or_published"] is False


def test_communication_publish_package_requires_separate_package_review_then_validation(
    communication,
):
    env, _, run = communication
    result = rpc_program(
        env,
        PROGRAM
        + """
execute(setup(),fields(setup()),'fictional-review');
let p=setup(),cleared=payload(call('vera_workspace_communication_draft_clear',{...authority(p),expected_draft_revision:p.draft_revision,confirmed:true}));
p=setup();execute(p,fields(p,'package'),'fictional-package');
p=setup();payload(call('vera_workspace_communication_draft_clear',{...authority(p),expected_draft_revision:p.draft_revision,confirmed:true}));
p=setup();const f=fields(p,'package_review');f.decision='accepted';execute(p,f,'fictional-package-review');
p=setup();payload(call('vera_workspace_communication_draft_clear',{...authority(p),expected_draft_revision:p.draft_revision,confirmed:true}));
p=setup();const completed=execute(p,fields(p,'validate'),'fictional-validation'),current=setup();
const artifact=current.data.artifacts.find(row=>row.name.startsWith('drafts/'));
const downloaded=payload(call('vera_workspace_communication_artifact',{work_ref:p.work_ref,revision:current.revision,source_ref:current.source_ref,artifact_ref:artifact.name}));
const result={completed:completed.result,current,downloaded};
""",
    )
    assert result["current"]["data"]["final"]["status"] == "final_ready"
    assert result["current"]["data"]["final"]["validation_receipt"]
    assert result["downloaded"]["base64"]
    assert result["completed"]["sent_or_published"] is False
    assert not (run / "external_delivery.json").exists()


def test_communication_no_publish_finalizes_internal_records_without_new_package_approval(
    tmp_path,
):
    run = _prepared_no_publication_package(tmp_path)
    env, workspace, run = connect(tmp_path, run.parents[1], run)
    result = rpc_program(
        env,
        PROGRAM
        + """
const p=setup(),step=execute(p,fields(p,'validate'),'fictional-no-publication'),current=setup();
const forbidden=call('vera_workspace_communication_artifact',{work_ref:p.work_ref,revision:current.revision,source_ref:current.source_ref,artifact_ref:'history_identity_map.json'});
const result={current,step:step.result,forbidden};
""",
    )
    final = result["current"]["data"]["final"]
    assert final["status"] == "no_publication_recommended"
    assert "package_review_event_id" not in final["validation_receipt"]
    assert result["forbidden"]["isError"] is True
    assert result["current"]["data"]["history_or_identity_map_returned"] is False
    assert not (run / "drafts").exists()


@pytest.mark.parametrize(
    "invalid", ["missing_scope", "unknown_scope", "no_reviewer", "no_confirmation"]
)
def test_communication_invalid_review_refused_without_public_write_or_pending_intent(
    communication, invalid
):
    env, workspace, run = communication
    before = (run / "review_log.json").read_bytes()
    result = rpc_program(
        env,
        PROGRAM
        + f"const invalid={json.dumps(invalid)};"
        + """
const p=setup(),f=fields(p);if(invalid==='missing_scope')delete f.decisions[p.data.workbench.required_review_scopes[0]];
if(invalid==='unknown_scope')f.decisions.invented={decision:'accepted',note:''};
if(invalid==='no_reviewer')f.reviewer='';
const draft=call('vera_workspace_communication_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f});
let rejected=draft;if(!draft.isError){const saved=payload(draft);rejected=call('vera_workspace_communication_execute',{...authority(p),expected_draft_revision:saved.draft_revision,fields:f,confirmed:invalid!=='no_confirmation',quality_checklist_confirmed:false,idempotency_key:'fictional-refused'});}
const current=setup();const result={rejected,current};
""",
    )
    assert result["rejected"]["isError"] is True
    assert result["current"]["pending_operations"] == []
    assert (run / "review_log.json").read_bytes() == before


def test_communication_current_scope_and_actor_viewer_enforced(communication):
    env, _, run = communication
    result = rpc_program(
        env,
        PROGRAM
        + """
const p=setup(),f=fields(p);process.env.VERA_WORKSPACE_ROLES='VIEWER';
const viewer=setup(),refused=call('vera_workspace_communication_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f});
process.env.VERA_WORKSPACE_ACTOR_ID='other-actor';const actor=call('vera_workspace_communication_setup',{work_ref:p.work_ref});
const result={viewer,refused,actor};
""",
    )
    assert result["viewer"]["can_write"] is False
    assert result["refused"]["isError"] is True
    assert result["actor"]["isError"] is True
    assert json.loads((run / "review_log.json").read_text())["events"] == []


def test_communication_changed_source_refuses_saved_scope(communication):
    env, workspace, run = communication
    result = rpc_program(
        env,
        PROGRAM
        + f"const root={json.dumps(str(run))};"
        + """
const p=setup(),f=fields(p),saved=save(p,f);require('node:fs').appendFileSync(root+'/review_handoff.md','\\nFICTIONAL changed retained handoff');
const refused=call('vera_workspace_communication_execute',{...authority(p),expected_draft_revision:saved.draft_revision,fields:f,confirmed:true,quality_checklist_confirmed:false,idempotency_key:'fictional-stale'});
const current=setup();const result={refused,current};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["current"]["draft_stale"] is True
    assert result["current"]["pending_operations"] == []


def test_communication_uncertain_write_retained_and_never_reexecuted(communication):
    env, workspace, run = communication
    result = rpc_program(
        env,
        PROGRAM
        + """
const p=setup(),f=fields(p,'validate'),saved=save(p,f),args={...authority(p),expected_draft_revision:saved.draft_revision,fields:f,confirmed:true,quality_checklist_confirmed:false,idempotency_key:'fictional-uncertain'};
const first=call('vera_workspace_communication_execute',args),retry=call('vera_workspace_communication_execute',args),current=setup();const result={first,retry,current};
""",
    )
    assert result["first"]["isError"] is True
    assert result["retry"]["isError"] is True
    assert result["current"]["pending_operations"] == ["fictional-uncertain"]
    assert not (run / "final_artifacts.json").exists()


def test_communication_six_routes_app_only_private_projection_and_shared_resource(
    communication,
):
    env, _, _ = communication
    result = rpc_program(
        env,
        """
const tools=service.handle({jsonrpc:'2.0',id:1,method:'tools/list'}).result.tools.filter(tool=>tool.name.startsWith('vera_workspace_communication_'));
const response=call('vera_workspace_communication_setup',{work_ref:'communication-fictional'});
const resource=service.handle({jsonrpc:'2.0',id:1,method:'resources/read',params:{uri:'ui://vera/workspace-v1.html'}}).result;
const result={tools,response,has_component:resource.contents[0].text.includes('VeraCommunication')};
""",
    )
    assert len(result["tools"]) == 6
    assert all(tool["_meta"]["ui"]["visibility"] == ["app"] for tool in result["tools"])
    assert "workbench" not in result["response"]["structuredContent"]
    assert "FICTIONAL_PROFESSIONAL" not in result["response"]["content"][0]["text"]
    assert result["has_component"] is True


def test_communication_no_host_binding_is_explicit_setup_state(communication):
    env, _, _ = communication
    env = {
        key: value
        for key, value in env.items()
        if key != "VERA_COMMUNICATION_WORKSPACE_BINDINGS"
    }
    result = rpc_program(
        env, "const result=payload(call('vera_workspace_communication_catalogue',{}));"
    )
    assert result["configured"] is False
    assert result["works"] == []
    assert result["initial_authoring_available"] is False
