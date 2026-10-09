"""Real public registry review producers, fictional evidence and no host acceptance."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins import test_registro_imprese_sari_plugin as public
from tests.plugins import test_vera_native_workspace as factory
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_sari_authoring import (
    author_program,
    register_program,
)
from tests.plugins.test_vera_native_sari_intake import sari_run  # noqa: F401

__all__ = []


@pytest.fixture
def prepared_sari(tmp_path, monkeypatch):
    captured = {}
    original = public._running_sari_workspace

    def capture(path):
        captured.update(original(path))
        return captured

    monkeypatch.setattr(public, "_running_sari_workspace", capture)
    output, _ = public._prepare_case(tmp_path, include_inventory=True)
    context = captured["context"]
    binding = {
        "work_ref": "fictional-prepared-registry",
        "client_root": str(captured["client_root"]),
        **{key: context[key] for key in ("client_id", "engagement_id", "run_id")},
        "workflow_id": "registro-imprese-sari",
    }
    factory.configure(monkeypatch, tmp_path, [binding])
    return captured, binding, output


def review_program(fixture):
    return f"""
const reviewWork={{work_ref:{json.dumps(fixture[1]['work_ref'])}}};
const reviewCall=call('vera_workspace_sari_review_setup',reviewWork),reviewPage=payload(reviewCall);
const reviewAuthority=page=>({{...reviewWork,revision:page.revision,source_ref:page.source_ref,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision}});
const selectedReview={{...reviewWork,revision:reviewPage.revision,source_ref:reviewPage.source_ref,item_id:reviewPage.rows[0].item_id}};
const privateFields={{reviewer:'Fictional declared professional',decisions:{{[selectedReview.item_id]:{{action:'accept',reviewer_note:'PRIVATE-UNSENT-NOTE',edit_value:'',requested_documents:''}}}}}};
"""


def saved_program():
    return """
const privateSaved=payload(call('vera_workspace_sari_review_draft_save',{...reviewAuthority(reviewPage),fields:privateFields}));
const publicSave={...reviewAuthority(reviewPage),expected_draft_revision:privateSaved.draft_revision,fields:privateFields,confirmed:true,idempotency_key:'fictional-public-review-save'};
const publicSaved=payload(call('vera_workspace_sari_review_save',publicSave));
const afterSave=payload(call('vera_workspace_sari_review_setup',reviewWork));
const publicApply={...reviewWork,revision:afterSave.revision,source_ref:afterSave.source_ref,review_ticket:afterSave.review_ticket,public_decisions_sha256:afterSave.public_decisions_sha256,reviewer:privateFields.reviewer,confirmed:true,idempotency_key:'fictional-public-review-apply'};
"""


def output_bytes(output):
    return {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*")
        if p.is_file()
    }


def test_sari_review_context_has_one_complete_item_and_no_private_choices_or_authority(
    prepared_sari,
):
    before = output_bytes(prepared_sari[2])
    result = rpc_program(
        os.environ.copy(),
        review_program(prepared_sari)
        + """
const privateSaved=payload(call('vera_workspace_sari_review_draft_save',{...reviewAuthority(reviewPage),fields:privateFields}));
const opened=payload(call('vera_workspace_sari_review_read',selectedReview));
const context=call('vera_workspace_sari_review_context',selectedReview);
const result={reviewCall,opened,context,recovered:payload(call('vera_workspace_sari_review_setup',reviewWork))};
""",
    )
    assert (
        result["opened"]["item"] == result["context"]["structuredContent"]["evidence"]
    )
    assert "_meta" not in result["context"]
    assert "PRIVATE-UNSENT" not in json.dumps(result["context"])
    assert "persistence_token" not in json.dumps(result)
    assert "reviewer" not in result["reviewCall"]["structuredContent"]
    assert (
        result["recovered"]["fields"]["reviewer"] == "Fictional declared professional"
    )
    assert (
        result["context"]["structuredContent"]["actual_model_reads_verified"] is False
    )
    assert output_bytes(prepared_sari[2]) == before


def test_sari_save_then_apply_use_actual_public_context_retain_versions_and_preserve_case(
    prepared_sari,
):
    before = output_bytes(prepared_sari[2])
    result = rpc_program(
        os.environ.copy(),
        review_program(prepared_sari)
        + saved_program()
        + """
