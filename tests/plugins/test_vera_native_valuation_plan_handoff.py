"""Actual finalized plan lineage survives native valuation authoring and review."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_business_valuation import ROOT, planning_case
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import archive_cli
from tests.plugins.test_vera_native_business_planning import PREPARE as PLAN_PREPARE
from tests.plugins.test_vera_native_valuation_authoring import PUBLISH, STAGE, begin
from tests.plugins.test_vera_native_valuation_review import CALCULATE, COMMIT
from tests.plugins.test_vera_native_valuation_review import begin as begin_review
from tests.plugins.test_vera_native_workspace import configure

__all__ = []


def retained_files(root: Path) -> dict[str, str]:
    """Snapshot exact bytes recursively, including nested native generations."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture
def plan_author_run(tmp_path, monkeypatch):
    """Use actual native planning, public sealing and hydrated upstream receipts."""
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    loose = tmp_path / "loose-fixture"
    loose.mkdir()
    case = planning_case(loose)
    plan_case = json.loads((loose / "plan.json").read_bytes())["case"]
    ledger = _load_customer_ledger()
    client = tmp_path / "Studio" / "Synthetic linked client"
    client.mkdir(parents=True)
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client, client_id)
    engagement_id = ledger.create_engagement(
        client, client_id, "Fictional plan and valuation mandate"
    )["engagement_id"]
    sources = {}
    for row in plan_case["sources"]:
        receipt = ledger.import_document(
            client,
            client_id,
            engagement_id,
            ROOT / "tests/fixtures/business_planning" / row["path"],
            "source",
        )["receipt"]
        sources[row["id"]] = receipt["input_id"]
        row["path"] = f"imports/{receipt['input_id']}/{receipt['imported_names'][0]}"
    authored = tmp_path / "planning-cycle.json"
    authored.write_text(json.dumps(plan_case))
    plan_case_id = ledger.import_document(
        client, client_id, engagement_id, authored, "source"
    )["receipt"]["input_id"]
    planned = ledger.prepare_run(
        client,
        client_id,
        engagement_id,
        "business-planning",
        "development",
        input_ids=[*sources.values(), plan_case_id],
    )
    plan_run_id = planned["run"]["run_id"]
    planned = ledger.start_run(client, engagement_id, plan_run_id)
    plan_binding = {
        "work_ref": "planning-cycle",
        "client_root": str(client),
        "client_id": client_id,
        "engagement_id": engagement_id,
        "run_id": plan_run_id,
        "workflow_id": "business-planning",
    }
    env = configure(monkeypatch, tmp_path, [plan_binding])
    prepared = rpc_program(env, PLAN_PREPARE + "const result=prepared;")
    assert prepared["status"] == "ready_for_professional_review"
    output = Path(planned["output_dir"])
    declarations = write_no_model_report(output, "business-planning", plan_run_id)
    for index, path in enumerate(sorted(output.rglob("*"))):
        if path.is_file() and path.parent != output:
            declarations.append(
                {
                    "artifact_id": (
                        "planning.workpaper"
                        if path.name == "business_plan.json"
                        else f"planning.file_{index}"
                    ),
                    "path": path.relative_to(output).as_posix(),
                    "purpose": "Retain exact fictional native planning output.",
                    "audience": "review",
                    "media_type": mimetypes.guess_type(path)[0]
                    or "application/octet-stream",
                }
            )
    ledger.finalize_run(client, engagement_id, plan_run_id, declarations)
    evidence_id = ledger.import_document(
        client, client_id, engagement_id, loose / "evidence.txt", "source"
    )["receipt"]["input_id"]
    valued = ledger.prepare_run(
        client,
        client_id,
        engagement_id,
        "business-valuation",
        "development",
        input_ids=[evidence_id, *sources.values()],
        upstream_artifacts=[
            {
                "run_id": plan_run_id,
                "artifact_id": "planning.workpaper",
                "role": "source",
            }
        ],
    )
    valued = ledger.start_run(client, engagement_id, valued["run"]["run_id"])
    context = valued["context"]
    binding = {
        **plan_binding,
        **{k: context[k] for k in ("run_id", "workflow_id")},
        "work_ref": "studio-"
        + "_".join(
            context[k].split("_", 1)[1]
            for k in ("client_id", "engagement_id", "run_id")
        ),
    }
    plan_id = f"artifact:{plan_run_id}:planning.workpaper"
    source_bindings = {
        "evidence": evidence_id,
        "plan": plan_id,
        **{f"plan-{key}": value for key, value in sources.items()},
    }
    receipts = {r["binding_id"]: r for r in context["input_bindings"]}
    for row in case["sources"]:
        receipt = receipts[source_bindings[row["id"]]]
        row["path"] = (
            Path(receipt["path"])
            .relative_to(Path(context["run_root"]) / "inputs")
            .as_posix()
        )
        row["sha256"] = receipt["sha256"]
    env.update(
        VERA_STUDIO_ARCHIVE_SESSION_ID="fictional-plan-valuation-handoff",
        VERA_STUDIO_ARCHIVE_STATE_DIR=str(tmp_path / "private-state"),
    )
    archive_cli(env, "configure", "--archive-root", str(client.parent))
    env.pop("VERA_WORKSPACE_BINDINGS")
    fixture = (
        env,
        Path(valued["output_dir"]),
        binding,
        {
            "case": case,
            "source_bindings": source_bindings,
            "note": "Explicit finalized same-engagement plan and all original receipts.",
        },
        "",
    )
    return fixture, output, plan_run_id


