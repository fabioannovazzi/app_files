"""Human-label/evaluation source mechanisms; no installed-host or provider acceptance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_passive_audit import audit_workspace  # noqa: F401
from tests.plugins.test_vera_native_passive_service import (  # noqa: F401
    passive_service,
    prepare,
)


def label_program(fields, label="problematic"):
    return (
        prepare(fields)
        + """
const reviewAuthority=p=>({work_ref:p.work_ref,revision:p.revision,review_ticket:p.review_ticket,source_ref:p.data.selection.source_ref,expected_draft_revision:p.draft.draft_revision});
const initial=payload(call('vera_workspace_passive_review_setup',{work_ref:qualified.work_ref}));
const entry={label:"""
        + json.dumps(label)
        + """,known_issue:'Fictional explicitly authored benchmark issue'};
const saved=payload(call('vera_workspace_passive_review_draft_save',{...reviewAuthority(initial),entries:{[initial.items[0].id]:entry},operator_ref:'Fictional actual reviewer',decision_basis:'Fictional reviewed benchmark; no approval of ledger treatment'}));
const recovered=payload(call('vera_workspace_passive_review_setup',{work_ref:initial.work_ref}));
"""
    )


@pytest.mark.parametrize(
    "label,recall,ambiguous",
    [("problematic", 0.0, 0), ("acceptable", None, 0), ("ambiguous", None, 1)],
)
def test_native_human_labels_evaluate_actual_public_results_and_preserve_screening(
    passive_service, label, recall, ambiguous
):
    work, _, env, fields, module = passive_service
    before = (work.output / "full_population.jsonl").read_bytes()
    result = rpc_program(
        env,
        label_program(fields, label)
        + """
const args={...reviewAuthority(recovered),human_reviewed:true,idempotency_key:'human-review'};
const published=payload(call('vera_workspace_passive_review_publish',args));
const retry=payload(call('vera_workspace_passive_review_publish',args));
const reopened=payload(call('vera_workspace_passive_review_setup',{work_ref:initial.work_ref}));
const files=payload(call('vera_workspace_passive_review_outputs',{work_ref:initial.work_ref,revision:reopened.revision,source_ref:reopened.data.selection.source_ref}));
const explain=call('vera_workspace_passive_review_explain',{work_ref:initial.work_ref,revision:reopened.revision,source_ref:reopened.data.selection.source_ref,review_ref:published.review_ref,item_id:initial.items[0].id}).structuredContent;
const result={published,retry,reopened,files,explain};
""",
    )
    assert result["published"]["status"] == "completed"
    assert result["retry"]["review_ref"] == result["published"]["review_ref"]
    metrics = result["reopened"]["selected_review"]["metrics"]
    assert metrics["exception_recall"] == recall
    assert metrics["ambiguous_population"] == ambiguous
    assert metrics["label_coverage"] == 1.0
    assert result["reopened"]["draft"]["exists"] is False
    assert result["reopened"]["items"][0]["reviewed"]["label"] == label
    assert result["explain"]["untrusted_evidence"]["value"]["label"] == label
    assert "population" not in result["explain"]
    assert len(result["files"]["outputs"]) == 4
    assert all(Path(row["path"]).is_file() for row in result["files"]["outputs"])
    assert (work.output / "full_population.jsonl").read_bytes() == before
    assert result["published"]["professional_approval"] is False
    assert result["reopened"]["professional_approval"] is False


def test_native_human_draft_cas_and_confirmation_refusal_preserve_unfinished_labels(
    passive_service,
):
    work, _, env, fields, _ = passive_service
    result = rpc_program(
        env,
        label_program(fields)
        + """
const raced=call('vera_workspace_passive_review_draft_save',{...reviewAuthority(initial),entries:{},operator_ref:'lost update',decision_basis:'lost update'});
const unconfirmed=call('vera_workspace_passive_review_publish',{...reviewAuthority(recovered),human_reviewed:false,idempotency_key:'not-confirmed'});
const result={raced,unconfirmed,recovered};
""",
    )
    assert result["raced"]["isError"] is True
    assert result["unconfirmed"]["isError"] is True
    assert result["recovered"]["items"][0]["draft"]["label"] == "problematic"
    assert result["recovered"]["operator_ref"] == "Fictional actual reviewer"
    assert "human_reviewed" not in result["recovered"]["draft"]
    assert not (work.output / "professional_reviews").exists()


def test_native_human_missing_draft_shard_requires_explicit_scoped_discard(
    passive_service,
):
    work, _, env, fields, _ = passive_service
    rpc_program(env, label_program(fields) + "const result=recovered;")
    directory = next(
        (work.output.parent / ".native-workspace").glob("passive-label-draft-*")
    )
    head = json.loads((directory / "head.json").read_text())
    (directory / (next(iter(head["buckets"].values())) + ".json")).unlink()
    result = rpc_program(
        env,
        """
