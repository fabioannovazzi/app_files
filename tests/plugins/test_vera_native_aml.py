"""Fictional AML records over the real archive and signed native MCP service."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_vera_aml_review import aml, review_for
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import ROOT, configure, workspace_module


@pytest.fixture
def aml_workspace(tmp_path, monkeypatch, request):
    """Persist a producer proposal against exact registered fictional evidence."""
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    ledger = _load_customer_ledger()
    folder = tmp_path / "Fictional AML client"
    folder.mkdir()
    client = "client_111111111111111111111111"
    ledger.create_client_manifest(folder, client)
    engagement = ledger.create_engagement(folder, client, "Fictional AML")
    source = tmp_path / "loan.txt"
    source.write_text("Fictional lender A; fictional payer B; EUR 200000.")
    imported = ledger.import_document(
        folder, client, engagement["engagement_id"], source, "source"
    )["receipt"]
    variant = getattr(request, "param", "one")
    selected = [imported["input_id"]]
    calculation_receipt = None
    if variant == "calculation":
        spec = importlib.util.spec_from_file_location(
            "native_aml_intake_test",
            ROOT / "plugins/new-client/scripts/initialize_case.py",
        )
        initializer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(initializer)
        intake = initializer.build_template(
            "FICTIONAL-CLIENT",
            client_type="company",
            engagement_kind="ongoing",
            assessment_date="2026-09-05",
        )
        path = tmp_path / "fictional-intake.json"
        path.write_text(json.dumps(intake))
        calculation_receipt = ledger.import_document(
            folder, client, engagement["engagement_id"], path, "support"
        )["receipt"]
        selected.append(calculation_receipt["input_id"])
    prepared = ledger.prepare_run(
        folder,
        client,
        engagement["engagement_id"],
        "aml-review",
        "test-version",
        input_ids=selected,
    )
    running = ledger.start_run(
        folder, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    binding = {
        "work_ref": "fictional-aml",
        "client_root": str(folder),
        "client_id": client,
        "engagement_id": engagement["engagement_id"],
        "run_id": prepared["run"]["run_id"],
        "workflow_id": "aml-review",
    }
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    module = workspace_module()
    loaded = module.load_binding(binding)
    inputs = Path(loaded["run_root"]) / "inputs"
    source_row = next(
        row
        for row in loaded["input_manifest"]["inputs"]
        if row["binding_id"] == imported["input_id"]
    )
    evidence = Path(loaded["run_root"]) / source_row["execution_relative_path"]
    review = review_for(evidence, inputs)
    if variant == "many":
        finding = review["findings"][0]
        review["findings"] = [
            {**copy.deepcopy(finding), "id": f"F{i}"} for i in range(1, 62)
        ]
    elif variant == "empty":
        review["findings"] = []
    elif variant == "long_id":
        review["findings"][0]["id"] = "F" * 500
    elif variant == "swiss":
        review.update(
            jurisdiction="CH-GE",
            jurisdiction_basis="Fictional Geneva mandate; applicability unresolved.",
            mandate_applicability={
                "status": "unresolved",
                "basis": "Fictional mandate requires professional qualification.",
                "citations": review["assessment_citations"],
            },
        )
    elif variant == "calculation":
        source_row = next(
            row
            for row in loaded["input_manifest"]["inputs"]
            if row["binding_id"] == calculation_receipt["input_id"]
        )
        path = Path(loaded["run_root"]) / source_row["execution_relative_path"]
        review["sources"].append(
            {
                "id": "S2",
                "path": path.relative_to(inputs).as_posix(),
                "title": "Fictional unresolved New Client intake",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
        review["calculation_source_id"] = "S2"
    record = aml.build_record(
        review,
        input_root=inputs,
        client_id=client,
        engagement_id=engagement["engagement_id"],
    )
    output = Path(running["output_dir"])
    path = aml.save_record(record, output)
    return env, output, binding, record, path.stem, module


VIEW = """
const view=payload(call('vera_workspace_view',{work_ref:'fictional-aml'}));
const authority=(view,stamp='')=>({work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,review_ticket:view.review_ticket,expected_checkpoint:view.data.decision_checkpoint,expected_draft_revision:stamp});
const fields={reviewer_ref:'fictional-professional',reviewed_at:'2026-09-05',conclusion:'Request supporting mandate; issue remains open.',next_review_date:'',review_date_reason:'Await requested evidence'};
"""
SAVE = (
    VIEW
    + """