CALCULATE_AUTHORED = """
const setupCalculated=payload(call('vera_workspace_valuation_setup',{work_ref:published.work_ref}));
const selectedCalculated=payload(call('vera_workspace_valuation_case',{work_ref:published.work_ref,revision:setupCalculated.revision,case_input_id:published.case_input_id}));
const calculated=payload(call('vera_workspace_valuation_prepare',{work_ref:published.work_ref,revision:selectedCalculated.revision,review_ticket:selectedCalculated.review_ticket,item_id:published.case_input_id,case_input_id:published.case_input_id,confirmed:true,idempotency_key:'linked-plan-calculation'}));
"""


def test_native_finalized_plan_survives_named_case_successor_and_public_replay(
    plan_author_run,
):
    fixture, plan_output, plan_run_id = plan_author_run
    env, intake_output, binding, _, _ = fixture
    before = retained_files(plan_output)

    result = rpc_program(
        env,
        begin(fixture)
        + STAGE
        + PUBLISH
        + CALCULATE_AUTHORED
        + "const result={published,calculated,files:payload(call('vera_workspace_valuation_outputs',{work_ref:published.work_ref,source_ref:calculated.source_ref}))};",
    )

    ledger = _load_customer_ledger()
    successor = ledger.load_run(
        Path(binding["client_root"]),
        binding["engagement_id"],
        result["published"]["run_id"],
    )
    retained = json.loads(
        (
            Path(successor["output_dir"])
            / result["calculated"]["source_ref"]
            / "valuation.json"
        ).read_bytes()
    )
    upstream = next(
        r
        for r in successor["input_manifest"]["inputs"]
        if r["kind"] == "upstream_artifact"
    )
    assert upstream["upstream_run_id"] == plan_run_id
    assert upstream["upstream_artifact_id"] == "planning.workpaper"
    assert upstream["upstream_workflow_id"] == "business-planning"
    assert retained["plan_bridge"]["annual"][0]["fcff"] == "-1200"
    assert len(retained["plan_bridge"]["monthly"]) == 12
    assert (
        retained["plan_bridge"]["monthly"][0]["plan_calculation_ids"][0]
        == "base/2027-01/ebit"
    )
    assert len(result["files"]["outputs"]) == 19
    assert result["calculated"]["status"] == "ready_for_professional_review"
    assert result["published"]["case_calculated"] is False
    assert retained["piv_conformity"] == "not_assessed"
    assert successor["run"]["status"] == "running"
    assert retained_files(plan_output) == before
    assert not list(intake_output.rglob("valuation.json"))


@pytest.fixture
def reviewed_plan(
    plan_author_run,
):
    fixture, plan_output, plan_run_id = plan_author_run
    env, _, binding, _, _ = fixture
    before = retained_files(plan_output)
    initial = rpc_program(
        env,
        begin(fixture)
        + STAGE
        + PUBLISH
        + CALCULATE_AUTHORED
        + "const result={published,calculated};",
    )
    ledger = _load_customer_ledger()
    authored = ledger.load_run(
        Path(binding["client_root"]),
        binding["engagement_id"],
        initial["published"]["run_id"],
    )
    authored_output = Path(authored["output_dir"])
    authored_before = retained_files(authored_output)
    review_fixture = (
        env,
        authored_output,
        {**binding, "work_ref": initial["published"]["work_ref"]},
        initial["calculated"],
    )

    result = rpc_program(
        env,
        begin_review(review_fixture)
        + COMMIT
        + CALCULATE
        + "const result={committed,calculated,rows:payload(call('vera_workspace_valuation_read',{work_ref:committed.work_ref,source_ref:calculated.source_ref,collection:'methods'}))};",
    )

    reviewed = ledger.load_run(
        Path(binding["client_root"]),
        binding["engagement_id"],
        result["committed"]["run_id"],
    )
    return (
        fixture,
        plan_output,
        plan_run_id,
        before,
        authored_output,
        authored_before,
        result,
        reviewed,
    )


