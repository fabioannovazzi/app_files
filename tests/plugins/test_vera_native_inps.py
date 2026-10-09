"""Owned INPS public-producer integration; no installed host/model acceptance."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_previdenza_inps_plugin import (
    _load_script,
    _write_case_records,
    _write_claims,
)
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import archive_cli
from tests.plugins.test_vera_native_workspace import configure

__all__ = []


@pytest.fixture
def inps_run(vera_workflow_workspace, tmp_path, monkeypatch):
    """Prepare an ordinary source-bound case, never a fabricated ready payload."""
    workspace = vera_workflow_workspace(
        "previdenza-inps",
        input_files={"mandato.txt": "Il rapporto decorre dal 1 gennaio 2021."},
    )
    output = Path(workspace["output_dir"])
    inventory = _load_script("inventory_case")
    validator = _load_script("validate_case_records")
    packager = _load_script("package_case")
    assert (
        inventory.main(
            [
                str(workspace["input_dir"]),
                "--output-dir",
                str(output),
                "--no-ocr",
                "--client-engagement",
                str(workspace["context_path"]),
            ]
        )
        == 0
    )
    records = _write_case_records(output / "case_records_draft.json")
    claims = _write_claims(output / "claims_review.json")
    assert (
        validator.validate_case_records(
            records, output / "file_inventory.json", output
        )["status"]
        == "passed"
    )
    assert (
        packager.main(
            [
                str(output / "case_records_validated.json"),
                str(claims),
                "--output-dir",
                str(output),
                "--client-engagement",
                str(workspace["context_path"]),
            ]
        )
        == 0
    )
    context = json.loads(Path(workspace["context_path"]).read_bytes())
    binding = {
        "work_ref": "fictional-inps",
        "client_root": str(workspace["client_root"]),
        "client_id": context["client_id"],
        "engagement_id": context["engagement_id"],
        "run_id": context["run_id"],
        "workflow_id": "previdenza-inps",
    }
    configure(monkeypatch, tmp_path, [binding])
    return workspace, binding, output


def program(fixture):
    return f"""
const work={{work_ref:{json.dumps(fixture[1]['work_ref'])}}};
const setupCall=call('vera_workspace_inps_setup',work),setup=payload(setupCall);
const identity={{...work,revision:setup.revision,source_ref:setup.source_ref,item_id:setup.rows[0].item_id}};
const readCall=call('vera_workspace_inps_read',identity),page=payload(readCall);
const authority=page=>({{...work,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision}});
const emptyChoice=()=>({{action:'',reviewer_note:'',edit_value:'',requested_documents:''}});
"""


def test_inps_complete_item_and_original_outputs_are_private_until_exact_model_choice(
    inps_run,
):
    before = {
        p.relative_to(inps_run[2]).as_posix(): p.read_bytes()
        for p in inps_run[2].rglob("*")
        if p.is_file()
    }
    result = rpc_program(
        os.environ.copy(),
        program(inps_run)
        + """
const original=payload(call('vera_workspace_inps_outputs',{...work,revision:setup.revision}));
const context=call('vera_workspace_inps_context',identity);
const result={setupCall,readCall,setup,page,original,context,catalogue:payload(call('vera_workspace_open',{}))};
""",
    )
    review = json.loads((inps_run[2] / "review_payload.json").read_bytes())
    assert result["page"]["item"] == review["items"][0]
    assert result["setup"]["total"] == len(review["items"])
    assert result["setup"]["draft"] == {"reviewer": "", "decisions": {}}
    assert "rows" not in result["setupCall"]["structuredContent"]
    assert "item" not in result["readCall"]["structuredContent"]
    assert "_meta" not in result["context"]
    assert result["context"]["structuredContent"]["evidence"] == review["items"][0]
    assert (
        result["context"]["structuredContent"]["actual_model_reads_verified"] is False
    )
    assert str(inps_run[2]) not in json.dumps(result["context"])
    assert result["catalogue"]["works"][0]["setup_available"] is True
    memo = next(
        row for row in result["original"]["files"] if row["name"] == "studio_memo.md"
    )
    assert memo["content"].encode() == (inps_run[2] / "studio_memo.md").read_bytes()
    assert (
        memo["sha256"]
        == hashlib.sha256((inps_run[2] / "studio_memo.md").read_bytes()).hexdigest()
    )
    assert {
        p.relative_to(inps_run[2]).as_posix(): p.read_bytes()
        for p in inps_run[2].rglob("*")
        if p.is_file()
    } == before


def test_inps_private_literal_choices_recover_without_model_exposure_or_confirmation(
    inps_run,
):
    result = rpc_program(
        os.environ.copy(),
        program(inps_run)
        + """
