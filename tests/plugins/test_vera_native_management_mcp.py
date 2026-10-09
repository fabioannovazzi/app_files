"""Real signed MCP/Archive management execution; no installed-host claim."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_vera_native_archive_closure import declare_all, setup
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import archive_cli
from tests.plugins.test_vera_native_management_execution import (  # noqa: F401
    management_run,
)

__all__ = []


@pytest.fixture
def registered_management_run(management_run, tmp_path, monkeypatch):
    """Use maintained Archive discovery instead of the operator-bound test pilot."""
    binding = management_run[2]
    env = {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-management-native",
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(
            tmp_path.parent / ("management-state-" + tmp_path.name)
        ),
    }
    env.pop("VERA_WORKSPACE_BINDINGS")
    archive_cli(
        env, "configure", "--archive-root", str(Path(binding["client_root"]).parent)
    )
    monkeypatch.delenv("VERA_WORKSPACE_BINDINGS")
    for name in ("VERA_STUDIO_ARCHIVE_SESSION_ID", "VERA_STUDIO_ARCHIVE_STATE_DIR"):
        monkeypatch.setenv(name, env[name])
    registered = {
        **binding,
        "work_ref": "studio-"
        + "_".join(
            binding[k].split("_", 1)[1]
            for k in ("client_id", "engagement_id", "run_id")
        ),
    }
    return (*management_run[:2], registered, *management_run[3:])


def begin(fixture) -> str:
    """Save literal choices and use the exact MCP-signed fresh generation."""
    return f"""
const work={{work_ref:{json.dumps(fixture[2]['work_ref'])}}};
const fields={json.dumps(fixture[3])};
const firstSetup=call('vera_workspace_management_setup',work);
const first=payload(firstSetup);
const save={{...work,revision:first.revision,review_ticket:first.review_ticket,expected_draft_revision:first.draft_revision,fields}};
const saved=payload(call('vera_workspace_management_draft_save',save));
const fresh=payload(call('vera_workspace_management_setup',work));
const args={{...work,revision:fresh.revision,review_ticket:fresh.review_ticket,expected_draft_revision:fresh.draft_revision,fields,confirmed:true,idempotency_key:'fictional-management-mcp'}};
"""


def calculated(fixture) -> str:
    return (
        begin(fixture)
        + """
const prepared=payload(call('vera_workspace_management_prepare',args));
const current=payload(call('vera_workspace_management_setup',work));
const exact={...work,revision:current.revision,source_ref:prepared.source_ref};
"""
    )


@pytest.mark.parametrize("management_run", ["reporting", "costing"], indirect=True)
def test_management_mcp_keeps_private_results_and_returns_only_explicit_model_context(
    management_run,
):
    result = rpc_program(
        os.environ.copy(),
        calculated(management_run)
        + """
const files=call('vera_workspace_management_outputs',exact);
const model=call('vera_workspace_management_context',exact);
const caseView=call('vera_workspace_management_case',{...work,revision:current.revision,fields});
const result={prepared,retry:payload(call('vera_workspace_management_prepare',args)),files,model,caseView,firstSetup};
""",
    )
    folder = management_run[1] / result["prepared"]["source_ref"]
    assert result["retry"] == result["prepared"]
    assert len(result["files"]["_meta"]["workspace"]["outputs"]) == 8
    assert "outputs" not in result["files"]["structuredContent"]
    assert "case" not in result["caseView"]["structuredContent"]
    assert "items" not in result["firstSetup"]["structuredContent"]
    assert "_meta" not in result["model"]
    assert result["model"]["structuredContent"]["model_context"] == json.loads(
        (folder / "model_context.json").read_bytes()
    )
    assert "management_control_pack" not in result["model"]["structuredContent"]
    assert result["model"]["structuredContent"]["actual_model_reads_verified"] is False
    assert result["prepared"]["professional_approval"] is False
    assert result["prepared"]["run_completed"] is False


@pytest.mark.parametrize("change", ["ticket", "revision", "confirmation", "draft"])
def test_management_mcp_refuses_invalid_authority_before_writing_outputs(
    management_run, change
):
    mutate = {
        "ticket": "args.review_ticket='not-a-signed-ticket';",
        "revision": "args.revision='stale';",
        "confirmation": "args.confirmed=false;",
        "draft": "args.expected_draft_revision='stale';",
    }[change]
    result = rpc_program(
        os.environ.copy(),
        begin(management_run)
        + mutate
        + "const result=call('vera_workspace_management_prepare',args);",
    )
    assert result["isError"] is True
    assert list(management_run[1].glob("management-*")) == []
    private = management_run[4].ui_state_directory(management_run[1], create=False)
    assert list(private.glob("management-request-*.json")) == []


def test_management_mcp_refuses_stale_window_and_preserves_complete_choices(
    management_run,
):
    result = rpc_program(
        os.environ.copy(),
        begin(management_run)
        + """
