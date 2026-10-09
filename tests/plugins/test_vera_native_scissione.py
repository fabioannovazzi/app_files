"""Fictional immutable Scissione records through real Archive and signed native MCP."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_scissione_archive import execute, workspace
from tests.plugins.test_scissione_guidata import row
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import ROOT, configure, workspace_module


@pytest.fixture
def scissione_workspace(tmp_path, monkeypatch, request):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    work = workspace(tmp_path)
    variant = getattr(request, "param", "one")
    data = work["case"]
    if variant == "unknown":
        row(data, "contracts")["status"] = "unknown"
    elif variant == "unsupported":
        row(data, "route")["data"]["scope"]["beneficiary"] = "existing"
    elif variant == "many":
        original = row(data, "contracts")
        data["records"] += [
            {**copy.deepcopy(original), "id": f"extra-{i}"} for i in range(61)
        ]
    work["request"].write_text(json.dumps({"case": data}))
    record = execute(Path(work["context_path"]), "prepare", work["request"])
    binding = {
        "work_ref": "fictional-scissione",
        "client_root": str(work["client"]),
        "client_id": work["context"]["client_id"],
        "engagement_id": work["engagement"],
        "run_id": work["context"]["run_id"],
        "workflow_id": "scissione-guidata",
    }
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    return env, Path(work["output_dir"]), binding, record, workspace_module(), work


VIEW = """
const first=payload(call('vera_workspace_view',{work_ref:'fictional-scissione'}));
const selected=first.items.find(row=>row.group==='record');
const view=payload(call('vera_workspace_view',{work_ref:first.work_ref,revision:first.revision,source_ref:first.data.selection.source_ref,item_id:selected.id}));
const authority=(view,stamp='')=>({work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,item_id:view.selection.id,review_ticket:view.review_ticket,expected_checkpoint:view.data.decision_checkpoint,expected_draft_revision:stamp});
const fields={reviewer:'fictional-professional',role:'Fictional reviewer',reviewed_at:'2026-10-07T10:00:00+02:00',rationale:'Fictional mechanical review; no legal certification.'};
"""
SAVE = (
    VIEW
    + """
const draft=payload(call('vera_workspace_scissione_draft_read',{work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,item_id:view.selection.id}));
const saved=payload(call('vera_workspace_scissione_draft_save',{...authority(view,draft.draft_revision),fields}));
const args={...authority(view,saved.draft_revision),human_reviewed:true,idempotency_key:'fictional-record-review'};
"""
)


@pytest.mark.parametrize("scissione_workspace", ["one", "unsupported"], indirect=True)
def test_native_scissione_review_appends_exact_record_and_retains_history(
    scissione_workspace,
):
    env, output, binding, original, module, _ = scissione_workspace
    original_bytes = (
        output / "scissione_versions" / original["revision_sha256"] / "revision.json"
    ).read_bytes()
    result = rpc_program(
        env,
        SAVE
        + """
const decided=payload(call('vera_workspace_scissione_review',args));
const retry=payload(call('vera_workspace_scissione_review',args));
const after=payload(call('vera_workspace_view',{work_ref:view.work_ref,source_ref:decided.source_ref,item_id:view.selection.id}));
const old=payload(call('vera_workspace_view',{work_ref:view.work_ref,revision:view.revision,source_ref:view.data.selection.source_ref,item_id:view.selection.id}));
const files=payload(call('vera_workspace_outputs',{work_ref:view.work_ref,revision:after.revision,source_ref:decided.source_ref}));
const result={view,decided,retry,after,old,files};
""",
    )
    produced = json.loads(
        (
            output
            / "scissione_versions"
            / result["decided"]["source_ref"]
            / "revision.json"
        ).read_bytes()
    )
    assert produced["case"] == original["case"]
    assert produced["previous_sha256"] == original["revision_sha256"]
    assert set(produced["approvals"]) == {"route"}
    assert produced["schedule"] == {}
    assert produced["filing_status"] == "not_performed"
    assert produced["legal_validation"] == "not_certified"
    assert result["retry"] == result["decided"]
    assert result["old"]["data"]["can_review"] is False
    assert result["files"]["status"] == "unfinalized_scissione_review"
    assert len(result["files"]["outputs"]) == 7
    assert (
        output / "scissione_versions" / original["revision_sha256"] / "revision.json"
    ).read_bytes() == original_bytes
    assert module.load_binding(binding)["run"]["status"] == "running"


def test_native_scissione_selected_dependencies_and_context_are_exact(
    scissione_workspace,
):
    env, _, _, original, _, _ = scissione_workspace
    result = rpc_program(
        env,
        VIEW
        + """