const fields={reviewer:'UNSENT_PRIVATE_REVIEWER',decisions:{[identity.item_id]:{...emptyChoice(),reviewer_note:'UNSENT_PRIVATE_NOTE',action:'mark_unclear'}}};
const saved=payload(call('vera_workspace_inps_draft_save',{...authority(page),fields}));
const recovered=payload(call('vera_workspace_inps_setup',work));
const context=call('vera_workspace_inps_context',identity);
const staleSave=call('vera_workspace_inps_draft_save',{...authority(page),fields});
const result={fields,saved,recovered,context,staleSave,initialDraftRevision:setup.draft_revision};
""",
    )
    assert result["recovered"]["draft"] == result["fields"]
    assert result["recovered"]["draft_revision"] != result["initialDraftRevision"]
    assert "confirmed" not in result["recovered"]["draft"]
    assert "UNSENT_PRIVATE" not in json.dumps(result["context"])
    assert result["staleSave"]["isError"] is True
    assert (
        json.loads((inps_run[2] / "ui_decisions.json").read_bytes())["decisions"] == []
    )


@pytest.mark.parametrize(
    "action",
    ["accept", "reject", "edit", "mark_unclear", "request_more_documents", "skip"],
)
def test_inps_actual_named_public_application_preserves_memo_and_review_ceiling(
    inps_run, action
):
    memo_before = (inps_run[2] / "studio_memo.md").read_bytes()
    body = (
        program(inps_run)
        + f"const selectedAction={json.dumps(action)};\n"
        + """
const fields={reviewer:'Fictional professional reviewer',decisions:{[identity.item_id]:{action:selectedAction,reviewer_note:'Actual fictional choice for this evidence',edit_value:selectedAction==='edit'?'Fictional revision requested; not yet applied':'',requested_documents:selectedAction==='request_more_documents'?'Readable original evidence':''}}};
const saved=payload(call('vera_workspace_inps_draft_save',{...authority(page),fields}));
const args={...authority(page),expected_draft_revision:saved.draft_revision,fields,confirmed:true,idempotency_key:'fictional-inps-apply'};
const first=payload(call('vera_workspace_inps_commit',args));
const retry=payload(call('vera_workspace_inps_commit',args));
const changed=call('vera_workspace_inps_commit',{...args,fields:{...fields,reviewer:'Different declared reviewer'}});
const result={first,retry,changed};
"""
    )
    result = rpc_program(os.environ.copy(), body)
    stored = json.loads((inps_run[2] / "ui_decisions.json").read_bytes())
    applied = json.loads((inps_run[2] / "applied_decisions.json").read_bytes())
    final = json.loads((inps_run[2] / "final_artifacts.json").read_bytes())
    assert stored["reviewer"] == "Fictional professional reviewer"
    assert stored["decisions"][0]["action"] == action
    assert result["first"]["public_application"]["persisted"] is True
    assert result["retry"] == result["first"]
    assert result["changed"]["isError"] is True
    assert (inps_run[2] / "studio_memo.md").read_bytes() == memo_before
    assert final["status"] in {
        "blocked",
        "partial_review_applied",
        "ready_for_professional_review",
    }
    assert applied["decision_count"] == 1
    if action == "edit":
        revision = json.loads((inps_run[2] / "revision_requirements.json").read_bytes())
        assert revision["source_artifacts_modified"] is False
        assert (
            revision["revisions"][0]["requested_change"]
            == "Fictional revision requested; not yet applied"
        )
    if action != "accept":
        assert final["status"] == "blocked"


def test_inps_commit_requires_saved_choices_actual_name_and_separate_confirmation(
    inps_run,
):
    result = rpc_program(
        os.environ.copy(),
        program(inps_run)
        + """
