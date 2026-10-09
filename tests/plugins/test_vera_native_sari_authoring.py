"""Owned synthetic SARI proposals through maintained public producers, not host acceptance."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.plugins import test_vera_native_workspace as factory
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_sari_intake import (  # noqa: F401
    initialized_program,
    sari_run,
)

__all__ = []


def output_hashes(output: Path) -> dict[str, str]:
    return {
        p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in output.rglob("*")
        if p.is_file()
    }


def author_program(fixture) -> str:
    """Use actual signed app authority and an explicit saved fictional question."""
    return (
        initialized_program(fixture)
        + """
const authorCall=call('vera_workspace_sari_author_setup',work),author=payload(authorCall);
const authorAuthority=state=>({...work,revision:state.revision,review_ticket:state.review_ticket,expected_draft_revision:state.draft_revision});
const question={question:'Prepare a fictional source-backed registry draft; chamber and applicability unresolved.',input_ids:[author.sources[0].input_id]};
const savedAuthor=payload(call('vera_workspace_sari_author_draft_save',{...authorAuthority(author),fields:question}));
const requestAuthor={...authorAuthority(author),expected_draft_revision:savedAuthor.draft_revision,fields:question,confirmed:true,idempotency_key:'synthetic-sari-author-request'};
const grant=payload(call('vera_workspace_sari_author_request',requestAuthor));
const mandate={...work,grant_ref:grant.grant_ref};
const contextCall=call('vera_workspace_sari_author_context',{...mandate,revision:grant.revision});
if(contextCall.isError)throw new Error(contextCall.content[0].text);
const context=contextCall.structuredContent;
const proposal={case_intake:structuredClone(context.initial_case),practice_plan:structuredClone(context.initial_plan),sources:[{
source_id:'SRC-FICTIONAL-001',source_type:'official_sari_selected_result',title:'Synthetic SARI metadata for mechanical tests only',
official_url:'https://supportospecialisticori.infocamere.it/sariWeb/ptpo?apriContenuto=SYNTHETIC001',
publisher:'Synthetic authority fixture',territorial_applicability:'Unresolved fictional territory'}]};
proposal.case_intake.competent_chamber={tenant:'UNRESOLVED',name:'Fictional chamber to verify',territorial_basis:'Unresolved fixture',confirmation_status:'unknown'};
proposal.case_intake.subject.legal_form='Fictional legal form, to verify';
proposal.case_intake.activity.description='Fictional documented activity, to verify';
proposal.case_intake.requested_operation.description='Fictional operation to review';
proposal.case_intake.requested_operation.position_types=['registro_imprese'];
proposal.case_intake.professional_question=question.question;
proposal.practice_plan.case_summary='Synthetic proposed case, no real legal acceptance.';
proposal.practice_plan.sari_question_draft='Fictional chamber question, not sent.';
proposal.practice_plan.position_matrix=[{id:'POSITION-FICTIONAL',title:'Fictional registry position',detail:'Source relevance unresolved.',source_ids:['SRC-FICTIONAL-001'],case_fact_ids:['CASE-OPERATION'],review_status:'proposed'}];
proposal.practice_plan.dire_steps=[{id:'STEP-FICTIONAL',title:'Fictional preparation step',detail:'Review authority and facts first.',source_ids:['SRC-FICTIONAL-001'],case_fact_ids:['CASE-CHAMBER'],review_status:'proposed'}];
const stageArgs={...mandate,revision:grant.revision,proposal,idempotency_key:'synthetic-sari-stage'};
"""
    )


def register_program() -> str:
    return """