const saveRetry=payload(call('vera_workspace_sari_review_save',publicSave));
const unconfirmed=call('vera_workspace_sari_review_apply',{...publicApply,confirmed:false});
const applied=payload(call('vera_workspace_sari_review_apply',publicApply));
const applyRetry=payload(call('vera_workspace_sari_review_apply',publicApply));
const result={publicSaved,saveRetry,afterSave,unconfirmed,applied,applyRetry,current:payload(call('vera_workspace_sari_review_setup',reviewWork))};
""",
    )
    assert result["publicSaved"] == result["saveRetry"]
    assert result["applied"] == result["applyRetry"]
    assert result["unconfirmed"]["isError"] is True
    assert result["afterSave"]["draft_stale"] is True
    assert result["applied"]["public_result"]["persisted"] is True
    assert result["applied"]["public_result"]["portal_actions_performed"] is False
    assert result["current"]["final_artifacts"]["ready_to_file"] is False
    after = output_bytes(prepared_sari[2])
    assert after["practice_plan_draft.json"] == before["practice_plan_draft.json"]
    assert after["case_intake_validated.json"] == before["case_intake_validated.json"]
    assert after["studio_checklist.md"] == before["studio_checklist.md"]
    assert after["sari_question_draft.md"] == before["sari_question_draft.md"]
    module = factory.workspace_module()
    state_dir = module.ui_state_directory(prepared_sari[2], create=False)
    operations = json.loads((state_dir / "sari-review-operations.json").read_bytes())[
        "operations"
    ]
    assert len(operations) == 2
    first_snapshot = state_dir / "sari-review-receipts" / operations[0]["snapshot_ref"]
    assert (first_snapshot / "ui_decisions.json").read_bytes() == before[
        "ui_decisions.json"
    ]
    assert (
        operations[0]["receipt"]["after_files"]["ui_decisions.json"]
        == operations[1]["receipt"]["before_files"]["ui_decisions.json"]
    )


@pytest.mark.parametrize(
    "invalid",
    [
        "edit_without_value",
        "documents_without_request",
        "unconfirmed",
        "stale_generation",
        "tampered_ticket",
        "invalid_signature",
    ],
)
def test_sari_expected_invalid_choices_never_write_public_intent(
    prepared_sari, invalid
):
    before = output_bytes(prepared_sari[2])
    modifications = {
        "edit_without_value": "privateFields.decisions[selectedReview.item_id].action='edit';",
        "documents_without_request": "privateFields.decisions[selectedReview.item_id].action='request_more_documents';",
        "unconfirmed": "args.confirmed=false;",
        "stale_generation": "args.expected_draft_revision='0'.repeat(64);",
        "tampered_ticket": "args.review_ticket+='0';",
        "invalid_signature": "args.review_ticket=args.review_ticket.slice(0,-1)+(args.review_ticket.endsWith('0')?'1':'0');",
    }
    pre = (
        modifications[invalid]
        if invalid in {"edit_without_value", "documents_without_request"}
        else ""
    )
    post = modifications[invalid] if not pre else ""
    result = rpc_program(
        os.environ.copy(),
        review_program(prepared_sari)
        + pre
        + """
const saved=payload(call('vera_workspace_sari_review_draft_save',{...reviewAuthority(reviewPage),fields:privateFields}));
const args={...reviewAuthority(reviewPage),expected_draft_revision:saved.draft_revision,fields:privateFields,confirmed:true,idempotency_key:'fictional-invalid-choice'};
"""
        + post
        + "const result=call('vera_workspace_sari_review_save',args);",
    )
    assert result["isError"] is True
    assert output_bytes(prepared_sari[2]) == before
    assert not (
        factory.workspace_module().ui_state_directory(prepared_sari[2], create=False)
        / "sari-review-operations.json"
    ).exists()


def test_sari_review_declared_edits_and_documents_remain_unapplied_case_revisions(
    prepared_sari,
):
    before = output_bytes(prepared_sari[2])
    result = rpc_program(
        os.environ.copy(),
        review_program(prepared_sari)
        + """
privateFields.decisions[selectedReview.item_id]={action:'edit',reviewer_note:'Fictional explicit revision',edit_value:'Exact requested fictional change',requested_documents:''};
privateFields.decisions[reviewPage.rows[1].item_id]={action:'request_more_documents',reviewer_note:'Fictional missing document',edit_value:'',requested_documents:'First fictional original\nSecond fictional original'};
""".replace(
            "original\nSecond", "original\\nSecond"
        )
        + saved_program()
        + "const result=payload(call('vera_workspace_sari_review_apply',publicApply));",
    )
    assert result["status"] == "review_incomplete_or_revision_required"
    assert result["public_result"]["final_artifacts"]["ready_to_file"] is False
    after = output_bytes(prepared_sari[2])
    assert after["practice_plan_draft.json"] == before["practice_plan_draft.json"]
    assert b"Exact requested fictional change" in after["applied_decisions.json"]
    assert b"Second fictional original" in after["ui_decisions.json"]


def test_sari_prepared_all_accepts_never_authorize_filing(prepared_sari):
    result = rpc_program(
        os.environ.copy(),
        review_program(prepared_sari)
        + """
