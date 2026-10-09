"""Actual named decisions preserve predecessor files and create public successors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import archive_cli
from tests.plugins.test_vera_native_valuation import (  # noqa: F401
    PREPARE,
    valuation_run,
)

__all__ = []


@pytest.fixture
def review_run(valuation_run):
    env, output, binding = valuation_run
    env = {
        **env,
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-financial-archive",
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(
            Path(binding["client_root"]).parent.parent
            / (Path(binding["client_root"]).parent.name + "-review-private-state")
        ),
    }
    archive_cli(
        env, "configure", "--archive-root", str(Path(binding["client_root"]).parent)
    )
    env.pop("VERA_WORKSPACE_BINDINGS")
    ref = "studio-" + "_".join(
        binding[k].split("_", 1)[1] for k in ("client_id", "engagement_id", "run_id")
    )
    prepared = rpc_program(
        env, PREPARE.replace("fictional-valuation", ref) + "const result=prepared;"
    )
    return env, output, {**binding, "work_ref": ref}, prepared


def begin(fixture, collection="methods", index=0):
    _, _, binding, prepared = fixture
    return f"""
const exact={{work_ref:{json.dumps(binding['work_ref'])},source_ref:{json.dumps(prepared['source_ref'])},collection:{json.dumps(collection)},index:{index}}};
const read=()=>payload(call('vera_workspace_valuation_review_read',exact));
const reviewScope=v=>({{...exact,revision:v.revision,review_ticket:v.review_ticket,item_id:v.selection.id,expected_draft_revision:v.draft_revision}});
const first=read();
const fields={{decision:'accepted',reviewer:'Fictional declared professional',reviewed_at:'2026-10-08T00:30:00+02:00',basis:'Actual explicit fictional review of the selected workpaper; no PIV attestation.'}};
"""


COMMIT = """
payload(call('vera_workspace_valuation_review_draft_save',{...reviewScope(first),fields}));
const reviewed=read();
const args={...reviewScope(reviewed),confirmed:true,idempotency_key:'fictional-record-review'};
const committed=payload(call('vera_workspace_valuation_review_commit',args));
const setup=payload(call('vera_workspace_valuation_setup',{work_ref:committed.work_ref}));
const chosen=payload(call('vera_workspace_valuation_case',{work_ref:committed.work_ref,revision:setup.revision,case_input_id:committed.case_input_id}));
"""

CALCULATE = """
const calculated=payload(call('vera_workspace_valuation_prepare',{work_ref:committed.work_ref,revision:chosen.revision,review_ticket:chosen.review_ticket,item_id:committed.case_input_id,case_input_id:committed.case_input_id,confirmed:true,idempotency_key:'separate-successor-calculation'}));
"""


@pytest.mark.parametrize(
    "valuation_run,collection",
    [
        ("ready", "methods"),
        ("ready", "mandate_assessment"),
        ("normalized", "normalization_adjustments"),
        ("statement", "statements"),
    ],
    indirect=["valuation_run"],
)
def test_named_public_record_review_registers_new_case_and_separate_calculation(
    review_run, collection
):
    env, output, binding, prepared = review_run
    prior = {
        p.name: p.read_bytes() for p in (output / prepared["source_ref"]).iterdir()
    }
    result = rpc_program(
        env,
        begin(review_run, collection)
        + COMMIT
        + CALCULATE
        + "const persisted=payload(call('vera_workspace_valuation_read',{work_ref:committed.work_ref,source_ref:calculated.source_ref,collection:exact.collection}));const result={committed,chosen,calculated,persisted,retry:payload(call('vera_workspace_valuation_review_commit',args))};",
    )
    assert result["committed"] == result["retry"]
    assert result["committed"]["case_calculated"] is False
    from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger

    ledger = _load_customer_ledger()
    runs = ledger.list_runs(Path(binding["client_root"]), binding["engagement_id"])
    assert len(runs) == 2
    successor = next(r for r in runs if r["run"]["run_id"] != binding["run_id"])
    loaded = ledger.load_run(
        Path(binding["client_root"]),
        binding["engagement_id"],
        successor["run"]["run_id"],
    )
    retained = json.loads(
        (
            Path(loaded["output_dir"])
            / result["calculated"]["source_ref"]
            / "valuation.json"
        ).read_bytes()
    )
    assert result["persisted"]["rows"][0]["status"] == "accepted_workpaper"
    assert (
        result["persisted"]["rows"][0]["review"]["reviewer"]
        == "Fictional declared professional"
    )
    assert {
        p.name: p.read_bytes() for p in (output / prepared["source_ref"]).iterdir()
    } == prior
    assert retained["piv_conformity"] == "not_assessed"
    assert loaded["run"]["status"] == "running"


def test_review_draft_recovers_empty_generation_and_refuses_concurrent_update(
    review_run,
):
    env, _, _, _ = review_run
    result = rpc_program(
        env,
        begin(review_run)
        + """
