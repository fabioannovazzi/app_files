"""Real CNC snapshots and signed native calls on fictional managed evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_composizione_negoziata import (  # noqa: F401
    case,
    cnc,
    initial,
    ledger,
)
from tests.plugins.test_vera_native_archive_closure import declare_all, setup
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import archive_cli
from tests.plugins.test_vera_native_workspace import configure, workspace_module

__all__ = []

REVIEW = {
    "decision": "accepted",
    "reviewer_ref": "Fictional reviewer",
    "confirmation_ref": "Fictional UI test confirmation only",
    "reason": "Full fictional node inspected; no real professional acceptance.",
    "reviewed_at": "2026-10-08T07:00:00+02:00",
}


@pytest.fixture
def cnc_run(case, tmp_path, monkeypatch):
    binding = {
        "work_ref": "fictional-cnc",
        "client_root": str(case.root),
        "client_id": case.client_id,
        "engagement_id": case.engagement_id,
        "run_id": case.run["run"]["run_id"],
        "workflow_id": "composizione-negoziata",
    }
    configure(monkeypatch, tmp_path, [binding])
    proposal = {
        k: v
        for k, v in initial(case).items()
        if k not in {"expected_revision", "idempotency_key"}
    }
    return case, binding, proposal


@pytest.fixture
def registered_cnc_run(cnc_run, tmp_path, monkeypatch):
    """Discover the actual managed run from the maintained archive configuration."""
    case, binding, proposal = cnc_run
    env = {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "fictional-cnc-native",
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(
            tmp_path.parent / ("cnc-state-" + tmp_path.name)
        ),
    }
    env.pop("VERA_WORKSPACE_BINDINGS")
    archive_cli(env, "configure", "--archive-root", str(case.root.parent))
    monkeypatch.delenv("VERA_WORKSPACE_BINDINGS")
    for name in ("VERA_STUDIO_ARCHIVE_SESSION_ID", "VERA_STUDIO_ARCHIVE_STATE_DIR"):
        monkeypatch.setenv(name, env[name])
    return (
        case,
        {
            **binding,
            "work_ref": "studio-"
            + "_".join(
                binding[k].split("_", 1)[1]
                for k in ("client_id", "engagement_id", "run_id")
            ),
        },
        proposal,
    )


def granted(fixture):
    fields = {
        "question": "Prepare complete fictional CNC findings and contrary evidence.",
        "role": "advisor",
        "input_ids": [fixture[0].receipt["input_id"]],
    }
    return f"""
const work={{work_ref:{json.dumps(fixture[1]['work_ref'])}}};
const first=payload(call('vera_workspace_cnc_author_setup',work));
const fields={json.dumps(fields)};
payload(call('vera_workspace_cnc_author_draft_save',{{...work,revision:first.revision,review_ticket:first.review_ticket,expected_draft_revision:first.draft_revision,fields}}));
const fresh=payload(call('vera_workspace_cnc_author_setup',work));
const request={{...work,revision:fresh.revision,review_ticket:fresh.review_ticket,expected_draft_revision:fresh.draft_revision,fields,confirmed:true,idempotency_key:'fictional-cnc-mandate'}};
const issued=payload(call('vera_workspace_cnc_author_request',request));
const identity={{...work,grant_ref:issued.grant_ref}};
const opened=payload(call('vera_workspace_cnc_author_read',identity));
"""


def staged(fixture):
    return (
        granted(fixture)
        + f"""
const stageArgs={{...identity,revision:opened.revision,proposal:{json.dumps(fixture[2])},idempotency_key:'fictional-cnc-stage'}};
const stageCall=call('vera_workspace_cnc_stage',stageArgs);
if(stageCall.isError)throw new Error(stageCall.content[0].text);
const chosen={{...identity,case_ref:stageCall.structuredContent.case_ref}};
const page=payload(call('vera_workspace_cnc_author_read',chosen));
const authority=p=>({{...chosen,revision:p.revision,review_ticket:p.review_ticket,source_ref:p.source_ref,item_id:p.selection.id}});
"""
    )


def conserved(fixture):
    return (
        staged(fixture)
        + """
