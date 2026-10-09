"""Actual merger store and source MCP; all people and evidence are fictional."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

from tests.plugins.test_fusione_guidata import api, case, fact_data  # noqa: F401
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import workspace_module

__all__ = []


def bind_case(tmp_path, store, *, case_actor="admin", proposals=None):
    """Declare exact private cases; use existing public grants without replacing them."""
    config = tmp_path / "native-bindings.json"
    config.write_text(
        json.dumps(
            {
                "tenant_id": "fictional-studio",
                "actor_id": "fictional-reviewer",
                "bindings": [
                    {
                        "work_ref": "fictional-merger",
                        "case_dir": str(store.root),
                        "operation_id": store.metadata["operation_id"],
                        "case_actor": case_actor,
                        "proposals": proposals or [],
                    }
                ],
            }
        )
    )
    env = {
        **{k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ},
        "VERA_WORKSPACE_TENANT_ID": "fictional-studio",
        "VERA_WORKSPACE_ACTOR_ID": "fictional-reviewer",
        "VERA_WORKSPACE_ROLES": "REVIEWER",
        "VERA_WORKSPACE_PYTHON": sys.executable,
        "VERA_FUSIONE_WORKSPACE_BINDINGS": str(config),
    }
    return env, config


@pytest.fixture
def merger(api, case, tmp_path):
    """Public APIs create records; only host bindings and proposals are test inputs."""
    case.put(
        "fact",
        "Fact",
        fact_data(),
        scope=["alpha"],
        dependencies=[api.reference(case.read("proof"))],
        expected_version=0,
    )
    proposal = tmp_path / "proposal.json"
    proposal.write_text(
        json.dumps(
            {
                "action": "put",
                "object_id": "native_fact",
                "kind": "Fact",
                "data": fact_data(
                    description="Fictional native proposal", value="123.45"
                ),
                "scope": ["alpha"],
                "dependencies": [api.reference(case.read("proof"))],
                "expected_version": 0,
            }
        )
    )
    env, config = bind_case(
        tmp_path,
        case,
        proposals=[{"proposal_ref": "fictional-proposal", "path": str(proposal)}],
    )
    return env, case, proposal, config


PROGRAM = """
const setup=()=>payload(call('vera_workspace_fusion_setup',{work_ref:'fictional-merger'}));
const authority=p=>({work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref,review_ticket:p.review_ticket});
const fields=(operation='apply_proposal')=>({operation,proposal_ref:'fictional-proposal',target_id:'fact',decision_id:'native_confirmation',professional_role:'Fictional professional',scope_text:'Fictional fixture only',confirmation:'Explicit fictional confirmation',note:''});
const save=(p,f)=>payload(call('vera_workspace_fusion_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f}));
const inspect=(p,f)=>payload(call('vera_workspace_fusion_preview',{work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref,fields:f}));
const prepare=(p,f,key)=>{const draft=save(p,f),preview=inspect(p,f);return {...authority(p),expected_draft_revision:draft.draft_revision,fields:f,preview_ref:preview.preview_ref,confirmed:true,idempotency_key:key};};
const execute=args=>payload(call('vera_workspace_fusion_execute',args));
"""


def test_fusion_initial_draft_restores_literal_fields_without_consent(merger):
    env, store, _, _ = merger
    before = store.report()["history"]
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields();f.note='  Literal unfinished note  ';const saved=save(p,f);const result={first:p,saved,restored:setup()};",
    )
    assert len(result["first"]["draft_revision"]) == 64
    assert result["saved"]["saved"] is True
    assert result["restored"]["fields"]["note"] == "  Literal unfinished note  "
    assert result["restored"]["confirmation_restored"] is False
    assert store.report()["history"] == before


def test_fusion_actual_proposal_preview_write_and_exact_retry(merger):
    env, store, _, _ = merger
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields(),preview=inspect(p,f),args=prepare(p,f,'proposal-1');const first=execute(args),retry=execute(args),changed=call('vera_workspace_fusion_execute',{...args,fields:{...f,note:'changed'}});const result={preview,first,retry,changed,after:setup()};",
    )
    assert result["preview"]["preview_only"] is True
    assert result["preview"]["proposed_record"]["data"]["value"] == "123.45"
    assert "sha256" not in result["preview"]["proposed_record"]
    assert {k: v for k, v in result["first"].items() if k != "review_ticket"} == {
        k: v for k, v in result["retry"].items() if k != "review_ticket"
    }
    assert result["changed"]["isError"] is True
    assert store.read("native_fact")["version"] == 1
    assert store.read("native_fact")["data"]["value"] == "123.45"
    assert result["after"]["draft_stale"] is True
    assert result["first"]["result"]["professional_approval_added"] is False
    assert result["first"]["sent_or_filed"] is False


def test_fusion_explicit_separate_approval_binds_actual_current_record(merger, api):
    env, store, _, _ = merger
    target = api.reference(store.read("fact"))
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields('approve'),preview=inspect(p,f),args=prepare(p,f,'approval-1');const result={preview,saved:execute(args),after:setup()};",
    )
    decision = store.read("native_confirmation")
    assert decision["kind"] == "Decision"
    assert decision["data"]["target"] == target
    assert decision["data"]["professional_role"] == "Fictional professional"
    assert result["preview"]["professional_confirmation_recorded"] is False
    assert store.status("fact")["review_state"] == "approved_for_defined_scope"
    assert result["saved"]["authenticated_signature"] is False


def test_fusion_exports_replay_public_formatter_and_return_exact_download(merger):
    env, store, _, _ = merger
    history = store.report()["history"]
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields('export'),args=prepare(p,f,'export-1'),saved=execute(args),after=setup(),item=after.data.exports[0];const artifact=payload(call('vera_workspace_fusion_artifact',{work_ref:after.work_ref,revision:after.revision,source_ref:after.source_ref,export_ref:item.export_ref,artifact_ref:'case-report.json'}));const result={saved,after,artifact};",
    )
    export = result["after"]["data"]["exports"][0]
    assert export["case_report"]["history"] == history
    assert export["model_report"]["workflow_id"] == "fusione-guidata"
    assert (
        json.loads(base64.b64decode(result["artifact"]["base64"]))
        == export["case_report"]
    )
    assert store.report()["history"] == history
    assert result["saved"]["archive_engagements_changed"] is False


@pytest.mark.parametrize(
    "variant", ["source", "ticket", "noncanonical_ticket", "cas", "preview", "consent"]
)
def test_fusion_changed_authority_or_consent_refuses_without_case_write(
    merger, variant
):
    env, store, _, _ = merger
    before = store.report()["history"]
    change = {
        "source": "args.source_ref='wrong';",
        "ticket": "args.review_ticket=args.review_ticket.slice(0,-1)+(args.review_ticket.endsWith('0')?'1':'0');",
        "noncanonical_ticket": "args.review_ticket+='invalid';",
        "cas": "args.expected_draft_revision='wrong';",
        "preview": "args.preview_ref='wrong';",
        "consent": "args.confirmed=false;",
    }[variant]
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields(),args=prepare(p,f,'denied-1');"
        + change
        + "const result=call('vera_workspace_fusion_execute',args);",
    )
    assert result.get("isError") is True
    assert store.report()["history"] == before


@pytest.mark.parametrize("authority", ["reader", "viewer", "editor"])
def test_fusion_case_and_operator_roles_keep_approval_separate(merger, authority):
    env, store, _, config = merger
    if authority == "viewer":
        env["VERA_WORKSPACE_ROLES"] = "VIEWER"
    else:
        store.grant("restricted", role=authority, entities=["alpha"])
        value = json.loads(config.read_bytes())
        value["bindings"][0]["case_actor"] = "restricted"
        config.write_text(json.dumps(value))
    before = store.report()["history"]
    body = "const p=setup(),f=fields('approve');const draft=call('vera_workspace_fusion_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f});let denied=draft;if(!draft.isError){const preview=inspect(p,f);denied=call('vera_workspace_fusion_execute',{...authority(p),expected_draft_revision:payload(draft).draft_revision,fields:f,preview_ref:preview.preview_ref,confirmed:true,idempotency_key:'denied-role'});}const result={p,denied};"
    result = rpc_program(env, PROGRAM + body)
    assert result["p"]["can_approve"] is False
    assert result["denied"]["isError"] is True
    assert store.report()["history"] == before


def test_fusion_company_reader_sees_all_own_versions_and_no_foreign_records(merger):
    env, store, _, config = merger
    store.put(
        "beta_fact",
        "Fact",
        fact_data(
            description="Fictional private beta", fact_status="unknown", value=None
        ),
        scope=["beta"],
        dependencies=[],
        expected_version=0,
    )
    store.put(
        "fact",
        "Fact",
        fact_data(value="101.00"),
        scope=["alpha"],
        dependencies=store.read("fact")["dependencies"],
        expected_version=1,
    )
    store.grant("alpha_reader", role="reader", entities=["alpha"])
    value = json.loads(config.read_bytes())
    value["bindings"][0]["case_actor"] = "alpha_reader"
    config.write_text(json.dumps(value))
    result = rpc_program(env, PROGRAM + "const result=setup();")
    history = result["data"]["report"]["history"]
    assert [r["version"] for r in history if r["id"] == "fact"] == [1, 2]
    assert not any(r["id"] in {"beta", "beta_fact"} for r in history)
    assert "Fictional private beta" not in json.dumps(result)
    assert result["can_write"] is False


def test_fusion_stale_private_fields_require_explicit_discard(merger):
    env, store, _, _ = merger
    rpc_program(env, PROGRAM + "const p=setup();const result=save(p,fields());")
    store.put(
        "fact",
        "Fact",
        fact_data(value="102.00"),
        scope=["alpha"],
        dependencies=store.read("fact")["dependencies"],
        expected_version=1,
    )
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),denied=call('vera_workspace_fusion_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:fields()});const cleared=payload(call('vera_workspace_fusion_draft_clear',{...authority(p),expected_draft_revision:p.draft_revision,confirmed:true}));const result={p,denied,cleared,after:setup()};",
    )
    assert result["p"]["draft_stale"] is True
    assert result["denied"]["isError"] is True
    assert set(result["after"]["fields"].values()) == {""}
    assert result["after"]["draft_stale"] is False
    assert store.read("fact")["version"] == 2


@pytest.mark.parametrize(
    "variant", ["owner", "foreign_case", "grant_proposal", "symlink"]
)
def test_fusion_host_scope_rejects_foreign_or_unsafe_inputs(merger, variant):
    env, store, proposal, config = merger
    value = json.loads(config.read_bytes())
    if variant == "owner":
        value["actor_id"] = "another-operator"
    elif variant == "foreign_case":
        value["bindings"][0]["operation_id"] = "op_" + "f" * 32
    elif variant == "grant_proposal":
        proposal.write_text(json.dumps({"action": "grant", "actor": "forged"}))
    else:
        link = proposal.with_name("linked.json")
        link.symlink_to(proposal)
        value["bindings"][0]["proposals"][0]["path"] = str(link)
    config.write_text(json.dumps(value))
    before = store.report()["history"]
    result = rpc_program(
        env,
        "const result=call('vera_workspace_fusion_setup',{work_ref:'fictional-merger'});",
    )
    assert result["isError"] is True
    assert store.report()["history"] == before


def test_fusion_current_evidence_download_uses_exact_record_reference(merger, api):
    env, store, _, _ = merger
    # The public MCP document selector is SHA256 of canonical exact reference JSON.
    reference = api.reference(store.read("proof"))
    document_ref = hashlib.sha256(
        json.dumps(
            reference, ensure_ascii=False, sort_keys=True, allow_nan=False
        ).encode()
    ).hexdigest()
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup();const result=payload(call('vera_workspace_fusion_artifact',{work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref,document_ref:"
        + json.dumps(document_ref)
        + "}));",
    )
    assert base64.b64decode(result["base64"]) == b"Synthetic source evidence"
    assert result["mime_type"] == "application/octet-stream"


@pytest.fixture
def p1_merger(api, tmp_path):
    demo_module = importlib.import_module("fusione_p1_demo")
    demo = demo_module.prepare_case(tmp_path / "p1", "ordinary_domestic_oic")
    request = json.loads((demo.root / "exchange-request.json").read_bytes())
    request["object_id"] = "native_exchange"
    request["expected_version"] = 0
    proposal = demo.root / "native-request.json"
    proposal.write_text(json.dumps(request))
    env, config = bind_case(
        tmp_path,
        demo.store,
        case_actor="synthetic_reviewer",
        proposals=[{"proposal_ref": "fictional-proposal", "path": str(proposal)}],
    )
    return env, demo, config


def test_fusion_p1_public_workpaper_preserves_both_archive_engagements(p1_merger):
    env, demo, _ = p1_merger
    before = {
        name: {
            str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }
        for name, (root, _, _) in demo.clients.items()
    }
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields(),preview=inspect(p,f),args=prepare(p,f,'p1-1');const result={preview,saved:execute(args),after:setup()};",
    )
    actual = demo.store.read("native_exchange")
    assert actual["kind"] == "ExchangeModel"
    assert actual["data"] == result["preview"]["proposed_record"]["data"]
    assert actual["scope"] == ["alpha", "beta"]
    assert result["saved"]["archive_engagements_changed"] is False
    assert {
        name: {
            str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }
        for name, (root, _, _) in demo.clients.items()
    } == before


def test_fusion_uncertain_public_write_retains_intent_and_refuses_repeat(
    merger, monkeypatch
):
    env, store, _, _ = merger
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    workspace = workspace_module()
    native = importlib.import_module("native_fusion")
    actual_producer = native.producer

    def interrupted(module, root, row, action, **arguments):
        if action == "apply_proposal":
            raise ValueError("Fictional transport interruption before public write")
        return actual_producer(module, root, row, action, **arguments)

    monkeypatch.setattr(native, "producer", interrupted)
    before = store.report()["history"]
    page = workspace.dispatch(
        "vera_workspace_fusion_setup", {"work_ref": "fictional-merger"}
    )
    selected = dict(
        native.EMPTY, operation="apply_proposal", proposal_ref="fictional-proposal"
    )
    authority = {k: page[k] for k in ("work_ref", "revision", "source_ref")}
    saved = workspace.dispatch(
        "vera_workspace_fusion_draft_save",
        {
            **authority,
            "expected_draft_revision": page["draft_revision"],
            "fields": selected,
        },
    )
    preview = workspace.dispatch(
        "vera_workspace_fusion_preview", {**authority, "fields": selected}
    )
    arguments = {
        **authority,
        "expected_draft_revision": saved["draft_revision"],
        "fields": selected,
        "preview_ref": preview["preview_ref"],
        "confirmed": True,
        "idempotency_key": "interrupted-1",
    }
    with pytest.raises(ValueError, match="transport interruption"):
        workspace.dispatch("vera_workspace_fusion_execute", arguments)
    reopened = workspace.dispatch(
        "vera_workspace_fusion_setup", {"work_ref": page["work_ref"]}
    )
    with pytest.raises(ValueError, match="uncertain"):
        workspace.dispatch("vera_workspace_fusion_execute", arguments)
    assert len(reopened["pending_operations"]) == 1
    assert store.report()["history"] == before


def test_fusion_altered_export_bytes_refuse_readback(merger):
    env, store, _, _ = merger
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields('export');const result=execute(prepare(p,f,'export-alter'));",
    )
    destination = Path(result["result"]["directory"])
    (destination / "case-report.md").write_text("Changed fictional export")
    after = rpc_program(
        env,
        "const result=call('vera_workspace_fusion_setup',{work_ref:'fictional-merger'});",
    )
    assert after["isError"] is True
    assert "scope changed" in after["content"][0]["text"]


def test_fusion_export_cannot_restore_revoked_company_access(merger):
    env, store, _, config = merger
    store.grant("scoped_reviewer", role="reviewer", entities=["alpha", "beta"])
    value = json.loads(config.read_bytes())
    value["bindings"][0]["case_actor"] = "scoped_reviewer"
    config.write_text(json.dumps(value))
    rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields('export');const result=execute(prepare(p,f,'export-revoke'));",
    )
    store.grant("scoped_reviewer", role="reader", entities=["alpha"])
    result = rpc_program(
        env,
        "const result=call('vera_workspace_fusion_setup',{work_ref:'fictional-merger'});",
    )
    assert result["isError"] is True
    assert set(result["_meta"]["workspace"]) == {"error"}
    assert store.read("beta")["kind"] == "Entity"


def test_fusion_whole_read_keeps_every_record_without_sampling(merger, api):
    env, store, _, _ = merger
    proof = api.reference(store.read("proof"))
    for number in range(71):
        store.put(
            f"complete_fact_{number}",
            "Fact",
            fact_data(description=f"Fictional complete fact {number}"),
            scope=["alpha"],
            dependencies=[proof],
            expected_version=0,
        )
    report = store.report()
    result = rpc_program(
        env,
        "const result=call('vera_workspace_fusion_setup',{work_ref:'fictional-merger'});",
    )
    private = result["_meta"]["workspace"]["data"]["report"]
    assert private["history"] == report["history"]
    assert len(private["records"]) == len(report["records"])
    assert "Fictional complete fact 70" in json.dumps(private)
    assert "Fictional complete fact 70" not in json.dumps(result["content"])


def test_fusion_p1_export_keeps_workpaper_outputs_and_canonical_report(p1_merger):
    env, demo, _ = p1_merger
    before = demo.store.report()["history"]
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields('export');execute(prepare(p,f,'p1-export'));const result=setup();",
    )
    export = result["data"]["exports"][0]
    assert {row["name"] for row in export["artifacts"]} == {
        "case-report.json",
        "case-report.md",
        "model_data_report.json",
        "model_data_report.md",
        "p1-workpapers.md",
        "p1-workpapers.html",
    }
    assert export["case_report"]["history"] == before
    assert export["model_report"]["workflow_id"] == "fusione-guidata"
    assert demo.store.report()["history"] == before
