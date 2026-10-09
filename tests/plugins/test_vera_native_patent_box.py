"""Actual fictional Archive/MCP Patent Box producers; no installed-host claim."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import process_environment
from tests.plugins.test_vera_native_workspace import ROOT

__all__ = []


@pytest.fixture
def owned_patent_box(tmp_path):
    """Exit the actual Archive builder to release its OS lease before MCP calls."""

    def build(kind="synthetic"):
        base = tmp_path / kind
        base.mkdir()
        env = {
            **process_environment(),
            "VERA_WORKSPACE_PYTHON": sys.executable,
            "VERA_WORKSPACE_TENANT_ID": "fictional-patent-box-tenant",
            "VERA_WORKSPACE_ACTOR_ID": "fictional-patent-box-reviewer",
            "VERA_WORKSPACE_ROLES": "REVIEWER",
            "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-patent-box-session",
            "VERA_STUDIO_ARCHIVE_STATE_DIR": str(base / "private-state"),
            "VERA_STUDIO_ARCHIVE_PROFILE_DIR": str(base / "private-profile"),
        }
        code = """
import json,sys,shutil
from pathlib import Path
from tests.plugins import test_patent_box_workflow as public
from tests.plugins.test_vera_native_workspace import workspace_module
base,kind=Path(sys.argv[1]),sys.argv[2]
workflow=public.workflow.__wrapped__()
table,plan=None,None
if kind=='normalized':
    from tests.plugins.test_patent_box_ledger_workflow import mapped_case
    run,proposal,table,plan=mapped_case(base,workflow)
else:
    run=public.running_case(base,workflow,demo=kind!='real')
    proposal=public.model_proposal(run,workflow) if kind!='empty' else None
if kind=='empty':
    for path in run['output'].iterdir():
        shutil.rmtree(path) if path.is_dir() else path.unlink()
api=workspace_module()
from native_archive_navigation import work_ref
context=json.loads(run['context'].read_text())
binding={**{k:context[k] for k in ('client_id','engagement_id','run_id')},'component':'patent-box-review','workflow_id':'patent-box-review','client_root':str(base/'studio'/'Synthetic software company')}
binding['work_ref']=work_ref(binding['client_id'],binding['engagement_id'],binding['run_id'])
print(json.dumps({'binding':binding,'output':str(run['output']),'proposal':proposal,'session':run['session'],'table':table,'plan':plan}))
"""
        completed = subprocess.run(
            [sys.executable, "-c", code, str(base), kind],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        return env, json.loads(completed.stdout)

    return build


def program(fixture):
    """Use genuine signed app tickets and complete real producer payloads."""
    ref = json.dumps(fixture[1]["binding"]["work_ref"])
    return f"""
const workRef={ref};
const setup=operation=>payload(call('vera_workspace_patent_box_setup',{{work_ref:workRef,operation}}));
const authority=p=>({{work_ref:workRef,operation:p.operation,revision:p.revision,source_ref:p.source_ref,review_ticket:p.review_ticket,expected_draft_revision:p.draft_revision}});
const perform=(operation,fields,key)=>{{
  const page=setup(operation);
  const saved=payload(call('vera_workspace_patent_box_draft_save',{{...authority(page),fields}}));
  const args={{...authority(page),expected_draft_revision:saved.draft_revision,fields,confirmed:true,idempotency_key:key}};
  return {{receipt:payload(call('vera_workspace_patent_box_execute',args)),args}};
}};
"""


def public_files(fixture):
    output = Path(fixture[1]["output"])
    return {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*")
        if p.is_file()
    }


def test_patent_box_empty_run_initialization_and_exact_retry_keep_no_decision(
    owned_patent_box,
):
    fixture = owned_patent_box("empty")
    result = rpc_program(
        fixture[0],
        program(fixture)
        + """