const records=payload(call('vera_workspace_sari_review_outputs',{...reviewWork,revision:reviewPage.revision}));
const whole=JSON.parse(records.files.find(file=>file.name==='review_payload.json').content);
privateFields.decisions=Object.fromEntries(whole.items.map(item=>[item.id,{action:'accept',reviewer_note:'Explicit fictional complete review',edit_value:'',requested_documents:''}]));
"""
        + saved_program()
        + "const result=payload(call('vera_workspace_sari_review_apply',publicApply));",
    )
    assert result["status"] == "reviewed_no_portal_action"
    assert result["public_result"]["final_artifacts"]["ready_to_file"] is False
    assert result["public_result"]["portal_actions_performed"] is False


def test_sari_prepared_native_authoring_flows_into_unchanged_public_review(sari_run):
    result = rpc_program(
        os.environ.copy(),
        author_program(sari_run)
        + register_program()
        + """
const registered=payload(call('vera_workspace_sari_author_register',registerArgs));
"""
        + review_program(sari_run)
        + saved_program()
        + "const result=payload(call('vera_workspace_sari_review_apply',publicApply));",
    )
    assert result["public_result"]["persisted"] is True
    assert result["public_result"]["final_artifacts"]["ready_to_file"] is False


def test_sari_sealed_review_remains_complete_readonly_without_persistence_authority(
    prepared_sari, monkeypatch
):
    output, binding = prepared_sari[2], prepared_sari[1]
    write_no_model_report(output, "registro-imprese-sari", binding["run_id"])
    declarations = [
        {
            "artifact_id": f"fictional_registry_{i}",
            "path": p.relative_to(output).as_posix(),
            "purpose": "Fictional complete registry review",
            "audience": "review",
            "media_type": "application/octet-stream",
        }
        for i, p in enumerate(sorted(p for p in output.rglob("*") if p.is_file()))
    ]
    ledger = _load_customer_ledger()
    ledger.finalize_run(
        Path(binding["client_root"]),
        binding["engagement_id"],
        binding["run_id"],
        declarations,
    )
    ledger.complete_run(
        Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
    )
    before = output_bytes(output)
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "VIEWER")
    result = rpc_program(
        os.environ.copy(),
        review_program(prepared_sari)
        + """
const result={reviewPage,read:payload(call('vera_workspace_sari_review_read',selectedReview)),denied:call('vera_workspace_sari_review_draft_save',{...reviewAuthority(reviewPage),fields:privateFields})};
""",
    )
    assert result["reviewPage"]["run_status"] == "completed"
    assert result["reviewPage"]["can_write"] is False
    assert result["denied"]["isError"] is True
    assert "persistence_token" not in json.dumps(result)
    assert output_bytes(output) == before


def test_sari_pending_review_receipt_blocks_future_writes_and_native_closure(
    prepared_sari, monkeypatch
):
    rpc_program(
        os.environ.copy(),
        review_program(prepared_sari) + saved_program() + "const result=publicSaved;",
    )
    module = factory.workspace_module()
    output, binding = prepared_sari[2], prepared_sari[1]
    path = module.ui_state_directory(output) / "sari-review-operations.json"
    ledger = json.loads(path.read_bytes())
    ledger["operations"][0]["status"] = "pending"
    module.atomic_json(path, ledger)
    result = rpc_program(
        os.environ.copy(),
        review_program(prepared_sari)
        + "const result={reviewPage,denied:call('vera_workspace_sari_review_draft_save',{...reviewAuthority(reviewPage),fields:privateFields})};",
    )
    assert result["reviewPage"]["recovery_required"] is True
    assert result["denied"]["isError"] is True
    # Independently exercise the new guard with actual core lease and complete API;
    # source dispatcher's older missing digest capability remains unapproved.
    monkeypatch.setenv(
        "VERA_STUDIO_ARCHIVE_STATE_DIR",
        str(prepared_sari[0]["client_root"].parent.parent / "private-state"),
    )
    monkeypatch.setitem(sys.modules, "archive_core", public._load_archive_core())
    from native_archive_closure import snapshot

    with pytest.raises(ValueError, match="public review requires ordinary recovery"):
        snapshot(
            module.module_root("studio-archive"),
            {key: binding[key] for key in ("client_id", "engagement_id", "run_id")},
            SimpleNamespace(**vars(module)),
        )


def test_sari_review_actor_isolation_viewer_denial_and_invalid_selection(prepared_sari):
    before = output_bytes(prepared_sari[2])
    result = rpc_program(
        os.environ.copy(),
        review_program(prepared_sari)
        + """
