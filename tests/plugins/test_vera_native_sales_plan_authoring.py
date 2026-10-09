"""Native authoring consumes exact recovered choices through the real Plan engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_sales_plan import initial_plan  # noqa: F401
from tests.plugins.test_vera_native_workspace import ROOT, workspace_module


def explicit_fields() -> dict:
    """Fictional professional choices; neither engine constants nor review is inferred."""
    case = json.loads(
        (ROOT / "plugins/sales-plan/evals/synthetic/case.json").read_bytes()
    )
    recipe = case["preparation_recipe"]
    keys = [
        "reporting_currency",
        "unit",
        "dimension_columns",
        "metric_columns",
        "period_mapping",
        "default_discount_behavior",
        "default_cogs_behavior",
        "same_driver_overlap_behavior",
        "discount_assumption_basis",
        "cogs_assumption_basis",
    ]
    return {
        **{k: recipe[k] for k in keys},
        "purpose": "Fictional explicit commercial Plan choices",
        "assumptions": case["reviewed_assumptions"]["assumptions"],
        "reviewed_by": "fictional-reviewer",
        "reviewed_at": "2026-10-07",
        "review_basis": "Explicit test-only review of source, mappings and assumptions",
    }


AUTHOR_SETUP = """
const setup=payload(call('vera_workspace_sales_plan_setup',{work_ref:'initial-plan'}));
const draft=payload(call('vera_workspace_sales_plan_draft_read',{work_ref:setup.work_ref}));
const actual=setup.items.find(row=>row.kind==='.csv');
const authorScope={work_ref:setup.work_ref,revision:setup.revision,review_ticket:draft.review_ticket,expected_draft_revision:draft.draft.draft_revision};
"""


def save_program(fields: dict | None = None) -> str:
    data = explicit_fields() if fields is None else fields
    return (
        AUTHOR_SETUP
        + f"const fields={{...{json.dumps(data)},actual_input_id:actual.id}};"
        + """
const saved=payload(call('vera_workspace_sales_plan_draft_save',{...authorScope,fields}));
const args={...authorScope,expected_draft_revision:saved.draft_revision,human_reviewed:true,idempotency_key:'fictional-authoring'};
"""
    )


@pytest.mark.parametrize("initial_plan", ["actual_only"], indirect=True)
def test_native_authoring_creates_real_plan_without_a_registered_case(initial_plan):
    env, output, binding = initial_plan
    result = rpc_program(
        env,
        save_program()
        + """
