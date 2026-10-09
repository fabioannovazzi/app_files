"""Human review metadata reaches a fresh real run without inventing business facts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import registry_workspace
from tests.plugins.test_vera_native_business_planning import FIXTURES, PREPARE
from tests.plugins.test_vera_native_workspace import workspace_module


@pytest.fixture
def case_review_run(registry_workspace, tmp_path, request):
    env, studio, _, _, client_id, engagement_id = registry_workspace
    env.update(
        VERA_WORKSPACE_ACTOR_ID="fictional-reviewer",
        VERA_WORKSPACE_TENANT_ID="fictional-studio",
        VERA_WORKSPACE_ROLES="REVIEWER",
    )
    client = studio / "Cliente Beta"
    ledger = _load_customer_ledger()
    case = json.loads((FIXTURES / "case.json").read_bytes())
    inputs = []
    for source in case["sources"]:
        path = FIXTURES / source["path"]
        receipt = ledger.import_document(
            client, client_id, engagement_id, path, "source"
        )["receipt"]
        inputs.append(receipt["input_id"])
        source["path"] = f"imports/{receipt['input_id']}/{path.name}"
    unreviewed = {"status": "unreviewed", "reviewer": "", "reviewed_at": ""}
    case["review"] = unreviewed.copy()
    variant = getattr(request, "param", "selected")
    if variant in {"selected", "all", "blocked"}:
        case["sources"][0]["review_status"] = "unverified"
        case["evidence"][0].update(unreviewed)
        case["narrative"][0]["review"] = unreviewed.copy()
    if variant == "all":
        for source in case["sources"]:
            source["review_status"] = "unverified"
        for name in ("evidence", "assumptions", "decisions"):
            for record in case[name]:
                record.update(unreviewed)
        for record in case["narrative"]:
            record["review"] = unreviewed.copy()
    if variant == "blocked":
        case["financial"]["scenarios"][0]["schedule"][0]["operating_expenses"] = "200"
    authored = tmp_path / "case-for-human-review.json"
    authored.write_text(json.dumps(case))
    inputs.append(
        ledger.import_document(client, client_id, engagement_id, authored, "source")[
            "receipt"
        ]["input_id"]
    )
    prepared = ledger.prepare_run(
        client, client_id, engagement_id, "business-planning", "0.1.0", input_ids=inputs
    )
    started = ledger.start_run(client, engagement_id, prepared["run"]["run_id"])
    reference = "studio-" + "_".join(
        x.split("_", 1)[1]
        for x in (client_id, engagement_id, prepared["run"]["run_id"])
    )
    return (
        env,
        Path(started["context"]["output_dir"]),
        reference,
        case,
        client,
        engagement_id,
    )


REVIEW = """
function reviewRecord(collection,index,action='accept') {
 const now=payload(call('vera_workspace_business_plan_setup',{work_ref:exact.work_ref}));
 const target={work_ref:exact.work_ref,revision:now.revision,generation:now.generation,collection,index};
 const read=payload(call('vera_workspace_business_plan_review_read',target));
 const authority={...target,item_id:read.selection.id,review_ticket:read.review_ticket,expected_draft_revision:read.draft.draft_revision};
 if(read.draft.stale){payload(call('vera_workspace_business_plan_review_draft_clear',authority));authority.expected_draft_revision='';}
 const fields={action,note:'Actual declaration in a fictional test only; review this exact item.',reviewer:'Fictional human reviewer',reviewed_at:'2026-10-07T16:30:00+02:00'};
 const draft=payload(call('vera_workspace_business_plan_review_draft_save',{...authority,fields}));
 return payload(call('vera_workspace_business_plan_review_commit',{...authority,expected_draft_revision:draft.draft_revision,human_reviewed:true,idempotency_key:collection+'-'+index+'-'+action}));
}
function caseSelection() {
 const now=payload(call('vera_workspace_business_plan_setup',{work_ref:exact.work_ref}));
 return {work_ref:exact.work_ref,revision:now.revision,generation:now.generation,collection:'case_review',index:0};
}
"""
FOUR = "reviewRecord('case_review',0);reviewRecord('sources',0);reviewRecord('evidence',0);reviewRecord('narrative',0);"
PROPOSE = """
const choice=caseSelection();
const preview=payload(call('vera_workspace_business_plan_case_review_read',choice));
const prepareArgs={...choice,item_id:preview.selection.id,review_ticket:preview.review_ticket,confirmed:true,idempotency_key:'reviewed-copy'};
const retainedCase=payload(call('vera_workspace_business_plan_case_review_prepare',prepareArgs));
const selectedRetained={...caseSelection(),case_ref:retainedCase.case_ref};
const retainedPreview=payload(call('vera_workspace_business_plan_case_review_read',selectedRetained));
const launchArgs={...selectedRetained,item_id:retainedPreview.selection.id,review_ticket:retainedPreview.review_ticket,confirmed:true,idempotency_key:'reviewed-run'};
"""


def program(reference: str, body: str) -> str:
    return PREPARE.replace("'planning-cycle'", json.dumps(reference)) + REVIEW + body


def test_reviewed_case_executes_same_business_inputs_in_fresh_ready_run(
    case_review_run,
):
    env, output, reference, case, client, engagement = case_review_run
    result = rpc_program(
        env,
        program(
            reference,
            FOUR
            + PROPOSE
            + """
