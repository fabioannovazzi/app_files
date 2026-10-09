"""Actual registered source grants, complete proposals and separate successor runs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import archive_cli
from tests.plugins.test_vera_native_variance import variance_run  # noqa: F401
from tests.plugins.test_vera_native_workspace import workspace_module

__all__ = []


@pytest.fixture
def author_run(variance_run, tmp_path):
    """Use the real owned Archive with separate state/source roots."""
    env, output, binding, execution = variance_run
    env = {
        **env,
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-variance-author",
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(
            tmp_path.parent / ("variance-author-state-" + tmp_path.name)
        ),
    }
    archive_cli(
        env, "configure", "--archive-root", str(Path(binding["client_root"]).parent)
    )
    env.pop("VERA_WORKSPACE_BINDINGS")
    binding = {
        **binding,
        "work_ref": "studio-"
        + "_".join(
            binding[k].split("_", 1)[1]
            for k in ("client_id", "engagement_id", "run_id")
        ),
    }
    choices = {
        "question": "Confronta AC e PL per mese e categoria; preserva limiti e controlli da riscontrare.",
        "source_input_id": execution["source_input_id"],
        "evidence_input_ids": [],
        "base_recipe_input_id": "",
        "currency": "EUR",
        "language": "it",
    }
    loaded = _load_customer_ledger().load_run(
        Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
    )
    receipt = next(
        r
        for r in loaded["input_manifest"]["inputs"]
        if r["binding_id"] == execution["recipe_input_id"]
    )
    recipe = json.loads(
        (Path(loaded["run_root"]) / receipt["execution_relative_path"]).read_bytes()
    )
    return (
        env,
        output,
        binding,
        choices,
        {
            "recipe": recipe,
            "note": "Controlli e interpretazione professionale da completare.",
        },
    )


def grant(fixture):
    return (
        f"const work={{work_ref:{json.dumps(fixture[2]['work_ref'])}}};const fields={json.dumps(fixture[3])};"
        + """
const setup=payload(call('vera_workspace_variance_author_setup',work));
payload(call('vera_workspace_variance_author_draft_save',{...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields}));
const fresh=payload(call('vera_workspace_variance_author_setup',work));
const request={...work,revision:fresh.revision,review_ticket:fresh.review_ticket,expected_draft_revision:fresh.draft_revision,fields,confirmed:true,idempotency_key:'fictional-author-grant'};
const issued=payload(call('vera_workspace_variance_author_request',request));
const identity={...work,grant_ref:issued.grant_ref};
const opened=payload(call('vera_workspace_variance_author_read',identity));
"""
    )


def stage(fixture):
    return (
        grant(fixture)
        + f"const proposal={json.dumps(fixture[4])};"
        + """
const stageArgs={...identity,revision:opened.revision,proposal,idempotency_key:'fictional-complete-proposal'};
const staged=call('vera_workspace_variance_author_stage',stageArgs).structuredContent;
if(!staged.saved)throw new Error(JSON.stringify(staged));
const chosen={...identity,case_ref:staged.case_ref};
const page=payload(call('vera_workspace_variance_author_read',chosen));
"""
    )


def publish(fixture):
    return (
        stage(fixture)
        + """
const reviewed={decision:'accepted',reviewer:'Fictional reviewer',reviewed_at:'2026-10-08T15:30:00+02:00',basis:'Fictional source, complete comparison choices and pending accounting decisions checked.'};
const authority=p=>({...chosen,source_ref:issued.grant_ref,item_id:staged.case_ref,revision:p.revision,review_ticket:p.review_ticket,expected_draft_revision:p.draft_revision,fields:reviewed});
payload(call('vera_workspace_variance_author_review_draft_save',authority(page)));
const current=payload(call('vera_workspace_variance_author_read',chosen));
const publishArgs={...authority(current),confirmed:true,idempotency_key:'fictional-readback-conservation'};
const conserved=payload(call('vera_workspace_variance_author_publish',publishArgs));
"""
    )


def test_native_variance_initial_authoring_conserves_fresh_run_before_separate_calculation(
    author_run,
):
    env, output, binding, _, _ = author_run
    result = rpc_program(
        env,
        publish(author_run)
        + """
