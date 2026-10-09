"""Native signed intake/supervision against fictional actual Archive/public jobs."""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_passive_audit import audit_workspace
from tests.plugins.test_vera_native_workspace import configure, workspace_module


@pytest.fixture
def passive_service(audit_workspace, tmp_path, monkeypatch):
    work = audit_workspace
    binding = {
        "work_ref": "fictional-passive",
        "client_root": str(work.work["client_root"]),
        **{key: work.work[key] for key in ("client_id", "engagement_id", "run_id")},
        "workflow_id": "passive-invoice-audit",
    }
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    choices = {
        identity: role
        for role, identity in work.recipe["inputs"].items()
        if role != "invoices"
    }
    choices.update(
        {identity: "invoices" for identity in work.recipe["inputs"]["invoices"]}
    )
    fields = {
        "choices": choices,
        "controls": {
            key: str(value) if value is not None else ""
            for key, value in work.recipe["controls"].items()
        },
        "operator_ref": "Fictional authorized operator",
        "decision_basis": "Fictional actual source scope and reviewed mapping; no accounting approval.",
    }
    return work, binding, env, fields, workspace_module()


def prepare(fields):
    return (
        """
const setup=payload(call('vera_workspace_passive_setup',{work_ref:'fictional-passive'}));
const authority=p=>({work_ref:p.work_ref,revision:p.revision,review_ticket:p.review_ticket,expected_draft_revision:p.draft.draft_revision,...(p.data.selection.source_ref?{source_ref:p.data.selection.source_ref}:{})});
"""
        + "const fields="
        + json.dumps(fields)
        + ";\n"
        + """
const drafted=payload(call('vera_workspace_passive_draft_save',{...authority(setup),fields}));
const fresh=payload(call('vera_workspace_passive_setup',{work_ref:setup.work_ref}));
const qualified=payload(call('vera_workspace_passive_qualify',{...authority(fresh),fields,human_reviewed:true}));
"""
    )


@pytest.mark.parametrize("audit_workspace", ["fresh", "ordinary"], indirect=True)
def test_native_passive_supervisor_launch_and_same_key_retry_preserve_actual_job(
    passive_service,
):
    work, binding, env, fields, module = passive_service
    result = rpc_program(
        env,
        prepare(fields)
        + """
const launchArgs={...authority(qualified),human_reviewed:true,idempotency_key:'fictional-launch'};
const accepted=payload(call('vera_workspace_passive_launch',launchArgs));
const retry=payload(call('vera_workspace_passive_launch',launchArgs));
let status;const deadline=Date.now()+15000;
do{status=payload(call('vera_workspace_passive_status',{work_ref:setup.work_ref}));}while((status.operation_live||status.operation.status==='accepted'||status.operation.status==='running')&&Date.now()<deadline);
const view=payload(call('vera_workspace_passive_view',{work_ref:status.work_ref,revision:status.revision,source_ref:status.data.selection.source_ref,view:'population'}));
const result={accepted,retry,status,view};
""",
    )
    assert result["accepted"]["operation_ref"] == result["retry"]["operation_ref"]
    assert result["status"]["operation"]["status"] == "completed"
    assert result["status"]["operation_live"] is False
    assert result["view"]["data"]["summary"]["population"] == 1
    assert result["view"]["data"]["professional_approval"] is False
    assert module.load_binding(binding)["run"]["status"] == "running"
    private = work.output.parent / ".native-workspace"
    assert len(list(private.glob("passive-operation-*.json"))) == 1
    assert not (private / "write.lock").exists()
    assert len(list(private.glob("passive-qualification-*.json"))) == 1


def test_native_passive_source_excerpt_and_draft_cas_never_choose_roles(
    passive_service,
):
    work, _, env, fields, _ = passive_service
    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_passive_setup',{work_ref:'fictional-passive'}));
