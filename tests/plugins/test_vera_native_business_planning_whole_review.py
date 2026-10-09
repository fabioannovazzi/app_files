"""Whole-plan human decisions bind the unchanged public generation and all files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_business_planning import PREPARE, planning_run
from tests.plugins.test_vera_native_business_planning_review import COMMIT, SAVE
from tests.plugins.test_vera_native_workspace import workspace_module

WHOLE_SAVE = SAVE.replace("collection:'evidence'", "collection:'whole_plan'")
WHOLE_COMMIT = COMMIT.replace("collection:'evidence'", "collection:'whole_plan'")


@pytest.mark.parametrize("action", ["accept", "reject", "request_changes"])
def test_whole_plan_decision_binds_complete_report_and_preserves_running_run(
    planning_run, action
):
    env, output, binding = planning_run
    result = rpc_program(
        env,
        PREPARE
        + WHOLE_COMMIT.replace(
            "action:'request_changes'", "action:" + json.dumps(action)
        )
        + """
const read=call('vera_workspace_business_plan_review_read',{...target,revision:updated.revision});
const history=call('vera_workspace_business_plan_review_history',{work_ref:exact.work_ref,revision:updated.revision});
const result={committed,retry:payload(call('vera_workspace_business_plan_review_commit',commit)),
 generation:prepared.generation,read,history,
 report:payload(call('vera_workspace_business_plan_report',current)),
 outputs:payload(call('vera_workspace_business_plan_outputs',current))};
""",
    )
    generation = output / result["generation"]
    decision = json.loads(
        (
            output / result["committed"]["review_ref"] / "professional_review.json"
        ).read_bytes()
    )
    original = json.loads((generation / "business_plan.json").read_bytes())
    read = result["read"]["_meta"]["workspace"]
    history = result["history"]["_meta"]["workspace"]
    assert decision["record"] == original
    assert len(decision["target"]["generation_artifacts"]) == 11
    assert "business_plan_review.html" in decision["target"]["generation_artifacts"]
    assert decision["fields"]["action"] == action
    assert read["record"] == original
    assert read["report"] == (generation / "business_plan_review.html").read_text()
    assert result["report"]["report"] == read["report"]
    assert read["can_accept"] is True
    assert (
        history["whole_plan_decision"]["review_ref"]
        == result["committed"]["review_ref"]
    )
    assert history["professional_plan_approval"] is (action == "accept")
    assert decision["professional_plan_approval"] is (action == "accept")
    assert result["committed"] == result["retry"]
    assert len(result["outputs"]["outputs"]) == 13
    assert "Synthetic private review" not in json.dumps(result["read"]["content"])
    assert decision["run_completed"] is False
    assert decision["report_changed"] is False
    assert (
        _load_customer_ledger().load_run(
            Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
        )["run"]["status"]
        == "running"
    )


@pytest.mark.parametrize("planning_run", ["partial", "blocked"], indirect=True)
def test_whole_plan_acceptance_refuses_unready_report_before_any_intent(planning_run):
    env, output, _ = planning_run
    result = rpc_program(
        env,
        PREPARE
        + WHOLE_SAVE.replace("action:'request_changes'", "action:'accept'")
        + "const result={review,write:call('vera_workspace_business_plan_review_commit',commit)};",
    )
    assert result["review"]["can_accept"] is False
    assert result["write"]["isError"] is True
    assert list(output.glob("planning-review-*")) == []
    private = workspace_module().ui_state_directory(output, create=False)
    assert list(private.glob("planning-review-request-*.json")) == []


@pytest.mark.parametrize("planning_run", ["partial", "blocked"], indirect=True)
@pytest.mark.parametrize("action", ["reject", "request_changes"])
def test_whole_plan_unready_report_keeps_explicit_negative_decision(
    planning_run, action
):
    env, output, _ = planning_run
    result = rpc_program(
        env,
        PREPARE
        + WHOLE_COMMIT.replace(
            "action:'request_changes'", "action:" + json.dumps(action)
        )
        + "const result={committed,report:payload(call('vera_workspace_business_plan_report',current))};",
    )
    decision = json.loads(
        (
            output / result["committed"]["review_ref"] / "professional_review.json"
        ).read_bytes()
    )
    assert decision["fields"]["action"] == action
    assert decision["professional_plan_approval"] is False
    assert decision["record"]["status"] == result["report"]["status"]


def test_last_whole_plan_decision_withdraws_acceptance_without_rewriting_history(
    planning_run,
):
    env, output, _ = planning_run
    result = rpc_program(
        env,
        PREPARE
        + WHOLE_COMMIT.replace("action:'request_changes'", "action:'accept'")
        + """
