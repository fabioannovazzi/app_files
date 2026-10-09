"""Initial bank preparation through real ledger files and public MCP transactions."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_archive_navigation import archive_cli
from tests.plugins.test_vera_native_workspace import ROOT, configure, workspace_module


@pytest.fixture
def initial_bank(tmp_path, monkeypatch, request):
    ledger = _load_customer_ledger()
    folder = tmp_path / "Fictional customer"
    folder.mkdir()
    client = "client_111111111111111111111111"
    ledger.create_client_manifest(folder, client)
    engagement = ledger.create_engagement(folder, client, "Fictional bank review")
    ids = []
    options = getattr(request, "param", {})
    for side in ("bank", "journal"):
        for part in range(options.get("parts", 1)):
            extension = options.get("format", "csv") if side == "bank" else "csv"
            source = tmp_path / (
                side + (("-" + str(part)) if part else "") + "." + extension
            )
            rows = [
                ["Date", "Amount", "Reference", "Description"],
                *[
                    [
                        "2025-03-10",
                        "80.00",
                        "ABC" + str(part) + str(index),
                        "Fictional " + side + " transfer",
                    ]
                    for index in range(options.get("rows", 1))
                ],
            ]
            if extension == "xlsx":
                from openpyxl import Workbook

                workbook = Workbook()
                for row in rows:
                    workbook.active.append(row)
                workbook.save(source)
            elif extension == "pdf":
                from tests.plugins.test_journal_bank_reconciliation_plugin import (
                    _write_unruled_pdf_line,
                )

                _write_unruled_pdf_line(source, "2025-03-10 80.00 Fictional transfer")
            else:
                delimiter = options.get("delimiter", ",") if side == "bank" else ","
                source.write_text("\n".join(delimiter.join(row) for row in rows) + "\n")
            imported = ledger.import_document(
                folder, client, engagement["engagement_id"], source, "source"
            )
            ids.append(imported["receipt"]["input_id"])
    prepared = ledger.prepare_run(
        folder,
        client,
        engagement["engagement_id"],
        "journal-bank-reconciliation",
        "test-version",
        input_ids=ids,
    )
    running = ledger.start_run(
        folder, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    binding = {
        "work_ref": "initial-bank",
        "client_root": str(folder),
        "client_id": client,
        "engagement_id": engagement["engagement_id"],
        "run_id": prepared["run"]["run_id"],
        "workflow_id": "journal-bank-reconciliation",
    }
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    return env, Path(running["output_dir"]), binding


INITIAL = """
const scopeBank = state => ({work_ref:state.work_ref, revision:state.revision, review_ticket:state.review_ticket, human_reviewed:true});
const initial = payload(call('vera_workspace_bank_setup', {work_ref:'initial-bank'}));
const inspectArgs = {...scopeBank(initial), bank_input_ids:initial.items.filter(row => row.title.startsWith('bank')).map(row=>row.id), journal_input_ids:initial.items.filter(row => row.title.startsWith('journal')).map(row=>row.id), language:'it', document_language:'auto', idempotency_key:'fictional-inspect'};
const inspected = payload(call('vera_workspace_bank_inspect', inspectArgs));
const page = payload(call('vera_workspace_bank_setup', {work_ref:'initial-bank'}));
"""

REVIEW = """
const proposal = structuredClone(page.proposal);
proposal.policy.default_currency = 'CHF';
proposal.policy.default_entity_ref = 'fictional-company';
const reviewed = payload(call('vera_workspace_bank_review', {...scopeBank(page), proposal_json:JSON.stringify(proposal), idempotency_key:'fictional-review'}));
const ready = payload(call('vera_workspace_bank_setup', {work_ref:'initial-bank'}));
"""


def test_initial_bank_inspection_review_and_execution_keep_engine_gates(initial_bank):
    env, output, _ = initial_bank
    result = rpc_program(
        env,
        INITIAL
        + REVIEW
        + """
