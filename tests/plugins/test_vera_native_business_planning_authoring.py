"""User mandates and model-staged cases through real owned Archive and MCP."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program, selected_scope
from tests.plugins.test_vera_native_archive_navigation import (  # noqa: F401
    registry_workspace,
)
from tests.plugins.test_vera_native_workspace import ROOT

IDEA = json.loads(
    (ROOT / "tests/fixtures/business_planning/idea-case.json").read_bytes()
)
QUESTION = "I propose mobile bicycle repairs, have repair skills and want to test demand before buying a vehicle."


def request_program(client: str, engagement: str) -> str:
    """Model output is an explicit synthetic fixture, never production authoring."""
    return f"""
const selected={selected_scope(client, engagement)};
const setup=payload(call('vera_workspace_business_plan_author_setup',selected));
const mandateArgs={{...scope(setup),expected_draft_revision:setup.draft.draft_revision,input_ids:[],upstream_artifacts:[],parent:null,question:{json.dumps(QUESTION)},label:'Synthetic model-authored pilot',purpose:'Test the idea against actual evidence',idempotency_key:'literal-request'}};
const mandate=payload(call('vera_workspace_business_plan_author_request',mandateArgs));
const exact={{...selected,grant_ref:mandate.grant_ref}};
const model=call('vera_workspace_business_plan_author_context',exact).structuredContent;
if(!model)throw new Error('Missing actual model context');
const caseValue={json.dumps(IDEA)};
caseValue.review={{status:'unreviewed',reviewer:'',reviewed_at:''}};
caseValue.sources[0].path=model.sources[0].path;caseValue.sources[0].sha256=model.sources[0].sha256;
caseValue.cycle.question=model.mandate.question;
const stageArgs={{...exact,expected_stage_revision:model.stage_revision,case:caseValue,idempotency_key:'model-proposal'}};
"""


STAGE = """
const staged=call('vera_workspace_business_plan_author_stage',stageArgs);
if(staged.isError)throw new Error(staged.content[0].text);
const stage=staged.structuredContent;
const preview=payload(call('vera_workspace_business_plan_author_read',{...exact,stage_ref:stage.stage_ref}));
"""


def test_user_question_model_stage_and_fresh_run_keep_full_public_report(
    registry_workspace,
):
    env, root, _, _, client, engagement = registry_workspace
    result = rpc_program(
        env,
        request_program(client, engagement)
        + STAGE
        + """
