"""Initial assetti proposals over actual owned receipts, with fictional evidence."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.plugins.test_adeguati_assetti import (
    assetti,
    intelligent_case,
    review_for,
    source_row,
)
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_aml_authoring import REQUEST, STAGE, program
from tests.plugins.test_vera_native_archive_closure import write_no_model_report
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import registry_workspace

__all__ = []


@pytest.fixture
def initial_assetti(registry_workspace, tmp_path):
    env, studio, _, _, client, engagement = registry_workspace
    env.update(
        VERA_WORKSPACE_ACTOR_ID="fictional-reviewer",
        VERA_WORKSPACE_TENANT_ID="fictional-studio",
        VERA_WORKSPACE_ROLES="REVIEWER",
    )
    folder = studio / "Cliente Beta"
    ledger = _load_customer_ledger()
    source = tmp_path / "fictional-reporting.txt"
    source.write_text(
        "Fictional monthly policy; two quarterly reports retained. Operation unresolved."
    )
    receipt = ledger.import_document(folder, client, engagement, source, "source")[
        "receipt"
    ]
    prepared = ledger.prepare_run(
        folder,
        client,
        engagement,
        "adeguati-assetti",
        "test-version",
        input_ids=[receipt["input_id"]],
    )
    ledger.start_run(folder, engagement, prepared["run"]["run_id"])
    loaded = ledger.load_run(folder, engagement, prepared["run"]["run_id"])
    evidence = (
        Path(loaded["run_root"])
        / loaded["input_manifest"]["inputs"][0]["execution_relative_path"]
    )
    review = review_for(evidence, Path(loaded["run_root"]) / "inputs")
    review["intelligent_review"] = intelligent_case(tmp_path)["intelligent_review"]
    ref = "studio-" + "_".join(
        value.split("_", 1)[1]
        for value in (client, engagement, prepared["run"]["run_id"])
    )
    return env, Path(loaded["output_dir"]), ref, review, loaded, folder


def assetti_program(reference: str, review: dict, body: str) -> str:
    """Share only the transport fixture; all semantics use the assetti producer."""
    return (
        program(reference, review, body)
        .replace("vera_workspace_aml_author_", "vera_workspace_assetti_author_")
        .replace(
            "Fictional review of the documented loan: preserve unresolved explanations.",
            "Fictional assessment of reporting operation: preserve unresolved evidence.",
        )
    )


@pytest.mark.parametrize("jurisdiction,language", [("IT", "fr"), ("CH-GE", "it")])
def test_initial_assetti_complete_intelligence_conserved_without_professional_decision(
    initial_assetti, jurisdiction, language
):
    env, output, ref, review, loaded, folder = initial_assetti
    review.update(
        jurisdiction=jurisdiction,
        language=language,
        jurisdiction_basis="Fictional explicit governing scope, independently of narrative language.",
    )
    result = rpc_program(
        env,
        assetti_program(
            ref,
            review,
            REQUEST
            + STAGE
            + """