const saved=payload(call('vera_workspace_valuation_review_draft_save',{...reviewScope(first),fields}));
const recovered=read();
const empty={decision:'',reviewer:'',reviewed_at:'',basis:''};
const cleared=payload(call('vera_workspace_valuation_review_draft_save',{...reviewScope(recovered),fields:empty}));
const stale=call('vera_workspace_valuation_review_draft_save',{...reviewScope(first),fields});
const result={saved,recovered,cleared,stale,current:read()};
""",
    )
    assert result["recovered"]["draft"]["reviewer"] == "Fictional declared professional"
    assert result["saved"]["draft_revision"] != result["cleared"]["draft_revision"]
    assert result["stale"]["isError"] is True
    assert result["current"]["draft"] == dict.fromkeys(
        ["decision", "reviewer", "reviewed_at", "basis"], ""
    )


@pytest.mark.parametrize("valuation_run", ["partial", "blocked"], indirect=True)
def test_public_missing_dependencies_refuse_acceptance_without_successor(review_run):
    env, _, binding, _ = review_run
    result = rpc_program(
        env,
        begin(review_run)
        + """
payload(call('vera_workspace_valuation_review_draft_save',{...reviewScope(first),fields}));
const reviewed=read();
const result=call('vera_workspace_valuation_review_commit',{...reviewScope(reviewed),confirmed:true,idempotency_key:'ineligible-review'});
""",
    )
    assert result["isError"] is True
    assert "dependencies" in result["content"][0]["text"]
    from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger

    assert (
        len(
            _load_customer_ledger().list_runs(
                Path(binding["client_root"]), binding["engagement_id"]
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    "change",
    [
        "confirmed:false",
        "item_id:'methods:1'",
        "source_ref:'foreign'",
        "revision:'stale'",
    ],
)
def test_review_commit_requires_exact_record_and_renewed_confirmation(
    review_run, change
):
    env, _, _, _ = review_run
    result = rpc_program(
        env,
        begin(review_run)
        + """
payload(call('vera_workspace_valuation_review_draft_save',{...reviewScope(first),fields}));
const reviewed=read();
"""
        + f"const result=call('vera_workspace_valuation_review_commit',{{...reviewScope(reviewed),confirmed:true,idempotency_key:'invalid-review',{change}}});",
    )
    assert result["isError"] is True


def test_viewer_can_read_decision_but_cannot_conserve_draft(review_run):
    env, _, _, _ = review_run
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": "VIEWER"},
        begin(review_run)
        + "const result={first,write:call('vera_workspace_valuation_review_draft_save',{...reviewScope(first),fields})};",
    )
    assert result["first"]["can_write"] is False
    assert result["write"]["isError"] is True


CHAIN = """
function decide(work,source,collection,index,key,decision='accepted') {
 const exact={work_ref:work,source_ref:source,collection,index};
 const read=()=>payload(call('vera_workspace_valuation_review_read',exact));
 const current=read();
 const authority=v=>({...exact,revision:v.revision,review_ticket:v.review_ticket,item_id:v.selection.id,expected_draft_revision:v.draft_revision});
 const fields={decision,reviewer:'Fictional chain reviewer',reviewed_at:'2026-10-08T01:00:00+02:00',basis:'Explicit separate fictional decision for '+collection+':'+index};
 payload(call('vera_workspace_valuation_review_draft_save',{...authority(current),fields}));
 const commit=payload(call('vera_workspace_valuation_review_commit',{...authority(read()),confirmed:true,idempotency_key:key}));
 const setup=payload(call('vera_workspace_valuation_setup',{work_ref:commit.work_ref}));
 const chosen=payload(call('vera_workspace_valuation_case',{work_ref:commit.work_ref,revision:setup.revision,case_input_id:commit.case_input_id}));
 const calculated=payload(call('vera_workspace_valuation_prepare',{work_ref:commit.work_ref,revision:chosen.revision,review_ticket:chosen.review_ticket,item_id:commit.case_input_id,case_input_id:commit.case_input_id,confirmed:true,idempotency_key:'calculate-'+key}));
 const inspected=payload(call('vera_workspace_valuation_read',{work_ref:commit.work_ref,source_ref:calculated.source_ref,collection}));
 return {commit,calculated,inspected};
}
"""


@pytest.mark.parametrize("valuation_run", ["conclusion"], indirect=True)
def test_native_review_chain_preserves_prior_attributions_and_requires_separate_conclusion(
    review_run,
):
    env, output, binding, prepared = review_run
    prior = {
        p.name: p.read_bytes() for p in (output / prepared["source_ref"]).iterdir()
    }
    result = rpc_program(
        env,
        CHAIN
        + f"""