const launched=payload(call('vera_workspace_business_plan_case_review_launch',launchArgs));
const retry=payload(call('vera_workspace_business_plan_case_review_launch',launchArgs));
const now=payload(call('vera_workspace_business_plan_setup',{work_ref:launched.work_ref}));
const report=payload(call('vera_workspace_business_plan_report',{work_ref:launched.work_ref,revision:now.revision,generation:now.generation}));
const result={prepared,retainedCase,preview,retainedPreview,launched,retry,report};
""",
        ),
    )
    assert result["prepared"]["status"] == "partial"
    assert result["launched"]["status"] == "ready_for_professional_review"
    assert result["retry"] == result["launched"]
    assert result["report"]["report"] == result["retainedPreview"]["report"]
    projected = result["retainedPreview"]["plan"]["case"]
    assert projected["review"]["reviewer"] == "Fictional human reviewer"
    assert projected["review"]["reviewed_at"] == "2026-10-07T16:30:00+02:00"
    assert projected["sources"][0]["review_status"] == "reviewed"
    assert projected["evidence"][0]["status"] == "reviewed"
    assert projected["narrative"][0]["review"]["status"] == "reviewed"
    assert projected["financial"] == case["financial"]
    assert projected["assessment"] == case["assessment"]
    assert projected["assumptions"] == case["assumptions"]
    assert projected["decisions"] == case["decisions"]
    assert projected["narrative"][0]["text"] == case["narrative"][0]["text"]
    assert projected["sources"][0]["path"] == case["sources"][0]["path"]
    original = json.loads(
        (output / result["prepared"]["generation"] / "business_plan.json").read_bytes()
    )
    assert original["case"] == case
    assert len(result["preview"]["changes"]) == 4
    assert result["launched"]["professional_plan_approval"] is False
    assert result["launched"]["run_completed"] is False
    loaded = _load_customer_ledger().load_run(
        client, engagement, result["launched"]["run_id"]
    )
    assert loaded["run"]["status"] == "running"
    control = next(
        r
        for r in loaded["input_manifest"]["inputs"]
        if r["role"] == "support"
        and Path(r["execution_relative_path"]).name == "review_lineage.json"
    )
    lineage = json.loads(
        (Path(loaded["run_root"]) / control["execution_relative_path"]).read_bytes()
    )
    assert lineage["changes"] == result["preview"]["changes"]
    assert lineage["original_case_sha256"] == original["case_sha256"]


@pytest.mark.parametrize("case_review_run", ["all", "blocked"], indirect=True)
def test_case_attestation_cannot_review_other_items_or_clear_conflicting_numbers(
    case_review_run,
):
    env, _, reference, case, _, _ = case_review_run
    result = rpc_program(
        env,
        program(
            reference,
            "reviewRecord('case_review',0);"
            + PROPOSE
            + "const result={preview,retainedCase};",
        ),
    )
    assert result["preview"]["plan"]["status"] in {"partial", "blocked"}
    assert result["preview"]["plan"]["case"]["evidence"] == case["evidence"]
    assert result["preview"]["plan"]["case"]["sources"] == case["sources"]
    assert result["preview"]["plan"]["case"]["financial"] == case["financial"]
    assert result["preview"]["professional_plan_approval"] is False


@pytest.mark.parametrize("action", ["reject", "request_changes"])
def test_negative_review_withdraws_only_exact_source_attestation(
    case_review_run, action
):
    env, _, reference, case, _, _ = case_review_run
    result = rpc_program(
        env,
        program(
            reference,
            "reviewRecord('sources',1,"
            + json.dumps(action)
            + ");const result=payload(call('vera_workspace_business_plan_case_review_read',caseSelection()));",
        ),
    )
    projected = result["plan"]["case"]
    assert projected["sources"][1]["review_status"] == "unverified"
    assert projected["sources"][0] == case["sources"][0]
    assert projected["review"] == case["review"]
    assert result["changes"][0]["fields"]["action"] == action
    assert result["plan"]["status"] == "partial"


@pytest.mark.parametrize(
    "change",
    [
        "review_ticket:'forged.signature'",
        "item_id:'case_header:0'",
        "revision:'stale'",
        "collection:'case_header'",
        "confirmed:false",
    ],
)
def test_reviewed_case_requires_exact_signed_full_case_scope(case_review_run, change):
    env, output, reference, _, _, _ = case_review_run
    result = rpc_program(
        env,
        program(
            reference,
            "reviewRecord('case_review',0);const choice=caseSelection();const preview=payload(call('vera_workspace_business_plan_case_review_read',choice));"
            + f"const result=call('vera_workspace_business_plan_case_review_prepare',{{...choice,item_id:preview.selection.id,review_ticket:preview.review_ticket,confirmed:true,idempotency_key:'forged',{change}}});",
        ),
    )
    assert result["isError"] is True
    assert list(output.glob("planning-case-review-*")) == []


def test_reviewed_case_refuses_execution_after_later_human_decision(case_review_run):
    env, _, reference, _, _, _ = case_review_run
    result = rpc_program(
        env,
        program(
            reference,
            FOUR
            + PROPOSE
            + """
