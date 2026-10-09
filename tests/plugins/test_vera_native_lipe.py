"""Synthetic LIPE calculations through the real ledger and signed native MCP service."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.plugins.test_lipe import case_data, prepare, quarterly
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_workspace import ROOT, configure, workspace_module


@pytest.fixture
def initial_lipe(tmp_path, monkeypatch, request):
    """Register fictional evidence and the explicitly reviewed immutable case."""
    ledger = _load_customer_ledger()
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    folder = tmp_path / "Fictional LIPE customer"
    folder.mkdir()
    client = "client_111111111111111111111111"
    ledger.create_client_manifest(folder, client)
    engagement = ledger.create_engagement(folder, client, "Fictional LIPE")
    variant = getattr(request, "param", "monthly")
    case = quarterly() if variant == "quarterly" else case_data()
    case.update(client_id=client, engagement_id=engagement["engagement_id"])
    if variant == "unknown_code":
        case["registers"][0]["rows"][0]["code"] = "UNKNOWN"
    elif variant == "scope_pending":
        case["scope_review"]["status"] = "PROPOSED"
    elif variant == "invalid":
        case["tax_year"] = 1900
    elif variant == "foreign":
        case["client_id"] = "client_222222222222222222222222"
    elif variant == "catalog":
        case["catalog_context"] = {
            "catalog_id": "fictional-catalog",
            "studio_id": "fictional-studio",
        }
    prepare(case, tmp_path)
    evidence = ledger.import_document(
        folder, client, engagement["engagement_id"], tmp_path / "evidence.txt", "source"
    )["receipt"]
    case["sources"][0]["path"] = (
        Path("imports") / evidence["input_id"] / Path(evidence["relative_path"]).name
    ).as_posix()
    if variant == "escape":
        case["sources"][0]["path"] = "../../../foreign.txt"
    source = tmp_path / "reviewed-case.json"
    source.write_text(json.dumps(case))
    imported = ledger.import_document(
        folder, client, engagement["engagement_id"], source, "support"
    )["receipt"]
    input_ids = [evidence["input_id"], imported["input_id"]]
    if variant == "two_cases":
        case["scope_review"]["status"] = "PROPOSED"
        second = tmp_path / "revised-case.json"
        second.write_text(json.dumps(case))
        input_ids.append(
            ledger.import_document(
                folder, client, engagement["engagement_id"], second, "support"
            )["receipt"]["input_id"]
        )
    prepared = ledger.prepare_run(
        folder,
        client,
        engagement["engagement_id"],
        "lipe",
        "test-version",
        input_ids=input_ids,
    )
    running = ledger.start_run(
        folder, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    binding = {
        "work_ref": "initial-lipe",
        "client_root": str(folder),
        "client_id": client,
        "engagement_id": engagement["engagement_id"],
        "run_id": prepared["run"]["run_id"],
        "workflow_id": "lipe",
    }
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    return env, Path(running["output_dir"]), binding


SETUP = """
const initial = payload(call('vera_workspace_lipe_setup', {work_ref:'initial-lipe'}));
const args = {work_ref:initial.work_ref, revision:initial.revision, review_ticket:initial.review_ticket, case_input_id:initial.items[0].id, human_reviewed:true, idempotency_key:'fictional-calculation'};
"""
CALCULATE = (
    SETUP
    + """