const fields={reviewer:'Fictional reviewer',decisions:{[identity.item_id]:{...emptyChoice(),action:'accept'}}};
const unsaved=call('vera_workspace_inps_commit',{...authority(page),fields,confirmed:true,idempotency_key:'unsaved'});
const saved=payload(call('vera_workspace_inps_draft_save',{...authority(page),fields}));
const unconfirmed=call('vera_workspace_inps_commit',{...authority(page),expected_draft_revision:saved.draft_revision,fields,confirmed:false,idempotency_key:'unconfirmed'});
const result={unsaved,unconfirmed};
""",
    )
    assert result["unsaved"]["isError"] is True
    assert result["unconfirmed"]["isError"] is True
    assert not (inps_run[2].parent / ".native-workspace/inps-operations.json").exists()


def test_inps_changed_evidence_keeps_stale_private_choices_without_silent_adoption(
    inps_run,
):
    saved = rpc_program(
        os.environ.copy(),
        program(inps_run)
        + """
const fields={reviewer:'Private previous reviewer',decisions:{[identity.item_id]:{...emptyChoice(),action:'mark_unclear',reviewer_note:'Previous evidence'}}};
payload(call('vera_workspace_inps_draft_save',{...authority(page),fields}));
const result={identity,fields};
""",
    )
    memo = inps_run[2] / "studio_memo.md"
    memo.write_bytes(memo.read_bytes() + b"\nFictional later draft revision.\n")
    result = rpc_program(
        os.environ.copy(),
        f"const old={json.dumps(saved)};\n"
        + program(inps_run)
        + """
const staleContext=call('vera_workspace_inps_context',old.identity);
const staleSave=call('vera_workspace_inps_draft_save',{...authority(setup),fields:old.fields});
const cleared=payload(call('vera_workspace_inps_draft_clear',{...authority(setup),confirmed:true}));
const result={setup,staleContext,staleSave,cleared};
""",
    )
    assert result["setup"]["draft_stale"] is True
    assert result["setup"]["draft"] == saved["fields"]
    assert result["staleContext"]["isError"] is True
    assert result["staleSave"]["isError"] is True
    assert result["cleared"]["draft"] == {"reviewer": "", "decisions": {}}


def test_inps_viewer_can_read_complete_case_but_cannot_save_or_apply(
    inps_run, monkeypatch
):
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "VIEWER")
    result = rpc_program(
        os.environ.copy(),
        program(inps_run)
        + """