const recovered=payload(call('vera_workspace_sales_plan_draft_read',{work_ref:setup.work_ref}));
const calculated=payload(call('vera_workspace_sales_plan_calculate_draft',args));
const view=payload(call('vera_workspace_view',{work_ref:setup.work_ref,source_ref:calculated.source_ref}));
const retry=payload(call('vera_workspace_sales_plan_calculate_draft',args));
const result={setup,recovered,calculated,view,retry};
""",
    )
    directory = output / result["calculated"]["source_ref"]
    case = json.loads((directory / "case.json").read_bytes())
    receipt = json.loads((directory / "plan/plan_execution_receipt.json").read_bytes())
    assert len(result["setup"]["items"]) == 1
    assert receipt["status"] == "passed"
    assert receipt["report_ready"] is False
    assert case["reviewed_assumptions"]["reviewed_by"] == "fictional-reviewer"
    assert result["retry"] == result["calculated"]
    assert result["view"]["kind"] == "sales"
    assert "human_reviewed" not in result["recovered"]["draft"]["fields"]
    assert workspace_module().load_binding(binding)["run"]["status"] == "running"
    assert not (directory / "original-case.json").exists()


def test_native_authoring_partial_choices_reopen_without_official_output(initial_plan):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        save_program({"purpose": "Incomplete fictional Plan"})
        + "const recovered=payload(call('vera_workspace_sales_plan_draft_read',{work_ref:setup.work_ref}));const refused=call('vera_workspace_sales_plan_calculate_draft',args);const result={recovered,refused};",
    )
    assert (
        result["recovered"]["draft"]["fields"]["purpose"] == "Incomplete fictional Plan"
    )
    assert result["refused"]["isError"] is True
    assert "Complete all" in result["refused"]["content"][0]["text"]
    assert list(output.iterdir()) == []


def test_native_authoring_keeps_previous_checkpoint_on_concurrent_save(initial_plan):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        save_program()
        + "const refused=call('vera_workspace_sales_plan_draft_save',{...authorScope,fields:{purpose:'other'}});const recovered=payload(call('vera_workspace_sales_plan_draft_read',{work_ref:setup.work_ref}));const result={refused,recovered,saved};",
    )
    assert result["refused"]["isError"] is True
    assert "concurrently" in result["refused"]["content"][0]["text"]
    assert (
        result["recovered"]["draft"]["draft_revision"]
        == result["saved"]["draft_revision"]
    )
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("expected_draft_revision", "0" * 64, "concurrently"),
        ("human_reviewed", False, "Invalid human_reviewed"),
        ("review_ticket", "invalid.signature", "Invalid review ticket"),
        ("revision", "0" * 64, "mismatched review ticket"),
    ],
)
def test_native_authoring_rejects_unconfirmed_or_substituted_scope(
    initial_plan, field, value, error
):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        save_program()
        + f"args[{json.dumps(field)}]={json.dumps(value)};const result=call('vera_workspace_sales_plan_calculate_draft',args);",
    )
    assert result["isError"] is True
    assert error in result["content"][0]["text"]
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "fields",
    [
        {"human_reviewed": True},
        {"report_ready": True},
        {"assumptions": {}},
        {"dimension_columns": "country"},
        {"period_mapping": [{}]},
    ],
)
def test_native_authoring_rejects_unsafe_or_unrenderable_draft_fields(
    initial_plan, fields
):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        AUTHOR_SETUP
        + "const result=call('vera_workspace_sales_plan_draft_save',{...authorScope,fields:"
        + json.dumps(fields)
        + "});",
    )
    assert result["isError"] is True
    assert list(output.iterdir()) == []


def test_native_authoring_viewer_reads_source_but_cannot_store_choices(initial_plan):
    env, output, _ = initial_plan
    env["VERA_WORKSPACE_ROLES"] = "VIEWER"
    result = rpc_program(
        env,
        AUTHOR_SETUP
        + "const page=payload(call('vera_workspace_sales_plan_source',{work_ref:setup.work_ref,revision:setup.revision,actual_input_id:actual.id}));const refused=call('vera_workspace_sales_plan_draft_save',{...authorScope,fields:{purpose:'attempt'}});const result={page,refused};",
    )
    assert result["page"]["total"] == 4
    assert result["refused"]["isError"] is True
    assert list(output.iterdir()) == []


def test_native_authoring_unmatched_scope_remains_failed_unapproved_output(
    initial_plan,
):
    env, output, _ = initial_plan
    fields = explicit_fields()
    fields["assumptions"][0]["scope"] = {"country": ["Unobserved"]}
    result = rpc_program(
        env,
        save_program(fields)
        + "const calculated=payload(call('vera_workspace_sales_plan_calculate_draft',args));const view=payload(call('vera_workspace_view',{work_ref:setup.work_ref,source_ref:calculated.source_ref}));const result={calculated,view};",
    )
    assert result["calculated"]["status"] == "failed"
    assert result["calculated"]["report_ready"] is False
    assert (
        output / result["calculated"]["source_ref"] / "plan/reconciliation.json"
    ).is_file()
    assert result["view"]["data"]["professional_approval"] is False


def test_native_authoring_contract_refusal_can_be_corrected_in_a_new_revision(
    initial_plan,
):
    env, output, _ = initial_plan
    fields = explicit_fields()
    fields["period_mapping"].append(fields["period_mapping"][0])
    result = rpc_program(
        env,
        save_program(fields)
        + f"""
