"""Evidence closure, reviewed arithmetic and annual mappings; no legal UAT claim."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_patent_box_workflow import model_proposal, reviewed, running_case, workflow

PLUGIN = Path(__file__).resolve().parents[2] / "plugins/patent-box-review"
sys.path.insert(0, str(PLUGIN))
from patent_box.casebook import check_casebook
from patent_box.contracts import ContractError
from patent_box.coordination import coordinate_incentives, reconcile_declarations


def incentive_plan() -> dict[str, Any]:
    """Fictional reviewed formula; these rates are test inputs, never defaults."""
    evidence = {"evidence_ids": ["E0002"], "source_ids": ["DEMO.SOURCE"]}
    return {
        "incentive_id": "I1",
        "allocation_ids": ["A1"],
        "period_id": "P2025",
        "regime": "Fictional test incentive",
        "assessment": "RECALCULATION",
        "conclusion": "Explicit synthetic plan; no legal treatment inferred.",
        **evidence,
        "inputs": [
            {
                "name": "base",
                "value": "100000.00",
                "unit": "EUR",
                "locator": "Fixture row 1",
                **evidence,
            },
            {
                "name": "rate",
                "value": "0.10",
                "unit": "RATIO",
                "locator": "Fictional rule 1",
                **evidence,
            },
            {
                "name": "reviewed_effect",
                "value": "26400.00",
                "unit": "EUR",
                "locator": "Reviewed synthetic plan",
                **evidence,
            },
            {
                "name": "used",
                "value": "10000.00",
                "unit": "EUR",
                "locator": "Fixture row 2",
                **evidence,
            },
        ],
        "steps": [
            {
                "name": "adjusted_base",
                "operation": "DIFFERENCE",
                "operands": ["base", "reviewed_effect"],
            },
            {
                "name": "revised",
                "operation": "PRODUCT",
                "operands": ["adjusted_base", "rate"],
            },
            {
                "name": "recovery",
                "operation": "DIFFERENCE",
                "operands": ["used", "revised"],
            },
        ],
        "outputs": [
            {"role": "revised_credit", "value_ref": "revised"},
            {"role": "repayment", "value_ref": "recovery"},
        ],
        "action": "Review synthetic outputs",
        "due_date": None,
        "deadline_source_ids": [],
        "deadline_reason": "No deadline proposed by this fixture",
    }


def annual_mapping() -> dict[str, Any]:
    def row(
        role: str, field: str, expected: str | None, reported: str | None
    ) -> dict[str, Any]:
        return {
            "mapping_id": role,
            "role": role,
            "form": "Fictional annual form",
            "field": field,
            "source_locator": "Selected annual instructions fixture",
            "expected": expected,
            "reported": reported,
            "reported_evidence_ids": ["E0002"] if reported is not None else [],
            "incentive_id": None,
            "output_role": None,
        }

    return {
        "model_year": 2026,
        "period_id": "P2025",
        "model_version": "2026.fixture.1",
        "instructions_version": "2026.fixture.1",
        "model_evidence_id": "E0001",
        "instructions_source_id": "DEMO.SOURCE",
        "rows": [
            row("OPTION", "annual/option", "yes", "yes"),
            row("INCOME_DEDUCTION", "annual/income", None, "110000.00"),
            row("IRAP_DEDUCTION", "annual/irap", None, "88000.00"),
        ],
    }


def complete_book() -> dict[str, Any]:
    """Synthetic proposal record for contract testing, not a real professional review."""
    evidence = {"evidence_ids": ["E0001"], "source_ids": ["DEMO.SOURCE"]}
    return {
        "schema_version": "1.0",
        "taxpayer": {
            "name": "Synthetic company",
            "identifier": "TEST",
            "evidence_ids": ["E0001"],
        },
        "objective": "Synthetic casebook acceptance",
        "facts": [
            {
                "fact_id": "F1",
                "topic": "Fixture",
                "statement": "Synthetic fact asserted solely by test fixture",
                "status": "EVIDENCED",
                "evidence_ids": ["E0001"],
                "locator": "synthetic.txt",
            }
        ],
        "projects": [
            {"project_id": "PROJECT.1", "name": "Synthetic project", "fact_ids": ["F1"]}
        ],
        "activities": [
            {
                "activity_id": "ACT.1",
                "project_id": "PROJECT.1",
                "ip_id": "IP.SOFT",
                "period_ids": ["P2025"],
                "description": "Synthetic activity",
                "fact_ids": ["F1"],
            }
        ],
        "ip_details": [
            {
                "ip_id": "IP.SOFT",
                "version": "fixture",
                "protected_subject": "Fictional software",
                "analysis": [
                    {
                        "issue": issue,
                        "conclusion": "Explicit fixture assertion",
                        "status": "EVIDENCED",
                        **evidence,
                    }
                    for issue in (
                        "AUTHORSHIP",
                        "ORIGINAL_COMPONENT",
                        "THIRD_PARTY_COMPONENTS",
                    )
                ],
                "rights_chain": [
                    {
                        "party": "Synthetic company",
                        "role": "Fictional author",
                        "right": "Test only",
                        "fact_ids": ["F1"],
                    }
                ],
                "use_fact_ids": ["F1"],
                "supplier_chain": [],
            }
        ],
        "applicability": [
            {
                "branch": branch,
                "scope": scope,
                "applicable": False,
                "reason": "Explicit fixture absence",
                **evidence,
            }
            for branch, scope in (
                ("OUTSOURCING", "ip:IP.SOFT"),
                ("PREMIAL", "ip:IP.SOFT"),
                ("EXTRAORDINARY", "case"),
                ("PENALTY", "case"),
            )
        ],
        "missing_documents": [],
        "template": None,
        "paragraphs": [
            {
                "paragraph_id": "A.1",
                "section": "A",
                "title": "Synthetic facts",
                "text": "Fictional evidence for contract test",
                "status": "EVIDENCED",
                "fact_ids": ["F1"],
                "source_ids": ["DEMO.SOURCE"],
            }
        ],
        "incentives": [incentive_plan()],
        "declarations": [annual_mapping()],
        "adversarial_review": [
            {
                "issue_id": "Q1",
                "allocation_ids": ["A1"],
                "argument": "Test cannot establish real eligibility",
                "response": "Keep this run synthetic",
                "income_at_risk": "100000.00",
                "irap_at_risk": "80000.00",
                "missing_request_ids": [],
                "decision": "ACCEPT",
                **evidence,
            }
        ],
        "office_requests": [],
    }


def test_reviewed_formula_produces_exact_revised_credit_and_repayment() -> None:
    result = coordinate_incentives([incentive_plan()])

    assert result[0]["outputs"] == {
        "revised_credit": {"value": "7360.00", "unit": "EUR"},
        "repayment": {"value": "2640.00", "unit": "EUR"},
    }
    assert result[0]["due_date"] is None
    assert result[0]["status"] == "PROPOSED"


def test_changed_reviewed_rate_changes_result_without_legal_default() -> None:
    plan = incentive_plan()
    plan["inputs"][1]["value"] = "0.05"

    result = coordinate_incentives([plan])

    assert result[0]["outputs"]["revised_credit"]["value"] == "3680.00"


@pytest.mark.parametrize(
    "operation,operands",
    [
        ("SUM", ["base", "rate"]),
        ("PRODUCT", ["base", "used"]),
        ("QUOTIENT", ["rate", "base"]),
    ],
)
def test_incompatible_units_rejected(operation: str, operands: list[str]) -> None:
    plan = incentive_plan()
    plan["steps"][0].update(operation=operation, operands=operands)

    with pytest.raises(ContractError):
        coordinate_incentives([plan])


def test_formula_forward_reference_is_rejected() -> None:
    plan = incentive_plan()
    plan["steps"][0]["operands"] = ["base", "recovery"]

    with pytest.raises(ContractError, match="forward"):
        coordinate_incentives([plan])


def test_formula_zero_divisor_is_rejected() -> None:
    plan = incentive_plan()
    plan["inputs"][1]["value"] = "0"
    plan["steps"][0].update(operation="QUOTIENT", operands=["base", "rate"])

    with pytest.raises(ContractError, match="arithmetic"):
        coordinate_incentives([plan])


def test_deadline_without_case_source_is_rejected() -> None:
    plan = incentive_plan()
    plan["due_date"] = "2026-06-30"

    with pytest.raises(ContractError, match="deadline"):
        coordinate_incentives([plan])


def test_no_overlap_cannot_disguise_a_calculation() -> None:
    plan = incentive_plan()
    plan["assessment"] = "NO_OVERLAP"

    with pytest.raises(ContractError, match="no-overlap"):
        coordinate_incentives([plan])


def test_annual_mapping_reconciles_income_and_irap_separately() -> None:
    result = reconcile_declarations(
        [annual_mapping()],
        {
            "claim_period_id": "P2025",
            "additional_deduction": {"income": "110000.00", "irap": "88000.00"},
        },
        [],
    )

    assert result["status"] == "RECONCILED"
    assert result["rows"][1]["expected"] == "110000.00"
    assert result["rows"][2]["expected"] == "88000.00"
    assert result["submitted"] is False


@pytest.mark.parametrize(
    "reported,state,difference",
    [(None, "NOT_TESTED", None), ("87999.99", "FAIL", "-0.01")],
)
def test_return_missing_or_mismatched_value_remains_open(
    reported: str | None, state: str, difference: str | None
) -> None:
    model = annual_mapping()
    model["rows"][2]["reported"] = reported

    result = reconcile_declarations(
        [model],
        {
            "claim_period_id": "P2025",
            "additional_deduction": {"income": "110000.00", "irap": "88000.00"},
        },
        [],
    )

    assert result["status"] == "OPEN"
    assert result["rows"][2]["status"] == state
    assert result["rows"][2]["difference"] == difference


def test_return_cannot_replace_computed_deduction_with_proposed_amount() -> None:
    model = annual_mapping()
    model["rows"][1]["expected"] = "200000.00"

    with pytest.raises(ContractError, match="computed"):
        reconcile_declarations(
            [model],
            {
                "claim_period_id": "P2025",
                "additional_deduction": {"income": "110000.00", "irap": "88000.00"},
            },
            [],
        )


def test_return_value_without_evidence_is_rejected() -> None:
    model = annual_mapping()
    model["rows"][1]["reported_evidence_ids"] = []

    with pytest.raises(ContractError, match="selected evidence"):
        reconcile_declarations(
            [model],
            {
                "claim_period_id": "P2025",
                "additional_deduction": {"income": "110000.00", "irap": "88000.00"},
            },
            [],
        )


def proposal_with_book(
    tmp_path: Path, workflow: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    run = running_case(tmp_path, workflow)
    proposal = model_proposal(run, workflow)
    book = complete_book()
    allocation = proposal["case"]["allocations"][0]
    book["projects"][0]["project_id"] = allocation["project_id"]
    book["activities"][0].update(
        activity_id=allocation["activity_id"], project_id=allocation["project_id"]
    )
    proposal["casebook"] = book
    return run, proposal


def test_complete_casebook_closes_references_without_claiming_professional_acceptance(
    tmp_path: Path, workflow: Any
) -> None:
    _, proposal = proposal_with_book(tmp_path, workflow)

    result = check_casebook(
        proposal["casebook"],
        proposal["case"],
        proposal["rules"],
        {r["key"] for r in proposal["controls"]},
    )

    assert result["gaps"] == []
    assert result["incentives"][0]["status"] == "PROPOSED"


def test_unsupported_fact_cannot_be_promoted_by_paragraph_status(
    tmp_path: Path, workflow: Any
) -> None:
    run, proposal = proposal_with_book(tmp_path, workflow)
    proposal["casebook"]["facts"][0]["status"] = "UNRESOLVED"

    with pytest.raises(workflow.ContractError, match="unsupported facts"):
        workflow.propose(run["context"], proposal)


def test_cross_project_activity_link_is_rejected(tmp_path: Path, workflow: Any) -> None:
    run, proposal = proposal_with_book(tmp_path, workflow)
    proposal["case"]["allocations"][0]["project_id"] = "WRONG.PROJECT"

    with pytest.raises(workflow.ContractError, match="disagrees"):
        workflow.propose(run["context"], proposal)


def test_pass_with_missing_rights_chain_is_rejected(
    tmp_path: Path, workflow: Any
) -> None:
    run, proposal = proposal_with_book(tmp_path, workflow)
    proposal["casebook"]["ip_details"][0]["rights_chain"] = []

    with pytest.raises(workflow.ContractError, match="PASS contradicts"):
        workflow.propose(run["context"], proposal)


def test_supplier_cycle_cannot_be_presented_as_a_chain(
    tmp_path: Path, workflow: Any
) -> None:
    run, proposal = proposal_with_book(tmp_path, workflow)
    proposal["casebook"]["ip_details"][0]["supplier_chain"] = [
        {
            "supplier_id": "S1",
            "parent_supplier_id": "S1",
            "name": "Synthetic supplier",
            "group_relationship": "Synthetic",
            "activity_location": "Synthetic",
            "technical_direction": "Synthetic",
            "risk": "Synthetic",
            "result_rights": "Synthetic",
            "fact_ids": ["F1"],
        }
    ]

    with pytest.raises(workflow.ContractError, match="cycle"):
        workflow.propose(run["context"], proposal)


def test_casebook_outputs_are_bound_to_reviewed_version(
    tmp_path: Path, workflow: Any
) -> None:
    run, proposal = proposal_with_book(tmp_path, workflow)
    digest = reviewed(run, workflow, proposal)

    result = workflow.calculate_draft(run["context"], digest=digest)

    folder = Path(result["output_dir"])
    assert (folder / "incentive_matrix.json").exists()
    assert (folder / "declaration_bridge.json").exists()
    assert "EVIDENCED" in (folder / "casebook.md").read_text()
    assert "2640.00" in (folder / "incentive_matrix.json").read_text()
