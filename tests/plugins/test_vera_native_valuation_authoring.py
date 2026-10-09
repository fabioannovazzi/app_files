"""Complete model proposals become named immutable cases before separate calculation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import archive_cli
from tests.plugins.test_vera_native_valuation import valuation_run  # noqa: F401

__all__ = []


@pytest.fixture
def author_run(valuation_run):
    env, output, binding = valuation_run
    env = {
        **env,
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-financial-archive",
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(
            Path(binding["client_root"]).parent.parent
            / (Path(binding["client_root"]).parent.name + "-author-private-state")
        ),
    }
    archive_cli(
        env, "configure", "--archive-root", str(Path(binding["client_root"]).parent)
    )
    env.pop("VERA_WORKSPACE_BINDINGS")
    ref = "studio-" + "_".join(
        binding[k].split("_", 1)[1] for k in ("client_id", "engagement_id", "run_id")
    )
    ledger = _load_customer_ledger()
    loaded = ledger.load_run(
        Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
    )
    rows = loaded["input_manifest"]["inputs"]
    root = Path(loaded["run_root"])
    case_row = next(
        r for r in rows if Path(r["execution_relative_path"]).suffix == ".json"
    )
    case = json.loads((root / case_row["execution_relative_path"]).read_bytes())
    by_path = {
        Path(r["execution_relative_path"])
        .relative_to("inputs")
        .as_posix(): r["binding_id"]
        for r in rows
    }
    sources = {r["id"]: by_path[r["path"]] for r in case["sources"]}
    return (
        env,
        output,
        {**binding, "work_ref": ref},
        {
            "case": case,
            "source_bindings": sources,
            "note": "Complete fictional proposal, pending named readback.",
        },
        case_row["binding_id"],
    )


def begin(fixture, base=False):
    _, _, binding, proposal, case_id = fixture
    return f"""
const work={{work_ref:{json.dumps(binding['work_ref'])}}};
const setup=payload(call('vera_workspace_valuation_author_setup',work));
const fields={{question:'Prepare the full fictional valuation case from only these selected originals.',input_ids:{json.dumps(list(proposal['source_bindings'].values()))},base_input_id:{json.dumps(case_id if base else '')}}};
const intakeScope=v=>({{...work,revision:v.revision,review_ticket:v.review_ticket,expected_draft_revision:v.draft_revision}});
const requested=payload(call('vera_workspace_valuation_author_request',{{...intakeScope(setup),fields,confirmed:true,idempotency_key:'fictional-author-request'}}));
const identity={{...work,grant_ref:requested.grant_ref}};
const read=()=>payload(call('vera_workspace_valuation_author_read',identity));
const first=read();
const proposal={json.dumps(proposal)};
"""


STAGE = """
const stagedCall=call('vera_workspace_valuation_author_stage',{...identity,revision:first.revision,proposal,idempotency_key:'fictional-author-stage'});
if(stagedCall.isError)throw new Error(stagedCall.content[0].text);
const staged=stagedCall.structuredContent;
const exact={...identity,case_ref:staged.case_ref};
const selected=()=>payload(call('vera_workspace_valuation_author_read',exact));
const chosen=selected();
const review={decision:'accepted',reviewer:'Fictional actual declared reviewer',reviewed_at:'2026-10-08T09:31:17+02:00',basis:'Actual fictional full-case readback, including proposed data states. No method/conclusion or PIV acceptance.'};
const reviewScope=v=>({...exact,revision:v.revision,review_ticket:v.review_ticket,source_ref:identity.grant_ref,item_id:exact.case_ref,expected_draft_revision:v.draft_revision});
"""
PUBLISH = """
payload(call('vera_workspace_valuation_author_review_draft_save',{...reviewScope(chosen),fields:review}));
const ready=selected();
const publishedArgs={...reviewScope(ready),fields:review,confirmed:true,idempotency_key:'fictional-author-publish'};
const published=payload(call('vera_workspace_valuation_author_publish',publishedArgs));
"""


@pytest.mark.parametrize(
    "valuation_run",
    ["ready", "partial", "blocked", "finite", "residual", "economic", "holding"],
    indirect=True,
)
def test_initial_whole_case_named_readback_creates_uncalculated_successor(author_run):
    env, output, binding, proposal, _ = author_run
    result = rpc_program(
        env,
        begin(author_run)
        + STAGE
        + PUBLISH
        + "const result={published,staged,retry:payload(call('vera_workspace_valuation_author_publish',publishedArgs)),closed:selected()};",
    )
    assert result["published"] == result["retry"]
    assert result["published"]["case_contents_confirmed"] is True
    assert result["published"]["case_calculated"] is False
    assert result["published"]["method_or_conclusion_acceptance"] is False
    assert result["published"]["piv_conformity"] == "not_assessed"
    assert result["closed"]["status"] == "registered"
    assert (
        result["closed"]["review_draft"]["reviewer"]
        == "Fictional actual declared reviewer"
    )
    ledger = _load_customer_ledger()
    successor = ledger.load_run(
        Path(binding["client_root"]),
        binding["engagement_id"],
        result["published"]["run_id"],
    )
    assert successor["run"]["status"] == "running"
    assert list(Path(successor["output_dir"]).iterdir()) == []
    assert list(output.iterdir()) == []
    row = next(
        r
        for r in successor["input_manifest"]["inputs"]
        if r["binding_id"] == result["published"]["case_input_id"]
    )
    case = json.loads(
        (Path(successor["run_root"]) / row["execution_relative_path"]).read_bytes()
    )
    assert case == proposal["case"]


def test_authored_case_separate_public_calculation_keeps_all_outputs(author_run):
    env, _, _, _, _ = author_run
    result = rpc_program(
        env,
        begin(author_run)
        + STAGE
        + PUBLISH
        + """