const retry=payload(call('vera_workspace_variance_author_publish',publishArgs));
const reopened=payload(call('vera_workspace_variance_author_read',chosen));
const target={work_ref:conserved.work_ref};
const before=payload(call('vera_workspace_variance_setup',target));
const values={source_input_id:conserved.source_input_id,recipe_input_id:conserved.recipe_input_id,currency:fields.currency,language:fields.language};
payload(call('vera_workspace_variance_draft_save',{...target,revision:before.revision,review_ticket:before.review_ticket,expected_draft_revision:before.draft_revision,fields:values}));
const final=payload(call('vera_workspace_variance_setup',target));
const calculated=payload(call('vera_workspace_variance_prepare',{...target,revision:final.revision,review_ticket:final.review_ticket,expected_draft_revision:final.draft_revision,fields:values,confirmed:true,idempotency_key:'fictional-separate-calculation'}));
const result={conserved,retry,reopened,before,calculated};
""",
    )
    assert result["conserved"] == result["retry"]
    assert result["conserved"]["comparison_calculated"] is False
    assert result["before"]["source_ref"] is None
    assert result["reopened"]["status"] == "registered"
    assert result["calculated"]["professional_approval"] is False
    ledger = _load_customer_ledger()
    runs = ledger.list_runs(Path(binding["client_root"]), binding["engagement_id"])
    assert len(runs) == 2
    successor = next(r["run"] for r in runs if r["run"]["run_id"] != binding["run_id"])
    loaded = ledger.load_run(
        Path(binding["client_root"]), binding["engagement_id"], successor["run_id"]
    )
    generation = Path(loaded["output_dir"]) / result["calculated"]["source_ref"]
    context = json.loads((generation / "standard_variance_context.json").read_bytes())
    assert context["totals"]["total_delta"] == 6000
    assert (generation / "root_cause_client_report.docx").is_file()
    assert len(list(output.rglob("inspection.json"))) == 1
    assert not list(output.rglob("variance_results.csv"))
    assert (
        ledger.load_run(
            Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
        )["run"]["status"]
        == "running"
    )


def test_native_variance_author_context_selects_only_explicit_sources_and_hides_private_readback(
    author_run,
):
    result = rpc_program(
        author_run[0],
        stage(author_run)
        + "const result=call('vera_workspace_variance_author_context',{...chosen,revision:page.revision});",
    )
    content = result["structuredContent"]
    assert len(content["sources"]) == 1
    assert content["sources"][0]["input_id"] == author_run[3]["source_input_id"]
    assert Path(content["sources"][0]["authorized_path"]).is_file()
    assert "review_draft" not in content
    assert "scope" not in content["mandate"]
    assert "_meta" not in result
    assert content["validation"]["calculated"] is False


@pytest.mark.parametrize("slot", ["professional_review", "root_cause_review"])
def test_native_variance_author_proposal_refuses_model_approval_before_conservation(
    author_run, slot
):
    author_run[4]["recipe"]["accounting_review"][slot] = {
        "status": "approved",
        "reviewed_by": "Invented reviewer",
    }
    result = rpc_program(
        author_run[0],
        grant(author_run)
        + f"const result=call('vera_workspace_variance_author_stage',{{...identity,revision:opened.revision,proposal:{json.dumps(author_run[4])},idempotency_key:'refuse-approval'}});",
    )
    assert result["isError"] is True
    assert "approval" in result["content"][0]["text"]
    assert not list(
        (author_run[1].parent / ".native-workspace").glob("variance-authored-*")
    )


@pytest.mark.parametrize(
    "change", ["missing-column", "text-amount", "missing-basis", "different-language"]
)
def test_native_variance_author_invalid_recipe_refuses_without_registered_successor(
    author_run, change
):
    recipe = author_run[4]["recipe"]
    if change == "missing-column":
        recipe["mappings"]["amount_column"] = "Not supplied"
    elif change == "text-amount":
        recipe["mappings"]["amount_column"] = "Category"
    elif change == "missing-basis":
        recipe["options"].pop("comparison_basis")
    else:
        recipe["language"] = "fr"
    result = rpc_program(
        author_run[0],
        grant(author_run)
        + f"const result=call('vera_workspace_variance_author_stage',{{...identity,revision:opened.revision,proposal:{json.dumps(author_run[4])},idempotency_key:'refuse-schema'}});",
    )
    assert result["isError"] is True
    assert not list(
        (author_run[1].parent / ".native-workspace").glob("variance-authored-*")
    )


def test_native_variance_author_empty_draft_cas_retains_no_grant(author_run):
    env, output, binding, values, _ = author_run
    result = rpc_program(
        env,
        f"const work={{work_ref:{json.dumps(binding['work_ref'])}}};const fields={json.dumps(values)};"
        + """
