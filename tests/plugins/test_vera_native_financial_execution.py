"""Eight reviewed public recipes execute from exact registered source choices."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_financial_analysis import (
    ROOT,
    _load_pack_module,
    _vera_case,
)
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import archive_cli
from tests.plugins.test_vera_native_financial_analysis import fdd_case
from tests.plugins.test_vera_native_workspace import configure, workspace_module

__all__ = []
PACKS = [
    "monthly_pnl",
    "working_capital",
    "customer_concentration",
    "quality_of_earnings",
    "net_debt",
    "normalized_working_capital",
    "capex",
    "deal_bridges",
]


@pytest.fixture(params=PACKS)
def financial_intake(request, tmp_path, monkeypatch):
    pack = request.param
    fixtures = {
        "monthly_pnl": "plugins/clara/evals/preparation/wd40_fy2025/case.json",
        "working_capital": "plugins/clara/evals/preparation/wd40_fy2025_working_capital/case.json",
        "customer_concentration": "plugins/clara/evals/preparation/udc_fy2025_customer_concentration/case.json",
    }
    case = (
        _vera_case(ROOT / fixtures[pack], tmp_path / "originals", pack_id=pack)
        if pack in fixtures
        else fdd_case(tmp_path / "originals", pack)
    )
    runner = _load_pack_module()
    sources = runner.declared_case_input_bindings(case, pack)
    ledger = _load_customer_ledger()
    folder = tmp_path / "Archive" / "Fictional financial customer"
    folder.mkdir(parents=True)
    client = "client_" + "f" * 24
    ledger.create_client_manifest(folder, client)
    engagement = ledger.create_engagement(folder, client, "Fictional financial intake")
    case_id = ledger.import_document(
        folder, client, engagement["engagement_id"], case, "source"
    )["receipt"]["input_id"]
    bindings = {
        identity: ledger.import_document(
            folder, client, engagement["engagement_id"], path, "source"
        )["receipt"]["input_id"]
        for identity, path in sources
    }
    prepared = ledger.prepare_run(
        folder,
        client,
        engagement["engagement_id"],
        "financial-analysis",
        "native-test",
        input_ids=list(dict.fromkeys([case_id, *bindings.values()])),
    )
    loaded = ledger.start_run(
        folder, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    binding = {
        "work_ref": "fictional-financial",
        "client_root": str(folder),
        "client_id": client,
        "engagement_id": engagement["engagement_id"],
        "run_id": prepared["run"]["run_id"],
        "workflow_id": "financial-analysis",
    }
    env = configure(monkeypatch, tmp_path, [binding])
    return env, Path(loaded["output_dir"]), binding, pack, case_id, bindings


def execute_script(fixture) -> str:
    _, _, _, pack, case_id, bindings = fixture
    return f"""
const exact={{work_ref:'fictional-financial',pack_id:{json.dumps(pack)},case_input_id:{json.dumps(case_id)}}};
const setup=payload(call('vera_workspace_financial_setup',{{work_ref:exact.work_ref}}));
const selected=payload(call('vera_workspace_financial_case',exact));
const executeArgs={{...exact,item_id:selected.selection.id,revision:selected.revision,review_ticket:selected.review_ticket,source_bindings:{json.dumps(bindings)},confirmed:true,human_reviewed:true,idempotency_key:'fictional-financial-execute'}};
"""


def test_native_financial_registered_reviewed_case_executes_all_normal_outputs(
    financial_intake,
):
    env, output, binding, pack, case_id, bindings = financial_intake
    result = rpc_program(
        env,
        execute_script(financial_intake)
        + """
const execution=payload(call('vera_workspace_financial_execute',executeArgs));
const retry=payload(call('vera_workspace_financial_execute',executeArgs));
const view=payload(call('vera_workspace_financial_view',{work_ref:exact.work_ref,source_ref:execution.source_ref}));
const artifact=view.items.find(v=>v.title==='reconciliation.json');
const selectedResult=payload(call('vera_workspace_financial_view',{work_ref:exact.work_ref,source_ref:execution.source_ref,item_id:artifact.id}));
const explained=call('vera_workspace_financial_explain',{work_ref:exact.work_ref,source_ref:execution.source_ref,item_id:artifact.id,revision:selectedResult.revision}).structuredContent;
const result={execution,retry,view,explained,after:payload(call('vera_workspace_financial_setup',{work_ref:exact.work_ref}))};
""",
    )
    assert result["execution"] == result["retry"]
    assert result["execution"]["pack_id"] == pack
    assert result["execution"]["report_ready"] is False
    assert result["execution"]["professional_approval"] is False
    assert result["execution"]["run_completed"] is False
    assert result["view"]["data"]["pack_id"] == pack
    assert len(result["after"]["versions"]) == 1
    assert "source_artifacts" not in result["explained"]
    prepared = output / result["execution"]["source_ref"] / "prepared"
    assert (prepared / "model_use_manifest.json").is_file()
    assert (prepared / "pack_execution_receipt.json").is_file()
    assert (prepared / "prepared_evidence_manifest.json").is_file()
    assert (prepared / "reconciliation.json").is_file()
    ledger = _load_customer_ledger()
    loaded = ledger.load_run(
        Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
    )
    originals = {
        row["binding_id"]: Path(loaded["run_root"]) / row["execution_relative_path"]
        for row in loaded["input_manifest"]["inputs"]
    }
    copied_case = prepared.parent / "case/case.json"
    assert copied_case.read_bytes() == originals[case_id].read_bytes()
    runner = _load_pack_module()
    for identity, path in runner.declared_case_input_bindings(copied_case, pack):
        assert path.read_bytes() == originals[bindings[identity]].read_bytes()


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_intake_draft_recovers_without_execution_and_refuses_lost_update(
    financial_intake,
):
    env, output, _, pack, case_id, bindings = financial_intake
    fields = {"pack_id": pack, "case_input_id": case_id, "source_bindings": bindings}
    result = rpc_program(
        env,
        execute_script(financial_intake)
        + f"""
