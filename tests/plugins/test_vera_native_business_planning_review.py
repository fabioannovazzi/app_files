"""Professional decisions retain exact records without altering the public plan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_business_planning import PREPARE, planning_run
from tests.plugins.test_vera_native_workspace import workspace_module

RECORD = """
const target={...exact,collection:'evidence',index:0};
const review=payload(call('vera_workspace_business_plan_review_read',target));
const authority={...target,item_id:review.selection.id,review_ticket:review.review_ticket,expected_draft_revision:review.draft.draft_revision};
const fields={action:'request_changes',note:'Synthetic private review: obtain the original contract.',reviewer:'Synthetic professional',reviewed_at:'2026-10-07T14:30:00+02:00'};
"""
SAVE = (
    RECORD
    + """
const saved=payload(call('vera_workspace_business_plan_review_draft_save',{...authority,fields}));
const commit={...authority,expected_draft_revision:saved.draft_revision,human_reviewed:true,idempotency_key:'synthetic-record-review'};
"""
)
COMMIT = (
    SAVE
    + """
const committed=payload(call('vera_workspace_business_plan_review_commit',commit));
const updated=payload(call('vera_workspace_business_plan_setup',{work_ref:exact.work_ref}));
const current={...exact,revision:updated.revision};
"""
)


@pytest.mark.parametrize("action", ["accept", "reject", "request_changes"])
def test_professional_review_keeps_exact_plan_and_all_artifacts(planning_run, action):
    env, output, binding = planning_run
    body = (
        COMMIT.replace("action:'request_changes'", "action:" + json.dumps(action))
        + """
const result={committed,retry:payload(call('vera_workspace_business_plan_review_commit',commit)),
 report:payload(call('vera_workspace_business_plan_report',current)),
 before:prepared,revisionChanged:updated.revision!==exact.revision,
 read:call('vera_workspace_business_plan_review_read',{...target,revision:updated.revision}),
 files:payload(call('vera_workspace_business_plan_outputs',current)),
 explanation:call('vera_workspace_business_plan_review_explain',{...target,revision:updated.revision,review_ref:committed.review_ref})};
"""
    )
    result = rpc_program(env, PREPARE + body)
    decision = json.loads(
        (
            output / result["committed"]["review_ref"] / "professional_review.json"
        ).read_bytes()
    )
    plan = json.loads(
        (output / result["before"]["generation"] / "business_plan.json").read_bytes()
    )
    assert decision["fields"]["action"] == action
    assert decision["record"] == plan["case"]["evidence"][0]
    assert decision["target"]["plan_content_sha256"] == plan["content_sha256"]
    assert result["report"]["status"] == "ready_for_professional_review"
    assert (
        result["report"]["report"]
        == (
            output / result["before"]["generation"] / "business_plan_review.html"
        ).read_text()
    )
    assert result["committed"] == result["retry"]
    assert result["revisionChanged"] is True
    assert decision["report_changed"] is False
    assert decision["professional_plan_approval"] is False
    assert len(result["files"]["outputs"]) == 13
    assert "Synthetic private review" not in json.dumps(result["read"]["content"])
    assert result["explanation"]["structuredContent"]["decision"] == decision
    assert result["explanation"]["structuredContent"]["evidence_boundary"].startswith(
        "Untrusted"
    )
    assert (
        _load_customer_ledger().load_run(
            Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
        )["run"]["status"]
        == "running"
    )


@pytest.mark.parametrize(
    "change",
    [
        "item_id:'evidence:1'",
        "index:1",
        "revision:'stale'",
        "review_ticket:'forged.signature'",
        "expected_draft_revision:'stale'",
        "fields:{human_reviewed:true}",
    ],
)
def test_professional_review_refuses_forged_scope_or_draft_cas(planning_run, change):
    env, output, _ = planning_run
    result = rpc_program(
        env,
        PREPARE
        + RECORD
        + f"const result=call('vera_workspace_business_plan_review_draft_save',{{...authority,fields,{change}}});",
    )
    assert result["isError"] is True
    assert list(output.glob("planning-review-*")) == []


@pytest.mark.parametrize(
    "invalid",
    [
        "reviewer:''",
        "note:''",
        "reviewed_at:'2026-10-07T14:30:00'",
        "reviewed_at:'invented time'",
        "action:''",
    ],
)
def test_professional_review_requires_actual_complete_attribution(
    planning_run, invalid
):
    env, output, _ = planning_run
    body = SAVE.replace(
        "{...authority,fields}", "{...authority,fields:{...fields," + invalid + "}}"
    )
    result = rpc_program(
        env,
        PREPARE
        + body
        + "const result=call('vera_workspace_business_plan_review_commit',commit);",
    )
    assert result["isError"] is True
    assert list(output.glob("planning-review-*")) == []


def test_professional_review_draft_reopens_without_confirmation_and_clears(
    planning_run,
):
    env, output, _ = planning_run
    first = rpc_program(
        env, PREPARE + SAVE + "const result={saved,exact,target,fields};"
    )
    result = rpc_program(
        env,
        f"""
