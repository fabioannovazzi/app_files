"""Literal complete narrative conservation, independent of accounting approval."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_vera_native_archive_closure import declare_all, setup
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_variance import variance_run  # noqa: F401
from tests.plugins.test_vera_native_variance_authoring import author_run  # noqa: F401
from tests.plugins.test_vera_native_variance_review import (  # noqa: F401
    initial,
    review_run,
)

__all__ = []

NOTES = {
    "codex_business_analysis.md": "# Fictional business analysis\n47,000 to 53,000; delta 6,000. These are calculations, not verified economic causes. Report remains draft.\n",
    "codex_root_cause_sweep_analysis.md": "# Fictional alternative interpretation\nReview every retained sequence using its exact numerical table. Residuals depend on preceding contributions. No automatic choice or claimed business cause.\n",
    "codex_run_review.md": "# Fictional run review\nRefer to standard_variance_context.json, root_cause_sweep_summary.csv and final_artifacts.json. No real model reads in this synthetic test. Professional approval remains open.\n",
}
READBACK = {
    "decision": "accepted",
    "reviewer": "Fictional named note reviewer",
    "reviewed_at": "2026-10-08T12:00:00+02:00",
    "basis": "Literal fictional readback of all three whole notes and open limits.",
}


def proposed(fixture) -> str:
    """Calculate through the public runner, then retain one complete host proposal."""
    return (
        initial(fixture)
        + f"""
const sealedFs=require('node:fs'),sealedCrypto=require('node:crypto');
const sealedRoot=folder=>Object.fromEntries(sealedFs.readdirSync(folder,{{withFileTypes:true}}).flatMap(p=>p.isDirectory()?Object.entries(sealedRoot(folder+'/'+p.name)).map(([k,v])=>[p.name+'/'+k,v]):[[p.name,sealedCrypto.createHash('sha256').update(sealedFs.readFileSync(folder+'/'+p.name)).digest('hex')]]));
const sealedFolder={json.dumps(str(fixture[1]))}+'/'+original.source_ref, sealedBefore=sealedRoot(sealedFolder);
const exact={{...originalWork,source_ref:original.source_ref}};
const before=payload(call('vera_workspace_variance_narrative_setup',exact));
const stageArgs={{...exact,revision:before.revision,documents:{json.dumps(NOTES)},idempotency_key:'fictional-notes-stage'}};
const stagedCall=call('vera_workspace_variance_narrative_stage',stageArgs);
if(stagedCall.isError)throw new Error(stagedCall.content[0].text);
const staged=stagedCall.structuredContent;
const chosen={{...exact,case_ref:staged.case_ref}};
const page=payload(call('vera_workspace_variance_narrative_read',chosen));
const noteAuthority=p=>({{...chosen,revision:p.revision,review_ticket:p.review_ticket,item_id:p.selection.id,expected_draft_revision:p.draft_revision}});
"""
    )


def conserved(decision: str = "accepted") -> str:
    return f"""
const fields={json.dumps({**READBACK, 'decision': decision})};
payload(call('vera_workspace_variance_narrative_draft_save',{{...noteAuthority(page),fields}}));
const fresh=payload(call('vera_workspace_variance_narrative_read',chosen));
const commitArgs={{...noteAuthority(fresh),confirmed:true,idempotency_key:'fictional-notes-commit'}};
const committed=payload(call('vera_workspace_variance_narrative_commit',commitArgs));
const retained=payload(call('vera_workspace_variance_narrative_read',chosen));
"""


def hashes(folder: Path) -> dict:
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize("decision", ["accepted", "rejected", "changes_requested"])
def test_native_variance_notes_preserve_three_literal_documents_and_accounting_gate(
    review_run, decision
):
    result = rpc_program(
        review_run[0],
        proposed(review_run)
        + conserved(decision)
        + """
