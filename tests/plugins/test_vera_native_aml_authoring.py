"""Actual maintained AML proposals and explicit human gates, using fictional evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_vera_aml_review import review_for
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import registry_workspace

__all__ = []


@pytest.fixture
def author_run(registry_workspace, tmp_path):
    env, studio, _, _, client_id, engagement_id = registry_workspace
    env.update(
        VERA_WORKSPACE_ACTOR_ID="fictional-reviewer",
        VERA_WORKSPACE_TENANT_ID="fictional-studio",
        VERA_WORKSPACE_ROLES="REVIEWER",
    )
    folder = studio / "Cliente Beta"
    ledger = _load_customer_ledger()
    source = tmp_path / "fictional-loan.txt"
    source.write_text(
        "Fictional lender A; fictional payer B; EUR 200000. No real client data."
    )
    imported = ledger.import_document(
        folder, client_id, engagement_id, source, "source"
    )["receipt"]
    prepared = ledger.prepare_run(
        folder,
        client_id,
        engagement_id,
        "aml-review",
        "test-version",
        input_ids=[imported["input_id"]],
    )
    loaded = ledger.start_run(folder, engagement_id, prepared["run"]["run_id"])
    loaded = ledger.load_run(folder, engagement_id, prepared["run"]["run_id"])
    source_row = loaded["input_manifest"]["inputs"][0]
    inputs = Path(loaded["run_root"]) / "inputs"
    evidence = Path(loaded["run_root"]) / source_row["execution_relative_path"]
    review = review_for(evidence, inputs)
    reference = "studio-" + "_".join(
        x.split("_", 1)[1]
        for x in (client_id, engagement_id, prepared["run"]["run_id"])
    )
    return (
        env,
        Path(loaded["output_dir"]),
        reference,
        review,
        folder,
        engagement_id,
        prepared["run"]["run_id"],
    )


def program(reference: str, review: dict, body: str) -> str:
    return f"""
const work_ref={json.dumps(reference)}, review={json.dumps(review)};
const setup=payload(call('vera_workspace_aml_author_setup',{{work_ref}}));
const fields={{question:'Fictional review of the documented loan: preserve unresolved explanations.',input_ids:setup.sources.map(s=>s.binding_id)}};
const requestArgs={{work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft.draft_revision,fields,confirmed:true,idempotency_key:'fictional-mandate'}};
const model=result=>{{if(result.isError)throw new Error(result.content[0].text);return result.structuredContent;}};
{body}
"""


REQUEST = """
const requested=payload(call('vera_workspace_aml_author_request',requestArgs));
const exact={work_ref,grant_ref:requested.grant_ref};
const context=model(call('vera_workspace_aml_author_context',exact));
"""
STAGE = """
const stageArgs={...exact,expected_stage_revision:context.stage_revision,review,idempotency_key:'fictional-proposal'};
const staged=model(call('vera_workspace_aml_author_stage',stageArgs));
const read=payload(call('vera_workspace_aml_author_read',{...exact,stage_ref:staged.stage_ref}));
const publishArgs={...exact,revision:read.revision,review_ticket:read.review_ticket,item_id:read.selection.id,stage_ref:staged.stage_ref,confirmed:true,idempotency_key:'fictional-conserve'};
"""


@pytest.mark.parametrize("variant", ["it", "empty", "geneva"])
def test_explicit_model_proposal_conserved_by_public_producer_without_professional_decision(
    author_run, variant
):
    env, output, reference, review, folder, engagement, run_id = author_run
    if variant == "empty":
        review["findings"] = []
    if variant == "geneva":
        review.update(
            jurisdiction="CH-GE",
            language="fr",
            jurisdiction_basis="Fictional Geneva mandate requiring professional qualification.",
            mandate_applicability={
                "status": "unresolved",
                "basis": "Fictional engagement; actual applicability not yet established.",
                "citations": review["assessment_citations"],
            },
        )
    result = rpc_program(
        env,
        program(
            reference,
            review,
            REQUEST
            + "const requestRetry=payload(call('vera_workspace_aml_author_request',requestArgs));"
            + STAGE
            + """
