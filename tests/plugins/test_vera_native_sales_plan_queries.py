"""Exact public scenario queries through real signed native MCP and durable files."""

from __future__ import annotations

import csv
import json
import subprocess

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_sales_plan import (  # noqa: F401
    CALCULATE,
    initial_plan,
)
from tests.plugins.test_vera_native_sales_plan_authoring import save_program
from tests.plugins.test_vera_native_workspace import workspace_module

QUERY = """
const exact={work_ref:'initial-plan',revision:view.revision,source_ref:calculated.source_ref};
const querySetup=payload(call('vera_workspace_sales_plan_query_setup',exact));
const queryArgs={...exact,review_ticket:querySetup.review_ticket,human_reviewed:true,idempotency_key:'fictional-query',reason:'Compare all China Actual and Plan rows',source_row_ids:[],where:['country=China'],columns:['country','units','gross_sales_reporting']};
"""


def test_query_keeps_all_exact_matches_and_preserves_plan_seal(initial_plan):
    env, output, binding = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + QUERY
        + """
const before=payload(call('vera_workspace_sales_plan_setup',{work_ref:'initial-plan'}));
const query=payload(call('vera_workspace_sales_plan_query',queryArgs));
const retry=payload(call('vera_workspace_sales_plan_query',queryArgs));
const page=payload(call('vera_workspace_sales_plan_query_read',{...exact,query_ref:query.query_ref}));
const evidence=call('vera_workspace_sales_plan_query_explain',{...exact,query_ref:query.query_ref});
const reopened=payload(call('vera_workspace_view',exact));
const after=payload(call('vera_workspace_sales_plan_setup',{work_ref:'initial-plan'}));
const result={before,after,query,retry,page,evidence,reopened};
""",
    )
    assert result["query"]["status"] == "queried"
    assert result["retry"] == result["query"]
    assert result["before"]["revision"] == result["after"]["revision"]
    assert result["page"]["total"] == 4
    assert result["page"]["population_rows_scanned"] == 8
    assert result["page"]["columns"] == [
        "source_row_id",
        "scenario",
        "country",
        "units",
        "gross_sales_reporting",
    ]
    evidence = result["evidence"]["structuredContent"]["evidence"]
    with (
        output / result["query"]["source_ref"] / "plan/sales_plan_scenario.csv"
    ).open() as handle:
        rows = [row for row in csv.DictReader(handle) if row["country"] == "China"]
    assert evidence["rows"] == [
        {key: row[key] for key in evidence["columns"]} for row in rows
    ]
    assert evidence["match_behavior"] == "all_exact_matches_no_sampling"
    assert result["reopened"]["data"]["report_ready"] is False
    assert result["query"]["professional_approval"] is False
    assert workspace_module().load_binding(binding)["run"]["status"] == "running"
    assert not (
        output / result["query"]["source_ref"] / "plan/model_drilldowns"
    ).exists()
    assert (
        len(
            list(
                (output / result["query"]["query_ref"] / "model_drilldowns").glob(
                    "*.json"
                )
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    ("ids", "where", "expected"),
    [
        ([], ["country= China"], 0),
        (["cn-bikes-2025-01"], ["scenario=PL"], 1),
        (["de-bikes-2025-01"], ["country=China"], 0),
        ([], ["country=China", "scenario=PL"], 2),
    ],
)
def test_query_uses_literal_and_filters_and_id_set(initial_plan, ids, where, expected):
    env, _, _ = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + QUERY
        + f"queryArgs.source_row_ids={json.dumps(ids)};queryArgs.where={json.dumps(where)};"
        + """
const receipt=payload(call('vera_workspace_sales_plan_query',queryArgs));
const result=payload(call('vera_workspace_sales_plan_query_read',{...exact,query_ref:receipt.query_ref}));
""",
    )
    assert result["total"] == expected
    assert result["population_rows_scanned"] == 8


@pytest.mark.parametrize(
    "change,error",
    [
        ("queryArgs.where=[]", "at least one"),
        ("queryArgs.columns=['invented_column']", "unknown prepared scenario"),
    ],
)
def test_query_retains_correctable_public_refusal_without_recovery(
    initial_plan, change, error
):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + QUERY
        + change
        + ";"
        + """
const receipt=payload(call('vera_workspace_sales_plan_query',queryArgs));
const page=payload(call('vera_workspace_sales_plan_query_read',{...exact,query_ref:receipt.query_ref}));
const setup=payload(call('vera_workspace_sales_plan_query_setup',exact));
const result={receipt,page,setup};
""",
    )
    assert result["receipt"]["status"] == "invalid_query"
    assert error in result["page"]["error"]
    assert result["setup"]["can_query"] is True
    assert (output / result["receipt"]["query_ref"] / "refusal.json").is_file()


