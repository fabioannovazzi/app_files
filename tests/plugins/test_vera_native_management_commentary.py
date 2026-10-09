"""Whole management commentary and unchanged finalizer on fictional Archive runs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_vera_native_archive_closure import declare_all, setup
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_management_execution import (  # noqa: F401
    management_run,
)
from tests.plugins.test_vera_native_management_mcp import (  # noqa: F401
    calculated,
    registered_management_run,
)
from tests.plugins.test_vera_native_workspace import workspace_module

__all__ = []
READBACK = {
    "decision": "accepted",
    "reviewer": "Fictional management reviewer",
    "reviewed_at": "2026-10-08T04:17:00+02:00",
    "basis": "Fictional readback of the whole commentary, references and open limits.",
}


def proposed(fixture) -> str:
    return (
        calculated(fixture)
        + """
const identity={...work,source_ref:prepared.source_ref};
const commentarySetup=payload(call('vera_workspace_management_commentary_setup',identity));
const contextCall=call('vera_workspace_management_commentary_context',{...identity,revision:commentarySetup.revision});
if(contextCall.isError)throw new Error(contextCall.content[0].text);
const context=contextCall.structuredContent;
const firstMetric=context.model_context.metrics[0];
const metric=firstMetric.metric_id||firstMetric.id;
const commentary={...context.commentary_template,observations:[{text:'Fictional observation of this exact calculated metric.',metric_ids:[metric]}],hypotheses:[{text:'Fictional hypothesis requiring independent evidence; no cause established.',metric_ids:[metric]}],questions:[{text:'Which evidence supports the interpretation?',metric_ids:[]}],limitations:[{text:'Fictional test; no actual model or professional acceptance.',metric_ids:[]}]};
const stageArgs={...identity,revision:commentarySetup.revision,commentary,idempotency_key:'fictional-management-commentary-stage'};
const stagedCall=call('vera_workspace_management_commentary_stage',stageArgs);
if(stagedCall.isError)throw new Error(stagedCall.content[0].text);
const staged=stagedCall.structuredContent;
const chosen={...identity,case_ref:staged.case_ref};
const page=payload(call('vera_workspace_management_commentary_read',chosen));
const noteAuthority=p=>({...chosen,revision:p.revision,review_ticket:p.review_ticket,item_id:p.selection.id,expected_draft_revision:p.draft_revision});
"""
    )


def conserved(decision="accepted") -> str:
    return f"""
const review={json.dumps({**READBACK, 'decision': decision})};
payload(call('vera_workspace_management_commentary_draft_save',{{...noteAuthority(page),fields:review}}));
const commentFresh=payload(call('vera_workspace_management_commentary_read',chosen));
const commitArgs={{...noteAuthority(commentFresh),confirmed:true,idempotency_key:'fictional-management-commentary-commit'}};
const committed=payload(call('vera_workspace_management_commentary_commit',commitArgs));
const retained=payload(call('vera_workspace_management_commentary_read',chosen));
"""


@pytest.mark.parametrize("decision", ["accepted", "rejected", "changes_requested"])
def test_management_commentary_preserves_complete_literal_content_and_normal_reports(
    management_run, decision
):
    result = rpc_program(
        os.environ.copy(),
        proposed(management_run)
        + conserved(decision)
        + "const result={prepared,commentary,staged,committed,retained,retry:payload(call('vera_workspace_management_commentary_commit',commitArgs)),stageRetry:call('vera_workspace_management_commentary_stage',stageArgs).structuredContent};",
    )
    folder = management_run[1] / result["committed"]["output_ref"]
    receipt = json.loads((folder / "native_commentary_readback.json").read_bytes())
    assert result["committed"] == result["retry"]
    assert result["staged"] == result["stageRetry"]
    assert result["retained"]["can_write"] is False
    assert result["retained"]["status"] == decision
    assert result["retained"]["commentary"] == result["commentary"]
    assert (
        json.loads((folder / "management_commentary.json").read_bytes())
        == result["commentary"]
    )
    assert receipt["review"] == {**READBACK, "decision": decision}
    assert receipt["calculation_status"] == result["prepared"]["status"]
    assert receipt["professional_approval"] is False
    assert receipt["actual_model_reads_verified"] is False
    assert receipt["reviewer_authenticated"] is False
    assert receipt["run_completed"] is False
    assert receipt["sent_or_published"] is False
    assert len(result["retained"]["files"]) == (5 if decision == "accepted" else 2)
    calculation = management_run[1] / result["prepared"]["source_ref"]
    execution = json.loads((calculation / "execution_receipt.json").read_bytes())
    for row in execution["outputs"]:
        assert (
            hashlib.sha256((calculation / row["path"]).read_bytes()).hexdigest()
            == row["sha256"]
        )
    if decision == "accepted":
        normal = json.loads((folder / "commentary_receipt.json").read_bytes())
        assert normal["status"] == "draft_pending_professional_review"
        assert (
            normal["pack_sha256"]
            == hashlib.sha256(
                (calculation / "management_control_pack.json").read_bytes()
            ).hexdigest()
        )
        assert normal["commentary_sha256"] == receipt["commentary_sha256"]
        assert (
            result["commentary"]["observations"][0]["text"]
            in (folder / "management_control_report.md").read_text()
        )
        for row in normal["outputs"]:
            assert (
                hashlib.sha256((folder / row["path"]).read_bytes()).hexdigest()
                == row["sha256"]
            )


@pytest.mark.parametrize("management_run", ["costing", "partial"], indirect=True)
def test_management_commentary_finalizes_costing_and_partial_without_promoting_calculation(
    management_run,
):
    result = rpc_program(
        os.environ.copy(),
        proposed(management_run) + conserved() + "const result={prepared,retained};",
    )
    assert result["retained"]["calculation_status"] == result["prepared"]["status"]
    assert len(result["retained"]["files"]) == 5
    assert result["retained"]["professional_approval"] is False


def test_management_commentary_context_omits_private_unsent_review_and_returns_explicit_whole_proposal(
    management_run,
):
    result = rpc_program(
        os.environ.copy(),
        proposed(management_run)
        + f"""