const mandate=decide({json.dumps(binding['work_ref'])},{json.dumps(prepared['source_ref'])},'mandate_assessment',0,'mandate');
const method=decide(mandate.commit.work_ref,mandate.calculated.source_ref,'methods',0,'method');
const claim=decide(method.commit.work_ref,method.calculated.source_ref,'claims',0,'claim');
const before=payload(call('vera_workspace_valuation_read',{{work_ref:claim.commit.work_ref,source_ref:claim.calculated.source_ref,collection:'conclusion'}}));
const conclusion=decide(claim.commit.work_ref,claim.calculated.source_ref,'conclusion',0,'conclusion');
const finalMandate=payload(call('vera_workspace_valuation_read',{{work_ref:conclusion.commit.work_ref,source_ref:conclusion.calculated.source_ref,collection:'mandate_assessment'}}));
const finalMethod=payload(call('vera_workspace_valuation_read',{{work_ref:conclusion.commit.work_ref,source_ref:conclusion.calculated.source_ref,collection:'methods'}}));
const finalClaim=payload(call('vera_workspace_valuation_read',{{work_ref:conclusion.commit.work_ref,source_ref:conclusion.calculated.source_ref,collection:'claims'}}));
const result={{mandate,method,claim,before,conclusion,finalMandate,finalMethod,finalClaim}};
""",
    )
    assert result["before"]["rows"][0]["status"] == "draft"
    assert (
        result["conclusion"]["inspected"]["rows"][0]["status"] == "accepted_workpaper"
    )
    assert result["finalMandate"]["rows"][0]["status"] == "accepted_workpaper"
    assert result["finalMethod"]["rows"][0]["status"] == "accepted_workpaper"
    assert result["finalClaim"]["rows"][0]["status"] == "accepted_workpaper"
    assert (
        result["finalClaim"]["rows"][0]["review"]["reviewer"]
        == "Fictional chain reviewer"
    )
    assert {
        p.name: p.read_bytes() for p in (output / prepared["source_ref"]).iterdir()
    } == prior
    from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger

    assert (
        len(
            _load_customer_ledger().list_runs(
                Path(binding["client_root"]), binding["engagement_id"]
            )
        )
        == 5
    )


@pytest.mark.parametrize("valuation_run", ["partial", "blocked"], indirect=True)
@pytest.mark.parametrize("decision", ["rejected", "changes_requested"])
def test_ineligible_workpapers_retain_refusal_and_request_changes_without_acceptance(
    review_run, decision
):
    env, _, _, _ = review_run
    result = rpc_program(
        env,
        begin(review_run)
        + f"fields.decision={json.dumps(decision)};"
        + COMMIT
        + CALCULATE
        + "const result={committed,readback:payload(call('vera_workspace_valuation_review_read',{work_ref:committed.work_ref,source_ref:calculated.source_ref,collection:'methods',index:0}))};",
    )
    assert result["readback"]["declared_review"]["decision"] == decision
    assert (
        result["readback"]["declared_review"]["reviewer"]
        == "Fictional declared professional"
    )
    assert result["readback"]["record"]["status"] != "accepted_workpaper"


@pytest.mark.parametrize(
    "change",
    ["reviewer:''", "basis:''", "reviewed_at:''", "reviewed_at:'2026-10-08T01:00:00'"],
)
def test_final_decision_requires_literal_attribution_and_actual_timezone(
    review_run, change
):
    env, _, _, _ = review_run
    result = rpc_program(
        env,
        begin(review_run)
        + f"Object.assign(fields,{{{change}}});"
        + """
payload(call('vera_workspace_valuation_review_draft_save',{...reviewScope(first),fields}));
const result=call('vera_workspace_valuation_review_commit',{...reviewScope(read()),confirmed:true,idempotency_key:'missing-attribution'});
""",
    )
    assert result["isError"] is True


def test_interrupted_review_retains_new_run_but_blocks_retry_and_closure(
    review_run, monkeypatch
):
    from tests.plugins.test_vera_native_workspace import workspace_module

    env, output, binding, _ = review_run
    saved = rpc_program(
        env,
        begin(review_run)
        + """