@pytest.mark.parametrize(
    "change",
    [
        "queryArgs.reason='Different question'",
        "queryArgs.where=['country=Germany']",
        "queryArgs.columns=['units']",
    ],
)
def test_query_rejects_retry_key_rebound_to_another_request(initial_plan, change):
    env, _, _ = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + QUERY
        + "payload(call('vera_workspace_sales_plan_query',queryArgs));"
        + change
        + ";const result=call('vera_workspace_sales_plan_query',queryArgs);",
    )
    assert result["isError"] is True
    assert "different request" in result["content"][0]["text"]


@pytest.mark.parametrize(
    "change,error",
    [
        (
            "queryArgs.source_ref='sales-plan-'+'0'.repeat(64)",
            "mismatched review ticket",
        ),
        ("queryArgs.revision='stale'", "mismatched review ticket"),
        ("queryArgs.human_reviewed=false", "Invalid human_reviewed"),
        (
            "queryArgs.review_ticket=queryArgs.review_ticket.slice(0,-1)+'z'",
            "Invalid review ticket",
        ),
    ],
)
def test_query_rejects_unsigned_or_unconfirmed_scopes_before_outputs(
    initial_plan, change, error
):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + QUERY
        + change
        + ";const result=call('vera_workspace_sales_plan_query',queryArgs);",
    )
    assert result["isError"] is True
    assert error in result["content"][0]["text"]
    assert list(output.glob("sales-query-*")) == []


def test_query_model_route_is_complete_and_app_routes_keep_values_private(initial_plan):
    env, _, _ = initial_plan
    result = rpc_program(
        env,
        CALCULATE
        + QUERY
        + """
const query=payload(call('vera_workspace_sales_plan_query',queryArgs));
const privatePage=call('vera_workspace_sales_plan_query_read',{...exact,query_ref:query.query_ref});
const tools=service.handle({jsonrpc:'2.0',id:3,method:'tools/list'}).result.tools.filter(x=>x.name.startsWith('vera_workspace_sales_plan_query'));
const result={privatePage,tools};
""",
    )
    assert "China" not in json.dumps(result["privatePage"]["content"])
    assert "China" not in json.dumps(result["privatePage"]["structuredContent"])
    assert "China" in json.dumps(result["privatePage"]["_meta"])
    visibility = {
        row["name"]: row["_meta"]["ui"]["visibility"] for row in result["tools"]
    }
    assert visibility["vera_workspace_sales_plan_query_explain"] == ["app", "model"]
    assert visibility["vera_workspace_sales_plan_query_read"] == ["app"]
    assert visibility["vera_workspace_sales_plan_query"] == ["app"]


def test_viewer_can_inspect_actuals_but_cannot_retain_queries(initial_plan):
    env, output, _ = initial_plan
    prepared = rpc_program(env, CALCULATE + "const result={calculated,view};")
    viewer_env = {**env, "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        viewer_env,
        f"const calculated={json.dumps(prepared['calculated'])};const view={json.dumps(prepared['view'])};"
        + QUERY
        + """
const source=payload(call('vera_workspace_sales_plan_setup',{work_ref:'initial-plan'}));
const preview=payload(call('vera_workspace_sales_plan_source',{work_ref:'initial-plan',revision:source.revision,actual_input_id:source.items.find(x=>x.kind==='.csv').id}));
const denied=call('vera_workspace_sales_plan_query',queryArgs);
const result={querySetup,preview,denied};
""",
    )
    assert result["preview"]["total"] == 4
    assert result["querySetup"]["can_query"] is False
    assert result["denied"]["isError"] is True
    assert "reviewer authority" in result["denied"]["content"][0]["text"]
    assert list(output.glob("sales-query-*")) == []


