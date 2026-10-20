"""Exercise a real three-invoice Archive run through the public review transport."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.open_item_reconciliation.test_reviewed_tabular_adapter import spec
from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
)

__all__: list[str] = []
PLUGIN = Path(__file__).resolve().parents[2] / "plugins/open-item-reconciliation"


@pytest.fixture
def reconciled_case(archive_core, client_case, tmp_path):
    sources = {
        "population.csv": (
            "InvoiceX;DateX;ValueX;DueX;PartyX;PrivateX\n"
            "F001;01/09/2026;1200.00;30/09/2026;Alfa;LOCAL_ONLY_1\n"
            "F002;05/09/2026;800.00;30/09/2026;Beta;LOCAL_ONLY_2\n"
            "F003;15/09/2026;500.00;15/10/2026;Gamma;LOCAL_ONLY_3\n"
        ),
        "bank.csv": (
            "InvoiceX;PostedX;ValueX;PartyX;PrivateX\n"
            "F001;05/10/2026;1200.00;Alfa;LOCAL_ONLY_4\n"
            "F002;10/10/2026;300.00;Beta;LOCAL_ONLY_5\n"
        ),
    }
    imported = []
    for name, text in sources.items():
        path = tmp_path / name
        path.write_text(text)
        imported.append(
            archive_core.import_studio_client_document(
                client_case.client_id,
                path,
                "source",
                engagement_id=client_case.engagement_id,
                state_dir=client_case.state_dir,
            )
        )
    prepared = archive_core.prepare_studio_client_workflow(
        client_case.engagement_id,
        "open-item-reconciliation",
        input_ids=[entry["input_id"] for entry in imported],
        purpose="PRIVATE_ENGAGEMENT_PURPOSE",
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
    decisions = {}
    for binding in loaded["context"]["input_bindings"]:
        path = Path(binding["path"])
        population = path.name == "population.csv"
        decision = spec(path, "open_items" if population else "bank_statement")
        decision["perimeter"]["party_ref"] = None
        decision["tabular"]["columns"]["party_ref"] = "PartyX"
        if population:
            decision["tabular"]["last_data_row"] = 4
            decision["tabular"]["columns"]["due_date"] = "DueX"
        else:
            del decision["tabular"]["columns"]["document_date"]
        decisions[str(path)] = decision
    assumptions = Path(loaded["output_dir"]) / "assumptions.json"
    assumptions.write_text(
        json.dumps(
            {
                "assurance_run_date": "2026-10-20",
                "scope_year": 2026,
                "cutoff_date": "2026-09-30",
                "post_cutoff_events_excluded": False,
                "reviewed_source_decisions": decisions,
            }
        )
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(PLUGIN / "scripts/raw_input_runner.py"),
            "--client-engagement",
            str(Path(loaded["run_root"]) / "context.json"),
            "--assumptions-json",
            str(assumptions),
            "--output-subdirectory",
            "reconciliation",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "ready_for_review"
    assert "PRIVATE_ENGAGEMENT_PURPOSE" not in completed.stdout
    loaded["calculation_dir"] = str(Path(loaded["output_dir"]) / "reconciliation")
    return loaded


@contextmanager
def review_transport(tmp_path):
    """Use the same owned emission bridge as installed Vera."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the real MCP transport.")
    vera = PLUGIN.parent / "vera"
    launcher = tmp_path / "bridge.cjs"
    launcher.write_text(
        "const {spawn}=require('node:child_process');\n"
        f"const {{bridge}}=require({json.dumps(str(vera / 'scripts/archive_emission_mcp.cjs'))});\n"
        f"const child=spawn(process.execPath,[{json.dumps(str(PLUGIN / 'mcp/server.cjs'))}],{{stdio:['pipe','pipe','inherit']}});\n"
        f"bridge(child,'open-item-reconciliation',{json.dumps(str(vera))});\n"
    )
    with subprocess.Popen(
        [node, str(launcher)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "VERA_REPORTING_PYTHON": sys.executable,
            "OPEN_ITEM_RECONCILIATION_PYTHON": sys.executable,
        },
    ) as process:

        def call(name, arguments):
            process.stdin.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    }
                )
                + "\n"
            )
            process.stdin.flush()
            response = json.loads(process.stdout.readline())
            assert not response["result"].get("isError"), response
            return response["result"]

        try:
            yield call
        finally:
            process.stdin.close()
            process.wait(timeout=15)


def report(loaded):
    from archive_reporting import snapshot_run

    return json.loads(Path(snapshot_run(loaded)["report_path"]).read_text())