const before=payload(call('vera_workspace_assetti_setup',{work_ref}));
const published=payload(call('vera_workspace_assetti_author_publish',publishArgs));
const retry=payload(call('vera_workspace_assetti_author_publish',publishArgs));
const view=payload(call('vera_workspace_view',{work_ref,source_ref:published.source_ref}));
const result={setup,context,read,before,published,retry,view};
""",
        ),
    )
    expected = assetti.build_record(
        review,
        input_root=Path(loaded["run_root"]) / "inputs",
        client_id=loaded["run"]["client_id"],
        engagement_id=loaded["run"]["engagement_id"],
    )
    assert result["setup"]["draft"]["fields"] == {"question": "", "input_ids": []}
    assert result["before"]["total"] == 0
    assert result["read"]["record"] == expected
    assert result["read"]["memo"] == assetti.render_memo(expected)
    assert result["published"]["status"] == "draft_for_review"
    assert result["published"]["professional_approval"] is False
    assert result["retry"] == result["published"]
    assert result["view"]["kind"] == "assetti"
    assert "intelligent-assessment" in result["context"]["instructions"]
    assert result["context"]["workflow"] == "adeguati-assetti"
    assert (
        json.loads((output / (result["published"]["source_ref"] + ".json")).read_text())
        == expected
    )
    assert (
        _load_customer_ledger().load_run(
            folder,
            loaded["run"]["engagement_id"],
            loaded["run"]["run_id"],
        )["run"]["status"]
        == "running"
    )


@pytest.mark.parametrize(
    "change",
    [
        "missing_intelligence",
        "professional_decision",
        "changed_source",
        "unselected_source",
        "foreign_predecessor",
        "broken_links",
    ],
)
def test_assetti_stage_invalid_proposal_refuses_without_official_outputs(
    initial_assetti, change
):
    env, output, ref, original, _, _ = initial_assetti
    review = copy.deepcopy(original)
    if change == "missing_intelligence":
        review.pop("intelligent_review")
    elif change == "professional_decision":
        review["professional_decision"] = {"decision": "accepted"}
    elif change == "changed_source":
        review["sources"][0]["sha256"] = "0" * 64
    elif change == "unselected_source":
        review["sources"][0]["path"] = "foreign.txt"
    elif change == "foreign_predecessor":
        review["previous"] = {
            "source_id": review["sources"][0]["id"],
            "record_sha256": "0" * 64,
        }
    else:
        review["intelligent_review"]["coverage"][0]["observation_ids"] = [
            "missing-observation"
        ]
    result = rpc_program(
        env,
        assetti_program(
            ref,
            review,
            REQUEST
            + "const refused=call('vera_workspace_aml_author_stage',{...exact,expected_stage_revision:context.stage_revision,review,idempotency_key:'invalid'});const result={refused};",
        ),
    )
    assert result["refused"]["isError"] is True
    assert not list(output.iterdir())


@pytest.mark.parametrize(
    "guard", ["no_confirmation", "forged_ticket", "viewer", "foreign_tool"]
)
def test_assetti_initial_mandate_requires_explicit_own_reviewer_selection(
    initial_assetti, guard
):
    env, output, ref, review, _, _ = initial_assetti
    if guard == "viewer":
        env["VERA_WORKSPACE_ROLES"] = "VIEWER"
    operation = (
        "requestArgs.confirmed=false;"
        if guard == "no_confirmation"
        else "requestArgs.review_ticket='forged';" if guard == "forged_ticket" else ""
    )
    tool = (
        "vera_workspace_assetti_author_request"
        if guard != "foreign_tool"
        else "vera_workspace_aml_author_request"
    )
    body = assetti_program(
        ref,
        review,
        operation
        + f"const refused=call({json.dumps(tool)},requestArgs);const result={{refused}};",
    )
    if guard == "foreign_tool":
        body = body.replace(
            'call("vera_workspace_assetti_author_request",requestArgs)',
            'call("vera_workspace_aml_author_request",requestArgs)',
        )
    result = rpc_program(env, body)
    assert result["refused"]["isError"] is True
    assert not list(output.iterdir())


@pytest.mark.parametrize(
    "damage", ["orphan", "pending", "missing_stage_receipt", "changed_stage"]
)
def test_assetti_uncertain_staging_blocks_authoring_and_archive_closure(
    initial_assetti, damage
):
    env, output, ref, review, loaded, _ = initial_assetti
    staged = rpc_program(
        env,
        assetti_program(
            ref, review, REQUEST + STAGE + "const result={requested,staged};"
        ),
    )
    base = (
        next((output.parent / ".native-workspace").glob("assetti-authoring-*"))
        / staged["requested"]["grant_ref"]
    )
    if damage == "orphan":
        (base / ("proposal-" + "0" * 64)).mkdir()
    elif damage == "pending":
        (base / "publish-request-interrupted.json").write_text("{}")
    elif damage == "missing_stage_receipt":
        next(base.glob("stage-request-*.json")).unlink()
    else:
        (base / staged["staged"]["stage_ref"] / "memo.md").write_text(
            "Altered fixture memo"
        )
    selected = {
        key: loaded["run"][key] for key in ("client_id", "engagement_id", "run_id")
    }
    result = rpc_program(
        env,
        f"const setupNow=call('vera_workspace_assetti_author_setup',{{work_ref:{json.dumps(ref)}}});const closure=call('vera_workspace_archive_closure',{json.dumps(selected)});const result={{setupNow,closure}};",
    )
    assert result["closure"]["isError"] is True
    if damage == "changed_stage":
        assert result["setupNow"]["isError"] is True
    else:
        assert result["setupNow"]["_meta"]["workspace"]["can_write"] is False
    assert not list(output.iterdir())


def test_assetti_literal_partial_draft_reopens_and_stale_panel_cannot_replace_it(
    initial_assetti,
):
    env, output, ref, review, _, _ = initial_assetti
    result = rpc_program(
        env,
        assetti_program(
            ref,
            review,
            """