payload(call('vera_workspace_valuation_review_draft_save',{...reviewScope(first),fields}));
const result={...reviewScope(read()),confirmed:true,idempotency_key:'interrupted-attributed-review'};
""",
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("VERA_WORKSPACE_BINDINGS", raising=False)
    api = workspace_module()
    atomic = api.atomic_json

    def fail_receipt(path, value):
        if path.name.startswith("valuation-review-request-") and "result" in value:
            raise OSError("fictional interrupted review receipt")
        return atomic(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(api, "atomic_json", fail_receipt)
        with pytest.raises(OSError, match="interrupted review"):
            api.dispatch("vera_workspace_valuation_review_commit", saved)
    from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger

    assert (
        len(
            _load_customer_ledger().list_runs(
                Path(binding["client_root"]), binding["engagement_id"]
            )
        )
        == 2
    )
    with pytest.raises(ValueError, match="Recover|recovery"):
        api.dispatch("vera_workspace_valuation_review_commit", saved)
    with pytest.raises(ValueError, match="Recover|recovery"):
        api.dispatch(
            "vera_workspace_archive_closure",
            {k: binding[k] for k in ("client_id", "engagement_id", "run_id")},
        )
    private = api.ui_state_directory(output, create=False)
    receipt = json.loads(
        next(private.glob("valuation-review-request-*.json")).read_bytes()
    )
    assert "result" not in receipt


def test_orphaned_retained_case_requires_recovery(review_run):
    from tests.plugins.test_vera_native_workspace import workspace_module

    env, output, binding, _ = review_run
    private = workspace_module().ui_state_directory(output, create=False)
    (private / "valuation-reviewed-case-orphan.json").write_text("{}")
    result = rpc_program(
        env,
        f"const result=payload(call('vera_workspace_valuation_setup',{{work_ref:{json.dumps(binding['work_ref'])}}}));",
    )
    assert result["status"] == "recovery_required"
    assert result["can_prepare"] is False


def test_owned_archive_catalogue_offers_valuation_for_predecessor_and_successor(
    review_run,
):
    env, _, binding, _ = review_run
    selected = {k: binding[k] for k in ("client_id", "engagement_id")}
    result = rpc_program(
        env,
        begin(review_run)
        + COMMIT
        + f"const result=payload(call('vera_workspace_open',{json.dumps(selected)}));",
    )
    assert len(result["works"]) == 2
    assert result["works"][0]["setup_available"] is True
    assert result["works"][1]["setup_available"] is True


def test_review_tool_contract_allows_unfinished_literal_fields_and_full_basis(
    review_run,
):
    env, _, _, _ = review_run
    result = rpc_program(
        env,
        "const result=service.handle({jsonrpc:'2.0',id:1,method:'tools/list'}).result.tools.find(t=>t.name==='vera_workspace_valuation_review_draft_save');",
    )
    fields = result["inputSchema"]["properties"]["fields"]["properties"]
    assert fields["reviewer"].get("minLength", 0) == 0
    assert fields["reviewed_at"].get("minLength", 0) == 0
    assert fields["basis"].get("minLength", 0) == 0
    assert fields["basis"]["maxLength"] == 4000
    assert result["_meta"]["ui"]["visibility"] == ["app"]


@pytest.mark.parametrize("tamper", ["case_bytes", "receipt_path"])
def test_retained_review_case_and_exact_receipt_path_are_verified_before_consultation(
    review_run, tamper
):
    from tests.plugins.test_vera_native_workspace import workspace_module

    env, output, binding, _ = review_run
    rpc_program(env, begin(review_run) + COMMIT + "const result=committed;")
    private = workspace_module().ui_state_directory(output, create=False)
    receipt = next(private.glob("valuation-review-request-*.json"))
    record = json.loads(receipt.read_bytes())
    if tamper == "case_bytes":
        Path(record["case_path"]).write_text("{}")
    else:
        record["case_path"] = str(output / "foreign-case.json")
        receipt.write_text(json.dumps(record))
    result = rpc_program(
        env,
        f"const result=call('vera_workspace_valuation_setup',{{work_ref:{json.dumps(binding['work_ref'])}}});",
    )
    assert result["isError"] is True
    assert "case" in result["content"][0]["text"].lower()