const first=perform('initialize',{as_of:'2026-09-23',demo:true},'fictional-init');
const retry=payload(call('vera_workspace_patent_box_execute',first.args));
const page=setup('initialize');
const result={first:first.receipt,retry,page};
""",
    )
    assert result["first"] == result["retry"]
    assert result["first"]["status"] == "complete"
    assert len(result["page"]["session"]["inputs"]) == 2
    assert result["page"]["confirmation_restored"] is False
    assert result["page"]["draft_stale"] is True
    assert result["page"]["proposals"] == []
    assert not any(name.startswith("decision_") for name in public_files(fixture))


def test_patent_box_private_draft_cas_restores_literal_fields_without_consent(
    owned_patent_box,
):
    fixture = owned_patent_box()
    before = public_files(fixture)
    result = rpc_program(
        fixture[0],
        program(fixture)
        + """
const page=setup('review');
const fields={reviewer:'  FICTIONAL DECLARED NAME  ',confirmation_ref:''};
const saved=payload(call('vera_workspace_patent_box_draft_save',{...authority(page),fields}));
const old=call('vera_workspace_patent_box_draft_save',{...authority(page),fields:{reviewer:'Other'}});
const reopened=setup('review');
const missing=call('vera_workspace_patent_box_execute',{...authority(reopened),fields,idempotency_key:'missing-consent'});
const result={saved,old,reopened,missing};
""",
    )
    assert result["reopened"]["fields"] == {
        "reviewer": "  FICTIONAL DECLARED NAME  ",
        "confirmation_ref": "",
    }
    assert result["reopened"]["confirmation_restored"] is False
    assert result["old"]["isError"] is True
    assert result["missing"]["isError"] is True
    assert public_files(fixture) == before


def test_patent_box_synthetic_whole_proposal_review_and_calculation_use_public_engine(
    owned_patent_box,
):
    fixture = owned_patent_box()
    before = public_files(fixture)
    result = rpc_program(
        fixture[0],
        program(fixture)
        + f"const proposal={json.dumps(fixture[1]['proposal'])};\n"
        + """
const prepared=perform('propose',{proposal},'fictional-proposal');
const digest=prepared.receipt.public_result.proposal_digest;
const review=perform('review',{digest,reviewer:'FICTIONAL REVIEWER',confirmation_ref:'fictional-test-confirmation',synthetic:true},'fictional-review');
const calculation=perform('calculate',{digest},'fictional-calculation');
const retry=payload(call('vera_workspace_patent_box_execute',calculation.args));
const page=setup('calculate');
const original=payload(call('vera_workspace_patent_box_read',{work_ref:workRef,operation:page.operation,revision:page.revision,source_ref:page.source_ref,file_ref:'proposal_'+digest+'.json'}));
const pdf=payload(call('vera_workspace_patent_box_artifact',{work_ref:workRef,operation:page.operation,revision:page.revision,source_ref:page.source_ref,file_ref:'calculation_'+digest+'/fascicolo_A_B.pdf'}));
const word=payload(call('vera_workspace_patent_box_artifact',{work_ref:workRef,operation:page.operation,revision:page.revision,source_ref:page.source_ref,file_ref:'calculation_'+digest+'/fascicolo_A_B.docx'}));
const result={prepared:prepared.receipt,review:review.receipt,calculation:calculation.receipt,retry,page,original,pdf,word};
""",
    )
    assert (
        result["review"]["public_result"]["identity_assurance"]
        == "SYNTHETIC_ACCEPTANCE"
    )
    assert result["calculation"]["public_result"]["result"]["additional_deduction"] == {
        "income": "110000.00",
        "irap": "88000.00",
    }
    assert result["calculation"] == result["retry"]
    assert result["calculation"]["professional_acceptance"] is False
    assert (
        result["page"]["proposals"][0]["professional_verification_performed"] is False
    )
    assert result["original"]["content"]
    after = public_files(fixture)
    assert before.items() <= after.items()
    assert any(name.endswith("/fascicolo_A_B.docx") for name in after)
    assert any(name.endswith("/fascicolo_A_B.pdf") for name in after)
    pdf = base64.b64decode(result["pdf"]["content"], validate=True)
    word = base64.b64decode(result["word"]["content"], validate=True)
    assert pdf.startswith(b"%PDF-")
    assert word.startswith(b"PK")
    assert hashlib.sha256(pdf).hexdigest() == result["pdf"]["sha256"]
    assert hashlib.sha256(word).hexdigest() == result["word"]["sha256"]
    assert pdf in after.values()
    assert word in after.values()


def test_patent_box_real_local_review_does_not_authorize_calculation(
    owned_patent_box,
):
    fixture = owned_patent_box("real")
    result = rpc_program(
        fixture[0],
        program(fixture)
        + f"const proposal={json.dumps(fixture[1]['proposal'])};\n"
        + """