const stageCall=call('vera_workspace_sari_author_stage',stageArgs);
if(stageCall.isError)throw new Error(stageCall.content[0].text);
const staged=stageCall.structuredContent;
const stagedPage=payload(call('vera_workspace_sari_author_read',{...mandate,stage_ref:staged.stage_ref}));
const registerArgs={...mandate,stage_ref:staged.stage_ref,source_ref:stagedPage.source_ref,revision:stagedPage.revision,review_ticket:stagedPage.review_ticket,source_ids:['SRC-FICTIONAL-001'],reviewer:'Declared fictional source selector',confirmed:true,idempotency_key:'synthetic-sari-register'};
"""


def test_sari_author_private_question_and_context_are_separate_exact_scopes(sari_run):
    result = rpc_program(
        os.environ.copy(),
        author_program(sari_run)
        + """
const recoveredCall=call('vera_workspace_sari_author_setup',work);
const retry=payload(call('vera_workspace_sari_author_request',requestAuthor));
const result={authorCall,savedAuthor,recoveredCall,recovered:payload(recoveredCall),contextCall,grant,retry};
""",
    )

    context = result["contextCall"]["structuredContent"]
    assert "fields" not in result["authorCall"]["structuredContent"]
    assert "Prepare a fictional" not in json.dumps(result["recoveredCall"]["content"])
    assert result["recovered"]["fields"]["question"] == context["question"]
    assert len(context["selected_originals"]) == 1
    assert Path(context["selected_originals"][0]["path"]).is_file()
    assert context["professional_decisions"] == "pending_only"
    assert context["actual_model_reads_verified"] is False
    assert {
        key: value for key, value in result["retry"].items() if key != "review_ticket"
    } == {
        key: value for key, value in result["grant"].items() if key != "review_ticket"
    }
    assert "_meta" not in result["contextCall"]
    assert (sari_run[2] / "official_sources.json").exists() is False


@pytest.mark.parametrize("copy_original", [False, True])
def test_sari_author_preview_and_confirmed_conservation_preserve_pending_decisions_and_initial_bytes(
    sari_run, copy_original
):
    result = rpc_program(
        os.environ.copy(),
        author_program(sari_run)
        + (
            "proposal.sources[0].snapshot_input_id=question.input_ids[0];\n"
            if copy_original
            else ""
        )
        + register_program()
        + """
const missingConfirmation=call('vera_workspace_sari_author_register',{...registerArgs,confirmed:false});
const missingSource=call('vera_workspace_sari_author_register',{...registerArgs,source_ids:[]});
const registered=payload(call('vera_workspace_sari_author_register',registerArgs));
const retry=payload(call('vera_workspace_sari_author_register',registerArgs));
const after=payload(call('vera_workspace_sari_author_read',{...mandate,stage_ref:staged.stage_ref}));
const result={context,staged,stagedPage,missingConfirmation,missingSource,registered,retry,after};
""",
    )

    output = sari_run[2]
    initial = next(
        output.parent.glob(
            ".native-workspace/sari-author-*/mandate-*/initial-output/case_intake_draft.json"
        )
    )
    assert json.loads(initial.read_bytes()) == result["context"]["initial_case"]
    assert result["staged"]["public_outputs_registered"] is False
    assert result["staged"]["audit_status"] == "passed_with_blockers"
    assert result["stagedPage"]["preview"]["final_artifacts"]["ready_to_file"] is False
    assert result["missingConfirmation"]["isError"] is True
    assert result["missingSource"]["isError"] is True
    assert result["registered"] == result["retry"]
    assert result["registered"]["status"] == "partial_review"
    assert result["registered"]["ready_to_file"] is False
    assert result["registered"]["actual_model_reads_verified"] is False
    assert result["after"]["status"] == "registered"
    source = json.loads((output / "official_sources.json").read_bytes())["sources"][0]
    assert source["selected_by"] == "Declared fictional source selector"
    assert (
        source["selection_status"]
        == "selected_requires_professional_applicability_review"
    )
    assert source["authorization_basis"] == (
        "user_provided_copy" if copy_original else "browser_assisted_metadata"
    )
    if copy_original:
        original = Path(result["context"]["selected_originals"][0]["path"])
        assert (output / source["artifact_path"]).read_bytes() == original.read_bytes()
    else:
        assert source["artifact_path"] is None
    plan = json.loads((output / "practice_plan_validated.json").read_bytes())
    assert plan["professional_review"]["status"] == "pending"
    assert plan["position_matrix"][0]["review_status"] == "proposed"
    assert result["registered"]["artifacts"] == output_hashes(output)


@pytest.mark.parametrize(
    "change",
    [
        "proposal.case_intake.competent_chamber.confirmation_status='confirmed'",
        "proposal.practice_plan.professional_review.status='reviewed'",
        "proposal.practice_plan.position_matrix[0].confirmation={confirmed_by_id:'invented'}",
        "proposal.sources[0].official_url='https://invalid.example/private'",
        "proposal.sources[0].snapshot_input_id='not-selected'",
        "proposal.case_intake.jurisdiction='CH-GE'",
    ],
)
def test_sari_author_expected_proposal_refusal_has_no_public_mutation_or_uncertain_intent(
    sari_run, change
):
    result = rpc_program(
        os.environ.copy(),
        author_program(sari_run)
        + change
        + ";\n"
        + """