const setup=payload(call('vera_workspace_variance_author_setup',work));
const authority={...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision};
const saved=payload(call('vera_workspace_variance_author_draft_save',{...authority,fields}));
const stale=call('vera_workspace_variance_author_draft_save',{...authority,fields});
const after=payload(call('vera_workspace_variance_author_setup',work));
const cleared=payload(call('vera_workspace_variance_author_draft_save',{...work,revision:after.revision,review_ticket:after.review_ticket,expected_draft_revision:after.draft_revision,fields:{question:'',source_input_id:'',base_recipe_input_id:'',evidence_input_ids:[],currency:'',language:''}}));
const result={saved,stale,cleared,after:payload(call('vera_workspace_variance_author_setup',work))};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["after"]["draft"]["question"] == ""
    assert result["after"]["grants"] == []
    assert list(output.iterdir()) == []


def test_native_variance_author_cancel_closes_model_grant_without_erasing_inspection(
    author_run,
):
    result = rpc_program(
        author_run[0],
        stage(author_run)
        + """
const args={...chosen,revision:page.revision,review_ticket:page.review_ticket,source_ref:issued.grant_ref,item_id:staged.case_ref,confirmed:true,idempotency_key:'cancel-comparison'};
const cancelled=payload(call('vera_workspace_variance_author_cancel',args));
const after=payload(call('vera_workspace_variance_author_read',chosen));
const context=call('vera_workspace_variance_author_context',{...chosen,revision:after.revision});
const result={cancelled,after,context};
""",
    )
    assert result["after"]["status"] == "cancelled"
    assert result["context"]["isError"] is True
    assert len(list(author_run[1].rglob("inspection.json"))) == 1
    assert (
        result["after"]["proposal"]["recipe"]["mappings"]["amount_column"] == "Amount"
    )


@pytest.mark.parametrize("role", ["VIEWER", ""])
def test_native_variance_author_read_only_role_cannot_save_or_issue_source_grant(
    author_run, role
):
    env, output, binding, values, _ = author_run
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": role},
        f"const work={{work_ref:{json.dumps(binding['work_ref'])}}};const fields={json.dumps(values)};"
        + """
const setup=payload(call('vera_workspace_variance_author_setup',work));
const authority={...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields};
const result={setup,save:call('vera_workspace_variance_author_draft_save',authority),grant:call('vera_workspace_variance_author_request',{...authority,confirmed:true,idempotency_key:'forbidden-grant'})};
""",
    )
    assert result["setup"]["can_write"] is False
    assert result["save"]["isError"] is True
    assert result["grant"]["isError"] is True
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "field", ["source_input_id", "evidence_input_ids", "base_recipe_input_id"]
)
def test_native_variance_author_foreign_receipt_refused_before_inspection(
    author_run, field
):
    values = dict(author_run[3])
    values[field] = (
        ["input_999999999999999999999999"]
        if field == "evidence_input_ids"
        else "input_999999999999999999999999"
    )
    result = rpc_program(
        author_run[0],
        f"const work={{work_ref:{json.dumps(author_run[2]['work_ref'])}}};const fields={json.dumps(values)};"
        + """
const setup=payload(call('vera_workspace_variance_author_setup',work));
const result=call('vera_workspace_variance_author_draft_save',{...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields});
""",
    )
    assert result["isError"] is True
    assert list(author_run[1].iterdir()) == []


@pytest.mark.parametrize("interruption", ["intent", "intake", "proposal", "readback"])
def test_native_variance_author_uncertain_write_refuses_stage_and_archive_closure(
    author_run, interruption
):
    env, output, binding, _, _ = author_run
    private = output.parent / ".native-workspace"
    private.mkdir(exist_ok=True)
    if interruption == "intent":
        (private / "variance-author-request-incomplete.json").write_text(
            json.dumps({"request_sha256": "0" * 64})
        )
    elif interruption == "intake":
        (output / ("variance-intake-" + "0" * 64)).mkdir()
    elif interruption == "proposal":
        (private / ("variance-authored-" + "0" * 64)).mkdir()
    else:
        (private / ("variance-comparison-readback-" + "0" * 64)).mkdir()
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        env,
        f"const work={{work_ref:{json.dumps(binding['work_ref'])}}};const result={{setup:payload(call('vera_workspace_variance_author_setup',work)),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};",
    )
    assert result["setup"]["recovery_required"] is True
    assert result["setup"]["can_write"] is False
    assert result["closure"]["isError"] is True