const save={{work_ref:exact.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields:{json.dumps(fields)}}};
const stored=payload(call('vera_workspace_financial_draft_save',save));
const stale=call('vera_workspace_financial_draft_save',{{...save,fields:{{pack_id:'',case_input_id:'',source_bindings:{{}}}}}});
const result={{stored,stale,after:payload(call('vera_workspace_financial_setup',{{work_ref:exact.work_ref}}))}};
""",
    )
    assert result["after"]["draft"] == fields
    assert result["after"]["versions"] == []
    assert result["stale"]["isError"] is True
    assert list(output.glob("financial-*")) == []


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
@pytest.mark.parametrize(
    "change",
    [
        "case_input_id:'foreign'",
        "item_id:'foreign'",
        "source_bindings:{}",
        "source_bindings:{'artifact.synthetic':'foreign'}",
        "revision:'stale'",
    ],
)
def test_native_financial_foreign_selection_or_incomplete_bindings_do_not_execute(
    financial_intake, change
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        execute_script(financial_intake)
        + f"const result=call('vera_workspace_financial_execute',{{...executeArgs,{change}}});",
    )
    assert result["isError"] is True
    assert list(output.glob("financial-*")) == []


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_viewer_cannot_execute_reviewed_case(financial_intake):
    env, output, *_ = financial_intake
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": "VIEWER"},
        execute_script(financial_intake)
        + "const result=call('vera_workspace_financial_execute',executeArgs);",
    )
    assert result["isError"] is True
    assert list(output.glob("financial-*")) == []


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_interrupted_producer_intent_blocks_retry_and_preserves_sources(
    financial_intake, monkeypatch
):
    env, output, *_ = financial_intake
    fixture = rpc_program(
        env, execute_script(financial_intake) + "const result={args:executeArgs};"
    )
    module = workspace_module()
    import native_financial_execution as engine

    original_bridge = engine.bridge

    def interrupt(root, request):
        if request["operation"] == "execute":
            raise OSError("Fictional public execution interrupted")
        return original_bridge(root, request)

    monkeypatch.setattr(engine, "bridge", interrupt)
    args = fixture["args"]
    args.pop("review_ticket")
    with pytest.raises(OSError, match="Fictional public execution interrupted"):
        module.dispatch("vera_workspace_financial_execute", args)
    monkeypatch.setattr(engine, "bridge", original_bridge)
    result = rpc_program(
        env,
        execute_script(financial_intake)
        + "const result={setup,refused:call('vera_workspace_financial_execute',executeArgs)};",
    )
    assert result["setup"]["recovery_required"] is True
    assert result["refused"]["isError"] is True
    assert len(list(output.glob("financial-*"))) == 1
    assert next(output.glob("financial-*")).joinpath("case/case.json").is_file()


def archive_environment(env: dict, binding: dict, output: Path) -> dict:
    """Register the same real fictional client for the shared closure boundary."""
    configured = {
        **env,
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-financial-archive",
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(
            Path(binding["client_root"]).parent.parent / "private-state"
        ),
    }
    archive_cli(
        configured,
        "configure",
        "--archive-root",
        str(Path(binding["client_root"]).parent),
    )
    configured.pop("VERA_WORKSPACE_BINDINGS")
    return configured


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
@pytest.mark.parametrize("mode", ["operator", "archive"])
def test_native_financial_unexecuted_run_offers_intake_without_false_recovery(
    financial_intake, mode
):
    env, output, binding, *_ = financial_intake
    args = {}
    if mode == "archive":
        env = archive_environment(env, binding, output)
        args = {k: binding[k] for k in ("client_id", "engagement_id")}
    result = rpc_program(
        env,
        f"const result=payload(call('vera_workspace_open',{json.dumps(args)}));",
    )
    identity = "work_ref" if mode == "operator" else "run_id"
    row = next(r for r in result["works"] if r[identity] == binding[identity])
    assert row["setup_available"] is True
    assert row.get("review_status") != "specialist_recovery_required"
    assert list(output.glob("financial-*")) == []


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
@pytest.mark.parametrize("changed", ["case/case.json", "prepared/reconciliation.json"])
def test_native_financial_changed_version_refuses_read_execution_and_archive_closure(
    financial_intake, changed
):
    env, output, binding, *_ = financial_intake
    stored = rpc_program(
        env,
        execute_script(financial_intake)
        + "const result={execution:payload(call('vera_workspace_financial_execute',executeArgs)),args:executeArgs};",
    )
    path = output / stored["execution"]["source_ref"] / changed
    path.write_bytes(path.read_bytes() + b"\n")
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        env,
        f"""