const intake=payload(call('vera_workspace_valuation_setup',{work_ref:published.work_ref}));
const casePage=payload(call('vera_workspace_valuation_case',{work_ref:published.work_ref,revision:intake.revision,case_input_id:published.case_input_id}));
const calculated=payload(call('vera_workspace_valuation_prepare',{work_ref:published.work_ref,revision:casePage.revision,review_ticket:casePage.review_ticket,item_id:published.case_input_id,case_input_id:published.case_input_id,confirmed:true,idempotency_key:'separate-author-calculation'}));
const result={calculated,files:payload(call('vera_workspace_valuation_outputs',{work_ref:published.work_ref,source_ref:calculated.source_ref}))};
""",
    )
    assert len(result["files"]["outputs"]) == 19
    assert result["calculated"]["status"] == "ready_for_professional_review"


def test_model_context_excludes_private_name_draft_and_stale_revision(author_run):
    env, _, _, _, _ = author_run
    result = rpc_program(
        env,
        begin(author_run)
        + STAGE
        + """
payload(call('vera_workspace_valuation_author_review_draft_save',{...reviewScope(chosen),fields:review}));
const current=selected();
const exposed=call('vera_workspace_valuation_author_context',{...exact,revision:current.revision});
const stale=call('vera_workspace_valuation_author_stage',{...identity,revision:first.revision,proposal,idempotency_key:'stale-stage'});
const result={exposed,stale};
""",
    )
    projection = result["exposed"]["structuredContent"]
    assert "review_draft" not in projection
    assert "scope" not in projection["mandate"]
    assert author_run[4] not in json.dumps(projection)
    assert "Fictional actual declared reviewer" not in json.dumps(projection)
    assert projection["sources"][0]["authorized_path"]
    assert projection["proposal"]["case"]
    assert result["stale"]["isError"] is True


@pytest.mark.parametrize(
    "corruption", ["human_review", "foreign_source", "source_path"]
)
def test_model_proposal_refuses_invented_attestation_or_rebinds_exact_receipt(
    author_run, corruption
):
    env, _, _, _, _ = author_run
    changes = {
        "human_review": "proposal.case.methods[0].review={decision:'accepted',reviewer:'Invented',reviewed_at:'2026-10-08T00:00:00Z',basis:'Invented'};",
        "foreign_source": "proposal.source_bindings[Object.keys(proposal.source_bindings)[0]]='input_foreign';",
        "source_path": "proposal.case.sources[0].path='../../foreign';proposal.case.sources[0].sha256='0'.repeat(64);",
    }
    result = rpc_program(
        env,
        begin(author_run)
        + changes[corruption]
        + "const result=call('vera_workspace_valuation_author_stage',{...identity,revision:first.revision,proposal,idempotency_key:'modified-stage'});",
    )
    if corruption == "source_path":
        assert result["structuredContent"]["validation"]["valid"] is True
    else:
        assert result["isError"] is True


def test_literal_empty_draft_cas_and_cancel_revoke_model_grant(author_run):
    env, _, binding, _, _ = author_run
    result = rpc_program(
        env,
        f"""