const stageRetry=model(call('vera_workspace_aml_author_stage',stageArgs));
const published=payload(call('vera_workspace_aml_author_publish',publishArgs));
const retry=payload(call('vera_workspace_aml_author_publish',publishArgs));
const view=payload(call('vera_workspace_view',{work_ref,source_ref:published.source_ref}));
const result={requested,requestRetry,context,staged,stageRetry,read,published,retry,view};
""",
        ),
    )
    actual = json.loads(
        (output / (result["published"]["source_ref"] + ".json")).read_bytes()
    )
    assert actual == result["read"]["record"]
    assert (output / (result["published"]["source_ref"] + ".md")).read_text() == result[
        "read"
    ]["memo"]
    assert actual["review"] == review
    assert actual["status"] == "draft_for_review"
    assert result["published"]["professional_approval"] is False
    assert result["requested"] == result["requestRetry"]
    assert result["staged"] == result["stageRetry"]
    assert result["published"] == result["retry"]
    assert (
        _load_customer_ledger().load_run(folder, engagement, run_id)["run"]["status"]
        == "running"
    )
    assert result["context"]["question"].startswith("Fictional review")
    assert (
        result["context"]["sources"][0]["relative_path"] == review["sources"][0]["path"]
    )
    assert result["view"]["data"]["can_decide"] is True


def test_unfinished_draft_recovers_without_model_grant_or_official_record(author_run):
    env, output, reference, review, *_ = author_run
    result = rpc_program(
        env,
        program(
            reference,
            review,
            """
const args={work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft.draft_revision,fields:{question:'Unfinished actual question',input_ids:[]}};
const saved=payload(call('vera_workspace_aml_author_draft_store',args));
const reopened=payload(call('vera_workspace_aml_author_setup',{work_ref}));
const contextDenied=call('vera_workspace_aml_author_context',{work_ref,grant_ref:'mandate-'+'a'.repeat(64)});
const result={saved,reopened,contextDenied};
""",
        ),
    )
    assert result["reopened"]["draft"]["fields"] == {
        "question": "Unfinished actual question",
        "input_ids": [],
    }
    assert result["reopened"]["mandates"] == []
    assert result["contextDenied"]["isError"] is True
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "change", ["approval", "missing_source", "changed_hash", "unsealed_previous"]
)
def test_model_proposal_refuses_fabricated_decisions_or_foreign_source_provenance(
    author_run, change
):
    env, output, reference, review, *_ = author_run
    if change == "approval":
        review["professional_decision"] = {"reviewer_ref": "Invented reviewer"}
    elif change == "missing_source":
        review["sources"] = []
    elif change == "changed_hash":
        review["sources"][0]["sha256"] = "0" * 64
    else:
        review["previous"] = {"source_id": "S1", "record_sha256": "a" * 64}
    result = rpc_program(
        env,
        program(
            reference,
            review,
            REQUEST
            + """