const nextTarget={...target,revision:updated.revision};
const nextRead=payload(call('vera_workspace_business_plan_review_read',nextTarget));
const nextAuthority={...nextTarget,item_id:nextRead.selection.id,review_ticket:nextRead.review_ticket,expected_draft_revision:nextRead.draft.draft_revision};
payload(call('vera_workspace_business_plan_review_draft_clear',nextAuthority));
const secondDraft=payload(call('vera_workspace_business_plan_review_draft_save',{...nextAuthority,expected_draft_revision:'',fields:{...fields,action:'reject',note:'Synthetic review withdrawn after professional readback.'}}));
const second=payload(call('vera_workspace_business_plan_review_commit',{...nextAuthority,expected_draft_revision:secondDraft.draft_revision,human_reviewed:true,idempotency_key:'withdraw-whole-plan'}));
const latest=payload(call('vera_workspace_business_plan_setup',{work_ref:exact.work_ref}));
const history=payload(call('vera_workspace_business_plan_review_history',{work_ref:exact.work_ref,revision:latest.revision}));
const result={first:committed,second,history};
""",
    )
    first = json.loads(
        (
            output / result["first"]["review_ref"] / "professional_review.json"
        ).read_bytes()
    )
    assert first["professional_plan_approval"] is True
    assert result["history"]["rows"][0]["professional_plan_approval"] is True
    assert (
        result["history"]["rows"][1]["previous_review_ref"]
        == result["first"]["review_ref"]
    )
    assert (
        result["history"]["whole_plan_decision"]["review_ref"]
        == result["second"]["review_ref"]
    )
    assert result["history"]["professional_plan_approval"] is False


def test_whole_plan_uncertain_review_never_reports_current_acceptance(planning_run):
    env, output, _ = planning_run
    rpc_program(
        env,
        PREPARE
        + WHOLE_COMMIT.replace("action:'request_changes'", "action:'accept'")
        + "const result=committed;",
    )
    private = workspace_module().ui_state_directory(output, create=False)
    (private / "planning-review-request-pending.json").write_text("{}")
    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_business_plan_setup',{work_ref:'planning-cycle'}));
const exact={work_ref:setup.work_ref,revision:setup.revision,generation:setup.generation};
const result=payload(call('vera_workspace_business_plan_review_read',{...exact,collection:'whole_plan',index:0}));
""",
    )
    assert result["professional_plan_approval"] is False
    assert result["status"] == "recovery_required"
    assert result["can_review"] is False
    assert result["whole_plan_decision"]["fields"]["action"] == "accept"


def test_whole_plan_read_refuses_changed_report_file(planning_run):
    env, output, _ = planning_run
    exact = rpc_program(env, PREPARE + "const result=exact;")
    (output / exact["generation"] / "business_plan_review.html").write_text("Changed")
    result = rpc_program(
        env,
        "const result=call('vera_workspace_business_plan_review_read',"
        + json.dumps({**exact, "collection": "whole_plan", "index": 0})
        + ");",
    )
    assert result["isError"] is True
    assert list(output.glob("planning-review-*")) == []