const prepared=perform('propose',{proposal},'fictional-real-proposal');
const digest=prepared.receipt.public_result.proposal_digest;
const review=perform('review',{digest,reviewer:'FICTIONAL UNAUTHENTICATED',confirmation_ref:'fictional-test-only',synthetic:false},'fictional-real-review');
const calculation=perform('calculate',{digest},'fictional-real-calculate');
const retry=payload(call('vera_workspace_patent_box_execute',calculation.args));
const page=setup('calculate');
const result={review:review.receipt,calculation:calculation.receipt,retry,page};
""",
    )
    assert (
        result["review"]["public_result"]["identity_assurance"]
        == "LOCAL_OPERATOR_ASSERTION_NOT_PROFESSIONAL_AUTHENTICATION"
    )
    assert result["calculation"]["status"] == "refused"
    assert "authenticated professional decision" in result["calculation"]["error"]
    assert result["calculation"] == result["retry"]
    assert result["page"]["can_write"] is True
    assert not any(name.endswith("/result.json") for name in public_files(fixture))


@pytest.mark.parametrize(
    "operation", ["accept_professional_review", "verify_formalities"]
)
def test_patent_box_no_firm_authority_is_created_by_refused_native_action(
    owned_patent_box, operation
):
    fixture = owned_patent_box()
    before = public_files(fixture)
    fields = (
        {
            "digest": "0" * 64,
            "request_digest": "0" * 64,
            "signature_ref": "../../foreign.der",
            "mandate_ref": "../../foreign.json",
            "mandate_signature_ref": "../../foreign.der",
        }
        if operation == "accept_professional_review"
        else {"plan": {}, "trust_basis": "Unconfigured fictional fixture"}
    )
    result = rpc_program(
        fixture[0],
        program(fixture)
        + f"const attempted=perform({json.dumps(operation)},{json.dumps(fields)},'fictional-authority-refused');const page=setup({json.dumps(operation)});const result={{attempted:attempted.receipt,page}};",
    )
    assert result["attempted"]["status"] == "refused"
    assert result["page"]["can_write"] is True
    assert public_files(fixture) == before
    assert "VERA_PATENT_BOX_AUTHORITY_CONFIG" not in fixture[0]


def test_patent_box_selected_ledger_inspection_uses_public_cell_and_row_references(
    owned_patent_box,
):
    fixture = owned_patent_box()
    ledger = next(
        row["evidence_id"]
        for row in fixture[1]["session"]["inputs"]
        if row["description"] == "ledger.csv"
    )
    result = rpc_program(
        fixture[0],
        program(fixture)
        + f"const evidence_id={json.dumps(ledger)};\n"
        + """
