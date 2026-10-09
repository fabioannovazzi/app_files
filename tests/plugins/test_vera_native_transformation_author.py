"""Real source MCP and isolated public replay, with fictional model proposals."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.plugins.test_trasformazione import module  # noqa: F401
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_transformation import (  # noqa: F401
    PROGRAM,
    transformation,
)
from tests.plugins.test_vera_native_workspace import ROOT

__all__ = []

AUTHOR = (
    PROGRAM
    + """
const authorSetup=()=>payload(call('vera_workspace_transformation_author_setup',{work_ref:'fictional-transform'}));
const authorFields=(operation='put',refs=['fictional-source'])=>({question:'  Requested synthetic proposal only  ',operation,source_refs:refs});
const grant=(f=authorFields())=>{const p=authorSetup(),saved=payload(call('vera_workspace_transformation_author_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f})),args={...authority(p),expected_draft_revision:saved.draft_revision,fields:f,confirmed:true,synthetic_only:true,idempotency_key:'fictional-grant'};return {value:payload(call('vera_workspace_transformation_author_request',args)),args};};
const exact=g=>({work_ref:'fictional-transform',grant_ref:g.value.grant_ref});
const visible=r=>{if(r.isError)throw new Error(r.content[0].text);return r.structuredContent;};
const context=g=>visible(call('vera_workspace_transformation_author_context',exact(g)));
const proposal=()=>({operation:'put',record_kind:'finding',record_json:JSON.stringify({id:'F2',statement:'Fictional model proposal',category:'fact',rationale:'Selected synthetic evidence only',alternatives:['Preserve unknown facts'],confidence:'synthetic_unverified',dependencies:['evidence:E1']}),branch_id:''});
const staged=(g,c,p=proposal())=>{const args={...exact(g),expected_stage_revision:c.stage_revision,idempotency_key:'fictional-stage',proposal:p};return {value:visible(call('vera_workspace_transformation_author_stage',args)),args};};
const readGrant=g=>payload(call('vera_workspace_transformation_author_read',exact(g)));
"""
)


def test_author_private_intake_recovers_without_model_authorization(transformation):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const p=authorSetup(),f=authorFields();f.operation='';payload(call('vera_workspace_transformation_author_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f}));const result=authorSetup();",
    )
    assert result["fields"]["question"] == "  Requested synthetic proposal only  "
    assert result["mandates"] == []
    assert result["confirmation_restored"] is False
    assert store.load() == before


def test_author_selected_context_stage_and_adoption_never_approve_or_write_public(
    transformation,
):
    env, store, source, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + """
const g=grant(),c=context(g),s=staged(g,c),view=readGrant(g);
const args={...authority(view),...exact(g),stage_ref:s.value.stage_ref,expected_stage_revision:view.stage_revision,expected_public_draft_revision:view.public_draft_revision,confirmed:true,idempotency_key:'fictional-adopt'};
const adopted=payload(call('vera_workspace_transformation_author_adopt',args)),retry=payload(call('vera_workspace_transformation_author_adopt',args));
const result={c,s,view,adopted,retry,ordinary:setup()};
""",
    )
    assert result["c"]["state"] == before
    assert result["c"]["sources"][0]["path"] == str(source)
    assert (
        result["view"]["selected_stage"]["preview_state"]["revision"]
        == before["revision"] + 1
    )
    assert result["view"]["selected_stage"]["preview_state"]["decisions"] == []
    assert result["adopted"] == result["retry"]
    fields = result["ordinary"]["fields"]
    assert fields["operation"] == "put"
    assert json.loads(fields["record_json"])["id"] == "F2"
    assert fields["actor"] == ""
    assert fields["decision"] == ""
    assert result["ordinary"]["confirmation_restored"] is False
    assert store.load() == before


def test_author_actual_public_execution_is_a_later_separately_confirmed_step(
    transformation,
):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const g=grant(),c=context(g),s=staged(g,c),view=readGrant(g);payload(call('vera_workspace_transformation_author_adopt',{...authority(view),...exact(g),stage_ref:s.value.stage_ref,expected_stage_revision:view.stage_revision,expected_public_draft_revision:view.public_draft_revision,confirmed:true,idempotency_key:'adopt'}));const p=setup(),f=p.fields;f.actor='FICTIONAL_ACTUAL_OPERATOR';execute(p,f,'explicit-public-put');const result=setup();",
    )
    assert store.load()["revision"] == before["revision"] + 1
    assert "F2" in store.load()["records"]["finding"]
    assert store.load()["decisions"] == []
    assert result["data"]["state"]["case"]["actual_date"] is None


@pytest.mark.parametrize(
    "change", ["confirmed:false", "synthetic_only:false", "revision:'changed'"]
)
def test_author_request_refuses_changed_scope_or_missing_separate_consent(
    transformation, change
):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const p=authorSetup(),f=authorFields(),saved=payload(call('vera_workspace_transformation_author_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:f}));const result=call('vera_workspace_transformation_author_request',{...authority(p),expected_draft_revision:saved.draft_revision,fields:f,confirmed:true,synthetic_only:true,idempotency_key:'refused',"
        + change
        + "});",
    )
    assert result["isError"] is True
    assert store.load() == before


def test_author_context_requires_exact_unforgeable_owned_mandate(transformation):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const result=call('vera_workspace_transformation_author_context',{work_ref:'fictional-transform',grant_ref:'author-'+ '0'.repeat(64)});",
    )
    assert result["isError"] is True
    assert store.load() == before


def test_author_context_only_returns_selected_originals(transformation):
    env, store, source, config = transformation
    another = source.with_name("unselected.txt")
    another.write_text("FICTIONAL UNSELECTED ORIGINAL")
    data = json.loads(config.read_text())
    data["bindings"][0]["sources"].append(
        {"source_ref": "unselected", "path": str(another)}
    )
    config.write_text(json.dumps(data))
    result = rpc_program(env, AUTHOR + "const g=grant();const result=context(g);")
    assert [row["source_ref"] for row in result["sources"]] == ["fictional-source"]
    assert str(another) not in json.dumps(result)
    assert store.load()["decisions"] == []


def test_author_whole_case_question_can_explicitly_select_no_additional_originals(
    transformation,
):
    env, store, _, _ = transformation
    result = rpc_program(
        env, AUTHOR + "const g=grant(authorFields('put',[]));const result=context(g);"
    )
    assert result["sources"] == []
    assert result["state"] == store.load()


def test_author_nonselected_import_proposal_is_refused(transformation):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const g=grant(authorFields('import_evidence',[])),c=context(g),p={operation:'import_evidence',record_kind:'',record_json:JSON.stringify({id:'E2',source_ref:'fictional-source',origin:'Fictional',locator:'line 1'}),branch_id:''};const result=call('vera_workspace_transformation_author_stage',{...exact(g),expected_stage_revision:c.stage_revision,idempotency_key:'refused-import',proposal:p});",
    )
    assert result["isError"] is True
    assert store.load() == before


@pytest.mark.parametrize("operation", ["review", "submit", "export"])
def test_author_model_cannot_stage_review_submission_or_export(
    transformation, operation
):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + f"const g=grant(),c=context(g),p=proposal();p.operation={json.dumps(operation)};const result=call('vera_workspace_transformation_author_stage',{{...exact(g),expected_stage_revision:c.stage_revision,idempotency_key:'refused',proposal:p}});",
    )
    assert result["isError"] is True
    assert store.load() == before


def test_author_public_domain_rejection_happens_on_isolated_copy_only(transformation):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const g=grant(),c=context(g),p=proposal();p.record_json=JSON.stringify({id:'invalid'});const response=call('vera_workspace_transformation_author_stage',{...exact(g),expected_stage_revision:c.stage_revision,idempotency_key:'invalid',proposal:p});const result={response,view:readGrant(g)};",
    )
    assert result["response"]["isError"] is True
    assert "expected fields" in result["response"]["content"][0]["text"]
    assert result["view"]["stages"] == []
    assert store.load() == before


def test_author_stale_stage_cas_and_changed_retry_are_refused(transformation):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const g=grant(),c=context(g),s=staged(g,c);const retry=visible(call('vera_workspace_transformation_author_stage',s.args)),oldCas=call('vera_workspace_transformation_author_stage',{...s.args,idempotency_key:'other'}),changed=call('vera_workspace_transformation_author_stage',{...s.args,proposal:{...proposal(),branch_id:'changed'}});const result={original:s.value,retry,oldCas,changed};",
    )
    assert result["original"] == result["retry"]
    assert result["oldCas"]["isError"] is True
    assert result["changed"]["isError"] is True
    assert store.load() == before


def test_author_existing_incomplete_public_fields_are_never_overwritten(transformation):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const p=setup(),f=fields('put');f.record_json='  unfinished original  ';save(p,f);const g=grant(),c=context(g),s=staged(g,c),view=readGrant(g),denied=call('vera_workspace_transformation_author_adopt',{...authority(view),...exact(g),stage_ref:s.value.stage_ref,expected_stage_revision:view.stage_revision,expected_public_draft_revision:view.public_draft_revision,confirmed:true,idempotency_key:'refused-adopt'});const result={denied,view,ordinary:setup()};",
    )
    assert result["denied"]["isError"] is True
    assert result["view"]["can_adopt"] is False
    assert result["ordinary"]["fields"]["record_json"] == "  unfinished original  "
    assert store.load() == before


def test_author_withdrawal_blocks_model_access_without_deleting_proposals(
    transformation,
):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const g=grant(),c=context(g);staged(g,c);const view=readGrant(g);payload(call('vera_workspace_transformation_author_cancel',{...authority(view),...exact(g),expected_stage_revision:view.stage_revision,confirmed:true}));const result={context:call('vera_workspace_transformation_author_context',exact(g)),view:readGrant(g)};",
    )
    assert result["context"]["isError"] is True
    assert result["view"]["status"] == "cancelled"
    assert len(result["view"]["stages"]) == 1
    assert store.load() == before


def test_author_request_preparation_is_durable_and_never_claims_model_receipt(
    transformation,
):
    env, store, _, _ = transformation
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const g=grant(),view=readGrant(g),args={...authority(view),...exact(g),expected_stage_revision:view.stage_revision,confirmed:true},first=payload(call('vera_workspace_transformation_author_message_prepare',args));const result={first,again:call('vera_workspace_transformation_author_message_prepare',args),view:readGrant(g)};",
    )
    assert result["first"]["message_received"] is False
    assert result["first"]["model_executed"] is False
    assert result["again"]["isError"] is True
    assert result["view"]["can_prepare_request"] is False
    assert store.load() == before


def test_author_public_source_change_invalidates_model_context(transformation):
    env, store, source, _ = transformation
    grant_result = rpc_program(env, AUTHOR + "const result=grant().value;")
    source.write_text("FICTIONAL CHANGED AFTER GRANT")
    result = rpc_program(
        env,
        "const result=call('vera_workspace_transformation_author_context',"
        + json.dumps(
            {"work_ref": "fictional-transform", "grant_ref": grant_result["grant_ref"]}
        )
        + ");",
    )
    assert result["isError"] is True
    assert store.load()["decisions"] == []


@pytest.mark.parametrize("action", ["context", "stage"])
def test_author_expired_mandate_refuses_model_access_before_replay(
    transformation, monkeypatch, action
):
    env, store, _, _ = transformation
    before = store.load()
    granted = rpc_program(
        env, AUTHOR + "const g=grant();const result={grant:g.value,context:context(g)};"
    )
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import native_transformation_author as author
    import native_workspace as workspace

    retained = next(store.root.glob(".native-workspace/**/mandate.json"))
    expires_at = json.loads(retained.read_text())["expires_at"]
    monkeypatch.setattr(author, "clock", lambda: expires_at)
    api = SimpleNamespace(
        atomic_json=workspace.atomic_json, write_lock=workspace.write_lock
    )
    args = {
        "work_ref": "fictional-transform",
        "grant_ref": granted["grant"]["grant_ref"],
        "expected_stage_revision": granted["context"]["stage_revision"],
        "idempotency_key": "expired-stage",
    }

    with pytest.raises(ValueError, match="stale, withdrawn or expired"):
        author.dispatch(
            "vera_workspace_transformation_author_" + action,
            args,
            ROOT / "plugins/trasformazione",
            api,
        )

    assert store.load() == before
    assert list(retained.parent.glob("intent-*.json")) == []


def test_author_viewer_cannot_issue_a_model_mandate(transformation):
    env, store, _, _ = transformation
    env["VERA_WORKSPACE_ROLES"] = "VIEWER"
    before = store.load()
    result = rpc_program(
        env,
        AUTHOR
        + "const p=authorSetup();const result=call('vera_workspace_transformation_author_draft_save',{...authority(p),expected_draft_revision:p.draft_revision,fields:authorFields()});",
    )
    assert result["isError"] is True
    assert store.load() == before


@pytest.mark.parametrize("after_write", [False, True])
def test_author_private_intent_uncertainty_blocks_repeat_and_preserves_public_case(
    transformation, monkeypatch, after_write
):
    env, store, _, _ = transformation
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import native_transformation_author as author
    import native_workspace as workspace

    api = SimpleNamespace(
        atomic_json=workspace.atomic_json, write_lock=workspace.write_lock
    )
    module_root = ROOT / "plugins/trasformazione"
    exact = {"work_ref": "fictional-transform"}
    setup = author.dispatch(
        "vera_workspace_transformation_author_setup", exact, module_root, api
    )
    fields = {
        "question": "FICTIONAL fault probe",
        "operation": "put",
        "source_refs": [],
    }
    scope = {**exact, "revision": setup["revision"], "source_ref": setup["source_ref"]}
    saved = author.dispatch(
        "vera_workspace_transformation_author_draft_save",
        {**scope, "expected_draft_revision": setup["draft_revision"], "fields": fields},
        module_root,
        api,
    )
    request = {
        **scope,
        "expected_draft_revision": saved["draft_revision"],
        "fields": fields,
        "confirmed": True,
        "synthetic_only": True,
        "idempotency_key": "fault",
    }
    before = store.load()

    def failing(path: Path, value: dict) -> None:
        if path.name == "mandate.json":
            if after_write:
                workspace.atomic_json(path, value)
            raise OSError("FICTIONAL private transport fault")
        workspace.atomic_json(path, value)

    broken = SimpleNamespace(atomic_json=failing, write_lock=workspace.write_lock)
    with pytest.raises(OSError, match="FICTIONAL private transport fault"):
        author.dispatch(
            "vera_workspace_transformation_author_request", request, module_root, broken
        )
    with pytest.raises(ValueError, match="uncertain synthetic mandate retry"):
        author.dispatch(
            "vera_workspace_transformation_author_request", request, module_root, api
        )
    recovered = author.dispatch(
        "vera_workspace_transformation_author_setup", exact, module_root, api
    )
    assert len(recovered["pending_requests"]) == 1
    assert recovered["mandates"] == []
    assert store.load() == before