const result={original,sealedBefore,sealedAfter:sealedRoot(sealedFolder),staged,committed,retained,stageRetry:call('vera_workspace_variance_narrative_stage',stageArgs).structuredContent,retry:payload(call('vera_workspace_variance_narrative_commit',commitArgs)),after:payload(call('vera_workspace_variance_setup',originalWork))};
""",
    )
    output = review_run[1]
    generation = output / result["original"]["source_ref"]
    receipt = json.loads(
        (
            output / result["committed"]["output_ref"] / "narrative_receipt.json"
        ).read_bytes()
    )
    assert len(hashes(generation)) == 93
    assert result["sealedBefore"] == result["sealedAfter"] == hashes(generation)
    assert (
        result["original"]["accounting_readiness"]
        == result["after"]["accounting_readiness"]
        == receipt["accounting_readiness"]
    )
    assert (
        result["after"]["accounting_readiness"]["client_report_status"]
        == "draft_pending_professional_review"
    )
    assert result["committed"] == result["retry"]
    assert result["staged"] == result["stageRetry"]
    assert result["retained"]["documents"] == NOTES
    assert result["retained"]["can_write"] is False
    assert result["retained"]["status"] == decision
    assert result["retained"]["conservation"]["review"] == {
        **READBACK,
        "decision": decision,
    }
    assert len(result["retained"]["files"]) == 4
    assert receipt["professional_approval"] is False
    assert receipt["actual_model_reads_verified"] is False
    assert receipt["reviewer_authenticated"] is False
    assert receipt["run_completed"] is False
    assert receipt["sent_or_published"] is False
    for name, text in NOTES.items():
        assert (
            output / result["committed"]["output_ref"] / name
        ).read_bytes() == text.encode()


def test_native_variance_note_context_paginates_all_verified_references_and_omits_private_readback(
    review_run,
):
    result = rpc_program(
        review_run[0],
        proposed(review_run)
        + f"""
const secretFields={json.dumps({**READBACK,'reviewer':'PRIVATE_UNSENT_REVIEWER','basis':'PRIVATE_UNSENT_BASIS'})};
payload(call('vera_workspace_variance_narrative_draft_save',{{...noteAuthority(page),fields:secretFields}}));
const records=[];let context;
for(let offset=0;;offset+=30){{const c=call('vera_workspace_variance_narrative_context',{{...exact,revision:page.revision,offset}});if(c.isError)throw new Error(c.content[0].text);context=c.structuredContent;records.push(...context.artifacts);if(!context.has_more)break;}}
const whole=call('vera_workspace_variance_narrative_context',{{...chosen,revision:page.revision}}).structuredContent;
const result={{records,context,whole,original}};
""",
    )
    generation = review_run[1] / result["original"]["source_ref"]
    manifest = json.loads((generation / "model_use_manifest.json").read_bytes())
    numerical = manifest["default_model_use"]["artifacts"]
    assert len(result["records"]) == len(numerical) + len(
        list(generation.rglob("*.png"))
    )
    assert [r["path"] for r in result["records"][: len(numerical)]] == [
        r["path"] for r in numerical
    ]
    assert "chosen_documents" not in result["context"]
    assert result["whole"]["chosen_documents"] == NOTES
    assert "PRIVATE_UNSENT" not in json.dumps(result)
    assert result["context"]["actual_model_reads_verified"] is False
    for record in result["records"]:
        assert (
            hashlib.sha256(Path(record["authorized_path"]).read_bytes()).hexdigest()
            == record["sha256"]
        )


@pytest.mark.parametrize("variance_run", ["blocked", "partial"], indirect=True)
def test_native_variance_note_acceptance_cannot_promote_blocked_or_partial_accounting_report(
    review_run,
):
    result = rpc_program(
        review_run[0],
        proposed(review_run)
        + conserved()
        + "const result={original,retained,after:payload(call('vera_workspace_variance_setup',originalWork))};",
    )
    assert (
        result["original"]["accounting_readiness"]
        == result["retained"]["accounting_readiness"]
        == result["after"]["accounting_readiness"]
    )
    assert (
        result["after"]["accounting_readiness"]["client_report_status"]
        != "approved_for_client_use"
    )


@pytest.mark.parametrize("bad", ["missing", "extra", "empty", "oversize"])
def test_native_variance_notes_refuse_incomplete_or_oversize_proposal_without_partial_intent(
    review_run, bad
):
    invalid = dict(NOTES)
    if bad == "missing":
        invalid.pop("codex_run_review.md")
    elif bad == "extra":
        invalid["another.md"] = "Extra file"
    elif bad == "empty":
        invalid["codex_run_review.md"] = "  "
    else:
        invalid["codex_run_review.md"] = "x" * 96001
    result = rpc_program(
        review_run[0],
        initial(review_run)
        + f"""
