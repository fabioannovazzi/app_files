"""Actual source mandates, full case/readback conservation and separate calculations."""

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
from tests.plugins.test_vera_native_management_commentary import READBACK
from tests.plugins.test_vera_native_management_execution import (  # noqa: F401
    management_run,
)
from tests.plugins.test_vera_native_management_mcp import (  # noqa: F401
    registered_management_run,
)
from tests.plugins.test_vera_native_workspace import workspace_module

__all__ = []


@pytest.fixture
def author_run(registered_management_run):
    fixture = registered_management_run
    api = fixture[4]
    loaded = api.load_binding(fixture[2])
    original = next(
        r
        for r in loaded["input_manifest"]["inputs"]
        if r["binding_id"] == fixture[3]["recipe_input_id"]
    )
    case = json.loads(
        (Path(loaded["run_root"]) / original["execution_relative_path"]).read_bytes()
    )
    if fixture[3]["mode"] == "reporting":
        case["mapping_review"] = {
            "status": "not_reviewed",
            "reviewer": "",
            "reviewed_at": "",
        }
    choices = {
        "question": "Fictional complete Management case: source roles, classifications, drivers and open limits require named readback.",
        "mode": fixture[3]["mode"],
        "input_ids": fixture[3]["input_ids"],
        "base_case_input_id": fixture[3]["recipe_input_id"],
    }
    return (
        *fixture,
        choices,
        {
            "case": case,
            "note": "Fictional complete proposal; no actual model or professional acceptance.",
        },
    )


def granted(fixture):
    return f"""
const work={{work_ref:{json.dumps(fixture[2]['work_ref'])}}};
const fields={json.dumps(fixture[5])};
const original=payload(call('vera_workspace_management_author_setup',work));
payload(call('vera_workspace_management_author_draft_save',{{...work,revision:original.revision,review_ticket:original.review_ticket,expected_draft_revision:original.draft_revision,fields}}));
const fresh=payload(call('vera_workspace_management_author_setup',work));
const request={{...work,revision:fresh.revision,review_ticket:fresh.review_ticket,expected_draft_revision:fresh.draft_revision,fields,confirmed:true,idempotency_key:'fictional-management-author-request'}};
const issued=payload(call('vera_workspace_management_author_request',request));
const identity={{...work,grant_ref:issued.grant_ref}};
const opened=payload(call('vera_workspace_management_author_read',identity));
"""


def proposed(fixture):
    return (
        granted(fixture)
        + f"""
const proposal={json.dumps(fixture[6])};
const stageArgs={{...identity,revision:opened.revision,proposal,idempotency_key:'fictional-management-author-stage'}};
const stagedCall=call('vera_workspace_management_author_stage',stageArgs);
if(stagedCall.isError)throw new Error(stagedCall.content[0].text);
const staged=stagedCall.structuredContent;
const chosen={{...identity,case_ref:staged.case_ref}};
const page=payload(call('vera_workspace_management_author_read',chosen));
const authority=p=>({{...chosen,source_ref:issued.grant_ref,revision:p.revision,review_ticket:p.review_ticket,item_id:p.selection.id,expected_draft_revision:p.draft_revision}});
"""
    )


def registered():
    return f"""
const review={json.dumps(READBACK)};
payload(call('vera_workspace_management_author_review_draft_save',{{...authority(page),fields:review}}));
const ready=payload(call('vera_workspace_management_author_read',chosen));
const registerArgs={{...authority(ready),fields:review,confirmed:true,idempotency_key:'fictional-management-author-register'}};
const registration=payload(call('vera_workspace_management_author_register',registerArgs));
const retained=payload(call('vera_workspace_management_author_read',chosen));
"""


