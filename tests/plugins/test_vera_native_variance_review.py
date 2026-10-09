"""Actual public accounting decisions, immutable predecessors and fresh runs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_closure import declare_all, setup
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_variance import variance_run  # noqa: F401
from tests.plugins.test_vera_native_variance_authoring import author_run  # noqa: F401
from tests.plugins.test_vera_native_workspace import workspace_module

__all__ = []


@pytest.fixture
def review_run(author_run):
    env, output, binding, choices, _ = author_run
    loaded = _load_customer_ledger().load_run(
        Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
    )
    recipe = next(
        r
        for r in loaded["input_manifest"]["inputs"]
        if r["execution_relative_path"].endswith(".json")
    )
    fields = {
        "source_input_id": choices["source_input_id"],
        "recipe_input_id": recipe["binding_id"],
        "currency": "EUR",
        "language": "it",
    }
    return env, output, binding, fields


def calculate(work_expression: str, fields_expression: str, identity: str) -> str:
    return f"""
const {identity}Work={work_expression};const {identity}Fields={fields_expression};
const {identity}Setup=payload(call('vera_workspace_variance_setup',{identity}Work));
payload(call('vera_workspace_variance_draft_save',{{...{identity}Work,revision:{identity}Setup.revision,review_ticket:{identity}Setup.review_ticket,expected_draft_revision:{identity}Setup.draft_revision,fields:{identity}Fields}}));
const {identity}Fresh=payload(call('vera_workspace_variance_setup',{identity}Work));
const {identity}=payload(call('vera_workspace_variance_prepare',{{...{identity}Work,revision:{identity}Fresh.revision,review_ticket:{identity}Fresh.review_ticket,expected_draft_revision:{identity}Fresh.draft_revision,fields:{identity}Fields,confirmed:true,idempotency_key:'fictional-{identity}'}}));
"""


def initial(fixture) -> str:
    return calculate(
        json.dumps({"work_ref": fixture[2]["work_ref"]}),
        json.dumps(fixture[3]),
        "original",
    )


def decision(
    work: str,
    generation: str,
    section: str,
    identity: str,
    *,
    alternative: int = 0,
    action: str = "accepted",
) -> str:
    return f"""
const {identity}Selection={{...{work},source_ref:{generation}.source_ref,section:{json.dumps(section)},alternative:{alternative}}};
const {identity}Page=payload(call('vera_workspace_variance_review_read',{identity}Selection));
const {identity}Fields={{decision:{json.dumps(action)},reviewer:'Fictional professional',reviewed_at:'2026-10-08T10:00:00+02:00',basis:'Literal fictional review of exact accounting controls or residual sequence; no economic-cause assertion.'}};
const {identity}Authority=p=>({{...{identity}Selection,revision:p.revision,review_ticket:p.review_ticket,item_id:p.selection.id,expected_draft_revision:p.draft_revision}});
payload(call('vera_workspace_variance_review_draft_save',{{...{identity}Authority({identity}Page),fields:{identity}Fields}}));
const {identity}Current=payload(call('vera_workspace_variance_review_read',{identity}Selection));
const {identity}Args={{...{identity}Authority({identity}Current),confirmed:true,idempotency_key:'fictional-{identity}'}};
const {identity}=payload(call('vera_workspace_variance_review_commit',{identity}Args));
"""


def successor_calculate(result: str, identity: str) -> str:
    return calculate(
        "{work_ref:" + result + ".work_ref}",
        "{source_input_id:"
        + result
        + ".source_input_id,recipe_input_id:"
        + result
        + '.recipe_input_id,currency:"EUR",language:"it"}',
        identity,
    )


def test_native_variance_professional_then_exact_alternative_regenerates_public_approved_report(
    review_run,
):
    body = (
        initial(review_run)
        + decision("originalWork", "original", "professional_review", "accounting")
        + successor_calculate("accounting", "afterAccounting")
        + decision(
            "afterAccountingWork",
            "afterAccounting",
            "root_cause_review",
            "root",
            alternative=2,
        )
        + successor_calculate("root", "final")
        + """