const item=first.items.find(row=>row.title==='Ipotesi e basi del calcolo');
const chosen={work_ref:first.work_ref,revision:first.revision,source_ref:first.data.selection.source_ref,item_id:item.id};
const selectedView=payload(call('vera_workspace_view',chosen));
const explanation=call('vera_workspace_explain',chosen).structuredContent;
const result={selectedView,explanation};
""",
    )
    selected = result["selectedView"]["selection"]
    assert selected["data"] == row(original["case"], "calculation")
    assert {r["id"] for r in selected["dependencies"]} == {
        "route",
        "ownership",
        "valuation",
        "inventory",
    }
    assert selected["evidence"] == original["case"]["evidence"]
    assert result["explanation"]["untrusted_evidence"]["selected_record"] == selected


@pytest.mark.parametrize("scissione_workspace", ["unknown"], indirect=True)
def test_native_scissione_unknown_dependencies_refuse_before_intent(
    scissione_workspace,
):
    env, output, _, _, _, _ = scissione_workspace
    result = rpc_program(
        env,
        VIEW
        + """
const item=first.items.find(row=>row.title==='Perimetro da verificare');
const target=payload(call('vera_workspace_view',{work_ref:first.work_ref,source_ref:first.data.selection.source_ref,item_id:item.id}));
const stored=payload(call('vera_workspace_scissione_draft_save',{...authority(target),fields}));
const refused=call('vera_workspace_scissione_review',{...authority(target,stored.draft_revision),human_reviewed:true,idempotency_key:'unknown-dependencies'});
const result=refused;
""",
    )
    assert result["isError"] is True
    assert len(list((output / "scissione_versions").iterdir())) == 1
    assert not list(
        (output.parent / ".native-workspace").glob("scissione-request-*.json")
    )


@pytest.mark.parametrize(
    "tool",
    [
        "vera_workspace_save",
        "vera_workspace_apply",
        "vera_workspace_draft_save",
        "vera_workspace_aml_setup",
    ],
)
def test_native_scissione_refuses_generic_or_foreign_mutations(
    scissione_workspace, tool
):
    env, _, _, _, _, _ = scissione_workspace
    result = rpc_program(
        env,
        VIEW
        + f"const result=call('{tool}',{{...authority(view),human_reviewed:true,idempotency_key:'wrong',fields:{{}}}});",
    )
    assert result["isError"] is True


@pytest.mark.parametrize("scissione_workspace", ["many"], indirect=True)
def test_native_scissione_paginates_all_exact_records(scissione_workspace):
    env, _, _, record, _, _ = scissione_workspace
    result = rpc_program(
        env,
        VIEW
        + """