const options={format:'CSV',sheet:null,header_row:1,first_row:2,last_row:2,delimiter:',',encoding:'utf-8',pdf_extraction:null};
const inspected=perform('inspect_ledger',{evidence_id,options},'fictional-inspection');
const result=inspected.receipt;
""",
    )
    assert result["status"] == "complete"
    assert result["public_result"]["source_evidence_id"] == ledger
    assert len(result["public_result"]["rows"]) == 1
    assert result["public_result"]["rows"][0]["row_ref"]
    assert any(name.startswith("ledger_table_") for name in public_files(fixture))


def test_patent_box_viewer_cannot_save_or_invoke_producer(owned_patent_box):
    fixture = owned_patent_box()
    env = {**fixture[0], "VERA_WORKSPACE_ROLES": "VIEWER"}
    before = public_files(fixture)
    result = rpc_program(
        env,
        program(fixture)
        + """
const page=setup('calculate');
const refused=call('vera_workspace_patent_box_draft_save',{...authority(page),fields:{digest:'0'.repeat(64)}});
const tools=require('./plugins/vera/mcp/workspace.cjs').handle({jsonrpc:'2.0',id:2,method:'tools/list'}).result.tools.filter(t=>t.name.startsWith('vera_workspace_patent_box_')&&!t.name.startsWith('vera_workspace_patent_box_author_'));
const result={page,refused,tools};
""",
    )
    assert result["page"]["can_write"] is False
    assert result["refused"]["isError"] is True
    assert public_files(fixture) == before
    assert len(result["tools"]) == 6
    assert all(row["_meta"]["ui"]["visibility"] == ["app"] for row in result["tools"])


def test_patent_box_changed_retained_public_bytes_are_not_adopted(owned_patent_box):
    fixture = owned_patent_box("empty")
    rpc_program(
        fixture[0],
        program(fixture)
        + "const result=perform('initialize',{as_of:'2026-09-23',demo:true},'fictional-tamper-init').receipt;",
    )
    (Path(fixture[1]["output"]) / "intake.md").write_text("Tampered fictional intake")
    result = rpc_program(
        fixture[0],
        f"const result=call('vera_workspace_patent_box_setup',{{work_ref:{json.dumps(fixture[1]['binding']['work_ref'])},operation:'initialize'}});",
    )
    assert result["isError"] is True
    assert "public bytes changed" in result["content"][0]["text"]


def test_patent_box_normalized_population_and_proposal_replay_exact_public_plan(
    owned_patent_box,
):
    fixture = owned_patent_box("normalized")
    result = rpc_program(
        fixture[0],
        program(fixture)
        + f"const plan={json.dumps(fixture[1]['plan'])};const proposal={json.dumps(fixture[1]['proposal'])};\n"
        + """
const normalized=perform('normalize_ledger',{plan},'fictional-normalize');
proposal.normalization_digest=normalized.receipt.public_result.normalization_digest;
proposal.case.costs=normalized.receipt.public_result.costs;
proposal.case.ledger_control_total=normalized.receipt.public_result.ledger_control_total;
const prepared=perform('propose',{proposal},'fictional-normalized-proposal');
const page=setup('propose');
const record=payload(call('vera_workspace_patent_box_read',{work_ref:workRef,operation:page.operation,revision:page.revision,source_ref:page.source_ref,file_ref:'proposal_'+prepared.receipt.public_result.proposal_digest+'.json'}));
const result={normalized:normalized.receipt,prepared:prepared.receipt,record};
""",
    )
    assert result["normalized"]["status"] == "complete"
    assert result["normalized"]["public_result"]["ledger_control_total"] == "100000.00"
    stored = json.loads(result["record"]["content"])
    assert stored["normalization_record"]["plan"] == fixture[1]["plan"]
    assert stored["normalization_record"]["tables"] == [fixture[1]["table"]]
    assert stored["case"]["costs"] == result["normalized"]["public_result"]["costs"]


def test_patent_box_pending_actual_intent_prevents_retry_and_archive_closure(
    owned_patent_box,
):
    fixture = owned_patent_box("empty")
    result = rpc_program(
        fixture[0],
        program(fixture)
        + "const result=perform('initialize',{as_of:'2026-09-23',demo:true},'fictional-pending-init');",
    )
    output = Path(fixture[1]["output"])
    state_path = output.parent / ".native-workspace/patent-box-operations.json"
    state = json.loads(state_path.read_text())
    state["operations"][0]["status"] = "pending"
    state_path.write_text(json.dumps(state))
    result = rpc_program(
        fixture[0],
        program(fixture)
        + f"const original={json.dumps(result['args'])};const binding={json.dumps(fixture[1]['binding'])};\n"
        + """
