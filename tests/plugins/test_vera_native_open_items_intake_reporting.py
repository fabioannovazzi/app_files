"""Native intake preserves automatic reporting and recorded source review."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.open_item_reconciliation.test_reviewed_tabular_adapter import spec
from tests.plugins import test_vera_native_workspace as native
from tests.plugins.test_open_item_reconciliation_plugin import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_open_items_intake import (
    initial_open_items,
    initial_program,
)

__all__ = []


def test_native_intake_calculates_multi_party_csv_with_recorded_agent_review(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    source.mkdir()
    population = source / "population.csv"
    population.write_text(
        "InvoiceX;DateX;ValueX;DueX;PartyX\n"
        "F001;01/09/2026;1200.00;30/09/2026;Cliente Alfa Test\n"
        "F002;05/09/2026;800.00;30/09/2026;Cliente Beta Test\n"
        "F003;15/09/2026;500.00;15/10/2026;Cliente Gamma Test\n"
    )
    bank = source / "bank.csv"
    bank.write_text(
        "InvoiceX;PostedX;ValueX;PartyX\n"
        "F001;05/10/2026;1200.00;Cliente Alfa Test\n"
        "F002;10/10/2026;300.00;Cliente Beta Test\n"
    )
    choices = {
        population.name: spec(population),
        bank.name: spec(bank, "bank_statement"),
    }
    choices[population.name]["tabular"]["last_data_row"] = 4
    choices[population.name]["tabular"]["columns"]["due_date"] = "DueX"
    del choices[bank.name]["tabular"]["columns"]["document_date"]
    for choice in choices.values():
        del choice["reviewer_ref"]
        del choice["reviewed_on"]
        choice["perimeter"]["party_ref"] = None
        choice["money"]["thousands_separator"] = None
        choice["tabular"]["columns"]["party_ref"] = "PartyX"
    ledger = _load_customer_ledger()
    client = tmp_path / "Fictional CSV client"
    client.mkdir()
    client_id = "client_" + "c7" * 12
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(client, client_id, "CSV intake")
    receipts = [
        ledger.import_document(
            client, client_id, engagement["engagement_id"], path, "source"
        )["receipt"]
        for path in (population, bank)
    ]
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "open-item-reconciliation",
        "synthetic",
        input_ids=[row["input_id"] for row in receipts],
    )
    started = ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    output = Path(started["context"]["output_dir"])
    report_before = {path.name: path.read_bytes() for path in output.iterdir()}
    binding = {
        "work_ref": "initial-open-items",
        "client_root": str(client),
        "client_id": client_id,
        "engagement_id": engagement["engagement_id"],
        "run_id": prepared["run"]["run_id"],
        "workflow_id": "open-item-reconciliation",
    }
    env = native.configure(monkeypatch, tmp_path, [binding])
    program = initial_program().split("fields.sources=")[0]
    program += "const choices=" + json.dumps(choices) + ";"
    program += """
fields.cutoff_date='2026-09-30';fields.post_cutoff_events_excluded=false;
fields.reviewer_ref='agent.codex';fields.counterparty_keywords=[];
fields.sources=Object.fromEntries(setup.items.map(row=>[row.id,choices[row.title]]));
const saved=payload(call('vera_workspace_open_items_intake_draft_save',{...intakeScope,fields}));
const args={...intakeScope,expected_draft_revision:saved.draft_revision,review_actor:'agent',human_reviewed:false,idempotency_key:'agent-tabular-intake'};
const prepared=payload(call('vera_workspace_open_items_intake_prepare',args));
const retry=payload(call('vera_workspace_open_items_intake_prepare',args));
const result={setup,prepared,retry};
"""

    result = rpc_program(env, program)

    assert result["setup"]["status"] == "ready"
    assert result["prepared"] == result["retry"]
    assert result["prepared"]["professional_approval"] is False
    assert result["prepared"]["source_review"]["actor_type"] == "agent"
    assert result["prepared"]["source_review"]["human_reviewed"] is False
    assert result["prepared"]["source_review"]["reviewer_ref"] == "agent.codex"
    assert {
        name: (output / name).read_bytes() for name in report_before
    } == report_before
    rows = json.loads(
        (output / "reconciliation/reconciliation_results.json").read_bytes()
    )
    assert [row["reconciliation_status"] for row in rows["reconciliation_rows"]] == [
        "closed",
        "partially_paid",
        "unresolved",
    ]
    assert rows["reconciliation_rows"][1]["residual_amount"] == "500.00"
    assert rows["reconciliation_rows"][2]["amount"] == "500"
    private = native.workspace_module().ui_state_directory(output, create=False)
    receipt = json.loads(
        next(private.glob("open-items-intake-request-*.json")).read_bytes()
    )
    assert receipt["source_review"] == result["prepared"]["source_review"]


@pytest.mark.parametrize("state", ["unknown_output", "pending_request"])
def test_native_intake_preserves_actual_unfinished_work(initial_open_items, state):
    env, output, _ = initial_open_items
    if state == "unknown_output":
        retained = output / "partial-result.json"
    else:
        private = native.workspace_module().ui_state_directory(output)
        retained = private / "open-items-intake-request-interrupted.json"
    retained.write_text('{"intent":"fictional unfinished work"}')
    before = retained.read_bytes()

    result = rpc_program(
        env,
        """
const setup=payload(call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'}));
const saved=call('vera_workspace_open_items_intake_draft_save',{work_ref:setup.work_ref,revision:setup.revision,review_ticket:setup.review_ticket,expected_draft_revision:'',fields:{currency:'EUR'}});
const result={setup,saved};
""",
    )

    assert result["setup"]["status"] == "recovery_required"
    assert result["saved"]["isError"] is True
    assert retained.read_bytes() == before
    assert not (output / "reconciliation").exists()


def test_native_intake_does_not_exempt_foreign_reporting_files(initial_open_items):
    env, output, _ = initial_open_items
    path = output / "model_data_report.json"
    report = json.loads(path.read_bytes())
    report["run_id"] = "run_" + "d8" * 12
    path.write_text(json.dumps(report))

    result = rpc_program(
        env,
        "const result=call('vera_workspace_open_items_intake_setup',{work_ref:'initial-open-items'});",
    )

    assert result["isError"] is True
    assert not (output / "reconciliation").exists()