const calculated = payload(call('vera_workspace_lipe_calculate', args));
const view = payload(call('vera_workspace_view', {work_ref:'initial-lipe', source_ref:calculated.source_ref}));
"""
)


@pytest.mark.parametrize(
    "initial_lipe,modules",
    [("monthly", 3), ("quarterly", 1)],
    indirect=["initial_lipe"],
)
def test_native_lipe_persists_real_engine_workpapers_without_approval(
    initial_lipe, modules
):
    env, output, _ = initial_lipe
    result = rpc_program(
        env,
        CALCULATE
        + "const retry = payload(call('vera_workspace_lipe_calculate', args)); const result = {initial, calculated, view, retry};",
    )
    produced = json.loads(
        (output / result["calculated"]["source_ref"] / "result.json").read_bytes()
    )
    assert produced["status"] == "DRAFT_FOR_REVIEW"
    assert len(produced["modules"]) == modules
    assert result["retry"] == result["calculated"]
    assert len(list(output.glob("lipe-*"))) == 1
    assert (output / result["calculated"]["source_ref"] / "workpaper.xlsx").is_file()
    assert (output / result["calculated"]["source_ref"] / "summary.pdf").is_file()
    assert result["view"]["data"]["local_review_read_only"] is True
    assert result["calculated"]["professional_approval"] is False
    assert result["calculated"]["run_completed"] is False
    assert result["view"]["data"]["export_status"] == "NOT_AUTHORIZED"


@pytest.mark.parametrize(
    "initial_lipe,status",
    [
        ("unknown_code", "BLOCKED"),
        ("scope_pending", "BLOCKED"),
        ("invalid", "BLOCKED_INVALID_INPUT"),
    ],
    indirect=["initial_lipe"],
)
def test_native_lipe_preserves_blocked_engine_result_without_filling_vp(
    initial_lipe, status
):
    env, output, _ = initial_lipe
    result = rpc_program(env, CALCULATE + "const result = {calculated,view};")
    produced = json.loads(
        (output / result["calculated"]["source_ref"] / "result.json").read_bytes()
    )
    assert produced["status"] == status
    assert produced["modules"] == []
    assert produced["blockers"]
    assert (output / result["calculated"]["source_ref"] / "workpaper.md").is_file()


@pytest.mark.parametrize(
    "change",
    [
        "review_ticket:'forged.signature'",
        "revision:'f'.repeat(64)",
        "human_reviewed:false",
        "case_input_id:'foreign-case'",
        "case_path:'/private/foreign.json'",
    ],
)
def test_native_lipe_signed_selection_refuses_forgery_before_outputs(
    initial_lipe, change
):
    env, output, _ = initial_lipe
    result = rpc_program(
        env,
        SETUP
        + f"const result=call('vera_workspace_lipe_calculate', {{...args,{change}}});",
    )
    assert result["isError"] is True
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("initial_lipe", ["foreign", "escape"], indirect=True)
def test_native_lipe_refuses_foreign_case_or_unregistered_source(initial_lipe):
    env, output, _ = initial_lipe
    result = rpc_program(
        env, SETUP + "const result=call('vera_workspace_lipe_calculate',args);"
    )
    assert result["isError"] is True
    assert list(output.iterdir()) == []


def test_native_lipe_model_reads_only_selected_producer_record_and_exact_revision(
    initial_lipe,
):
    env, _, _ = initial_lipe
    result = rpc_program(
        env,
        CALCULATE
        + """
const selected = payload(call('vera_workspace_view', {work_ref:'initial-lipe', revision:view.revision, source_ref:calculated.source_ref, item_id:'modules:0'}));
const explained = call('vera_workspace_explain', {work_ref:'initial-lipe', revision:view.revision, source_ref:calculated.source_ref, item_id:'modules:0'});
const stale = call('vera_workspace_explain', {work_ref:'initial-lipe', revision:'f'.repeat(64), source_ref:calculated.source_ref, item_id:'modules:0'});
const foreign = call('vera_workspace_explain', {work_ref:'initial-lipe', revision:view.revision, source_ref:'lipe-'+'f'.repeat(64), item_id:'modules:0'});
const result = {selected,explained,stale,foreign};
""",
    )
    assert (
        result["explained"]["structuredContent"]["untrusted_evidence"][
            "selected_record"
        ]["data"]["period"]
        == 4
    )
    assert "registers" not in json.dumps(result["explained"])
    assert result["selected"]["selection"]["id"] == "modules:0"
    assert result["stale"]["isError"] is True
    assert result["foreign"]["isError"] is True


@pytest.mark.parametrize(
    "tool", ["vera_workspace_save", "vera_workspace_apply", "vera_workspace_draft_save"]
)
def test_native_lipe_refuses_generic_mutation_without_domain_api(initial_lipe, tool):
    env, output, _ = initial_lipe
    result = rpc_program(
        env,
        CALCULATE
        + f"""