def test_pending_review_counts_do_not_claim_source_cell_exposure(
    reconciled_case, tmp_path
):
    loaded = reconciled_case
    output = Path(loaded["calculation_dir"])
    with review_transport(tmp_path) as call:
        index = call(
            "validate_open_item_reconciliation_review",
            {
                "review_payload_path": str(output / "review_payload.json"),
                "client_engagement": str(Path(loaded["run_root"]) / "context.json"),
            },
        )["structuredContent"]
        rendered = call(
            "render_open_item_reconciliation_review",
            {
                "persistence_token": index["review_reference"]["persistence_token"],
            },
        )
        assert "review_payload" not in rendered["structuredContent"]
        assert (
            rendered["_meta"]["private_review_payload"]["review_payload"]["item_count"]
            == 8
        )
        handle = next(
            item["case_handle"]
            for item in index["model_context_index"]["cases"]
            if item["item_type"] == "check_exception"
        )
        selected = call(
            "get_open_item_reconciliation_case_context",
            {
                "persistence_token": index["review_reference"]["persistence_token"],
                "case_handles": [handle],
            },
        )["structuredContent"]

    assert selected["cases"][0]["semantic_fields"]["actual"] == 3
    measured = report(loaded)
    assert measured["collection_status"] == "complete", measured["errors"]
    assert (
        sum(
            entry["sent_cells"]
            for entry in measured["sources"]
            if entry["role"] == "input"
        )
        == 0
    )


@pytest.mark.parametrize("exact_identifiers,expected_cells", [(False, 6), (True, 7)])
def test_selected_partial_payment_has_exact_cells_and_retains_private_columns(
    reconciled_case, tmp_path, exact_identifiers, expected_cells
):
    loaded = reconciled_case
    output = Path(loaded["calculation_dir"])
    with review_transport(tmp_path) as call:
        index = call(
            "validate_open_item_reconciliation_review",
            {
                "review_payload_path": str(output / "review_payload.json"),
                "client_engagement": str(Path(loaded["run_root"]) / "context.json"),
            },
        )["structuredContent"]
        initial = report(loaded)
        assert initial["collection_status"] == "complete", initial["errors"]
        assert (
            sum(s["sent_cells"] for s in initial["sources"] if s["role"] == "input")
            == 0
        )
        partial = next(
            item["case_handle"]
            for item in index["model_context_index"]["cases"]
            if item["item_type"] == "manual_review"
        )
        selected = call(
            "get_open_item_reconciliation_case_context",
            {
                "persistence_token": index["review_reference"]["persistence_token"],
                "case_handles": [partial],
                "include_exact_identifiers": exact_identifiers,
            },
        )["structuredContent"]

    fields = selected["cases"][0]["semantic_fields"]
    assert fields["party_ref"] == "Beta"
    assert fields["allocated_amount"] == "300.00"
    assert fields["residual_amount"] == "500.00"
    assert fields["supporting_bank_date"] == "2026-10-10"
    assert "LOCAL_ONLY" not in json.dumps(selected)
    measured = report(loaded)
    assert measured["collection_status"] == "complete", measured["errors"]
    inputs = [entry for entry in measured["sources"] if entry["role"] == "input"]
    assert sum(entry["sent_cells"] for entry in inputs) == expected_cells
    assert sum(entry["not_sent_cells"] for entry in inputs) == 28 - expected_cells


