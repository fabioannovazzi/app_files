"""Complete immutable CNC history through actual owned Archive/MCP calls."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_cnc import (  # noqa: F401
    REVIEW,
    case,
    cnc,
    cnc_run,
    initial,
    ledger,
    registered_cnc_run,
)
from tests.plugins.test_vera_native_workspace import configure

__all__ = []


def append(case, update):
    """Use the public producer and exact ordinary memo renderer unchanged."""
    record = cnc.apply_request(case.context, update)
    output = Path(case.run["output_dir"])
    (output / f"cnc-revision-{record['revision']:06d}.md").write_text(
        cnc.render_record(record)
    )
    return record


@pytest.fixture
def history_run(registered_cnc_run):
    case, binding, proposal = registered_cnc_run
    first = append(case, initial(case))
    update = initial(case)
    update.update(expected_revision=1, idempotency_key="fictional-history-second")
    update["upsert_nodes"] = [update["upsert_nodes"][0]]
    update["upsert_nodes"][0][
        "content"
    ] = "Fictional second revision: payment confirmation still absent."
    second = append(case, update)
    return case, binding, proposal, first, second


def history_program(fixture):
    return f"""
const work={{work_ref:{json.dumps(fixture[1]['work_ref'])}}};
const setupCall=call('vera_workspace_cnc_history_setup',work);
const setup=payload(setupCall);
const identity={{...work,source_ref:{json.dumps(fixture[3]['content_sha256'])}}};
const readCall=call('vera_workspace_cnc_history_read',identity);
const page=payload(readCall);
const exact={{...identity,revision:page.revision}};
"""


def test_cnc_history_private_complete_outputs_equal_ordinary_bytes_and_context_is_explicit(
    history_run,
):
    case, _, _, first, _ = history_run
    output = Path(case.run["output_dir"])
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    result = rpc_program(
        os.environ.copy(),
        history_program(history_run)
        + """
const outputsCall=call('vera_workspace_cnc_history_outputs',exact);
const model=call('vera_workspace_cnc_history_context',exact);
const result={setupCall,readCall,outputsCall,model,setup,page,outputs:payload(outputsCall)};
""",
    )
    assert result["page"]["record"] == first["payload"]
    assert result["page"]["is_latest"] is False
    assert result["page"]["can_write"] is False
    assert result["setup"]["total"] == 2
    assert [row["case_revision"] for row in result["setup"]["rows"]] == [2, 1]
    assert "record" not in result["readCall"]["structuredContent"]
    assert "rows" not in result["setupCall"]["structuredContent"]
    assert "files" not in result["outputsCall"]["structuredContent"]
    assert "_meta" not in result["model"]
    assert result["model"]["structuredContent"]["record"] == first["payload"]
    assert str(case.root) not in json.dumps(result["model"])
    for file in result["outputs"]["files"]:
        assert file["available"] is True
        raw = Path(file["path"]).read_bytes()
        assert file["content"].encode() == raw
        assert file["sha256"] == hashlib.sha256(raw).hexdigest()
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    assert not (output.parent / ".native-workspace").exists()


def test_cnc_history_excludes_unsent_local_review_draft(history_run):
    private = {
        **REVIEW,
        "reviewer_ref": "PRIVATE HISTORY UNSENT NAME",
        "reason": "PRIVATE HISTORY UNSENT REASON",
    }
    result = rpc_program(
        os.environ.copy(),
        history_program(history_run)
        + f"""
const current=payload(call('vera_workspace_cnc_setup',work));
const nodeId={{...work,source_ref:current.source_ref,item_id:'document'}};
const node=payload(call('vera_workspace_cnc_read',nodeId));
payload(call('vera_workspace_cnc_review_draft_save',{{...nodeId,revision:node.revision,review_ticket:node.review_ticket,expected_draft_revision:node.draft_revision,fields:{json.dumps(private)}}}));
const result=call('vera_workspace_cnc_history_context',exact);
""",
    )
    assert "PRIVATE HISTORY UNSENT" not in json.dumps(result)
    assert result["structuredContent"]["record"] == history_run[3]["payload"]
    assert result["structuredContent"]["actual_model_reads_verified"] is False


def test_cnc_history_latest_view_is_readonly_even_for_reviewer(history_run):
    result = rpc_program(
        os.environ.copy(),
        history_program(history_run)
        + f"""