const work={{work_ref:{json.dumps(binding['work_ref'])}}};
const setup=payload(call('vera_workspace_valuation_author_setup',work));
const args={{...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields:setup.draft}};
const saved=payload(call('vera_workspace_valuation_author_draft_save',args));
const stale=call('vera_workspace_valuation_author_draft_save',args);
const result={{saved,stale,current:payload(call('vera_workspace_valuation_author_setup',work))}};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["saved"]["draft_revision"] != result["current"]["revision"]
    result = rpc_program(
        env,
        begin(author_run)
        + """
const cancelled=payload(call('vera_workspace_valuation_author_cancel',{...identity,source_ref:identity.grant_ref,revision:first.revision,review_ticket:first.review_ticket,confirmed:true,idempotency_key:'cancel-author'}));
const closed=read();
const denied=call('vera_workspace_valuation_author_context',{...identity,revision:closed.revision});
const result={cancelled,denied};
""",
    )
    assert result["cancelled"]["status"] == "cancelled"
    assert result["denied"]["isError"] is True


@pytest.mark.parametrize(
    "damage",
    ["proposal_bytes", "readback_bytes", "orphan", "incomplete_after_registration"],
)
def test_retained_tamper_or_incomplete_registration_blocks_reads_and_new_writes(
    author_run, damage
):
    env, output, binding, _, _ = author_run
    completed = rpc_program(
        env, begin(author_run) + STAGE + PUBLISH + "const result={published,staged};"
    )
    private = output.parent / ".native-workspace"
    if damage == "proposal_bytes":
        (private / completed["staged"]["case_ref"] / "case.json").write_text("{}")
    elif damage == "readback_bytes":
        next(
            private.glob("valuation-case-readback-*/valuation-case-readback.json")
        ).write_text("{}")
    elif damage == "orphan":
        (private / ("valuation-authored-" + "0" * 64)).mkdir()
    else:
        request_path = next(
            p
            for p in private.glob("valuation-author-request-*.json")
            if json.loads(p.read_bytes()).get("result", {}).get("status")
            == "authored_case_registered"
        )
        request = json.loads(request_path.read_bytes())
        request.pop("result")
        request_path.write_text(json.dumps(request))
    result = rpc_program(
        env,
        f"const result=call('vera_workspace_valuation_author_setup',{{work_ref:{json.dumps(binding['work_ref'])}}});",
    )
    if damage in {"orphan", "incomplete_after_registration"}:
        assert result["_meta"]["workspace"]["can_write"] is False
    else:
        assert result["isError"] is True
    ledger = _load_customer_ledger()
    assert (
        len(ledger.list_runs(Path(binding["client_root"]), binding["engagement_id"]))
        == 2
    )


def test_open_model_mandate_blocks_archive_closure(author_run):
    env, _, binding, _, _ = author_run
    exact = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        env,
        begin(author_run)
        + f"const result=call('vera_workspace_archive_closure',{json.dumps(exact)});",
    )
    assert result["isError"] is True
    assert (
        "named case readback or explicit cancellation" in result["content"][0]["text"]
    )


