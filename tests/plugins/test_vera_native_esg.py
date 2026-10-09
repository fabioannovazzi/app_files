"""Owned ESG native protocol proofs; no installed-host or assurance acceptance."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_esg_foundation import (  # noqa: F401
    bind_request,
    case,
    decision,
    draft,
)
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import configure

__all__ = []


@pytest.fixture
def esg_run(case, monkeypatch, tmp_path):
    """Bind a real public partial case and immutable ordinary draft to the host."""
    evidence = case.esg.execute(case.context, "bind_evidence", bind_request(case))
    reviewed = decision(case, evidence["reference"])
    artifact = draft(case, reviewed["reference"])
    binding = {
        "work_ref": "fictional-esg",
        "client_root": str(case.root),
        "client_id": case.client,
        "engagement_id": case.engagement,
        "run_id": case.prepared["run"]["run_id"],
        "workflow_id": "esg-reporting-assurance",
    }
    configure(monkeypatch, tmp_path, [binding])
    return case, binding, artifact["reference"]


def program(fixture):
    return f"""
const work={{work_ref:{json.dumps(fixture[1]['work_ref'])}}};
const setupCall=call('vera_workspace_esg_setup',work);
const setup=payload(setupCall);
const identity={{...work,source_ref:{json.dumps(fixture[2]['sha256'])}}};
const readCall=call('vera_workspace_esg_read',identity);
const page=payload(readCall);
const exact={{...identity,revision:page.revision}};
"""


def test_esg_whole_versions_dependencies_original_drafts_and_explicit_model_context(
    esg_run,
):
    fixture = esg_run[0]
    before = {p.name: p.read_bytes() for p in fixture.output.iterdir()}
    result = rpc_program(
        os.environ.copy(),
        program(esg_run)
        + """
const outputsCall=call('vera_workspace_esg_outputs',exact);
const contextCall=call('vera_workspace_esg_context',exact);
const catalogue=payload(call('vera_workspace_open',{}));
const result={setupCall,readCall,outputsCall,contextCall,setup,page,outputs:payload(outputsCall),catalogue};
""",
    )
    state = json.loads((fixture.output / "esg_state.json").read_bytes())
    assert result["page"]["version_record"] == state["objects"][-1]
    assert result["page"]["dependencies"] == state["objects"][-1]["dependencies"]
    assert result["page"]["can_write"] is False
    assert result["page"]["compliance_claim_enabled"] is False
    assert result["setup"]["total"] == 4
    assert "rows" not in result["setupCall"]["structuredContent"]
    assert "record" not in result["readCall"]["structuredContent"]
    assert "files" not in result["outputsCall"]["structuredContent"]
    context = result["contextCall"]["structuredContent"]
    assert "_meta" not in result["contextCall"]
    assert [x["version_record"] for x in context["dependency_records"]] == state[
        "objects"
    ][:-1]
    assert context["actual_model_reads_verified"] is False
    assert str(fixture.root) not in json.dumps(result["contextCall"])
    assert result["catalogue"]["works"][0]["setup_available"] is True
    for file in result["outputs"]["files"]:
        raw = Path(file["path"]).read_bytes()
        assert file["content"].encode() == raw
        assert file["sha256"] == hashlib.sha256(raw).hexdigest()
    assert {p.name: p.read_bytes() for p in fixture.output.iterdir()} == before


def test_esg_updated_observation_keeps_historical_decision_and_draft_stale(esg_run):
    fixture = esg_run[0]
    request = bind_request(fixture, idempotency_key="changed-observation")
    request["observation"][
        "rationale"
    ] = "Fictional clarified interpretation of the same zero"
    fixture.esg.execute(fixture.context, "bind_evidence", request)
    result = rpc_program(
        os.environ.copy(),
        program(esg_run)
        + "const result={setup,page,context:call('vera_workspace_esg_context',exact).structuredContent};",
    )
    assert result["page"]["current"] is False
    old = result["context"]["dependency_records"]
    assert old[-1]["version_record"]["record"]["decided_by"] == "Synthetic reviewer"
    assert old[-1]["current"] is False
    assert (
        old[1]["version_record"]["record"]["observation"]["rationale"]
        == "Supplied synthetic cell"
    )
    assert result["setup"]["total"] == 5


def test_esg_new_state_refuses_old_context_and_output_selection(esg_run):
    old = rpc_program(os.environ.copy(), program(esg_run) + "const result=exact;")
    request = bind_request(esg_run[0], idempotency_key="state-changed")
    request["observation"]["rationale"] = "Fictional new interpretation"
    esg_run[0].esg.execute(esg_run[0].context, "bind_evidence", request)
    result = rpc_program(
        os.environ.copy(),
        f"const exact={json.dumps(old)};const result={{context:call('vera_workspace_esg_context',exact),outputs:call('vera_workspace_esg_outputs',exact)}};",
    )
    assert result["context"]["isError"] is True
    assert result["outputs"]["isError"] is True


@pytest.mark.parametrize("member", ["esg_state.json", ".md", ".json"])
def test_esg_altered_ordinary_state_or_draft_refuses_resume(esg_run, member):
    path = esg_run[0].output / (
        member
        if member == "esg_state.json"
        else "esg-draft-" + esg_run[2]["sha256"] + member
    )
    path.write_bytes(path.read_bytes() + b" changed")
    result = rpc_program(
        os.environ.copy(),
        f"const result=call('vera_workspace_esg_setup',{{work_ref:{json.dumps(esg_run[1]['work_ref'])}}});",
    )
    assert result["isError"] is True


def test_esg_foreign_version_and_nonartifact_output_are_refused(esg_run):
    result = rpc_program(
        os.environ.copy(),
        program(esg_run)
        + """
