"""Real owned new-run creation from fictional public SARI review workpapers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.plugins import test_vera_native_workspace as factory
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import process_environment
from tests.plugins.test_vera_native_sari_authoring import (
    author_program,
    register_program,
)
from tests.plugins.test_vera_native_sari_review import prepared_sari  # noqa: F401
from tests.plugins.test_vera_native_sari_review import (
    output_bytes,
    review_program,
    saved_program,
)

__all__ = []


@pytest.fixture
def owned_sari(tmp_path):
    """Exit the real registry setup process so its exclusive OS lease is released."""
    env = {
        **process_environment(),
        "VERA_WORKSPACE_PYTHON": sys.executable,
        "VERA_WORKSPACE_TENANT_ID": "fictional-sari-followup-tenant",
        "VERA_WORKSPACE_ACTOR_ID": "fictional-sari-followup-reviewer",
        "VERA_WORKSPACE_ROLES": "REVIEWER",
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-sari-followup-session",
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(tmp_path / "private-state"),
    }
    code = """
import json, sys
from pathlib import Path
from tests.plugins import test_registro_imprese_sari_plugin as public
captured = {}
original = public._running_sari_workspace
def capture(path):
    captured.update(original(path))
    return captured
public._running_sari_workspace = capture
output, _ = public._prepare_case(Path(sys.argv[1]), include_inventory=True)
print(json.dumps({'captured':captured,'output':output}, default=str))
"""
    built = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        env=env,
        cwd=factory.ROOT,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    data = json.loads(built.stdout)
    value = data["captured"]["context"]
    binding = {
        "client_root": data["captured"]["client_root"],
        **{key: value[key] for key in ("client_id", "engagement_id", "run_id")},
        "workflow_id": "registro-imprese-sari",
        "component": "registro-imprese-sari",
    }
    module = factory.workspace_module()
    from native_archive_navigation import work_ref

    binding["work_ref"] = work_ref(
        binding["client_id"], binding["engagement_id"], binding["run_id"]
    )
    output = Path(data["output"])
    applied = rpc_program(
        env,
        review_program((data["captured"], binding, output))
        + "privateFields.decisions[selectedReview.item_id].action='edit';privateFields.decisions[selectedReview.item_id].edit_value='Fictional new activity description requiring new review';\n"
        + saved_program()
        + "const result=payload(call('vera_workspace_sari_review_apply',publicApply));",
    )
    assert applied["public_result"]["persisted"] is True
    return env, binding, output, module


def followup_program(fixture):
    return f"""
const oldWork={{work_ref:{json.dumps(fixture[1]['work_ref'])}}};
const page=payload(call('vera_workspace_sari_followup_setup',oldWork));
const authority=p=>({{...oldWork,revision:p.revision,source_ref:p.source_ref,review_ticket:p.review_ticket,expected_draft_revision:p.draft_revision}});
const fields={{question:'Rework the fictional activity description from applied review. Treat all prior approvals as historical, leave new confirmations pending.',input_ids:[page.rows[0].input_id],include_previous_outputs:true,reference_date:'2026-10-08',client_reference:'FICTIONAL-FOLLOWUP-CLIENT',language:'it',jurisdiction:'IT'}};
const saved=payload(call('vera_workspace_sari_followup_draft_save',{{...authority(page),fields}}));
const createArgs={{...authority(page),expected_draft_revision:saved.draft_revision,fields,confirmed:true,idempotency_key:'fictional-followup-create'}};
"""


def test_sari_followup_creates_exact_distinct_registered_history_and_model_mandate(
    owned_sari,
):
    env, binding, output, module = owned_sari
    before = output_bytes(output)
    result = rpc_program(
        env,
        followup_program(owned_sari)
        + """