const pages=[];for(let offset=0;offset<first.total;offset+=30)pages.push(payload(call('vera_workspace_view',{work_ref:first.work_ref,revision:first.revision,source_ref:first.data.selection.source_ref,offset})));
const result={pages};
""",
    )
    items = [i for p in result["pages"] for i in p["items"]]
    assert len(items) == result["pages"][0]["total"]
    assert sum(i["group"] == "record" for i in items) == len(record["case"]["records"])
    assert len({i["id"] for i in items}) == len(items)


@pytest.mark.parametrize(
    "damage", ["memo", "resealed_memo", "html", "derived", "source", "linked"]
)
def test_native_scissione_refuses_altered_sources_or_resealed_artifacts(
    scissione_workspace, damage
):
    import hashlib

    env, output, binding, original, module, _ = scissione_workspace
    folder = output / "scissione_versions" / original["revision_sha256"]
    if damage in {"memo", "resealed_memo"}:
        (folder / "review.md").write_text("Changed fictional professional conclusions")
        if damage == "resealed_memo":
            manifest = json.loads((folder / "artifact_manifest.json").read_bytes())
            manifest["files"]["review.md"] = hashlib.sha256(
                (folder / "review.md").read_bytes()
            ).hexdigest()
            (folder / "artifact_manifest.json").write_text(json.dumps(manifest))
    elif damage == "html":
        (folder / "review.html").write_text("<p>Invented professional conclusion</p>")
        manifest = json.loads((folder / "artifact_manifest.json").read_bytes())
        manifest["files"]["review.html"] = hashlib.sha256(
            (folder / "review.html").read_bytes()
        ).hexdigest()
        (folder / "artifact_manifest.json").write_text(json.dumps(manifest))
    elif damage == "derived":
        (folder / "allocations.json").write_text(
            '[{"fictional":"invented calculation"}]'
        )
        manifest = json.loads((folder / "artifact_manifest.json").read_bytes())
        manifest["files"]["allocations.json"] = hashlib.sha256(
            (folder / "allocations.json").read_bytes()
        ).hexdigest()
        (folder / "artifact_manifest.json").write_text(json.dumps(manifest))
    elif damage == "source":
        loaded = module.load_binding(binding)
        path = (
            Path(loaded["run_root"])
            / "inputs"
            / original["case"]["evidence"][0]["path"]
        )
        path.write_text("Changed registered source")
    else:
        path = folder / "revision.json"
        moved = output / "linked.json"
        path.rename(moved)
        path.symlink_to(moved)
    result = rpc_program(
        env,
        "const result=call('vera_workspace_view',{work_ref:'fictional-scissione'});",
    )
    assert result["isError"] is True


def test_native_scissione_private_draft_cas_and_current_pointer_are_required(
    scissione_workspace,
):
    env, output, _, _, _, _ = scissione_workspace
    result = rpc_program(
        env,
        SAVE
        + """
const concurrent=call('vera_workspace_scissione_draft_save',{...authority(view),fields});
const wrong=call('vera_workspace_scissione_draft_save',{...authority(view,saved.draft_revision),fields:{record_ids:'foreign'}});
const forged=call('vera_workspace_scissione_review',{...args,review_ticket:'forged'});
const appended=payload(call('vera_workspace_scissione_review',args));
const stale=call('vera_workspace_scissione_draft_save',{...authority(view),fields});
const changedRetry=call('vera_workspace_scissione_review',{...args,expected_draft_revision:''});
const result={concurrent,wrong,forged,stale,changedRetry,appended};
""",
    )
    assert all(
        result[k]["isError"] is True
        for k in ("concurrent", "wrong", "forged", "stale", "changedRetry")
    )
    assert len(list((output / "scissione_versions").iterdir())) == 2


def test_native_scissione_viewer_cannot_store_private_review(scissione_workspace):
    env, output, _, _, _, _ = scissione_workspace
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": "VIEWER"},
        VIEW
        + "const result=call('vera_workspace_scissione_draft_save',{...authority(view),fields});",
    )
    assert result["isError"] is True
    assert len(list((output / "scissione_versions").iterdir())) == 1


def test_native_scissione_interrupted_review_refuses_repetition_and_retains_draft(
    scissione_workspace, monkeypatch
):
    env, output, binding, original, module, _ = scissione_workspace
    saved = rpc_program(env, SAVE + "const result={view,saved};")
    import native_scissione

    call = native_scissione.engine_call

    def interrupted(root, request):
        if request["operation"] == "review":
            raise TimeoutError("Fictional interrupted Scissione review")
        return call(root, request)

    monkeypatch.setattr(native_scissione, "engine_call", interrupted)
    args = {
        "work_ref": binding["work_ref"],
        "source_ref": original["revision_sha256"],
        "revision": saved["view"]["revision"],
        "item_id": saved["view"]["selection"]["id"],
        "expected_checkpoint": saved["view"]["data"]["decision_checkpoint"],
        "expected_draft_revision": saved["saved"]["draft_revision"],
        "human_reviewed": True,
        "idempotency_key": "interrupted",
    }
    with pytest.raises(TimeoutError, match="interrupted"):
        module.dispatch("vera_workspace_scissione_review", args)
    with pytest.raises(ValueError, match="Interrupted Scissione"):
        module.dispatch("vera_workspace_scissione_review", args)
    assert (
        len(list((output.parent / ".native-workspace").glob("scissione-draft-*.json")))
        == 1
    )
    assert len(list((output / "scissione_versions").iterdir())) == 1


def test_native_scissione_calculation_and_document_review_use_unchanged_engine(
    scissione_workspace,
):
    env, output, _, original, _, _ = scissione_workspace
    result = rpc_program(
        env,
        VIEW
        + """