const publishArgs={...authority(page),confirmed:true,idempotency_key:'fictional-cnc-publish'};
const published=payload(call('vera_workspace_cnc_publish',publishArgs));
const current=payload(call('vera_workspace_cnc_setup',work));
const nodeIdentity={...work,source_ref:current.source_ref,item_id:'proposal'};
const node=payload(call('vera_workspace_cnc_read',nodeIdentity));
const reviewAuthority=p=>({...nodeIdentity,revision:p.revision,review_ticket:p.review_ticket,expected_draft_revision:p.draft_revision});
"""
    )


def test_cnc_conserves_complete_public_snapshot_memo_and_exact_retry(cnc_run):
    result = rpc_program(
        os.environ.copy(),
        conserved(cnc_run)
        + "const result={published,current,node,retry:payload(call('vera_workspace_cnc_publish',publishArgs))};",
    )
    assert result["published"] == result["retry"]
    assert result["current"]["role"] == "advisor"
    assert result["current"]["total"] == 6
    assert result["published"]["professional_approval"] is False
    assert result["published"]["run_completed"] is False
    assert len(result["published"]["files"]) == 4
    snapshot = next(
        p
        for p in result["published"]["files"]
        if p["name"].startswith("workflow-revision")
    )
    saved = json.loads(Path(snapshot["path"]).read_bytes())
    assert (
        saved["payload"]["nodes"]["proposal"]["content"]
        == cnc_run[2]["upsert_nodes"][4]["content"]
    )
    assert (
        result["node"]["node"]["version"]
        == saved["payload"]["nodes"]["proposal"]["version"]
    )
    assert saved["payload"]["reviews"] == []


@pytest.mark.parametrize("decision", ["accepted", "rejected", "changes_requested"])
def test_cnc_exact_local_review_keeps_declared_fields_without_authenticated_approval(
    cnc_run, decision
):
    value = {**REVIEW, "decision": decision}
    result = rpc_program(
        os.environ.copy(),
        conserved(cnc_run)
        + f"""
const reviewFields={json.dumps(value)};
payload(call('vera_workspace_cnc_review_draft_save',{{...reviewAuthority(node),fields:reviewFields}}));
const ready=payload(call('vera_workspace_cnc_read',nodeIdentity));
const args={{...reviewAuthority(ready),fields:reviewFields,confirmed:true,idempotency_key:'fictional-cnc-local-review'}};
const committed=payload(call('vera_workspace_cnc_review_commit',args));
const after=payload(call('vera_workspace_cnc_setup',work));
const reviewed=payload(call('vera_workspace_cnc_read',{{...nodeIdentity,source_ref:after.source_ref}}));
const result={{committed,reviewed,retry:payload(call('vera_workspace_cnc_review_commit',args))}};
""",
    )
    assert result["committed"] == result["retry"]
    review = result["reviewed"]["reviews"][-1]
    assert review["decision"] == decision
    assert review["authority"] == "record_only_identity_not_verified"
    assert review["reviewer_ref"] == REVIEW["reviewer_ref"]
    receipt = next(
        p
        for p in result["committed"]["files"]
        if p["name"].startswith("cnc-native-receipt")
    )
    assert json.loads(Path(receipt["path"]).read_bytes())["declared_fields"] == value
    assert result["reviewed"]["professional_approval"] is False


def test_cnc_private_unsent_named_draft_stays_out_of_model_context(cnc_run):
    private = {
        **REVIEW,
        "reviewer_ref": "PRIVATE UNSENT NAME",
        "reason": "PRIVATE UNSENT REASON",
    }
    result = rpc_program(
        os.environ.copy(),
        conserved(cnc_run)
        + f"""