const launchArgs={...scope(preview),...exact,stage_ref:stage.stage_ref,idempotency_key:'execute-proposal'};
const launched=payload(call('vera_workspace_business_plan_author_launch',launchArgs));
const retry=payload(call('vera_workspace_business_plan_author_launch',launchArgs));
const run=payload(call('vera_workspace_business_plan_setup',{work_ref:launched.work_ref}));
const report=payload(call('vera_workspace_business_plan_report',{work_ref:run.work_ref,revision:run.revision,generation:run.generation}));
const requestRetry=payload(call('vera_workspace_business_plan_author_request',mandateArgs));
const stageRetry=call('vera_workspace_business_plan_author_stage',stageArgs).structuredContent;
const result={mandate,model,stage,preview,launched,retry,run,report,requestRetry,stageRetry};
""",
    )

    ledger = _load_customer_ledger()
    loaded = ledger.load_run(
        root / "Cliente Beta", engagement, result["launched"]["run_id"]
    )
    assert result["launched"] == result["retry"]
    assert result["mandate"] == result["requestRetry"]
    assert result["stage"] == result["stageRetry"]
    assert loaded["run"]["status"] == "running"
    assert result["report"]["report"] == result["preview"]["report"]
    assert result["preview"]["plan"]["status"] == "partial"
    assert result["model"]["mandate"]["question"] == QUESTION
    assert len(result["model"]["sources"]) == 1
    assert Path(result["model"]["sources"][0]["local_path"]).read_text() == QUESTION
    assert result["launched"]["professional_approval"] is False
    assert result["launched"]["run_completed"] is False
    assert len(list(Path(loaded["output_dir"]).rglob("execution_receipt.json"))) == 1


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (
            "stageArgs.case.review={status:'reviewed',reviewer:'Fabricated',reviewed_at:'2026-10-07'}",
            "professional attestation",
        ),
        (
            "stageArgs.case.evidence[0].reviewer='Fabricated'",
            "Fresh record attestations",
        ),
        ("stageArgs.case.sources[0].review_status='reviewed'", "fresh source"),
        ("stageArgs.case.sources=[]", "every selected source"),
        ("stageArgs.case.sources[0].sha256='0'.repeat(64)", "source identity"),
        ("stageArgs.expected_stage_revision='0'.repeat(64)", "proposal changed"),
        ("stageArgs.grant_ref='author-'+'0'.repeat(64)", "mandate.json"),
        ("stageArgs.engagement_id='engagement_foreign'", "engagement"),
    ],
)
def test_model_staging_refuses_fake_attestation_missing_source_and_stale_scope(
    registry_workspace, mutation, expected
):
    env, _, _, _, client, engagement = registry_workspace

    result = rpc_program(
        env,
        request_program(client, engagement)
        + mutation
        + ";const result=call('vera_workspace_business_plan_author_stage',stageArgs);",
    )

    assert result["isError"] is True
    assert expected.lower() in result["content"][0]["text"].lower()


@pytest.mark.parametrize("operation", ["stage", "launch"])
def test_interrupted_intent_blocks_distinct_key_instead_of_duplicate_run(
    registry_workspace, operation
):
    env, _, _, _, client, engagement = registry_workspace
    body = request_program(client, engagement) + STAGE
    body += f"""
const fs=require('node:fs'),path=require('node:path');
const base=path.dirname(path.dirname(path.dirname(model.sources[0].local_path)));
// Canonical imports/<receipt>/<file> beneath base/inputs.
const grantBase=path.dirname(base);
fs.writeFileSync(path.join(grantBase,'{operation}-request-interrupted.json'),JSON.stringify({{request_sha256:'0'.repeat(64)}}));
const reopened=payload(call('vera_workspace_business_plan_author_read',exact));
const result={{reopened,attempt:call('vera_workspace_business_plan_author_{operation}',{("{...stageArgs,idempotency_key:'distinct-request'}" if operation == "stage" else "{...scope(preview),...exact,stage_ref:stage.stage_ref,idempotency_key:'distinct-request'}")})}};
"""

    result = rpc_program(env, body)

    assert result["reopened"]["recovery_required"] is True
    assert result["reopened"]["can_launch"] is False
    assert result["attempt"]["isError"] is True
    assert "recovery" in result["attempt"]["content"][0]["text"]


def test_cached_chosen_source_change_refuses_model_context(registry_workspace):
    env, _, _, _, client, engagement = registry_workspace
    result = rpc_program(
        env,
        request_program(client, engagement)
        + """
require('node:fs').appendFileSync(model.sources[0].local_path,' changed');
const result=call('vera_workspace_business_plan_author_context',exact);
""",
    )

    assert result["isError"] is True
    assert "evidence changed" in result["content"][0]["text"]


@pytest.mark.parametrize(
    "change",
    [
        "expected_draft_revision:'stale'",
        "fields:{question:'Unscoped data'}",
        "confirmed:false",
        "archive_ticket:'forged.signature'",
    ],
)
def test_intake_draft_refuses_foreign_fields_stale_cas_and_unsigned_write(
    registry_workspace, change
):
    env, _, _, _, client, engagement = registry_workspace
    result = rpc_program(
        env,
        f"""