const reconciled = payload(call('vera_workspace_bank_reconcile', {...scopeBank(ready), idempotency_key:'fictional-reconcile'}));
const view = payload(call('vera_workspace_view', {work_ref:'initial-bank'}));
const result = {initial, inspected, page, reviewed, ready, reconciled, view};
""",
    )
    assert result["page"]["proposal"]["policy"]["default_currency"] is None
    assert result["ready"]["can_execute"] is True
    assert result["reconciled"]["matched"] == 1
    assert result["reconciled"]["professional_approval"] is False
    assert result["reconciled"]["run_completed"] is False
    assert result["view"]["workflow"] == "journal-bank-reconciliation"
    assert (output / "reconciliation/review_payload.json").is_file()
    recipe = next((output / "bank-preparation").glob("review-*/reviewed_recipe.json"))
    assert (
        json.loads(recipe.read_bytes())["relationship"]["decision"]["reviewer_ref"]
        == "fictional-reviewer"
    )


@pytest.mark.parametrize(
    "change",
    [
        "review_ticket:'forged.signature'",
        "revision:'f'.repeat(64)",
        "human_reviewed:false",
        "bank_input_ids:[]",
        "journal_input_ids:inspectArgs.bank_input_ids",
        "bank_input_ids:['foreign-input']",
        "bank_input_ids:[...inspectArgs.bank_input_ids, ...inspectArgs.bank_input_ids]",
        "sample_input_id:inspectArgs.bank_input_ids[0]",
        "bank_path:'/private/another-client.csv'",
        "language:'xx'",
        "document_language:'xx'",
    ],
)
def test_initial_bank_invalid_selection_or_authority_keeps_outputs_empty(
    initial_bank, change
):
    env, output, _ = initial_bank
    result = rpc_program(
        env,
        INITIAL.split("const inspected =")[0]
        + "const result = call('vera_workspace_bank_inspect', {...inspectArgs, "
        + change
        + "});",
    )
    assert result["isError"] is True
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("role", ["VIEWER", ""])
def test_initial_bank_viewer_reads_labels_but_cannot_inspect(initial_bank, role):
    env, output, _ = initial_bank
    result = rpc_program(
        {**env, "VERA_WORKSPACE_ROLES": role},
        INITIAL.split("const inspected =")[0]
        + "const result = {initial, write:call('vera_workspace_bank_inspect', inspectArgs)};",
    )
    assert result["initial"]["can_write"] is False
    assert result["write"]["isError"] is True
    assert list(output.iterdir()) == []


def test_initial_bank_identical_inspection_retry_keeps_one_generation(initial_bank):
    env, output, _ = initial_bank
    result = rpc_program(
        env,
        INITIAL
        + """
const retry = payload(call('vera_workspace_bank_inspect', inspectArgs));
const changed = call('vera_workspace_bank_inspect', {...inspectArgs, language:'fr'});
const early = call('vera_workspace_bank_reconcile', {...scopeBank(page), idempotency_key:'early'});
const stale = call('vera_workspace_bank_setup', {work_ref:'initial-bank', revision:initial.revision});
const result = {inspected, retry, changed, early, stale};
""",
    )
    assert result["retry"] == result["inspected"]
    assert result["changed"]["isError"] is True
    assert result["early"]["isError"] is True
    assert result["stale"]["isError"] is True
    assert len(list((output / "bank-preparation").glob("inspect-*"))) == 1
    assert not (output / "reconciliation").exists()


@pytest.mark.parametrize(
    "change",
    [
        "proposal.policy.allow_evidence_reuse = true;",
        "proposal.policy.require_same_currency = false;",
        "proposal.policy.require_same_unit = false;",
        "proposal.policy.relationship_shape = 'unknown';",
        "delete proposal.bank[Object.keys(proposal.bank)[0]];",
        "proposal.bank[Object.keys(proposal.bank)[0]].mapping_decision = {status:'reviewed'};",
    ],
)
def test_initial_bank_invalid_professional_review_can_be_corrected_without_overwrite(
    initial_bank, change
):
    env, output, _ = initial_bank
    result = rpc_program(
        env,
        INITIAL
        + """
const proposal = structuredClone(page.proposal);
"""
        + change
        + """
const refused = call('vera_workspace_bank_review', {...scopeBank(page), proposal_json:JSON.stringify(proposal), idempotency_key:'invalid-review'});
const recovered = payload(call('vera_workspace_bank_setup', {work_ref:'initial-bank'}));
const corrected = structuredClone(recovered.proposal);
corrected.policy.default_currency = 'CHF'; corrected.policy.default_entity_ref = 'fictional-company';
const reviewed = payload(call('vera_workspace_bank_review', {...scopeBank(recovered), proposal_json:JSON.stringify(corrected), idempotency_key:'corrected-review'}));
const result = {refused, recovered, reviewed};
""",
    )
    assert result["refused"]["isError"] is True
    assert result["recovered"]["status"] == "inspected"
    assert result["recovered"]["can_write"] is True
    assert result["reviewed"]["qualification_status"] == "qualified"
    assert not (output / "reconciliation").exists()


@pytest.mark.parametrize(
    "initial_bank", [{"rows": 25}, {"format": "xlsx"}, {"parts": 2}], indirect=True
)
def test_initial_bank_selected_context_is_bounded_and_sources_are_exact_copies(
    initial_bank,
):
    env, output, _ = initial_bank
    result = rpc_program(
        env,
        INITIAL
        + """