payload(call('vera_workspace_cnc_review_draft_save',{{...reviewAuthority(node),fields:{json.dumps(private)}}}));
const result=call('vera_workspace_cnc_context',{{...nodeIdentity,revision:node.revision}});
""",
    )
    assert "PRIVATE UNSENT" not in json.dumps(result)
    assert "_meta" not in result
    assert result["structuredContent"]["node"]["id"] == "proposal"
    assert result["structuredContent"]["actual_model_reads_verified"] is False


def test_cnc_requires_fresh_confirmed_generation_for_source_mandate(cnc_run):
    result = rpc_program(
        os.environ.copy(),
        granted(cnc_run).split("const issued=", 1)[0]
        + "const result={unconfirmed:call('vera_workspace_cnc_author_request',{...request,confirmed:false}),stale:call('vera_workspace_cnc_author_draft_save',{...work,revision:first.revision,review_ticket:first.review_ticket,expected_draft_revision:first.draft_revision,fields})};",
    )
    assert result["unconfirmed"]["isError"] is True
    assert result["stale"]["isError"] is True


def test_cnc_empty_original_grant_excludes_model_citations_before_staging(cnc_run):
    body = granted(cnc_run).replace(
        "const fields="
        + json.dumps(
            {
                "question": "Prepare complete fictional CNC findings and contrary evidence.",
                "role": "advisor",
                "input_ids": [cnc_run[0].receipt["input_id"]],
            }
        ),
        "const fields="
        + json.dumps(
            {
                "question": "Prepare complete fictional CNC findings and contrary evidence.",
                "role": "advisor",
                "input_ids": [],
            }
        ),
    )
    result = rpc_program(
        os.environ.copy(),
        body
        + f"const result=call('vera_workspace_cnc_stage',{{...identity,revision:opened.revision,proposal:{json.dumps(cnc_run[2])},idempotency_key:'ungranted-citation'}});",
    )
    assert result["isError"] is True
    output = Path(cnc_run[0].run["output_dir"])
    assert list(output.glob("workflow-revision-*.json")) == []


def test_cnc_model_cannot_manufacture_review_attribution(cnc_run):
    proposal = {
        **cnc_run[2],
        "reviews": [{"decision": "accepted", "reviewer_ref": "invented"}],
    }
    result = rpc_program(
        os.environ.copy(),
        granted(cnc_run)
        + f"const result=call('vera_workspace_cnc_stage',{{...identity,revision:opened.revision,proposal:{json.dumps(proposal)},idempotency_key:'fabricated-review'}});",
    )
    assert result["isError"] is True
    assert "empty model review" in result["content"][0]["text"]


def test_cnc_cancel_preserves_proposal_and_refuses_further_original_context(cnc_run):
    result = rpc_program(
        os.environ.copy(),
        staged(cnc_run)
        + """
payload(call('vera_workspace_cnc_cancel',{...authority(page),confirmed:true,idempotency_key:'fictional-cnc-cancel'}));
const retained=payload(call('vera_workspace_cnc_author_read',chosen));
const result={retained,context:call('vera_workspace_cnc_author_context',{...chosen,revision:retained.revision})};
""",
    )
    assert result["retained"]["status"] == "cancelled"
    assert result["retained"]["proposal"]["upsert_nodes"] == cnc_run[2]["upsert_nodes"]
    assert result["context"]["isError"] is True


def test_cnc_viewer_cannot_save_or_publish_full_proposal(cnc_run):
    staged_case = rpc_program(
        os.environ.copy(), staged(cnc_run) + "const result=chosen;"
    )
    result = rpc_program(
        {**os.environ, "VERA_WORKSPACE_ROLES": "VIEWER"},
        f"""
const chosen={json.dumps(staged_case)};
const page=payload(call('vera_workspace_cnc_author_read',chosen));
const result={{page,write:call('vera_workspace_cnc_publish',{{...chosen,revision:page.revision,review_ticket:page.review_ticket,source_ref:page.source_ref,item_id:page.selection.id,confirmed:true,idempotency_key:'viewer-publish'}})}};
""",
    )
    assert result["page"]["can_write"] is False
    assert result["write"]["isError"] is True


def test_cnc_registered_archive_discovery_conserves_and_reopens_completed_run_readonly(
    registered_cnc_run,
):
    case, binding, _ = registered_cnc_run
    first = rpc_program(
        os.environ.copy(),
        conserved(registered_cnc_run) + "const result={published,current,node};",
    )
    output = Path(case.run["output_dir"])
    write_no_model_report(output, "composizione-negoziata", binding["run_id"])
    selected = {k: binding[k] for k in ("client_id", "engagement_id", "run_id")}
    closure = rpc_program(
        os.environ.copy(),
        setup(selected)
        + declare_all()
        + """
const finalized=payload(call('vera_workspace_archive_finalize',seal));
const ready=read();
const completed=payload(call('vera_workspace_archive_complete',{...authority(ready),human_reviewed:true,idempotency_key:'fictional-cnc-complete'}));
const result={finalized,completed};
""",
    )
    reopened = rpc_program(
        os.environ.copy(),
        f"""
