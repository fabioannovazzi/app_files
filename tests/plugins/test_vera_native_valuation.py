"""Actual public valuation workpapers through the owned optional native adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_business_valuation import (
    FIXTURE,
    case_data,
    prepare_archive_run,
)
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_financial_execution import archive_environment
from tests.plugins.test_vera_native_workspace import configure, workspace_module

__all__ = []


@pytest.fixture
def valuation_run(tmp_path, monkeypatch, request):
    """Register complete synthetic case and source receipts using the public ledger."""
    variant = getattr(request, "param", "ready")
    case = case_data()
    source_files = [FIXTURE / "evidence.txt"]
    if variant in {"normalized", "statement", "claim", "conclusion"}:
        from tests.plugins.test_business_valuation import (
            claimed_case,
            normalized_case,
            statement_case,
        )

        case = {
            "normalized": normalized_case,
            "statement": statement_case,
            "claim": claimed_case,
            "conclusion": claimed_case,
        }[variant]()
        if variant == "statement":
            source_files.append(FIXTURE / "statements.txt")
        if variant == "conclusion":
            case["conclusion"] = {
                "text": "Conclusione fittizia da riesaminare separatamente.",
                "method_ids": ["fcff"],
                "claim_ids": ["fcff-equity"],
                "review": None,
            }
    if variant in {"finite", "residual", "economic", "holding"}:
        from tests.plugins.test_business_valuation_economic import economic_case
        from tests.plugins.test_business_valuation_holding import holding_case
        from tests.plugins.test_business_valuation_income import finite_case
        from tests.plugins.test_business_valuation_residual import residual_case

        builders = {
            "finite": (finite_case, "finite-income.txt"),
            "residual": (residual_case, "residual-income.txt"),
            "economic": (economic_case, "economic-profit.txt"),
            "holding": (holding_case, "holding-sotp.txt"),
        }
        builder, source = builders[variant]
        case = builder()
        source_files.append(FIXTURE / source)
    if variant == "partial":
        case["sources"][0]["status"] = "unverified"
    if variant == "blocked":
        for item in case["inputs"]:
            item["value"] = None
    if variant == "audience":
        case["audience"] = "bank"
    if variant == "many":
        case["limitations"] = [f"Complete fictional limitation {i}" for i in range(43)]
    if variant == "claimed-review":
        case["methods"][0]["review"] = {"decision": "accepted"}
    if variant == "wrong-plan":
        case["plan_binding"] = {"source_id": "evidence"}
    case_path, context_path = prepare_archive_run(
        tmp_path, supplied_case=case, source_files=source_files
    )
    context = json.loads(context_path.read_bytes())
    client = tmp_path / "Client"
    ledger = _load_customer_ledger()
    loaded = ledger.load_run(client, context["engagement_id"], context["run_id"])
    context = loaded["context"]
    if variant == "foreign":
        source = next(
            r for r in context["input_bindings"] if Path(r["path"]) != case_path
        )
        altered = json.loads(case_path.read_bytes())
        altered["sources"][0]["path"] = "unregistered/evidence.txt"
        original = tmp_path / "foreign-case.json"
        original.write_text(json.dumps(altered))
        receipt = ledger.import_document(
            client, context["client_id"], context["engagement_id"], original, "source"
        )["receipt"]
        prepared = ledger.prepare_run(
            client,
            context["client_id"],
            context["engagement_id"],
            "business-valuation",
            "development",
            input_ids=[source["binding_id"], receipt["input_id"]],
        )
        started = ledger.start_run(
            client, context["engagement_id"], prepared["run"]["run_id"]
        )
        context = started["context"]
        loaded = started
    binding = {
        "work_ref": "fictional-valuation",
        "client_root": str(client),
        **{
            k: context[k]
            for k in ("client_id", "engagement_id", "run_id", "workflow_id")
        },
    }
    return (
        configure(monkeypatch, tmp_path, [binding]),
        Path(loaded["output_dir"]),
        binding,
    )


SELECT = """
const work={work_ref:'fictional-valuation'};
const setup=payload(call('vera_workspace_valuation_setup',work));
const chosen=payload(call('vera_workspace_valuation_case',{...work,revision:setup.revision,case_input_id:setup.items[0].id}));
const args={...work,revision:chosen.revision,review_ticket:chosen.review_ticket,item_id:chosen.selection.id,case_input_id:chosen.selection.id,confirmed:true,idempotency_key:'fictional-valuation-prepare'};
"""

PREPARE = (
    SELECT
    + """
