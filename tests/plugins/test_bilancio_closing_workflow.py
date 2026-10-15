from __future__ import annotations

import csv
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/bilancio-xbrl-it"
FIXTURES = ROOT / "tests/fixtures/bilancio_alfa_v3"
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from closing_workflow import (  # noqa: E402
    closing_status,
    closing_validation_issues,
    ingest_closing_trial_balance,
    open_closing_reconsideration,
    propose_closing_adjustment,
    propose_closing_review,
    record_closing_decision,
    start_closing_workflow,
    verify_closing_register,
)
from xbrl_case import (  # noqa: E402
    apply_mapping_decisions,
    attach_supporting_document,
    create_case,
    ingest_trial_balance,
    load_case,
    save_case,
)

_SPEC = importlib.util.spec_from_file_location(
    "alfa_v3_acceptance", ROOT / "scripts/run_bilancio_alfa_v3_acceptance.py"
)
assert _SPEC and _SPEC.loader
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


@pytest.fixture(autouse=True)
def _module_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restore the plugin import path after the repository's isolation fixture."""
    monkeypatch.syspath_prepend(str(SCRIPTS))


def _baseline(tmp_path: Path) -> dict:
    """Prepare only the reviewed source required by adjustment guard tests."""
    payload = {
        "case_id": "closing_test",
        "tenant_id": "synthetic",
        "entity": {
            "legal_name": "Synthetic",
            "tax_identifier": "SYNTHETIC",
            "registered_office": "Fictitious",
            "legal_form": "SRL",
            "accounting_framework": "OIC",
            "listed": False,
            "regulated_sector": False,
            "consolidated": False,
            "final_liquidation": False,
            "first_financial_year": False,
            "prior_year_form": "ABBREVIATED",
            "prior_period_start": "2024-01-01",
            "prior_period_end": "2024-12-31",
            "micro_exclusion_flags": [],
        },
        "period": {"start": "2025-01-01", "end": "2025-12-31"},
        "oic_rule_pack": "OIC_2024_2025.1",
        "filing_campaign_year": 2026,
        "taxonomy_checksum": "a" * 64,
    }
    rule = json.loads(
        (PLUGIN / "rulepacks/it/statutory-forms-2026.1.json").read_bytes()
    )
    case = create_case(tmp_path / "case", payload, rule, "P1")
    start_closing_workflow(
        case, {"accounting_origin": "CONTABILITA_ESTERNA"}, "P1", case["revision_id"]
    )
    source = next((FIXTURES / "dati").glob("01_*"))
    ingest_trial_balance(
        case,
        source,
        "C1",
        case["revision_id"],
        column_mapping=runner.COLUMN_MAPPING,
        blank_balance_cells_are_zero=True,
    )
    document = case["source_documents"][0]["document_id"]
    record_closing_decision(
        case,
        {
            "record_id": "fascicolo",
            "kind": "FASCICOLO",
            "evidence_refs": [document],
            "reason": "Source evidence reviewed.",
            "decision": {
                "requirements": [
                    {
                        "requirement_id": "source",
                        "description": "Trial balance",
                        "reason": "Selected for a bounded mechanical test.",
                        "status": "AVAILABLE_SUFFICIENT",
                        "evidence_refs": [document],
                        "request_from_client": False,
                    }
                ],
                "sufficient_to_start": True,
            },
        },
        "P1",
        case["revision_id"],
    )
    record_closing_decision(
        case,
        {
            "record_id": "screening",
            "kind": "SCREENING",
            "evidence_refs": [document],
            "reason": "All source checks reviewed.",
            "decision": {
                "version_id": "baseline",
                "convention": "SIGNED_BALANCE_ONLY",
                "closing_entries_included": False,
                "checks": dict.fromkeys(
                    ["period", "comparative", "debit_credit", "closing_entries"], True
                ),
            },
        },
        "P1",
        case["revision_id"],
    )
    return case


def _proposal(case: dict) -> dict:
    return {
        "proposal_id": "A1",
        "subject_key": "depreciation",
        "reason": "Reviewed synthetic depreciation.",
        "evidence_refs": [case["source_documents"][0]["document_id"]],
        "lines": [
            {"account_code": "4140", "debit": "12000", "credit": "0"},
            {"account_code": "1015", "debit": "0", "credit": "12000"},
        ],
    }