const refused=call('vera_workspace_sari_author_stage',stageArgs);
const current=payload(call('vera_workspace_sari_author_setup',work));
const result={refused,current};
""",
    )

    assert result["refused"]["isError"] is True
    assert result["current"]["can_author"] is True
    assert result["current"]["recovery_required"] is False
    assert (sari_run[2] / "official_sources.json").exists() is False
    stored = json.loads(
        next(
            sari_run[2].parent.glob(".native-workspace/sari-author-*/state.json")
        ).read_bytes()
    )
    assert len(stored["operations"]) == 1
    assert stored["grants"][0]["stages"] == []


def test_sari_author_schema_errors_remain_private_and_block_registration(sari_run):
    result = rpc_program(
        os.environ.copy(),
        author_program(sari_run)
        + "proposal.practice_plan.case_summary='';\n"
        + register_program()
        + """
const refused=call('vera_workspace_sari_author_register',registerArgs);
const result={staged,stagedPage,refused};
""",
    )

    assert result["staged"]["audit_status"] == "schema_error"
    assert result["stagedPage"]["preview"]["final_artifacts"] is None
    assert result["refused"]["isError"] is True
    assert (sari_run[2] / "practice_validation_audit.json").exists() is False


def test_sari_author_obsolete_mandate_can_be_cancelled_without_changing_public_case(
    sari_run,
):
    result = rpc_program(
        os.environ.copy(),
        author_program(sari_run)
        + """
const fs=require('node:fs');fs.writeFileSync({output},'Additional ordinary evidence, preserved after cancellation.');
const old=call('vera_workspace_sari_author_context',{...mandate,revision:grant.revision});
const changedPage=payload(call('vera_workspace_sari_author_read',mandate));
const cancellation={...mandate,revision:changedPage.revision,review_ticket:changedPage.review_ticket,confirmed:true,idempotency_key:'synthetic-cancel'};
const cancelled=payload(call('vera_workspace_sari_author_cancel',cancellation));
const retry=payload(call('vera_workspace_sari_author_cancel',cancellation));
const result={old,page:changedPage,cancelled,retry};
""".replace(
            "{output}", json.dumps(str(sari_run[2] / "additional-evidence.txt"))
        ),
    )

    assert result["old"]["isError"] is True
    assert result["page"]["obsolete"] is True
    assert result["cancelled"] == result["retry"]
    assert result["cancelled"]["public_case_unchanged"] is True


def test_sari_author_viewer_and_forged_scope_cannot_authorize(sari_run):
    result = rpc_program(
        os.environ.copy(),
        author_program(sari_run)
        + """