const denied=call('vera_workspace_aml_author_stage',{...exact,expected_stage_revision:context.stage_revision,review,idempotency_key:'refused-stage'});
const result={denied};
""",
        ),
    )
    assert result["denied"]["isError"] is True
    assert not list(output.glob("aml-review-*"))
    private = output.parent / ".native-workspace"
    assert not list(private.glob("aml-authoring-*/mandate-*/stage-request-*"))


@pytest.mark.parametrize(
    "change",
    ["ticket", "foreign_input", "empty_sources", "unconfirmed", "stale_revision"],
)
def test_app_mandate_refuses_wrong_scope_without_creating_grant(author_run, change):
    env, output, reference, review, *_ = author_run
    mutation = {
        "ticket": "requestArgs.review_ticket='bad';",
        "foreign_input": "requestArgs.fields.input_ids=['input_'+'0'.repeat(24)];",
        "empty_sources": "requestArgs.fields.input_ids=[];",
        "unconfirmed": "requestArgs.confirmed=false;",
        "stale_revision": "requestArgs.revision='0'.repeat(64);",
    }[change]
    result = rpc_program(
        env,
        program(
            reference,
            review,
            mutation
            + "const result=call('vera_workspace_aml_author_request',requestArgs);",
        ),
    )
    assert result["isError"] is True
    assert not list(
        (output.parent / ".native-workspace").glob("aml-authoring-*/mandate-*")
    )


@pytest.mark.parametrize(
    "damage", ["orphan", "pending", "missing_stage_receipt", "changed_stage"]
)
def test_uncertain_private_proposals_block_writes_and_archive_closure(
    author_run, damage
):
    env, output, reference, review, folder, engagement, run_id = author_run
    staged = rpc_program(
        env,
        program(
            reference, review, REQUEST + STAGE + "const result={requested,staged,read};"
        ),
    )
    base = (
        next((output.parent / ".native-workspace").glob("aml-authoring-*"))
        / staged["requested"]["grant_ref"]
    )
    if damage == "orphan":
        (base / ("proposal-" + "0" * 64)).mkdir()
    elif damage == "pending":
        (base / "publish-request-interrupted.json").write_text("{}")
    elif damage == "missing_stage_receipt":
        next(base.glob("stage-request-*.json")).unlink()
    else:
        (base / staged["staged"]["stage_ref"] / "memo.md").write_text("Altered memo")
    result = rpc_program(
        env,
        f"""
const work_ref={json.dumps(reference)};
const setupNow=call('vera_workspace_aml_author_setup',{{work_ref}});
const closure=call('vera_workspace_archive_closure',{{client_id:'client_222222222222222222222222',engagement_id:{json.dumps(engagement)},run_id:{json.dumps(run_id)}}});
const result={{setupNow,closure}};
""",
    )
    assert result["closure"]["isError"] is True
    if damage == "changed_stage":
        assert result["setupNow"]["isError"] is True
    else:
        assert result["setupNow"]["_meta"]["workspace"]["can_write"] is False
        assert result["setupNow"]["_meta"]["workspace"]["recovery_required"] is True


def test_registered_source_change_refuses_retained_grant(author_run):
    env, output, reference, review, folder, engagement, run_id = author_run
    result = rpc_program(
        env, program(reference, review, REQUEST + "const result={requested,context};")
    )
    Path(result["context"]["sources"][0]["path"]).write_text(
        "Changed fictional evidence"
    )
    denied = rpc_program(
        env,
        f"const result=call('vera_workspace_aml_author_context',{{work_ref:{json.dumps(reference)},grant_ref:{json.dumps(result['requested']['grant_ref'])}}});",
    )
    assert denied["isError"] is True
    assert not list(output.glob("aml-review-*"))


def test_concurrent_intake_does_not_overwrite_retained_question(author_run):
    env, output, reference, review, *_ = author_run
    result = rpc_program(
        env,
        program(
            reference,
            review,
            """