const denied=call('vera_workspace_inps_draft_save',{...authority(page),fields:{reviewer:'',decisions:{}}});
const result={setup,page,denied};
""",
    )
    assert result["setup"]["can_write"] is False
    assert result["page"]["item"]["data"]
    assert result["denied"]["isError"] is True


@pytest.mark.parametrize("tamper", ["inventory", "acquisition", "review"])
def test_inps_changed_bound_acquisition_or_review_refuses_before_private_or_public_write(
    inps_run, tamper
):
    if tamper == "inventory":
        path = inps_run[2] / "file_inventory.json"
        path.write_bytes(path.read_bytes() + b"\n")
    elif tamper == "acquisition":
        path = inps_run[2] / "run_intake.json"
        value = json.loads(path.read_bytes())
        value["data_posture"]["network_access_allowed_for_model_weights"] = True
        path.write_text(json.dumps(value))
    else:
        path = inps_run[2] / "review_payload.json"
        path.write_bytes(path.read_bytes() + b"\n")
    before = {p.name: p.read_bytes() for p in inps_run[2].iterdir() if p.is_file()}
    result = rpc_program(
        os.environ.copy(),
        f"const result=call('vera_workspace_inps_setup',{{work_ref:{json.dumps(inps_run[1]['work_ref'])}}});",
    )
    assert result["isError"] is True
    assert {
        p.name: p.read_bytes() for p in inps_run[2].iterdir() if p.is_file()
    } == before
    assert not (inps_run[2].parent / ".native-workspace/inps-operations.json").exists()


def test_inps_completed_sealed_case_remains_readonly_with_ordinary_originals(
    inps_run, monkeypatch
):
    workspace, binding, output = inps_run
    ledger = _load_customer_ledger()
    write_no_model_report(output, "previdenza-inps", binding["run_id"])
    declarations = [
        {
            "artifact_id": f"fictional_inps_{index}",
            "path": path.relative_to(output).as_posix(),
            "purpose": "Preserve the complete fictional INPS case",
            "audience": "review",
            "media_type": "application/octet-stream",
        }
        for index, path in enumerate(
            sorted(p for p in output.rglob("*") if p.is_file())
        )
    ]
    ledger.finalize_run(
        Path(workspace["client_root"]),
        binding["engagement_id"],
        binding["run_id"],
        declarations,
    )
    ledger.complete_run(
        Path(workspace["client_root"]),
        binding["engagement_id"],
        binding["run_id"],
    )
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "VIEWER")
    result = rpc_program(
        os.environ.copy(),
        program(inps_run)
        + "const result={setup,page,outputs:payload(call('vera_workspace_inps_outputs',{...work,revision:setup.revision}))};",
    )
    assert result["setup"]["run_status"] == "completed"
    assert result["setup"]["can_write"] is False
    assert result["page"]["item"]["data"]
    assert (
        next(
            row for row in result["outputs"]["files"] if row["name"] == "studio_memo.md"
        )["content"].encode()
        == (output / "studio_memo.md").read_bytes()
    )


@pytest.mark.parametrize(
    "changed",
    ["review_ticket:'forged.ticket'", "revision:'f'.repeat(64)"],
)
def test_inps_signed_mutation_rejects_forged_or_stale_authority_without_writes(
    inps_run, changed
):
    before = (inps_run[2] / "ui_decisions.json").read_bytes()
    result = rpc_program(
        os.environ.copy(),
        program(inps_run)
        + f"const result=call('vera_workspace_inps_draft_save',{{...authority(page),{changed},fields:{{reviewer:'',decisions:{{}}}}}});",
    )
    assert result["isError"] is True
    assert (inps_run[2] / "ui_decisions.json").read_bytes() == before
    assert not list((inps_run[2].parent / ".native-workspace").glob("inps-draft-*"))


def test_inps_absent_review_continues_ordinary_preparation_without_public_writes(
    inps_run,
):
    (inps_run[2] / "review_payload.json").unlink()
    before = {p.name: p.read_bytes() for p in inps_run[2].iterdir() if p.is_file()}
    result = rpc_program(
        os.environ.copy(),
        f"const result=payload(call('vera_workspace_inps_setup',{{work_ref:{json.dumps(inps_run[1]['work_ref'])}}}));",
    )
    assert result["setup_status"] == "preparation_required"
    assert result["can_write"] is False
    assert result["rows"] == []
    assert {
        p.name: p.read_bytes() for p in inps_run[2].iterdir() if p.is_file()
    } == before


def test_inps_pending_intent_blocks_native_write_and_real_registry_closure(
    inps_run, tmp_path, monkeypatch
):
    workspace, binding, output = inps_run
    env = {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-inps-closure",
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(
            tmp_path.parent / ("inps-registry-" + tmp_path.name)
        ),
    }
    env.pop("VERA_WORKSPACE_BINDINGS")
    archive_cli(
        env, "configure", "--archive-root", str(Path(workspace["client_root"]).parent)
    )
    monkeypatch.delenv("VERA_WORKSPACE_BINDINGS")
    for name in ("VERA_STUDIO_ARCHIVE_SESSION_ID", "VERA_STUDIO_ARCHIVE_STATE_DIR"):
        monkeypatch.setenv(name, env[name])
    selected = {key: binding[key] for key in ("client_id", "engagement_id", "run_id")}
    before = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
    request = {"fictional_uncertain_public_write": True}
    private = output.parent / ".native-workspace"
    private.mkdir(exist_ok=True)
    (private / "inps-operations.json").write_text(
        json.dumps(
            {
                "operations": [
                    {
                        "key": "fictional-pending",
                        "request": request,
                        "fingerprint": hashlib.sha256(
                            json.dumps(
                                request, sort_keys=True, ensure_ascii=False
                            ).encode()
                        ).hexdigest(),
                        "status": "pending",
                    }
                ]
            }
        )
    )
    result = rpc_program(
        os.environ.copy(),
        f"const catalogue=payload(call('vera_workspace_open',{json.dumps({key: binding[key] for key in ('client_id', 'engagement_id')})}));const work={{work_ref:catalogue.works[0].work_ref}};"
        + """
const page=payload(call('vera_workspace_inps_setup',work));
const denied=call('vera_workspace_inps_draft_save',{...work,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision,fields:{reviewer:'',decisions:{}}});
"""
        + f"const closure=call('vera_workspace_archive_closure',{json.dumps(selected)});const result={{page,denied,closure}};",
    )
    assert result["page"]["recovery_required"] is True
    assert result["page"]["can_write"] is False
    assert result["denied"]["isError"] is True
    assert result["closure"]["isError"] is True
    assert (
        "ordinary recovery before output closure"
        in result["closure"]["content"][0]["text"]
    )
    assert {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()} == before
