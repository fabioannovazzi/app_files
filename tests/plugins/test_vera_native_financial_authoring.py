"""Exact model candidates require separate named review before public execution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_financial_execution import (
    archive_environment,
    financial_intake,
)
from tests.plugins.test_vera_native_workspace import workspace_module

__all__ = []

PENDING_FDD = """
const fdd=proposal.case.fdd_case,stack=fdd.contract_stack;
proposal.case={schema_version:'vera.native.fdd_case_proposal.v1',case_id:fdd.case_id,scope_id:fdd.scope_id,entity_refs:fdd.entity_refs,pack_id:fdd.pack_id,currency:fdd.currency,unit:fdd.unit,reporting_period:fdd.reporting_period,package:stack.package,datasets:stack.datasets,relationships:stack.relationships,crosswalks:stack.crosswalks,request_id:stack.request.request_id,decisions:fdd.reviewed_decisions.map(d=>({decision_ref:d.decision_ref,basis:d.basis})),inputs:fdd.inputs,limitations:fdd.limitations};
"""


def author_script(fixture) -> str:
    env, _, _, pack, case_id, bindings = fixture
    return f"""
const work={{work_ref:'fictional-financial'}};
const intake=payload(call('vera_workspace_financial_author_setup',work));
const fields={{pack_id:{json.dumps(pack)},input_ids:{json.dumps([case_id,*dict.fromkeys(bindings.values())])},question:'Prepare this complete fictional Financial case from these explicit originals.',base_ref:''}};
const requestArgs={{...work,revision:intake.revision,review_ticket:intake.review_ticket,expected_draft_revision:intake.draft_revision,fields,confirmed:true,idempotency_key:'fictional-author-request'}};
const request=payload(call('vera_workspace_financial_author_request',requestArgs));
const exact={{...work,grant_ref:request.grant_ref}};
const page=payload(call('vera_workspace_financial_author_read',exact));
const selected=payload(call('vera_workspace_financial_case',{{...work,pack_id:fields.pack_id,case_input_id:{json.dumps(case_id)}}}));
const proposal={{case:selected.case_content,source_bindings:{json.dumps(bindings)},note:'Fictional fixture proposal only; accounting meaning and completeness require professional review.'}};
const stageArgs={{...exact,revision:page.revision,proposal,idempotency_key:'fictional-author-stage'}};
"""


def stage_script(fixture) -> str:
    return (
        author_script(fixture)
        + """
const stagedCall=call('vera_workspace_financial_author_stage',stageArgs);
if(stagedCall.isError)throw new Error(JSON.stringify(stagedCall));
const staged=stagedCall.structuredContent;
if(!staged||!staged.saved)throw new Error(JSON.stringify(stagedCall));
const candidate=payload(call('vera_workspace_financial_author_read',{...exact,case_ref:staged.case_ref}));
const reviewFields={reviewer:'Fictional reviewer',reviewed_at:'2026-10-07',basis:'Explicit review of the complete fictional case, its sources and professional choices.'};
const reviewArgs={...exact,case_ref:staged.case_ref,item_id:staged.case_ref,source_ref:exact.grant_ref,revision:candidate.revision,review_ticket:candidate.review_ticket,expected_review_draft_revision:candidate.review_draft_revision,fields:reviewFields,confirmed:true,idempotency_key:'fictional-author-review'};
"""
    )


def test_native_financial_model_case_requires_named_review_and_executes_all_public_recipes(
    financial_intake,
):
    env, output, _, pack, _, bindings = financial_intake
    result = rpc_program(
        env,
        stage_script(financial_intake)
        + """
