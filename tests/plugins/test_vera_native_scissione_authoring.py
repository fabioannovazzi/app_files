"""Actual owned Scissione source mandates and public versions; no host/model claim."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from tests._plugin_cli import workflow_cli
from tests.plugins.test_scissione_archive import execute, read_revision
from tests.plugins.test_scissione_guidata import case, review_request, row
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_aml_authoring import REQUEST, STAGE, program
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import registry_workspace

__all__ = []


@pytest.fixture
def initial_scissione(registry_workspace):
    env, studio, _, _, client, engagement = registry_workspace
    env.update(
        VERA_WORKSPACE_ACTOR_ID="fictional-reviewer",
        VERA_WORKSPACE_TENANT_ID="fictional-studio",
        VERA_WORKSPACE_ROLES="REVIEWER",
    )
    folder = studio / "Cliente Beta"
    ledger = _load_customer_ledger()
    imported = ledger.list_inputs(folder, engagement)[0]
    prepared = ledger.prepare_run(
        folder,
        client,
        engagement,
        "scissione-guidata",
        "test-version",
        input_ids=[imported["input_id"]],
    )
    ledger.start_run(folder, engagement, prepared["run"]["run_id"])
    loaded = ledger.load_run(folder, engagement, prepared["run"]["run_id"])
    source = loaded["input_manifest"]["inputs"][0]
    data = case()
    data["evidence"][0].update(
        path=Path(source["execution_relative_path"]).relative_to("inputs").as_posix(),
        sha256=source["sha256"],
    )
    ref = "studio-" + "_".join(
        v.split("_", 1)[1] for v in (client, engagement, prepared["run"]["run_id"])
    )
    return env, folder, loaded, data, ref


def scissione_program(ref: str, review: dict, body: str) -> str:
    return (
        program(ref, review, body)
        .replace("vera_workspace_aml_author_", "vera_workspace_scissione_author_")
        .replace(
            "Fictional review of the documented loan: preserve unresolved explanations.",
            "Fictional operation draft; preserve unsupported route, unknown values and pending professional approvals.",
        )
    )


@pytest.mark.parametrize("variant", ["ordinary", "unknown", "unsupported"])
def test_initial_case_conserves_exact_public_dossier_without_any_approval(
    initial_scissione, variant
):
    env, _, loaded, data, ref = initial_scissione
    if variant == "unknown":
        row(data, "contracts")["status"] = "unknown"
    if variant == "unsupported":
        row(data, "route")["data"]["scope"]["beneficiary"] = "existing"
    result = rpc_program(
        env,
        scissione_program(
            ref,
            {"case": data},
            REQUEST
            + STAGE
            + "const saved=payload(call('vera_workspace_scissione_author_publish',publishArgs));const retry=payload(call('vera_workspace_scissione_author_publish',publishArgs));const result={context,read,saved,retry};",
        ),
    )
    output = Path(loaded["output_dir"])
    produced = read_revision(output, result["saved"]["source_ref"])
    assert produced == result["read"]["record"]
    assert produced["case"] == data
    assert produced["approvals"] == {}
    assert produced["schedule"] == {}
    assert produced["legal_validation"] == "not_certified"
    assert produced["filing_status"] == "not_performed"
    assert row(produced["case"], "ownership")["data"]["owners"][0]["tax_cost"] is None
    assert result["context"]["case_scope"] is None
    assert result["saved"] == result["retry"]
    assert produced["status"] == (
        "unsupported" if variant == "unsupported" else "partial"
    )
    assert (
        output / "scissione_versions" / produced["revision_sha256"] / "review.md"
    ).read_text() == result["read"]["memo"]
    assert (
        output / ("scissione-native-proposal-" + produced["revision_sha256"] + ".json")
    ).is_file()


def test_literal_question_and_source_draft_recovers_without_model_grant(
    initial_scissione,
):
    env, _, _, data, ref = initial_scissione
    saved = rpc_program(
        env,
        scissione_program(
            ref,
            {"case": data},
            "const {confirmed,idempotency_key,...draftArgs}=requestArgs;const stored=payload(call('vera_workspace_scissione_author_draft_store',{...draftArgs,fields:"
            + json.dumps({"question": "  Literal question\n", "input_ids": []})
            + "}));const result=stored;",
        ),
    )
    recovered = rpc_program(env, scissione_program(ref, {}, "const result=setup;"))
    assert recovered["draft"]["draft_revision"] == saved["draft_revision"]
    assert recovered["draft"]["fields"] == {
        "question": "  Literal question\n",
        "input_ids": [],
    }
    assert recovered["mandates"] == []
    assert "confirmed" not in recovered["draft"]


@pytest.mark.parametrize(
    "change",
    ["approval", "foreign_source", "changed_hash", "foreign_previous", "lost_source"],
)
def test_model_case_refuses_ungranted_sources_and_approval_fields(
    initial_scissione, change
):
    env, _, loaded, data, ref = initial_scissione
    proposal = {"case": data}
    if change == "approval":
        proposal["record_ids"] = ["route"]
    if change == "foreign_source":
        data["evidence"][0]["path"] = "../foreign.json"
    if change == "changed_hash":
        data["evidence"][0]["sha256"] = "0" * 64
    if change == "foreign_previous":
        proposal["previous_revision_path"] = data["evidence"][0]["path"]
    if change == "lost_source":
        data["evidence"] = []
    result = rpc_program(
        env,
        scissione_program(
            ref,
            proposal,
            REQUEST
            + "const result=call('vera_workspace_scissione_author_stage',{...exact,expected_stage_revision:context.stage_revision,review,idempotency_key:'refused-case'});",
        ),
    )
    assert result["isError"] is True
    assert not (Path(loaded["output_dir"]) / "scissione_current.json").exists()


def test_model_case_revision_preserves_original_and_only_public_carried_approvals(
    initial_scissione,
):
    env, _, loaded, data, ref = initial_scissione
    output = Path(loaded["output_dir"])
    first = output / "first.json"
    first.write_text(json.dumps({"case": data}))
    original = execute(Path(loaded["context_path"]), "prepare", first)
    approve = output / "actual-fixture-review.json"
    approve.write_text(json.dumps(review_request(original, ["route"])))
    accepted = execute(Path(loaded["context_path"]), "review", approve)
    original_bytes = (
        output / "scissione_versions" / accepted["revision_sha256"] / "revision.json"
    ).read_bytes()
    changed = copy.deepcopy(data)
    row(changed, "contracts")["status"] = "unknown"
    proposal = {"case": changed, "revision_sha256": accepted["revision_sha256"]}
    result = rpc_program(
        env,
        scissione_program(
            ref,
            proposal,
            REQUEST
            + STAGE
            + "const result=payload(call('vera_workspace_scissione_author_publish',publishArgs));",
        ),
    )
    produced = read_revision(output, result["source_ref"])
    assert produced["previous_sha256"] == accepted["revision_sha256"]
    assert produced["approvals"] == accepted["approvals"]
    assert row(produced["case"], "contracts")["status"] == "unknown"
    assert (
        output / "scissione_versions" / accepted["revision_sha256"] / "revision.json"
    ).read_bytes() == original_bytes


@pytest.mark.parametrize(
    "change",
    ["ticket", "foreign_input", "empty_sources", "unconfirmed", "stale_revision"],
)
def test_source_mandate_refuses_unsigned_unconfirmed_or_stale_selection(
    initial_scissione, change
):
    env, _, loaded, data, ref = initial_scissione
    mutation = {
        "ticket": "requestArgs.review_ticket='bad';",
        "foreign_input": "requestArgs.fields.input_ids=['input_'+'0'.repeat(24)];",
        "empty_sources": "requestArgs.fields.input_ids=[];",
        "unconfirmed": "requestArgs.confirmed=false;",
        "stale_revision": "requestArgs.revision='0'.repeat(64);",
    }[change]
    result = rpc_program(
        env,
        scissione_program(
            ref,
            {"case": data},
            mutation
            + "const result=call('vera_workspace_scissione_author_request',requestArgs);",
        ),
    )
    assert result["isError"] is True
    assert not list(
        (Path(loaded["output_dir"]).parent / ".native-workspace").glob(
            "scissione-authoring-*/mandate-*"
        )
    )


@pytest.mark.parametrize(
    "damage", ["orphan", "pending", "missing_stage_receipt", "changed_stage"]
)
def test_uncertain_case_authoring_blocks_new_writes_record_review_and_closure(
    initial_scissione, damage
):
    env, _, loaded, data, ref = initial_scissione
    staged = rpc_program(
        env,
        scissione_program(
            ref, {"case": data}, REQUEST + STAGE + "const result={requested,staged};"
        ),
    )
    output = Path(loaded["output_dir"])
    base = (
        next((output.parent / ".native-workspace").glob("scissione-authoring-*"))
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
    # Independent specialist preparation does not erase an uncertain native intent.
    public = output / "independent-specialist.json"
    public.write_text(json.dumps({"case": data}))
    original = execute(Path(loaded["context_path"]), "prepare", public)
    result = rpc_program(
        env,
        f"""