@pytest.mark.parametrize(
    "management_run,expected_status",
    [
        ("reporting", "ready_for_review"),
        ("costing", "ready_for_review"),
        ("partial", "partial"),
        ("blocked", "blocked"),
    ],
    indirect=["management_run"],
)
def test_management_authoring_keeps_full_case_registers_actual_successor_and_calculates_separately(
    author_run,
    expected_status,
):
    fixture = author_run
    result = rpc_program(
        os.environ.copy(),
        proposed(fixture)
        + registered()
        + """
const successor={work_ref:registration.work_ref};
const before=payload(call('vera_workspace_management_setup',successor));
const executionFields={mode:registration.mode,input_ids:registration.input_ids,recipe_input_id:registration.recipe_input_id};
payload(call('vera_workspace_management_draft_save',{...successor,revision:before.revision,review_ticket:before.review_ticket,expected_draft_revision:before.draft_revision,fields:executionFields}));
const preparedChoices=payload(call('vera_workspace_management_setup',successor));
const prepared=payload(call('vera_workspace_management_prepare',{...successor,revision:preparedChoices.revision,review_ticket:preparedChoices.review_ticket,expected_draft_revision:preparedChoices.draft_revision,fields:executionFields,confirmed:true,idempotency_key:'fictional-authored-calculation'}));
const result={before,registration,retained,prepared,retry:payload(call('vera_workspace_management_author_register',registerArgs)),stageRetry:call('vera_workspace_management_author_stage',stageArgs).structuredContent,staged};
""",
    )
    assert result["registration"] == result["retry"]
    assert result["staged"] == result["stageRetry"]
    assert result["before"]["source_ref"] is None
    assert result["registration"]["calculated"] is False
    assert result["registration"]["work_ref"] != fixture[2]["work_ref"]
    assert result["retained"]["can_write"] is False
    assert result["retained"]["case"] == fixture[6]["case"]
    assert result["retained"]["registration"]["fields"] == READBACK
    api = fixture[4]
    original = api.load_binding(fixture[2])
    assert original["run"]["status"] == "running"
    assert list(fixture[1].glob("management-*")) == []
    private = api.ui_state_directory(fixture[1], create=False)
    state = json.loads((private / "management-author-state.json").read_bytes())
    receipt = state["proposals"][0]["registration"]
    successor = api.load_binding(receipt["binding"])
    assert successor["run"]["status"] == "running"
    assert successor["run"]["client_id"] == fixture[2]["client_id"]
    assert successor["run"]["engagement_id"] == fixture[2]["engagement_id"]
    case_path = private / receipt["receipt_ref"] / "case.json"
    saved = json.loads(case_path.read_bytes())
    if fixture[5]["mode"] == "reporting":
        assert saved["mapping_review"] == {
            "status": "reviewed",
            "reviewer": READBACK["reviewer"],
            "reviewed_at": READBACK["reviewed_at"],
            "basis": READBACK["basis"],
        }
        assert {k: v for k, v in saved.items() if k != "mapping_review"} == {
            k: v for k, v in fixture[6]["case"].items() if k != "mapping_review"
        }
    else:
        assert saved == fixture[6]["case"]
    calculation = Path(successor["output_dir"]) / result["prepared"]["source_ref"]
    execution = json.loads((calculation / "execution_receipt.json").read_bytes())
    assert len(list(calculation.iterdir())) == 8
    assert all(
        hashlib.sha256((calculation / r["path"]).read_bytes()).hexdigest()
        == r["sha256"]
        for r in execution["outputs"]
    )
    assert result["prepared"]["status"] == expected_status


def test_management_authoring_context_omits_unsent_readback_and_returns_only_granted_sources(
    author_run,
):
    result = rpc_program(
        os.environ.copy(),
        proposed(author_run)
        + f"""
payload(call('vera_workspace_management_author_review_draft_save',{{...authority(page),fields:{json.dumps({**READBACK,'reviewer':'PRIVATE UNSENT NAME','basis':'PRIVATE UNSENT BASIS'})}}}));
const model=call('vera_workspace_management_author_context',{{...chosen,revision:page.revision}});
const result={{model,issued,proposal}};
""",
    )
    assert "PRIVATE UNSENT" not in json.dumps(result)
    assert "_meta" not in result["model"]
    model = result["model"]["structuredContent"]
    assert [r["input_id"] for r in model["sources"]] == [
        *author_run[5]["input_ids"],
        author_run[5]["base_case_input_id"],
    ]
    assert model["actual_model_reads_verified"] is False
    assert (
        json.loads(Path(model["chosen_proposal"]["authorized_path"]).read_bytes())
        == author_run[6]["case"]
    )