payload(call('vera_workspace_management_commentary_draft_save',{{...noteAuthority(page),fields:{json.dumps({**READBACK,'reviewer':'PRIVATE_UNSENT_NAME','basis':'PRIVATE_UNSENT_BASIS'})}}}));
const explicit=call('vera_workspace_management_commentary_context',{{...chosen,revision:page.revision}});
const plain=call('vera_workspace_management_commentary_context',{{...identity,revision:page.revision}});
const result={{explicit,plain,commentary}};
""",
    )
    assert (
        result["explicit"]["structuredContent"]["chosen_commentary"]
        == result["commentary"]
    )
    assert "chosen_commentary" not in result["plain"]["structuredContent"]
    assert "PRIVATE_UNSENT" not in json.dumps(result)
    assert "_meta" not in result["explicit"]


def test_management_commentary_invalid_metric_refuses_before_intent_or_proposal(
    management_run,
):
    result = rpc_program(
        os.environ.copy(),
        calculated(management_run)
        + """
const identity={...work,source_ref:prepared.source_ref};
const page=payload(call('vera_workspace_management_commentary_setup',identity));
const context=call('vera_workspace_management_commentary_context',{...identity,revision:page.revision}).structuredContent;
const commentary={...context.commentary_template,observations:[{text:'Fictional invalid metric',metric_ids:['does-not-exist']}]};
const result=call('vera_workspace_management_commentary_stage',{...identity,revision:page.revision,commentary,idempotency_key:'fictional-invalid-metric'});
""",
    )
    assert result["isError"] is True
    private = management_run[4].ui_state_directory(management_run[1], create=False)
    assert list(private.glob("management-commentary-request-*.json")) == []
    assert list(private.glob("management-commentary-*/")) == []


def test_management_commentary_requires_new_confirmation_and_draft_cas(management_run):
    result = rpc_program(
        os.environ.copy(),
        proposed(management_run)
        + f"""
payload(call('vera_workspace_management_commentary_draft_save',{{...noteAuthority(page),fields:{json.dumps(READBACK)}}}));
const commentFresh=payload(call('vera_workspace_management_commentary_read',chosen));
const result={{missing:call('vera_workspace_management_commentary_commit',{{...noteAuthority(commentFresh),confirmed:false,idempotency_key:'fictional-unconfirmed-comment'}}),stale:call('vera_workspace_management_commentary_draft_save',{{...noteAuthority(page),fields:{{decision:'',reviewer:'',reviewed_at:'',basis:''}}}}),current:payload(call('vera_workspace_management_commentary_read',chosen))}};
""",
    )
    assert result["missing"]["isError"] is result["stale"]["isError"] is True
    assert result["current"]["draft"] == READBACK
    assert list(management_run[1].glob("codex-management-notes-*")) == []


@pytest.mark.parametrize("management_run", ["blocked"], indirect=True)
def test_management_commentary_blocked_pack_cannot_stage_or_finalize(management_run):
    result = rpc_program(
        os.environ.copy(),
        calculated(management_run)
        + """