const exact={{...originalWork,source_ref:original.source_ref}};const page=payload(call('vera_workspace_variance_narrative_setup',exact));
const rejected=call('vera_workspace_variance_narrative_stage',{{...exact,revision:page.revision,documents:{json.dumps(invalid)},idempotency_key:'fictional-invalid-notes'}});
const result={{rejected,after:payload(call('vera_workspace_variance_narrative_setup',exact))}};
""",
    )
    assert result["rejected"]["isError"] is True
    assert result["after"]["versions"] == []
    assert (
        list(
            (review_run[1].parent / ".native-workspace").glob(
                "variance-narrative-request-*.json"
            )
        )
        == []
    )


@pytest.mark.parametrize(
    "bad",
    [
        "unsigned",
        "altered_signature",
        "foreign_item",
        "foreign_source",
        "foreign_proposal",
        "stale_revision",
        "stale_draft",
        "unconfirmed",
        "incomplete_readback",
        "naive_time",
    ],
)
def test_native_variance_note_commit_refuses_wrong_authority_or_readback_without_conservation(
    review_run, bad
):
    altered = {**READBACK}
    if bad == "incomplete_readback":
        altered["basis"] = ""
    if bad == "naive_time":
        altered["reviewed_at"] = "2026-10-08T12:00:00"
    mutation = {
        "unsigned": "delete args.review_ticket;",
        "altered_signature": "{const [b,s]=args.review_ticket.split('.');args.review_ticket=b+'.'+(s[0]==='a'?'b':'a')+s.slice(1);}",
        "foreign_item": "args.item_id='variance-narrative-'+'0'.repeat(64);",
        "foreign_source": "args.source_ref='variance-'+'0'.repeat(64);",
        "foreign_proposal": "args.case_ref='variance-narrative-'+'0'.repeat(64);",
        "stale_revision": "args.revision='0'.repeat(64);",
        "stale_draft": "args.expected_draft_revision=page.draft_revision;",
        "unconfirmed": "args.confirmed=false;",
        "incomplete_readback": "",
        "naive_time": "",
    }[bad]
    result = rpc_program(
        review_run[0],
        proposed(review_run)
        + f"""
payload(call('vera_workspace_variance_narrative_draft_save',{{...noteAuthority(page),fields:{json.dumps(altered)}}}));
const fresh=payload(call('vera_workspace_variance_narrative_read',chosen));
const args={{...noteAuthority(fresh),confirmed:true,idempotency_key:'fictional-refuse-commit'}};{mutation}
const refused=call('vera_workspace_variance_narrative_commit',args);
const result={{refused,after:payload(call('vera_workspace_variance_narrative_read',chosen))}};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["after"]["status"] == "pending"
    assert result["after"]["conservation"] is None
    assert list(review_run[1].glob("codex-notes-*")) == []


