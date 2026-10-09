"""Retained CR proposals are exact read-only choices, with CAS draft recovery."""

from __future__ import annotations

import json

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_centrale_rischi import cr_run, proposal_script
from tests.plugins.test_vera_native_centrale_rischi_editor import EDITOR
from tests.plugins.test_vera_native_workspace import workspace_module

__all__ = ["cr_run"]

HISTORY = """
const priorSha=candidate.proposal_sha256;
const priorRevision=model('vera_workspace_cr_model_context',exact).proposal_revision;
const newer={...proposal,entity:'Proposta corrente fittizia'};
model('vera_workspace_cr_stage',{...exact,expected_proposal_revision:priorRevision,proposal:newer,idempotency_key:'newer-history-proposal'});
const history=payload(call('vera_workspace_cr_proposal_history',exact));
const historical=payload(call('vera_workspace_cr_proposal_read',{...exact,proposal_sha256:priorSha}));
"""


def test_cr_historical_recipe_is_complete_read_only_and_recovers_as_pending_draft(
    cr_run,
):
    env, output, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + HISTORY
        + EDITOR
        + """
const signedHistoricalCalculation=call('vera_workspace_cr_calculate',{...calculateArgs,revision:historical.revision,review_ticket:historical.review_ticket,proposal_sha256:historical.proposal_sha256});
const restoreArgs={...editScope(initialEditor),expected_draft_revision:historical.draft_revision,expected_proposal_revision:historical.proposal_revision,fields:historical.proposal};
const restored=payload(call('vera_workspace_cr_recipe_save',restoreArgs));
const recovered=editor(),currentProposal=payload(call('vera_workspace_cr_proposal_read',exact));
const result={history,historical,signedHistoricalCalculation,restored,recovered,currentProposal};
""",
    )
    assert result["history"]["total"] == 2
    assert sum(row["is_current"] for row in result["history"]["rows"]) == 1
    assert result["historical"]["history_selected"] is True
    assert result["historical"]["is_current"] is False
    assert result["signedHistoricalCalculation"]["isError"] is True
    assert result["recovered"]["draft"] == result["historical"]["proposal"]
    assert result["recovered"]["draft"]["mapping_review"]["status"] == "pending"
    assert (
        result["currentProposal"]["proposal"]["entity"] == "Proposta corrente fittizia"
    )
    assert len(list(output.glob("cr-*"))) == 1


def test_cr_historical_restore_checkpoint_refuses_newer_draft_without_overwrite(cr_run):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + HISTORY
        + EDITOR
        + """
payload(call('vera_workspace_cr_recipe_save',{...editScope(initialEditor),fields:{...initialEditor.fields,entity:'Bozza contemporanea'}}));
const fresh=editor();
const refused=call('vera_workspace_cr_recipe_save',{...editScope(fresh),expected_draft_revision:historical.draft_revision,expected_proposal_revision:historical.proposal_revision,fields:historical.proposal});
const result={refused,recovered:editor()};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["recovered"]["draft"]["entity"] == "Bozza contemporanea"


def test_cr_historical_restore_checkpoint_refuses_changed_model_proposal(cr_run):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + HISTORY
        + EDITOR
        + """
model('vera_workspace_cr_stage',{...exact,expected_proposal_revision:initialEditor.proposal_revision,proposal:{...newer,entity:'Ulteriore proposta'},idempotency_key:'third-history-proposal'});
const fresh=editor();
const refused=call('vera_workspace_cr_recipe_save',{...editScope(fresh),expected_draft_revision:historical.draft_revision,expected_proposal_revision:historical.proposal_revision,fields:historical.proposal});
const result={refused,recovered:editor()};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["recovered"]["draft"] is None
    assert result["recovered"]["fields"]["entity"] == "Ulteriore proposta"


def test_cr_history_paginates_all_grant_local_hashes_without_invented_chronology(
    cr_run,
):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + """
for(let i=0;i<33;i++)model('vera_workspace_cr_stage',{...exact,expected_proposal_revision:model('vera_workspace_cr_model_context',exact).proposal_revision,proposal:{...proposal,entity:'Proposta fittizia '+i},idempotency_key:'history-'+i});
const first=payload(call('vera_workspace_cr_proposal_history',exact));
const last=payload(call('vera_workspace_cr_proposal_history',{...exact,offset:30}));
const result={first,last};
""",
    )
    assert result["first"]["total"] == 34
    assert len(result["first"]["rows"]) == 30
    assert len(result["last"]["rows"]) == 4
    assert result["last"]["has_more"] is False
    rows = result["first"]["rows"] + result["last"]["rows"]
    assert [row["proposal_sha256"] for row in rows] == sorted(
        row["proposal_sha256"] for row in rows
    )
    assert sum(row["is_current"] for row in rows) == 1
    assert all(set(row) == {"proposal_sha256", "is_current"} for row in rows)