def test_native_variance_author_private_readback_name_never_enters_model_context(
    author_run,
):
    result = rpc_program(
        author_run[0],
        stage(author_run)
        + """
payload(call('vera_workspace_variance_author_review_draft_save',{...chosen,revision:page.revision,review_ticket:page.review_ticket,source_ref:issued.grant_ref,item_id:staged.case_ref,expected_draft_revision:page.draft_revision,fields:{decision:'',reviewer:'Private unsent reviewer',reviewed_at:'',basis:''}}));
const current=payload(call('vera_workspace_variance_author_read',chosen));
const result=call('vera_workspace_variance_author_context',{...chosen,revision:current.revision});
""",
    )
    assert "Private unsent reviewer" not in json.dumps(result)
    assert "review_draft" not in result["structuredContent"]


def test_native_variance_author_omitted_proposal_does_not_select_latest(author_run):
    result = rpc_program(
        author_run[0],
        stage(author_run)
        + "const result=payload(call('vera_workspace_variance_author_read',identity));",
    )
    assert len(result["proposals"]) == 1
    assert result["selection"] is None
    assert "proposal" not in result


def test_native_variance_author_changed_proposal_bytes_refuse_read(author_run):
    env, output, binding, _, _ = author_run
    result = rpc_program(env, stage(author_run) + "const result={staged,chosen};")
    path = (
        output.parent
        / ".native-workspace"
        / result["staged"]["case_ref"]
        / "comparison.json"
    )
    value = json.loads(path.read_bytes())
    value["mappings"]["amount_column"] = "Category"
    path.write_text(json.dumps(value))
    changed = rpc_program(
        env,
        f"const result=call('vera_workspace_variance_author_read',{json.dumps(result['chosen'])});",
    )
    assert changed["isError"] is True
    assert "changed" in changed["content"][0]["text"]


def test_native_variance_author_changed_same_key_stage_refuses_new_proposal(author_run):
    result = rpc_program(
        author_run[0],
        stage(author_run)
        + "const result=call('vera_workspace_variance_author_stage',{...stageArgs,proposal:{...proposal,note:'Changed same-key note'}});",
    )
    assert result["isError"] is True
    assert "retry" in result["content"][0]["text"]


@pytest.mark.parametrize("variance_run", ["prior-reviewed"], indirect=True)
def test_native_variance_author_correction_preserves_prior_raw_reviews_without_inheriting_approval(
    author_run,
):
    ledger = _load_customer_ledger()
    loaded = ledger.load_run(
        Path(author_run[2]["client_root"]),
        author_run[2]["engagement_id"],
        author_run[2]["run_id"],
    )
    prior = next(
        r
        for r in loaded["input_manifest"]["inputs"]
        if r["execution_relative_path"].endswith(".json")
    )
    original = json.loads(
        (Path(loaded["run_root"]) / prior["execution_relative_path"]).read_bytes()
    )
    author_run[3]["base_recipe_input_id"] = prior["binding_id"]
    author_run[4]["recipe"]["accounting_review"]["professional_review"] = {
        "status": "pending"
    }
    author_run[4]["recipe"]["accounting_review"]["root_cause_review"] = {
        "status": "pending"
    }
    result = rpc_program(
        author_run[0],
        publish(author_run)
        + "const result={conserved,proposal:page.proposal,context:call('vera_workspace_variance_author_context',{...chosen,revision:page.revision})};",
    )
    assert result["proposal"]["prior_recipe_and_reviews"] == original
    assert result["proposal"]["recipe"]["accounting_review"]["professional_review"] == {
        "status": "pending"
    }
    assert result["proposal"]["recipe"]["accounting_review"]["root_cause_review"] == {
        "status": "pending"
    }
    successor = next(
        r["run"]
        for r in ledger.list_runs(
            Path(author_run[2]["client_root"]), author_run[2]["engagement_id"]
        )
        if r["run"]["run_id"] != author_run[2]["run_id"]
    )
    retained = ledger.load_run(
        Path(author_run[2]["client_root"]),
        author_run[2]["engagement_id"],
        successor["run_id"],
    )
    assert any(
        r["binding_id"] == prior["binding_id"]
        for r in retained["input_manifest"]["inputs"]
    )
    assert result["context"]["isError"] is True