const prepared=payload(call('vera_workspace_valuation_prepare',args));
const reopened=payload(call('vera_workspace_valuation_setup',work));
const exact={...work,source_ref:prepared.source_ref};
"""
)


@pytest.mark.parametrize(
    "valuation_run,kind",
    [
        ("finite", "INCOME_EQUITY_FINITE"),
        ("residual", "RESIDUAL_INCOME_EQUITY"),
        ("economic", "ECONOMIC_PROFIT"),
        ("holding", "HOLDING_SOTP"),
    ],
    indirect=["valuation_run"],
)
def test_native_valuation_preserves_specialist_method_and_its_complete_basis(
    valuation_run, kind
):
    env, output, _ = valuation_run
    result = rpc_program(
        env,
        PREPARE
        + "const result=payload(call('vera_workspace_valuation_read',{...exact,collection:'methods'}));",
    )
    assert result["total"] == 8
    method = result["rows"][-1]
    assert method["kind"] == kind
    assert method["status"] == "ready_for_professional_review"
    retained = json.loads(
        (output / result["source_ref"] / "valuation.json").read_bytes()
    )
    assert method == retained["methods"][-1]


@pytest.mark.parametrize(
    "valuation_run,expected",
    [
        ("ready", "ready_for_professional_review"),
        ("partial", "partial"),
        ("blocked", "blocked"),
        ("claimed-review", "ready_for_professional_review"),
    ],
    indirect=["valuation_run"],
)
def test_native_valuation_preserves_all_public_outputs_status_and_retry(
    valuation_run, expected
):
    env, output, _ = valuation_run
    result = rpc_program(
        env,
        PREPARE
        + """
const result={prepared,reopened,retry:payload(call('vera_workspace_valuation_prepare',args)),report:payload(call('vera_workspace_valuation_report',exact)),files:payload(call('vera_workspace_valuation_outputs',exact)),methods:payload(call('vera_workspace_valuation_read',{...exact,collection:'methods'}))};
""",
    )
    assert result["prepared"]["status"] == expected
    assert result["prepared"] == result["retry"]
    assert result["prepared"]["professional_approval"] is False
    assert result["prepared"]["run_completed"] is False
    assert result["reopened"]["can_prepare"] is False
    directory = output / result["prepared"]["source_ref"]
    assert (
        result["report"]["report"] == (directory / "valuation_report.html").read_text()
    )
    assert len(result["files"]["outputs"]) == 19
    assert {Path(r["path"]).name for r in result["files"]["outputs"]} == {
        p.name for p in directory.iterdir()
    }
    assert result["methods"]["piv_conformity"] == "not_assessed"
    assert result["methods"]["total"] == 7
    assert (directory / "valuation_workbook.xlsx").is_file()
    assert (directory / "valuation_report.pdf").is_file()
    if expected == "blocked":
        assert {r["status"] for r in result["methods"]["rows"]} == {"blocked"}


@pytest.mark.parametrize("valuation_run", ["many"], indirect=True)
def test_native_valuation_pages_complete_population_and_exact_model_selection(
    valuation_run,
):
    env, *_ = valuation_run
    result = rpc_program(
        env,
        PREPARE
        + """
let rows=[],offset=0,total;
do{const page=payload(call('vera_workspace_valuation_read',{...exact,collection:'limitations',offset}));rows.push(...page.rows);total=page.total;offset+=20;}while(offset<total);
const publicRead=call('vera_workspace_valuation_read',{...exact,collection:'limitations'});
const explain=call('vera_workspace_valuation_explain',{...exact,revision:reopened.revision,collection:'limitations',index:42});
const stale=call('vera_workspace_valuation_explain',{...exact,revision:'stale',collection:'limitations',index:42});
const result={rows,total,publicRead,explain,stale};
""",
    )
    assert result["total"] == len(result["rows"]) == 43
    assert (
        result["explain"]["structuredContent"]["record"]
        == "Complete fictional limitation 42"
    )
    assert "Complete fictional limitation" not in json.dumps(
        result["publicRead"]["structuredContent"]
    )
    assert "sources" not in result["explain"]["structuredContent"]
    assert result["stale"]["isError"] is True


def test_native_valuation_draft_recovers_empty_generation_and_refuses_concurrent_replay(
    valuation_run,
):
    env, *_ = valuation_run
    result = rpc_program(
        env,
        """