reviewRecord('evidence',0,'reject');
const now={...caseSelection(),case_ref:retainedCase.case_ref};
const read=payload(call('vera_workspace_business_plan_case_review_read',now));
const write=call('vera_workspace_business_plan_case_review_launch',{...now,item_id:read.selection.id,review_ticket:read.review_ticket,confirmed:true,idempotency_key:'later-launch'});
const result={read,write};
""",
        ),
    )
    assert result["read"]["can_launch"] is False
    assert result["write"]["isError"] is True


@pytest.mark.parametrize("damage", ["pending", "orphan", "changed"])
def test_reviewed_case_uncertainty_blocks_new_decisions_and_all_output_closure(
    case_review_run, damage
):
    env, output, reference, _, _, _ = case_review_run
    first = rpc_program(
        env,
        program(
            reference,
            "reviewRecord('case_review',0);" + PROPOSE + "const result={retainedCase};",
        ),
    )
    private = workspace_module().ui_state_directory(output, create=False)
    if damage == "pending":
        (private / "planning-case-launch-pending.json").write_text("{}")
    elif damage == "orphan":
        (output / "planning-case-review-orphan").mkdir()
    else:
        (output / first["retainedCase"]["case_ref"] / "case.json").write_text("{}")
    result = rpc_program(
        env,
        "const result=call('vera_workspace_business_plan_setup',{work_ref:"
        + json.dumps(reference)
        + "});",
    )
    if damage == "changed":
        assert result["isError"] is True
    else:
        exact = result["_meta"]["workspace"]
        closure = rpc_program(
            env,
            "const result=call('vera_workspace_business_plan_outputs',"
            + json.dumps(
                {
                    "work_ref": reference,
                    "revision": exact["revision"],
                    "generation": exact["generation"],
                }
            )
            + ");",
        )
        assert closure["isError"] is True


def test_without_human_decisions_readback_creates_no_official_case(case_review_run):
    env, output, reference, _, _, _ = case_review_run
    result = rpc_program(
        env,
        program(
            reference,
            "const result=payload(call('vera_workspace_business_plan_case_review_read',caseSelection()));",
        ),
    )
    assert result["can_prepare"] is False
    assert result["changes"] == []
    assert list(output.glob("planning-case-review-*")) == []


def test_source_review_displays_complete_exact_small_original_privately(
    case_review_run,
):
    env, _, reference, _, _, _ = case_review_run
    result = rpc_program(
        env,
        program(
            reference,
            "const choice={...caseSelection(),collection:'sources'};const result=call('vera_workspace_business_plan_review_read',choice);",
        ),
    )
    source = result["_meta"]["workspace"]["source_file"]
    assert source["text"] == Path(source["path"]).read_text()
    assert source["sha256"] == result["_meta"]["workspace"]["record"]["sha256"]
    assert source["text"] not in json.dumps(result["content"])


def test_missing_completed_launch_receipt_requires_recovery_before_repetition(
    case_review_run,
):
    env, output, reference, _, _, _ = case_review_run
    rpc_program(
        env,
        program(
            reference,
            FOUR
            + PROPOSE
            + "const result=payload(call('vera_workspace_business_plan_case_review_launch',launchArgs));",
        ),
    )
    private = workspace_module().ui_state_directory(output, create=False)
    next(private.glob("planning-case-launch-*.json")).unlink()
    result = rpc_program(
        env,
        "const exact={work_ref:"
        + json.dumps(reference)
        + "};"
        + REVIEW
        + "const result=payload(call('vera_workspace_business_plan_case_review_read',caseSelection()));",
    )
    assert result["recovery_required"] is True
    assert result["can_prepare"] is False


@pytest.mark.parametrize("case_review_run", ["all"], indirect=True)
def test_each_fresh_attestation_can_reach_ready_without_model_generated_review(
    case_review_run,
):
    env, output, reference, case, _, _ = case_review_run
    initial = rpc_program(env, program(reference, "const result=prepared;"))
    selections = [("case_review", 0)] + [
        (collection, index)
        for collection in (
            "sources",
            "evidence",
            "assumptions",
            "decisions",
            "narrative",
        )
        for index in range(len(case[collection]))
    ]
    for start in range(0, len(selections), 7):
        body = "const exact={work_ref:" + json.dumps(reference) + "};" + REVIEW
        body += "".join(
            "reviewRecord(" + json.dumps(collection) + "," + str(index) + ");"
            for collection, index in selections[start : start + 7]
        )
        rpc_program(env, body + "const result={saved:true};")
    result = rpc_program(
        env,
        "const exact={work_ref:"
        + json.dumps(reference)
        + "};"
        + REVIEW
        + PROPOSE
        + "const result={preview,retainedCase};",
    )
    assert result["preview"]["plan"]["status"] == "ready_for_professional_review"
    assert len(result["preview"]["changes"]) == len(selections)
    assert result["preview"]["professional_plan_approval"] is False
    assert result["preview"]["plan"]["case"]["financial"] == case["financial"]
    assert (
        json.loads(
            (output / initial["generation"] / "business_plan.json").read_bytes()
        )["case"]
        == case
    )