const args={work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:setup.draft.draft_revision,fields:{question:'First explicit draft',input_ids:[]}};
const first=payload(call('vera_workspace_aml_author_draft_store',args));
const second=call('vera_workspace_aml_author_draft_store',{...args,fields:{question:'Stale replacement',input_ids:[]}});
const reopened=payload(call('vera_workspace_aml_author_setup',{work_ref}));
const result={first,second,reopened};
""",
        ),
    )
    assert result["second"]["isError"] is True
    assert result["reopened"]["draft"]["fields"]["question"] == "First explicit draft"
    assert list(output.iterdir()) == []


def test_other_reviewer_cannot_reopen_model_mandate(author_run):
    env, output, reference, review, *_ = author_run
    granted = rpc_program(
        env, program(reference, review, REQUEST + "const result=requested;")
    )
    foreign_env = {**env, "VERA_WORKSPACE_ACTOR_ID": "different-fictional-reviewer"}
    result = rpc_program(
        foreign_env,
        f"const result=call('vera_workspace_aml_author_context',{{work_ref:{json.dumps(reference)},grant_ref:{json.dumps(granted['grant_ref'])}}});",
    )
    assert result["isError"] is True
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "damage", ["missing_receipt", "foreign_record_identity", "changed_stage_identity"]
)
def test_conservation_metadata_damage_refuses_fresh_write_and_closure(
    author_run, damage
):
    env, output, reference, review, folder, engagement, run_id = author_run
    result = rpc_program(
        env,
        program(
            reference,
            review,
            REQUEST
            + STAGE
            + "const published=payload(call('vera_workspace_aml_author_publish',publishArgs));const result={requested,staged,published};",
        ),
    )
    base = (
        next((output.parent / ".native-workspace").glob("aml-authoring-*"))
        / result["requested"]["grant_ref"]
    )
    if damage == "missing_receipt":
        next(base.glob("publish-request-*.json")).unlink()
    else:
        state = json.loads((base / "state.json").read_text())
        if damage == "foreign_record_identity":
            state["publications"][0]["result"]["source_ref"] = "../outside"
        else:
            state["stages"][0]["source_ref"] = "aml-review-" + "0" * 64
        (base / "state.json").write_text(json.dumps(state))
    conserved = (output / (result["published"]["source_ref"] + ".json")).read_bytes()
    denied = rpc_program(
        env,
        f"""
const setupNow=call('vera_workspace_aml_author_setup',{{work_ref:{json.dumps(reference)}}});
const closure=call('vera_workspace_archive_closure',{{client_id:'client_222222222222222222222222',engagement_id:{json.dumps(engagement)},run_id:{json.dumps(run_id)}}});
const result={{setupNow,closure}};
""",
    )
    assert denied["closure"]["isError"] is True
    assert (
        output / (result["published"]["source_ref"] + ".json")
    ).read_bytes() == conserved
    if damage == "missing_receipt":
        assert denied["setupNow"]["_meta"]["workspace"]["can_write"] is False
    else:
        assert denied["setupNow"]["isError"] is True


def test_conserved_model_proposal_requires_separate_complete_human_decision(author_run):
    env, output, reference, review, folder, engagement, run_id = author_run
    result = rpc_program(
        env,
        program(
            reference,
            review,
            REQUEST
            + STAGE
            + """
