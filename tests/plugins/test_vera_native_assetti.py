"""Fictional evidence-linked assetti reviews over real receipts and signed native MCP."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_adeguati_assetti import assetti, intelligent_case, review_for
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import ROOT, configure, workspace_module


@pytest.fixture
def assetti_workspace(tmp_path, monkeypatch, request):
    """Persist a producer proposal against exact registered fictional evidence."""
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    ledger = _load_customer_ledger()
    folder = tmp_path / "Fictional assetti client"
    folder.mkdir()
    client = "client_111111111111111111111111"
    ledger.create_client_manifest(folder, client)
    engagement = ledger.create_engagement(folder, client, "Fictional assetti")
    source = tmp_path / "reporting.txt"
    source.write_text("Monthly reporting policy.\nInventory: two quarterly reports.\n")
    imported = ledger.import_document(
        folder, client, engagement["engagement_id"], source, "source"
    )["receipt"]
    variant = getattr(request, "param", "one")
    selected = [imported["input_id"]]
    prepared = ledger.prepare_run(
        folder,
        client,
        engagement["engagement_id"],
        "adeguati-assetti",
        "test-version",
        input_ids=selected,
    )
    running = ledger.start_run(
        folder, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    binding = {
        "work_ref": "fictional-assetti",
        "client_root": str(folder),
        "client_id": client,
        "engagement_id": engagement["engagement_id"],
        "run_id": prepared["run"]["run_id"],
        "workflow_id": "adeguati-assetti",
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
    if variant != "historical":
        review["intelligent_review"] = intelligent_case(tmp_path)["intelligent_review"]
    if variant == "many":
        for section in ("observations", "findings", "actions"):
            original = review[section][0]
            review[section] = [
                {**copy.deepcopy(original), "id": original["id"][0] + str(i)}
                for i in range(1, 62)
            ]
        for section in ("coverage", "processes", "questions", "chronology"):
            original = review["intelligent_review"][section][0]
            review["intelligent_review"][section] = [
                {**copy.deepcopy(original), "id": section + str(i)}
                for i in range(1, 62)
            ]
    elif variant == "swiss":
        review.update(
            jurisdiction="CH-GE",
            jurisdiction_basis="Fictional Geneva entity; professional scope unresolved.",
        )
    elif variant == "empty":
        review["findings"] = []
        review["actions"] = []
        review["intelligent_review"]["action_ids"] = []
    record = assetti.build_record(
        review,
        input_root=inputs,
        client_id=client,
        engagement_id=engagement["engagement_id"],
    )
    output = Path(running["output_dir"])
    path = assetti.save_record(record, output)
    if variant == "prior":
        previous = ledger.import_document(
            folder, client, engagement["engagement_id"], path, "support"
        )["receipt"]
        prepared = ledger.prepare_run(
            folder,
            client,
            engagement["engagement_id"],
            "adeguati-assetti",
            "test-version",
            input_ids=[imported["input_id"], previous["input_id"]],
        )
        running = ledger.start_run(
            folder, engagement["engagement_id"], prepared["run"]["run_id"]
        )
        binding = {**binding, "run_id": prepared["run"]["run_id"]}
        env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
        loaded = module.load_binding(binding)
        inputs = Path(loaded["run_root"]) / "inputs"
        source_row = next(
            row
            for row in loaded["input_manifest"]["inputs"]
            if row["binding_id"] == previous["input_id"]
        )
        prior_path = Path(loaded["run_root"]) / source_row["execution_relative_path"]
        review = copy.deepcopy(record["review"])
        review.update(
            as_of="2026-09-08",
            previous={
                "source_id": "PREVIOUS",
                "record_sha256": record["record_sha256"],
            },
            changes_since_previous="No new operating evidence supplied.",
            prior_action_review={
                "A1": {
                    "status": "not_assessed",
                    "assessment": "Still awaiting reports and decision evidence.",
                    "citations": [],
                    "current_action_ids": [],
                }
            },
        )
        from tests.plugins.test_adeguati_assetti import source_row as receipt_row

        review["sources"].append(receipt_row(prior_path, inputs, "PREVIOUS"))
        record = assetti.build_record(
            review,
            input_root=inputs,
            client_id=client,
            engagement_id=engagement["engagement_id"],
        )
        output = Path(running["output_dir"])
        path = assetti.save_record(record, output)
    return env, output, binding, record, path.stem, module


VIEW = """
const view=payload(call('vera_workspace_view',{work_ref:'fictional-assetti'}));
const authority=(view,stamp='')=>({work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,review_ticket:view.review_ticket,expected_checkpoint:view.data.decision_checkpoint,expected_draft_revision:stamp});
const fields={reviewer_ref:'fictional-professional',reviewed_at:'2026-09-07',conclusion:'Request operating evidence; assessment remains limited.',next_review_date:'',review_date_reason:'Await evidence; no monitoring scheduled.'};
"""
SAVE = (
    VIEW
    + """