@pytest.mark.parametrize("variance_run", ["pvm"], indirect=True)
def test_native_variance_author_pvm_uses_registered_units_and_separate_public_calculation(
    author_run,
):
    result = rpc_program(
        author_run[0],
        publish(author_run)
        + """
const target={work_ref:conserved.work_ref};
const pvmSetup=payload(call('vera_workspace_variance_setup',target));
const pvmFields={source_input_id:conserved.source_input_id,recipe_input_id:conserved.recipe_input_id,currency:'EUR',language:'it'};
payload(call('vera_workspace_variance_draft_save',{...target,revision:pvmSetup.revision,review_ticket:pvmSetup.review_ticket,expected_draft_revision:pvmSetup.draft_revision,fields:pvmFields}));
const pvmFresh=payload(call('vera_workspace_variance_setup',target));
const calculated=payload(call('vera_workspace_variance_prepare',{...target,revision:pvmFresh.revision,review_ticket:pvmFresh.review_ticket,expected_draft_revision:pvmFresh.draft_revision,fields:pvmFields,confirmed:true,idempotency_key:'fictional-pvm-calculation'}));
const result={conserved,calculated,validation:page.validation};
""",
    )
    assert result["validation"]["pvm_mapped"] is True
    assert result["validation"]["calculated"] is False
    ledger = _load_customer_ledger()
    successor = next(
        r["run"]
        for r in ledger.list_runs(
            Path(author_run[2]["client_root"]), author_run[2]["engagement_id"]
        )
        if r["run"]["run_id"] != author_run[2]["run_id"]
    )
    loaded = ledger.load_run(
        Path(author_run[2]["client_root"]),
        author_run[2]["engagement_id"],
        successor["run_id"],
    )
    generation = Path(loaded["output_dir"]) / result["calculated"]["source_ref"]
    context = json.loads((generation / "standard_variance_context.json").read_bytes())
    assert context["totals"]["amount_baseline"] == 3000
    assert context["totals"]["amount_comparison"] == 3300
    assert context["totals"]["total_delta"] == 300
    assert (generation / "pvm_decomposition_ladder_context.json").is_file()
    assert (generation / "pvm_decomposition_ladder.png").is_file()
    ladder = json.loads(
        (generation / "pvm_decomposition_ladder_context.json").read_bytes()
    )
    pvm = ladder["totals"]
    assert (
        pvm["price_variance"]
        + pvm["volume_variance"]
        + pvm["mix_variance"]
        + pvm["component_reconciliation_delta"]
    ) == pytest.approx(300)
    assert pvm["component_reconciliation_delta"] == pytest.approx(-20)
    assert ladder["levels"][2]["components"][3] == {
        "variance_type": "Other",
        "variance_amount": -20,
        "source_columns": ["component_reconciliation_delta"],
        "is_residual_other": True,
    }
    assert result["calculated"]["professional_approval"] is False


@pytest.mark.parametrize(
    "slot,attribution",
    [
        ("professional_review", {"reviewed_by": "Invented person"}),
        ("root_cause_review", {"selected_alternative": 2}),
    ],
)
def test_native_variance_author_pending_status_cannot_hide_model_attribution(
    author_run, slot, attribution
):
    author_run[4]["recipe"]["accounting_review"][slot] = {
        "status": "pending",
        **attribution,
    }
    result = rpc_program(
        author_run[0],
        grant(author_run)
        + f"const result=call('vera_workspace_variance_author_stage',{{...identity,revision:opened.revision,proposal:{json.dumps(author_run[4])},idempotency_key:'refuse-hidden-attribution'}});",
    )
    assert result["isError"] is True
    assert "attribute" in result["content"][0]["text"]