const result={{read:call('vera_workspace_financial_view',{{work_ref:'fictional-financial',source_ref:{json.dumps(stored['execution']['source_ref'])}}}),
execute:call('vera_workspace_financial_execute',{json.dumps(stored['args'])})}};
""",
    )
    closure = rpc_program(
        archive_environment(env, binding, output),
        f"const result=call('vera_workspace_archive_closure',{json.dumps(selected)});",
    )
    assert result["read"]["isError"] is True
    assert result["execute"]["isError"] is True
    assert closure["isError"] is True
    assert "artifacts changed" in closure["content"][0]["text"]
    assert len(list(output.glob("financial-*"))) == 1


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_wrong_registered_source_preserves_refused_intent_and_closure_gate(
    financial_intake,
):
    env, output, binding, _, case_id, bindings = financial_intake
    wrong = dict.fromkeys(bindings, case_id)
    result = rpc_program(
        env,
        execute_script(financial_intake)
        + f"""
const refused=call('vera_workspace_financial_execute',{{...executeArgs,source_bindings:{json.dumps(wrong)}}});
const result={{refused,after:payload(call('vera_workspace_financial_setup',{{work_ref:exact.work_ref}}))}};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["after"]["recovery_required"] is True
    assert result["after"]["versions"] == []
    retained = next(output.glob("financial-*"))
    assert (retained / "case/case.json").is_file()
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    closure = rpc_program(
        archive_environment(env, binding, output),
        f"const result=call('vera_workspace_archive_closure',{json.dumps(selected)});",
    )
    assert closure["isError"] is True
    assert "recovery before output closure" in closure["content"][0]["text"]


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_two_versions_keep_exact_selection_and_refuse_stale_model_context(
    financial_intake,
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        execute_script(financial_intake)
        + """
const first=payload(call('vera_workspace_financial_execute',executeArgs));
const firstView=payload(call('vera_workspace_financial_view',{work_ref:exact.work_ref,source_ref:first.source_ref}));
const artifact=firstView.items.find(v=>v.title==='reconciliation.json');
const before=payload(call('vera_workspace_financial_view',{work_ref:exact.work_ref,source_ref:first.source_ref,item_id:artifact.id}));
const fresh=payload(call('vera_workspace_financial_case',exact));
const second=payload(call('vera_workspace_financial_execute',{...executeArgs,revision:fresh.revision,review_ticket:fresh.review_ticket,idempotency_key:'fictional-financial-second'}));
const stale=call('vera_workspace_financial_explain',{work_ref:exact.work_ref,source_ref:first.source_ref,item_id:artifact.id,revision:before.revision});
const after=payload(call('vera_workspace_financial_view',{work_ref:exact.work_ref,source_ref:first.source_ref,item_id:artifact.id}));
const explained=call('vera_workspace_financial_explain',{work_ref:exact.work_ref,source_ref:first.source_ref,item_id:artifact.id,revision:after.revision}).structuredContent;
const result={first,second,stale,after,explained,setup:payload(call('vera_workspace_financial_setup',{work_ref:exact.work_ref}))};
""",
    )
    assert result["first"]["source_ref"] != result["second"]["source_ref"]
    assert len(result["setup"]["versions"]) == 2
    assert result["stale"]["isError"] is True
    assert (
        result["after"]["data"]["selection"]["source_ref"]
        == result["first"]["source_ref"]
    )
    assert result["explained"]["source_ref"] == result["first"]["source_ref"]
    assert result["explained"]["selected"] == result["after"]["selection"]
    assert len(list(output.glob("financial-*"))) == 2


@pytest.mark.parametrize("financial_intake", ["net_debt"], indirect=True)
def test_native_financial_cleared_draft_generation_refuses_prior_empty_state_replay(
    financial_intake,
):
    env, output, *_ = financial_intake
    result = rpc_program(
        env,
        execute_script(financial_intake)
        + """
const empty={pack_id:'',case_input_id:'',source_bindings:{}};
const save={work_ref:exact.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft_revision,fields:empty};
const first=payload(call('vera_workspace_financial_draft_save',save));
const cleared=payload(call('vera_workspace_financial_draft_save',{...save,expected_draft_revision:first.draft_revision}));
const replay=call('vera_workspace_financial_draft_save',{...save,fields:{...empty,pack_id:exact.pack_id}});
const result={first,cleared,replay,after:payload(call('vera_workspace_financial_setup',{work_ref:exact.work_ref}))};
""",
    )
    assert result["first"]["draft_revision"] != result["cleared"]["draft_revision"]
    assert result["replay"]["isError"] is True
    assert result["after"]["draft"]["pack_id"] == ""
    assert list(output.glob("financial-*")) == []
