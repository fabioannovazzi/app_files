"""Verify producer evidence through real Journal–Bank operations."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests._plugin_cli import workflow_cli
from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
    start,
)

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "plugins/journal-bank-reconciliation/scripts"
)


def run_cli(name, loaded, *arguments):
    completed = subprocess.run(
        [
            *workflow_cli(SCRIPTS / name),
            *map(str, arguments),
            "--output-dir",
            loaded.get("calculation_dir", loaded["output_dir"]),
            "--client-engagement",
            str(Path(loaded["run_root"]) / "context.json"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return completed


@pytest.fixture
def reconciled_case(archive_core, client_case, tmp_path, request):
    reviewed_balances = getattr(request, "param", None) in {
        "reviewed_balances",
        "reviewed_balances_copied",
    }
    sources = {
        "bank": (
            "2026-10-05,500.00,Receipt,INV01,LOCAL_BANK_ONE\n"
            "2026-10-06,-200.00,Payment,PAY01,LOCAL_BANK_TWO\n"
            "2026-10-07,-5.00,Bank fee,FEE01,LOCAL_BANK_THREE\n"
        ),
        "journal": (
            "2026-10-05,500.00,Receipt,INV01,LOCAL_JOURNAL_ONE\n"
            "2026-10-06,-200.00,Payment,PAY01,LOCAL_JOURNAL_TWO\n"
        ),
    }
    header = "date,amount,description,reference,private_note\n"
    if reviewed_balances:
        header = (
            "date,amount,description,reference,private_note,beneficiary,"
            "currency,unit,entity_ref,party_ref,opening_balance,balance\n"
        )
        sources = {
            "bank": (
                "2026-10-05,500.00,Receipt,INV01,LOCAL_BANK_ONE,Customer,EUR,currency,entity.test,party.test,1000,1500\n"
                "2026-10-06,-200.00,Payment,PAY01,LOCAL_BANK_TWO,Supplier,EUR,currency,entity.test,party.test,1000,1300\n"
                "2026-10-07,-5.00,Bank fee,FEE01,LOCAL_BANK_THREE,Bank,EUR,currency,entity.test,party.test,1000,1295\n"
            ),
            "journal": (
                "2026-10-05,500.00,Receipt,INV01,LOCAL_JOURNAL_ONE,Customer,EUR,currency,entity.test,party.test,1000,1500\n"
                "2026-10-06,-200.00,Payment,PAY01,LOCAL_JOURNAL_TWO,Supplier,EUR,currency,entity.test,party.test,1000,1300\n"
            ),
        }
    imported = []
    for side, rows in sources.items():
        source = tmp_path / f"{side}.csv"
        source.write_text(header + rows)
        imported.append(
            archive_core.import_studio_client_document(
                client_case.client_id,
                source,
                "journal" if side == "journal" else "source",
                engagement_id=client_case.engagement_id,
                state_dir=client_case.state_dir,
            )
        )
    prepared = archive_core.prepare_studio_client_workflow(
        client_case.engagement_id,
        "journal-bank-reconciliation",
        input_ids=[item["input_id"] for item in imported],
        state_dir=client_case.state_dir,
    )
    run_id = prepared["run"]["run_id"]
    archive_core.start_studio_client_workflow(
        client_case.client_id,
        client_case.engagement_id,
        run_id,
        state_dir=client_case.state_dir,
    )
    loaded = archive_core.ledger.load_run(
        client_case.client_root, client_case.engagement_id, run_id
    )
    loaded["calculation_dir"] = str(Path(loaded["output_dir"]) / "reconciliation")
    bound = [item["path"] for item in loaded["context"]["input_bindings"]]
    run_cli("inspect_inputs.py", loaded, *bound)
    output = Path(loaded["calculation_dir"])
    recipe_path = output / "suggested_recipe.json"
    recipe = json.loads(recipe_path.read_text())
    decisions = {
        "reviewer_ref": "agent.test",
        "reviewed_on": "2026-10-20",
        "relationship": recipe["relationship"]["policy"],
    }
    for side in sources:
        decisions[side] = {
            "files": {
                name: {
                    key: file_recipe.get(key)
                    for key in (
                        "header_rows",
                        "mapping",
                        "excluded_monetary_columns",
                        "date_convention",
                    )
                }
                for name, file_recipe in recipe[side]["files"].items()
            }
        }
    decisions_path = output / "agent_decisions.json"
    if reviewed_balances:
        for side in sources:
            for choice in decisions[side]["files"].values():
                choice["excluded_monetary_columns"] = ["opening_balance", "balance"]
    if getattr(request, "param", None) == "reviewed_balances_copied":
        for side in sources:
            for name, choice in decisions[side]["files"].items():
                choice["potential_monetary_columns"] = recipe[side]["files"][name][
                    "potential_monetary_columns"
                ]
    decisions_path.write_text(json.dumps(decisions))
    if getattr(request, "param", None) == "modified_recipe":
        recipe["unregistered_note"] = "Extra case data outside producer metadata"
        recipe_path.write_text(json.dumps(recipe))
    run_cli(
        "seal_review_receipts.py",
        loaded,
        "--recipe",
        recipe_path,
        "--decisions",
        decisions_path,
    )
    run_cli("run_reconciliation.py", loaded, *bound, "--recipe", recipe_path)
    return loaded


def test_calculation_audit_and_status_have_complete_input_lineage(reconciled_case):
    from archive_reporting import read_artifact, snapshot_run

    loaded = reconciled_case
    output = Path(loaded["calculation_dir"])
    for name in (
        "reconciliation_audit.json",
        "input_receipts.json",
        "source_qualifications.json",
        "assurance_gates.json",
        "review_notes.md",
        "suggested_recipe.json",
    ):
        read_artifact(loaded, output / name)
    audit = json.loads((output / "reconciliation_audit.json").read_text())
    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())

    assert audit["matched_count"] == 2
    assert audit["unmatched_bank_count"] == 1
    assert report["collection_status"] == "complete", report["errors"]
    inputs = [item for item in report["sources"] if item["role"] == "input"]
    assert sum(item["sent_cells"] for item in inputs) == 20
    assert sum(item["not_sent_cells"] for item in inputs) == 5


@pytest.mark.parametrize(
    "reconciled_case",
    ["reviewed_balances", "reviewed_balances_copied"],
    indirect=True,
)
def test_reviewed_balance_exclusions_preserve_preview_and_recipe_provenance(
    reconciled_case,
):
    from archive_reporting import read_artifact, snapshot_run

    loaded = reconciled_case
    output = Path(loaded["calculation_dir"])
    read_artifact(loaded, output / "suggested_recipe.json")
    read_artifact(loaded, output / "reconciliation_audit.json")
    audit = json.loads((output / "reconciliation_audit.json").read_text())
    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())

    assert audit["matched_count"] == 2
    assert audit["unmatched_bank_count"] == 1
    assert report["collection_status"] == "complete", report["errors"]
    inputs = [item for item in report["sources"] if item["role"] == "input"]
    assert sum(item["sent_cells"] for item in inputs) == 45
    assert sum(item["not_sent_cells"] for item in inputs) == 15


@pytest.mark.parametrize("reconciled_case", ["modified_recipe"], indirect=True)
def test_sealing_does_not_certify_unknown_recipe_content(reconciled_case):
    from archive_reporting import read_artifact, snapshot_run

    loaded = reconciled_case
    read_artifact(loaded, Path(loaded["calculation_dir"]) / "suggested_recipe.json")
    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())

    assert report["collection_status"] == "incomplete"
    assert any(
        error.startswith("derived_output_lineage_unavailable:")
        for error in report["errors"]
    )


def test_edited_review_cannot_reuse_known_transaction_origins(reconciled_case):
    from archive_emit import record_output
    from archive_report_store import digest
    from archive_reporting import snapshot_run

    loaded = reconciled_case
    review = json.loads(
        (Path(loaded["calculation_dir"]) / "review_payload.json").read_text()
    )
    item = next(
        item for item in review["items"] if item["item_type"] == "unmatched_bank"
    )
    item["data"]["description"] = "Extra case data from outside the source"
    payload = {
        "structuredContent": {"description": item["data"]["description"]},
        "_meta": {
            "vera_source_review_sha256": digest(review),
            "vera_source_records": [
                {
                    "record_id": item["data"]["transaction_id"],
                    "fields": ["description"],
                }
            ],
        },
    }

    record_output(
        "journal-bank-reconciliation",
        {"output_dir": loaded["output_dir"]},
        payload,
        channel="mcp",
    )
    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())

    assert report["collection_status"] == "incomplete"
    assert "sent_data_has_no_source_coordinates" in report["errors"]
    assert (
        sum(item["sent_cells"] for item in report["sources"] if item["role"] == "input")
        == 0
    )


@pytest.mark.parametrize(
    ("item_type", "exact_identifiers", "expected_cells"),
    [
        ("unmatched_bank", False, 3),
        ("unmatched_bank", True, 4),
        ("matched_pair", False, 4),
        ("matched_pair", True, 6),
    ],
)
def test_mcp_records_only_selected_case_fields(
    reconciled_case, tmp_path, item_type, exact_identifiers, expected_cells
):
    from archive_reporting import snapshot_run

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the real MCP transport.")
    loaded = reconciled_case
    output = Path(loaded["calculation_dir"])
    vera = SCRIPTS.parents[1] / "vera"
    launcher = tmp_path / "bridge.cjs"
    launcher.write_text(
        "const {spawn}=require('node:child_process');\n"
        f"const {{bridge}}=require({json.dumps(str(vera / 'scripts/archive_emission_mcp.cjs'))});\n"
        f"const child=spawn(process.execPath,[{json.dumps(str(SCRIPTS.parent / 'mcp/server.cjs'))}],{{stdio:['pipe','pipe','inherit']}});\n"
        f"bridge(child,'journal-bank-reconciliation',{json.dumps(str(vera))});\n"
    )
    with subprocess.Popen(
        [node, str(launcher)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "VERA_REPORTING_PYTHON": sys.executable},
    ) as process:

        def call(number, name, arguments):
            process.stdin.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": number,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    }
                )
                + "\n"
            )
            process.stdin.flush()
            response = json.loads(process.stdout.readline())
            assert not response["result"].get("isError"), response
            return response["result"]["structuredContent"]

        index = call(
            1,
            "validate_journal_bank_review",
            {
                "review_payload_path": str(output / "review_payload.json"),
                "client_engagement": str(Path(loaded["run_root"]) / "context.json"),
            },
        )
        before = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())
        assert before["collection_status"] == "complete", before["errors"]
        assert (
            sum(
                item["sent_cells"]
                for item in before["sources"]
                if item["role"] == "input"
            )
            == 0
        )
        handle = next(
            item["case_handle"]
            for item in index["model_context_index"]["cases"]
            if item["item_type"] == item_type
        )
        selected = call(
            2,
            "get_journal_bank_case_context",
            {
                "persistence_token": index["review_reference"]["persistence_token"],
                "case_handles": [handle],
                "include_exact_identifiers": exact_identifiers,
            },
        )
        process.stdin.close()
        process.wait(timeout=10)

    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())
    assert selected["case_count"] == 1
    assert report["collection_status"] == "complete", report["errors"]
    inputs = [item for item in report["sources"] if item["role"] == "input"]
    assert sum(item["sent_cells"] for item in inputs) == expected_cells
    assert sum(item["not_sent_cells"] for item in inputs) == 25 - expected_cells


def run_worker_case(
    loaded, monkeypatch, tmp_path, *, native_execution=False, run_pipeline=False
):
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _mock_semantic_worker_runtime,
        load_core,
        load_semantic_review,
    )

    load_core()
    if native_execution:
        monkeypatch.setenv("VERA_REPORTING_INTERNAL", "1")
    semantic = load_semantic_review()
    output = Path(loaded["calculation_dir"])
    worker_output = output.parent / "semantic-review"
    context = semantic.load_client_engagement_context_file(
        Path(loaded["run_root"]) / "context.json",
        expected_workflow_id="journal-bank-reconciliation",
    )
    prepared = semantic.prepare_semantic_review(
        output, worker_output, client_engagement=context
    )
    graph = json.loads(prepared["candidate_graph"].read_text())
    [component] = graph["selected_components"]
    [bank] = component["bank_records"]
    response = {
        "schema_version": "journal_bank.semantic_worker_response.v3",
        "candidate_graph_sha256": graph["candidate_graph_sha256"],
        "component_reviews": [
            {
                "component_id": component["component_id"],
                "decisions": [
                    {
                        "bank_transaction_id": bank["transaction_id"],
                        "journal_transaction_id": None,
                        "verdict": "needs_evidence",
                        "evidence_fields": ["description", "amount_signed"],
                        "rationale": "The fee has no journal entry in this packet.",
                        "contradictions": [],
                        "requested_evidence": ["Journal support for the fee"],
                        "resolution_level": "unresolved",
                        "classification": None,
                        "identified_counterparty": None,
                    }
                ],
            }
        ],
    }
    events = [
        {"type": "thread.started", "thread_id": "synthetic-fee-review"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "answer",
                "type": "agent_message",
                "text": json.dumps(response),
            },
        },
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]
    captured = _mock_semantic_worker_runtime(
        monkeypatch,
        semantic,
        tmp_path,
        {
            "return_code": 0,
            "stdout": "".join(json.dumps(event) + "\n" for event in events).encode(),
            "stderr": b"",
            "duration_ms": 1,
        },
    )

    if run_pipeline:
        result = semantic.run_semantic_resolution_pipeline(
            output, worker_output, client_engagement=context
        )
    else:
        result = semantic.run_semantic_worker(
            output,
            worker_output,
            prepared["candidate_graph"],
            client_engagement=context,
        )
    return result, captured


@pytest.mark.skipif(
    sys.platform != "darwin", reason="Exercises the macOS worker launch path"
)
@pytest.mark.parametrize("native_execution", [False, True])
@pytest.mark.parametrize("read_receipts", [False, True])
def test_worker_submission_counts_only_the_unmatched_candidate(
    reconciled_case, monkeypatch, tmp_path, native_execution, read_receipts
):
    from archive_report_store import RunStore
    from archive_reporting import read_artifact, snapshot_run

    loaded = reconciled_case
    result, captured = run_worker_case(
        loaded,
        monkeypatch,
        tmp_path,
        native_execution=native_execution,
        run_pipeline=read_receipts,
    )
    if read_receipts:
        [batch] = result["batches"]
        read_artifact(loaded, batch["worker_run"])
        read_artifact(loaded, batch["launch_receipt"])
        read_artifact(
            loaded,
            result["resolution_application"].parent / "semantic_review_status.json",
        )
    response_path = (
        result["batches"][0]["worker_run"].with_name("luna_response.json")
        if read_receipts
        else result["response"]
    )

    assert response_path.is_file()
    assert "--model" in captured["command"]
    sends = [
        event
        for event in RunStore(Path(loaded["run_root"])).events()
        if event.get("channel", "").startswith("model_worker:")
    ]
    assert len(sends) == 1
    assert sends[0]["unmapped"] is False
    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())
    assert report["collection_status"] == "complete", report["errors"]
    inputs = [item for item in report["sources"] if item["role"] == "input"]
    assert sum(item["sent_cells"] for item in inputs) == 4
    assert sum(item["not_sent_cells"] for item in inputs) == 21


@pytest.mark.skipif(
    sys.platform != "darwin", reason="Exercises the macOS worker launch path"
)
@pytest.mark.parametrize("receipt_key", ["worker_run", "launch_receipt", "status"])
def test_edited_worker_receipt_cannot_reuse_producer_provenance(
    reconciled_case, monkeypatch, tmp_path, receipt_key
):
    from archive_reporting import read_artifact, snapshot_run

    loaded = reconciled_case
    result, _ = run_worker_case(loaded, monkeypatch, tmp_path, run_pipeline=True)
    [batch] = result["batches"]
    path = (
        result["resolution_application"].parent / "semantic_review_status.json"
        if receipt_key == "status"
        else batch[receipt_key]
    )
    receipt = json.loads(path.read_text())
    receipt["unregistered_note"] = "Case data added after receipt creation"
    path.write_text(json.dumps(receipt))

    read_artifact(loaded, path)
    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())

    assert report["collection_status"] == "incomplete"
    assert any(
        error.startswith("derived_output_lineage_unavailable:")
        for error in report["errors"]
    )


@pytest.mark.parametrize("read_preview", [False, True])
@pytest.mark.parametrize(
    ("source_rows", "sent_cells", "unsent_cells"),
    [(1, 3, 1), (30, 60, 60)],
)
def test_inspection_counts_mapped_preview_cells_only_after_delivery(
    archive_core,
    client_case,
    tmp_path,
    read_preview,
    source_rows,
    sent_cells,
    unsent_cells,
):
    from archive_reporting import read_artifact, snapshot_run

    source = tmp_path / "source.csv"
    source.write_text(
        "date,amount,description,private_note\n"
        + "2026-10-05,100.00,Receipt,LOCAL_ONLY\n" * source_rows
    )
    client_case.imported = archive_core.import_studio_client_document(
        client_case.client_id,
        source,
        "journal",
        engagement_id=client_case.engagement_id,
        state_dir=client_case.state_dir,
    )
    loaded = start(archive_core, client_case, "journal-bank-reconciliation")
    bound = loaded["context"]["input_bindings"][0]["path"]

    completed = subprocess.run(
        [
            *workflow_cli(SCRIPTS / "inspect_inputs.py"),
            bound,
            bound,
            "--output-dir",
            loaded["output_dir"],
            "--client-engagement",
            str(Path(loaded["run_root"]) / "context.json"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert f"INFO: bank_rows={source_rows}\n" in completed.stderr
    if read_preview:
        read_artifact(loaded, Path(loaded["output_dir"]) / "inspection.json")
    report = json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())
    assert report["collection_status"] == "complete", report["errors"]
    source_measure = next(item for item in report["sources"] if item["role"] == "input")
    assert source_measure["sent_cells"] == (sent_cells if read_preview else 0)
    assert source_measure["not_sent_cells"] == (
        unsent_cells if read_preview else source_measure["source_cells"]
    )
    assert report["sent_characters"] > 0