const first=payload(call('vera_workspace_aml_draft_read',{work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref}));
const dispositions=Object.fromEntries(first.finding_items.map(item=>[item.id,'Unresolved pending evidence']));
const saved=payload(call('vera_workspace_aml_draft_save',{...authority(view,first.draft_revision),fields,dispositions}));
const args={...authority(view,saved.draft_revision),human_reviewed:true,idempotency_key:'fictional-decision'};
"""
)


@pytest.mark.parametrize(
    "aml_workspace", ["one", "empty", "long_id", "swiss"], indirect=True
)
def test_native_aml_appends_exact_decision_without_clearing_findings_or_completing_run(
    aml_workspace,
):
    env, output, binding, original, ref, module = aml_workspace
    original_bytes = (output / (ref + ".json")).read_bytes()
    result = rpc_program(
        env,
        SAVE
        + """
const decided=payload(call('vera_workspace_aml_decide',args));
const retry=payload(call('vera_workspace_aml_decide',args));
const after=payload(call('vera_workspace_view',{work_ref:view.work_ref,source_ref:decided.source_ref}));
const old=payload(call('vera_workspace_view',{work_ref:view.work_ref,source_ref:view.data.selection.source_ref,revision:view.revision}));
const files=payload(call('vera_workspace_outputs',{work_ref:view.work_ref,source_ref:decided.source_ref,revision:after.revision}));
const result={view,decided,retry,after,old,files};
""",
    )
    produced = json.loads(
        (output / (result["decided"]["source_ref"] + ".json")).read_bytes()
    )
    assert produced["review"]["findings"] == original["review"]["findings"]
    assert produced["proposal_sha256"] == original["proposal_sha256"]
    assert produced["review"]["professional_decision"]["next_review_date"] is None
    assert produced["status"] == "professional_decision_recorded"
    assert (
        "Unresolved pending evidence"
        in (output / (result["decided"]["source_ref"] + ".md")).read_text()
        or not original["review"]["findings"]
    )
    assert (output / (ref + ".json")).read_bytes() == original_bytes
    assert result["retry"] == result["decided"]
    assert result["decided"]["authenticated_signature"] is False
    assert result["decided"]["run_completed"] is False
    assert result["old"]["revision"] == result["view"]["revision"]
    assert module.load_binding(binding)["run"]["status"] == "running"
    assert result["files"]["status"] == "unfinalized_aml_review"
    assert {Path(row["path"]).name for row in result["files"]["outputs"]} == {
        result["decided"]["source_ref"] + ".json",
        result["decided"]["source_ref"] + ".md",
    }
    assert len(list(output.glob("aml-review-*.json"))) == 2


@pytest.mark.parametrize("aml_workspace", ["many"], indirect=True)
def test_native_aml_paginated_patches_preserve_every_off_page_disposition(
    aml_workspace,
):
    env, output, _, _, _, _ = aml_workspace
    result = rpc_program(
        env,
        VIEW
        + """
let stamp='';
for(let offset=0;offset<61;offset+=30){
 const page=payload(call('vera_workspace_aml_draft_read',{work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,offset}));
 const dispositions=Object.fromEntries(page.finding_items.map(item=>[item.id,'Pending evidence: '+item.id]));
 stamp=payload(call('vera_workspace_aml_draft_save',{...authority(view,stamp),fields,dispositions})).draft_revision;
}
const first=payload(call('vera_workspace_aml_draft_read',{work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref}));
const decided=payload(call('vera_workspace_aml_decide',{...authority(view,stamp),human_reviewed:true,idempotency_key:'fictional-paginated'}));
const result={first,decided};
""",
    )
    decision = json.loads(
        (output / (result["decided"]["source_ref"] + ".json")).read_bytes()
    )["review"]["professional_decision"]
    assert len(decision["finding_dispositions"]) == 61
    assert decision["finding_dispositions"]["F1"] == "Pending evidence: F1"
    assert decision["finding_dispositions"]["F61"] == "Pending evidence: F61"
    assert len(result["first"]["finding_items"]) == 30
    assert result["first"]["ready"] is True
    assert "human_reviewed" not in result["first"]


@pytest.mark.parametrize(
    "change",
    [
        "review_ticket:'forged.signature'",
        "revision:'f'.repeat(64)",
        "source_ref:'aml-review-'+ 'f'.repeat(64)",
        "expected_checkpoint:'f'.repeat(64)",
        "expected_draft_revision:'f'.repeat(64)",
        "human_reviewed:false",
    ],
)
def test_native_aml_invalid_authority_or_concurrent_stamp_cannot_append(
    aml_workspace, change
):
    env, output, _, _, _, _ = aml_workspace
    result = rpc_program(
        env,
        SAVE + f"const result=call('vera_workspace_aml_decide',{{...args,{change}}});",
    )
    assert result["isError"] is True
    assert len(list(output.glob("aml-review-*.json"))) == 1


@pytest.mark.parametrize("role", ["VIEWER", ""])
def test_native_aml_viewer_can_read_but_cannot_persist_decision_draft(
    aml_workspace, role
):
    env, output, _, _, _, _ = aml_workspace
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": role},
        VIEW
        + "const result={view,saved:call('vera_workspace_aml_draft_save',{...authority(view),fields,dispositions:{F1:'Pending'}})};",
    )
    assert result["view"]["data"]["can_decide"] is False
    assert result["saved"]["isError"] is True
    assert not (output.parent / ".native-workspace").exists()


def test_native_aml_invalid_review_date_is_correctable_before_append_intent(
    aml_workspace,
):
    env, output, _, _, _, _ = aml_workspace
    result = rpc_program(
        env,
        SAVE
        + """