const repeated=payload(call('vera_workspace_variance_review_commit',rootArgs));
const finalState=payload(call('vera_workspace_variance_setup',finalWork));
const result={original,accounting,afterAccounting,root,final,repeated,finalSetup:finalState};
"""
    )
    result = rpc_program(review_run[0], body)
    assert result["root"] == result["repeated"]
    assert result["accounting"]["comparison_calculated"] is False
    assert result["root"]["comparison_calculated"] is False
    assert result["root"]["calculation_choices"] == {
        **review_run[3],
        "recipe_input_id": result["root"]["recipe_input_id"],
    }
    assert (
        result["afterAccounting"]["accounting_readiness"]["client_report_status"]
        == "draft_pending_professional_review"
    )
    assert (
        result["final"]["accounting_readiness"]["client_report_status"]
        == "approved_for_client_use"
    )
    assert (
        result["finalSetup"]["accounting_readiness"]["root_cause_review"][
            "selected_alternative"
        ]
        == 2
    )
    ledger = _load_customer_ledger()
    runs = ledger.list_runs(
        Path(review_run[2]["client_root"]), review_run[2]["engagement_id"]
    )
    assert len(runs) == 3
    loaded = ledger.load_run(
        Path(review_run[2]["client_root"]),
        review_run[2]["engagement_id"],
        result["root"]["run_id"],
    )
    generation = Path(loaded["output_dir"]) / result["final"]["source_ref"]
    used = json.loads((generation / "used_recipe.json").read_bytes())
    assert (
        used["accounting_review"]["professional_review"]["reviewed_by"]
        == "Fictional professional"
    )
    assert used["accounting_review"]["root_cause_review"]["selected_alternative"] == 2
    assert (generation / "root_cause_client_report.docx").is_file()
    assert (
        review_run[1]
        / result["original"]["source_ref"]
        / "root_cause_client_report.docx"
    ).is_file()
    assert all(r["run"]["status"] == "running" for r in runs)


@pytest.mark.parametrize("variance_run", ["blocked", "partial", "pvm"], indirect=True)
def test_native_variance_public_blocked_or_partial_controls_refuse_positive_professional_acceptance(
    review_run,
):
    result = rpc_program(
        review_run[0],
        initial(review_run)
        + """
const chosen={...originalWork,source_ref:original.source_ref,section:'professional_review',alternative:0};
const page=payload(call('vera_workspace_variance_review_read',chosen));
const fields={decision:'accepted',reviewer:'Fictional reviewer',reviewed_at:'2026-10-08T10:00:00+02:00',basis:'Fictional review'};
const authority=p=>({...chosen,revision:p.revision,review_ticket:p.review_ticket,item_id:p.selection.id,expected_draft_revision:p.draft_revision});
payload(call('vera_workspace_variance_review_draft_save',{...authority(page),fields}));
const current=payload(call('vera_workspace_variance_review_read',chosen));
const result={page,refused:call('vera_workspace_variance_review_commit',{...authority(current),confirmed:true,idempotency_key:'refuse-ineligible'})};
""",
    )
    assert result["page"]["acceptance_available"] is False
    assert result["refused"]["isError"] is True
    assert "public accounting controls" in result["refused"]["content"][0]["text"]
    assert (
        len(
            _load_customer_ledger().list_runs(
                Path(review_run[2]["client_root"]), review_run[2]["engagement_id"]
            )
        )
        == 1
    )


@pytest.mark.parametrize("action", ["rejected", "changes_requested"])
def test_native_variance_negative_professional_decision_remains_attributed_and_report_draft(
    review_run, action
):
    result = rpc_program(
        review_run[0],
        initial(review_run)
        + decision(
            "originalWork", "original", "professional_review", "declined", action=action
        )
        + successor_calculate("declined", "after")
        + "const result={declined,after};",
    )
    assert result["declined"]["decision"] == action
    assert (
        result["after"]["accounting_readiness"]["professional_review"]["status"]
        == action
    )
    assert (
        result["after"]["accounting_readiness"]["professional_review"]["reviewed_by"]
        == "Fictional professional"
    )
    assert (
        result["after"]["accounting_readiness"]["client_report_status"]
        == "draft_pending_professional_review"
    )


@pytest.mark.parametrize("alternative", [0, 11, True])
def test_native_variance_root_review_refuses_absent_or_boolean_alternative(
    review_run, alternative
):
    result = rpc_program(
        review_run[0],
        initial(review_run)
        + f"const result=call('vera_workspace_variance_review_read',{{...originalWork,source_ref:original.source_ref,section:'root_cause_review',alternative:{json.dumps(alternative)}}});",
    )
    assert result["isError"] is True


def selected_review(fixture) -> str:
    return (
        initial(fixture)
        + """