const premature=call('vera_workspace_financial_case',{...work,pack_id:fields.pack_id,case_input_id:staged.case_ref});
const context=call('vera_workspace_financial_author_context',{...exact,case_ref:staged.case_ref,revision:candidate.revision}).structuredContent;
const retry=call('vera_workspace_financial_author_stage',stageArgs).structuredContent;
const reviewed=payload(call('vera_workspace_financial_author_review',reviewArgs));
const eligible=payload(call('vera_workspace_financial_case',{...work,pack_id:fields.pack_id,case_input_id:reviewed.case_ref}));
const execution=payload(call('vera_workspace_financial_execute',{...work,pack_id:fields.pack_id,case_input_id:reviewed.case_ref,item_id:eligible.selection.id,revision:eligible.revision,review_ticket:eligible.review_ticket,source_bindings:proposal.source_bindings,human_reviewed:true,confirmed:true,idempotency_key:'fictional-authored-execution'}));
const result={staged,premature,context,retry,reviewed,execution,after:payload(call('vera_workspace_financial_setup',work))};
""",
    )
    assert result["staged"]["validation"]["valid"] is True
    assert result["staged"]["validation"]["recipe_executed"] is False
    assert result["premature"]["isError"] is True
    assert result["retry"] == result["staged"]
    assert result["context"]["professional_approval"] is False
    assert "review_draft" not in result["context"]
    assert result["reviewed"]["financial_conclusions_approved"] is False
    assert result["execution"]["status"] == "passed"
    assert result["execution"]["pack_id"] == pack
    assert result["execution"]["run_completed"] is False
    candidate = output / result["reviewed"]["case_ref"]
    calculation = output / result["execution"]["source_ref"]
    assert (candidate / "case/case.json").read_bytes() == (
        calculation / "case/case.json"
    ).read_bytes()
    assert len(result["after"]["versions"]) == 1
    assert any(
        row["id"] == result["reviewed"]["case_ref"] for row in result["after"]["inputs"]
    )
    assert len(result["context"]["sources"]) == len(
        {*bindings.values(), financial_intake[4]}
    )


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_authoring_draft_empty_generation_and_stale_refusal(
    financial_intake,
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        """
const work={work_ref:'fictional-financial'};
const setup=payload(call('vera_workspace_financial_author_setup',work));
const fields={pack_id:'',input_ids:[],question:'Literal unsent question.',base_ref:''};
const args={...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields};
const saved=payload(call('vera_workspace_financial_author_draft_save',args));
const stale=call('vera_workspace_financial_author_draft_save',{...args,fields:{...fields,question:''}});
const reopened=call('vera_workspace_financial_author_setup',work);
const clear=payload(call('vera_workspace_financial_author_draft_save',{...args,expected_draft_revision:reopened._meta.workspace.draft_revision,fields:{...fields,question:''}}));
const replay=call('vera_workspace_financial_author_draft_save',{...args,expected_draft_revision:reopened._meta.workspace.draft_revision});
const result={saved,stale,reopened,clear,replay,after:payload(call('vera_workspace_financial_author_setup',work))};
""",
    )
    assert (
        result["reopened"]["_meta"]["workspace"]["draft"]["question"]
        == "Literal unsent question."
    )
    assert "Literal unsent question." not in json.dumps(
        result["reopened"]["structuredContent"]
    )
    assert result["stale"]["isError"] is True
    assert result["replay"]["isError"] is True
    assert result["after"]["draft"]["question"] == ""
    assert result["after"]["grants"] == []
    assert list(output.glob("financial-authored-*")) == []


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_professional_review_draft_recovers_without_approval_or_model_leak(
    financial_intake,
):
    env, *_ = financial_intake
    result = rpc_program(
        env,
        stage_script(financial_intake)
        + """
const args={...reviewArgs};delete args.confirmed;delete args.idempotency_key;
const saved=payload(call('vera_workspace_financial_author_review_draft_save',args));
const stale=call('vera_workspace_financial_author_review_draft_save',{...args,fields:{reviewer:'',reviewed_at:'',basis:''}});
const reopened=payload(call('vera_workspace_financial_author_read',{...exact,case_ref:staged.case_ref}));
const model=call('vera_workspace_financial_author_context',{...exact,case_ref:staged.case_ref,revision:reopened.revision}).structuredContent;
const result={saved,stale,reopened,model};
""",
    )
    assert result["reopened"]["review_draft"]["reviewer"] == "Fictional reviewer"
    assert result["reopened"]["review"] is None
    assert result["saved"]["case_reviewed"] is False
    assert result["stale"]["isError"] is True
    assert "review_draft" not in result["model"]


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
@pytest.mark.parametrize(
    "change",
    [
        "confirmed:false",
        "fields:{...reviewFields,reviewer:''}",
        "item_id:'foreign'",
        "revision:'stale'",
        "expected_review_draft_revision:'stale'",
    ],
)
def test_native_financial_case_review_refuses_invalid_confirmation_selection_or_named_review(
    financial_intake, change
):
    env, *_ = financial_intake
    result = rpc_program(
        env,
        stage_script(financial_intake)
        + f"const result=call('vera_workspace_financial_author_review',{{...reviewArgs,{change}}});",
    )
    assert result["isError"] is True


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_invalid_contract_is_retained_and_cannot_be_reviewed(
    financial_intake,
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        author_script(financial_intake)
        + """