const first=payload(call('vera_workspace_assetti_draft_read',{work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref}));
const dispositions=Object.fromEntries(first.finding_items.map(item=>[item.id,'Open; proposed action accepted for investigation.']));
const saved=payload(call('vera_workspace_assetti_draft_save',{...authority(view,first.draft_revision),fields,dispositions}));
const args={...authority(view,saved.draft_revision),human_reviewed:true,idempotency_key:'fictional-decision'};
"""
)


@pytest.mark.parametrize(
    "assetti_workspace", ["one", "historical", "swiss", "empty"], indirect=True
)
def test_native_assetti_decision_retains_proposal_and_does_not_record_adoption(
    assetti_workspace,
):
    env, output, binding, original, ref, module = assetti_workspace
    original_bytes = (output / (ref + ".json")).read_bytes()
    result = rpc_program(
        env,
        SAVE
        + """
const decided=payload(call('vera_workspace_assetti_decide',args));
const retry=payload(call('vera_workspace_assetti_decide',args));
const after=payload(call('vera_workspace_view',{work_ref:view.work_ref,source_ref:decided.source_ref}));
const old=payload(call('vera_workspace_view',{work_ref:view.work_ref,source_ref:view.data.selection.source_ref,revision:view.revision}));
const files=payload(call('vera_workspace_outputs',{work_ref:view.work_ref,source_ref:decided.source_ref,revision:after.revision}));
const result={view,decided,retry,after,old,files};
""",
    )
    produced = json.loads(
        (output / (result["decided"]["source_ref"] + ".json")).read_bytes()
    )
    assert {
        k: v for k, v in produced["review"].items() if k != "professional_decision"
    } == original["review"]
    assert produced["proposal_sha256"] == original["proposal_sha256"]
    assert result["retry"] == result["decided"]
    assert result["decided"]["run_completed"] is False
    assert result["decided"]["authenticated_signature"] is False
    assert result["files"]["status"] == "unfinalized_assetti_review"
    assert (output / (ref + ".json")).read_bytes() == original_bytes
    assert module.load_binding(binding)["run"]["status"] == "running"
    assert result["view"]["kind"] == "assetti"
    assert result["view"]["data"]["intelligent_review_present"] == (
        "intelligent_review" in original["review"]
    )
    assert (
        "Request operating evidence"
        in (output / (result["decided"]["source_ref"] + ".md")).read_text()
    )


def test_native_assetti_selected_process_links_observation_and_exact_citation(
    assetti_workspace,
):
    env, _, _, original, _, _ = assetti_workspace
    result = rpc_program(
        env,
        VIEW
        + """
const item=view.items.find(row=>row.group==='processes');
const selected=payload(call('vera_workspace_view',{work_ref:view.work_ref,source_ref:view.data.selection.source_ref,revision:view.revision,item_id:item.id}));
const explanation=call('vera_workspace_explain',{work_ref:view.work_ref,source_ref:view.data.selection.source_ref,revision:view.revision,item_id:item.id}).structuredContent;
const result={selected,explanation};
""",
    )
    selection = result["selected"]["selection"]
    assert selection["data"] == original["review"]["intelligent_review"]["processes"][0]
    assert selection["linked_observations"] == original["review"]["observations"]
    assert selection["sources"] == original["review"]["sources"]
    assert result["explanation"]["untrusted_evidence"]["selected_record"] == selection
    assert (
        "operating effectiveness"
        in result["explanation"]["untrusted_evidence"]["professional_boundary"]
    )


@pytest.mark.parametrize("assetti_workspace", ["many"], indirect=True)
def test_native_assetti_paginated_sections_and_all_finding_decisions(assetti_workspace):
    env, output, _, original, _, _ = assetti_workspace
    result = rpc_program(
        env,
        VIEW
        + """
