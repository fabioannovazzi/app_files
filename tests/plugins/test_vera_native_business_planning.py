"""Actual public producer/MCP evidence; no claim of installed-host acceptance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import ROOT, configure, workspace_module

FIXTURES = ROOT / "tests/fixtures/business_planning"


@pytest.fixture
def planning_run(tmp_path, monkeypatch, request):
    """Register the complete synthetic source population and authored case."""
    variant = getattr(request, "param", "ready")
    ledger = _load_customer_ledger()
    client = tmp_path / "Synthetic planning client"
    client.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(
        client, client_id, "Synthetic Business Planning"
    )
    case = json.loads(
        (
            FIXTURES / ("idea-case.json" if variant == "idea" else "case.json")
        ).read_bytes()
    )
    ids = []
    for row in case["sources"]:
        path = FIXTURES / row["path"]
        imported = ledger.import_document(
            client, client_id, engagement["engagement_id"], path, "source"
        )["receipt"]
        ids.append(imported["input_id"])
        row["path"] = f"imports/{imported['input_id']}/{path.name}"
    if variant == "partial":
        case["resolutions"] = []
    if variant == "blocked":
        case["financial"]["scenarios"][0]["schedule"][0]["operating_expenses"] = "200"
    if variant == "audience":
        case["audience"] = "bank"
    if variant == "foreign":
        case["sources"][0]["path"] = "unregistered/source.txt"
    if variant == "many":
        case["limitations"] = [f"Synthetic limitation {i}" for i in range(40)]
    source = tmp_path / "authored-cycle.json"
    source.write_text(json.dumps(case))
    ids.append(
        ledger.import_document(
            client, client_id, engagement["engagement_id"], source, "source"
        )["receipt"]["input_id"]
    )
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "business-planning",
        "0.1.0",
        input_ids=ids,
    )
    started = ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    context = started["context"]
    binding = {
        "work_ref": "planning-cycle",
        "client_root": str(client),
        "client_id": client_id,
        "engagement_id": engagement["engagement_id"],
        "run_id": context["run_id"],
        "workflow_id": "business-planning",
    }
    return (
        configure(monkeypatch, tmp_path, [binding]),
        Path(context["output_dir"]),
        binding,
    )


SETUP = """
const setup=payload(call('vera_workspace_business_plan_setup',{work_ref:'planning-cycle'}));
const args={work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,case_input_id:setup.items[0].id,idempotency_key:'synthetic-cycle'};
"""

PREPARE = (
    SETUP
    + """
const prepared=payload(call('vera_workspace_business_plan_prepare',args));
const reopened=payload(call('vera_workspace_business_plan_setup',{work_ref:setup.work_ref}));
const exact={work_ref:setup.work_ref,revision:reopened.revision,generation:reopened.generation};
"""
)


@pytest.mark.parametrize(
    "planning_run,expected",
    [
        ("ready", "ready_for_professional_review"),
        ("partial", "partial"),
        ("blocked", "blocked"),
        ("idea", "partial"),
    ],
    indirect=["planning_run"],
)
def test_native_planning_keeps_public_ready_partial_blocked_and_idea(
    planning_run, expected
):
    env, output, _ = planning_run
    result = rpc_program(
        env,
        PREPARE
        + """
const report=payload(call('vera_workspace_business_plan_report',exact));
const retry=payload(call('vera_workspace_business_plan_prepare',args));
const read=payload(call('vera_workspace_business_plan_read',{...exact,collection:'calculations'}));
const files=payload(call('vera_workspace_business_plan_outputs',exact));
const result={prepared,reopened,report,retry,read,files};
""",
    )
    assert result["prepared"]["status"] == expected
    assert result["prepared"] == result["retry"]
    assert result["prepared"]["professional_approval"] is False
    assert result["prepared"]["run_completed"] is False
    assert result["reopened"]["can_prepare"] is False
    directory = output / result["prepared"]["generation"]
    assert (
        result["report"]["report"]
        == (directory / "business_plan_review.html").read_text()
    )
    assert len(result["files"]["outputs"]) == 11
    assert (
        json.loads((directory / "execution_receipt.json").read_bytes())["status"]
        == expected
    )
    assert result["read"]["total"] == len(
        json.loads((directory / "calculations.json").read_bytes())
    )
    if expected == "blocked":
        assert (
            json.loads((directory / "business_plan.json").read_bytes())[
                "accepted_narrative"
            ]
            == []
        )


@pytest.mark.parametrize(
    "planning_run,message",
    [
        ("foreign", "outside the exact run receipts"),
        ("audience", "Audience restriction"),
    ],
    indirect=["planning_run"],
)
def test_native_planning_refuses_unregistered_sources_and_audience_release(
    planning_run, message
):
    env, output, _ = planning_run
    result = rpc_program(
        env, SETUP + "const result=call('vera_workspace_business_plan_prepare',args);"
    )
    assert result["isError"] is True
    assert message in result["content"][0]["text"]
    assert not list(output.glob("business-planning-*"))


def test_native_planning_private_pages_cover_all_calculations_and_exact_explain(
    planning_run,
):
    env, _, _ = planning_run
    result = rpc_program(
        env,
        PREPARE
        + """