const identity={...work,source_ref:prepared.source_ref};
const page=payload(call('vera_workspace_management_commentary_setup',identity));
const model=call('vera_workspace_management_commentary_context',{...identity,revision:page.revision}).structuredContent;
const result={page,attempt:call('vera_workspace_management_commentary_stage',{...identity,revision:page.revision,commentary:model.commentary_template,idempotency_key:'fictional-blocked-commentary'})};
""",
    )
    assert result["page"]["can_stage"] is False
    assert result["attempt"]["isError"] is True
    assert list(management_run[1].glob("codex-management-notes-*")) == []


def test_management_commentary_pending_proposal_blocks_real_archive_closure(
    registered_management_run,
):
    fixture = registered_management_run
    selected = {k: fixture[2][k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        proposed(fixture)
        + f"const result=call('vera_workspace_archive_closure',{json.dumps(selected)});",
    )
    assert result["isError"] is True
    assert "named readback" in result["content"][0]["text"]


def test_management_commentary_completed_archive_retains_whole_readonly_reports(
    registered_management_run,
):
    fixture = registered_management_run
    first = rpc_program(
        os.environ.copy(),
        proposed(fixture) + conserved() + "const result={chosen,committed};",
    )
    output, binding = fixture[1:3]
    write_no_model_report(output, binding["workflow_id"], binding["run_id"])
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        setup(selected)
        + declare_all()
        + f"""
payload(call('vera_workspace_archive_finalize',seal));
const ready=read();
const completed=payload(call('vera_workspace_archive_complete',{{...authority(ready),human_reviewed:true,idempotency_key:'fictional-management-commentary-complete'}}));
const chosen={json.dumps(first['chosen'])};
const page=payload(call('vera_workspace_management_commentary_read',chosen));
const result={{completed,page,model:call('vera_workspace_management_commentary_context',{{...chosen,revision:page.revision}})}};
""",
    )
    assert result["completed"]["status"] == "completed"
    assert result["page"]["can_write"] is False
    assert len(result["page"]["files"]) == 5
    assert "isError" not in result["model"]
    assert (
        result["model"]["structuredContent"]["chosen_commentary"]
        == result["page"]["commentary"]
    )


@pytest.mark.parametrize("action", ["stage", "commit"])
def test_management_commentary_process_failure_retains_real_files_and_refuses_retry(
    registered_management_run, action
):
    fixture = registered_management_run
    if action == "stage":
        body = (
            proposed(fixture)
            + "const result={...stageArgs,idempotency_key:'interrupted-second-proposal'};"
        )
    else:
        body = (
            proposed(fixture)
            + f"""
payload(call('vera_workspace_management_commentary_draft_save',{{...noteAuthority(page),fields:{json.dumps(READBACK)}}}));
const finalPage=payload(call('vera_workspace_management_commentary_read',chosen));
const result={{...noteAuthority(finalPage),confirmed:true,idempotency_key:'interrupted-commentary-commit'}};
"""
        )
    args = rpc_program(os.environ.copy(), body)
    module = workspace_module()
    program = f"""
import json, sys
sys.path.insert(0, {str(Path(module.__file__).parent)!r})
import native_workspace as workspace
ordinary=workspace.atomic_json
def interrupted(path,value):
    if path.name=='management-commentary-state.json':
        raise RuntimeError('Fictional interruption after actual commentary files')
    return ordinary(path,value)