const chosen={...originalWork,source_ref:original.source_ref,section:'root_cause_review',alternative:2};
const page=payload(call('vera_workspace_variance_review_read',chosen));
const authority=p=>({...chosen,revision:p.revision,review_ticket:p.review_ticket,item_id:p.selection.id,expected_draft_revision:p.draft_revision});
const fields={decision:'accepted',reviewer:'PRIVATE UNSENT REVIEWER',reviewed_at:'2026-10-08T10:00:00+02:00',basis:'PRIVATE UNSENT BASIS'};
"""
    )


def test_native_variance_exact_explanation_omits_private_draft_and_other_alternatives(
    review_run,
):
    result = rpc_program(
        review_run[0],
        selected_review(review_run)
        + """
payload(call('vera_workspace_variance_review_draft_save',{...authority(page),fields}));
const recovered=payload(call('vera_workspace_variance_review_read',chosen));
const result={recovered,explanation:call('vera_workspace_variance_review_explain',{...chosen,revision:page.revision})};
""",
    )
    explanation = result["explanation"]
    context = explanation["structuredContent"]
    assert result["recovered"]["draft"]["reviewer"] == "PRIVATE UNSENT REVIEWER"
    assert "PRIVATE UNSENT" not in json.dumps(explanation)
    assert "_meta" not in explanation
    assert context["record"]["alternative"]["alternative_result"] == 2
    assert context["record"]["alternative"]["selected_rows"]
    assert "alternatives" not in context["record"]
    assert "original" not in context
    assert context["professional_approval"] is False
    assert context["run_completed"] is False


@pytest.mark.parametrize(
    "change",
    [
        "{review_ticket:''}",
        "{review_ticket:page.review_ticket.replace(/\\.([a-f0-9])/,(_,c)=>'.'+(c==='a'?'b':'a'))}",
        "{item_id:'root_cause_review:3'}",
        "{alternative:3}",
        "{source_ref:'variance-'+ 'a'.repeat(64)}",
        "{revision:'stale'}",
    ],
)
def test_native_variance_signed_mutation_refuses_changed_exact_identity(
    review_run, change
):
    result = rpc_program(
        review_run[0],
        selected_review(review_run)
        + f"const result=call('vera_workspace_variance_review_draft_save',{{...authority(page),fields,...{change}}});",
    )
    assert result["isError"] is True
    assert not list(
        review_run[1].parent.glob(".native-workspace/variance-professional-draft-*")
    )


@pytest.mark.parametrize(
    "change",
    [
        "{reviewer:''}",
        "{basis:' '}",
        "{decision:''}",
        "{reviewed_at:'2026-10-08T10:00:00'}",
        "{reviewed_at:'not-a-date'}",
    ],
)
def test_native_variance_incomplete_saved_attribution_cannot_conserve(
    review_run, change
):
    result = rpc_program(
        review_run[0],
        selected_review(review_run)
        + f"payload(call('vera_workspace_variance_review_draft_save',{{...authority(page),fields:{{...fields,...{change}}}}}));"
        + """
const current=payload(call('vera_workspace_variance_review_read',chosen));
const result=call('vera_workspace_variance_review_commit',{...authority(current),confirmed:true,idempotency_key:'invalid-attribution'});
""",
    )
    assert result["isError"] is True
    assert not list(
        review_run[1].parent.glob(".native-workspace/variance-review-request-*")
    )


def test_native_variance_concurrent_draft_and_unrenewed_confirmation_refuse_writes(
    review_run,
):
    result = rpc_program(
        review_run[0],
        selected_review(review_run)
        + """
payload(call('vera_workspace_variance_review_draft_save',{...authority(page),fields}));
const stale=call('vera_workspace_variance_review_draft_save',{...authority(page),fields:{...fields,basis:'overwritten'}});
const current=payload(call('vera_workspace_variance_review_read',chosen));
const unconfirmed=call('vera_workspace_variance_review_commit',{...authority(current),confirmed:false,idempotency_key:'unconfirmed'});
const result={stale,unconfirmed,current};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["unconfirmed"]["isError"] is True
    assert result["current"]["draft"]["basis"] == "PRIVATE UNSENT BASIS"
    assert not list(
        review_run[1].parent.glob(".native-workspace/variance-review-request-*")
    )


def test_native_variance_viewer_can_read_exact_record_but_cannot_save(review_run):
    prepared = rpc_program(
        review_run[0], initial(review_run) + "const result=original;"
    )
    env = {**review_run[0], "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        env,
        f"const chosen={{work_ref:{json.dumps(review_run[2]['work_ref'])},source_ref:{json.dumps(prepared['source_ref'])},section:'professional_review',alternative:0}};"
        + """
const page=payload(call('vera_workspace_variance_review_read',chosen));
const result={page,refused:call('vera_workspace_variance_review_draft_save',{...chosen,revision:page.revision,review_ticket:page.review_ticket,item_id:page.selection.id,expected_draft_revision:page.draft_revision,fields:{decision:'',reviewer:'',reviewed_at:'',basis:''}})};
""",
    )
    assert result["page"]["can_write"] is False
    assert result["refused"]["isError"] is True


