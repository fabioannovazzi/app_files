"""Offline native mechanics over real fictional owned public grant dossiers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins import test_vera_native_workspace as factory
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import process_environment

__all__ = []


@pytest.fixture
def owned_bandi(tmp_path):
    """Create actual Archive state in an exited process to release its OS lease."""

    def build(kind="prepared"):
        base = tmp_path / kind
        base.mkdir()
        env = {
            **process_environment(),
            "VERA_WORKSPACE_PYTHON": sys.executable,
            "VERA_WORKSPACE_TENANT_ID": "fictional-bandi-tenant",
            "VERA_WORKSPACE_ACTOR_ID": "fictional-bandi-reviewer",
            "VERA_WORKSPACE_ROLES": "REVIEWER",
            "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-bandi-session",
            "VERA_STUDIO_ARCHIVE_STATE_DIR": str(base / "private-state"),
        }
        code = """
import json, sys
from pathlib import Path
from tests.plugins import test_bandi_agevolazioni_plugin as public
base,kind=Path(sys.argv[1]),sys.argv[2]
if kind=='empty':
    workspace=public._running_workspace(base)
else:
    scripts,workspace=public._initialized_case(base)
    if kind in {'prepared','needs-review'}:
        public._reviewable_workbench(workspace['output_dir'])
    if kind=='prepared':
        public._accept_all_reviews(scripts,workspace)
context=json.loads(workspace['context_path'].read_text())
print(json.dumps({'workspace':workspace,'context':context},default=str))
"""
        built = subprocess.run(
            [sys.executable, "-c", code, str(base), kind],
            env=env,
            cwd=factory.ROOT,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        assert built.returncode == 0, built.stderr
        data = json.loads(built.stdout)
        context = data["context"]
        factory.workspace_module()
        from native_archive_navigation import work_ref

        binding = {
            **{key: context[key] for key in ("client_id", "engagement_id", "run_id")},
            "component": "bandi-agevolazioni",
            "workflow_id": "bandi-agevolazioni",
            "client_root": str(base / "Studio" / "Impresa Demo SPA"),
        }
        binding["work_ref"] = work_ref(
            binding["client_id"], binding["engagement_id"], binding["run_id"]
        )
        return env, binding, Path(data["workspace"]["output_dir"])

    return build


def program(fixture, scope="dossier"):
    return f"""
const identity={{work_ref:{json.dumps(fixture[1]['work_ref'])},scope:{json.dumps(scope)}}};
const page=payload(call('vera_workspace_bandi_setup',identity));
const authority=p=>({{...identity,revision:p.revision,source_ref:p.source_ref,review_ticket:p.review_ticket,expected_draft_revision:p.draft_revision}});
const literal={{decision:'accepted',reviewer_id:'fictional-reviewer',reviewer_role:'fictional-commercialista',notes:'Whole fictional scope reviewed; individual row confirmations remain separate.'}};
"""


def review_program(fixture, scope="dossier"):
    return (
        program(fixture, scope)
        + """
const saved=payload(call('vera_workspace_bandi_draft_save',{...authority(page),fields:literal}));
const reviewArgs={...authority(page),expected_draft_revision:saved.draft_revision,fields:literal,confirmed:true,idempotency_key:'fictional-whole-review'};
const recorded=payload(call('vera_workspace_bandi_review',reviewArgs));
"""
    )


def output_bytes(output):
    return {
        p.name: p.read_bytes()
        for p in output.iterdir()
        if p.is_file() and p.name != ".bandi-agevolazioni.lock"
    }


def test_bandi_initialization_preserves_private_draft_and_exact_completed_retry(
    owned_bandi,
):
    fixture = owned_bandi("empty")
    body = (
        program(fixture, "initialization")
        + """