def test_cr_changed_historical_bytes_refuse_readback_and_current_calculation(cr_run):
    env, output, _ = cr_run
    fixture = rpc_program(
        env,
        proposal_script()
        + "const result={exact,calculateArgs,sha:candidate.proposal_sha256};",
    )
    path = (
        output.parent
        / ".native-workspace"
        / (fixture["exact"]["grant_ref"] + "-proposal-" + fixture["sha"] + ".json")
    )
    changed = json.loads(path.read_bytes())
    changed["entity"] = "Contenuti alterati"
    path.write_text(json.dumps(changed))
    module = workspace_module()
    with pytest.raises(ValueError, match="history bytes changed"):
        module.dispatch("vera_workspace_cr_proposal_read", fixture["exact"])
    args = fixture["calculateArgs"]
    args.pop("review_ticket")
    with pytest.raises(ValueError, match="history bytes changed"):
        module.dispatch("vera_workspace_cr_calculate", args)
    assert len(list(output.glob("cr-*"))) == 1


@pytest.mark.parametrize("sha", ["0" * 64, "../foreign", "x" * 64])
def test_cr_history_refuses_unknown_or_foreign_hash_selection(cr_run, sha):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + f"const result=call('vera_workspace_cr_proposal_read',{{...exact,proposal_sha256:{json.dumps(sha)}}});",
    )
    assert result["isError"] is True


@pytest.mark.parametrize("cr_run", ["extended"], indirect=True)
def test_cr_editor_recovers_exact_observed_value_page_without_grant_or_review(cr_run):
    env, output, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + EDITOR
        + """
const view_selector={field:'original_duration',offset:30};
payload(call('vera_workspace_cr_recipe_save',{...editScope(initialEditor),fields:initialEditor.fields,view_selector}));
const restored=editor();
const page=payload(call('vera_workspace_cr_source',{work_ref:exact.work_ref,source_ref:inspected.source_ref,source_selector:{table_id:restored.draft.table_id,kind:'values',column:restored.draft.columns[restored.view_selector.field],offset:restored.view_selector.offset}}));
const result={restored,page};
""",
    )
    assert result["restored"]["view_selector"] == {
        "field": "original_duration",
        "offset": 30,
    }
    assert len(result["page"]["source"]["page"]["entries"]) == 4
    assert result["page"]["model_grant_issued"] is False
    assert result["restored"]["draft"]["mapping_review"]["status"] == "pending"
    assert len(list(output.glob("cr-*"))) == 1


@pytest.mark.parametrize(
    "selector",
    [
        {"field": "path", "offset": 0},
        {"field": "original_duration", "offset": True},
        {"field": "original_duration", "offset": -1},
        {"field": "original_duration", "offset": 0, "path": "../foreign"},
    ],
)
def test_cr_editor_refuses_foreign_or_invalid_value_page_coordinates(cr_run, selector):
    env, _, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + EDITOR
        + f"const result=call('vera_workspace_cr_recipe_save',{{...editScope(initialEditor),fields:initialEditor.fields,view_selector:{json.dumps(selector)}}});",
    )
    assert result["isError"] is True


def test_cr_commentary_history_keeps_exact_analysis_and_cannot_finalize_historical_ticket(
    cr_run,
):
    env, output, _ = cr_run
    result = rpc_program(
        env,
        proposal_script()
        + """
const calculated=payload(call('vera_workspace_cr_calculate',calculateArgs));
const analysis=payload(call('vera_workspace_cr_view',{work_ref:exact.work_ref,source_ref:calculated.source_ref}));
const commentGrant=payload(call('vera_workspace_cr_grant',{work_ref:exact.work_ref,source_ref:calculated.source_ref,revision:analysis.revision,review_ticket:analysis.review_ticket,question:'Commento fittizio con cronologia.',human_reviewed:true,confirmed:true,idempotency_key:'history-comment-grant'}));
const commentExact={work_ref:exact.work_ref,grant_ref:commentGrant.grant_ref};
const commentContext=model('vera_workspace_cr_model_context',commentExact);
const comment={...commentContext.template,observations:[{text:'Utilizzato del mese fittizio.',evidence_refs:['metric:'+commentContext.context.metrics[0].metric_id]}],hypotheses:[],questions:['Domanda precedente'],limitations:['Fonti fittizie.']};
const original=model('vera_workspace_cr_stage',{...commentExact,expected_proposal_revision:commentContext.proposal_revision,proposal:comment,idempotency_key:'history-comment-one'});
model('vera_workspace_cr_stage',{...commentExact,expected_proposal_revision:model('vera_workspace_cr_model_context',commentExact).proposal_revision,proposal:{...comment,questions:['Domanda corrente']},idempotency_key:'history-comment-two'});
const history=payload(call('vera_workspace_cr_proposal_history',commentExact));
const historical=payload(call('vera_workspace_cr_proposal_read',{...commentExact,proposal_sha256:original.proposal_sha256}));
const refused=call('vera_workspace_cr_finalize',{...commentExact,source_ref:calculated.source_ref,revision:historical.revision,review_ticket:historical.review_ticket,proposal_sha256:historical.proposal_sha256,human_reviewed:true,confirmed:true,idempotency_key:'history-comment-finalize'});
const result={history,historical,refused,comment};
""",
    )
    assert result["history"]["kind"] == "commentary"
    assert result["history"]["total"] == 2
    assert result["historical"]["proposal"] == result["comment"]
    assert result["historical"]["is_current"] is False
    assert result["refused"]["isError"] is True
    assert len(list(output.glob("cr-*"))) == 2