const forged=call('vera_workspace_sari_author_request',{...requestAuthor,review_ticket:'forged.signature',idempotency_key:'forged'});
process.env.VERA_WORKSPACE_ROLES='VIEWER';
const refused=call('vera_workspace_sari_author_stage',stageArgs);
const viewer=payload(call('vera_workspace_sari_author_setup',work));
const result={forged,refused,viewer};
""",
    )

    assert result["forged"]["isError"] is True
    assert result["refused"]["isError"] is True
    assert result["viewer"]["can_write"] is False
    assert (sari_run[2] / "official_sources.json").exists() is False


def test_sari_author_uncertain_intent_blocks_writes_and_audit_retains_open_mandate(
    sari_run,
):
    rpc_program(os.environ.copy(), author_program(sari_run) + "const result={grant};")
    output = sari_run[2]
    api = factory.workspace_module()
    spec = importlib.util.spec_from_file_location(
        "sari_author_audit_test",
        Path(api.__file__).with_name("native_sari_authoring.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    audited = module.audit_run(output, SimpleNamespace(**vars(api)))
    assert audited["unfinished"] is True
    assert audited["recovery_required"] is False
    state_path = next(output.parent.glob(".native-workspace/sari-author-*/state.json"))
    stored = json.loads(state_path.read_bytes())
    request = {"action": "stage", "grant_ref": stored["grants"][0]["grant_ref"]}
    stored["operations"].append(
        {
            "key": "interrupted-stage",
            "request": request,
            "fingerprint": module.stamp(request),
            "status": "pending",
        }
    )
    state_path.write_text(json.dumps(stored))
    result = rpc_program(
        os.environ.copy(),
        """
const result=payload(call('vera_workspace_sari_author_setup',{work_ref:'fictional-registry-intake'}));
""",
    )
    assert result["recovery_required"] is True
    assert result["can_write"] is False


def test_sari_author_preview_keeps_public_population_unchanged_and_exact_stage_retry(
    sari_run,
):
    result = rpc_program(
        os.environ.copy(),
        author_program(sari_run)
        + register_program()
        + """
const retry=call('vera_workspace_sari_author_stage',stageArgs).structuredContent;
const changed=call('vera_workspace_sari_author_stage',{...stageArgs,proposal:{...proposal,sources:[]}});
const result={staged,retry,changed};
""",
    )
    assert result["staged"] == result["retry"]
    assert result["changed"]["isError"] is True
    initial = next(
        sari_run[2].parent.glob(
            ".native-workspace/sari-author-*/mandate-*/initial-output"
        )
    )
    assert output_hashes(sari_run[2]) == output_hashes(initial)


def test_sari_author_mandate_is_private_to_actual_actor(sari_run):
    result = rpc_program(
        os.environ.copy(),
        author_program(sari_run)
        + """
process.env.VERA_WORKSPACE_ACTOR_ID='another-actual-actor';
const read=call('vera_workspace_sari_author_read',mandate);
const deniedContext=call('vera_workspace_sari_author_context',{...mandate,revision:grant.revision});
const other=call('vera_workspace_sari_author_setup',work);
const result={read,deniedContext,other};
""",
    )
    assert result["read"]["isError"] is True
    assert result["deniedContext"]["isError"] is True
    assert result["other"]["isError"] is True
    assert "fields" not in result["other"]["_meta"]["workspace"]
    assert "grants" not in result["other"]["_meta"]["workspace"]
    assert "Prepare a fictional" not in json.dumps(result["other"])


def test_sari_author_changed_preview_cannot_be_registered(sari_run):
    result = rpc_program(
        os.environ.copy(),
        author_program(sari_run)
        + register_program()
        + """
const fs=require('node:fs'),path=require('node:path');
const privateRoot=path.join({parent},'.native-workspace');
const home=fs.readdirSync(privateRoot).find(name=>name.startsWith('sari-author-'));
fs.appendFileSync(path.join(privateRoot,home,grant.grant_ref,staged.stage_ref,'preview','studio_checklist.md'),'Changed private preview');
const refused=call('vera_workspace_sari_author_register',registerArgs);
const result={refused};
""".replace(
            "{parent}", json.dumps(str(sari_run[2].parent))
        ),
    )
    assert result["refused"]["isError"] is True
    assert (sari_run[2] / "official_sources.json").exists() is False