def test_management_authoring_requires_new_confirmation_and_readback_cas(author_run):
    result = rpc_program(
        os.environ.copy(),
        proposed(author_run)
        + f"""
payload(call('vera_workspace_management_author_review_draft_save',{{...authority(page),fields:{json.dumps(READBACK)}}}));
const ready=payload(call('vera_workspace_management_author_read',chosen));
const result={{unconfirmed:call('vera_workspace_management_author_register',{{...authority(ready),fields:{json.dumps(READBACK)},confirmed:false,idempotency_key:'no-confirmation'}}),stale:call('vera_workspace_management_author_review_draft_save',{{...authority(page),fields:{{decision:'',reviewer:'',reviewed_at:'',basis:''}}}}),current:ready}};
""",
    )
    assert result["unconfirmed"]["isError"] is True
    assert result["stale"]["isError"] is True
    assert result["current"]["review_draft"] == READBACK
    private = author_run[4].ui_state_directory(author_run[1], create=False)
    assert list(private.glob("management-case-readback-*")) == []


@pytest.mark.parametrize("action", ["request", "stage", "register"])
def test_management_authoring_interruption_keeps_real_files_and_blocks_retry_and_closure(
    author_run, action
):
    if action == "request":
        body = granted(author_run).split("const issued=", 1)[0]
        body += (
            "const result={...request,idempotency_key:'interrupted-source-mandate'};"
        )
    elif action == "stage":
        body = proposed(author_run)
        body += "const result={...stageArgs,revision:page.revision,idempotency_key:'interrupted-whole-case'};"
    else:
        body = proposed(author_run)
        body += f"""
const review={json.dumps(READBACK)};
payload(call('vera_workspace_management_author_review_draft_save',{{...authority(page),fields:review}}));
const ready=payload(call('vera_workspace_management_author_read',chosen));
const result={{...authority(ready),fields:review,confirmed:true,idempotency_key:'interrupted-real-successor'}};
"""
    args = rpc_program(os.environ.copy(), body)
    module = workspace_module()
    program = f"""
import json, sys
sys.path.insert(0, {str(Path(module.__file__).parent)!r})
import native_workspace as workspace
ordinary=workspace.atomic_json
def interrupted(path,value):
    if path.name=='management-author-state.json':
        raise RuntimeError('Fictional interruption after actual authoring files')
    return ordinary(path,value)
workspace.atomic_json=interrupted
workspace.dispatch('vera_workspace_management_author_{action}',json.load(sys.stdin))
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
    assert "after actual authoring files" in child.stderr
    private = author_run[4].ui_state_directory(author_run[1], create=False)
    if action == "request":
        folders = list(author_run[1].glob("codex-management-intake-*"))
        assert len(folders) == 1
    elif action == "stage":
        folders = list(private.glob("management-authored-*"))
        assert len(folders) == 2
    else:
        folders = list(private.glob("management-case-readback-*"))
        assert len(folders) == 1
        runs = list(author_run[1].parent.parent.glob("run_*"))
        assert len(runs) == 2
        assert {p.name for p in folders[0].iterdir()} == {
            "case.json",
            "case-readback.json",
        }
    before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in folders
        for p in folder.iterdir()
    }
    selected = {k: author_run[2][k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        f"""
