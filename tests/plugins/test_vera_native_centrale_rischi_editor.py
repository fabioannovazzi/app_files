"""Exact signed CR drafts remain pending, recoverable and concurrency safe."""

from __future__ import annotations

import json

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_centrale_rischi import (
    INSPECT,
    cr_run,
    proposal_script,
)
from tests.plugins.test_vera_native_workspace import workspace_module

__all__ = ["cr_run"]

EDITOR = """
const editor=()=>payload(call('vera_workspace_cr_recipe_read',exact));
const editScope=e=>({...exact,item_id:grant.grant_ref,source_ref:inspected.source_ref,revision:e.revision,review_ticket:e.review_ticket,expected_draft_revision:e.draft_revision,expected_proposal_revision:e.proposal_revision});
const initialEditor=editor();
"""


def test_cr_recipe_draft_restores_complete_pending_recipe_and_stages_without_calculation(
    cr_run,
):
    env, output, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + EDITOR
        + """
const fields=structuredClone(initialEditor.fields);fields.entity='Soggetto fittizio Ω';
fields.value_mappings.original_term['Chiave ancora ignota']='';
Object.defineProperty(fields.value_mappings.original_term,'__proto__',{value:'unclassified',enumerable:true});
const saved=payload(call('vera_workspace_cr_recipe_save',{...editScope(initialEditor),fields}));
const restored=editor();
const stage={...editScope(restored),confirmed:true,idempotency_key:'editor-stage'};
const editorStaged=payload(call('vera_workspace_cr_recipe_stage',stage));
const retry=payload(call('vera_workspace_cr_recipe_stage',stage));
const after=editor(),candidateAfter=payload(call('vera_workspace_cr_proposal_read',exact));
const result={fields,saved,restored,staged:editorStaged,retry,after,candidateAfter};
""",
    )
    assert result["restored"]["draft"] == result["fields"]
    assert result["restored"]["draft"]["mapping_review"] == {
        "status": "pending",
        "reviewer": "",
        "reviewed_at": "",
    }
    assert result["staged"] == result["retry"]
    assert result["staged"]["professional_approval"] is False
    assert result["after"]["draft"] is None
    assert result["candidateAfter"]["proposal"] == result["fields"]
    assert len(list(output.glob("cr-*"))) == 1
    assert (
        len(list((output.parent / ".native-workspace").glob("*-proposal-*.json"))) == 2
    )


def test_cr_recipe_editor_can_start_incomplete_template_without_model_proposal(cr_run):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        INSPECT
        + EDITOR
        + """
const saved=payload(call('vera_workspace_cr_recipe_save',{...editScope(initialEditor),fields:initialEditor.fields}));
const restored=editor();
const stage=payload(call('vera_workspace_cr_recipe_stage',{...editScope(restored),confirmed:true,idempotency_key:'manual-pending'}));
const result={initialEditor,saved,restored,stage};
""",
    )
    assert result["initialEditor"]["proposal_revision"] == ""
    assert result["restored"]["draft"] == result["initialEditor"]["fields"]
    assert result["stage"]["status"] == "proposal_pending_review"


@pytest.mark.parametrize(
    "change",
    [
        "fields.mapping_review.status='reviewed'",
        "fields.inventory_sha256='foreign'",
        "fields.table_id='foreign'",
        "fields.columns.original_duration='absent column'",
        "fields.value_mappings.original_term['ignoto']='invented class'",
        "fields.control_totals.foreign='100'",
        "fields.control_totals.used=100",
    ],
)
def test_cr_recipe_draft_refuses_foreign_provenance_or_invalid_mechanical_choices(
    cr_run, change
):
    env, output, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + EDITOR
        + f"""
const fields=structuredClone(initialEditor.fields);{change};
const refused=call('vera_workspace_cr_recipe_save',{{...editScope(initialEditor),fields}});
const result={{refused,reopened:editor()}};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["reopened"]["draft"] is None
    assert list((output.parent / ".native-workspace").glob("cr-editor-*.json")) == []


def test_cr_recipe_model_update_preserves_stale_draft_until_explicit_discard(cr_run):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + EDITOR
        + """