def test_unsigned_authoring_request_is_refused_before_any_grant(author_run):
    env, _, binding, _, _ = author_run
    result = rpc_program(
        env,
        f"""
const work={{work_ref:{json.dumps(binding['work_ref'])}}};
const setup=payload(call('vera_workspace_valuation_author_setup',work));
const refused=call('vera_workspace_valuation_author_request',{{...work,revision:setup.revision,review_ticket:'forged',expected_draft_revision:setup.draft_revision,fields:setup.draft,confirmed:true,idempotency_key:'forged-request'}});
const result={{refused,current:payload(call('vera_workspace_valuation_author_setup',work))}};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["current"]["grants"] == []


from tests.plugins.test_vera_native_valuation_review import (  # noqa: E402,F401
    COMMIT as REVIEW_COMMIT,
)
from tests.plugins.test_vera_native_valuation_review import begin as review_begin
from tests.plugins.test_vera_native_valuation_review import (
    review_run,
)


@pytest.fixture
def correction_run(review_run):
    env, _, binding, _ = review_run
    committed = rpc_program(
        env, review_begin(review_run) + REVIEW_COMMIT + "const result=committed;"
    )
    ledger = _load_customer_ledger()
    loaded = ledger.load_run(
        Path(binding["client_root"]), binding["engagement_id"], committed["run_id"]
    )
    rows = loaded["input_manifest"]["inputs"]
    case_row = next(r for r in rows if r["binding_id"] == committed["case_input_id"])
    case = json.loads(
        (Path(loaded["run_root"]) / case_row["execution_relative_path"]).read_bytes()
    )
    by_path = {
        Path(r["execution_relative_path"])
        .relative_to("inputs")
        .as_posix(): r["binding_id"]
        for r in rows
    }
    proposal = {
        "case": case,
        "source_bindings": {r["id"]: by_path[r["path"]] for r in case["sources"]},
        "note": "Corrected fictional mandate; retain the previous actual method review.",
    }
    return (
        env,
        Path(loaded["output_dir"]),
        {**binding, "run_id": committed["run_id"], "work_ref": committed["work_ref"]},
        proposal,
        committed["case_input_id"],
    )


def test_whole_case_correction_keeps_actual_raw_review_and_publicly_expires_dependencies(
    correction_run,
):
    env, _, binding, proposal, _ = correction_run
    original_review = proposal["case"]["methods"][0]["review"]
    result = rpc_program(
        env,
        begin(correction_run, base=True)
        + "proposal.case.mandate_details.commissioning_party.value='Actual fictional correction of commissioning party';proposal.case.methods[0].review=null;"
        + STAGE
        + PUBLISH
        + """
const intake=payload(call('vera_workspace_valuation_setup',{work_ref:published.work_ref}));
const casePage=payload(call('vera_workspace_valuation_case',{work_ref:published.work_ref,revision:intake.revision,case_input_id:published.case_input_id}));
const calculated=payload(call('vera_workspace_valuation_prepare',{work_ref:published.work_ref,revision:casePage.revision,review_ticket:casePage.review_ticket,item_id:published.case_input_id,case_input_id:published.case_input_id,confirmed:true,idempotency_key:'corrected-separate-calculation'}));
const methods=payload(call('vera_workspace_valuation_read',{work_ref:published.work_ref,source_ref:calculated.source_ref,collection:'methods'}));
const result={casePage,methods};
""",
    )
    assert result["casePage"]["case"]["methods"][0]["review"] == original_review
    assert result["methods"]["rows"][0]["stale_review"] is True
    assert result["methods"]["rows"][0]["status"] == "ready_for_professional_review"
    assert (
        len(
            _load_customer_ledger().list_runs(
                Path(binding["client_root"]), binding["engagement_id"]
            )
        )
        == 3
    )


@pytest.mark.parametrize("change", ["remove_reviewed_record", "invent_attribution"])
def test_correction_refuses_deleted_review_record_or_model_forged_attribution(
    correction_run, change
):
    env, _, _, _, _ = correction_run
    alteration = (
        "proposal.case.methods.shift();"
        if change == "remove_reviewed_record"
        else "proposal.case.methods[0].review.reviewer='Model invented name';"
    )
    result = rpc_program(
        env,
        begin(correction_run, base=True)
        + alteration
        + "const result=call('vera_workspace_valuation_author_stage',{...identity,revision:first.revision,proposal,idempotency_key:'bad-correction'});",
    )
    assert result["isError"] is True
    assert "review" in result["content"][0]["text"]


@pytest.mark.parametrize("scope_change", ["owner", "inputs", "implementation"])
def test_author_intake_never_exposes_mandates_from_changed_authorized_scope(
    author_run, scope_change
):
    env, output, binding, _, _ = author_run
    rpc_program(env, begin(author_run) + "const result=requested;")
    state_path = output.parent / ".native-workspace" / "valuation-author-state.json"
    state = json.loads(state_path.read_bytes())
    mandate = state["grants"][0]["mandate"]
    if scope_change == "owner":
        mandate["scope"]["owner"][0] = "another-operator"
    elif scope_change == "inputs":
        mandate["scope"]["inputs"]["inputs"] = []
    else:
        mandate["scope"]["implementation"] = {}
    import hashlib

    state["grants"][0]["grant_ref"] = (
        "valuation-mandate-"
        + hashlib.sha256(
            json.dumps(mandate, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    )
    state_path.write_text(json.dumps(state))
    result = rpc_program(
        env,
        f"const result=call('vera_workspace_valuation_author_setup',{{work_ref:{json.dumps(binding['work_ref'])}}});",
    )
    assert result["isError"] is True
    assert "another owner, inputs or implementation" in result["content"][0]["text"]