const latest=payload(call('vera_workspace_cnc_history_read',{{...work,source_ref:{json.dumps(history_run[4]['content_sha256'])}}}));
const result={{latest,misuse:call('vera_workspace_cnc_review_draft_save',{{...work,source_ref:latest.source_ref,item_id:'document',revision:latest.revision,review_ticket:latest.review_ticket,expected_draft_revision:'not-a-current-node-draft',fields:{json.dumps(REVIEW)}}})}};
""",
    )
    assert result["latest"]["is_latest"] is True
    assert result["latest"]["can_write"] is False
    assert result["misuse"]["isError"] is True


def test_cnc_history_context_and_outputs_refuse_new_case_revision_until_reread(
    history_run,
):
    read = rpc_program(
        os.environ.copy(), history_program(history_run) + "const result=exact;"
    )
    update = initial(history_run[0])
    update.update(
        expected_revision=2, idempotency_key="fictional-history-third", upsert_nodes=[]
    )
    append(history_run[0], update)
    result = rpc_program(
        os.environ.copy(),
        f"const result={{model:call('vera_workspace_cnc_history_context',{json.dumps(read)}),files:call('vera_workspace_cnc_history_outputs',{json.dumps(read)})}};",
    )
    assert result["model"]["isError"] is True
    assert result["files"]["isError"] is True


@pytest.mark.parametrize("member", ["snapshot", "memo"])
def test_cnc_history_altered_old_output_refuses_complete_history_read(
    history_run, member
):
    output = Path(history_run[0].run["output_dir"])
    name = (
        "workflow-revision-000001.json"
        if member == "snapshot"
        else "cnc-revision-000001.md"
    )
    path = output / name
    path.write_bytes(path.read_bytes() + b" changed old output")
    result = rpc_program(
        os.environ.copy(),
        f"const result=call('vera_workspace_cnc_history_setup',{{work_ref:{json.dumps(history_run[1]['work_ref'])}}});",
    )
    assert result["isError"] is True


def test_cnc_history_missing_old_memo_keeps_snapshot_readable_without_regeneration(
    history_run,
):
    path = Path(history_run[0].run["output_dir"]) / "cnc-revision-000001.md"
    path.unlink()
    result = rpc_program(
        os.environ.copy(),
        history_program(history_run)
        + "const result=payload(call('vera_workspace_cnc_history_outputs',exact));",
    )
    assert result["recovery_required"] is True
    assert result["files"][0]["available"] is True
    assert result["files"][1]["available"] is False
    assert result["files"][1]["content"] is None
    assert not path.exists()


def test_cnc_history_pagination_covers_all_versions_newest_first(registered_cnc_run):
    case, binding, _ = registered_cnc_run
    first = append(case, initial(case))
    for revision in range(1, 32):
        update = initial(case)
        update.update(
            expected_revision=revision,
            idempotency_key=f"fictional-history-{revision}",
            upsert_nodes=[],
        )
        append(case, update)
    result = rpc_program(
        os.environ.copy(),
        f"""
const work={{work_ref:{json.dumps(binding['work_ref'])}}};
const result={{first:payload(call('vera_workspace_cnc_history_setup',work)),last:payload(call('vera_workspace_cnc_history_setup',{{...work,offset:30}}))}};
""",
    )
    assert result["first"]["total"] == 32
    assert len(result["first"]["rows"]) == 30
    assert result["first"]["rows"][0]["case_revision"] == 32
    assert [row["case_revision"] for row in result["last"]["rows"]] == [2, 1]
    assert result["last"]["rows"][-1]["source_ref"] == first["content_sha256"]
    assert result["last"]["has_more"] is False


def test_cnc_history_complete_large_case_remains_private_and_model_refuses_truncation(
    registered_cnc_run,
):
    case, binding, _ = registered_cnc_run
    update = initial(case)
    update["upsert_nodes"][0]["content"] = "Fictional complete evidence " + "a" * 70_000
    record = append(case, update)
    result = rpc_program(
        os.environ.copy(),
        f"""