const blocked=payload(call('vera_workspace_sales_plan_calculate_draft',args));
const view=payload(call('vera_workspace_view',{{work_ref:setup.work_ref,source_ref:blocked.source_ref,item_id:'native_contract_refusal.json'}}));
const current=payload(call('vera_workspace_sales_plan_draft_read',{{work_ref:setup.work_ref}}));
const newScope={{work_ref:setup.work_ref,revision:current.revision,review_ticket:current.review_ticket,expected_draft_revision:current.draft.draft_revision}};
const refused=call('vera_workspace_sales_plan_draft_save',{{...newScope,fields}});
payload(call('vera_workspace_sales_plan_draft_clear',newScope));
const fixed=payload(call('vera_workspace_sales_plan_draft_save',{{...newScope,expected_draft_revision:'',fields:{{...{json.dumps(explicit_fields())},actual_input_id:actual.id}}}}));
const passed=payload(call('vera_workspace_sales_plan_calculate_draft',{{...newScope,expected_draft_revision:fixed.draft_revision,human_reviewed:true,idempotency_key:'fictional-correction'}}));
const result={{blocked,view,current,refused,passed}};
""",
    )
    assert result["blocked"]["status"] == "invalid_case"
    assert (
        "period_mapping source and target periods must be chronological"
        in result["view"]["selection"]["data"]["producer_contract_error"]
    )
    assert result["current"]["draft"]["stale"] is True
    assert result["refused"]["isError"] is True
    assert result["passed"]["status"] == "passed"
    assert len(list(output.glob("sales-plan-*"))) == 2
    assert not (
        output / result["blocked"]["source_ref"] / "plan/plan_execution_receipt.json"
    ).exists()


def test_native_authoring_literal_members_scan_complete_registered_source(initial_plan):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        AUTHOR_SETUP
        + "const members=call('vera_workspace_sales_plan_members',{work_ref:setup.work_ref,revision:setup.revision,actual_input_id:actual.id,column:'country',query:'China'});const result={members};",
    )
    assert result["members"]["_meta"]["workspace"]["members"] == ["China"]
    assert result["members"]["_meta"]["workspace"]["population_rows_scanned"] == 4
    assert "China" not in json.dumps(result["members"]["structuredContent"])
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "tool,extra",
    [
        ("vera_workspace_sales_plan_source", {}),
        ("vera_workspace_sales_plan_members", {"column": "country"}),
    ],
)
def test_native_authoring_source_read_refuses_foreign_binding(
    initial_plan, tool, extra
):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        AUTHOR_SETUP
        + "const result=call("
        + json.dumps(tool)
        + ",{work_ref:setup.work_ref,revision:setup.revision,actual_input_id:'foreign',..."
        + json.dumps(extra)
        + "});",
    )
    assert result["isError"] is True
    assert "outside this run" in result["content"][0]["text"]
    assert list(output.iterdir()) == []


def test_native_authoring_actor_cannot_adopt_another_operators_draft(initial_plan):
    env, output, binding = initial_plan
    first = rpc_program(env, save_program() + "const result=saved;")
    config = Path(env["VERA_WORKSPACE_BINDINGS"])
    value = json.loads(config.read_bytes())
    value["actor_id"] = "other-fictional-reviewer"
    config.write_text(json.dumps(value))
    other = {**env, "VERA_WORKSPACE_ACTOR_ID": value["actor_id"]}
    result = rpc_program(other, AUTHOR_SETUP + "const result=draft;")
    assert first["draft_revision"]
    assert result["draft"]["fields"] == {}
    assert result["draft"]["draft_revision"] == ""
    assert (
        len(list((output.parent / ".native-workspace").glob("sales-plan-draft-*.json")))
        == 1
    )


def test_native_authoring_shared_select_source_keeps_only_native_accessible_label():
    """Keep the maintained dropdown with its explicit native label projection."""
    canonical = ROOT / "static/js/custom_select.js"
    bundled = ROOT / "plugins/vera/ui/custom_select.js"
    label_projection = (
        '    const accessibleLabel = select.getAttribute("aria-label");\n'
        '    if (accessibleLabel) trigger.setAttribute("aria-label", accessibleLabel);\n'
    )
    native_source = bundled.read_text()

    assert native_source.count(label_projection) == 1
    assert native_source.replace(label_projection, "") == canonical.read_text()


@pytest.mark.parametrize("initial_plan", ["actual_only_large"], indirect=True)
def test_native_authoring_pages_rows_and_members_over_the_complete_source(initial_plan):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        AUTHOR_SETUP
        + """
const sourceArgs={work_ref:setup.work_ref,revision:setup.revision,actual_input_id:actual.id};
const first=payload(call('vera_workspace_sales_plan_source',sourceArgs));
const tail=payload(call('vera_workspace_sales_plan_source',{...sourceArgs,offset:40}));
const members=payload(call('vera_workspace_sales_plan_members',{...sourceArgs,column:'country',offset:30}));
const match=payload(call('vera_workspace_sales_plan_members',{...sourceArgs,column:'country',query:'Member40'}));
const result={first,tail,members,match};
""",
    )
    assert result["first"]["total"] == 45
    assert len(result["first"]["rows"]) == 20
    assert result["first"]["has_more"] is True
    assert len(result["tail"]["rows"]) == 5
    assert result["tail"]["has_more"] is False
    assert result["members"]["total"] == 43
    assert len(result["members"]["members"]) == 13
    assert result["match"]["members"] == ["Member40"]
    assert result["match"]["population_rows_scanned"] == 45
    assert list(output.iterdir()) == []