def test_public_review_save_apply_keeps_notes_private_and_report_complete(
    reconciled_case, tmp_path
):
    loaded = reconciled_case
    output = Path(loaded["calculation_dir"])
    review = json.loads((output / "review_payload.json").read_text())
    checkpoint = json.loads((output / "assurance_receipts.json").read_text())[
        "content_sha256"
    ]
    args = {
        "client_engagement": str(Path(loaded["run_root"]) / "context.json"),
        **{
            key + "_path": str(output / (key + ".json"))
            for key in ("run_intake", "review_payload", "final_artifacts")
        },
        "decision_source": "codex_agent",
        "reviewer": "agent.test",
        "decisions": [
            {"item_id": item["id"], "action": "accept", "note": "PRIVATE_REVIEW_NOTE"}
            for item in review["items"]
            if item["id"].startswith("review:")
        ],
    }
    with review_transport(tmp_path) as call:
        index = call(
            "validate_open_item_reconciliation_review",
            {
                "review_payload_path": str(output / "review_payload.json"),
                "client_engagement": str(Path(loaded["run_root"]) / "context.json"),
            },
        )["structuredContent"]
        selected = call(
            "get_open_item_reconciliation_case_context",
            {
                "persistence_token": index["review_reference"]["persistence_token"],
                "case_handles": [
                    item["case_handle"]
                    for item in index["model_context_index"]["cases"]
                ],
            },
        )["structuredContent"]
        assert selected["case_count"] == 4
        saved = call("save_open_item_reconciliation_decisions", args)
        applied = call(
            "apply_open_item_reconciliation_decisions",
            {
                **args,
                "expected_predecessor_checkpoint": checkpoint,
            },
        )

    assert saved["structuredContent"]["decision_count"] == 3
    assert applied["structuredContent"]["decision_count"] == 3
    assert "PRIVATE_REVIEW_NOTE" not in json.dumps(saved["structuredContent"])
    assert "PRIVATE_REVIEW_NOTE" not in json.dumps(applied["structuredContent"])
    assert "PRIVATE_REVIEW_NOTE" in json.dumps(saved["_meta"]["private_review_payload"])
    assert "PRIVATE_REVIEW_NOTE" in json.dumps(
        applied["_meta"]["private_review_payload"]
    )
    measured = report(loaded)
    assert measured["collection_status"] == "complete", measured["errors"]

    # Complete the real producer -> public save/apply -> native regeneration
    # integration, retaining the original sources and predecessor snapshot.
    sources_before = {
        entry["path"]: Path(entry["path"]).read_bytes()
        for entry in loaded["context"]["input_bindings"]
    }
    history = output / "assurance_transition_history" / checkpoint
    retained_before = {
        str(path.relative_to(history)): path.read_bytes()
        for path in history.rglob("*")
        if path.is_file()
    }
    regenerated = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(PLUGIN.parent / "vera/scripts/native_open_item_bridge.py"),
            str(PLUGIN),
        ],
        input=json.dumps(
            {
                "operation": "regenerate",
                "output_dir": str(output),
                "context": str(Path(loaded["run_root"]) / "context.json"),
                "arguments": {"expected_predecessor_checkpoint": checkpoint},
            }
        ),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert regenerated.returncode == 0, regenerated.stderr
    summary = json.loads(regenerated.stdout)
    assert summary["regenerated"] is True
    assert summary["report_ready"] is True
    assert (
        json.loads((output / "final_artifacts.json").read_text())["status"]
        == "final_ready"
    )
    assert sources_before == {path: Path(path).read_bytes() for path in sources_before}
    assert retained_before == {
        str(path.relative_to(history)): path.read_bytes()
        for path in history.rglob("*")
        if path.is_file()
    }
    with review_transport(tmp_path) as call:
        call(
            "validate_open_item_reconciliation_review",
            {
                "review_payload_path": str(output / "review_payload.json"),
                "client_engagement": str(Path(loaded["run_root"]) / "context.json"),
            },
        )
    measured = report(loaded)
    assert measured["collection_status"] == "complete", measured["errors"]


@pytest.mark.parametrize("changed_field", ["amount", "review_notes"])
def test_edited_review_cannot_claim_the_producers_source_coordinates(
    reconciled_case, tmp_path, changed_field
):
    loaded = reconciled_case
    output = Path(loaded["calculation_dir"])
    path = output / "review_payload.json"
    review = json.loads(path.read_text())
    item = next(
        item for item in review["items"] if item["item_type"] == "manual_review"
    )
    item["data"][changed_field] = "UNKNOWN_CASE_DATA"
    path.write_text(json.dumps(review))

    with review_transport(tmp_path) as call:
        index = call(
            "validate_open_item_reconciliation_review",
            {
                "review_payload_path": str(path),
                "client_engagement": str(Path(loaded["run_root"]) / "context.json"),
            },
        )["structuredContent"]
        handle = next(
            item["case_handle"]
            for item in index["model_context_index"]["cases"]
            if item["item_type"] == "manual_review"
        )
        selected = call(
            "get_open_item_reconciliation_case_context",
            {
                "persistence_token": index["review_reference"]["persistence_token"],
                "case_handles": [handle],
            },
        )["structuredContent"]

    assert selected["cases"][0]["semantic_fields"][changed_field] == "UNKNOWN_CASE_DATA"
    measured = report(loaded)
    assert measured["collection_status"] == "incomplete"
    assert "sent_data_has_no_source_coordinates" in measured["errors"]


@pytest.mark.parametrize("claim", ["no_residual", "fully_closed"])
def test_partial_payment_cannot_erase_its_balance_or_claim_full_closure(
    reconciled_case, monkeypatch, claim
):
    from tests.plugins.test_open_item_reconciliation_plugin import load_raw_input_runner

    loaded = reconciled_case
    runner = load_raw_input_runner()
    original = runner.finalize_assurance_run

    def altered_claim(**kwargs):
        rows = copy.deepcopy(kwargs["reconciliation_rows"])
        partial = next(
            row for row in rows if row["reconciliation_status"] == "partially_paid"
        )
        if claim == "no_residual":
            partial["residual_amount"] = "0.00"
        else:
            partial["reconciliation_status"] = "closed"
        return original(**{**kwargs, "reconciliation_rows": rows})

    monkeypatch.setattr(runner, "finalize_assurance_run", altered_claim)
    assumptions = json.loads(
        (Path(loaded["output_dir"]) / "assumptions.json").read_text()
    )

    with pytest.raises(
        ValueError, match="partial payment|balanced evidence allocation"
    ):
        runner.run_raw_input_reconciliation(
            input_dir=loaded["context"]["input_dir"],
            prepared_client_engagement=loaded["context"],
            assumptions=assumptions,
            output_subdirectory="reconciliation",
        )