const selected={selected_scope(client,engagement)};
const setup=payload(call('vera_workspace_business_plan_author_setup',selected));
const result={{attempt:call('vera_workspace_business_plan_author_draft_store',{{...scope(setup),expected_draft_revision:setup.draft.draft_revision,fields:setup.draft.fields,{change}}}),after:payload(call('vera_workspace_business_plan_author_setup',selected))}};
""",
    )

    assert result["attempt"]["isError"] is True
    assert result["after"]["draft"]["draft_revision"] == ""
    assert result["after"]["mandates"]["total"] == 0


def test_partial_intake_recovers_literal_fields_without_grant_or_run(
    registry_workspace,
):
    env, root, _, _, client, engagement = registry_workspace
    result = rpc_program(
        env,
        f"""
const selected={selected_scope(client,engagement)};
const setup=payload(call('vera_workspace_business_plan_author_setup',selected));
const fields={{...setup.draft.fields,question:'Incomplete actual user question'}};
const stored=payload(call('vera_workspace_business_plan_author_draft_store',{{...scope(setup),expected_draft_revision:'',fields}}));
const reopened=payload(call('vera_workspace_business_plan_author_setup',selected));
const model=call('vera_workspace_business_plan_author_context',{{...selected,grant_ref:'author-'+'0'.repeat(64)}});
const cleared=payload(call('vera_workspace_business_plan_author_draft_clear',{{...scope(reopened),expected_draft_revision:stored.draft_revision}}));
const result={{stored,reopened,model,cleared,after:payload(call('vera_workspace_business_plan_author_setup',selected))}};
""",
    )

    assert (
        result["reopened"]["draft"]["fields"]["question"]
        == "Incomplete actual user question"
    )
    assert result["reopened"]["draft"]["stale"] is False
    assert result["model"]["isError"] is True
    assert result["after"]["draft"]["draft_revision"] == ""
    assert result["after"]["mandates"]["total"] == 0
    assert (
        len(_load_customer_ledger().list_runs(root / "Cliente Beta", engagement)) == 1
    )


@pytest.mark.parametrize(
    "change",
    [
        "archive_ticket:'forged.signature'",
        "confirmed:false",
        "scope_revision:'0'.repeat(64)",
        "input_ids:['input_foreign']",
        "question:''",
        "parent:{run_id:'run_foreign',artifact_id:'foreign'}",
    ],
)
def test_user_request_refuses_unsigned_stale_and_foreign_choices(
    registry_workspace, change
):
    env, _, _, _, client, engagement = registry_workspace
    body = f"""
const selected={selected_scope(client,engagement)};
const setup=payload(call('vera_workspace_business_plan_author_setup',selected));
const args={{...scope(setup),expected_draft_revision:setup.draft.draft_revision,input_ids:[],upstream_artifacts:[],parent:null,question:'Actual user question',label:'Synthetic idea',purpose:'Test user request',idempotency_key:'refused-request',{change}}};
const attempt=call('vera_workspace_business_plan_author_request',args);
const after=payload(call('vera_workspace_business_plan_author_setup',selected));
const result={{attempt,after}};
"""

    result = rpc_program(env, body)

    assert result["attempt"]["isError"] is True
    assert result["after"]["mandates"]["total"] == 0
    assert result["after"]["total"] == 1


def test_sealed_parent_and_explicit_supporting_output_create_successor_preserving_parent(
    registry_workspace,
):
    env, root, _, _, client, engagement = registry_workspace
    initial = rpc_program(
        env,
        request_program(client, engagement)
        + STAGE
        + """