def test_native_variance_note_draft_cas_keeps_other_window_and_empty_readback(
    review_run,
):
    result = rpc_program(
        review_run[0],
        proposed(review_run)
        + f"""
const saved=payload(call('vera_workspace_variance_narrative_draft_save',{{...noteAuthority(page),fields:{json.dumps(READBACK)}}}));
const stale=call('vera_workspace_variance_narrative_draft_save',{{...noteAuthority(page),fields:{{decision:'',reviewer:'',reviewed_at:'',basis:''}}}});
const current=payload(call('vera_workspace_variance_narrative_read',chosen));
payload(call('vera_workspace_variance_narrative_draft_save',{{...noteAuthority(current),fields:{{decision:'',reviewer:'',reviewed_at:'',basis:''}}}}));
const result={{stale,current,cleared:payload(call('vera_workspace_variance_narrative_read',chosen))}};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["current"]["draft"] == READBACK
    assert result["cleared"]["draft"] == dict.fromkeys(READBACK, "")
    assert list(review_run[1].glob("codex-notes-*")) == []


def test_native_variance_pending_notes_block_archive_closure(review_run):
    selected = {k: review_run[2][k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        review_run[0],
        proposed(review_run)
        + f"const result={{refused:call('vera_workspace_archive_closure',{json.dumps(selected)})}};",
    )
    assert result["refused"]["isError"] is True
    assert (
        "notes require recovery or explicit named readback"
        in result["refused"]["content"][0]["text"]
    )


def test_native_variance_completed_archive_keeps_conserved_note_readonly(review_run):
    first = rpc_program(
        review_run[0],
        proposed(review_run) + conserved() + "const result={original,chosen};",
    )
    write_no_model_report(review_run[1], "variance-analysis", review_run[2]["run_id"])
    selected = {k: review_run[2][k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        review_run[0],
        setup(selected)
        + declare_all()
        + f"""
payload(call('vera_workspace_archive_finalize',seal));const ready=read();
const completed=payload(call('vera_workspace_archive_complete',{{...authority(ready),human_reviewed:true,idempotency_key:'fictional-notes-complete'}}));
const chosen={json.dumps(first['chosen'])};const notes=payload(call('vera_workspace_variance_narrative_read',chosen));
const result={{completed,notes}};
""",
    )
    assert result["notes"]["can_write"] is False
    assert result["notes"]["documents"] == NOTES
    assert result["notes"]["conservation"]["review"] == READBACK
    assert len(result["notes"]["files"]) == 4


@pytest.mark.parametrize("action", ["stage", "commit"])
def test_native_variance_narrative_real_process_failure_preserves_intent_and_requires_recovery(
    review_run, action
):
    import os
    import subprocess
    import sys

    from tests.plugins.test_vera_native_workspace import workspace_module

    if action == "stage":
        body = (
            initial(review_run)
            + f"""
const exact={{...originalWork,source_ref:original.source_ref}};const page=payload(call('vera_workspace_variance_narrative_setup',exact));
const result={{...exact,revision:page.revision,documents:{json.dumps(NOTES)},idempotency_key:'fictional-stage-failure'}};
"""
        )
    else:
        body = (
            proposed(review_run)
            + f"""
payload(call('vera_workspace_variance_narrative_draft_save',{{...noteAuthority(page),fields:{json.dumps(READBACK)}}}));
const fresh=payload(call('vera_workspace_variance_narrative_read',chosen));
const result={{...noteAuthority(fresh),confirmed:true,idempotency_key:'fictional-commit-failure'}};
"""
        )
    args = rpc_program(review_run[0], body)
    module = workspace_module()
    program = f"""
import json, sys
sys.path.insert(0, {str(Path(module.__file__).parent)!r})
import native_workspace as workspace
ordinary=workspace.atomic_json
def interrupted(path,value):
    if path.name=='variance-narrative-state.json':
        raise RuntimeError('Fictional interruption after actual complete note files')
    return ordinary(path,value)
workspace.atomic_json=interrupted
workspace.dispatch('vera_workspace_variance_narrative_{action}',json.load(sys.stdin))
"""
    env = {**os.environ, **review_run[0]}
    env.pop("VERA_WORKSPACE_BINDINGS", None)
    child = subprocess.run(
        [sys.executable, "-B", "-c", program],
        input=json.dumps(args),
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert child.returncode != 0
    assert "after actual complete note files" in child.stderr
    private = review_run[1].parent / ".native-workspace"
    pending = [
        json.loads(p.read_bytes())
        for p in private.glob("variance-narrative-request-*.json")
    ]
    assert sum("result" not in value for value in pending) == 1
    preserved = (
        next(private.glob("variance-narrative-*/codex_business_analysis.md"))
        if action == "stage"
        else next(review_run[1].glob("codex-notes-*/codex_business_analysis.md"))
    )
    assert preserved.read_bytes() == NOTES["codex_business_analysis.md"].encode()
    selected = {k: review_run[2][k] for k in ("client_id", "engagement_id", "run_id")}
    # Direct child does not receive an MCP ticket; the mechanical service must still refuse an uncertain retry.
    retry = subprocess.run(
        [sys.executable, "-B", str(Path(module.__file__))],
        input=json.dumps(
            {"tool": f"vera_workspace_variance_narrative_{action}", "arguments": args}
        ),
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    result = rpc_program(
        review_run[0],
        f"const result={{setup:payload(call('vera_workspace_variance_setup',{{work_ref:{json.dumps(review_run[2]['work_ref'])}}})),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};",
    )
    assert retry.returncode != 0
    assert result["setup"]["status"] == "recovery_required"
    assert result["closure"]["isError"] is True
    assert preserved.read_bytes() == NOTES["codex_business_analysis.md"].encode()


@pytest.mark.parametrize("kind", ["proposal", "conserved"])
def test_native_variance_narrative_changed_note_refuses_read_and_closure(
    review_run, kind
):
    result = rpc_program(
        review_run[0],
        proposed(review_run)
        + (conserved() if kind == "conserved" else "")
        + "const result={chosen"
        + (",committed" if kind == "conserved" else "")
        + "};",
    )
    folder = (
        review_run[1] / result["committed"]["output_ref"]
        if kind == "conserved"
        else review_run[1].parent / ".native-workspace" / result["chosen"]["case_ref"]
    )
    changed = folder / "codex_business_analysis.md"
    changed.write_bytes(changed.read_bytes() + b"Changed note.\n")
    selected = {k: review_run[2][k] for k in ("client_id", "engagement_id", "run_id")}
    refusal = rpc_program(
        review_run[0],
        f"const result={{read:call('vera_workspace_variance_narrative_read',{json.dumps(result['chosen'])}),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};",
    )
    assert refusal["read"]["isError"] is True
    assert "changed" in refusal["read"]["content"][0]["text"]
    assert refusal["closure"]["isError"] is True
    assert changed.read_bytes().endswith(b"Changed note.\n")


def test_native_variance_viewer_reads_notes_but_cannot_stage_or_save(review_run):
    first = rpc_program(
        review_run[0], proposed(review_run) + "const result={chosen,stageArgs};"
    )
    env = {**review_run[0], "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        env,
        f"""
const chosen={json.dumps(first['chosen'])};const page=payload(call('vera_workspace_variance_narrative_read',chosen));
const result={{page,stage:call('vera_workspace_variance_narrative_stage',{json.dumps({**first['stageArgs'],'idempotency_key':'viewer-notes'})}),save:call('vera_workspace_variance_narrative_draft_save',{{...chosen,revision:page.revision,review_ticket:page.review_ticket,item_id:page.selection.id,expected_draft_revision:page.draft_revision,fields:{json.dumps(READBACK)}}})}};
""",
    )
    assert result["page"]["can_write"] is False
    assert result["page"]["documents"] == NOTES
    assert result["stage"]["isError"] is True
    assert result["save"]["isError"] is True
    assert list(review_run[1].glob("codex-notes-*")) == []


def test_native_variance_note_changed_idempotent_request_cannot_replace_proposal(
    review_run,
):
    result = rpc_program(
        review_run[0],
        proposed(review_run)
        + """
const changed=call('vera_workspace_variance_narrative_stage',{...stageArgs,documents:{...stageArgs.documents,'codex_business_analysis.md':'Changed literal note'}});
const result={changed,whole:payload(call('vera_workspace_variance_narrative_read',chosen)),setup:payload(call('vera_workspace_variance_narrative_setup',exact))};
""",
    )
    assert result["changed"]["isError"] is True
    assert result["whole"]["documents"] == NOTES
    assert len(result["setup"]["versions"]) == 1


def test_native_variance_two_whole_note_versions_keep_explicit_selection_and_readback_isolation(
    review_run,
):
    result = rpc_program(
        review_run[0],
        proposed(review_run)
        + conserved("rejected")
        + """
const another=call('vera_workspace_variance_narrative_stage',{...stageArgs,idempotency_key:'another-notes',documents:{...stageArgs.documents,'codex_business_analysis.md':'A second distinct whole fictional analysis.'}}).structuredContent;
const current=payload(call('vera_workspace_variance_narrative_read',{...exact,case_ref:another.case_ref}));
const previous=payload(call('vera_workspace_variance_narrative_read',chosen));
const result={another,current,previous,setup:payload(call('vera_workspace_variance_narrative_setup',exact))};
""",
    )
    assert (
        result["current"]["documents"]["codex_business_analysis.md"]
        == "A second distinct whole fictional analysis."
    )
    assert result["current"]["draft"] == dict.fromkeys(READBACK, "")
    assert result["previous"]["documents"] == NOTES
    assert result["previous"]["status"] == "rejected"
    assert result["current"]["status"] == "pending"
    assert len(result["setup"]["versions"]) == 2