const stale=call('vera_workspace_management_draft_save',{...save,fields:{mode:'',input_ids:[],recipe_input_id:''}});
const result={stale,current:payload(call('vera_workspace_management_setup',work))};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["current"]["draft"] == management_run[3]
    assert list(management_run[1].glob("management-*")) == []


def test_management_mcp_viewer_reads_choices_but_cannot_save_or_calculate(
    management_run,
):
    env = {**os.environ, "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        env,
        f"""
const work={{work_ref:{json.dumps(management_run[2]['work_ref'])}}};
const page=payload(call('vera_workspace_management_setup',work));
const args={{...work,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision,fields:{json.dumps(management_run[3])}}};
const result={{page,save:call('vera_workspace_management_draft_save',args),prepare:call('vera_workspace_management_prepare',{{...args,confirmed:true,idempotency_key:'fictional-viewer'}})}};
""",
    )
    assert result["page"]["can_prepare"] is False
    assert result["save"]["isError"] is result["prepare"]["isError"] is True
    assert list(management_run[1].glob("management-*")) == []


def test_management_mcp_completed_archive_retains_exact_readonly_calculation(
    registered_management_run,
):
    management_run = registered_management_run
    first = rpc_program(
        os.environ.copy(),
        calculated(management_run) + "const result={prepared,exact};",
    )
    output, binding = management_run[1:3]
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (output / first["prepared"]["source_ref"]).iterdir()
    }
    write_no_model_report(output, binding["workflow_id"], binding["run_id"])
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        setup(selected)
        + declare_all()
        + f"""
payload(call('vera_workspace_archive_finalize',seal));
const ready=read();
const completed=payload(call('vera_workspace_archive_complete',{{...authority(ready),human_reviewed:true,idempotency_key:'fictional-management-complete'}}));
const work={{work_ref:{json.dumps(binding['work_ref'])}}};
const current=payload(call('vera_workspace_management_setup',work));
const exact={{...work,revision:current.revision,source_ref:{json.dumps(first['prepared']['source_ref'])}}};
const result={{completed,current,files:payload(call('vera_workspace_management_outputs',exact)),model:call('vera_workspace_management_context',exact),write:call('vera_workspace_management_draft_save',{{...work,revision:current.revision,review_ticket:current.review_ticket,expected_draft_revision:current.draft_revision,fields:current.draft}})}};
""",
    )
    assert result["completed"]["status"] == "completed"
    assert result["current"]["can_prepare"] is False
    assert len(result["files"]["outputs"]) == 8
    assert "isError" not in result["model"]
    assert result["write"]["isError"] is True
    assert {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (output / first["prepared"]["source_ref"]).iterdir()
    } == before


@pytest.mark.parametrize("target", ["source", "output"])
def test_management_mcp_refuses_changed_bytes_and_archive_closure(
    management_run, target
):
    first = rpc_program(
        os.environ.copy(),
        calculated(management_run) + "const result={prepared,exact};",
    )
    _, output, binding, choices, api = management_run
    if target == "output":
        path = output / first["prepared"]["source_ref"] / "management_control_facts.md"
    else:
        loaded = api.load_binding(binding)
        receipt = next(
            r
            for r in loaded["input_manifest"]["inputs"]
            if r["binding_id"] == choices["input_ids"][0]
        )
        path = Path(loaded["context_path"]).parent / receipt["execution_relative_path"]
    path.write_bytes(path.read_bytes() + b"\nfictional changed bytes")
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        f"const result={{setup:call('vera_workspace_management_setup',{{work_ref:{json.dumps(binding['work_ref'])}}}),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};",
    )
    assert result["setup"]["isError"] is result["closure"]["isError"] is True


def test_management_mcp_orphaned_execution_refuses_calculation_and_closure(
    management_run,
):
    _, output, binding, _, _ = management_run
    (output / ("management-" + "f" * 64)).mkdir()
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        f"const result={{setup:payload(call('vera_workspace_management_setup',{{work_ref:{json.dumps(binding['work_ref'])}}})),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};",
    )
    assert result["setup"]["status"] == "recovery_required"
    assert result["setup"]["can_prepare"] is False
    assert result["closure"]["isError"] is True