workspace.atomic_json=interrupted
workspace.dispatch('vera_workspace_management_commentary_{action}',json.load(sys.stdin))
"""
    child = subprocess.run(
        [sys.executable, "-B", "-c", program],
        input=json.dumps(args),
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    assert child.returncode != 0
    assert "after actual commentary files" in child.stderr
    private = fixture[4].ui_state_directory(fixture[1], create=False)
    requests = [
        json.loads(p.read_bytes())
        for p in private.glob("management-commentary-request-*.json")
    ]
    assert sum("result" not in value for value in requests) == 1
    folders = (
        list(fixture[1].glob("codex-management-notes-*"))
        if action == "commit"
        else list(private.glob("management-commentary-*/"))
    )
    assert len(folders) == (1 if action == "commit" else 2)
    before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in folders
        for p in folder.iterdir()
    }
    if action == "commit":
        assert {p.name for p in folders[0].iterdir()} == {
            "management_commentary.json",
            "native_commentary_readback.json",
            "management_control_report.md",
            "management_control_dashboard_reviewed.html",
            "commentary_receipt.json",
        }
    selected = {k: fixture[2][k] for k in ("client_id", "engagement_id", "run_id")}
    identity = {"work_ref": fixture[2]["work_ref"], "source_ref": args["source_ref"]}
    retry = subprocess.run(
        [sys.executable, "-B", str(module.__file__)],
        input=json.dumps(
            {
                "tool": f"vera_workspace_management_commentary_{action}",
                "arguments": args,
            }
        ),
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    result = rpc_program(
        os.environ.copy(),
        f"const result={{page:payload(call('vera_workspace_management_commentary_setup',{json.dumps(identity)})),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};",
    )
    assert retry.returncode != 0
    assert result["page"]["recovery_required"] is True
    assert result["page"]["can_stage"] is False
    assert result["closure"]["isError"] is True
    assert {
        path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in before
    } == before


def test_management_commentary_viewer_cannot_stage_save_or_commit(management_run):
    first = rpc_program(
        os.environ.copy(), proposed(management_run) + "const result={chosen,stageArgs};"
    )
    env = {**os.environ, "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        env,
        f"""
const chosen={json.dumps(first['chosen'])};
const page=payload(call('vera_workspace_management_commentary_read',chosen));
const authority={{...chosen,revision:page.revision,review_ticket:page.review_ticket,item_id:page.selection.id,expected_draft_revision:page.draft_revision}};
const result={{page,stage:call('vera_workspace_management_commentary_stage',{json.dumps({**first['stageArgs'],'idempotency_key':'viewer-commentary'})}),save:call('vera_workspace_management_commentary_draft_save',{{...authority,fields:{json.dumps(READBACK)}}}),commit:call('vera_workspace_management_commentary_commit',{{...authority,confirmed:true,idempotency_key:'viewer-commit'}})}};
""",
    )
    assert result["page"]["can_write"] is False
    assert result["stage"]["isError"] is True
    assert result["save"]["isError"] is True
    assert result["commit"]["isError"] is True
    assert list(management_run[1].glob("codex-management-notes-*")) == []


@pytest.mark.parametrize("target", ["proposal", "report"])
def test_management_commentary_changed_bytes_refuse_context_and_archive_closure(
    registered_management_run, target
):
    fixture = registered_management_run
    first = rpc_program(
        os.environ.copy(),
        proposed(fixture) + conserved() + "const result={chosen,committed};",
    )
    if target == "proposal":
        private = fixture[4].ui_state_directory(fixture[1], create=False)
        changed = private / first["chosen"]["case_ref"] / "management_commentary.json"
    else:
        changed = (
            fixture[1]
            / first["committed"]["output_ref"]
            / "management_control_report.md"
        )
    changed.write_bytes(changed.read_bytes() + b"\nFictional altered bytes\n")
    selected = {k: fixture[2][k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        f"const chosen={json.dumps(first['chosen'])};const result={{read:call('vera_workspace_management_commentary_read',chosen),context:call('vera_workspace_management_commentary_context',{{...chosen,revision:'old'}}),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};",
    )
    assert result["read"]["isError"] is True
    assert result["context"]["isError"] is True
    assert result["closure"]["isError"] is True


def test_management_commentary_multiple_proposals_require_explicit_selection(
    management_run,
):
    result = rpc_program(
        os.environ.copy(),
        proposed(management_run)
        + """
const secondCommentary={...commentary,questions:[{text:'Second complete fictional proposal',metric_ids:[]}]};
const second=call('vera_workspace_management_commentary_stage',{...stageArgs,commentary:secondCommentary,idempotency_key:'second-complete-proposal'}).structuredContent;
const result={first:payload(call('vera_workspace_management_commentary_read',chosen)),second:payload(call('vera_workspace_management_commentary_read',{...identity,case_ref:second.case_ref})),implicit:call('vera_workspace_management_commentary_read',identity),versions:payload(call('vera_workspace_management_commentary_setup',identity)).versions};
""",
    )
    assert (
        result["first"]["commentary"]["questions"][0]["text"]
        == "Which evidence supports the interpretation?"
    )
    assert (
        result["second"]["commentary"]["questions"][0]["text"]
        == "Second complete fictional proposal"
    )
    assert len(result["versions"]) == 2
    assert result["implicit"]["isError"] is True