const pages=[];
for(let offset=0;offset<view.total;offset+=30) pages.push(payload(call('vera_workspace_view',{work_ref:view.work_ref,source_ref:view.data.selection.source_ref,revision:view.revision,offset})));
let stamp='';
for(let offset=0;offset<61;offset+=30){
 const page=payload(call('vera_workspace_assetti_draft_read',{work_ref:view.work_ref,source_ref:view.data.selection.source_ref,revision:view.revision,offset}));
 const patch=Object.fromEntries(page.finding_items.map(row=>[row.id,'Pending operating evidence']));
 stamp=payload(call('vera_workspace_assetti_draft_save',{...authority(view,stamp),fields,dispositions:patch})).draft_revision;
}
const decided=payload(call('vera_workspace_assetti_decide',{...authority(view,stamp),human_reviewed:true,idempotency_key:'all-findings'}));
const result={pages,decided};
""",
    )
    items = [item for page in result["pages"] for item in page["items"]]
    assert len(items) == result["pages"][0]["total"]
    assert len({item["id"] for item in items}) == len(items)
    for group in (
        "observation",
        "finding",
        "action",
        "coverage",
        "processes",
        "questions",
        "chronology",
    ):
        assert sum(item["group"] == group for item in items) == 61
    produced = json.loads(
        (output / (result["decided"]["source_ref"] + ".json")).read_bytes()
    )
    assert (
        len(produced["review"]["professional_decision"]["finding_dispositions"]) == 61
    )
    assert produced["review"]["actions"] == original["review"]["actions"]


@pytest.mark.parametrize(
    "tool",
    [
        "vera_workspace_save",
        "vera_workspace_apply",
        "vera_workspace_draft_save",
        "vera_workspace_aml_setup",
    ],
)
def test_native_assetti_refuses_generic_or_foreign_workflow_mutations(
    assetti_workspace, tool
):
    env, _, _, _, _, _ = assetti_workspace
    result = rpc_program(
        env,
        VIEW
        + f"const result=call('{tool}',{{...authority(view),human_reviewed:true,idempotency_key:'wrong',fields:{{}}}});",
    )
    assert result["isError"] is True


def test_native_assetti_earlier_review_date_is_rejected_before_append_intent(
    assetti_workspace,
):
    env, output, _, _, _, _ = assetti_workspace
    result = rpc_program(
        env,
        SAVE
        + """
const changed=payload(call('vera_workspace_assetti_draft_save',{...authority(view,saved.draft_revision),fields:{reviewed_at:'2026-09-06'},dispositions:{}}));
const result=call('vera_workspace_assetti_decide',{...args,expected_draft_revision:changed.draft_revision});
""",
    )
    assert result["isError"] is True
    assert len(list(output.glob("adeguati-assetti-*.json"))) == 1
    assert not list(
        (output.parent / ".native-workspace").glob("assetti-request-*.json")
    )


@pytest.mark.parametrize("damage", ["memo", "source", "identity", "linked_record"])
def test_native_assetti_refuses_unreplayable_or_foreign_source_records(
    assetti_workspace, damage
):
    env, output, _, original, ref, module = assetti_workspace
    path = output / (ref + ".json")
    if damage == "memo":
        path.with_suffix(".md").write_text("Changed fictional memo")
    elif damage == "source":
        loaded = module.load_binding(assetti_workspace[2])
        source = (
            Path(loaded["run_root"])
            / "inputs"
            / original["review"]["sources"][0]["path"]
        )
        source.write_text("Changed registered source")
    elif damage == "identity":
        original["client_id"] = "client_other"
        path.write_text(json.dumps(original))
    else:
        external = output.parent / "linked-record.json"
        path.rename(external)
        path.symlink_to(external)
    result = rpc_program(
        env, "const result=call('vera_workspace_view',{work_ref:'fictional-assetti'});"
    )
    assert result["isError"] is True
    assert len(list(output.glob("adeguati-assetti-*.json"))) == 1


def test_native_assetti_refuses_forged_and_concurrent_private_patch(
    assetti_workspace,
):
    env, _, _, _, _, _ = assetti_workspace
    result = rpc_program(
        env,
        SAVE
        + """