const bad=payload(call('vera_workspace_aml_draft_save',{...authority(view,saved.draft_revision),fields:{reviewed_at:'bad-date'},dispositions:{}}));
const refused=call('vera_workspace_aml_decide',{...authority(view,bad.draft_revision),human_reviewed:true,idempotency_key:'invalid-date'});
const corrected=payload(call('vera_workspace_aml_draft_save',{...authority(view,bad.draft_revision),fields,dispositions:{}}));
const decided=payload(call('vera_workspace_aml_decide',{...authority(view,corrected.draft_revision),human_reviewed:true,idempotency_key:'corrected-date'}));
const result={refused,decided};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["decided"]["saved"] is True
    assert len(list((output.parent / ".native-workspace").glob("aml-request-*"))) == 1


def test_native_aml_model_read_is_one_exact_selected_finding_without_other_case_sections(
    aml_workspace,
):
    env, _, _, _, _, _ = aml_workspace
    result = rpc_program(
        env,
        VIEW
        + """
const finding=view.items.find(item=>item.group==='finding');
const exact={work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,item_id:finding.id};
const explain=call('vera_workspace_explain',exact);
const stale=call('vera_workspace_explain',{...exact,revision:'f'.repeat(64)});
const result={explain,stale};
""",
    )
    public = json.dumps(result["explain"]["structuredContent"])
    assert "Payer differs from contractual lender." in public
    assert "The supplied evidence does not yet explain" not in public
    assert "professional_decision" not in public
    assert result["stale"]["isError"] is True


@pytest.mark.parametrize("aml_workspace", ["calculation"], indirect=True)
def test_native_aml_preserves_existing_incomplete_new_client_calculation(aml_workspace):
    env, output, _, original, _, _ = aml_workspace
    result = rpc_program(
        env, SAVE + "const result=payload(call('vera_workspace_aml_decide',args));"
    )
    produced = json.loads((output / (result["source_ref"] + ".json")).read_bytes())
    assert original["calculation"]["status"] == "blocked_incomplete_scores"
    assert produced["calculation"] == original["calculation"]
    assert produced["calculation"]["professional_review_required"] is True


@pytest.mark.parametrize("mutation", ["memo", "record", "orphan", "hardlink"])
def test_native_aml_tampered_record_or_memo_is_refused(
    aml_workspace, mutation, tmp_path
):
    env, output, _, _, ref, _ = aml_workspace
    path = output / (ref + ".json")
    if mutation == "memo":
        path.with_suffix(".md").write_text("Changed memo")
    elif mutation == "record":
        record = json.loads(path.read_bytes())
        record["review"]["assessment"] = "Changed"
        path.write_text(json.dumps(record))
    elif mutation == "orphan":
        path.with_suffix(".md").unlink()
    else:
        os.link(path, tmp_path / "second-link")
    result = rpc_program(
        env, "const result=call('vera_workspace_view',{work_ref:'fictional-aml'});"
    )
    assert result["isError"] is True