const work={work_ref:'fictional-valuation'},setup=payload(call('vera_workspace_valuation_setup',work));
const args={...work,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields:{case_input_id:setup.items[0].id}};
const saved=payload(call('vera_workspace_valuation_draft_save',args));
const reopened=payload(call('vera_workspace_valuation_setup',work));
const stale=call('vera_workspace_valuation_draft_save',{...args,fields:{case_input_id:''}});
const clear=payload(call('vera_workspace_valuation_draft_save',{...args,expected_draft_revision:reopened.draft_revision,fields:{case_input_id:''}}));
const replay=call('vera_workspace_valuation_draft_save',{...args,expected_draft_revision:reopened.draft_revision});
const result={saved,reopened,stale,clear,replay,final:payload(call('vera_workspace_valuation_setup',work))};
""",
    )
    assert (
        result["reopened"]["draft"]["case_input_id"]
        == result["reopened"]["items"][0]["id"]
    )
    assert result["stale"]["isError"] is True
    assert result["replay"]["isError"] is True
    assert result["final"]["draft"] == {"case_input_id": ""}
    assert result["final"]["versions"] == []


@pytest.mark.parametrize(
    "valuation_run", ["audience", "foreign", "wrong-plan"], indirect=True
)
def test_native_valuation_refuses_foreign_audience_or_arbitrary_upstream_plan_before_export(
    valuation_run,
):
    env, output, _ = valuation_run
    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_valuation_setup',{work_ref:'fictional-valuation'}));
const result=call('vera_workspace_valuation_case',{work_ref:setup.work_ref,revision:setup.revision,case_input_id:setup.items[0].id});
""",
    )
    assert result["isError"] is True
    assert list(output.iterdir()) == []
    assert list(output.parent.glob(".native-workspace/valuation-request-*")) == []


@pytest.mark.parametrize(
    "change", ["confirmed:false", "item_id:'foreign'", "revision:'stale'"]
)
def test_native_valuation_requires_exact_selected_case_and_fresh_confirmation(
    valuation_run, change
):
    env, output, _ = valuation_run
    result = rpc_program(
        env,
        SELECT
        + "const result=call('vera_workspace_valuation_prepare',{...args,"
        + change
        + "});",
    )
    assert result["isError"] is True
    assert list(output.iterdir()) == []


def test_native_valuation_viewer_may_consult_case_but_cannot_execute(valuation_run):
    env, output, _ = valuation_run
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": "VIEWER"},
        SELECT
        + "const result={chosen,write:call('vera_workspace_valuation_prepare',args)};",
    )
    assert result["chosen"]["can_prepare"] is False
    assert result["write"]["isError"] is True
    assert list(output.iterdir()) == []


def test_native_valuation_tampered_artifact_refuses_consultation(valuation_run):
    env, output, _ = valuation_run
    prepared = rpc_program(env, PREPARE + "const result=prepared;")
    (output / prepared["source_ref"] / "valuation_report.md").write_text("altered")
    result = rpc_program(
        env,
        "const result=call('vera_workspace_valuation_setup',{work_ref:'fictional-valuation'});",
    )
    assert result["isError"] is True


def test_native_valuation_interrupted_export_retains_intent_and_blocks_archive_closure(
    valuation_run, monkeypatch
):
    env, output, binding = valuation_run
    module = workspace_module()
    module.dispatch(
        "vera_workspace_valuation_setup", {"work_ref": "fictional-valuation"}
    )
    import native_valuation

    public_call = native_valuation.engine_call

    def fail_after_export(root, request):
        result = public_call(root, request)
        if request["operation"] == "prepare":
            raise OSError("fictional interrupted native conservation")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(native_valuation, "engine_call", fail_after_export)
        setup = module.dispatch(
            "vera_workspace_valuation_setup", {"work_ref": "fictional-valuation"}
        )
        chosen = module.dispatch(
            "vera_workspace_valuation_case",
            {
                "work_ref": "fictional-valuation",
                "revision": setup["revision"],
                "case_input_id": setup["items"][0]["id"],
            },
        )
        with pytest.raises(OSError, match="interrupted"):
            module.dispatch(
                "vera_workspace_valuation_prepare",
                {
                    "work_ref": "fictional-valuation",
                    "revision": chosen["revision"],
                    "case_input_id": chosen["selection"]["id"],
                    "item_id": chosen["selection"]["id"],
                    "confirmed": True,
                    "idempotency_key": "interrupted-valuation",
                },
            )
    assert len(list(output.glob("valuation-*"))) == 1
    result = rpc_program(
        env,
        "const result=payload(call('vera_workspace_valuation_setup',{work_ref:'fictional-valuation'}));",
    )
    assert result["status"] == "recovery_required"
    archived = archive_environment(env, binding, output)
    result = rpc_program(
        archived,
        "const result=call('vera_workspace_archive_closure',"
        + json.dumps({k: binding[k] for k in ("client_id", "engagement_id", "run_id")})
        + ");",
    )
    assert result["isError"] is True
    assert "recovery" in result["content"][0]["text"]