const page=setup('initialize');
const retry=call('vera_workspace_patent_box_execute',original);
const closure=call('vera_workspace_archive_closure',{client_id:binding.client_id,engagement_id:binding.engagement_id,run_id:binding.run_id});
const result={page,retry,closure};
""",
    )
    assert result["page"]["recovery_required"] is True
    assert result["page"]["can_write"] is False
    assert result["retry"]["isError"] is True
    assert result["closure"]["isError"] is True
    assert "Patent Box operation" in result["closure"]["content"][0]["text"]


def test_patent_box_stale_draft_requires_explicit_discard_then_new_scope(
    owned_patent_box,
):
    fixture = owned_patent_box()
    rpc_program(
        fixture[0],
        program(fixture)
        + "const page=setup('review');const result=payload(call('vera_workspace_patent_box_draft_save',{...authority(page),fields:{reviewer:'FICTIONAL OLD DRAFT'}}));",
    )
    (Path(fixture[1]["output"]) / "ordinary_specialist_note.md").write_text(
        "New fictional source-bound note"
    )
    result = rpc_program(
        fixture[0],
        program(fixture)
        + """
const page=setup('review');
const refused=call('vera_workspace_patent_box_draft_save',{...authority(page),fields:{reviewer:'CHANGED'}});
const missing=call('vera_workspace_patent_box_draft_clear',authority(page));
const cleared=payload(call('vera_workspace_patent_box_draft_clear',{...authority(page),confirmed:true}));
const reopened=setup('review');
const result={page,refused,missing,cleared,reopened};
""",
    )
    assert result["page"]["draft_stale"] is True
    assert result["page"]["fields"] == {"reviewer": "FICTIONAL OLD DRAFT"}
    assert result["refused"]["isError"] is True
    assert result["missing"]["isError"] is True
    assert result["reopened"]["draft_stale"] is False
    assert result["reopened"]["fields"] == {}
    assert result["reopened"]["confirmation_restored"] is False


def test_patent_box_domain_closure_refuses_pending_intent_with_required_api_contract(
    owned_patent_box,
):
    """Domain contract check; it does not qualify the currently broken MCP closure route."""
    fixture = owned_patent_box("empty")
    rpc_program(
        fixture[0],
        program(fixture)
        + "const result=perform('initialize',{as_of:'2026-09-23',demo:true},'fictional-domain-pending').receipt;",
    )
    state_path = (
        Path(fixture[1]["output"]).parent
        / ".native-workspace/patent-box-operations.json"
    )
    state = json.loads(state_path.read_text())
    state["operations"][0]["status"] = "pending"
    state_path.write_text(json.dumps(state))
    code = """
import json,sys
from types import SimpleNamespace
from tests.plugins.test_vera_native_workspace import workspace_module
api=workspace_module()
import native_archive_closure
binding=json.loads(sys.argv[1])
args={k:binding[k] for k in ('client_id','engagement_id','run_id')}
try:
    native_archive_closure.snapshot(api.module_root('studio-archive'),args,SimpleNamespace(**vars(api)))
except ValueError as error:
    print(str(error))
else:
    raise AssertionError('Pending producer intent was incorrectly accepted')
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, json.dumps(fixture[1]["binding"])],
        cwd=ROOT,
        env=fixture[0],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert (
        "Patent Box operation requires ordinary recovery before closure"
        in completed.stdout
    )