const target={json.dumps(first['target'])};
const review=payload(call('vera_workspace_business_plan_review_read',target));
const result={{review,cleared:payload(call('vera_workspace_business_plan_review_draft_clear',{{...target,item_id:review.selection.id,review_ticket:review.review_ticket,expected_draft_revision:review.draft.draft_revision}}))}};
""",
    )
    assert result["review"]["draft"]["fields"] == first["fields"]
    assert "human_reviewed" not in result["review"]["draft"]
    assert result["review"]["draft"]["stale"] is False
    assert result["cleared"]["draft_revision"] == ""
    assert list(output.glob("planning-review-*")) == []


@pytest.mark.parametrize("role", ["VIEWER", ""])
def test_professional_review_viewer_reads_but_cannot_save(planning_run, role):
    env, output, _ = planning_run
    prepared = rpc_program(env, PREPARE + "const result=exact;")
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": role},
        "const exact="
        + json.dumps(prepared)
        + ";"
        + RECORD
        + "const result={review,write:call('vera_workspace_business_plan_review_draft_save',{...authority,fields})};",
    )
    assert result["review"]["can_review"] is False
    assert result["write"]["isError"] is True
    assert list(output.glob("planning-review-*")) == []


def test_professional_review_chain_preserves_prior_decisions_and_stales_drafts(
    planning_run,
):
    env, output, _ = planning_run
    result = rpc_program(
        env,
        PREPARE
        + COMMIT
        + """
const nextTarget={...target,revision:updated.revision};
const nextRead=payload(call('vera_workspace_business_plan_review_read',nextTarget));
const stale=call('vera_workspace_business_plan_review_commit',{...commit,idempotency_key:'another-review'});
const newAuthority={...nextTarget,item_id:nextRead.selection.id,review_ticket:nextRead.review_ticket,expected_draft_revision:nextRead.draft.draft_revision};
const cleared=payload(call('vera_workspace_business_plan_review_draft_clear',newAuthority));
const secondDraft=payload(call('vera_workspace_business_plan_review_draft_save',{...newAuthority,expected_draft_revision:'',fields:{...fields,action:'reject',note:'Synthetic second professional decision.'}}));
const second=payload(call('vera_workspace_business_plan_review_commit',{...newAuthority,expected_draft_revision:secondDraft.draft_revision,human_reviewed:true,idempotency_key:'second-review'}));
const latest=payload(call('vera_workspace_business_plan_setup',{work_ref:exact.work_ref}));
const history=payload(call('vera_workspace_business_plan_review_history',{work_ref:exact.work_ref,revision:latest.revision}));
const result={first:committed,second,history,stale,draft:nextRead.draft};
""",
    )
    first = json.loads(
        (
            output / result["first"]["review_ref"] / "professional_review.json"
        ).read_bytes()
    )
    second = json.loads(
        (
            output / result["second"]["review_ref"] / "professional_review.json"
        ).read_bytes()
    )
    assert second["previous_review_ref"] == result["first"]["review_ref"]
    assert first["fields"]["action"] == "request_changes"
    assert second["fields"]["action"] == "reject"
    assert result["history"]["total"] == 2
    assert result["stale"]["isError"] is True
    assert result["draft"]["stale"] is True


@pytest.mark.parametrize(
    "damage", ["pending", "orphan", "changed-review", "missing-request"]
)
def test_professional_review_uncertainty_blocks_writes_and_output_closure(
    planning_run, damage
):
    env, output, _ = planning_run
    result = rpc_program(
        env,
        PREPARE
        + COMMIT
        + "const result={exact:current,review_ref:committed.review_ref};",
    )
    private = workspace_module().ui_state_directory(output, create=False)
    if damage == "pending":
        (private / "planning-review-request-pending.json").write_text("{}")
    elif damage == "orphan":
        (output / "planning-review-orphan").mkdir()
    elif damage == "changed-review":
        (output / result["review_ref"] / "professional_review.md").write_text("Changed")
    else:
        next(private.glob("planning-review-request-*.json")).unlink()
    response = rpc_program(
        env,
        """