proposal.case.content_sha256='0'.repeat(64);
const staged=call('vera_workspace_financial_author_stage',stageArgs).structuredContent;
const invalidPage=payload(call('vera_workspace_financial_author_read',{...exact,case_ref:staged.case_ref}));
const refused=call('vera_workspace_financial_author_review',{...exact,case_ref:staged.case_ref,item_id:staged.case_ref,source_ref:exact.grant_ref,revision:invalidPage.revision,review_ticket:invalidPage.review_ticket,expected_review_draft_revision:invalidPage.review_draft_revision,fields:{reviewer:'Fictional reviewer',reviewed_at:'2026-10-07',basis:'Cannot approve stale digest.'},confirmed:true,idempotency_key:'invalid-review'});
const result={staged,refused};
""",
    )
    assert result["staged"]["validation"]["valid"] is False
    assert result["refused"]["isError"] is True
    assert (output / result["staged"]["case_ref"] / "validation.json").is_file()


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_cancel_retains_proposal_and_refuses_model_reads_and_writes(
    financial_intake,
):
    env, output, binding, *_ = financial_intake
    result = rpc_program(
        env,
        stage_script(financial_intake)
        + """
const cancelled=payload(call('vera_workspace_financial_author_cancel',{...exact,source_ref:exact.grant_ref,item_id:staged.case_ref,revision:candidate.revision,review_ticket:candidate.review_ticket,confirmed:true,idempotency_key:'fictional-author-cancel'}));
const fresh=payload(call('vera_workspace_financial_author_read',{...exact,case_ref:staged.case_ref}));
const read=call('vera_workspace_financial_author_context',{...exact,revision:fresh.revision});
const write=call('vera_workspace_financial_author_stage',{...stageArgs,revision:fresh.revision,idempotency_key:'new-stage-after-cancel'});
const result={staged,cancelled,fresh,read,write};
""",
    )
    assert result["cancelled"]["status"] == "cancelled"
    assert result["read"]["isError"] is True
    assert result["write"]["isError"] is True
    assert (output / result["staged"]["case_ref"] / "case/case.json").is_file()
    closure = rpc_program(
        archive_environment(env, binding, output),
        f"const result=call('vera_workspace_archive_closure',{json.dumps({k:binding[k] for k in ['client_id','engagement_id','run_id']})});",
    )
    assert not closure.get("isError")


@pytest.mark.parametrize(
    "financial_intake",
    [
        "quality_of_earnings",
        "net_debt",
        "normalized_working_capital",
        "capex",
        "deal_bridges",
    ],
    indirect=True,
)
def test_native_financial_pending_fdd_fields_build_public_case_only_after_actual_named_review(
    financial_intake,
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        author_script(financial_intake)
        + PENDING_FDD
        + """