const evidence=setup.rows.find(r=>r.kind==='evidence');
const selected=payload(call('vera_workspace_esg_read',{...work,source_ref:evidence.source_ref}));
const result={foreign:call('vera_workspace_esg_read',{...work,source_ref:'a'.repeat(64)}),nonartifact:call('vera_workspace_esg_outputs',{...work,source_ref:evidence.source_ref,revision:selected.revision})};
""",
    )
    assert result["foreign"]["isError"] is True
    assert result["nonartifact"]["isError"] is True


def test_esg_paging_exposes_every_version_without_automatic_selection(esg_run):
    fixture = esg_run[0]
    for index in range(31):
        request = bind_request(
            fixture, id=f"energy-{index}", idempotency_key=f"page-{index}"
        )
        fixture.esg.execute(fixture.context, "bind_evidence", request)
    result = rpc_program(
        os.environ.copy(),
        program(esg_run)
        + "const result={setup,last:payload(call('vera_workspace_esg_setup',{...work,offset:30}))};",
    )
    assert result["setup"]["total"] == 35
    assert len(result["setup"]["rows"]) == 30
    assert result["setup"]["has_more"] is True
    assert len(result["last"]["rows"]) == 5
    assert result["last"]["has_more"] is False
    assert "selection" not in result["setup"]


def test_esg_complete_context_over_limit_refuses_without_truncation(esg_run):
    fixture = esg_run[0]
    # Public draft text can exceed the native context envelope; ordinary files stay intact.
    value = fixture.esg.execute(
        fixture.context,
        "build_deliverables",
        {
            "id": "long-memo",
            "idempotency_key": "long-memo",
            "dependencies": [esg_run[2]],
            "expected_state_sha256": fixture.esg.resume_case(fixture.context)[
                "state_sha256"
            ],
            "claim": "partial_draft",
            "title": "Fictional long partial draft",
            "content": "a" * 70000,
        },
    )
    result = rpc_program(
        os.environ.copy(),
        program((fixture, esg_run[1], value["reference"]))
        + "const result={page,context:call('vera_workspace_esg_context',exact)};",
    )
    assert len(result["page"]["record"]["content"]) == 70000
    assert result["context"]["isError"] is True
    assert (
        fixture.output / ("esg-draft-" + value["reference"]["sha256"] + ".md")
    ).is_file()


def test_esg_missing_case_is_explicit_and_does_not_invent_evidence(esg_run):
    fixture = esg_run[0]
    (fixture.output / "esg_state.json").unlink()
    result = rpc_program(
        os.environ.copy(),
        f"const result=payload(call('vera_workspace_esg_setup',{{work_ref:{json.dumps(esg_run[1]['work_ref'])}}}));",
    )
    assert result["setup_status"] == "case_required"
    assert result["rows"] == []
    assert not (fixture.output / "esg_state.json").exists()


def test_esg_completed_viewer_preserves_originals_after_same_engagement_successor(
    esg_run, monkeypatch
):
    fixture, binding, _ = esg_run
    write_no_model_report(fixture.output, "esg-reporting-assurance", binding["run_id"])
    declarations = [
        {
            "artifact_id": path.name.replace(".", "-"),
            "path": path.name,
            "purpose": "Inspect fictional partial ESG foundation outputs.",
            "audience": "review",
            "media_type": (
                "application/json" if path.suffix == ".json" else "text/markdown"
            ),
        }
        for path in fixture.output.iterdir()
        if path.is_file()
    ]
    fixture.ledger.finalize_run(
        fixture.root, fixture.engagement, binding["run_id"], declarations
    )
    fixture.ledger.complete_run(fixture.root, fixture.engagement, binding["run_id"])
    before = {p.name: p.read_bytes() for p in fixture.output.iterdir()}
    prepared = fixture.ledger.prepare_run(
        fixture.root,
        fixture.client,
        fixture.engagement,
        "esg-reporting-assurance",
        "development",
        input_ids=[fixture.receipt["input_id"]],
    )
    fixture.ledger.start_run(
        fixture.root, fixture.engagement, prepared["run"]["run_id"]
    )
    successor = {
        **fixture.request,
        "idempotency_key": "successor-start",
        "previous_context": str(fixture.context),
    }
    fixture.esg.execute(Path(prepared["context_path"]), "start_case", successor)
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "VIEWER")
    result = rpc_program(
        os.environ.copy(),
        program(esg_run)
        + "const result={page,outputs:payload(call('vera_workspace_esg_outputs',exact))};",
    )
    assert result["page"]["run_status"] == "completed"
    assert result["page"]["can_write"] is False
    assert (
        result["outputs"]["files"][0]["content"].encode()
        == before[result["outputs"]["files"][0]["name"]]
    )
    assert {p.name: p.read_bytes() for p in fixture.output.iterdir()} == before
    assert fixture.ledger.validate_run_artifacts(
        fixture.root, fixture.engagement, binding["run_id"]
    )["artifacts"]


def test_esg_other_engagement_cannot_retrieve_foreign_version(
    esg_run, monkeypatch, tmp_path
):
    fixture, binding, reference = esg_run
    other = fixture.ledger.create_engagement(
        fixture.root, fixture.client, "Other fictional ESG"
    )["engagement_id"]
    receipt = fixture.ledger.import_document(
        fixture.root, fixture.client, other, fixture.source, "source"
    )["receipt"]
    prepared = fixture.ledger.prepare_run(
        fixture.root,
        fixture.client,
        other,
        "esg-reporting-assurance",
        "development",
        input_ids=[receipt["input_id"]],
    )
    fixture.ledger.start_run(fixture.root, other, prepared["run"]["run_id"])
    fixture.esg.execute(
        Path(prepared["context_path"]),
        "start_case",
        {**fixture.request, "case_id": "other-esg"},
    )
    foreign = {
        **binding,
        "work_ref": "foreign-esg",
        "engagement_id": other,
        "run_id": prepared["run"]["run_id"],
    }
    configure(monkeypatch, tmp_path, [binding, foreign])
    result = rpc_program(
        os.environ.copy(),
        f"const result=call('vera_workspace_esg_read',{{work_ref:'foreign-esg',source_ref:{json.dumps(reference['sha256'])}}});",
    )
    assert result["isError"] is True
    assert "owned run" in result["content"][0]["text"]


def test_esg_state_link_refused_without_reading_target(esg_run, tmp_path):
    path = esg_run[0].output / "esg_state.json"
    saved = tmp_path / "outside-state.json"
    path.rename(saved)
    path.symlink_to(saved)
    result = rpc_program(
        os.environ.copy(),
        f"const result=call('vera_workspace_esg_setup',{{work_ref:{json.dumps(esg_run[1]['work_ref'])}}});",
    )
    assert result["isError"] is True
    assert saved.is_file()