const result={{page:payload(call('vera_workspace_management_author_setup',{{work_ref:{json.dumps(author_run[2]['work_ref'])}}})),retry:call('vera_workspace_management_author_{action}',{json.dumps(args)}),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};
""",
    )
    assert result["page"]["recovery_required"] is True
    assert result["page"]["can_write"] is False
    assert result["retry"]["isError"] is True
    assert result["closure"]["isError"] is True
    assert {
        path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in before
    } == before


def test_management_authoring_refuses_model_fabricated_reporting_readback_before_intent(
    author_run,
):
    proposal = {
        **author_run[6],
        "case": {
            **author_run[6]["case"],
            "mapping_review": {
                "status": "reviewed",
                "reviewer": "invented",
                "reviewed_at": "invented",
            },
        },
    }
    result = rpc_program(
        os.environ.copy(),
        granted(author_run)
        + f"const result=call('vera_workspace_management_author_stage',{{...identity,revision:opened.revision,proposal:{json.dumps(proposal)},idempotency_key:'fabricated-review'}});",
    )
    assert result["isError"] is True
    assert "pending human review" in result["content"][0]["text"]
    private = author_run[4].ui_state_directory(author_run[1], create=False)
    assert list(private.glob("management-authored-*")) == []


def test_management_authoring_cancel_retains_complete_files_and_blocks_model_context(
    author_run,
):
    selected = {k: author_run[2][k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        proposed(author_run)
        + f"""
const blocked=call('vera_workspace_archive_closure',{json.dumps(selected)});
payload(call('vera_workspace_management_author_cancel',{{...identity,source_ref:issued.grant_ref,revision:page.revision,review_ticket:page.review_ticket,item_id:page.selection.id,confirmed:true,idempotency_key:'cancel-mandate'}}));
const current=payload(call('vera_workspace_management_author_read',chosen));
const result={{blocked,current,context:call('vera_workspace_management_author_context',{{...chosen,revision:current.revision}}),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};
""",
    )
    assert result["blocked"]["isError"] is True
    assert result["current"]["status"] == "cancelled"
    assert result["current"]["case"] == author_run[6]["case"]
    assert result["context"]["isError"] is True
    assert "isError" not in result["closure"]


def test_management_authoring_viewer_reads_case_but_cannot_stage_register_or_save(
    author_run,
):
    first = rpc_program(
        os.environ.copy(), proposed(author_run) + "const result={chosen,stageArgs};"
    )
    env = {**os.environ, "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        env,
        f"""
const chosen={json.dumps(first['chosen'])};const page=payload(call('vera_workspace_management_author_read',chosen));
const args={{...chosen,source_ref:chosen.grant_ref,revision:page.revision,review_ticket:page.review_ticket,item_id:page.selection.id,expected_draft_revision:page.draft_revision,fields:{json.dumps(READBACK)}}};
const result={{page,save:call('vera_workspace_management_author_review_draft_save',args),register:call('vera_workspace_management_author_register',{{...args,confirmed:true,idempotency_key:'viewer-register'}}),stage:call('vera_workspace_management_author_stage',{json.dumps({**first['stageArgs'],'idempotency_key':'viewer-stage'})})}};
""",
    )
    assert result["page"]["can_write"] is False
    assert result["save"]["isError"] is True
    assert result["register"]["isError"] is True
    assert result["stage"]["isError"] is True


@pytest.mark.parametrize("changed_target", ["original_source", "complete_proposal"])
def test_management_authoring_changed_bytes_refuse_context_and_registration(
    author_run, changed_target
):
    staged = rpc_program(
        os.environ.copy(),
        proposed(author_run)
        + """
const model=call('vera_workspace_management_author_context',{...chosen,revision:page.revision}).structuredContent;
const result={chosen,authority:authority(page),model};
""",
    )
    if changed_target == "original_source":
        changed = Path(staged["model"]["sources"][0]["authorized_path"])
    else:
        changed = Path(staged["model"]["chosen_proposal"]["authorized_path"])
    changed.write_bytes(changed.read_bytes() + b"\nchanged fictional bytes\n")

    result = rpc_program(
        os.environ.copy(),
        f"""
const chosen={json.dumps(staged['chosen'])};
const authority={json.dumps(staged['authority'])};
const result={{context:call('vera_workspace_management_author_context',{{...chosen,revision:authority.revision}}),registration:call('vera_workspace_management_author_register',{{...authority,fields:{json.dumps(READBACK)},confirmed:true,idempotency_key:'changed-bytes-register'}})}};
""",
    )

    assert result["context"]["isError"] is True
    assert result["registration"]["isError"] is True
    private = author_run[4].ui_state_directory(author_run[1], create=False)
    assert list(private.glob("management-case-readback-*")) == []


def test_management_authoring_completed_original_run_reopens_whole_case_readonly(
    author_run,
):
    saved = rpc_program(
        os.environ.copy(),
        proposed(author_run) + registered() + "const result={chosen,registration};",
    )
    binding = author_run[2]
    write_no_model_report(author_run[1], binding["workflow_id"], binding["run_id"])
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}

    result = rpc_program(
        os.environ.copy(),
        setup(selected)
        + declare_all()
        + f"""
payload(call('vera_workspace_archive_finalize',seal));
const ready=read();
const completed=payload(call('vera_workspace_archive_complete',{{...authority(ready),human_reviewed:true,idempotency_key:'fictional-management-author-complete-original'}}));
const chosen={json.dumps(saved['chosen'])};
const reopened=payload(call('vera_workspace_management_author_read',chosen));
const result={{completed,reopened,model:call('vera_workspace_management_author_context',{{...chosen,revision:reopened.revision}})}};
""",
    )

    assert result["completed"]["status"] == "completed"
    assert result["reopened"]["can_write"] is False
    assert result["reopened"]["case"] == author_run[6]["case"]
    assert result["reopened"]["registration"]["fields"] == READBACK
    assert "isError" not in result["model"]
    assert result["model"]["structuredContent"]["actual_model_reads_verified"] is False