def test_full_alfa_v3_service_acceptance_e1_e2_and_intermediate_states_pass(
    tmp_path: Path,
) -> None:
    acceptance = runner.AlfaAcceptance(PLUGIN, FIXTURES, tmp_path / "acceptance")

    report = acceptance.run()

    assert report["status"] == "PASS"
    assert report["failures"] == []
    assert report["check_count"] >= 100
    assert (tmp_path / "acceptance/confronto_alfa_v3.md").is_file()
    assert acceptance.status()["closure_allowed"] is False
    assert acceptance.status()["register_count"] == 13


def test_dependent_controls_require_new_screening_and_keep_professional_issues_open(
    tmp_path: Path,
) -> None:
    acceptance = runner.AlfaAcceptance(PLUGIN, FIXTURES, tmp_path / "acceptance")
    acceptance.run()
    suspended = deepcopy(acceptance.snapshots["06_suspended_after_A2bis"])
    premature = {
        "record_id": "controls",
        "kind": "CONTROL_REVIEW",
        "reason": "Synthetic repeat review",
        "evidence_refs": [acceptance.documents["06"]],
        "decision": {
            "version_id": "doc10",
            "scopes": runner.SCOPES,
            "workpaper_refs": [acceptance.documents["06"]],
        },
    }

    with pytest.raises(ValueError, match="acquired and screened"):
        record_closing_decision(suspended, premature, "P1", suspended["revision_id"])

    current = acceptance.case()
    workpaper = tmp_path / "repeated-controls.md"
    workpaper.write_text(
        "Synthetic workpaper: repeated checks of the reviewed replacement balance and selected affected mappings.\n"
    )
    attach_supporting_document(
        current,
        workpaper,
        "RESTATEMENT_WORKPAPER",
        "Repeated controls",
        "C1",
        current["revision_id"],
    )
    workpaper_id = current["source_documents"][-1]["document_id"]
    reviewed = {
        **premature,
        "evidence_refs": [workpaper_id],
        "decision": {
            "version_id": "doc12",
            "scopes": runner.SCOPES,
            "workpaper_refs": [workpaper_id],
        },
    }
    record_closing_decision(current, reviewed, "P1", current["revision_id"])

    assert closing_status(current)["dependencies"] == dict.fromkeys(
        runner.SCOPES, "VALID"
    )
    assert closing_status(current)["closure_allowed"] is False
    assert sorted(i["issue_id"] for i in closing_status(current)["open_issues"]) == [
        "imposte2025",
        "vertenza",
    ]