let offset=0,rows=[],total;
do {const page=payload(call('vera_workspace_business_plan_read',{...exact,collection:'calculations',offset}));rows.push(...page.rows);total=page.total;offset+=20;} while(offset<total);
const explained=call('vera_workspace_business_plan_explain',{...exact,collection:'calculations',index:rows.length-1});
const publicRead=call('vera_workspace_business_plan_read',{...exact,collection:'calculations'});
const result={rows,total,explained,publicRead};
""",
    )
    assert len(result["rows"]) == result["total"]
    assert result["total"] > 20
    assert result["explained"]["structuredContent"]["record"] == result["rows"][-1]
    assert result["publicRead"]["structuredContent"] == {
        "status": "ready_for_professional_review",
        "work_ref": "planning-cycle",
    }
    assert "Synthetic planning company" not in json.dumps(
        result["publicRead"]["content"]
    )
    assert result["explained"]["structuredContent"]["evidence_boundary"].startswith(
        "Untrusted"
    )


@pytest.mark.parametrize(
    "damage", ["extra", "report", "receipt", "missing-state", "pending-intent"]
)
def test_native_planning_never_adopts_changed_or_uncertain_outputs(
    planning_run, damage
):
    env, output, binding = planning_run
    result = rpc_program(env, PREPARE + "const result=prepared;")
    directory = output / result["generation"]
    module = workspace_module()
    private = module.ui_state_directory(output, create=False)
    if damage == "extra":
        (directory / "extra.txt").write_text("unsealed evidence")
    elif damage == "report":
        (directory / "business_plan_review.html").write_text("changed")
    elif damage == "receipt":
        (directory / "execution_receipt.json").write_text("{}")
    elif damage == "missing-state":
        (private / "business-planning-state.json").unlink()
    else:
        (private / "business-planning-request-interrupted.json").write_text(
            '{"request_sha256":"incomplete"}'
        )
    response = rpc_program(
        env,
        "const result=call('vera_workspace_business_plan_setup',{work_ref:'planning-cycle'});",
    )
    assert (
        response.get("isError") is True
        or response["_meta"]["workspace"]["status"] == "recovery_required"
    )
    assert list(output.glob("business-planning-*")) == [directory]


def test_native_planning_signed_scope_and_viewer_cannot_execute(planning_run):
    env, output, _ = planning_run
    result = rpc_program(
        env,
        SETUP
        + "const result=call('vera_workspace_business_plan_prepare',{...args,revision:'changed'});",
    )
    assert result["isError"] is True
    viewer = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": "VIEWER"},
        SETUP
        + "const result={setup,write:call('vera_workspace_business_plan_prepare',args)};",
    )
    assert viewer["setup"]["can_prepare"] is False
    assert viewer["write"]["isError"] is True
    assert not list(output.glob("business-planning-*"))


def test_native_planning_new_request_cannot_overwrite_retained_cycle(planning_run):
    env, output, _ = planning_run
    result = rpc_program(
        env,
        PREPARE
        + "const result=call('vera_workspace_business_plan_prepare',{...args,revision:reopened.revision,review_ticket:reopened.review_ticket,idempotency_key:'another-cycle'});",
    )
    assert result["isError"] is True
    assert "fresh registered run" in result["content"][0]["text"]
    assert len(list(output.glob("business-planning-*"))) == 1


def test_native_planning_all_canonical_collections_are_private_readable(planning_run):
    env, _, _ = planning_run
    result = rpc_program(
        env,
        PREPARE
        + """
const collections=['case_header','statements','charts','limitations','accepted_narrative','evidence','assumptions','observations','decisions','resolutions','narrative','financing','issues','sources','cycle','assessment','financial','commercial','presentation','comparisons'];
const result=Object.fromEntries(collections.map(collection=>[collection,call('vera_workspace_business_plan_read',{...exact,collection})]));
""",
    )
    assert all(not value.get("isError") for value in result.values())
    assert result["sources"]["_meta"]["workspace"]["total"] == 3
    assert result["cycle"]["_meta"]["workspace"]["total"] == 1