const concurrent=call('vera_workspace_assetti_draft_save',{...authority(view),fields:{conclusion:'Overwritten'},dispositions:{}});
const forged=call('vera_workspace_assetti_draft_save',{...authority(view,saved.draft_revision),review_ticket:'forged',fields:{},dispositions:{}});
const incomplete=call('vera_workspace_assetti_draft_save',{...authority(view,saved.draft_revision),fields:{action_status:'completed'},dispositions:{}});
const result={concurrent,forged,incomplete,saved};
""",
    )
    assert all(
        result[key]["isError"] is True for key in ("concurrent", "forged", "incomplete")
    )


def test_native_assetti_viewer_cannot_store_or_register_decision(assetti_workspace):
    env, output, _, _, _, _ = assetti_workspace
    env = {**env, "VERA_WORKSPACE_ROLES": "VIEWER"}
    result = rpc_program(
        env,
        VIEW
        + "const result=call('vera_workspace_assetti_draft_save',{...authority(view),fields,dispositions:{F1:'Unresolved'}});",
    )
    assert result["isError"] is True
    assert len(list(output.glob("adeguati-assetti-*.json"))) == 1


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_native_assetti_fresh_extracted_package_replays_and_appends_maintained_record(
    assetti_workspace, surface, tmp_path
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, output, _, original, _, _ = assetti_workspace
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
        SAVE + "const result=payload(call('vera_workspace_assetti_decide',args));",
        server=target / "mcp/workspace.cjs",
    )
    produced = json.loads((output / (result["source_ref"] + ".json")).read_bytes())
    assert produced["proposal_sha256"] == original["proposal_sha256"]
    assert produced["review"]["findings"] == original["review"]["findings"]
    assert result["run_completed"] is False
    assert (target / "scripts/native_assetti.py").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_assetti.py"
    ).read_bytes()
    assert (target / "scripts/native_aml_bridge.py").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_aml_bridge.py"
    ).read_bytes()
    assert (
        target / "modules/adeguati-assetti/scripts/assetti_review.py"
    ).read_bytes() == (
        ROOT / "plugins/adeguati-assetti/scripts/assetti_review.py"
    ).read_bytes()


def test_cowork_assetti_fallback_cli_preserves_customer_folder_outputs_without_native_tools(
    assetti_workspace, tmp_path
):
    """Exercise the maintained packaged specialist CLI independently of MCP Apps."""
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, output, binding, original, ref, module = assetti_workspace
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
        "reviewed_at": "2026-09-07",
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
            str(target / "modules/adeguati-assetti/scripts/assetti_review.py"),
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
        path for path in output.glob("adeguati-assetti-*.json") if path.stem != ref
    )
    record = json.loads(successor.read_bytes())
    assert record["status"] == "professional_decision_recorded"
    assert record["review"]["findings"] == original["review"]["findings"]
    assert "Unresolved pending evidence" in successor.with_suffix(".md").read_text()
    assert (output / (ref + ".json")).exists()
    assert module.load_binding(binding)["run"]["status"] == "running"
    assert not (output.parent / ".native-workspace").exists()


def test_native_assetti_population_change_requires_fresh_signed_scope_for_next_review(
    assetti_workspace,
):
    env, output, _, original, ref, _ = assetti_workspace
    result = rpc_program(
        env,
        SAVE
        + """
const firstDecision=payload(call('vera_workspace_assetti_decide',args));
const stale=call('vera_workspace_assetti_draft_save',{...authority(view),fields,dispositions});
const refreshed=payload(call('vera_workspace_view',{work_ref:view.work_ref,source_ref:view.data.selection.source_ref,revision:view.revision}));
const updated=payload(call('vera_workspace_assetti_draft_save',{...authority(refreshed),fields:{...fields,conclusion:'Still awaiting mandate; explicitly reviewed again.'},dispositions}));
const second=payload(call('vera_workspace_assetti_decide',{...authority(refreshed,updated.draft_revision),human_reviewed:true,idempotency_key:'second-reviewed-decision'}));
const result={first:firstDecision,stale,second};
""",
    )
    assert result["stale"]["isError"] is True
    assert result["second"]["source_ref"] != result["first"]["source_ref"]
    assert json.loads((output / (ref + ".json")).read_bytes()) == original
    assert len(list(output.glob("adeguati-assetti-*.json"))) == 3


def test_native_assetti_interrupted_append_refuses_duplicate_and_retains_draft(
    assetti_workspace, monkeypatch
):
    env, output, binding, _, ref, module = assetti_workspace
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
        module.dispatch("vera_workspace_assetti_decide", args)
    with pytest.raises(ValueError, match="Interrupted Adeguati assetti append"):
        module.dispatch("vera_workspace_assetti_decide", args)
    assert len(list(output.glob("adeguati-assetti-*.json"))) == 1
    assert len(list((output.parent / ".native-workspace").glob("assetti-draft-*"))) == 1


@pytest.mark.parametrize("assetti_workspace", ["prior"], indirect=True)
def test_native_assetti_follow_up_preserves_prior_action_unknown_state(
    assetti_workspace,
):
    env, output, _, original, _, _ = assetti_workspace
    result = rpc_program(
        env,
        SAVE.replace("2026-09-07", "2026-09-08")
        + """
const item=view.items.find(row=>row.group==='prior-action');
const selected=payload(call('vera_workspace_view',{work_ref:view.work_ref,source_ref:view.data.selection.source_ref,revision:view.revision,item_id:item.id}));
const decided=payload(call('vera_workspace_assetti_decide',args));
const result={selected,decided};
""",
    )
    assert result["selected"]["selection"]["data"]["status"] == "not_assessed"
    produced = json.loads(
        (output / (result["decided"]["source_ref"] + ".json")).read_bytes()
    )
    assert (
        produced["review"]["prior_action_review"]
        == original["review"]["prior_action_review"]
    )
    assert produced["previous_record_sha256"] == original["previous_record_sha256"]
    assert produced["review"]["actions"][0]["status"] == "proposed"