const selected=payload(call('vera_workspace_view',{{work_ref:'initial-lipe', source_ref:calculated.source_ref,item_id:'modules:0'}}));
const result=call('{tool}',{{work_ref: selected.work_ref, revision:selected.revision, review_ticket:selected.review_ticket, item_id:'modules:0', source_ref:calculated.source_ref, ...( '{tool}' === 'vera_workspace_draft_save' ? {{fields:{{}}}} : {{human_reviewed:true,idempotency_key:'forbidden-write'}})}});
""",
    )
    assert result["isError"] is True
    assert "immutable" in result["content"][0]["text"]
    assert len(list(output.glob("lipe-*"))) == 1


@pytest.mark.parametrize("tamper", ["bytes", "extra", "symlink", "hardlink"])
def test_native_lipe_artifact_closure_refuses_changed_population(initial_lipe, tamper):
    env, output, _ = initial_lipe
    result = rpc_program(env, CALCULATE + "const result=calculated;")
    directory = output / result["source_ref"]
    file = directory / "workpaper.md"
    if tamper == "bytes":
        file.write_text("changed")
    elif tamper == "extra":
        (directory / "extra.txt").write_text("extra")
    elif tamper == "hardlink":
        (directory / "linked.txt").hardlink_to(file)
    else:
        (directory / "linked.txt").symlink_to(file)
    refused = rpc_program(
        env, "const result=call('vera_workspace_lipe_setup',{work_ref:'initial-lipe'});"
    )
    assert refused["isError"] is True


def test_native_lipe_unknown_outputs_and_interrupted_requests_require_recovery(
    initial_lipe,
):
    env, output, binding = initial_lipe
    module = workspace_module()
    private = module.ui_state_directory(output)
    module.atomic_json(
        private / "lipe-request-uncertain.json", {"request_sha256": "unknown"}
    )
    result = rpc_program(
        env,
        "const result=payload(call('vera_workspace_lipe_setup',{work_ref:'initial-lipe'}));",
    )
    assert result["status"] == "recovery_required"
    assert result["can_write"] is False
    assert list(output.iterdir()) == []


def test_native_lipe_viewer_cannot_calculate(initial_lipe):
    env, output, _ = initial_lipe
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": "VIEWER"},
        SETUP + "const result=call('vera_workspace_lipe_calculate',args);",
    )
    assert result["isError"] is True
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("initial_lipe", ["two_cases"], indirect=True)
def test_native_lipe_preserves_previous_version_and_refuses_implicit_latest(
    initial_lipe,
):
    env, output, _ = initial_lipe
    result = rpc_program(
        env,
        CALCULATE
        + """
