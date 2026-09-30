"""Public archive-bound ledger actions and proposal binding, without calculation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_patent_box_workflow import model_proposal, running_case, workflow


def mapped_case(
    tmp_path: Path, workflow: ModuleType, *, duplicate: bool = False
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    run = running_case(tmp_path, workflow, mixed=duplicate)
    proposal = model_proposal(run, workflow)
    ledger = next(
        r for r in run["session"]["inputs"] if r["description"] == "ledger.csv"
    )
    options = {
        "format": "CSV",
        "sheet": None,
        "header_row": 1,
        "first_row": 2,
        "last_row": 3 if duplicate else 2,
        "delimiter": ",",
        "encoding": "utf-8",
        "pdf_extraction": None,
    }
    table = workflow.inspect_ledger(
        run["context"], evidence_id=ledger["evidence_id"], options=options
    )
    plan = {
        "schema_version": "1.0",
        "purpose": "Synthetic source binding test",
        "mappings": [
            {
                "table_id": table["table_id"],
                "amount_column": "F",
                "currency_column": None,
                "currency_constant": "EUR",
                "row_key_column": "B",
                "decimal_separator": ".",
                "thousands_separator": None,
                "parentheses_negative": False,
                "economic_key_columns": ["D"] if duplicate else ["B"],
                "mapping_rationale": "Model-proposed fixture mapping",
            }
        ],
        "control_totals": [
            {
                "table_id": table["table_id"],
                "currency": "EUR",
                "value": "200000.00" if duplicate else "100000.00",
                "evidence_id": ledger["evidence_id"],
                "locator": "Fixture total",
                "source_cell": None,
            }
        ],
        "fx_rates": [],
        "costs": [],
        "excluded_rows": [],
        "non_data_rows": [],
        "duplicate_reviews": [],
        "population_duplicate_review": {
            "assessment": "Synthetic review; matching economic fields require explicit decision",
            "evidence_ids": [ledger["evidence_id"]],
        },
        "rounding_policy": "HALF_UP_AT_NORMALIZED_COST_TOTAL",
    }
    for cost, row in zip(proposal["case"]["costs"], table["rows"]):
        plan["costs"].append(
            {
                **{
                    k: cost[k]
                    for k in (
                        "cost_id",
                        "period_id",
                        "account",
                        "category",
                        "income_max",
                        "irap_max",
                    )
                },
                "components": [{"row_ref": row["row_ref"], "fx_rate_id": None}],
                "rationale": "Explicit synthetic fiscal basis",
                "evidence_ids": [ledger["evidence_id"]],
            }
        )
    return run, proposal, table, plan


def normalized_proposal(
    run: dict[str, Any],
    proposal: dict[str, Any],
    plan: dict[str, Any],
    workflow: ModuleType,
) -> dict[str, Any]:
    result = workflow.normalize_ledger(run["context"], plan)
    proposal["normalization_digest"] = result["normalization_digest"]
    proposal["case"]["costs"] = result["costs"]
    proposal["case"]["ledger_control_total"] = result["ledger_control_total"]
    return result


def test_propose_binds_normalized_costs_plan_and_readable_review(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run, proposal, table, plan = mapped_case(tmp_path, workflow)
    normalized = normalized_proposal(run, proposal, plan, workflow)

    result = workflow.propose(run["context"], proposal)

    saved = json.loads(
        (run["output"] / f"proposal_{result['proposal_digest']}.json").read_text()
    )
    assert saved["normalization_record"]["plan"] == plan
    assert saved["normalization_record"]["tables"] == [table]
    assert saved["normalization_record"]["result"] == normalized
    assert (
        "Basi candidate: redditi EUR 100000.00; IRAP EUR 80000.00"
        in Path(result["review_path"]).read_text()
    )
    assert normalized["professional_approval"] is False


def test_normalize_rejects_rehashed_cell_edit_by_replaying_original(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run, _, table, plan = mapped_case(tmp_path, workflow)
    table["rows"][0]["cells"]["F"]["value"] = "900000.00"
    table["table_digest"] = workflow.canonical_hash(
        {k: v for k, v in table.items() if k != "table_digest"}
    )
    target = run["output"] / f"ledger_table_{table['table_id']}.json"
    target.write_text(json.dumps(table))

    with pytest.raises(
        workflow.ContractError, match="replay from the selected original"
    ):
        workflow.normalize_ledger(run["context"], plan)


def test_propose_rejects_amount_changed_after_normalization(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run, proposal, _, plan = mapped_case(tmp_path, workflow)
    normalized_proposal(run, proposal, plan, workflow)
    proposal["case"]["costs"][0]["income_max"] = "99999.00"

    with pytest.raises(
        workflow.ContractError, match="differs from reviewed normalization"
    ):
        workflow.propose(run["context"], proposal)


def test_propose_rejects_normalization_from_another_run(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run, proposal, _, plan = mapped_case(tmp_path, workflow)
    normalized = normalized_proposal(run, proposal, plan, workflow)
    target = run["output"] / f"normalization_{normalized['normalization_digest']}.json"
    record = json.loads(target.read_text())
    record["run_id"] = "another_client_run"
    target.write_text(json.dumps(record))

    with pytest.raises(workflow.ContractError, match="another run"):
        workflow.propose(run["context"], proposal)


def test_propose_rejects_pass_on_unresolved_duplicate_cost(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run, proposal, _, plan = mapped_case(tmp_path, workflow, duplicate=True)
    normalized_proposal(run, proposal, plan, workflow)

    with pytest.raises(workflow.ContractError, match="Unresolved duplicate"):
        workflow.propose(run["context"], proposal)


def test_propose_retains_blocked_duplicate_cost_as_open_work(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run, proposal, _, plan = mapped_case(tmp_path, workflow, duplicate=True)
    normalized_proposal(run, proposal, plan, workflow)
    control = next(
        r for r in proposal["controls"] if r["key"] == "allocation:A1/PB.COST"
    )
    control.update(
        status="BLOCKED", conclusion="Duplicate economic evidence requires a decision"
    )

    result = workflow.propose(run["context"], proposal)

    saved = json.loads(
        (run["output"] / f"proposal_{result['proposal_digest']}.json").read_text()
    )
    assert saved["normalization_record"]["result"]["blocked_cost_ids"] == ["C1", "C2"]
    assert "allocation:A1/PB.COST — BLOCKED" in Path(result["review_path"]).read_text()


def test_inspect_ledger_rejects_evidence_outside_selected_run(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run = running_case(tmp_path, workflow)

    with pytest.raises(workflow.ContractError, match="not selected evidence"):
        workflow.inspect_ledger(run["context"], evidence_id="OTHER_CLIENT", options={})


def test_inspect_ledger_is_reusable_without_overwriting_snapshot(
    tmp_path: Path, workflow: ModuleType
) -> None:
    run, _, table, _ = mapped_case(tmp_path, workflow)
    target = run["output"] / f"ledger_table_{table['table_id']}.json"
    before = target.stat().st_mtime_ns

    result = workflow.inspect_ledger(
        run["context"],
        evidence_id=table["source_evidence_id"],
        options=table["options"],
    )

    assert result == table
    assert target.stat().st_mtime_ns == before