def test_reordered_replacement_preserves_account_identity_and_unaffected_mapping(
    tmp_path: Path,
) -> None:
    acceptance = runner.AlfaAcceptance(PLUGIN, FIXTURES, tmp_path / "acceptance")
    acceptance.run()
    case = deepcopy(acceptance.snapshots["06_suspended_after_A2bis"])
    accounts = {
        r["account_code"]: r["account_id"] for r in case["trial_balance"]["entries"]
    }
    bank_mapping = {
        "account_id": accounts["1410"],
        "decision": "ACCEPTED",
        "reason": "Reviewed bank mapping",
    }
    case["mappings"] = [
        bank_mapping,
        {
            "account_id": accounts["4210"],
            "decision": "ACCEPTED",
            "reason": "Old interest mapping",
        },
    ]
    original = next((FIXTURES / "dati").glob("12_*"))
    with original.open(newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        rows = list(reader)
    source = tmp_path / "reordered.csv"
    with source.open("w", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows([rows[0], *reversed(rows[1:])])

    ingest_closing_trial_balance(
        case,
        source,
        {
            "version_id": "reordered",
            "column_mapping": runner.COLUMN_MAPPING,
            "blank_balance_cells_are_zero": True,
        },
        "C1",
        case["revision_id"],
    )
    document_id = case["source_documents"][-1]["document_id"]
    record_closing_decision(
        case,
        {
            "record_id": "D-SCR3",
            "kind": "SCREENING",
            "reason": "Reviewed reordered replacement",
            "evidence_refs": [document_id],
            "decision": {
                "version_id": "reordered",
                "convention": "SIGNED_BALANCE_ONLY",
                "closing_entries_included": True,
                "checks": dict.fromkeys(
                    ["period", "comparative", "debit_credit", "closing_entries"], True
                ),
            },
        },
        "P1",
        case["revision_id"],
    )

    assert {
        r["account_code"]: r["account_id"] for r in case["trial_balance"]["entries"]
    } == accounts
    assert case["mappings"] == [bank_mapping]


@pytest.mark.parametrize(
    "change",
    [
        "unbalanced",
        "unknown_account",
        "both_sides",
        "negative",
        "nonfinite",
        "unknown_evidence",
        "unsafe_subject",
    ],
)
def test_adjustment_invalid_mechanical_contract_is_rejected_atomically(
    tmp_path: Path, change: str
) -> None:
    case = _baseline(tmp_path)
    payload = _proposal(case)
    if change == "unbalanced":
        payload["lines"][0]["debit"] = "11999"
    elif change == "unknown_account":
        payload["lines"][0]["account_code"] = "unknown"
    elif change == "both_sides":
        payload["lines"][0]["credit"] = "1"
    elif change == "negative":
        payload["lines"][0]["debit"] = "-12000"
    elif change == "nonfinite":
        payload["lines"][0]["debit"] = "NaN"
    elif change == "unknown_evidence":
        payload["evidence_refs"] = ["unknown"]
    else:
        payload["subject_key"] = "../unsafe"
    before = deepcopy(case)

    with pytest.raises(ValueError):
        propose_closing_adjustment(case, payload, "C1", case["revision_id"])

    assert case == before


def test_adjustment_preparer_cannot_approve_own_proposal(tmp_path: Path) -> None:
    case = _baseline(tmp_path)
    propose_closing_adjustment(case, _proposal(case), "C1", case["revision_id"])
    decision = {
        "record_id": "D-A1",
        "kind": "ADJUSTMENT",
        "reason": "Review",
        "evidence_refs": [case["source_documents"][0]["document_id"]],
        "decision": {"proposal_id": "A1", "outcome": "APPROVED"},
    }

    with pytest.raises(ValueError, match="distinct"):
        record_closing_decision(case, decision, "C1", case["revision_id"])

    assert closing_status(case)["active_adjustments"] == {}


def test_rejected_adjustment_is_retained_without_changing_accounts(
    tmp_path: Path,
) -> None:
    case = _baseline(tmp_path)
    original_entries = deepcopy(case["trial_balance"]["entries"])
    propose_closing_adjustment(case, _proposal(case), "C1", case["revision_id"])

    record_closing_decision(
        case,
        {
            "record_id": "D-A1",
            "kind": "ADJUSTMENT",
            "reason": "Proposal rejected after source review.",
            "evidence_refs": [case["source_documents"][0]["document_id"]],
            "decision": {"proposal_id": "A1", "outcome": "REJECTED"},
        },
        "P1",
        case["revision_id"],
    )

    assert closing_status(case)["active_adjustments"] == {}
    assert closing_status(case)["pending_adjustment_proposals"] == []
    assert case["trial_balance"]["entries"] == original_entries
    assert case["closing_workflow"]["events"][-1]["decision"]["outcome"] == "REJECTED"


@pytest.mark.parametrize(
    "part",
    ["opening", "event", "order", "head", "approved_proposal", "screened_source"],
)
def test_decision_register_detects_out_of_band_changes(
    tmp_path: Path, part: str
) -> None:
    case = _baseline(tmp_path)
    propose_closing_adjustment(case, _proposal(case), "C1", case["revision_id"])
    record_closing_decision(
        case,
        {
            "record_id": "D-A1",
            "kind": "ADJUSTMENT",
            "reason": "Reviewed",
            "evidence_refs": [case["source_documents"][0]["document_id"]],
            "decision": {"proposal_id": "A1", "outcome": "APPROVED"},
        },
        "P1",
        case["revision_id"],
    )
    workflow = case["closing_workflow"]
    if part == "opening":
        workflow["opening"]["accounting_origin"] = "CONTABILITA_INTERNA"
    elif part == "event":
        workflow["events"][0]["reason"] = "Changed"
    elif part == "order":
        workflow["events"].reverse()
    elif part == "head":
        workflow["head_sha256"] = "0" * 64
    elif part == "approved_proposal":
        workflow["proposals"][0]["lines"][0]["debit"] = "13000"
    else:
        workflow["versions"][0]["trial_balance"]["entries"][0][
            "closing_signed"
        ] = "90000"

    with pytest.raises(ValueError, match="integrity|head"):
        verify_closing_register(case)


def test_closing_only_source_preserves_missing_turnover_and_original_headers(
    tmp_path: Path,
) -> None:
    case = _baseline(tmp_path)

    table = case["trial_balance"]

    assert table["layout"] == "CLOSING_BALANCES_ONLY"
    assert table["entries"][0]["opening_signed"] is None
    assert table["entries"][0]["period_debit"] is None
    assert table["calibration"]["blank_balance_cells_are_zero"] is True
    assert table["source_anchors"][2]["column_header"] == "dare_2025"
    assert table["source_anchors"][2]["normalized_column"] == "closing_debit"


def test_trial_balance_with_blank_cells_requires_explicit_source_convention(
    tmp_path: Path,
) -> None:
    case = _baseline(tmp_path)
    case.pop("closing_workflow")

    with pytest.raises(ValueError, match="monetary value is required"):
        ingest_trial_balance(
            case,
            next((FIXTURES / "dati").glob("01_*")),
            "C1",
            case["revision_id"],
            column_mapping=runner.COLUMN_MAPPING,
        )

    assert case["trial_balance"]["layout"] == "CLOSING_BALANCES_ONLY"


def test_review_proposal_stays_non_authoritative_and_duplicate_ids_fail(
    tmp_path: Path,
) -> None:
    case = _baseline(tmp_path)
    payload = {
        "proposal_id": "area_suggestion",
        "kind": "AREAS",
        "content": {"areas": [{"area_id": "risk", "status": "EXCLUDED"}]},
        "reason": "Proposal needs professional review.",
        "evidence_refs": [case["source_documents"][0]["document_id"]],
    }

    propose_closing_review(case, payload, "C1", case["revision_id"])

    assert closing_status(case)["areas"] == []
    assert (
        case["closing_workflow"]["review_proposals"][0]["status"] == "MODEL_SUGGESTED"
    )
    with pytest.raises(ValueError, match="reused"):
        propose_closing_review(case, payload, "C1", case["revision_id"])


def test_invalid_replacement_does_not_replace_canonical_source_or_enable_mapping(
    tmp_path: Path,
) -> None:
    case = _baseline(tmp_path)
    before = deepcopy(case["trial_balance"])

    ingest_closing_trial_balance(
        case,
        next((FIXTURES / "dati").glob("13_*")),
        {
            "version_id": "E1",
            "column_mapping": runner.COLUMN_MAPPING,
            "blank_balance_cells_are_zero": True,
        },
        "C1",
        case["revision_id"],
    )

    assert case["trial_balance"] == before
    assert (
        case["closing_workflow"]["versions"][-1]["reconciliation"]["status"]
        == "MISMATCH"
    )
    with pytest.raises(ValueError, match="Closing fascicolo"):
        apply_mapping_decisions(case, [], "P1", case["revision_id"])


def test_canonical_save_and_reopen_preserves_register_and_blockers(
    tmp_path: Path,
) -> None:
    case = _baseline(tmp_path)
    save_case(tmp_path / "reopened", case)

    reopened = load_case(tmp_path / "reopened")

    assert closing_status(reopened) == closing_status(case)
    assert (
        closing_validation_issues(reopened)[0]["rule_id"] == "CLOSING.REVIEW_REQUIRED"
    )


def test_new_supporting_source_requires_review_in_existing_closing_case(
    tmp_path: Path,
) -> None:
    case = _baseline(tmp_path)
    source = next((FIXTURES / "dati").glob("11_*"))

    attach_supporting_document(
        case, source, "CONTRACT", "Changed interest rate", "C1", case["revision_id"]
    )

    assert closing_status(case)["unreviewed_document_ids"] == [
        case["source_documents"][-1]["document_id"]
    ]
    assert closing_status(case)["form_and_mapping_allowed"] is False


@pytest.mark.parametrize(
    "function,payload",
    [
        (propose_closing_adjustment, {}),
        (record_closing_decision, {}),
        (open_closing_reconsideration, {}),
        (propose_closing_review, {}),
        (start_closing_workflow, {}),
    ],
)
def test_closing_mutation_rejects_stale_revision_before_payload_processing(
    tmp_path: Path, function, payload: dict
) -> None:
    case = _baseline(tmp_path)
    original = deepcopy(case)

    with pytest.raises(ValueError, match="Stale revision"):
        function(case, payload, "P1", "rev_0")

    assert case == original