const published=payload(call('vera_workspace_aml_author_publish',publishArgs));
const view=payload(call('vera_workspace_view',{work_ref,source_ref:published.source_ref}));
const decisionScope={work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,review_ticket:view.review_ticket,expected_checkpoint:view.data.decision_checkpoint};
const draft=payload(call('vera_workspace_aml_draft_read',{work_ref,revision:view.revision,source_ref:published.source_ref}));
const dispositions=Object.fromEntries(draft.finding_items.map(item=>[item.id,'Unresolved pending evidence']));
const humanFields={reviewer_ref:'Fictional professional',reviewed_at:'2026-10-07',conclusion:'Request supporting mandate; issue remains open.',next_review_date:'',review_date_reason:'Await requested evidence'};
const saved=payload(call('vera_workspace_aml_draft_save',{...decisionScope,expected_draft_revision:draft.draft_revision,fields:humanFields,dispositions}));
const denied=call('vera_workspace_aml_decide',{...decisionScope,expected_draft_revision:saved.draft_revision,human_reviewed:false,idempotency_key:'unconfirmed-human'});
const decided=payload(call('vera_workspace_aml_decide',{...decisionScope,expected_draft_revision:saved.draft_revision,human_reviewed:true,idempotency_key:'confirmed-human'}));
const result={published,denied,decided,read};
""",
        ),
    )
    proposal = json.loads(
        (output / (result["published"]["source_ref"] + ".json")).read_text()
    )
    decision = json.loads(
        (output / (result["decided"]["source_ref"] + ".json")).read_text()
    )
    assert result["denied"]["isError"] is True
    assert proposal == result["read"]["record"]
    assert proposal["status"] == "draft_for_review"
    assert decision["status"] == "professional_decision_recorded"
    assert decision["review"]["findings"] == proposal["review"]["findings"]
    assert decision["review"]["professional_decision"]["finding_dispositions"] == {
        "F1": "Unresolved pending evidence"
    }
    assert (
        _load_customer_ledger().load_run(folder, engagement, run_id)["run"]["status"]
        == "running"
    )


def test_fresh_run_links_only_actual_sealed_aml_predecessor(author_run):
    env, output, reference, review, folder, engagement, run_id = author_run
    initial = rpc_program(
        env,
        program(
            reference,
            review,
            REQUEST
            + STAGE
            + "const result=payload(call('vera_workspace_aml_author_publish',publishArgs));",
        ),
    )
    ledger = _load_customer_ledger()
    previous = json.loads((output / (initial["source_ref"] + ".json")).read_text())
    # The fixture authors JSON directly; no actual model or research was executed.
    write_no_model_report(output, "aml-review", run_id)
    originals = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
    declarations = [
        {
            "artifact_id": f"fictional.{i}",
            "path": name,
            "purpose": "Retain exact fictional AML evidence for successor review.",
            "audience": "review",
            "media_type": "application/octet-stream",
        }
        for i, name in enumerate(sorted(originals))
    ]
    manifest = ledger.finalize_run(folder, engagement, run_id, declarations)[
        "artifact_manifest"
    ]
    artifact = next(
        r for r in manifest["artifacts"] if r["path"] == initial["source_ref"] + ".json"
    )
    original = ledger.load_run(folder, engagement, run_id)
    prepared = ledger.prepare_run(
        folder,
        original["run"]["client_id"],
        engagement,
        "aml-review",
        "test-version",
        input_ids=[original["input_manifest"]["inputs"][0]["binding_id"]],
        upstream_artifacts=[
            {"run_id": run_id, "artifact_id": artifact["artifact_id"], "role": "source"}
        ],
        new_run=True,
    )
    fresh_id = prepared["run"]["run_id"]
    ledger.start_run(folder, engagement, fresh_id)
    fresh = ledger.load_run(folder, engagement, fresh_id)
    roots = Path(fresh["run_root"]) / "inputs"
    inputs = fresh["input_manifest"]["inputs"]
    loan = next(r for r in inputs if r["kind"] == "import")
    updated = review_for(
        Path(fresh["run_root"]) / loan["execution_relative_path"], roots
    )
    prior = next(r for r in inputs if r["kind"] == "upstream_artifact")
    prior_path = Path(fresh["run_root"]) / prior["execution_relative_path"]
    updated["sources"].append(
        {
            "id": "S_previous",
            "path": prior_path.relative_to(roots).as_posix(),
            "title": "Exact sealed fictional AML predecessor",
            "sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
        }
    )
    updated["previous"] = {
        "source_id": "S_previous",
        "record_sha256": previous["record_sha256"],
    }
    updated["changes_since_previous"] = (
        "The supporting mandate remains absent; preserve the earlier uncertainty."
    )
    ref = "studio-" + "_".join(
        x.split("_", 1)[1] for x in (fresh["run"]["client_id"], engagement, fresh_id)
    )
    result = rpc_program(
        env,
        program(
            ref,
            updated,
            REQUEST
            + STAGE
            + "const result=payload(call('vera_workspace_aml_author_publish',publishArgs));",
        ),
    )
    record = json.loads(
        (Path(fresh["output_dir"]) / (result["source_ref"] + ".json")).read_text()
    )
    assert record["previous_record_sha256"] == previous["record_sha256"]
    assert (
        record["review"]["changes_since_previous"] == updated["changes_since_previous"]
    )
    assert {
        p.name: p.read_bytes() for p in output.iterdir() if p.is_file()
    } == originals
    assert ledger.load_run(folder, engagement, fresh_id)["run"]["status"] == "running"