const work={{work_ref:{json.dumps(binding['work_ref'])}}};
const current=payload(call('vera_workspace_cnc_setup',work));
const node=payload(call('vera_workspace_cnc_read',{{...work,source_ref:current.source_ref,item_id:'proposal'}}));
const result={{current,node}};
""",
    )
    assert closure["completed"]["status"] == "completed"
    assert reopened["current"]["can_write"] is False
    assert reopened["node"]["node"] == first["node"]["node"]
    assert ledger.validate_run_artifacts(
        case.root, case.engagement_id, binding["run_id"]
    )["artifacts"]


@pytest.mark.parametrize("member", ["request.json", "preview.json"])
def test_cnc_altered_complete_proposal_blocks_read_and_publish(cnc_run, member):
    chosen = rpc_program(os.environ.copy(), staged(cnc_run) + "const result=chosen;")
    folder = (
        Path(cnc_run[0].run["output_dir"]).parent
        / ".native-workspace"
        / chosen["case_ref"]
    )
    target = folder / member
    target.write_bytes(target.read_bytes() + b" ")
    result = rpc_program(
        os.environ.copy(),
        f"const result=call('vera_workspace_cnc_author_read',{json.dumps(chosen)});",
    )
    assert result["isError"] is True
    assert "proposal changed" in result["content"][0]["text"]
    assert (
        list(Path(cnc_run[0].run["output_dir"]).glob("workflow-revision-*.json")) == []
    )


@pytest.mark.parametrize("kind", ["snapshot", "memo", "receipt", "request"])
def test_cnc_altered_conserved_bytes_refuse_reopening(cnc_run, kind):
    published = rpc_program(
        os.environ.copy(), conserved(cnc_run) + "const result=published;"
    )
    prefixes = {
        "snapshot": "workflow-revision",
        "memo": "cnc-revision",
        "receipt": "cnc-native-receipt",
        "request": "cnc-native-request",
    }
    target = Path(
        next(
            row["path"]
            for row in published["files"]
            if row["name"].startswith(prefixes[kind])
        )
    )
    target.write_bytes(target.read_bytes() + b" altered")
    result = rpc_program(
        os.environ.copy(),
        f"const result=call('vera_workspace_cnc_setup',{{work_ref:{json.dumps(cnc_run[1]['work_ref'])}}});",
    )
    assert result["isError"] is True


def test_cnc_fixed_role_rejects_cross_role_proposal_and_new_intake(cnc_run):
    rpc_program(os.environ.copy(), conserved(cnc_run) + "const result=published;")
    result = rpc_program(
        os.environ.copy(),
        f"""
const work={{work_ref:{json.dumps(cnc_run[1]['work_ref'])}}};
const page=payload(call('vera_workspace_cnc_author_setup',work));
const result={{page,changed:call('vera_workspace_cnc_author_draft_save',{{...work,revision:page.revision,review_ticket:page.review_ticket,expected_draft_revision:page.draft_revision,fields:{{...page.fields,role:'esperto'}}}})}};
""",
    )
    assert result["page"]["fixed_role"] == "advisor"
    assert result["changed"]["isError"] is True
    assert "separate engagement" in result["changed"]["content"][0]["text"]


def test_cnc_real_source_revision_marks_transitive_node_stale_and_refuses_local_decision(
    cnc_run,
):
    rpc_program(os.environ.copy(), conserved(cnc_run) + "const result=published;")
    update = initial(cnc_run[0])
    update.update(expected_revision=1, idempotency_key="fictional-source-update")
    update["upsert_nodes"] = [update["upsert_nodes"][0]]
    update["upsert_nodes"][0][
        "content"
    ] = "Fictional payment delayed; original dependency requires reanalysis."
    record = cnc.apply_request(cnc_run[0].context, update)
    (Path(cnc_run[0].run["output_dir"]) / "cnc-revision-000002.md").write_text(
        cnc.render_record(record)
    )
    result = rpc_program(
        os.environ.copy(),
        f"""