const authority={work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:''};
const source=payload(call('vera_workspace_passive_source',{work_ref:setup.work_ref,revision:setup.revision,item_id:setup.items[0].id}));
const first=payload(call('vera_workspace_passive_draft_save',{...authority,fields:{operator_ref:'actual unfinished reference'}}));
const cas=call('vera_workspace_passive_draft_save',{...authority,fields:{operator_ref:'lost update'}});
const resumed=payload(call('vera_workspace_passive_setup',{work_ref:setup.work_ref}));
const result={setup,source,first,cas,resumed};
""",
    )
    assert result["setup"]["draft"]["fields"] == {}
    assert result["setup"]["qualified"] is None
    assert result["source"]["selection"]["id"] == result["setup"]["items"][0]["id"]
    assert result["cas"]["isError"] is True
    assert result["resumed"]["draft"]["fields"] == {
        "operator_ref": "actual unfinished reference"
    }
    assert "human_reviewed" not in result["resumed"]["draft"]["fields"]


def test_native_passive_forged_ticket_and_missing_confirmation_do_not_start_worker(
    passive_service,
):
    work, _, env, fields, _ = passive_service
    result = rpc_program(
        env,
        prepare(fields)
        + """
const args={...authority(qualified),human_reviewed:true,idempotency_key:'forged'};
const forged=call('vera_workspace_passive_launch',{...args,review_ticket:args.review_ticket.slice(0,-1)+'x'});
const missing=call('vera_workspace_passive_launch',{...args,human_reviewed:false});
const result={forged,missing};
""",
    )
    assert result["forged"]["isError"] is True
    assert result["missing"]["isError"] is True
    assert not list(
        (work.output.parent / ".native-workspace").glob("passive-operation-*.json")
    )


def test_native_passive_qualification_and_job_view_do_not_leak_population_to_model(
    passive_service,
):
    _, _, env, fields, _ = passive_service
    result = rpc_program(
        env,
        prepare(fields)
        + """
const view=payload(call('vera_workspace_passive_view',{work_ref:qualified.work_ref,revision:qualified.revision,source_ref:qualified.data.selection.source_ref,view:'population'}));
const explanation=call('vera_workspace_passive_explain',{work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,view:'population',item_id:view.items[0].id}).structuredContent;
const result={view,explanation};
""",
    )
    assert (
        result["explanation"]["untrusted_evidence"]["id"]
        == result["view"]["items"][0]["id"]
    )
    assert "summary" not in result["explanation"]
    assert "full_population" not in result["explanation"]
    assert result["explanation"]["untrusted_evidence"]["evidence_page"][
        "coverage"
    ].startswith("This exact member page")


def test_native_passive_files_are_actual_public_outputs_and_private_to_app(
    passive_service,
):
    work, _, env, fields, _ = passive_service
    result = rpc_program(
        env,
        prepare(fields)
        + """
const args={work_ref:qualified.work_ref,revision:qualified.revision,source_ref:qualified.data.selection.source_ref};
const raw=call('vera_workspace_passive_outputs',args);
const outputs=payload(raw);
const stale=call('vera_workspace_passive_outputs',{...args,revision:'stale'});
const result={raw,outputs,stale};
""",
    )
    assert {row["name"] for row in result["outputs"]["outputs"]} == {
        "full_population.jsonl",
        "ledger_entries_without_invoice.jsonl",
        "run_summary.json",
        "run_summary.md",
        "exception_workpaper.xlsx",
    }
    assert all(Path(row["path"]).is_file() for row in result["outputs"]["outputs"])
    assert str(work.output) not in json.dumps(result["raw"]["content"])
    assert result["raw"]["structuredContent"] == {
        "status": "ready",
        "work_ref": "fictional-passive",
    }
    assert result["stale"]["isError"] is True
    assert result["outputs"]["professional_approval"] is False


def test_native_passive_qualification_tamper_is_not_hidden_by_rehashed_state(
    passive_service,
):
    work, _, env, fields, module = passive_service
    rpc_program(env, prepare(fields) + "const result={qualified:true};")
    path = work.output.parent / ".native-workspace/passive-state.json"
    state = json.loads(path.read_text())
    state["operator_review"]["decision_basis"] = "Changed after qualification"
    state.pop("record_sha256")
    state["record_sha256"] = module.digest(state)
    path.write_text(json.dumps(state))
    result = rpc_program(
        env,
        "const result=call('vera_workspace_passive_setup',{work_ref:'fictional-passive'});",
    )
    assert result["isError"] is True
    assert "immutable qualification" in result["content"][0]["text"]
    assert not list(path.parent.glob("passive-operation-*.json"))


def test_native_passive_another_actor_must_requalify_before_launch(passive_service):
    work, _, env, fields, _ = passive_service
    result = rpc_program(
        env,
        prepare(fields)
        + """