const literal={question:'Domanda incompleta: quale evidenza manca?  ',input_ids:[]};
const args={work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:'',fields:literal};
const saved=payload(call('vera_workspace_aml_author_draft_store',args));
const reopened=payload(call('vera_workspace_aml_author_setup',{work_ref}));
const concurrent=call('vera_workspace_aml_author_draft_store',{...args,fields:{question:'Replacement',input_ids:[]}});
const result={saved,reopened,concurrent};
""",
        ),
    )
    assert result["reopened"]["draft"]["fields"] == {
        "question": "Domanda incompleta: quale evidenza manca?  ",
        "input_ids": [],
    }
    assert result["concurrent"]["isError"] is True
    assert result["reopened"]["mandates"] == []
    assert not list(output.iterdir())


@pytest.mark.parametrize("change", ["other_actor", "source_bytes"])
def test_assetti_exact_mandate_refuses_changed_source_or_foreign_actor(
    initial_assetti, change
):
    env, output, ref, review, loaded, _ = initial_assetti
    result = rpc_program(
        env, assetti_program(ref, review, REQUEST + "const result={requested,context};")
    )
    if change == "other_actor":
        env["VERA_WORKSPACE_ACTOR_ID"] = "other-fictional-reviewer"
    else:
        Path(result["context"]["sources"][0]["path"]).write_text(
            "Changed fictional bytes"
        )
    refused = rpc_program(
        env,
        f"const result=call('vera_workspace_assetti_author_context',{{work_ref:{json.dumps(ref)},grant_ref:{json.dumps(result['requested']['grant_ref'])}}});",
    )
    assert refused["isError"] is True
    assert not list(output.iterdir())


def test_initial_assetti_conservation_then_separate_human_review_retains_unknowns(
    initial_assetti,
):
    env, output, ref, review, loaded, folder = initial_assetti
    result = rpc_program(
        env,
        assetti_program(
            ref,
            review,
            REQUEST
            + STAGE
            + """
const published=payload(call('vera_workspace_assetti_author_publish',publishArgs));
const view=payload(call('vera_workspace_view',{work_ref,source_ref:published.source_ref}));
const decisionScope={work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,review_ticket:view.review_ticket,expected_checkpoint:view.data.decision_checkpoint};
const draft=payload(call('vera_workspace_assetti_draft_read',{work_ref,revision:view.revision,source_ref:published.source_ref}));
const dispositions=Object.fromEntries(draft.finding_items.map(item=>[item.id,'Unresolved pending operating evidence']));
const humanFields={reviewer_ref:'Fictional professional',reviewed_at:'2026-10-07',conclusion:'Request actual report use and decision evidence.',next_review_date:'',review_date_reason:'Await requested operating evidence'};
const saved=payload(call('vera_workspace_assetti_draft_save',{...decisionScope,expected_draft_revision:draft.draft_revision,fields:humanFields,dispositions}));
const denied=call('vera_workspace_assetti_decide',{...decisionScope,expected_draft_revision:saved.draft_revision,human_reviewed:false,idempotency_key:'unconfirmed-human'});
const decided=payload(call('vera_workspace_assetti_decide',{...decisionScope,expected_draft_revision:saved.draft_revision,human_reviewed:true,idempotency_key:'confirmed-human'}));
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
    preserved = dict(decision["review"])
    preserved.pop("professional_decision")
    assert preserved == proposal["review"]
    assert decision["review"]["professional_decision"]["finding_dispositions"] == {
        "F1": "Unresolved pending operating evidence"
    }
    assert (
        _load_customer_ledger().load_run(
            folder, loaded["run"]["engagement_id"], loaded["run"]["run_id"]
        )["run"]["status"]
        == "running"
    )


