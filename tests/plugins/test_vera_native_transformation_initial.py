"""Actual public synthetic initialization through source MCP; no native acceptance."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.plugins.test_trasformazione import module  # noqa: F401
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import ROOT, workspace_module

__all__ = []


@pytest.fixture
def initial_case(tmp_path, module):
    root = tmp_path / "synthetic-new-case"
    controls = tmp_path / "private-initialization"
    controls.mkdir()
    config = tmp_path / "initial-bindings.json"
    row = {
        "work_ref": "fictional-init",
        "case_dir": str(root),
        "case_id": "FICTIONAL-TR-INIT",
        "synthetic_only": True,
        "initialize": True,
        "initial_state_dir": str(controls),
        "sources": [],
    }
    config.write_text(
        json.dumps(
            {
                "tenant_id": "fictional-tenant",
                "actor_id": "fictional-actor",
                "bindings": [row],
            }
        )
    )
    env = {
        **{key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ},
        "VERA_WORKSPACE_TENANT_ID": "fictional-tenant",
        "VERA_WORKSPACE_ACTOR_ID": "fictional-actor",
        "VERA_WORKSPACE_ROLES": "REVIEWER",
        "VERA_WORKSPACE_PYTHON": sys.executable,
        "VERA_TRANSFORMATION_WORKSPACE_BINDINGS": str(config),
    }
    return env, root, controls, config, module


PROGRAM = """
const setup=()=>payload(call('vera_workspace_transformation_initial_setup',{work_ref:'fictional-init'}));
const auth=p=>({work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref,review_ticket:p.review_ticket});
const fields={owner:'FICTIONAL_OWNER',purpose:'Only a requested synthetic demonstration'};
const save=(p,f=fields)=>payload(call('vera_workspace_transformation_initial_draft_save',{...auth(p),expected_draft_revision:p.draft_revision,fields:f}));
const createArgs=(p,saved,f=fields)=>({...auth(p),expected_draft_revision:saved.draft_revision,fields:f,confirmed:true,synthetic_only:true,idempotency_key:'fictional-initial-create'});
"""


def test_initial_private_fields_recover_without_creation_or_confirmation(initial_case):
    env, root, _, _, _ = initial_case
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup();save(p,{owner:'  Literal unfinished owner  ',purpose:''});const result=setup();",
    )
    assert result["fields"] == {"owner": "  Literal unfinished owner  ", "purpose": ""}
    assert result["confirmation_restored"] is False
    assert result["draft_revision"]
    assert result["created"] is False
    assert not root.exists()


def test_initial_creation_uses_public_store_preserves_unknowns_and_exact_retry(
    initial_case,
):
    env, root, _, _, module = initial_case
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),saved=save(p),args=createArgs(p,saved),first=payload(call('vera_workspace_transformation_initial_create',args)),second=payload(call('vera_workspace_transformation_initial_create',args)),catalogue=payload(call('vera_workspace_transformation_catalogue',{})),existing=payload(call('vera_workspace_transformation_setup',{work_ref:'fictional-init'}));const result={first,second,catalogue,existing};",
    )
    state = module.CaseStore(root).load()
    assert result["first"] == result["second"]
    assert state["revision"] == 1
    assert state["case"]["id"] == "FICTIONAL-TR-INIT"
    assert state["case"]["owner"] == "FICTIONAL_OWNER"
    assert state["case"]["initial_form"] is None
    assert state["case"]["final_form"] is None
    assert state["case"]["initial_tax_regime"] is None
    assert state["case"]["actual_date"] is None
    assert state["branches"] == {}
    assert state["decisions"] == []
    assert result["existing"]["data"]["state"] == state
    assert result["first"]["professional_validation"] is False
    assert "initialization" not in result["catalogue"]["works"][0]


@pytest.mark.parametrize(
    "change",
    [
        "args.confirmed=false",
        "args.synthetic_only=false",
        "args.fields={owner:'CHANGED',purpose:fields.purpose}",
        "args.expected_draft_revision='wrong'",
        "args.source_ref='wrong'",
    ],
)
def test_initial_creation_rejects_unconfirmed_or_changed_scope_without_public_case(
    initial_case, change
):
    env, root, _, _, _ = initial_case
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),saved=save(p),args=createArgs(p,saved);"
        + change
        + ";const response=call('vera_workspace_transformation_initial_create',args);const result={denied:response.isError===true,after:setup()};",
    )
    assert result["denied"] is True
    assert result["after"]["created"] is False
    assert not root.exists()


def test_initial_incomplete_fields_cannot_create_or_change_unknown_values(initial_case):
    env, root, _, _, _ = initial_case
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f={owner:'FICTIONAL_OWNER',purpose:''},saved=save(p,f),args=createArgs(p,saved,f),response=call('vera_workspace_transformation_initial_create',args);const result={denied:response.isError===true,after:setup()};",
    )
    assert result["denied"] is True
    assert result["after"]["fields"]["purpose"] == ""
    assert not root.exists()


def test_initial_viewer_reads_but_cannot_save_or_create(initial_case):
    env, root, _, _, _ = initial_case
    env["VERA_WORKSPACE_ROLES"] = "VIEWER"
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),response=call('vera_workspace_transformation_initial_draft_save',{...auth(p),expected_draft_revision:p.draft_revision,fields});const result={page:p,denied:response.isError===true};",
    )
    assert result["page"]["can_write"] is False
    assert result["denied"] is True
    assert not root.exists()


@pytest.mark.parametrize("occupant", ["file", "empty-directory"])
def test_initial_rejects_any_existing_target_content_without_overwriting(
    initial_case, occupant
):
    env, root, _, _, _ = initial_case
    root.mkdir()
    path = root / "retained"
    if occupant == "file":
        path.write_text("Keep this existing content")
    else:
        path.mkdir()
    result = rpc_program(
        env,
        PROGRAM
        + "const response=call('vera_workspace_transformation_initial_setup',{work_ref:'fictional-init'});const result={denied:response.isError===true};",
    )
    assert result["denied"] is True
    assert path.exists()
    assert not (root / "history").exists()


def test_initial_catalogue_offers_bound_new_target_without_case_or_model_work(
    initial_case,
):
    env, root, _, _, _ = initial_case
    result = rpc_program(
        env, "const result=payload(call('vera_workspace_transformation_catalogue',{}));"
    )
    assert result["works"][0]["initialization"] is True
    assert result["initial_authoring_available"] is True
    assert result["model_context_transferred"] is False
    assert not root.exists()


def test_initial_ordinary_case_routes_cannot_skip_initial_confirmation(initial_case):
    env, root, _, _, _ = initial_case
    result = rpc_program(
        env,
        "const response=call('vera_workspace_transformation_setup',{work_ref:'fictional-init'});const result={denied:response.isError===true};",
    )
    assert result["denied"] is True
    assert not root.exists()


def test_initial_changed_retry_cannot_create_second_case_or_repeat_creation(
    initial_case,
):
    env, root, _, _, module = initial_case
    result = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),args=createArgs(p,save(p));payload(call('vera_workspace_transformation_initial_create',args));args.fields={owner:fields.owner,purpose:'Changed retry'};const response=call('vera_workspace_transformation_initial_create',args);const result={denied:response.isError===true};",
    )
    assert result["denied"] is True
    assert module.CaseStore(root).load()["revision"] == 1


def test_initial_owner_mismatch_refuses_private_fields_and_case_creation(initial_case):
    env, root, _, _, _ = initial_case
    env["VERA_WORKSPACE_ACTOR_ID"] = "another-actor"
    result = rpc_program(
        env,
        "const response=call('vera_workspace_transformation_initial_setup',{work_ref:'fictional-init'});const result={denied:response.isError===true};",
    )
    assert result["denied"] is True
    assert not root.exists()


def test_initial_no_public_target_inside_private_controls(initial_case):
    env, root, controls, config, _ = initial_case
    data = json.loads(config.read_text())
    data["bindings"][0]["case_dir"] = str(controls / "case")
    config.write_text(json.dumps(data))
    result = rpc_program(
        env,
        "const response=call('vera_workspace_transformation_initial_setup',{work_ref:'fictional-init'});const result={denied:response.isError===true};",
    )
    assert result["denied"] is True
    assert not root.exists()
    assert not (controls / "case").exists()


@pytest.mark.parametrize("phase", ["before", "after"])
def test_initial_public_creation_interruption_retains_intent_and_refuses_repetition(
    initial_case, monkeypatch, phase
):
    env, root, controls, _, public = initial_case
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    path = ROOT / "plugins/vera/scripts/native_transformation_initial.py"
    spec = importlib.util.spec_from_file_location("initial_fault_check", path)
    initial = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(initial)
    workspace = workspace_module()
    api = SimpleNamespace(
        atomic_json=workspace.atomic_json, write_lock=workspace.write_lock
    )
    module_root = Path(public.__file__).parents[1]
    prefix = "vera_workspace_transformation_initial_"
    page = initial.dispatch(
        prefix + "setup", {"work_ref": "fictional-init"}, module_root, api
    )
    fields = {
        "owner": "FICTIONAL_OWNER",
        "purpose": "Requested synthetic demonstration",
    }
    authority = {key: page[key] for key in ("work_ref", "revision", "source_ref")}
    saved = initial.dispatch(
        prefix + "draft_save",
        {
            **authority,
            "expected_draft_revision": page["draft_revision"],
            "fields": fields,
        },
        module_root,
        api,
    )
    request = {
        **authority,
        "expected_draft_revision": saved["draft_revision"],
        "fields": fields,
        "confirmed": True,
        "synthetic_only": True,
        "idempotency_key": "interrupted",
    }
    actual_producer = initial.producer

    def interrupted_producer(module, target, row, action, **arguments):
        if action == "initialize":
            if phase == "after":
                actual_producer(module, target, row, action, **arguments)
            raise ValueError("Injected transport interruption")
        return actual_producer(module, target, row, action, **arguments)

    monkeypatch.setattr(initial, "producer", interrupted_producer)

    with pytest.raises(ValueError, match="transport interruption"):
        initial.dispatch(prefix + "create", request, module_root, api)

    current = initial.dispatch(
        prefix + "setup", {"work_ref": "fictional-init"}, module_root, api
    )
    assert current["pending_operations"] == ["interrupted"]
    assert current["created"] is (phase == "after")
    assert current["can_write"] is False
    with pytest.raises(ValueError, match="Uncertain"):
        initial.dispatch(prefix + "create", request, module_root, api)
    pending = next(controls.glob("*/operations.json"))
    assert json.loads(pending.read_text())["interrupted"]["status"] == "pending"
    if phase == "after":
        assert public.CaseStore(root).load()["revision"] == 1
    else:
        assert not root.exists()


def test_initial_created_case_never_reinitializes_after_later_public_change(
    initial_case,
):
    env, root, _, _, public = initial_case
    first = rpc_program(
        env,
        PROGRAM
        + "const p=setup(),args=createArgs(p,save(p));payload(call('vera_workspace_transformation_initial_create',args));const result={args};",
    )
    public.CaseStore(root).update_case(
        {"initial_form": "FICTIONAL SNC"}, "FICTIONAL_OWNER"
    )

    result = rpc_program(
        env,
        "const args="
        + json.dumps(first["args"])
        + ";const response=call('vera_workspace_transformation_initial_create',args);const result={denied:response.isError===true};",
    )

    assert result["denied"] is True
    assert public.CaseStore(root).load()["revision"] == 2
    assert public.CaseStore(root).load()["case"]["initial_form"] == "FICTIONAL SNC"


@pytest.mark.parametrize(
    "unsafe", ["engagements", "linked-target", "linked-controls", "disabled-synthetic"]
)
def test_initial_unsafe_binding_refuses_case_creation(initial_case, unsafe, tmp_path):
    env, root, controls, config, _ = initial_case
    data = json.loads(config.read_text())
    row = data["bindings"][0]
    if unsafe == "engagements":
        folder = tmp_path / "engagements"
        folder.mkdir()
        row["case_dir"] = str(folder / "new-case")
    elif unsafe == "linked-target":
        actual = tmp_path / "actual"
        actual.mkdir()
        root.symlink_to(actual, target_is_directory=True)
    elif unsafe == "linked-controls":
        linked = tmp_path / "linked-controls"
        linked.symlink_to(controls, target_is_directory=True)
        row["initial_state_dir"] = str(linked)
    else:
        row["synthetic_only"] = False
    config.write_text(json.dumps(data))

    result = rpc_program(
        env,
        "const response=call('vera_workspace_transformation_initial_setup',{work_ref:'fictional-init'});const result={denied:response.isError===true};",
    )

    assert result["denied"] is True
    assert not (root / "history").exists()