@pytest.mark.parametrize("missing", ["reviewer", "reviewed_at", "basis"])
def test_native_variance_author_incomplete_readback_cannot_register_successor(
    author_run, missing
):
    reviewed = {
        "decision": "accepted",
        "reviewer": "Fictional reviewer",
        "reviewed_at": "2026-10-08T16:00:00+02:00",
        "basis": "Fictional full comparison checked.",
    }
    reviewed[missing] = ""
    result = rpc_program(
        author_run[0],
        stage(author_run)
        + f"const reviewed={json.dumps(reviewed)};"
        + """
const authority=p=>({...chosen,source_ref:issued.grant_ref,item_id:staged.case_ref,revision:p.revision,review_ticket:p.review_ticket,expected_draft_revision:p.draft_revision,fields:reviewed});
payload(call('vera_workspace_variance_author_review_draft_save',authority(page)));
const current=payload(call('vera_workspace_variance_author_read',chosen));
const result=call('vera_workspace_variance_author_publish',{...authority(current),confirmed:true,idempotency_key:'refuse-incomplete-readback'});
""",
    )
    assert result["isError"] is True
    assert (
        len(
            _load_customer_ledger().list_runs(
                Path(author_run[2]["client_root"]), author_run[2]["engagement_id"]
            )
        )
        == 1
    )


def test_native_variance_author_readback_cas_preserves_first_concurrent_edit(
    author_run,
):
    result = rpc_program(
        author_run[0],
        stage(author_run)
        + """
const authority={...chosen,source_ref:issued.grant_ref,item_id:staged.case_ref,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision};
payload(call('vera_workspace_variance_author_review_draft_save',{...authority,fields:{decision:'',reviewer:'First literal draft',reviewed_at:'',basis:''}}));
const stale=call('vera_workspace_variance_author_review_draft_save',{...authority,fields:{decision:'',reviewer:'Concurrent overwrite',reviewed_at:'',basis:''}});
const current=payload(call('vera_workspace_variance_author_read',chosen));
const result={stale,current};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["current"]["review_draft"]["reviewer"] == "First literal draft"


def test_native_variance_author_open_mandate_blocks_archive_closure_without_erasing_inspection(
    author_run,
):
    selected = {k: author_run[2][k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        author_run[0],
        grant(author_run)
        + f"const result=call('vera_workspace_archive_closure',{json.dumps(selected)});",
    )
    assert result["isError"] is True
    assert "conserved/cancelled mandate" in result["content"][0]["text"]
    assert len(list(author_run[1].rglob("inspection.json"))) == 1


def test_native_variance_author_real_successor_process_failure_requires_recovery(
    author_run,
):
    args = rpc_program(
        author_run[0],
        stage(author_run)
        + """
const reviewed={decision:'accepted',reviewer:'Fictional reviewer',reviewed_at:'2026-10-08T15:30:00+02:00',basis:'Fictional complete comparison readback; accounting decisions remain pending.'};
const authority=p=>({...chosen,source_ref:issued.grant_ref,item_id:staged.case_ref,revision:p.revision,review_ticket:p.review_ticket,expected_draft_revision:p.draft_revision,fields:reviewed});
payload(call('vera_workspace_variance_author_review_draft_save',authority(page)));
const current=payload(call('vera_workspace_variance_author_read',chosen));
const result={...authority(current),confirmed:true,idempotency_key:'interrupted-real-author-conservation'};
""",
    )
    program = f"""
import json, sys
sys.path.insert(0, {str(Path(workspace_module().__file__).parent)!r})
import native_workspace as workspace
import native_variance_authoring as author
ordinary = author.conserve
def interrupted(*values, **options):
    ordinary(*values, **options)
    raise RuntimeError('Fictional process failure after actual authored successor')
author.conserve = interrupted
workspace.dispatch('vera_workspace_variance_author_publish', json.load(sys.stdin))
"""
    env = {**os.environ, **author_run[0]}
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
    assert "after actual authored successor" in completed.stderr
    ledger = _load_customer_ledger()
    folder = Path(author_run[2]["client_root"])
    assert len(ledger.list_runs(folder, author_run[2]["engagement_id"])) == 2
    selected = {k: author_run[2][k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        author_run[0],
        f"const result={{setup:payload(call('vera_workspace_variance_author_setup',{{work_ref:{json.dumps(author_run[2]['work_ref'])}}})),retry:call('vera_workspace_variance_author_publish',{json.dumps(args)}),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};",
    )
    assert result["setup"]["recovery_required"] is True
    assert result["retry"]["isError"] is True
    assert result["closure"]["isError"] is True
    assert len(ledger.list_runs(folder, author_run[2]["engagement_id"])) == 2
    assert len(list(author_run[1].rglob("inspection.json"))) == 1
    assert (
        len(
            list(
                author_run[1].parent.glob(
                    ".native-workspace/variance-authored-*/comparison.json"
                )
            )
        )
        == 1
    )
    assert not list(author_run[1].rglob("variance_results.csv"))