def test_native_plan_dependent_named_method_review_keeps_exact_upstream(reviewed_plan):
    (
        _,
        plan_output,
        plan_run_id,
        before,
        authored_output,
        authored_before,
        result,
        reviewed,
    ) = reviewed_plan
    assert result["rows"]["rows"][0]["status"] == "accepted_workpaper"
    assert (
        result["rows"]["rows"][0]["review"]["reviewer"]
        == "Fictional declared professional"
    )
    assert (
        next(
            r
            for r in reviewed["input_manifest"]["inputs"]
            if r["kind"] == "upstream_artifact"
        )["upstream_run_id"]
        == plan_run_id
    )
    assert retained_files(plan_output) == before
    assert retained_files(authored_output) == authored_before


def test_native_linked_plan_correction_retains_raw_review_and_expires_acceptance(
    reviewed_plan,
):
    fixture, plan_output, plan_run_id, before, _, _, prior, loaded = reviewed_plan
    env, _, binding, _, _ = fixture
    rows = loaded["input_manifest"]["inputs"]
    case_id = prior["committed"]["case_input_id"]
    case_row = next(r for r in rows if r["binding_id"] == case_id)
    case = json.loads(
        (Path(loaded["run_root"]) / case_row["execution_relative_path"]).read_bytes()
    )
    by_path = {
        Path(r["execution_relative_path"])
        .relative_to("inputs")
        .as_posix(): r["binding_id"]
        for r in rows
    }
    predecessor = Path(loaded["output_dir"])
    predecessor_bytes = retained_files(predecessor)
    raw_review = case["methods"][0]["review"]
    correction = (
        env,
        predecessor,
        {
            **binding,
            "run_id": prior["committed"]["run_id"],
            "work_ref": prior["committed"]["work_ref"],
        },
        {
            "case": case,
            "source_bindings": {r["id"]: by_path[r["path"]] for r in case["sources"]},
            "note": "Explicit fictional correction retaining exact plan lineage and raw prior review.",
        },
        case_id,
    )

    result = rpc_program(
        env,
        begin(correction, base=True)
        + "proposal.case.mandate_details.commissioning_party.value='Changed fictional commissioning party';proposal.case.methods[0].review=null;"
        + STAGE
        + PUBLISH
        + CALCULATE_AUTHORED
        + "const result={published,calculated,rows:payload(call('vera_workspace_valuation_read',{work_ref:published.work_ref,source_ref:calculated.source_ref,collection:'methods'}))};",
    )

    successor = _load_customer_ledger().load_run(
        Path(binding["client_root"]),
        binding["engagement_id"],
        result["published"]["run_id"],
    )
    report = json.loads(
        (
            Path(successor["output_dir"])
            / result["calculated"]["source_ref"]
            / "valuation.json"
        ).read_bytes()
    )
    assert report["case"]["methods"][0]["review"] == raw_review
    assert result["rows"]["rows"][0]["stale_review"] is True
    assert result["rows"]["rows"][0]["status"] == "ready_for_professional_review"
    assert report["plan_bridge"]["annual"][0]["fcff"] == "-1200"
    assert (
        next(
            r
            for r in successor["input_manifest"]["inputs"]
            if r["kind"] == "upstream_artifact"
        )["upstream_run_id"]
        == plan_run_id
    )
    assert retained_files(predecessor) == predecessor_bytes
    assert retained_files(plan_output) == before


@pytest.mark.parametrize(
    "change,message",
    [
        (
            "delete proposal.case.plan_binding.cash_operating_taxes['2027-01'];",
            "every month",
        ),
        ("proposal.case.inputs[0].value='-1190';", "differs from replayed"),
        (
            "delete proposal.case.plan_binding.source_map[Object.keys(proposal.case.plan_binding.source_map)[0]];",
            "Map every original",
        ),
        (
            "const originalPlan=proposal.source_bindings.plan;proposal.source_bindings.plan=proposal.source_bindings.evidence;proposal.source_bindings.evidence=originalPlan;",
            "finalized same-engagement",
        ),
    ],
)
def test_native_linked_plan_refuses_incomplete_or_substituted_proposal(
    plan_author_run,
    change,
    message,
):
    fixture, plan_output, _ = plan_author_run
    env, output, binding, _, _ = fixture
    before = retained_files(plan_output)

    result = rpc_program(
        env,
        begin(fixture)
        + change
        + "const result=call('vera_workspace_valuation_author_stage',{...identity,revision:first.revision,proposal,idempotency_key:'invalid-plan-proposal'});",
    )

    ledger = _load_customer_ledger()
    assert result["isError"] is True
    assert message in result["content"][0]["text"]
    assert (
        len(ledger.list_runs(Path(binding["client_root"]), binding["engagement_id"]))
        == 2
    )
    assert not list(output.rglob("valuation.json"))
    assert retained_files(plan_output) == before