def test_fresh_assetti_authoring_uses_exact_sealed_predecessor_and_all_prior_actions(
    initial_assetti,
):
    env, output, ref, review, loaded, folder = initial_assetti
    initial = rpc_program(
        env,
        assetti_program(
            ref,
            review,
            REQUEST
            + STAGE
            + "const result=payload(call('vera_workspace_assetti_author_publish',publishArgs));",
        ),
    )
    previous = json.loads((output / (initial["source_ref"] + ".json")).read_text())
    ledger = _load_customer_ledger()
    run_id, engagement = loaded["run"]["run_id"], loaded["run"]["engagement_id"]
    # Fictional JSON was authored by the fixture; no model/research was executed.
    write_no_model_report(output, "adeguati-assetti", run_id)
    originals = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
    declarations = [
        {
            "artifact_id": f"fictional.{i}",
            "path": name,
            "purpose": "Exact fictional assetti predecessor retained for follow-up.",
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
    prepared = ledger.prepare_run(
        folder,
        loaded["run"]["client_id"],
        engagement,
        "adeguati-assetti",
        "test-version",
        input_ids=[loaded["input_manifest"]["inputs"][0]["binding_id"]],
        upstream_artifacts=[
            {"run_id": run_id, "artifact_id": artifact["artifact_id"], "role": "source"}
        ],
        new_run=True,
    )
    fresh_id = prepared["run"]["run_id"]
    ledger.start_run(folder, engagement, fresh_id)
    fresh = ledger.load_run(folder, engagement, fresh_id)
    roots = Path(fresh["run_root"]) / "inputs"
    current = next(
        r for r in fresh["input_manifest"]["inputs"] if r["kind"] == "import"
    )
    prior = next(
        r for r in fresh["input_manifest"]["inputs"] if r["kind"] == "upstream_artifact"
    )
    updated = copy.deepcopy(review)
    updated["sources"] = [
        source_row(
            Path(fresh["run_root"]) / current["execution_relative_path"], roots, "S1"
        ),
        source_row(
            Path(fresh["run_root"]) / prior["execution_relative_path"],
            roots,
            "PREVIOUS",
        ),
    ]
    updated.update(
        as_of="2026-10-07",
        previous={"source_id": "PREVIOUS", "record_sha256": previous["record_sha256"]},
        changes_since_previous="No new operating evidence supplied.",
        prior_action_review={
            "A1": {
                "status": "not_assessed",
                "assessment": "Still awaiting reports and actual decision evidence.",
                "citations": [],
                "current_action_ids": [],
            }
        },
    )
    fresh_ref = "studio-" + "_".join(
        x.split("_", 1)[1] for x in (fresh["run"]["client_id"], engagement, fresh_id)
    )
    result = rpc_program(
        env,
        assetti_program(
            fresh_ref,
            updated,
            REQUEST
            + STAGE
            + "const result=payload(call('vera_workspace_assetti_author_publish',publishArgs));",
        ),
    )
    record = json.loads(
        (Path(fresh["output_dir"]) / (result["source_ref"] + ".json")).read_text()
    )
    assert record["previous_record_sha256"] == previous["record_sha256"]
    assert record["review"]["prior_action_review"]["A1"]["status"] == "not_assessed"
    assert record["review"]["intelligent_review"] == updated["intelligent_review"]
    assert {
        p.name: p.read_bytes() for p in output.iterdir() if p.is_file()
    } == originals


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_extracted_assetti_initial_proposal_uses_complete_maintained_producer(
    initial_assetti,
    surface,
    tmp_path,
):
    from tests.plugins.test_packaged_mcp_startup import ROOT, load_builder

    env, output, ref, review, loaded, _ = initial_assetti
    builder = load_builder(
        "build_codex_plugin_zip" if surface == "codex" else "build_claude_plugin_zip"
    )
    if surface == "codex":
        vera = next(item for item in builder.load_bundles() if item.name == "vera")
        entries = builder.expected_zip_entries(vera)
        prefix = vera.package_root + "/plugins/vera/"
    else:
        _, packages = builder.load_configuration()
        vera = next(item for item in packages if item.plugin == "vera")
        entries = builder.claude_package_entries(vera)
        prefix = ""
    target = tmp_path / "extracted"
    for name, content in entries.items():
        if name.startswith(prefix):
            path = target / name[len(prefix) :]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    result = rpc_program(
        env,
        assetti_program(
            ref,
            review,
            REQUEST
            + STAGE
            + "const result=payload(call('vera_workspace_assetti_author_publish',publishArgs));",
        ),
        server=target / "mcp/workspace.cjs",
    )
    produced = json.loads((output / (result["source_ref"] + ".json")).read_text())
    expected = assetti.build_record(
        review,
        input_root=Path(loaded["run_root"]) / "inputs",
        client_id=loaded["run"]["client_id"],
        engagement_id=loaded["run"]["engagement_id"],
    )
    assert produced == expected
    assert (output / (result["source_ref"] + ".md")).read_text() == assetti.render_memo(
        expected
    )
    assert (
        target / "modules/adeguati-assetti/scripts/assetti_review.py"
    ).read_bytes() == (
        ROOT / "plugins/adeguati-assetti/scripts/assetti_review.py"
    ).read_bytes()
    assert (target / "scripts/native_aml_authoring.py").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_aml_authoring.py"
    ).read_bytes()


def test_assetti_initial_mandate_without_selected_sources_refuses_no_implicit_access(
    initial_assetti,
):
    env, output, ref, review, _, _ = initial_assetti
    body = (
        "fields.input_ids=[];fields.question='Fictional first interview with no selected documents.';"
        "const refused=call('vera_workspace_assetti_author_request',requestArgs);"
        "const result={refused};"
    )
    result = rpc_program(env, assetti_program(ref, review, body))
    assert result["refused"]["isError"] is True
    assert "Choose distinct actual" in result["refused"]["content"][0]["text"]
    assert not list(output.iterdir())