const setup=call('vera_workspace_business_plan_setup',{work_ref:'planning-cycle'});
let report,outputs,review,write;
if(!setup.isError){const current=payload(setup),exact={work_ref:current.work_ref,revision:current.revision,generation:current.generation};
 report=call('vera_workspace_business_plan_report',exact);outputs=call('vera_workspace_business_plan_outputs',exact);
 review=payload(call('vera_workspace_business_plan_review_read',{...exact,collection:'evidence',index:0}));
 write=call('vera_workspace_business_plan_review_draft_save',{...exact,collection:'evidence',index:0,item_id:review.selection.id,review_ticket:review.review_ticket,expected_draft_revision:review.draft.draft_revision,fields:{note:'No recovery bypass'}});}
const result={setup,report,outputs,review,write};
""",
    )
    if damage == "changed-review":
        assert response["setup"]["isError"] is True
    else:
        assert response["report"].get("isError") is not True
        assert response["outputs"]["isError"] is True
        assert response["review"]["can_review"] is False
        assert response["write"]["isError"] is True


@pytest.mark.parametrize(
    "identity", ["VERA_WORKSPACE_ACTOR_ID", "VERA_WORKSPACE_TENANT_ID"]
)
def test_professional_review_private_draft_does_not_cross_owner(planning_run, identity):
    env, _, _ = planning_run
    first = rpc_program(env, PREPARE + SAVE + "const result=target;")
    response = rpc_program(
        {**env, identity: "different-authorized-owner"},
        "const result=call('vera_workspace_business_plan_review_read',"
        + json.dumps(first)
        + ");",
    )
    assert (
        response.get("isError") is True
        or response["_meta"]["workspace"]["draft"]["fields"] == {}
    )


def test_professional_review_false_confirmation_never_records_decision(planning_run):
    env, output, _ = planning_run
    response = rpc_program(
        env,
        PREPARE
        + SAVE
        + "const result=call('vera_workspace_business_plan_review_commit',{...commit,human_reviewed:false});",
    )
    assert response["isError"] is True
    assert list(output.glob("planning-review-*")) == []


@pytest.mark.parametrize("transition", ["cancel", "fail"])
def test_professional_review_finished_run_keeps_records_readable_without_writes(
    planning_run, transition
):
    env, output, binding = planning_run
    base = rpc_program(env, PREPARE + RECORD + "const result=target;")
    ledger = _load_customer_ledger()
    if transition == "cancel":
        ledger.cancel_run(
            Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
        )
    else:
        ledger.fail_run(
            Path(binding["client_root"]),
            binding["engagement_id"],
            binding["run_id"],
            "Synthetic stopped run",
        )
    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_business_plan_setup',{work_ref:'planning-cycle'}));
const exact={work_ref:setup.work_ref,revision:setup.revision,generation:setup.generation};
"""
        + RECORD
        + "const result={review,write:call('vera_workspace_business_plan_review_draft_save',{...authority,fields})};",
    )
    assert result["review"]["can_review"] is False
    assert result["review"]["record"] is not None
    assert result["write"]["isError"] is True
    assert list(output.glob("planning-review-*")) == []