const work={{work_ref:{json.dumps(cnc_run[1]['work_ref'])}}};
const current=payload(call('vera_workspace_cnc_setup',work));
const identity={{...work,source_ref:current.source_ref,item_id:'proposal'}};
const node=payload(call('vera_workspace_cnc_read',identity));
const result={{current,node,save:call('vera_workspace_cnc_review_draft_save',{{...identity,revision:node.revision,review_ticket:node.review_ticket,expected_draft_revision:node.draft_revision,fields:{json.dumps(REVIEW)}}})}};
""",
    )
    assert result["node"]["stale"] is True
    assert result["node"]["can_write"] is False
    assert result["save"]["isError"] is True
    assert (
        record["payload"]["nodes"]["proposal"]["content"]
        == cnc_run[2]["upsert_nodes"][4]["content"]
    )


@pytest.mark.parametrize("action", ["author_request", "stage", "publish"])
def test_cnc_real_interrupted_write_preserves_files_and_blocks_retry_and_archive_closure(
    registered_cnc_run, action
):
    fixture = registered_cnc_run
    if action == "author_request":
        body = granted(fixture).split("const issued=", 1)[0] + "const result=request;"
    elif action == "stage":
        body = (
            granted(fixture)
            + f"const result={{...identity,revision:opened.revision,proposal:{json.dumps(fixture[2])},idempotency_key:'fictional-interrupted-stage'}};"
        )
    else:
        body = (
            staged(fixture)
            + "const result={...authority(page),confirmed:true,idempotency_key:'fictional-interrupted-publish'};"
        )
    args = rpc_program(os.environ.copy(), body)
    module = workspace_module()
    program = f"""
import json, sys
sys.path.insert(0, {str(Path(module.__file__).parent)!r})
import native_workspace as workspace
ordinary=workspace.atomic_json
def interrupted(path,value):
    if path.name=='cnc-state.json':
        raise RuntimeError('Fictional interruption after actual CNC files')
    return ordinary(path,value)
workspace.atomic_json=interrupted
workspace.dispatch('vera_workspace_cnc_{action}',json.load(sys.stdin))
"""
    child = subprocess.run(
        [sys.executable, "-B", "-c", program],
        input=json.dumps(args),
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    assert child.returncode != 0
    assert "after actual CNC files" in child.stderr
    output = Path(fixture[0].run["output_dir"])
    private = output.parent / ".native-workspace"
    before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in (output, private)
        for p in folder.rglob("*")
        if p.is_file()
    }
    selected = {k: fixture[1][k] for k in ("client_id", "engagement_id", "run_id")}
    result = rpc_program(
        os.environ.copy(),
        f"""
const result={{page:payload(call('vera_workspace_cnc_setup',{{work_ref:{json.dumps(fixture[1]['work_ref'])}}})),retry:call('vera_workspace_cnc_{action}',{json.dumps(args)}),closure:call('vera_workspace_archive_closure',{json.dumps(selected)})}};
""",
    )
    assert result["page"]["recovery_required"] is True
    assert result["page"]["can_write"] is False
    assert result["retry"]["isError"] is True
    assert result["closure"]["isError"] is True
    assert {
        name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in before
    } == before
    if action == "publish":
        assert len(list(output.glob("workflow-revision-*.json"))) == 1
        assert len(list(output.glob("cnc-revision-*.md"))) == 1


def test_cnc_expert_role_remains_explicit_and_preserves_complete_ordinary_case(cnc_run):
    proposal = json.loads(json.dumps(cnc_run[2]))
    proposal["role"] = "esperto"
    for node in proposal["upsert_nodes"]:
        node["responsibility"] = "esperto"
    fixture = cnc_run[0], cnc_run[1], proposal
    body = conserved(fixture).replace('"role": "advisor"', '"role": "esperto"')
    result = rpc_program(os.environ.copy(), body + "const result={current,node};")
    assert result["current"]["role"] == "esperto"
    assert result["node"]["node"]["responsibility"] == "esperto"
    assert result["current"]["total"] == 6


def test_cnc_older_open_mandate_can_be_cancelled_after_another_case_revision_without_new_reads(
    registered_cnc_run,
):
    fixture = registered_cnc_run
    result = rpc_program(
        os.environ.copy(),
        staged(fixture)
        + f"""