const selected = payload(call('vera_workspace_bank_setup', {work_ref:'initial-bank', item_id:page.items[0].id, revision:page.revision}));
const explained = call('vera_workspace_bank_explain', {work_ref:'initial-bank', item_id:page.items[0].id, revision:page.revision});
const result = {initial, page, selected, explained};
""",
    )
    assert not result["explained"].get("isError"), result["explained"]
    source = result["explained"]["structuredContent"]["source"]
    assert len(source["preview"]) <= 20
    assert "row_dispositions" not in json.dumps(source)
    assert "transaction_id" not in json.dumps(source)
    assert "source_row" not in json.dumps(source)
    assert "reference" not in source["preview"][0]
    assert source["source_file"] in {
        row["title"]
        for row in result["initial"]["items"]
        if row["title"].startswith("bank")
    }
    assert len(result["page"]["items"]) == len(result["initial"]["items"])
    assert all(
        path.stat().st_nlink == 1
        for path in (output / "bank-preparation/sources").rglob("*")
        if path.is_file()
    )
    assert source["side"] == "bank"


@pytest.mark.parametrize(
    "change", ["copy", "extra", "generation", "ancestor_link", "hardlink", "original"]
)
def test_initial_bank_source_or_inspection_tamper_refuses_read(initial_bank, change):
    env, output, binding = initial_bank
    rpc_program(env, INITIAL + "const result = inspected;")
    source = next((output / "bank-preparation/sources/bank").rglob("*.csv"))
    if change == "copy":
        source.write_text("changed")
    elif change == "extra":
        (source.parent / "extra.csv").write_text("extra")
    elif change == "generation":
        next(
            (output / "bank-preparation").glob("inspect-*/inspection.json")
        ).write_text("{}")
    elif change == "ancestor_link":
        directory = output / "bank-preparation"
        destination = output.parent / "relocated-preparation"
        directory.rename(destination)
        directory.symlink_to(destination, target_is_directory=True)
    elif change == "hardlink":
        (output.parent / "alias.csv").hardlink_to(source)
    else:
        service = workspace_module()
        loaded = service.load_binding(binding)
        row = loaded["input_manifest"]["inputs"][0]
        (Path(loaded["run_root"]) / row["execution_relative_path"]).write_text(
            "changed"
        )
    result = rpc_program(
        env,
        "const result = call('vera_workspace_bank_setup', {work_ref:'initial-bank'});",
    )
    assert result["isError"] is True
    assert not (output / "reconciliation").exists()


@pytest.mark.parametrize("initial_bank", [{"format": "pdf"}], indirect=True)
def test_initial_bank_unsupported_pdf_retains_diagnostics_and_refuses_execution(
    initial_bank,
):
    env, output, _ = initial_bank
    result = rpc_program(
        env,
        INITIAL
        + """
const execute = call('vera_workspace_bank_reconcile', {...scopeBank(page), idempotency_key:'blocked-pdf'});
const result = {inspected, page, execute};
""",
    )
    assert result["inspected"]["qualification_status"] == "unsupported_source_layout"
    assert result["inspected"]["bank_rows"] == 0
    assert result["page"]["can_execute"] is False
    assert result["execute"]["isError"] is True
    assert next(
        (output / "bank-preparation").glob("inspect-*/source_qualifications.json")
    ).is_file()
    assert not (output / "reconciliation").exists()


@pytest.mark.parametrize(
    "initial_bank",
    [{"format": "xlsx"}, {"parts": 2}, {"delimiter": ";"}],
    indirect=True,
)
def test_initial_bank_reviewed_multiple_and_nondefault_sources_execute_public_engine(
    initial_bank,
):
    env, output, _ = initial_bank
    result = rpc_program(
        env,
        INITIAL
        + REVIEW
        + """