def test_native_aml_interrupted_append_refuses_duplicate_and_retains_draft(
    aml_workspace, monkeypatch
):
    env, output, binding, _, ref, module = aml_workspace
    saved = rpc_program(env, SAVE + "const result={view,saved};")
    import native_aml

    original = native_aml.engine_call

    def interrupted(root, request):
        if request["operation"] == "decide":
            raise TimeoutError("Fictional interrupted append")
        return original(root, request)

    monkeypatch.setattr(native_aml, "engine_call", interrupted)
    args = {
        "work_ref": binding["work_ref"],
        "revision": saved["view"]["revision"],
        "source_ref": ref,
        "expected_checkpoint": saved["view"]["data"]["decision_checkpoint"],
        "expected_draft_revision": saved["saved"]["draft_revision"],
        "human_reviewed": True,
        "idempotency_key": "interrupted",
    }
    with pytest.raises(TimeoutError, match="interrupted"):
        module.dispatch("vera_workspace_aml_decide", args)
    with pytest.raises(ValueError, match="Interrupted AML append"):
        module.dispatch("vera_workspace_aml_decide", args)
    assert len(list(output.glob("aml-review-*.json"))) == 1
    assert len(list((output.parent / ".native-workspace").glob("aml-draft-*"))) == 1


def test_native_aml_generic_mutable_save_and_apply_are_refused(aml_workspace):
    _, output, binding, _, _, module = aml_workspace
    for tool in (
        "vera_workspace_save",
        "vera_workspace_apply",
        "vera_workspace_draft_save",
    ):
        with pytest.raises(ValueError, match="complete professional decision"):
            module.dispatch(tool, {"work_ref": binding["work_ref"]})
    assert len(list(output.glob("aml-review-*.json"))) == 1