const page=payload(call('vera_workspace_passive_review_setup',{work_ref:'fictional-passive'}));
const args={work_ref:page.work_ref,revision:page.revision,review_ticket:page.review_ticket,source_ref:page.data.selection.source_ref,expected_draft_revision:page.draft.draft_revision};
const refused=call('vera_workspace_passive_review_publish',{...args,human_reviewed:true,idempotency_key:'damaged-draft'});
const cleared=payload(call('vera_workspace_passive_review_draft_clear',args));
const reopened=payload(call('vera_workspace_passive_review_setup',{work_ref:page.work_ref}));
const result={page,refused,cleared,reopened};
""",
    )
    assert result["page"]["draft"]["damaged"] is True
    assert result["page"]["items"][0]["draft"] is None
    assert result["refused"]["isError"] is True
    assert result["cleared"]["cleared"] is True
    assert result["reopened"]["draft"]["exists"] is False
    assert not (work.output / "professional_reviews").exists()


@pytest.mark.parametrize(
    "surface,audit_workspace,screening_status",
    [
        ("codex", "ordinary", "completed"),
        ("cowork", "cowork", "awaiting_semantic_review"),
    ],
    indirect=["audit_workspace"],
)
def test_native_human_evaluation_fresh_package_preserves_host_pending_boundary(
    passive_service, tmp_path, surface, screening_status
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    work, _, env, fields, _ = passive_service
    builder = load_builder(
        "build_codex_plugin_zip" if surface == "codex" else "build_claude_plugin_zip"
    )
    if surface == "codex":
        vera = next(p for p in builder.load_bundles() if p.name == "vera")
        entries = builder.expected_zip_entries(vera)
        prefix = vera.package_root + "/plugins/vera/"
    else:
        _, packages = builder.load_configuration()
        vera = next(p for p in packages if p.plugin == "vera")
        entries = builder.claude_package_entries(vera)
        prefix = ""
    target = tmp_path / "fresh-review-package"
    for name, content in entries.items():
        if name.startswith(prefix):
            path = target / name[len(prefix) :]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    before = (work.output / "full_population.jsonl").read_bytes()

    result = rpc_program(
        env,
        label_program(fields)
        + """
const published=payload(call('vera_workspace_passive_review_publish',{...reviewAuthority(recovered),human_reviewed:true,idempotency_key:'packaged-human-review'}));
const current=payload(call('vera_workspace_passive_review_setup',{work_ref:initial.work_ref}));
const result={published,current};
""",
        server=target / "mcp/workspace.cjs",
    )

    assert result["published"]["status"] == "completed"
    assert result["current"]["screening_status"] == screening_status
    assert (
        result["current"]["selected_review"]["record"]["screening_status"]
        == screening_status
    )
    assert result["current"]["professional_approval"] is False
    assert (work.output / "full_population.jsonl").read_bytes() == before
    if surface == "cowork":
        assert list(work.output.rglob("cowork_request.json"))
        assert not list(work.output.rglob("cowork_response.json"))


@pytest.mark.parametrize("audit_workspace", ["many"], indirect=True)
def test_native_human_labels_three_pages_and_correction_retain_previous_version(
    passive_service,
):
    work, _, env, fields, _ = passive_service
    result = rpc_program(
        env,
        prepare(fields)
        + """