const stagedCall=call('vera_workspace_financial_author_stage',stageArgs);if(stagedCall.isError)throw new Error(JSON.stringify(stagedCall));
const staged=stagedCall.structuredContent;
const candidate=payload(call('vera_workspace_financial_author_read',{...exact,case_ref:staged.case_ref}));
const reviewed=payload(call('vera_workspace_financial_author_review',{...exact,case_ref:staged.case_ref,item_id:staged.case_ref,source_ref:exact.grant_ref,revision:candidate.revision,review_ticket:candidate.review_ticket,expected_review_draft_revision:candidate.review_draft_revision,fields:{reviewer:'Fictional real reviewer',reviewed_at:'2026-10-07',basis:'Named review of this complete proposal and each professional decision.'},confirmed:true,idempotency_key:'pending-fdd-review'}));
const eligible=payload(call('vera_workspace_financial_case',{...work,pack_id:fields.pack_id,case_input_id:reviewed.case_ref}));
const execution=payload(call('vera_workspace_financial_execute',{...work,pack_id:fields.pack_id,case_input_id:reviewed.case_ref,item_id:eligible.selection.id,revision:eligible.revision,review_ticket:eligible.review_ticket,source_bindings:proposal.source_bindings,human_reviewed:true,confirmed:true,idempotency_key:'pending-fdd-execute'}));
const result={staged,candidate,reviewed,eligible,execution};
""",
    )
    assert result["staged"]["validation"]["valid"] is False
    assert result["staged"]["validation"]["reviewable"] is True
    assert (
        result["candidate"]["case"]["schema_version"]
        == "vera.native.fdd_case_proposal.v1"
    )
    assert "review" not in result["candidate"]["case"]
    public = result["eligible"]["case_content"]
    assert public["schema_version"] == "vera.fdd_execution_bundle.v2"
    assert public["fdd_case"]["review"]["reviewed_on"] == "2026-10-07"
    assert public["fdd_case"]["review"]["reviewer_ref"].startswith("reviewer.native-")
    assert {d["reviewed_on"] for d in public["fdd_case"]["reviewed_decisions"]} == {
        "2026-10-07"
    }
    assert result["execution"]["status"] == "passed"
    assert result["reviewed"]["case_ref"] != result["staged"]["case_ref"]
    receipt = json.loads(
        (output / result["reviewed"]["case_ref"] / "case_review.json").read_bytes()
    )
    assert receipt["proposal_ref"] == result["staged"]["case_ref"]
    assert receipt["fields"]["reviewer"] == "Fictional real reviewer"


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_retained_model_correction_changes_calculation_without_replacing_predecessor(
    financial_intake,
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        author_script(financial_intake)
        + PENDING_FDD
        + """
const first=call('vera_workspace_financial_author_stage',stageArgs).structuredContent;
const fresh=payload(call('vera_workspace_financial_author_read',exact));
const oldContext=call('vera_workspace_financial_author_context',{...exact,case_ref:first.case_ref,revision:fresh.revision}).structuredContent;
proposal.case.inputs.items.find(i=>i.item_id==='item.debt').amount='600';
const second=call('vera_workspace_financial_author_stage',{...stageArgs,revision:fresh.revision,idempotency_key:'second-corrected-proposal'}).structuredContent;
const noLatest=payload(call('vera_workspace_financial_author_read',exact));
const historical=payload(call('vera_workspace_financial_author_read',{...exact,case_ref:first.case_ref}));
const candidate=payload(call('vera_workspace_financial_author_read',{...exact,case_ref:second.case_ref}));
const reviewed=payload(call('vera_workspace_financial_author_review',{...exact,case_ref:second.case_ref,item_id:second.case_ref,source_ref:exact.grant_ref,revision:candidate.revision,review_ticket:candidate.review_ticket,expected_review_draft_revision:candidate.review_draft_revision,fields:{reviewer:'Fictional reviewer',reviewed_at:'2026-10-07',basis:'Reviewed corrected debt 600 from explicit fictional evidence.'},confirmed:true,idempotency_key:'corrected-review'}));
const corrected=payload(call('vera_workspace_financial_case',{...work,pack_id:fields.pack_id,case_input_id:reviewed.case_ref}));
const execution=payload(call('vera_workspace_financial_execute',{...work,pack_id:fields.pack_id,case_input_id:reviewed.case_ref,item_id:corrected.selection.id,revision:corrected.revision,review_ticket:corrected.review_ticket,source_bindings:proposal.source_bindings,human_reviewed:true,confirmed:true,idempotency_key:'corrected-execution'}));
const result={first,second,noLatest,historical,reviewed,execution,oldContext};
""",
    )
    assert "case" not in result["noLatest"]
    assert result["historical"]["case"]["inputs"]["items"][1]["amount"] == "500"
    assert result["oldContext"]["case"]["inputs"]["items"][1]["amount"] == "500"
    public = json.loads(
        (
            output / result["execution"]["source_ref"] / "prepared/fdd_result.json"
        ).read_bytes()
    )
    assert {r["metric_id"]: r["value"] for r in public["metrics"]}["net_debt"] == "550"
    assert (output / result["first"]["case_ref"] / "case/case.json").exists()
    assert (output / result["second"]["case_ref"] / "case/case.json").exists()


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_foreign_source_and_stale_model_stage_refuse_without_uncertain_copy(
    financial_intake,
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        author_script(financial_intake)
        + """
