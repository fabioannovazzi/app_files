"""Actual Sales Plan executions through registered inputs and signed native MCP."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import ROOT, configure, workspace_module


@pytest.fixture
def initial_plan(tmp_path, monkeypatch, request):
    """Import a fictional reviewed case and exact Actuals into a real running ledger."""
    ledger = _load_customer_ledger()
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    folder = tmp_path / "Fictional Sales Plan customer"
    folder.mkdir()
    client = "client_111111111111111111111111"
    ledger.create_client_manifest(folder, client)
    engagement = ledger.create_engagement(folder, client, "Fictional Sales Plan")
    source = ROOT / "plugins/sales-plan/evals/synthetic"
    case = json.loads((source / "case.json").read_bytes())
    variant = getattr(request, "param", "valid")
    if variant == "failed_scope":
        case["reviewed_assumptions"]["assumptions"][0]["scope"]["country"] = [
            "Unobserved"
        ]
    elif variant == "stale_source":
        case["files"]["actual_sales"]["sha256"] = "0" * 64
    elif variant == "unreviewed":
        case["reviewed_assumptions"]["status"] = "proposed"
    elif variant == "invalid_locator":
        case["files"]["actual_sales"]["path"] = "../foreign.csv"
    actual_path = source / "actual_sales.csv"
    if variant in {"actual_only_large", "actual_only_large_wide"}:
        with actual_path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames
            rows = list(reader)
        actual_path = tmp_path / "large-actual.csv"
        with actual_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
            writer.writerows(
                {
                    **rows[0],
                    "source_row_id": f"extra-{index}",
                    "country": f"Member{index:02}"
                    + ("x" * 2600 if variant == "actual_only_large_wide" else ""),
                }
                for index in range(41)
            )
    reviewed = tmp_path / "reviewed-case.json"
    reviewed.write_text(json.dumps(case))
    imported = [
        ledger.import_document(
            folder,
            client,
            engagement["engagement_id"],
            path,
            "support" if path.suffix == ".json" else "source",
        )["receipt"]["input_id"]
        for path in (reviewed, actual_path)
    ]
    if variant in {"actual_only", "actual_only_large", "actual_only_large_wide"}:
        imported = imported[1:]
    if variant == "two_cases":
        case["reviewed_assumptions"]["assumptions"][0]["change_pct"] = "12"
        second = tmp_path / "alternative-case.json"
        second.write_text(json.dumps(case))
        imported.append(
            ledger.import_document(
                folder, client, engagement["engagement_id"], second, "support"
            )["receipt"]["input_id"]
        )
    if variant == "same_bytes_distinct_receipts":
        # Imports deduplicate identical bytes. Distinct, legitimate upstream
        # artifact receipts exercise the exact-identity boundary instead.
        upstream = ledger.prepare_run(
            folder,
            client,
            engagement["engagement_id"],
            "client-file-preparation",
            "test-version",
            input_ids=imported,
        )
        started = ledger.start_run(
            folder, engagement["engagement_id"], upstream["run"]["run_id"]
        )
        upstream_output = Path(started["output_dir"])
        declarations = write_no_model_report(
            upstream_output, "client-file-preparation", upstream["run"]["run_id"]
        )
        for artifact_id, name, original in [
            ("case.first", "first-case.json", reviewed),
            ("case.second", "second-case.json", reviewed),
            ("actual", "actual.csv", source / "actual_sales.csv"),
        ]:
            (upstream_output / name).write_bytes(original.read_bytes())
            declarations.append(
                {
                    "artifact_id": artifact_id,
                    "path": name,
                    "purpose": "Fictional exact receipt identity",
                    "audience": "internal",
                    "media_type": (
                        "application/json" if name.endswith("json") else "text/csv"
                    ),
                }
            )
        ledger.finalize_run(
            folder, engagement["engagement_id"], upstream["run"]["run_id"], declarations
        )
        prepared = ledger.prepare_run(
            folder,
            client,
            engagement["engagement_id"],
            "sales-plan",
            "test-version",
            upstream_artifacts=[
                {
                    "run_id": upstream["run"]["run_id"],
                    "artifact_id": identity,
                    "role": "support" if identity.startswith("case") else "source",
                }
                for identity in ["case.first", "actual", "case.second"]
            ],
        )
    else:
        prepared = ledger.prepare_run(
            folder,
            client,
            engagement["engagement_id"],
            "sales-plan",
            "test-version",
            input_ids=imported,
        )
    running = ledger.start_run(
        folder, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    binding = {
        "work_ref": "initial-plan",
        "client_root": str(folder),
        "client_id": client,
        "engagement_id": engagement["engagement_id"],
        "run_id": prepared["run"]["run_id"],
        "workflow_id": "sales-plan",
    }
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    return env, Path(running["output_dir"]), binding


SETUP = """
const initial=payload(call('vera_workspace_sales_plan_setup',{work_ref:'initial-plan'}));
const selected={work_ref:initial.work_ref,revision:initial.revision,case_input_id:initial.items.find(x=>x.kind==='.json').id,actual_input_id:initial.items.find(x=>x.kind==='.csv').id};
const args={...selected,review_ticket:initial.review_ticket,human_reviewed:true,idempotency_key:'fictional-plan'};
"""
CALCULATE = (
    SETUP
    + """