const fields={reference_date:'2026-10-08',client_reference:'FICTIONAL-CLIENT',language:'it'};
const saved=payload(call('vera_workspace_bandi_draft_save',{...authority(page),fields}));
const reopened=payload(call('vera_workspace_bandi_setup',identity));
const args={...authority(reopened),fields,confirmed:true,idempotency_key:'fictional-initialize'};
const missing={...args};delete missing.confirmed;
const refused=call('vera_workspace_bandi_initialize',missing);
const first=payload(call('vera_workspace_bandi_initialize',args));
const retry=payload(call('vera_workspace_bandi_initialize',args));
const result={reopened,refused,first,retry};
"""
    )
    result = rpc_program(fixture[0], body)
    assert result["reopened"]["confirmation_restored"] is False
    assert result["reopened"]["draft_stale"] is False
    assert result["refused"]["isError"] is True
    assert result["first"] == result["retry"]
    assert result["first"]["public_result"]["status"] == "empty_drafts_created"
    assert result["first"]["model_reads_performed"] is False
    intake = json.loads((fixture[2] / "case_intake.json").read_text())
    assert intake["applicant"]["confirmation_status"] == "unknown"
    assert intake["professional_question"] == ""


@pytest.mark.parametrize(
    "scope", ["source_baseline", "requirements", "assessments", "dossier"]
)
def test_bandi_exact_scope_review_appends_public_event_without_row_confirmation(
    owned_bandi, scope
):
    fixture = owned_bandi("unreviewed")
    before = output_bytes(fixture[2])
    result = rpc_program(
        fixture[0],
        review_program(fixture, scope)
        + "const retry=payload(call('vera_workspace_bandi_review',reviewArgs));const result={page,recorded,retry};",
    )
    assert result["recorded"] == result["retry"]
    event = result["recorded"]["public_result"]
    assert event["scope"] == scope
    assert event["scope_sha256"] == result["page"]["scope_sha256"]
    assert event["identity_assurance"] == "asserted_not_authenticated"
    assert result["recorded"]["individual_record_confirmation_performed"] is False
    after = output_bytes(fixture[2])
    assert after["application_workbench.json"] == before["application_workbench.json"]
    assert after["source_register.json"] == before["source_register.json"]
    assert after["case_intake.json"] == before["case_intake.json"]
    assert json.loads(after["review_log.json"])["events"] == [event]


def test_bandi_failed_audit_persists_and_prevents_packaging(owned_bandi):
    fixture = owned_bandi("needs-review")
    result = rpc_program(
        fixture[0],
        program(fixture)
        + """
const args={...identity,revision:page.revision,source_ref:page.source_ref,review_ticket:page.review_ticket,idempotency_key:'fictional-validate'};
const validation=payload(call('vera_workspace_bandi_validate',args));
const retry=payload(call('vera_workspace_bandi_validate',args));
const current=payload(call('vera_workspace_bandi_setup',identity));
const refused=call('vera_workspace_bandi_package',{...identity,revision:current.revision,source_ref:current.source_ref,review_ticket:current.review_ticket,idempotency_key:'fictional-package'});
const result={validation,retry,current,refused};
""",
    )
    assert result["validation"]["public_result"]["status"] == "failed"
    assert result["validation"]["public_result"]["issues"]
    assert result["validation"] == result["retry"]
    assert result["current"]["audit_current"] is True
    assert result["refused"]["isError"] is True
    assert (fixture[2] / "validation_audit.json").exists()
    assert not (fixture[2] / "dossier_manifest.json").exists()


def test_bandi_passing_public_audit_and_package_keep_actual_complete_html(owned_bandi):
    fixture = owned_bandi()
    result = rpc_program(
        fixture[0],
        program(fixture)
        + """
const args={...identity,revision:page.revision,source_ref:page.source_ref,review_ticket:page.review_ticket,idempotency_key:'fictional-validate'};
const validation=payload(call('vera_workspace_bandi_validate',args));
const validated=payload(call('vera_workspace_bandi_setup',identity));
const packageArgs={...identity,revision:validated.revision,source_ref:validated.source_ref,review_ticket:validated.review_ticket,idempotency_key:'fictional-package'};
const packaged=payload(call('vera_workspace_bandi_package',packageArgs));
const retry=payload(call('vera_workspace_bandi_package',packageArgs));
const current=payload(call('vera_workspace_bandi_setup',identity));
const artifact=payload(call('vera_workspace_bandi_read',{...identity,revision:current.revision,source_ref:current.source_ref,file_name:'review_dossier.html'}));
const result={validation,packaged,retry,current,artifact};
""",
    )
    assert result["validation"]["public_result"]["status"] == "passed"
    assert result["packaged"] == result["retry"]
    assert result["current"]["package_current"] is True
    content = (fixture[2] / "review_dossier.html").read_text()
    assert result["artifact"]["content"] == content
    assert result["artifact"]["sha256"] == hashlib.sha256(content.encode()).hexdigest()
    assert result["packaged"]["ready_to_file"] is False
    manifest = json.loads((fixture[2] / "dossier_manifest.json").read_text())
    assert manifest["ready_to_file"] is False
    assert manifest["submission_actions_performed"] is False


def test_bandi_stale_draft_is_visible_and_explicitly_discarded_without_public_change(
    owned_bandi,
):
    fixture = owned_bandi()
    path = fixture[2] / "case_intake.json"
    result = rpc_program(
        fixture[0],
        program(fixture)
        + f"""
const saved=payload(call('vera_workspace_bandi_draft_save',{{...authority(page),fields:literal}}));
const fs=require('node:fs'),file={json.dumps(str(path))};const intake=JSON.parse(fs.readFileSync(file));intake.professional_question='Changed fictional question';fs.writeFileSync(file,JSON.stringify(intake));
const current=payload(call('vera_workspace_bandi_setup',identity));
const denied=call('vera_workspace_bandi_draft_save',{{...authority(current),fields:literal}});
const cleared=payload(call('vera_workspace_bandi_draft_clear',{{...authority(current),confirmed:true}}));
const reopened=payload(call('vera_workspace_bandi_setup',identity));const result={{current,denied,cleared,reopened}};
""",
    )
    assert result["current"]["draft_stale"] is True
    assert result["current"]["fields"]["reviewer_id"] == "fictional-reviewer"
    assert result["denied"]["isError"] is True
    assert result["reopened"]["draft_stale"] is False
    assert result["reopened"]["fields"]["decision"] == ""
    assert (
        json.loads(path.read_text())["professional_question"]
        == "Changed fictional question"
    )


def test_bandi_substituted_source_and_forged_ticket_refuse_public_mutation(owned_bandi):
    fixture = owned_bandi()
    before = output_bytes(fixture[2])
    result = rpc_program(
        fixture[0],
        program(fixture)
        + """