const outside=call('vera_workspace_financial_author_stage',{...stageArgs,proposal:{...proposal,source_bindings:{'artifact.source':'foreign'}}});
const staged=call('vera_workspace_financial_author_stage',stageArgs).structuredContent;
const stale=call('vera_workspace_financial_author_stage',{...stageArgs,idempotency_key:'stale-new-stage'});
const result={outside,stale,staged,after:payload(call('vera_workspace_financial_setup',work))};
""",
    )
    assert result["outside"]["isError"] is True
    assert result["stale"]["isError"] is True
    assert result["after"]["recovery_required"] is False
    assert len(list(output.glob("financial-authored-*"))) == 1


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_interrupted_contract_check_preserves_candidate_and_blocks_closure(
    financial_intake, monkeypatch
):
    env, output, binding, *_ = financial_intake
    prepared = rpc_program(
        env, author_script(financial_intake) + "const result={args:stageArgs};"
    )
    module = workspace_module()
    import native_financial_authoring as authoring

    original = authoring.public_check

    def interrupted(root, request):
        if "operation" not in request:
            raise OSError("Fictional contract check interrupted")
        return original(root, request)

    monkeypatch.setattr(authoring, "public_check", interrupted)
    with pytest.raises(OSError, match="Fictional contract check interrupted"):
        module.dispatch("vera_workspace_financial_author_stage", prepared["args"])
    monkeypatch.setattr(authoring, "public_check", original)
    read = rpc_program(
        env,
        "const result=payload(call('vera_workspace_financial_setup',{work_ref:'fictional-financial'}));",
    )
    assert read["recovery_required"] is True
    assert len(list(output.glob("financial-authored-*"))) == 1
    closure = rpc_program(
        archive_environment(env, binding, output),
        f"const result=call('vera_workspace_archive_closure',{json.dumps({k:binding[k] for k in ['client_id','engagement_id','run_id']})});",
    )
    assert closure["isError"] is True
    assert "requires recovery before output closure" in closure["content"][0]["text"]


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_open_authoring_mandate_blocks_shared_closure(
    financial_intake,
):
    env, output, binding, *_ = financial_intake
    rpc_program(env, author_script(financial_intake) + "const result=request;")
    closure = rpc_program(
        archive_environment(env, binding, output),
        f"const result=call('vera_workspace_archive_closure',{json.dumps({k:binding[k] for k in ['client_id','engagement_id','run_id']})});",
    )
    assert closure["isError"] is True
    assert "exact case review or explicit cancellation" in closure["content"][0]["text"]


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_viewer_cannot_stage_or_review_and_tampered_case_refuses_read(
    financial_intake,
):
    env, output, *_ = financial_intake
    stored = rpc_program(
        env,
        stage_script(financial_intake) + "const result={stageArgs,reviewArgs,staged};",
    )
    denied = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": "VIEWER"},
        f"const result={{stage:call('vera_workspace_financial_author_stage',{json.dumps(stored['stageArgs'])}),review:call('vera_workspace_financial_author_review',{json.dumps(stored['reviewArgs'])})}};",
    )
    assert denied["stage"]["isError"] is True
    assert denied["review"]["isError"] is True
    case = output / stored["staged"]["case_ref"] / "case/case.json"
    case.write_bytes(case.read_bytes() + b"\n")
    refused = rpc_program(
        env,
        f"const result=call('vera_workspace_financial_author_read',{{work_ref:'fictional-financial',grant_ref:{json.dumps(stored['stageArgs']['grant_ref'])},case_ref:{json.dumps(stored['staged']['case_ref'])}}});",
    )
    assert refused["isError"] is True