@pytest.mark.parametrize("member", ["comparison.json", "professional-decision.json"])
def test_native_variance_changed_conserved_artifact_refuses_predecessor_read(
    review_run, member
):
    rpc_program(
        review_run[0],
        initial(review_run)
        + decision("originalWork", "original", "professional_review", "accounting")
        + "const result=accounting;",
    )
    path = next(
        review_run[1].parent.glob(".native-workspace/variance-reviewed-*/" + member)
    )
    path.write_bytes(path.read_bytes() + b" ")
    result = rpc_program(
        review_run[0],
        f"const result=call('vera_workspace_variance_setup',{{work_ref:{json.dumps(review_run[2]['work_ref'])}}});",
    )
    assert result["isError"] is True
    assert "changed" in result["content"][0]["text"]


def test_native_variance_real_archive_side_effect_interruption_requires_recovery(
    review_run,
):
    args = rpc_program(
        review_run[0],
        selected_review(review_run)
        + """
payload(call('vera_workspace_variance_review_draft_save',{...authority(page),fields}));
const current=payload(call('vera_workspace_variance_review_read',chosen));
const result={...authority(current),confirmed:true,idempotency_key:'interrupted-real-conservation'};
""",
    )
    module = workspace_module()
    program = f"""
import json, sys
sys.path.insert(0, {str(Path(module.__file__).parent)!r})
import native_workspace as workspace
import native_variance_review as review
ordinary = review.conserve
def interrupted(*values, **options):
    ordinary(*values, **options)
    raise RuntimeError('Fictional process interrupted after actual registered successor')
review.conserve = interrupted
workspace.dispatch('vera_workspace_variance_review_commit', json.load(sys.stdin))
"""
    env = {**os.environ, **review_run[0]}
    env.pop("VERA_WORKSPACE_BINDINGS", None)
    completed = subprocess.run(
        [sys.executable, "-B", "-c", program],
        input=json.dumps(args),
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode != 0
    assert "after actual registered successor" in completed.stderr
    ledger = _load_customer_ledger()
    runs = ledger.list_runs(
        Path(review_run[2]["client_root"]), review_run[2]["engagement_id"]
    )
    assert len(runs) == 2
    selected = {k: review_run[2][k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        review_run[0],
        f"const result={{setup:payload(call('vera_workspace_variance_setup',{{work_ref:{json.dumps(review_run[2]['work_ref'])}}})),retry:call('vera_workspace_variance_review_commit',{json.dumps(args)}),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};",
    )
    assert result["setup"]["status"] == "recovery_required"
    assert result["retry"]["isError"] is True
    assert result["closure"]["isError"] is True
    assert (
        len(
            ledger.list_runs(
                Path(review_run[2]["client_root"]), review_run[2]["engagement_id"]
            )
        )
        == 2
    )


def test_native_variance_ordinary_file_execution_can_close_without_native_review_state(
    review_run,
):
    env, output, binding, fields = review_run
    ledger = _load_customer_ledger()
    loaded = ledger.load_run(
        Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
    )
    inputs = {
        r["binding_id"]: Path(loaded["run_root"]) / r["execution_relative_path"]
        for r in loaded["input_manifest"]["inputs"]
    }
    root = workspace_module().module_root("variance-analysis")
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(root / "scripts/run_variance.py"),
            str(inputs[fields["source_input_id"]]),
            "--recipe",
            str(inputs[fields["recipe_input_id"]]),
            "--output-dir",
            str(output / "ordinary-file-variance"),
            "--currency",
            fields["currency"],
            "--language",
            fields["language"],
            "--client-engagement",
            loaded["context_path"],
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    write_no_model_report(output, "variance-analysis", binding["run_id"])
    before = {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        env,
        setup(selected)
        + declare_all()
        + """
const finalized=payload(call('vera_workspace_archive_finalize',seal));
const ready=read();
const result={finalized,completed:payload(call('vera_workspace_archive_complete',{...authority(ready),human_reviewed:true,idempotency_key:'ordinary-file-complete'}))};
""",
    )
    assert result["completed"]["status"] == "completed"
    assert result["completed"]["professional_approval"] is False
    assert result["completed"]["sent_or_published"] is False
    assert {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    } == before
    assert not list(output.parent.glob(".native-workspace/variance-state.json"))
    assert not list(output.parent.glob(".native-workspace/variance-review-request-*"))