const created=payload(call('vera_workspace_sari_followup_create',createArgs));
const retry=payload(call('vera_workspace_sari_followup_create',createArgs));
const mandate={work_ref:created.work_ref,grant_ref:created.grant_ref};
const read=payload(call('vera_workspace_sari_author_read',mandate));
const contextCall=call('vera_workspace_sari_author_context',{...mandate,revision:read.revision});
const result={page,created,retry,contextCall,read,after:payload(call('vera_workspace_sari_followup_setup',oldWork))};
""",
    )
    assert result["page"]["can_create"] is True
    assert result["created"] == result["retry"]
    assert result["created"]["run_id"] != binding["run_id"]
    assert result["created"]["ready_to_file"] is False
    assert result["created"]["professional_approvals_carried"] is False
    assert result["contextCall"].get("isError") is not True
    context = result["contextCall"]["structuredContent"]
    assert context["professional_decisions"] == "pending_only"
    assert context["actual_model_reads_verified"] is False
    assert context["question"].startswith("Rework the fictional activity")
    assert output_bytes(output) == before
    state = module.ui_state_directory(output, create=False)
    operations = json.loads((state / "sari-followup-operations.json").read_bytes())[
        "operations"
    ]
    assert len(operations) == 1
    assert operations[0]["status"] == "complete"
    lineage = json.loads(
        (
            state
            / "sari-followups"
            / operations[0]["snapshot_ref"]
            / "followup-lineage.json"
        ).read_bytes()
    )
    originals = {row["input_id"]: row for row in context["selected_originals"]}
    for row in lineage["history_inputs"]:
        assert originals[row["input_id"]]["sha256"] == row["sha256"]
        assert (
            hashlib.sha256(before[row["predecessor_relative_path"]]).hexdigest()
            == row["sha256"]
        )
    assert lineage["professional_approvals_carried"] is False
    assert len(result["after"]["successors"]) == 1


@pytest.mark.parametrize(
    "invalid",
    [
        "confirmation",
        "whole_history",
        "changed_draft",
        "foreign_input",
        "stale",
        "viewer",
    ],
)
def test_sari_followup_invalid_requests_create_no_intent_or_successor(
    owned_sari, invalid
):
    env, _, output, module = owned_sari
    before = output_bytes(output)
    edits = {
        "confirmation": "createArgs.confirmed=false;",
        "whole_history": "createArgs.fields.include_previous_outputs=false;",
        "changed_draft": "createArgs.fields.question+=' Changed after save';",
        "foreign_input": "createArgs.fields.input_ids=['input-foreign'];",
        "stale": "createArgs.expected_draft_revision='0'.repeat(64);",
        "viewer": "process.env.VERA_WORKSPACE_ROLES='VIEWER';",
    }
    result = rpc_program(
        env,
        followup_program(owned_sari)
        + edits[invalid]
        + "const result=call('vera_workspace_sari_followup_create',createArgs);",
    )
    assert result["isError"] is True
    assert output_bytes(output) == before
    assert not (
        module.ui_state_directory(output, create=False)
        / "sari-followup-operations.json"
    ).exists()


def test_sari_pending_followup_blocks_other_registry_tools_and_archive_closure(
    owned_sari, monkeypatch
):
    env, binding, output, module = owned_sari
    home = module.ui_state_directory(output)
    (home / "sari-followups" / "unreceipted-fictional-copy").mkdir(parents=True)
    result = rpc_program(
        env,
        f"const result=call('vera_workspace_sari_review_setup',{{work_ref:{json.dumps(binding['work_ref'])}}});",
    )
    assert result["isError"] is True
    assert "follow-up" in result["content"][0]["text"]
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from native_archive_navigation import archive_module
    from native_sari_followup import closure_audit

    core = archive_module(module.module_root("studio-archive"))
    loaded = module.load_binding(binding)
    audited = closure_audit(
        core, Path(binding["client_root"]), loaded, SimpleNamespace(**vars(module))
    )
    assert audited["recovery_required"] is True


def test_sari_followup_new_proposal_public_packaging_and_review_leave_old_case_unchanged(
    owned_sari,
):
    env, binding, output, _ = owned_sari
    before = output_bytes(output)
    proposal_fixture = (
        "const proposal=" + author_program(owned_sari).split("const proposal=", 1)[1]
    )
    new_review = review_program((None, binding, None)).replace(
        json.dumps(binding["work_ref"]), "created.work_ref"
    )
    result = rpc_program(
        env,
        followup_program(owned_sari)
        + """