const identity={{work_ref:{json.dumps(binding['work_ref'])},source_ref:{json.dumps(record['content_sha256'])}}};
const page=payload(call('vera_workspace_cnc_history_read',identity));
const result={{page,model:call('vera_workspace_cnc_history_context',{{...identity,revision:page.revision}})}};
""",
    )
    assert result["page"]["record"] == record["payload"]
    assert result["model"]["isError"] is True
    assert "native limit" in result["model"]["content"][0]["text"]


def test_cnc_history_other_engagement_cannot_open_foreign_version(
    cnc_run, tmp_path, monkeypatch
):
    case, binding, _ = cnc_run
    first = append(case, initial(case))
    other = ledger.create_engagement(
        case.root, case.client_id, "Other fictional CNC engagement"
    )["engagement_id"]
    receipt = ledger.import_document(
        case.root, case.client_id, other, case.root.parent / "incassi.txt", "source"
    )["receipt"]
    prepared = ledger.prepare_run(
        case.root,
        case.client_id,
        other,
        "composizione-negoziata",
        "development",
        input_ids=[receipt["input_id"]],
    )
    started = ledger.start_run(case.root, other, prepared["run"]["run_id"])
    foreign = {
        **binding,
        "work_ref": "foreign-fictional-cnc",
        "engagement_id": other,
        "run_id": started["run"]["run_id"],
    }
    configure(monkeypatch, tmp_path, [binding, foreign])
    result = rpc_program(
        os.environ.copy(),
        f"const result=call('vera_workspace_cnc_history_read',{{work_ref:'foreign-fictional-cnc',source_ref:{json.dumps(first['content_sha256'])}}});",
    )
    assert result["isError"] is True
    assert "owned engagement" in result["content"][0]["text"]


def test_cnc_history_closed_run_keeps_old_outputs_and_browses_same_engagement_successor(
    history_run,
):
    from types import SimpleNamespace

    case, binding, proposal, first, second = history_run
    output = Path(case.run["output_dir"])
    write_no_model_report(output, "composizione-negoziata", binding["run_id"])
    declarations = [
        {
            "artifact_id": path.name.replace(".", "-"),
            "path": path.name,
            "purpose": "Inspect complete fictional CNC history output.",
            "audience": "review",
            "media_type": (
                "application/json" if path.suffix == ".json" else "text/markdown"
            ),
        }
        for path in output.iterdir()
        if path.is_file()
    ]
    ledger.finalize_run(case.root, case.engagement_id, binding["run_id"], declarations)
    ledger.complete_run(case.root, case.engagement_id, binding["run_id"])
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    prepared = ledger.prepare_run(
        case.root,
        case.client_id,
        case.engagement_id,
        "composizione-negoziata",
        "development",
        input_ids=[case.receipt["input_id"]],
    )
    started = ledger.start_run(case.root, case.engagement_id, prepared["run"]["run_id"])
    successor = SimpleNamespace(
        **{**vars(case), "run": started, "context": Path(started["context_path"])}
    )
    update = initial(successor)
    update.update(
        expected_revision=2,
        idempotency_key="fictional-successor-history",
        upsert_nodes=[],
    )
    third = append(successor, update)
    result = rpc_program(
        {**os.environ, "VERA_WORKSPACE_ROLES": "VIEWER"},
        history_program(history_run)
        + "const result={setup,page,outputs:payload(call('vera_workspace_cnc_history_outputs',exact))};",
    )
    assert result["setup"]["total"] == 3
    assert result["setup"]["rows"][0]["run_id"] == started["run"]["run_id"]
    assert result["setup"]["rows"][0]["source_ref"] == third["content_sha256"]
    assert result["page"]["run_id"] == binding["run_id"]
    assert result["page"]["can_write"] is False
    assert result["page"]["record"] == first["payload"]
    assert result["outputs"]["files"][0]["path"] == str(
        output / "workflow-revision-000001.json"
    )
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    assert ledger.validate_run_artifacts(
        case.root, case.engagement_id, binding["run_id"]
    )["artifacts"]