process.env.VERA_WORKSPACE_ACTOR_ID='another-fictional-actor';
const fs=require('node:fs'),configPath=process.env.VERA_WORKSPACE_BINDINGS;
const config=JSON.parse(fs.readFileSync(configPath));config.actor_id=process.env.VERA_WORKSPACE_ACTOR_ID;fs.writeFileSync(configPath,JSON.stringify(config));
const next=payload(call('vera_workspace_passive_setup',{work_ref:qualified.work_ref}));
const attempted=call('vera_workspace_passive_launch',{...authority(next),human_reviewed:true,idempotency_key:'foreign-actor'});
const result={next,attempted};
""",
    )
    assert result["next"]["can_launch"] is False
    assert result["next"]["draft"]["fields"] == {}
    assert result["attempted"]["isError"] is True
    assert not list(
        (work.output.parent / ".native-workspace").glob("passive-operation-*.json")
    )


def test_native_passive_actual_os_lease_distinguishes_marker_from_live_owner(
    tmp_path, audit_workspace
):
    from native_passive_service import lease, lease_alive

    path = tmp_path / "lease.lock"
    with lease(path, create=True):
        assert lease_alive(path) is True
    assert path.is_file()
    assert lease_alive(path) is False


def test_native_passive_changed_global_guard_is_preserved_for_recovery(
    tmp_path, audit_workspace
):
    from native_passive_supervisor import producer_guard

    path = tmp_path / "write.lock"
    with pytest.raises(ValueError, match="preserve uncertain job"):
        with producer_guard(path, "owned-operation"):
            path.write_text("foreign-change")
    assert path.read_text() == "foreign-change"


@pytest.mark.parametrize(
    "surface,audit_workspace",
    [("codex", "fresh"), ("cowork", "cowork")],
    indirect=["audit_workspace"],
)
def test_native_passive_supervisor_fresh_packages_preserve_runtime_boundary(
    passive_service, tmp_path, surface
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    _, _, env, fields, _ = passive_service
    builder = load_builder(
        "build_codex_plugin_zip" if surface == "codex" else "build_claude_plugin_zip"
    )
    if surface == "codex":
        vera = next(p for p in builder.load_bundles() if p.name == "vera")
        entries, prefix = (
            builder.expected_zip_entries(vera),
            vera.package_root + "/plugins/vera/",
        )
    else:
        _, packages = builder.load_configuration()
        vera = next(p for p in packages if p.plugin == "vera")
        entries, prefix = builder.claude_package_entries(vera), ""
    target = tmp_path / "packaged"
    for name, data in entries.items():
        if name.startswith(prefix):
            path = target / name[len(prefix) :]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    result = rpc_program(
        env,
        prepare(fields)
        + """