const created=payload(call('vera_workspace_sari_followup_create',createArgs));
const work={work_ref:created.work_ref},mandate={...work,grant_ref:created.grant_ref};
const read=payload(call('vera_workspace_sari_author_read',mandate));
const grant={...created,revision:read.revision};
const contextCall=call('vera_workspace_sari_author_context',{...mandate,revision:grant.revision});
if(contextCall.isError)throw new Error(contextCall.content[0].text);
const context=contextCall.structuredContent;
const question={question:fields.question,input_ids:context.selected_originals.map(row=>row.input_id)};
"""
        + proposal_fixture
        + """
proposal.case_intake.activity.description='Fictional NEW activity proposed after prior review; confirmation pending.';
proposal.practice_plan.case_summary='Fictional NEW source-linked diagnosis; prior confirmations not inherited.';
"""
        + register_program()
        + """
const registered=payload(call('vera_workspace_sari_author_register',registerArgs));
"""
        + new_review
        + saved_program()
        + """
const applied=payload(call('vera_workspace_sari_review_apply',publicApply));
const current=payload(call('vera_workspace_sari_review_setup',reviewWork));
const newOutputs=payload(call('vera_workspace_sari_review_outputs',{...work,revision:current.revision}));
const result={created,registered,applied,initial:context.initial_case,current,newOutputs};
""",
    )
    assert result["registered"]["status"] == "partial_review"
    assert result["applied"]["public_result"]["persisted"] is True
    assert result["current"]["final_artifacts"]["ready_to_file"] is False
    assert result["initial"]["competent_chamber"]["confirmation_status"] == "unknown"
    assert output_bytes(output) == before
    new_case = next(
        row
        for row in result["newOutputs"]["files"]
        if row["name"] == "case_intake_draft.json"
    )
    assert "Fictional NEW activity" in new_case["content"]


def test_sari_followup_operator_bound_pilot_reads_without_live_archive_or_creation(
    prepared_sari,
):
    """The explicit fixture binding stays read-only for a new Archive run."""
    import os

    before = output_bytes(prepared_sari[2])
    result = rpc_program(
        os.environ.copy(),
        f"const result=payload(call('vera_workspace_sari_followup_setup',{{work_ref:{json.dumps(prepared_sari[1]['work_ref'])}}}));",
    )
    assert result["can_create"] is False
    assert result["applied_review"] is None
    assert result["rows"][0]["original_name"] == "received-evidence.txt"
    assert output_bytes(prepared_sari[2]) == before


@pytest.mark.parametrize("tamper", ["pending_parent", "retained_history"])
def test_sari_followup_successor_refuses_uncertain_parent_or_changed_historical_bytes(
    owned_sari, tamper
):
    env, _, output, module = owned_sari
    created = rpc_program(
        env,
        followup_program(owned_sari)
        + "const result=payload(call('vera_workspace_sari_followup_create',createArgs));",
    )
    home = module.ui_state_directory(output, create=False)
    path = home / "sari-followup-operations.json"
    state = json.loads(path.read_bytes())
    if tamper == "pending_parent":
        state["operations"][0]["status"] = "pending"
        path.write_text(json.dumps(state))
    else:
        preserved = (
            home
            / "sari-followups"
            / state["operations"][0]["snapshot_ref"]
            / "prior-outputs"
            / "practice_plan_draft.json"
        )
        preserved.write_text("Changed historical bytes")
    request = {"work_ref": created["work_ref"], "grant_ref": created["grant_ref"]}
    refused = rpc_program(
        env,
        f"const result=call('vera_workspace_sari_author_read',{json.dumps(request)});",
    )
    assert refused["isError"] is True
    assert "follow-up" in refused["content"][0]["text"]