def test_native_aml_population_change_requires_fresh_signed_scope_for_next_review(
    aml_workspace,
):
    env, output, _, original, ref, _ = aml_workspace
    result = rpc_program(
        env,
        SAVE
        + """
const firstDecision=payload(call('vera_workspace_aml_decide',args));
const stale=call('vera_workspace_aml_draft_save',{...authority(view),fields,dispositions});
const refreshed=payload(call('vera_workspace_view',{work_ref:view.work_ref,source_ref:view.data.selection.source_ref,revision:view.revision}));
const updated=payload(call('vera_workspace_aml_draft_save',{...authority(refreshed),fields:{...fields,conclusion:'Still awaiting mandate; explicitly reviewed again.'},dispositions}));
const second=payload(call('vera_workspace_aml_decide',{...authority(refreshed,updated.draft_revision),human_reviewed:true,idempotency_key:'second-reviewed-decision'}));
const result={first:firstDecision,stale,second};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["second"]["source_ref"] != result["first"]["source_ref"]
    assert json.loads((output / (ref + ".json")).read_bytes()) == original
    assert len(list(output.glob("aml-review-*.json"))) == 3


def test_native_aml_unknown_or_incomplete_finding_patch_cannot_register_decision(
    aml_workspace,
):
    env, output, _, _, _, _ = aml_workspace
    result = rpc_program(
        env,
        VIEW
        + """
const unknown=call('vera_workspace_aml_draft_save',{...authority(view),fields,dispositions:{foreign:'Unreviewed'}});
const partial=payload(call('vera_workspace_aml_draft_save',{...authority(view),fields,dispositions:{}}));
const incomplete=call('vera_workspace_aml_decide',{...authority(view,partial.draft_revision),human_reviewed:true,idempotency_key:'incomplete'});
const result={unknown,incomplete};
""",
    )
    assert result["unknown"]["isError"] is True
    assert result["incomplete"]["isError"] is True
    assert len(list(output.glob("aml-review-*.json"))) == 1


def test_native_aml_changed_duplicate_request_is_refused(aml_workspace):
    env, _, _, _, _, _ = aml_workspace
    result = rpc_program(
        env,
        SAVE
        + """
payload(call('vera_workspace_aml_decide',args));
const result=call('vera_workspace_aml_decide',{...args,expected_draft_revision:''});
""",
    )
    assert result["isError"] is True
    assert "different decision" in result["content"][0]["text"]


def test_native_aml_draft_tampering_refuses_recovery(aml_workspace):
    env, output, _, _, _, _ = aml_workspace
    rpc_program(env, SAVE + "const result=saved;")
    draft = next((output.parent / ".native-workspace").glob("aml-draft-*"))
    value = json.loads(draft.read_bytes())
    value["fields"]["conclusion"] = "Changed"
    draft.write_text(json.dumps(value))
    result = rpc_program(
        env,
        VIEW
        + "const result=call('vera_workspace_aml_draft_read',{work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref});",
    )
    assert result["isError"] is True
    assert "draft content changed" in result["content"][0]["text"]


def test_native_aml_retry_refuses_missing_authoritative_saved_record(aml_workspace):
    env, output, _, _, _, _ = aml_workspace
    result = rpc_program(
        env,
        SAVE
        + """
const fs=require('node:fs');
const decided=payload(call('vera_workspace_aml_decide',args));
fs.unlinkSync(process.env.FICTIONAL_OUTPUT+'/'+decided.source_ref+'.json');
fs.unlinkSync(process.env.FICTIONAL_OUTPUT+'/'+decided.source_ref+'.md');
const result=call('vera_workspace_aml_decide',args);
""".replace(
            "process.env.FICTIONAL_OUTPUT", json.dumps(str(output))
        ),
    )
    assert result["isError"] is True


def test_native_aml_oversized_finding_page_requires_specialist_route(aml_workspace):
    _, output, binding, record, ref, module = aml_workspace
    old = output / (ref + ".json")
    old.unlink()
    old.with_suffix(".md").unlink()
    review = record["review"]
    review["findings"][0]["observation"] = "X" * 2_000_001
    loaded = module.load_binding(binding)
    produced = aml.build_record(
        review,
        input_root=Path(loaded["run_root"]) / "inputs",
        client_id=binding["client_id"],
        engagement_id=binding["engagement_id"],
    )
    path = aml.save_record(produced, output)
    with pytest.raises(ValueError, match="page exceeds"):
        module.dispatch(
            "vera_workspace_aml_draft_read",
            {"work_ref": binding["work_ref"], "source_ref": path.stem},
        )


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_native_aml_fresh_extracted_package_replays_and_appends_maintained_record(
    aml_workspace, surface, tmp_path
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, output, _, original, _, _ = aml_workspace
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
        SAVE + "const result=payload(call('vera_workspace_aml_decide',args));",
        server=target / "mcp/workspace.cjs",
    )
    produced = json.loads((output / (result["source_ref"] + ".json")).read_bytes())
    assert produced["proposal_sha256"] == original["proposal_sha256"]
    assert produced["review"]["findings"] == original["review"]["findings"]
    assert result["run_completed"] is False
    assert (target / "scripts/native_aml_bridge.py").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_aml_bridge.py"
    ).read_bytes()
    assert (target / "modules/aml-review/scripts/aml_review.py").read_bytes() == (
        ROOT / "plugins/aml-review/scripts/aml_review.py"
    ).read_bytes()


def test_cowork_aml_fallback_cli_preserves_customer_folder_outputs_without_native_tools(
    aml_workspace, tmp_path
):
    """Exercise the maintained packaged specialist CLI independently of MCP Apps."""
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, output, binding, original, ref, module = aml_workspace
    builder = load_builder("build_claude_plugin_zip")
    _, packages = builder.load_configuration()
    vera = next(item for item in packages if item.plugin == "vera")
    target = tmp_path / "cowork-extracted"
    for name, content in builder.claude_package_entries(vera).items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    loaded = module.load_binding(binding)
    review = original["review"]
    review["professional_decision"] = {
        "proposal_sha256": original["proposal_sha256"],
        "reviewer_ref": "fictional-cowork-reviewer",
        "reviewed_at": "2026-09-05",
        "conclusion": "Request mandate; issue remains open.",
        "finding_dispositions": {"F1": "Unresolved pending evidence"},
        "next_review_date": None,
        "review_date_reason": "Await requested evidence",
    }
    review_input = output / "review_input.json"
    review_input.write_text(json.dumps(review))
    result = subprocess.run(
        [
            sys.executable,
            str(target / "modules/aml-review/scripts/aml_review.py"),
            "--client-engagement",
            str(loaded["context_path"]),
            "--review",
            str(review_input),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    successor = next(
        path for path in output.glob("aml-review-*.json") if path.stem != ref
    )
    record = json.loads(successor.read_bytes())
    assert record["status"] == "professional_decision_recorded"
    assert record["review"]["findings"] == original["review"]["findings"]
    assert "Unresolved pending evidence" in successor.with_suffix(".md").read_text()
    assert (output / (ref + ".json")).exists()
    assert module.load_binding(binding)["run"]["status"] == "running"
    assert not (output.parent / ".native-workspace").exists()