const result = payload(call('vera_workspace_bank_reconcile', {...scopeBank(ready), idempotency_key:'multiple-reconcile'}));
""",
    )
    assert result["matched"] == (
        2
        if len(list((output / "bank-preparation/sources/bank").rglob("*.*"))) == 2
        else 1
    )
    assert result["unmatched_bank"] == 0
    assert result["unmatched_journal"] == 0
    assert (output / "reconciliation/journal_bank_reconciliation.xlsx").is_file()


def test_initial_bank_owned_archive_catalogue_exposes_setup_and_executes_exact_run(
    initial_bank, tmp_path
):
    env, output, binding = initial_bank
    env = {key: value for key, value in env.items() if key != "VERA_WORKSPACE_BINDINGS"}
    env.update(
        VERA_STUDIO_ARCHIVE_SESSION_ID="fictional-bank-owned",
        VERA_STUDIO_ARCHIVE_STATE_DIR=str(
            tmp_path.with_name(tmp_path.name + "-private-archive")
        ),
    )
    archive_cli(
        env, "configure", "--archive-root", str(Path(binding["client_root"]).parent)
    )
    prefix = """
const catalog = payload(call('vera_workspace_open', {client_id:CLIENT, engagement_id:ENGAGEMENT}));
const work = catalog.works[0];
""".replace(
        "CLIENT", json.dumps(binding["client_id"])
    ).replace(
        "ENGAGEMENT", json.dumps(binding["engagement_id"])
    )
    result = rpc_program(
        env,
        prefix
        + INITIAL.replace("'initial-bank'", "work.work_ref")
        + REVIEW.replace("'initial-bank'", "work.work_ref")
        + """
const reconciled = payload(call('vera_workspace_bank_reconcile', {...scopeBank(ready), idempotency_key:'owned-reconcile'}));
const result = {work, reconciled};
""",
    )
    assert result["work"]["setup_available"] is True
    assert result["work"]["review_available"] is False
    assert result["reconciled"]["matched"] == 1
    assert (output / "reconciliation/review_payload.json").is_file()


def test_initial_bank_execution_timeout_retains_uncertain_intent_and_refuses_retry(
    initial_bank, monkeypatch
):
    env, output, binding = initial_bank
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    import native_bank_preparation as preparation

    service = workspace_module()
    initial = service.dispatch(
        "vera_workspace_bank_setup", {"work_ref": binding["work_ref"]}
    )
    args = {
        "work_ref": binding["work_ref"],
        "revision": initial["revision"],
        "human_reviewed": True,
        "idempotency_key": "timeout",
        "language": "it",
        "document_language": "auto",
        "bank_input_ids": [initial["items"][0]["id"]],
        "journal_input_ids": [initial["items"][1]["id"]],
    }
    original_call = preparation.engine_call

    def timeout_execution(root, request):
        if request["operation"] == "implementation":
            return original_call(root, request)
        raise subprocess.TimeoutExpired("fictional-bank-worker", 90)

    monkeypatch.setattr(preparation, "engine_call", timeout_execution)
    with pytest.raises(subprocess.TimeoutExpired):
        service.dispatch("vera_workspace_bank_inspect", args)
    recovered = service.dispatch(
        "vera_workspace_bank_setup", {"work_ref": binding["work_ref"]}
    )
    with pytest.raises(ValueError, match="outcome needs verification"):
        service.dispatch("vera_workspace_bank_inspect", args)
    assert recovered["status"] == "recovery_required"
    assert recovered["can_write"] is False
    assert len(list((output / "bank-preparation/sources").rglob("*.csv"))) == 2
    assert not (output / "reconciliation").exists()


@pytest.mark.parametrize("surface", ["codex", "cowork"])
def test_initial_bank_fresh_extracted_package_executes_and_retains_customer_files(
    initial_bank, tmp_path, surface
):
    from tests.plugins.test_packaged_mcp_startup import load_builder

    env, output, _ = initial_bank
    if surface == "codex":
        builder = load_builder("build_codex_plugin_zip")
        vera = next(
            package for package in builder.load_bundles() if package.name == "vera"
        )
        entries = builder.expected_zip_entries(vera)
        prefix = vera.package_root + "/plugins/vera/"
    else:
        builder = load_builder("build_claude_plugin_zip")
        _, packages = builder.load_configuration()
        vera = next(package for package in packages if package.plugin == "vera")
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
        INITIAL
        + REVIEW
        + """
const reconciled = payload(call('vera_workspace_bank_reconcile', {...scopeBank(ready), idempotency_key:'extracted-reconcile'}));
const view = payload(call('vera_workspace_view', {work_ref:'initial-bank'}));
const result = {reconciled, view};
""",
        server=target / "mcp/workspace.cjs",
    )
    assert result["reconciled"]["matched"] == 1
    assert result["view"]["workflow"] == "journal-bank-reconciliation"
    assert (output / "reconciliation/journal_bank_reconciliation.xlsx").is_file()
    assert (target / "scripts/native_bank_preparation.py").read_bytes() == (
        ROOT / "plugins/vera/scripts/native_bank_preparation.py"
    ).read_bytes()