def test_query_tampered_artifacts_block_read_and_retries(initial_plan):
    env, output, _ = initial_plan
    prepared = rpc_program(
        env,
        CALCULATE
        + QUERY
        + "const query=payload(call('vera_workspace_sales_plan_query',queryArgs));const result={query,exact};",
    )
    (output / prepared["query"]["query_ref"] / "request.json").write_text("{}")
    result = rpc_program(
        env,
        f"const exact={json.dumps(prepared['exact'])};const result=call('vera_workspace_sales_plan_query_read',{{...exact,query_ref:{json.dumps(prepared['query']['query_ref'])}}});",
    )
    assert result["isError"] is True
    assert "artifact bytes or population changed" in result["content"][0]["text"]


def test_query_other_actor_cannot_read_retained_values(initial_plan):
    env, _, _ = initial_plan
    prepared = rpc_program(
        env,
        CALCULATE
        + QUERY
        + "const query=payload(call('vera_workspace_sales_plan_query',queryArgs));const result={query,exact};",
    )
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ACTOR_ID": "another-reviewer"},
        f"const result=call('vera_workspace_sales_plan_query_explain',{{...{json.dumps(prepared['exact'])},query_ref:{json.dumps(prepared['query']['query_ref'])}}});",
    )
    assert result["isError"] is True
    assert "actor" in result["content"][0]["text"]


@pytest.mark.parametrize("initial_plan", ["actual_only_large_wide"], indirect=True)
def test_query_keeps_complete_large_result_but_refuses_model_sampling(initial_plan):
    env, output, _ = initial_plan
    result = rpc_program(
        env,
        save_program()
        + """
const calculated=payload(call('vera_workspace_sales_plan_calculate_draft',args));
const view=payload(call('vera_workspace_view',{work_ref:'initial-plan',source_ref:calculated.source_ref}));
"""
        + QUERY
        + """
queryArgs.where=['scenario=PL'];queryArgs.columns=['country','units'];
const query=payload(call('vera_workspace_sales_plan_query',queryArgs));
const page0=payload(call('vera_workspace_sales_plan_query_read',{...exact,query_ref:query.query_ref}));
const page1=payload(call('vera_workspace_sales_plan_query_read',{...exact,query_ref:query.query_ref,offset:20}));
const page2=payload(call('vera_workspace_sales_plan_query_read',{...exact,query_ref:query.query_ref,offset:40}));
const model=call('vera_workspace_sales_plan_query_explain',{...exact,query_ref:query.query_ref});
const result={query,page0,page1,page2,model};
""",
    )
    assert result["page0"]["total"] == 45
    assert result["page0"]["population_rows_scanned"] == 90
    assert result["page0"]["has_more"] is True
    assert result["page2"]["has_more"] is False
    artifact = next(
        (output / result["query"]["query_ref"] / "model_drilldowns").glob("*.json")
    )
    complete = json.loads(artifact.read_bytes())
    assert len(complete["rows"]) == 45
    assert (
        complete["rows"]
        == result["page0"]["rows"] + result["page1"]["rows"] + result["page2"]["rows"]
    )
    assert result["model"]["isError"] is True
    assert "No sample was returned" in result["model"]["content"][0]["text"]
    assert "structuredContent" not in result["model"]


def test_interrupted_public_query_retains_intent_and_never_reexecutes(
    initial_plan, monkeypatch
):
    env, output, _ = initial_plan
    prepared = rpc_program(env, CALCULATE + QUERY + "const result={exact,queryArgs};")
    import native_sales_plan

    original = native_sales_plan.engine_call
    attempts = []

    def interrupted(root, request):
        if request["operation"] == "query":
            attempts.append(request)
            raise subprocess.TimeoutExpired("public-model-use", 90)
        return original(root, request)

    monkeypatch.setattr(native_sales_plan, "engine_call", interrupted)
    module = workspace_module()
    with pytest.raises(subprocess.TimeoutExpired):
        module.dispatch("vera_workspace_sales_plan_query", prepared["queryArgs"])
    setup = module.dispatch("vera_workspace_sales_plan_query_setup", prepared["exact"])
    with pytest.raises(ValueError, match="Interrupted Sales query"):
        module.dispatch("vera_workspace_sales_plan_query", prepared["queryArgs"])
    assert len(attempts) == 1
    assert setup["status"] == "recovery_required"
    assert setup["can_query"] is False
    assert len(list(output.glob("sales-query-*"))) == 1
    assert not (output.parent / ".native-workspace/write.lock").exists()