const launched=payload(call('vera_workspace_business_plan_author_launch',{...scope(preview),...exact,stage_ref:stage.stage_ref,idempotency_key:'first-cycle'}));
const result={launched,model,preview};
""",
    )
    ledger = _load_customer_ledger()
    folder = root / "Cliente Beta"
    parent_run = ledger.load_run(folder, engagement, initial["launched"]["run_id"])
    output = Path(parent_run["output_dir"])
    # No model executes in this fixture; disclose that actual test boundary.
    write_no_model_report(output, "business-planning", parent_run["run"]["run_id"])
    files = sorted(path for path in output.rglob("*") if path.is_file())
    declarations = [
        {
            "artifact_id": f"synthetic.{index}",
            "path": path.relative_to(output).as_posix(),
            "purpose": "Retain this exact synthetic planning output for review.",
            "audience": "review",
            "media_type": "application/octet-stream",
        }
        for index, path in enumerate(files)
    ]
    before = {path.relative_to(output).as_posix(): path.read_bytes() for path in files}
    manifest = ledger.finalize_run(
        folder, engagement, parent_run["run"]["run_id"], declarations
    )["artifact_manifest"]
    parent = next(
        row
        for row in manifest["artifacts"]
        if row["path"].endswith("/business_plan.json")
    )
    support = next(
        row
        for row in manifest["artifacts"]
        if row["path"].endswith("/calculations.json")
    )
    case = deepcopy(initial["preview"]["plan"]["case"])
    case["cycle"]["id"] = "successor"
    case["cycle"]["parent_source_id"] = "parent"
    case["cycle"]["reassessed_ids"] = [row["id"] for row in case["narrative"]]
    descriptor = {
        "run_id": parent_run["run"]["run_id"],
        "artifact_id": parent["artifact_id"],
    }
    supporting = {
        "run_id": parent_run["run"]["run_id"],
        "artifact_id": support["artifact_id"],
    }
    body = f"""
const selected={selected_scope(client,engagement)};
const setup=payload(call('vera_workspace_business_plan_author_setup',selected));
const requested=payload(call('vera_workspace_business_plan_author_request',{{...scope(setup),expected_draft_revision:setup.draft.draft_revision,input_ids:{json.dumps(initial['model']['mandate']['input_ids'])},upstream_artifacts:[{json.dumps(supporting)}],parent:{json.dumps(descriptor)},question:'What would change our pilot decision?',label:'Synthetic successor',purpose:'Reconsider the pilot',idempotency_key:'second-cycle'}}));
const exact={{...selected,grant_ref:requested.grant_ref}};
const model=call('vera_workspace_business_plan_author_context',exact).structuredContent;
const caseValue={json.dumps(case)};
caseValue.cycle.question=model.mandate.question;
for(const row of model.sources){{
 if(caseValue.sources.some(source=>source.path===row.path))continue;
 const id=row.role==='prior_plan'?'parent':row.kind==='upstream_artifact'?'support':'new-question';
 caseValue.sources.push({{...caseValue.sources[0],id,path:row.path,sha256:row.sha256,role:row.role==='prior_plan'?'prior_plan':row.kind==='upstream_artifact'?'financial_model':'user_statement'}});
 caseValue.evidence.push({{id:'evidence-'+id,kind:'fact',description:'Explicit synthetic source for successor review.',source_ids:[id],status:'pending'}});
}}
const authored=call('vera_workspace_business_plan_author_stage',{{...exact,expected_stage_revision:model.stage_revision,case:caseValue,idempotency_key:'successor-proposal'}});
if(authored.isError)throw new Error(authored.content[0].text);
const preview=payload(call('vera_workspace_business_plan_author_read',{{...exact,stage_ref:authored.structuredContent.stage_ref}}));
const launched=payload(call('vera_workspace_business_plan_author_launch',{{...scope(preview),...exact,stage_ref:preview.selected_stage,idempotency_key:'successor-run'}}));
const result={{setup,model,preview,launched}};
"""

    result = rpc_program(env, body)

    assert result["launched"]["run_id"] != parent_run["run"]["run_id"]
    assert result["preview"]["plan"]["case"]["cycle"]["id"] == "successor"
    assert len(result["model"]["sources"]) == 4
    assert any(row["predecessor_eligible"] for row in result["setup"]["upstream_rows"])
    assert {
        path.relative_to(output).as_posix(): path.read_bytes() for path in files
    } == before
    assert (
        ledger.load_run(folder, engagement, parent_run["run"]["run_id"])["run"][
            "status"
        ]
        == "ready_for_review"
    )