const saved=payload(call('vera_workspace_sari_review_draft_save',{...reviewAuthority(reviewPage),fields:privateFields}));
const originalActor=process.env.VERA_WORKSPACE_ACTOR_ID;
process.env.VERA_WORKSPACE_ACTOR_ID='fictional-different-reviewer';
const other=call('vera_workspace_sari_review_setup',reviewWork);
const replay=call('vera_workspace_sari_review_draft_save',{...reviewAuthority(reviewPage),fields:privateFields});
process.env.VERA_WORKSPACE_ACTOR_ID=originalActor;
process.env.VERA_WORKSPACE_ROLES='VIEWER';
const viewer=payload(call('vera_workspace_sari_review_setup',reviewWork));
const denied=call('vera_workspace_sari_review_draft_save',{...reviewAuthority(viewer),fields:privateFields});
const invalid=call('vera_workspace_sari_review_context',{...selectedReview,item_id:'wrong-item'});
const result={other,replay,viewer,denied,invalid};
""",
    )
    assert result["other"]["isError"] is True
    assert "PRIVATE-UNSENT" not in json.dumps(result["other"])
    assert result["replay"]["isError"] is True
    assert result["viewer"]["can_write"] is False
    assert result["denied"]["isError"] is True
    assert result["invalid"]["isError"] is True
    assert output_bytes(prepared_sari[2]) == before


def test_sari_review_replacement_requires_reselection_and_apply_exact_saved_hash(
    prepared_sari,
):
    result = rpc_program(
        os.environ.copy(),
        review_program(prepared_sari)
        + saved_program()
        + """
const wrongHash=call('vera_workspace_sari_review_apply',{...publicApply,public_decisions_sha256:'0'.repeat(64)});
const wrongReviewer=call('vera_workspace_sari_review_apply',{...publicApply,reviewer:'Another person'});
const cleared=payload(call('vera_workspace_sari_review_draft_clear',{...reviewAuthority(afterSave),confirmed:true}));
const reopened=payload(call('vera_workspace_sari_review_setup',reviewWork));
const otherFields={reviewer:privateFields.reviewer,decisions:{[reopened.rows[1].item_id]:{action:'accept',reviewer_note:'',edit_value:'',requested_documents:''}}};
const saved=payload(call('vera_workspace_sari_review_draft_save',{...reviewAuthority(reopened),fields:otherFields}));
const dropped=call('vera_workspace_sari_review_save',{...reviewAuthority(reopened),expected_draft_revision:saved.draft_revision,fields:otherFields,confirmed:true,idempotency_key:'fictional-unsafe-replacement'});
const result={wrongHash,wrongReviewer,dropped,current:payload(call('vera_workspace_sari_review_setup',reviewWork))};
""",
    )
    assert result["wrongHash"]["isError"] is True
    assert result["wrongReviewer"]["isError"] is True
    assert result["dropped"]["isError"] is True
    assert result["current"]["public_decisions"]["decision_count"] == 1


@pytest.mark.parametrize("tampered", ["practice_plan_validated.json", "prior_version"])
def test_sari_review_changed_validated_binding_or_retained_snapshot_refuses_new_scope(
    prepared_sari, tampered
):
    rpc_program(
        os.environ.copy(),
        review_program(prepared_sari) + saved_program() + "const result=publicSaved;",
    )
    module = factory.workspace_module()
    if tampered == "prior_version":
        home = (
            module.ui_state_directory(prepared_sari[2], create=False)
            / "sari-review-receipts"
        )
        target = next(home.glob("*/ui_decisions.json"))
    else:
        target = prepared_sari[2] / tampered
    target.write_bytes(target.read_bytes() + b"\n")
    before = output_bytes(prepared_sari[2])
    result = rpc_program(
        os.environ.copy(),
        f"const result=call('vera_workspace_sari_review_setup',{{work_ref:{json.dumps(prepared_sari[1]['work_ref'])}}});",
    )
    assert result["isError"] is True
    assert output_bytes(prepared_sari[2]) == before