let currentRef=first.data.selection.source_ref;
const preparedRecords=first.items.filter(row=>row.group==='record');
for(const item of preparedRecords){
 const latest=payload(call('vera_workspace_view',{work_ref:first.work_ref,source_ref:currentRef,item_id:item.id}));
 const patch=payload(call('vera_workspace_scissione_draft_save',{...authority(latest),fields}));
 const outcome=payload(call('vera_workspace_scissione_review',{...authority(latest,patch.draft_revision),human_reviewed:true,idempotency_key:item.id.replace(':','-')}));currentRef=outcome.source_ref;
}
const final=payload(call('vera_workspace_view',{work_ref:first.work_ref,source_ref:currentRef}));
const result={final};
""",
    )
    final = json.loads(
        (
            output
            / "scissione_versions"
            / result["final"]["data"]["selection"]["source_ref"]
            / "revision.json"
        ).read_bytes()
    )
    assert final["status"] == "prepared_for_review"
    assert final["schedule"]["owners"][0]["economic_transferred"] == "180000.00"
    assert final["schedule"]["owners"][0]["shareholder_tax_cost"] is None
    assert final["case"] == original["case"]
    assert final["filing_status"] == "not_performed"


@pytest.mark.parametrize(
    "refusal", ["document_before_calculation", "date_without_zone"]
)
def test_native_scissione_professional_prevalidation_does_not_create_intent(
    scissione_workspace, refusal
):
    env, output, _, _, _, _ = scissione_workspace
    choice = (
        "first.items.find(row=>row.title.startsWith('Documento · '))"
        if refusal == "document_before_calculation"
        else "selected"
    )
    date = (
        "2026-10-07T10:00:00"
        if refusal == "date_without_zone"
        else "2026-10-07T10:00:00+02:00"
    )
    result = rpc_program(
        env,
        VIEW
        + f"""