const next = payload(call('vera_workspace_lipe_setup',{work_ref:'initial-lipe'}));
const second = payload(call('vera_workspace_lipe_calculate',{...args, revision:next.revision, review_ticket:next.review_ticket, case_input_id:next.items.find(row=>row.id!==args.case_input_id).id, idempotency_key:'second-case'}));
const implicit = call('vera_workspace_view',{work_ref:'initial-lipe'});
const old = payload(call('vera_workspace_view',{work_ref:'initial-lipe',revision:view.revision,source_ref:calculated.source_ref,item_id:'modules:0'}));
const result = {calculated, second, implicit, old};
""",
    )
    assert len(list(output.glob("lipe-*"))) == 2
    assert result["second"]["status"] == "BLOCKED"
    assert result["old"]["selection"]["data"]["rows"]["vp14_debit"] == "110.00"
    assert result["implicit"]["isError"] is True


@pytest.mark.parametrize("initial_lipe", ["catalog"], indirect=True)
def test_native_lipe_missing_bound_catalog_blocks_without_manual_fallback(initial_lipe):
    env, output, _ = initial_lipe
    result = rpc_program(env, CALCULATE + "const result=calculated;")
    produced = json.loads((output / result["source_ref"] / "result.json").read_bytes())
    assert "CATALOG_NOT_AVAILABLE" in produced["blockers"]
    assert produced["modules"] == []
    assert produced["export_status"] == "NOT_AUTHORIZED"


def test_native_lipe_reused_request_key_rejects_changed_choice(initial_lipe):
    env, output, _ = initial_lipe
    result = rpc_program(
        env,
        CALCULATE
        + "const result=call('vera_workspace_lipe_calculate',{...args,case_input_id:'foreign-case'});",
    )
    assert result["isError"] is True
    assert "different request" in result["content"][0]["text"]
    assert len(list(output.glob("lipe-*"))) == 1


def test_native_lipe_changed_registered_source_refuses_read(initial_lipe):
    env, _, binding = initial_lipe
    rpc_program(env, CALCULATE + "const result=calculated;")
    loaded = _load_customer_ledger().load_run(
        Path(binding["client_root"]), binding["engagement_id"], binding["run_id"]
    )
    source = next(
        Path(row["path"])
        for row in loaded["context"]["input_bindings"]
        if Path(row["path"]).suffix == ".txt"
    )
    source.write_text("changed fictional source")
    refused = rpc_program(
        env, "const result=call('vera_workspace_lipe_setup',{work_ref:'initial-lipe'});"
    )
    assert refused["isError"] is True


def test_native_lipe_interrupted_execution_retains_intent_and_refuses_replay(
    initial_lipe, monkeypatch
):
    import subprocess

    import native_lipe

    _, output, _ = initial_lipe
    module = workspace_module()
    original = native_lipe.engine_call

    def interrupted(root, request):
        if request["operation"] == "calculate":
            raise subprocess.TimeoutExpired("fictional LIPE", 90)
        return original(root, request)

    monkeypatch.setattr(native_lipe, "engine_call", interrupted)
    setup = module.dispatch("vera_workspace_lipe_setup", {"work_ref": "initial-lipe"})
    args = {
        "work_ref": "initial-lipe",
        "revision": setup["revision"],
        "case_input_id": setup["items"][0]["id"],
        "human_reviewed": True,
        "idempotency_key": "interrupted-test",
    }
    with pytest.raises(subprocess.TimeoutExpired):
        module.dispatch("vera_workspace_lipe_calculate", args)
    with pytest.raises(ValueError, match="Interrupted LIPE"):
        module.dispatch("vera_workspace_lipe_calculate", args)
    after = module.dispatch("vera_workspace_lipe_setup", {"work_ref": "initial-lipe"})
    assert after["status"] == "recovery_required"
    assert after["can_write"] is False
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_native_lipe_fresh_extracted_package_executes_unchanged_calculation(
    initial_lipe, surface, tmp_path
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, output, _ = initial_lipe
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
        CALCULATE + "const result={calculated,view};",
        server=target / "mcp/workspace.cjs",
    )
    assert result["calculated"]["status"] == "DRAFT_FOR_REVIEW"
    assert result["view"]["data"]["export_status"] == "NOT_AUTHORIZED"
    assert (output / result["calculated"]["source_ref"] / "summary.pdf").is_file()
    assert (target / "scripts/native_lipe_bridge.py").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_lipe_bridge.py"
    ).read_bytes()
    assert (target / "modules/lipe/scripts/lipe_core.py").read_bytes() == (
        ROOT / "plugins/lipe/scripts/lipe_core.py"
    ).read_bytes()


def test_native_lipe_file_paths_require_exact_closed_calculation(initial_lipe):
    env, output, _ = initial_lipe
    result = rpc_program(
        env,
        CALCULATE
        + """
const listed = call('vera_workspace_outputs',{work_ref:'initial-lipe',revision:view.revision,source_ref:calculated.source_ref});
const implicit = call('vera_workspace_outputs',{work_ref:'initial-lipe'});
const stale = call('vera_workspace_outputs',{work_ref:'initial-lipe',revision:'f'.repeat(64),source_ref:calculated.source_ref});
const result={listed,implicit,stale,calculated};
""",
    )
    files = result["listed"]["_meta"]["workspace"]
    assert files["status"] == "unfinalized_calculation"
    assert {item["name"] for item in files["outputs"]} == {
        p.name for p in (output / result["calculated"]["source_ref"]).iterdir()
    }
    assert "summary.pdf" in {item["name"] for item in files["outputs"]}
    assert str(output) not in json.dumps(result["listed"]["structuredContent"])
    assert result["implicit"]["isError"] is True
    assert result["stale"]["isError"] is True