const args={...identity,revision:page.revision,source_ref:page.source_ref,review_ticket:page.review_ticket,idempotency_key:'fictional-validate'};
const wrong=call('vera_workspace_bandi_validate',{...args,source_ref:'other-source'});
const forged=call('vera_workspace_bandi_validate',{...args,review_ticket:page.review_ticket.slice(0,-1)+(page.review_ticket.endsWith('a')?'b':'a')});const result={wrong,forged};
""",
    )
    assert result["wrong"]["isError"] is True
    assert result["forged"]["isError"] is True
    assert output_bytes(fixture[2]) == before


def test_bandi_viewer_reads_complete_records_but_cannot_save_or_validate(owned_bandi):
    fixture = owned_bandi()
    env = {**fixture[0], "VERA_WORKSPACE_ROLES": "VIEWER"}
    before = output_bytes(fixture[2])
    result = rpc_program(
        env,
        program(fixture)
        + """
const artifact=payload(call('vera_workspace_bandi_read',{...identity,revision:page.revision,source_ref:page.source_ref,file_name:'case_intake.json'}));
const denied=call('vera_workspace_bandi_draft_save',{...authority(page),fields:literal});
const validated=call('vera_workspace_bandi_validate',{...identity,revision:page.revision,source_ref:page.source_ref,review_ticket:page.review_ticket,idempotency_key:'fictional-viewer'});const result={page,artifact,denied,validated};
""",
    )
    assert result["page"]["can_write"] is False
    assert result["artifact"]["content"] == before["case_intake.json"].decode()
    assert result["denied"]["isError"] is True
    assert result["validated"]["isError"] is True
    assert output_bytes(fixture[2]) == before


@pytest.mark.parametrize("defect", ["pending", "tampered_history"])
def test_bandi_uncertain_or_altered_retained_versions_block_writes_and_closure(
    owned_bandi, defect
):
    fixture = owned_bandi("unreviewed")
    state = fixture[2].parent / ".native-workspace" / "bandi-operations.json"
    body = (
        review_program(fixture)
        + f"""
const fs=require('node:fs'),statePath={json.dumps(str(state))};const operations=JSON.parse(fs.readFileSync(statePath));
if({json.dumps(defect)}==='pending'){{operations.operations[0].status='pending';fs.writeFileSync(statePath,JSON.stringify(operations));}}else{{fs.writeFileSync({json.dumps(str(state.parent / 'bandi-receipts'))}+'/'+operations.operations[0].snapshot_ref+'/case_intake.json','tampered prior version');}}
const reopened=call('vera_workspace_bandi_setup',identity);
const closure=call('vera_workspace_archive_closure',{{client_id:{json.dumps(fixture[1]['client_id'])},engagement_id:{json.dumps(fixture[1]['engagement_id'])},run_id:{json.dumps(fixture[1]['run_id'])}}});
const result={{reopened,closure}};
"""
    )
    result = rpc_program(fixture[0], body)
    if defect == "pending":
        assert result["reopened"]["_meta"]["workspace"]["recovery_required"] is True
        assert result["reopened"]["_meta"]["workspace"]["can_write"] is False
    else:
        assert result["reopened"]["isError"] is True
    assert result["closure"]["isError"] is True


def test_bandi_oversized_complete_record_is_refused_without_truncation(owned_bandi):
    fixture = owned_bandi()
    path = fixture[2] / "case_intake.json"
    intake = json.loads(path.read_text())
    intake["professional_question"] = "x" * 2_000_001
    path.write_text(json.dumps(intake))
    result = rpc_program(
        fixture[0],
        f"const result=call('vera_workspace_bandi_setup',{{work_ref:{json.dumps(fixture[1]['work_ref'])}}});",
    )
    assert result["isError"] is True
    assert "whole-record boundary" in result["content"][0]["text"]


def test_bandi_dossier_tools_remain_app_only_without_model_handoff():
    program = f"const service=require({json.dumps(str(factory.SERVER))});process.stdout.write(JSON.stringify(service.handle({{jsonrpc:'2.0',id:1,method:'tools/list'}}).result.tools.filter(t=>t.name.startsWith('vera_workspace_bandi_')&&!t.name.startsWith('vera_workspace_bandi_author_'))));"
    result = subprocess.run(
        [factory.NODE, "-e", program],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    tools = json.loads(result.stdout)
    assert len(tools) == 8
    assert all(tool["_meta"]["ui"]["visibility"] == ["app"] for tool in tools)