const fields={...initialEditor.fields,entity:'Bozza precedente'};
payload(call('vera_workspace_cr_recipe_save',{...editScope(initialEditor),fields}));
const savedEditor=editor();
const modelUpdate={...proposal,entity:'Proposta nuova del modello'};
model('vera_workspace_cr_stage',{...exact,expected_proposal_revision:savedEditor.proposal_revision,proposal:modelUpdate,idempotency_key:'new-model-proposal'});
const stale=editor();
const saveRefused=call('vera_workspace_cr_recipe_save',{...editScope(stale),fields});
const stageRefused=call('vera_workspace_cr_recipe_stage',{...editScope(stale),confirmed:true,idempotency_key:'stale-editor-stage'});
const cleared=payload(call('vera_workspace_cr_recipe_clear',editScope(stale)));
const reopened=editor();
const oldClear=call('vera_workspace_cr_recipe_clear',editScope(stale));
const result={stale,saveRefused,stageRefused,cleared,reopened,oldClear};
""",
    )
    assert result["stale"]["stale"] is True
    assert result["stale"]["draft"]["entity"] == "Bozza precedente"
    assert result["saveRefused"]["isError"] is True
    assert result["stageRefused"]["isError"] is True
    assert result["oldClear"]["isError"] is True
    assert result["reopened"]["fields"]["entity"] == "Proposta nuova del modello"
    assert result["reopened"]["draft"] is None
    assert result["reopened"]["draft_revision"] != ""


@pytest.mark.parametrize(
    "change",
    ["item_id:'foreign'", "source_ref:'foreign'", "expected_draft_revision:'foreign'"],
)
def test_cr_recipe_save_rejects_foreign_ticket_or_checkpoint(cr_run, change):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + EDITOR
        + f"""
const result={{refused:call('vera_workspace_cr_recipe_save',{{...editScope(initialEditor),fields:initialEditor.fields,{change}}}),reopened:editor()}};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["reopened"]["draft"] is None


def test_cr_recipe_draft_compare_and_swap_refuses_lost_update(cr_run):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + EDITOR
        + """
payload(call('vera_workspace_cr_recipe_save',{...editScope(initialEditor),fields:{...initialEditor.fields,entity:'Prima bozza'}}));
const refused=call('vera_workspace_cr_recipe_save',{...editScope(initialEditor),fields:{...initialEditor.fields,entity:'Sovrascrittura'}});
const result={refused,reopened:editor()};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["reopened"]["draft"]["entity"] == "Prima bozza"


def test_cr_recipe_app_proposal_requires_separate_named_review_before_public_calculation(
    cr_run,
):
    env, output, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + EDITOR
        + """
payload(call('vera_workspace_cr_recipe_save',{...editScope(initialEditor),fields:{...initialEditor.fields,entity:'Soggetto riesaminato'}}));
payload(call('vera_workspace_cr_recipe_stage',{...editScope(editor()),confirmed:true,idempotency_key:'app-pending-proposal'}));
const pending=payload(call('vera_workspace_cr_proposal_read',exact));
const reviewedArgs={...calculateArgs,revision:pending.revision,review_ticket:pending.review_ticket,proposal_sha256:pending.proposal_sha256};
const unnamed=call('vera_workspace_cr_calculate',{...reviewedArgs,reviewer:'',idempotency_key:'missing-named-review'});
const calculated=payload(call('vera_workspace_cr_calculate',reviewedArgs));
const result={pending,unnamed,calculated};
""",
    )
    assert result["pending"]["proposal"]["mapping_review"]["status"] == "pending"
    assert result["unnamed"]["isError"] is True
    reviewed = json.loads(
        (
            output / result["calculated"]["source_ref"] / "reviewed_recipe.json"
        ).read_bytes()
    )
    assert reviewed["entity"] == "Soggetto riesaminato"
    assert reviewed["mapping_review"]["reviewer"] == "Fictional professional"
    assert result["calculated"]["professional_approval"] is False
    assert result["calculated"]["run_completed"] is False
    assert (
        output / result["calculated"]["source_ref"] / "centrale_rischi_analysis.json"
    ).is_file()


def test_cr_recipe_interrupted_conservation_keeps_history_draft_and_blocks_retry(
    cr_run, monkeypatch
):
    env, output, _ = cr_run
    fixture = rpc_program(
        env,
        proposal_script()
        + EDITOR
        + """
payload(call('vera_workspace_cr_recipe_save',{...editScope(initialEditor),fields:{...initialEditor.fields,entity:'Bozza da conservare'}}));
const result={stageArgs:{...editScope(editor()),confirmed:true,idempotency_key:'interrupted-editor-stage'},original:initialEditor.fields};
""",
    )
    module = workspace_module()
    args = fixture["stageArgs"]
    args.pop("review_ticket")
    atomic = module.atomic_json

    def refuse_pointer(path, payload):
        if path.name.endswith("-proposal.json"):
            raise OSError("Fictional interrupted pointer write")
        atomic(path, payload)

    monkeypatch.setattr(module, "atomic_json", refuse_pointer)
    with pytest.raises(OSError, match="Fictional interrupted pointer write"):
        module.dispatch("vera_workspace_cr_recipe_stage", args)
    monkeypatch.setattr(module, "atomic_json", atomic)
    reopened = module.dispatch(
        "vera_workspace_cr_recipe_read",
        {"work_ref": "fictional-cr", "grant_ref": args["grant_ref"]},
    )
    assert reopened["can_write"] is False
    assert reopened["draft"]["entity"] == "Bozza da conservare"
    assert reopened["fields"] == fixture["original"]
    assert (
        len(list((output.parent / ".native-workspace").glob("*-proposal-*.json"))) == 2
    )
    with pytest.raises(ValueError, match="interrupted CR recipe request"):
        module.dispatch("vera_workspace_cr_recipe_stage", args)