const accepted=payload(call('vera_workspace_passive_launch',{...authority(qualified),human_reviewed:true,idempotency_key:'packaged-job'}));
let status;const deadline=Date.now()+15000;
do{status=payload(call('vera_workspace_passive_status',{work_ref:setup.work_ref}));}while((status.operation_live||status.operation.status==='accepted'||status.operation.status==='running')&&Date.now()<deadline);
const result={accepted,status};
""",
        server=target / "mcp/workspace.cjs",
    )
    assert result["status"]["operation_live"] is False
    assert result["status"]["runtime"] == (
        "codex-luna" if surface == "codex" else "cowork-haiku"
    )
    assert result["status"]["operation"]["status"] == (
        "completed" if surface == "codex" else "awaiting_semantic_review"
    )
    assert result["status"]["run_status"] == "running"


def pending_launch(passive_service, monkeypatch):
    """Retain a real backend launch intent while simulating only OS spawn failure."""
    import native_passive_service as service
    import native_passive_supervisor as supervisor

    work, binding, env, fields, module = passive_service
    rpc_program(env, prepare(fields) + "const result={qualified:true};")
    page = module.dispatch(
        "vera_workspace_passive_setup", {"work_ref": binding["work_ref"]}
    )
    actual = service.subprocess

    def refused_spawn(*args, **kwargs):
        raise OSError("Fictional OS spawn fault")

    monkeypatch.setattr(
        service,
        "subprocess",
        SimpleNamespace(
            run=actual.run,
            Popen=refused_spawn,
            PIPE=actual.PIPE,
            DEVNULL=actual.DEVNULL,
        ),
    )
    args = {
        "work_ref": binding["work_ref"],
        "revision": page["revision"],
        "source_ref": page["data"]["selection"]["source_ref"],
        "expected_draft_revision": page["draft"]["draft_revision"],
        "human_reviewed": True,
        "idempotency_key": "fault-intent",
    }
    with pytest.raises(OSError, match="spawn fault"):
        module.dispatch("vera_workspace_passive_launch", args)
    private = work.output.parent / ".native-workspace"
    path = next(private.glob("passive-operation-*.json"))
    monkeypatch.setitem(sys.modules, "native_workspace", module)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(supervisor.__file__),
            (
                str(work.plan["root"])
                if "root" in work.plan
                else str(
                    Path(__file__).resolve().parents[2]
                    / "plugins/passive-invoice-audit"
                )
            ),
            str(path),
        ],
    )
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(
        supervisor, "signal", SimpleNamespace(SIGTERM=15, signal=lambda *args: None)
    )
    return work, binding, module, supervisor, path


def test_native_passive_supervisor_output_race_blocks_worker_and_retains_intent(
    passive_service, monkeypatch
):
    import native_passive_audit as audit

    work, binding, module, supervisor, path = pending_launch(
        passive_service, monkeypatch
    )
    concurrent = work.output / "concurrent-specialist.txt"
    concurrent.write_text("Fictional externally retained output")

    def must_not_run(*args):
        pytest.fail("Changed output must be refused before producer execution")

    monkeypatch.setattr(audit, "run_job", must_not_run)
    with pytest.raises(ValueError, match="output changed"):
        supervisor.main()
    receipt = json.loads(path.read_text())
    assert receipt["status"] == "uncertain"
    assert concurrent.read_text() == "Fictional externally retained output"
    assert (
        module.dispatch(
            "vera_workspace_passive_setup", {"work_ref": binding["work_ref"]}
        )["interrupted"]
        is True
    )


def test_native_passive_supervisor_guard_cleanup_fault_never_commits_completed(
    passive_service, monkeypatch
):
    import native_passive_audit as audit

    work, _, _, supervisor, path = pending_launch(passive_service, monkeypatch)
    actual_run = audit.run_job

    def changed_guard(*args):
        actual_run(*args)
        (path.parent / "write.lock").write_text("Foreign guard replacement")

    monkeypatch.setattr(audit, "run_job", changed_guard)
    with pytest.raises(ValueError, match="guard changed"):
        supervisor.main()
    receipt = json.loads(path.read_text())
    assert receipt["status"] == "uncertain"
    assert (path.parent / "write.lock").read_text() == "Foreign guard replacement"
    assert (work.output / "full_population.jsonl").is_file()


def test_native_passive_source_binds_returned_bytes_not_a_second_read(
    passive_service, monkeypatch
):
    import native_passive_service as service

    _, binding, _, _, module = passive_service
    page = module.dispatch(
        "vera_workspace_passive_setup", {"work_ref": binding["work_ref"]}
    )
    monkeypatch.setattr(
        service, "ordinary", lambda path: b"Unregistered transient bytes"
    )
    with pytest.raises(ValueError, match="Registered invoice source changed"):
        module.dispatch(
            "vera_workspace_passive_source",
            {
                "work_ref": binding["work_ref"],
                "revision": page["revision"],
                "item_id": page["items"][0]["id"],
            },
        )