const item={choice};
const exact=payload(call('vera_workspace_view',{{work_ref:first.work_ref,source_ref:first.data.selection.source_ref,item_id:item.id}}));
const stored=payload(call('vera_workspace_scissione_draft_save',{{...authority(exact),fields:{{...fields,reviewed_at:{json.dumps(date)}}}}}));
const result=call('vera_workspace_scissione_review',{{...authority(exact,stored.draft_revision),human_reviewed:true,idempotency_key:'prevalidate'}});
""",
    )
    assert result["isError"] is True
    assert len(list((output / "scissione_versions").iterdir())) == 1
    assert not list(
        (output.parent / ".native-workspace").glob("scissione-request-*.json")
    )
    assert not list(output.glob("native-scissione-review-*.json"))


def test_native_scissione_specialist_revision_reopens_dependent_approvals(
    scissione_workspace,
):
    env, output, _, original, _, work = scissione_workspace
    from tests.plugins.test_scissione_guidata import review_request

    request = output / "review-by-specialist.json"
    request.write_text(
        json.dumps(
            review_request(
                original,
                ["route", "ownership", "valuation", "inventory", "calculation"],
            )
        )
    )
    reviewed = execute(Path(work["context_path"]), "review", request)
    changed = copy.deepcopy(work["case"])
    row(changed, "inventory")["data"][
        "rationale"
    ] = "Fictional revised evidence description"
    request = output / "revise-by-specialist.json"
    request.write_text(
        json.dumps({"case": changed, "revision_sha256": reviewed["revision_sha256"]})
    )
    revised = execute(Path(work["context_path"]), "revise", request)
    result = rpc_program(
        env,
        f"const result=payload(call('vera_workspace_view',{{work_ref:'fictional-scissione',source_ref:{json.dumps(revised['revision_sha256'])}}}));",
    )
    assert result["data"]["current"] is True
    assert set(revised["approvals"]) == {"route", "ownership", "valuation"}
    assert set(revised["change_impact"]["invalidated_approval_ids"]) == {
        "inventory",
        "calculation",
    }
    assert revised["schedule"] == {}
    assert len(list((output / "scissione_versions").iterdir())) == 3


def test_native_scissione_reads_finalized_upstream_and_preserves_approval(
    scissione_workspace, monkeypatch, tmp_path
):
    from tests.model_data_helpers import write_no_model_report
    from tests.plugins.test_scissione_guidata import review_request

    env, output, binding, original, _, work = scissione_workspace
    request = output / "review-by-specialist.json"
    request.write_text(json.dumps(review_request(original, ["ownership"])))
    previous = execute(Path(work["context_path"]), "review", request)
    run_id = work["context"]["run_id"]
    write_no_model_report(output, "scissione-guidata", run_id)
    exact = f"scissione_versions/{previous['revision_sha256']}/revision.json"
    declarations = [
        {
            "artifact_id": (
                "previous"
                if p.relative_to(output).as_posix() == exact
                else f"artifact_{index}"
            ),
            "path": p.relative_to(output).as_posix(),
            "purpose": "Fictional continuation",
            "audience": "internal",
            "media_type": "application/octet-stream",
        }
        for index, p in enumerate(sorted(p for p in output.rglob("*") if p.is_file()))
    ]
    work["ledger"].finalize_run(
        work["client"], work["engagement"], run_id, declarations
    )
    imported = next(
        i for i in work["context"]["input_bindings"] if i["kind"] == "import"
    )
    downstream = work["ledger"].prepare_run(
        work["client"],
        binding["client_id"],
        work["engagement"],
        "scissione-guidata",
        "0.1.0",
        input_ids=[imported["binding_id"]],
        upstream_artifacts=[
            {"run_id": run_id, "artifact_id": "previous", "role": "case"}
        ],
        new_run=True,
    )
    running = work["ledger"].start_run(
        work["client"], work["engagement"], downstream["run"]["run_id"]
    )
    receipt = next(
        i
        for i in running["context"]["input_bindings"]
        if i["kind"] == "upstream_artifact"
    )
    proposal = Path(running["output_dir"]) / "continuation.json"
    proposal.write_text(
        json.dumps(
            {
                "case": work["case"],
                "previous_revision_path": Path(receipt["path"])
                .relative_to(Path(running["context"]["run_root"]) / "inputs")
                .as_posix(),
            }
        )
    )
    continued = execute(Path(running["context_path"]), "prepare", proposal)
    binding = {**binding, "run_id": running["run"]["run_id"]}
    env.update(configure(monkeypatch, tmp_path, [binding]))
    result = rpc_program(env, VIEW + "const result={view,first};")
    assert result["first"]["data"]["current"] is True
    assert continued["approvals"] == previous["approvals"]
    assert continued["previous_sha256"] == previous["revision_sha256"]
    assert continued["change_impact"]["invalidated_approval_ids"] == []


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_native_scissione_fresh_package_replays_and_appends_exact_record(
    scissione_workspace, surface, tmp_path, monkeypatch
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, output, binding, original, _, work = scissione_workspace
    builder = load_builder(
        "build_codex_plugin_zip" if surface == "codex" else "build_claude_plugin_zip"
    )
    if surface == "codex":
        vera = next(i for i in builder.load_bundles() if i.name == "vera")
        entries = builder.expected_zip_entries(vera)
        prefix = vera.package_root + "/plugins/vera/"
    else:
        _, packages = builder.load_configuration()
        vera = next(i for i in packages if i.plugin == "vera")
        entries = builder.claude_package_entries(vera)
        prefix = ""
    target = tmp_path / "extracted"
    for name, content in entries.items():
        if name.startswith(prefix):
            path = target / name[len(prefix) :]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    if surface == "cowork":
        # Cowork projects runtime-specific report text. Generate its own prepared
        # artifacts in a fresh registered run rather than weakening exact replay.
        downstream = work["ledger"].prepare_run(
            work["client"],
            binding["client_id"],
            work["engagement"],
            "scissione-guidata",
            "0.1.0",
            input_ids=[i["binding_id"] for i in work["context"]["input_bindings"]],
            new_run=True,
        )
        running = work["ledger"].start_run(
            work["client"], work["engagement"], downstream["run"]["run_id"]
        )
        output = Path(running["output_dir"])
        request = output / "cowork-proposal.json"
        request.write_text(json.dumps({"case": original["case"]}))
        prepared = subprocess.run(
            [
                sys.executable,
                str(target / "modules/scissione-guidata/scripts/run_scissione.py"),
                "prepare",
                "--client-engagement",
                str(running["context_path"]),
                "--request",
                str(request),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert prepared.returncode == 0, prepared.stderr
        binding = {**binding, "run_id": running["run"]["run_id"]}
        env.update(configure(monkeypatch, tmp_path, [binding]))
    result = rpc_program(
        env,
        SAVE + "const result=payload(call('vera_workspace_scissione_review',args));",
        server=target / "mcp/workspace.cjs",
    )
    produced = json.loads(
        (
            output / "scissione_versions" / result["source_ref"] / "revision.json"
        ).read_bytes()
    )
    assert produced["case"] == original["case"]
    assert produced["previous_sha256"] == original["revision_sha256"]
    assert set(produced["approvals"]) == {"route"}
    assert result["run_completed"] is False
    for file in (
        "scripts/native_scissione.py",
        "scripts/native_scissione_bridge.py",
        "modules/scissione-guidata/scripts/run_scissione.py",
    ):
        source = ROOT / (
            "plugins/scissione-guidata/scripts/run_scissione.py"
            if file.startswith("modules/")
            else "plugins/vera/" + file
        )
        expected = (
            entries[prefix + file]
            if surface == "cowork" and file.startswith("modules/")
            else source.read_bytes()
        )
        assert (target / file).read_bytes() == expected


def test_cowork_scissione_specialist_cli_retains_customer_outputs_without_native(
    scissione_workspace, tmp_path
):
    from tests.plugins.test_packaged_mcp_startup import load_builder
    from tests.plugins.test_scissione_guidata import review_request

    env, output, binding, original, module, _ = scissione_workspace
    builder = load_builder("build_claude_plugin_zip")
    _, packages = builder.load_configuration()
    vera = next(i for i in packages if i.plugin == "vera")
    target = tmp_path / "cowork-extracted"
    for name, content in builder.claude_package_entries(vera).items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    request = output / "cowork-professional-review.json"
    request.write_text(json.dumps(review_request(original, ["route"])))
    completed = subprocess.run(
        [
            sys.executable,
            str(target / "modules/scissione-guidata/scripts/run_scissione.py"),
            "review",
            "--client-engagement",
            str(module.load_binding(binding)["context_path"]),
            "--request",
            str(request),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    pointer = json.loads((output / "scissione_current.json").read_bytes())
    record = json.loads(
        (
            output / "scissione_versions" / pointer["revision_sha256"] / "revision.json"
        ).read_bytes()
    )
    assert set(record["approvals"]) == {"route"}
    assert record["case"] == original["case"]
    assert len(list((output / "scissione_versions").iterdir())) == 2
    assert module.load_binding(binding)["run"]["status"] == "running"
    assert not (output.parent / ".native-workspace").exists()