for(const offset of [0,30,60]){const page=payload(call('vera_workspace_passive_review_setup',{work_ref:qualified.work_ref,offset}));const entries=Object.fromEntries(page.items.map(row=>[row.id,{label:'problematic',known_issue:'Fictional reviewed benchmark '+row.title}]));payload(call('vera_workspace_passive_review_draft_save',{...authority(page),entries,operator_ref:'Fictional paginated reviewer',decision_basis:'Explicit fictional benchmark; no posting approval'}));}
const firstPage=payload(call('vera_workspace_passive_review_setup',{work_ref:qualified.work_ref}));
const first=payload(call('vera_workspace_passive_review_publish',{...authority(firstPage),human_reviewed:true,idempotency_key:'first-61'}));
const last=payload(call('vera_workspace_passive_review_setup',{work_ref:qualified.work_ref,offset:60}));
payload(call('vera_workspace_passive_review_draft_save',{...authority(last),entries:{[last.items[0].id]:{label:'acceptable',known_issue:'Fictional explicitly corrected judgment'}},operator_ref:'Fictional correcting reviewer',decision_basis:'Changed only this exact label; preserve all other labels'}));
const changed=payload(call('vera_workspace_passive_review_setup',{work_ref:qualified.work_ref}));
const second=payload(call('vera_workspace_passive_review_publish',{...authority(changed),human_reviewed:true,idempotency_key:'second-61'}));
const historical=payload(call('vera_workspace_passive_review_setup',{work_ref:qualified.work_ref,review_ref:first.review_ref,offset:60}));
const current=payload(call('vera_workspace_passive_review_setup',{work_ref:qualified.work_ref,offset:60}));
const result={first,second,historical,current};
""",
    )
    assert result["current"]["selected_review"]["metrics"]["labelled_population"] == 61
    assert (
        result["current"]["selected_review"]["metrics"]["problematic_population"] == 60
    )
    assert result["current"]["items"][0]["reviewed"]["label"] == "acceptable"
    assert result["historical"]["items"][0]["reviewed"]["label"] == "problematic"
    assert (
        result["historical"]["selected_review"]["metrics"]["problematic_population"]
        == 61
    )
    assert result["historical"]["can_edit"] is False
    assert (
        result["current"]["selected_review"]["record"]["parent_review_ref"]
        == result["first"]["review_ref"]
    )
    assert (
        len(list((work.output / "professional_review_populations").glob("*.jsonl")))
        == 1
    )
    assert len(list((work.output / "professional_reviews").iterdir())) == 2


@pytest.mark.parametrize(
    "fault", ["foreign_output", "replaced_guard", "changed_review_code"]
)
def test_native_human_evaluation_fault_preserves_artifacts_and_uncertain_intent(
    passive_service, monkeypatch, fault
):
    import native_passive_review as review

    work, _, env, fields, module = passive_service
    page = rpc_program(env, label_program(fields) + "const result=recovered;")
    before = (work.output / "full_population.jsonl").read_bytes()
    actual = review.evaluate
    actual_hash = review.file_hash

    def faulty_evaluate(*args):
        result = actual(*args)
        if fault == "changed_review_code":
            monkeypatch.setattr(
                review,
                "file_hash",
                lambda path: (
                    "0" * 64
                    if path.name == "native_passive_review_bridge.py"
                    else actual_hash(path)
                ),
            )
        else:
            path = (
                work.output / "external-change.txt"
                if fault == "foreign_output"
                else work.output.parent / ".native-workspace/write.lock"
            )
            path.write_text("Fictional external change")
        return result

    monkeypatch.setattr(review, "evaluate", faulty_evaluate)
    args = {
        "work_ref": page["work_ref"],
        "revision": page["revision"],
        "source_ref": page["data"]["selection"]["source_ref"],
        "expected_draft_revision": page["draft"]["draft_revision"],
        "human_reviewed": True,
        "idempotency_key": "faulty-human-write",
    }
    with pytest.raises(ValueError, match="changed"):
        module.dispatch("vera_workspace_passive_review_publish", args)
    receipt = json.loads(
        next(
            (work.output.parent / ".native-workspace").glob(
                "passive-label-operation-*.json"
            )
        ).read_text()
    )
    assert receipt["status"] == "uncertain"
    assert (work.output / "full_population.jsonl").read_bytes() == before
    assert (
        len(list((work.output / "professional_reviews").glob("*/evaluation.json"))) == 1
    )
    monkeypatch.setattr(review, "evaluate", actual)
    monkeypatch.setattr(review, "file_hash", actual_hash)
    reopened = module.dispatch(
        "vera_workspace_passive_review_setup", {"work_ref": page["work_ref"]}
    )
    assert reopened["can_edit"] is False
    assert reopened["pending"][0]["status"] == "uncertain"


def test_native_human_evaluation_modified_timestamp_is_not_a_new_valid_version(
    passive_service,
):
    work, _, env, fields, module = passive_service
    rpc_program(
        env,
        label_program(fields)
        + "const result=payload(call('vera_workspace_passive_review_publish',{...reviewAuthority(recovered),human_reviewed:true,idempotency_key:'immutable-review'}));",
    )
    path = next((work.output / "professional_reviews").glob("*/evaluation.json"))
    report = json.loads(path.read_text())
    report["evaluated_at"] = "Altered timestamp"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="completed receipt"):
        module.dispatch(
            "vera_workspace_passive_review_setup", {"work_ref": "fictional-passive"}
        )


@pytest.mark.parametrize("audit_workspace", ["failed"], indirect=True)
def test_native_human_historical_population_survives_actual_public_job_resume(
    passive_service,
):
    work, _, env, fields, _ = passive_service
    original = (work.output / "full_population.jsonl").read_bytes()
    first = rpc_program(
        env,
        label_program(fields)
        + "const result=payload(call('vera_workspace_passive_review_publish',{...reviewAuthority(recovered),human_reviewed:true,idempotency_key:'before-worker-resume'}));",
    )

    work.native.run_job(work.producer, work.plan, work.fixture.FixtureRunner({}))
    result = rpc_program(
        env,
        """
const current=payload(call('vera_workspace_passive_review_setup',{work_ref:'fictional-passive'}));
const historical=payload(call('vera_workspace_passive_review_setup',{work_ref:'fictional-passive',review_ref:"""
        + json.dumps(first["review_ref"])
        + """}));
const result={current,historical};
""",
    )

    assert (work.output / "full_population.jsonl").read_bytes() != original
    assert result["current"]["selected_review"]["current_population"] is False
    assert result["current"]["items"][0]["reviewed"] is None
    assert result["historical"]["items"][0]["reviewed"]["label"] == "problematic"
    assert result["historical"]["can_edit"] is False
    assert result["current"]["screening_status"] == "completed"
    assert (
        result["historical"]["selected_review"]["record"]["screening_status"]
        == "failed"
    )
    snapshot = next((work.output / "professional_review_populations").glob("*.jsonl"))
    assert snapshot.read_bytes() == original