const setupNow=call('vera_workspace_scissione_author_setup',{{work_ref:{json.dumps(ref)}}});
const view=call('vera_workspace_view',{{work_ref:{json.dumps(ref)},source_ref:{json.dumps(original['revision_sha256'])}}});
const closure=call('vera_workspace_archive_closure',{{client_id:{json.dumps(loaded['run']['client_id'])},engagement_id:{json.dumps(loaded['run']['engagement_id'])},run_id:{json.dumps(loaded['run']['run_id'])}}});
const result={{setupNow,view,closure}};
""",
    )
    assert result["closure"]["isError"] is True
    if damage == "changed_stage":
        assert result["setupNow"]["isError"] is True
        assert result["view"]["isError"] is True
    else:
        assert result["setupNow"]["_meta"]["workspace"]["can_write"] is False
        assert result["view"]["_meta"]["workspace"]["data"]["can_review"] is False
    assert read_revision(output)["revision_sha256"] == original["revision_sha256"]


@pytest.mark.parametrize("change", ["actor", "tenant", "source", "current_case"])
def test_retained_mandate_refuses_foreign_owner_changed_source_or_successor(
    initial_scissione, change
):
    env, _, loaded, data, ref = initial_scissione
    grant = rpc_program(
        env,
        scissione_program(
            ref, {"case": data}, REQUEST + "const result={requested,context};"
        ),
    )
    if change == "actor":
        env = {**env, "VERA_WORKSPACE_ACTOR_ID": "another-fictional-reviewer"}
    elif change == "tenant":
        env = {**env, "VERA_WORKSPACE_TENANT_ID": "another-fictional-studio"}
    elif change == "source":
        Path(grant["context"]["sources"][0]["path"]).write_text("Changed original")
    else:
        public = Path(loaded["output_dir"]) / "independent-case.json"
        public.write_text(json.dumps({"case": data}))
        execute(Path(loaded["context_path"]), "prepare", public)
    denied = rpc_program(
        env,
        "const result=call('vera_workspace_scissione_author_context',"
        + json.dumps({"work_ref": ref, "grant_ref": grant["requested"]["grant_ref"]})
        + ");",
    )
    assert denied["isError"] is True


def test_same_evidence_correction_invalidates_only_actual_changed_dependencies(
    initial_scissione,
):
    env, _, loaded, data, ref = initial_scissione
    output = Path(loaded["output_dir"])
    request = output / "actual-fixture-review.json"
    request.write_text(json.dumps({"case": data}))
    original = execute(Path(loaded["context_path"]), "prepare", request)
    request.write_text(
        json.dumps(
            review_request(
                original,
                ["route", "ownership", "valuation", "inventory", "calculation"],
            )
        )
    )
    accepted = execute(Path(loaded["context_path"]), "review", request)
    changed = copy.deepcopy(data)
    row(changed, "inventory")["data"][
        "rationale"
    ] = "Fictional changed inventory explanation"
    result = rpc_program(
        env,
        scissione_program(
            ref,
            {"case": changed, "revision_sha256": accepted["revision_sha256"]},
            REQUEST
            + STAGE
            + "const result=payload(call('vera_workspace_scissione_author_publish',publishArgs));",
        ),
    )
    produced = read_revision(output, result["source_ref"])
    assert set(produced["approvals"]) == {"route", "ownership", "valuation"}
    assert set(produced["change_impact"]["invalidated_approval_ids"]) == {
        "inventory",
        "calculation",
    }
    assert produced["schedule"] == {}
    assert read_revision(output, accepted["revision_sha256"]) == accepted


def test_fresh_run_case_uses_only_chosen_sealed_same_engagement_predecessor(
    initial_scissione,
):
    from tests.model_data_helpers import write_no_model_report

    env, folder, loaded, data, ref = initial_scissione
    initial = rpc_program(
        env,
        scissione_program(
            ref,
            {"case": data},
            REQUEST
            + STAGE
            + "const result=payload(call('vera_workspace_scissione_author_publish',publishArgs));",
        ),
    )
    output = Path(loaded["output_dir"])
    previous = read_revision(output, initial["source_ref"])
    ledger = _load_customer_ledger()
    run_id, engagement = loaded["run"]["run_id"], loaded["run"]["engagement_id"]
    write_no_model_report(output, "scissione-guidata", run_id)
    selected = f"scissione_versions/{initial['source_ref']}/revision.json"
    declarations = [
        {
            "artifact_id": (
                "previous"
                if p.relative_to(output).as_posix() == selected
                else f"artifact_{i}"
            ),
            "path": p.relative_to(output).as_posix(),
            "purpose": "Fictional exact continuation",
            "audience": "internal",
            "media_type": "application/octet-stream",
        }
        for i, p in enumerate(sorted(p for p in output.rglob("*") if p.is_file()))
    ]
    ledger.finalize_run(folder, engagement, run_id, declarations)
    prepared = ledger.prepare_run(
        folder,
        loaded["run"]["client_id"],
        engagement,
        "scissione-guidata",
        "test-version",
        input_ids=[loaded["input_manifest"]["inputs"][0]["binding_id"]],
        upstream_artifacts=[
            {"run_id": run_id, "artifact_id": "previous", "role": "case"}
        ],
        new_run=True,
    )
    ledger.start_run(folder, engagement, prepared["run"]["run_id"])
    downstream = ledger.load_run(folder, engagement, prepared["run"]["run_id"])
    predecessor = next(
        r
        for r in downstream["input_manifest"]["inputs"]
        if r["kind"] == "upstream_artifact"
    )
    proposal = {
        "case": data,
        "previous_revision_path": Path(predecessor["execution_relative_path"])
        .relative_to("inputs")
        .as_posix(),
    }
    new_ref = "studio-" + "_".join(
        v.split("_", 1)[1]
        for v in (loaded["run"]["client_id"], engagement, prepared["run"]["run_id"])
    )
    result = rpc_program(
        env,
        scissione_program(
            new_ref,
            proposal,
            REQUEST
            + STAGE
            + "const result=payload(call('vera_workspace_scissione_author_publish',publishArgs));",
        ),
    )
    produced = read_revision(Path(downstream["output_dir"]), result["source_ref"])
    assert produced["previous_sha256"] == previous["revision_sha256"]
    assert produced["case"] == data
    assert produced["approvals"] == {}
    assert read_revision(output, previous["revision_sha256"]) == previous


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_extracted_native_initial_case_preserves_public_cli_correction(
    initial_scissione, surface, tmp_path
):
    from tests.plugins.test_packaged_mcp_startup import ROOT, load_builder

    env, _, loaded, data, ref = initial_scissione
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
        scissione_program(
            ref,
            {"case": data},
            REQUEST
            + STAGE
            + "const result=payload(call('vera_workspace_scissione_author_publish',publishArgs));",
        ),
        server=target / "mcp/workspace.cjs",
    )
    output = Path(loaded["output_dir"])
    initial = read_revision(output, result["source_ref"])
    request = output / "independent-public-cli-correction.json"
    changed = copy.deepcopy(data)
    row(changed, "contracts")["status"] = "unknown"
    request.write_text(
        json.dumps({"case": changed, "revision_sha256": initial["revision_sha256"]})
    )
    completed = subprocess.run(
        [
            *workflow_cli(
                target / "modules/scissione-guidata/scripts/run_scissione.py"
            ),
            "revise",
            "--client-engagement",
            loaded["context_path"],
            "--request",
            str(request),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr
    produced = read_revision(output)
    assert produced["case"] == changed
    assert produced["approvals"] == {}
    assert produced["previous_sha256"] == initial["revision_sha256"]
    assert read_revision(output, initial["revision_sha256"]) == initial
    assert (target / "scripts/native_scissione_authoring.py").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_scissione_authoring.py"
    ).read_bytes()
    assert (
        target / "modules/scissione-guidata/scripts/run_scissione.py"
    ).read_bytes() == entries[
        prefix + "modules/scissione-guidata/scripts/run_scissione.py"
    ]
    assert (
        target / "modules/scissione-guidata/scripts/scissione_core.py"
    ).read_bytes() == (
        ROOT / "plugins/scissione-guidata/scripts/scissione_core.py"
    ).read_bytes()


@pytest.mark.parametrize("committed", [False, True])
def test_interrupted_public_conservation_never_adopts_or_repeats_uncertain_case(
    initial_scissione, monkeypatch, committed
):
    from tests.plugins.test_vera_native_workspace import workspace_module

    env, _, loaded, data, ref = initial_scissione
    prepared = rpc_program(
        env,
        scissione_program(
            ref,
            {"case": data},
            REQUEST + STAGE + "const result={requested,staged,publishArgs};",
        ),
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[2] / "plugins/vera/scripts")
    )
    import native_aml_authoring

    original = native_aml_authoring.inspect

    def interrupted(*args, **kwargs):
        if kwargs.get("save"):
            if committed:
                original(*args, **kwargs)
            raise TimeoutError("Fictional interrupted Scissione conservation")
        return original(*args, **kwargs)

    monkeypatch.setattr(native_aml_authoring, "inspect", interrupted)
    api = workspace_module()
    with pytest.raises(TimeoutError, match="interrupted"):
        api.dispatch("vera_workspace_scissione_author_publish", prepared["publishArgs"])
    output = Path(loaded["output_dir"])
    before = {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*")
        if p.is_file()
    }
    with pytest.raises(PermissionError, match="uncertain writes"):
        api.dispatch("vera_workspace_scissione_author_publish", prepared["publishArgs"])
    setup = api.dispatch("vera_workspace_scissione_author_setup", {"work_ref": ref})
    assert setup["can_write"] is False
    assert setup["recovery_required"] is True
    assert {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*")
        if p.is_file()
    } == before
    assert (output / "scissione_current.json").exists() is committed
    if committed:
        assert read_revision(output)["approvals"] == {}