const older=chosen;
const intake=payload(call('vera_workspace_cnc_author_setup',work));
const newer=payload(call('vera_workspace_cnc_author_request',{{...work,revision:intake.revision,review_ticket:intake.review_ticket,expected_draft_revision:intake.draft_revision,fields:intake.fields,confirmed:true,idempotency_key:'fictional-newer-mandate'}}));
const newerIdentity={{...work,grant_ref:newer.grant_ref}};
const newerPage=payload(call('vera_workspace_cnc_author_read',newerIdentity));
const newerStage=call('vera_workspace_cnc_stage',{{...newerIdentity,revision:newerPage.revision,proposal:{json.dumps(fixture[2])},idempotency_key:'fictional-newer-stage'}});
if(newerStage.isError)throw new Error(newerStage.content[0].text);
const newerChosen={{...newerIdentity,case_ref:newerStage.structuredContent.case_ref}};
const toPublish=payload(call('vera_workspace_cnc_author_read',newerChosen));
payload(call('vera_workspace_cnc_publish',{{...newerChosen,revision:toPublish.revision,review_ticket:toPublish.review_ticket,source_ref:toPublish.source_ref,item_id:toPublish.selection.id,confirmed:true,idempotency_key:'fictional-newer-publish'}}));
const oldRead=call('vera_workspace_cnc_author_read',older);
const old=oldRead.isError?null:payload(oldRead);
const context=call('vera_workspace_cnc_author_context',{{...older,revision:old?old.revision:'missing'}});
const publish=old?call('vera_workspace_cnc_publish',{{...older,revision:old.revision,review_ticket:old.review_ticket,source_ref:old.source_ref,item_id:old.selection.id,confirmed:true,idempotency_key:'fictional-obsolete-publish'}}):oldRead;
const cancel=old?call('vera_workspace_cnc_cancel',{{...older,revision:old.revision,review_ticket:old.review_ticket,source_ref:old.source_ref,item_id:old.selection.id,confirmed:true,idempotency_key:'fictional-obsolete-cancel'}}):oldRead;
const after=payload(call('vera_workspace_cnc_setup',work));
const result={{oldRead,old,context,publish,cancel,after}};
""",
    )
    assert result["oldRead"].get("isError") is not True, result["oldRead"]
    assert result["old"]["case_changed"] is True
    assert result["context"]["isError"] is True
    assert result["publish"]["isError"] is True
    assert result["cancel"].get("isError") is not True
    assert {row["status"] for row in result["after"]["grants"]} == {
        "cancelled",
        "published",
    }
    assert result["after"]["case_revision"] == 1
    output = Path(fixture[0].run["output_dir"])
    private = output.parent / ".native-workspace"
    assert len(list(private.glob("cnc-proposal-*"))) == 2
    assert len(list(output.glob("workflow-revision-*.json"))) == 1


def test_cnc_two_actual_writers_preserve_one_literal_draft_and_reject_lost_update(
    cnc_run, tmp_path
):
    from concurrent.futures import ThreadPoolExecutor

    case, binding, _ = cnc_run
    page = rpc_program(
        os.environ.copy(),
        f"const result=payload(call('vera_workspace_cnc_author_setup',{{work_ref:{json.dumps(binding['work_ref'])}}}));",
    )
    common = {
        "work_ref": binding["work_ref"],
        "revision": page["revision"],
        "review_ticket": page["review_ticket"],
        "expected_draft_revision": page["draft_revision"],
    }
    script_dir = str(Path(workspace_module().__file__).parent)
    program = f"""
import json, sys, time
from pathlib import Path
from contextlib import contextmanager
sys.path.insert(0,{script_dir!r})
import native_workspace as workspace
original=workspace.write_lock
barrier=Path(sys.argv[1]);label=sys.argv[2]
@contextmanager
def synchronized(output):
    (barrier/label).write_text('snapshot read before real lock')
    deadline=time.monotonic()+30
    while len(list(barrier.iterdir()))<2:
        if time.monotonic()>deadline:raise TimeoutError('other real writer did not arrive')
        time.sleep(0.01)
    with original(output):yield
workspace.write_lock=synchronized
workspace.dispatch('vera_workspace_cnc_author_draft_save',json.load(sys.stdin))
"""
    barrier = tmp_path / "real-writer-barrier"
    barrier.mkdir()
    requests = [
        {
            **common,
            "fields": {
                "question": "Fictional writer " + label,
                "role": "advisor",
                "input_ids": [case.receipt["input_id"]],
            },
        }
        for label in ("A", "B")
    ]

    def run_writer(index):
        return subprocess.run(
            [sys.executable, "-B", "-c", program, str(barrier), str(index)],
            input=json.dumps(requests[index]),
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            check=False,
            timeout=90,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(run_writer, (0, 1)))
    assert sorted([first.returncode, second.returncode]) == [0, 1]
    final = rpc_program(
        os.environ.copy(),
        f"const result=payload(call('vera_workspace_cnc_author_setup',{{work_ref:{json.dumps(binding['work_ref'])}}}));",
    )
    expected = requests[0 if first.returncode == 0 else 1]["fields"]
    assert final["fields"] == expected
    assert final["draft_revision"] != page["draft_revision"]
    assert list(Path(case.run["output_dir"]).glob("workflow-revision-*.json")) == []