const inspected=payload(call('vera_workspace_sales_plan_inspect',selected));
const calculated=payload(call('vera_workspace_sales_plan_calculate',args));
const view=payload(call('vera_workspace_view',{work_ref:'initial-plan',source_ref:calculated.source_ref}));
"""
)


def test_native_plan_runs_complete_engine_and_reopens_without_approval(initial_plan):
    env, output, binding = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + "const retry=payload(call('vera_workspace_sales_plan_calculate',args)); const result={initial,inspected,calculated,view,retry};",
    )
    destination = output / result["calculated"]["source_ref"]
    receipt = json.loads(
        (destination / "plan/plan_execution_receipt.json").read_bytes()
    )
    with (destination / "plan/sales_plan_scenario.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert receipt["status"] == "passed"
    assert receipt["report_ready"] is False
    assert len(rows) == 8
    assert result["retry"] == result["calculated"]
    assert result["calculated"]["professional_approval"] is False
    assert result["view"]["kind"] == "sales"
    assert result["view"]["data"]["local_review_read_only"] is True
    assert all(
        row["group"] != "sales_plan_scenario.csv" for row in result["view"]["items"]
    )
    assert (
        result["inspected"]["case"]["preparation_recipe"]["reporting_currency"] == "EUR"
    )
    module = workspace_module()
    assert module.load_binding(binding)["run"]["status"] == "running"


@pytest.mark.parametrize("initial_plan", ["failed_scope"], indirect=True)
def test_native_plan_retains_failed_reconciliation_and_unapproved_revision(
    initial_plan,
):
    env, output, _ = initial_plan
    result = rpc_program(env, CALCULATE + "const result={calculated,view};")
    assert result["calculated"]["status"] == "failed"
    assert result["view"]["data"]["report_ready"] is False
    assert (
        output / result["calculated"]["source_ref"] / "plan/reconciliation.json"
    ).is_file()


@pytest.mark.parametrize("initial_plan", ["stale_source"], indirect=True)
def test_native_plan_rejects_unmatched_actual_receipt_before_writing(initial_plan):
    env, output, _ = initial_plan
    result = rpc_program(
        env, SETUP + "const result=call('vera_workspace_sales_plan_calculate',args);"
    )
    assert result["isError"] is True
    assert "Actuals differ" in result["content"][0]["text"]
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("initial_plan", ["unreviewed"], indirect=True)
def test_native_plan_preserves_refused_request_and_requires_recovery(initial_plan):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        SETUP
        + "const refused=call('vera_workspace_sales_plan_calculate',args);const after=payload(call('vera_workspace_sales_plan_setup',{work_ref:'initial-plan'}));const retry=call('vera_workspace_sales_plan_calculate',args);const result={refused,after,retry};",
    )
    assert result["refused"]["isError"] is True
    assert result["after"]["status"] == "recovery_required"
    assert result["after"]["can_write"] is False
    assert "recovery" in result["retry"]["content"][0]["text"]
    assert len(list(output.glob("sales-plan-*"))) == 1


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("revision", "0" * 64, "mismatched review ticket"),
        ("review_ticket", "invalid.signature", "Invalid review ticket"),
        ("case_input_id", "foreign-case", "outside this run"),
        ("actual_input_id", "foreign-actual", "outside this run"),
        ("human_reviewed", False, "Invalid human_reviewed"),
    ],
)
def test_native_plan_rejects_invalid_scope_without_output_mutation(
    initial_plan, field, value, error
):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        SETUP
        + f"args[{json.dumps(field)}]={json.dumps(value)};const result=call('vera_workspace_sales_plan_calculate',args);",
    )
    assert result["isError"] is True
    assert error in result["content"][0]["text"]
    assert list(output.iterdir()) == []


def test_native_plan_viewer_cannot_calculate(initial_plan):
    env, output, _ = initial_plan
    env["VERA_WORKSPACE_ROLES"] = "VIEWER"
    result = rpc_program(
        env,
        SETUP
        + "const response=call('vera_workspace_sales_plan_calculate',args);const result={initial,response};",
    )
    assert result["initial"]["can_write"] is False
    assert result["response"]["isError"] is True
    assert list(output.iterdir()) == []


def test_native_plan_request_key_cannot_change_selected_input(initial_plan):
    env, _, _ = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + "args.actual_input_id='foreign';const result=call('vera_workspace_sales_plan_calculate',args);",
    )
    assert result["isError"] is True
    assert "different request" in result["content"][0]["text"]


@pytest.mark.parametrize("tamper", ["changed", "extra", "missing"])
def test_native_plan_rejects_changed_artifact_population(initial_plan, tamper):
    env, output, _ = initial_plan
    result = rpc_program(env, CALCULATE + "const result=calculated;")
    destination = output / result["source_ref"] / "plan"
    if tamper == "changed":
        (destination / "scenario_summary.csv").write_text("modified")
    elif tamper == "extra":
        (destination / "unexpected.txt").write_text("foreign")
    else:
        (destination / "scenario_summary.csv").unlink()
    refused = rpc_program(
        env,
        "const result=call('vera_workspace_view',"
        + json.dumps({"work_ref": "initial-plan", "source_ref": result["source_ref"]})
        + ");",
    )
    assert refused["isError"] is True
    assert "population changed" in refused["content"][0]["text"]


def test_native_plan_explain_reads_selected_prepared_row_and_opaque_app_summary(
    initial_plan,
):
    env, _, _ = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + "const exact=payload(call('vera_workspace_view',{work_ref:'initial-plan',source_ref:calculated.source_ref,item_id:view.items[0].id,revision:view.revision}));const explained=call('vera_workspace_explain',{work_ref:exact.work_ref,source_ref:calculated.source_ref,revision:exact.revision,item_id:exact.selection.id});const summary=call('vera_workspace_sales_plan_setup',{work_ref:'initial-plan'});const result={exact,explained,summary};",
    )
    evidence = result["explained"]["structuredContent"]["untrusted_evidence"]
    assert evidence["selected_record"] == result["exact"]["selection"]
    assert evidence["report_ready"] is False
    assert "original-case.json" not in json.dumps(evidence)
    assert "actual_sales.csv" not in json.dumps(result["summary"]["structuredContent"])
    assert "review_ticket" not in result["summary"]["structuredContent"]


def test_native_plan_unknown_outputs_require_recovery(initial_plan):
    env, output, _ = initial_plan
    (output / ("sales-plan-" + "0" * 64)).mkdir()
    result = rpc_program(
        env,
        SETUP
        + "const refused=call('vera_workspace_sales_plan_calculate',args);const result={initial,refused};",
    )
    assert result["initial"]["status"] == "recovery_required"
    assert result["refused"]["isError"] is True


def test_native_plan_generic_save_cannot_edit_immutable_case(initial_plan):
    _, _, _ = initial_plan
    module = workspace_module()
    with pytest.raises(ValueError, match="immutable confirmed cases"):
        module.dispatch("vera_workspace_save", {"work_ref": "initial-plan"})


@pytest.mark.parametrize("initial_plan", ["two_cases"], indirect=True)
def test_native_plan_preserves_distinct_cases_and_requires_exact_generation(
    initial_plan,
):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + """
const next=payload(call('vera_workspace_sales_plan_setup',{work_ref:'initial-plan'}));
const secondArgs={...args,revision:next.revision,review_ticket:next.review_ticket,case_input_id:next.items.filter(x=>x.kind==='.json')[1].id,idempotency_key:'fictional-alternative'};
const alternative=payload(call('vera_workspace_sales_plan_calculate',secondArgs));
const ambiguous=call('vera_workspace_view',{work_ref:'initial-plan'});
const old=payload(call('vera_workspace_view',{work_ref:'initial-plan',source_ref:calculated.source_ref}));
const result={calculated,alternative,ambiguous,old,view};
""",
    )
    assert result["alternative"]["source_ref"] != result["calculated"]["source_ref"]
    assert result["ambiguous"]["isError"] is True
    assert result["old"]["revision"] == result["view"]["revision"]
    assert len(list(output.glob("sales-plan-*"))) == 2


def test_native_plan_old_setup_cannot_launch_new_execution(initial_plan):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + "args.idempotency_key='another-calculation';const result=call('vera_workspace_sales_plan_calculate',args);",
    )
    assert result["isError"] is True
    assert "Stale Sales Plan setup" in result["content"][0]["text"]
    assert len(list(output.glob("sales-plan-*"))) == 1


@pytest.mark.parametrize("initial_plan", ["invalid_locator"], indirect=True)
def test_native_plan_rejects_invalid_original_locator_before_derivation(initial_plan):
    env, output, _ = initial_plan
    result = rpc_program(
        env, SETUP + "const result=call('vera_workspace_sales_plan_calculate',args);"
    )
    assert result["isError"] is True
    assert "locator must be canonical" in result["content"][0]["text"]
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "initial_plan", ["same_bytes_distinct_receipts"], indirect=True
)
def test_native_plan_same_bytes_keep_the_selected_receipt_identity(initial_plan):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + """
const next=payload(call('vera_workspace_sales_plan_setup',{work_ref:'initial-plan'}));
const secondArgs={...args,revision:next.revision,review_ticket:next.review_ticket,case_input_id:next.items.filter(x=>x.kind==='.json')[1].id,idempotency_key:'fictional-same-bytes'};
const alternative=payload(call('vera_workspace_sales_plan_calculate',secondArgs));
const result={calculated,alternative,secondArgs};
""",
    )
    state = json.loads(
        (output.parent / ".native-workspace/sales-plan-state.json").read_bytes()
    )
    assert result["alternative"]["source_ref"] != result["calculated"]["source_ref"]
    assert (
        state["generations"][1]["case_input_id"]
        == result["secondArgs"]["case_input_id"]
    )
    assert (
        output / result["alternative"]["source_ref"] / "original-case.json"
    ).read_bytes() == (
        output / result["calculated"]["source_ref"] / "original-case.json"
    ).read_bytes()
