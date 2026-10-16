from __future__ import annotations

import base64
import importlib.util
import json
import sys
from copy import deepcopy
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/bilancio-xbrl-it"
FIXTURES = ROOT / "tests/fixtures/bilancio_alfa_v3"
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))
from area_review import (  # noqa: E402
    build_area_review,
    confirm_area_review,
    propose_area_review,
    propose_qualitative_evidence,
    record_area_controls,
    record_review_source_replacement,
    review_catalogue,
    review_qualitative_evidence,
    review_source,
    review_validation_issues,
    verify_area_review,
)
from review_views import build_review_view  # noqa: E402
from review_workbook import build_review_workbook  # noqa: E402
from workspace_contract import build_workspace_snapshot  # noqa: E402
from xbrl_case import attach_supporting_document, load_case, save_case  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "area_alfa", ROOT / "scripts/run_bilancio_alfa_v3_acceptance.py"
)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
ORACLE = json.loads(
    (ROOT / "tests/fixtures/bilancio_area_review/expected.json").read_bytes()
)


@pytest.fixture(scope="module")
def original(tmp_path_factory: pytest.TempPathFactory) -> dict:
    acceptance = runner.AlfaAcceptance(
        PLUGIN, FIXTURES, tmp_path_factory.mktemp("area-original") / "alfa"
    )
    report = acceptance.run()
    assert report["status"] == "PASS"
    assert report["check_count"] == ORACLE["original_alfa_checks"]
    return acceptance.case()


@pytest.fixture
def case(original: dict) -> dict:
    return deepcopy(original)


def proposal(case: dict, *, internal: bool = False) -> dict:
    if internal:
        # This is a separate synthetic engagement-origin scenario, not a mutation
        # of the original Alfa register. Its source population is reused only.
        case.pop("closing_workflow")
        case["review_source_extracts"] = []
    assignments = [
        {
            "account_id": e["account_id"],
            "area_id": ORACLE["account_areas"][e["account_code"]],
        }
        for e in case["trial_balance"]["entries"]
    ]
    active = {a["area_id"] for a in assignments}
    baseline = case["source_documents"][0]["document_id"]
    bank = next(
        d["document_id"]
        for d in case["source_documents"]
        if d["file_name"].startswith("03_")
    )
    return {
        "id": "plan1",
        "reason": "Explicit synthetic account and evidence assessment.",
        "evidence_refs": [baseline],
        "content": {
            "complexity": "SIMPLE",
            "complexity_reason": "Synthetic uncomplicated reporting scope.",
            "account_areas": assignments,
            "areas": [
                {
                    "area_id": a["id"],
                    "status": "ACTIVE" if a["id"] in active else "EXCLUDED",
                    "reason": "Synthetic professional conclusion with selected evidence.",
                    "evidence_refs": (
                        [bank] if a["id"] == "PAYABLES_FINANCING" else [baseline]
                    ),
                }
                for a in review_catalogue()["areas"]
            ],
        },
    }


def confirm(case: dict, p: dict | None = None) -> dict:
    p = p or proposal(case)
    propose_area_review(case, p, "C1", case["revision_id"])
    confirm_area_review(
        case,
        {
            "proposal_id": p["id"],
            "source_versions_reviewed": True,
            "oic_rule_pack_checksum": case["oic_rule_pack_checksum"],
            "reason": "Synthetic reviewer verified the period-specific sources.",
        },
        "P1",
        case["revision_id"],
    )
    return build_area_review(case)


def qualitative(case: dict, *, period: str = "2025", quote: str | None = None) -> dict:
    doc = next(
        d["document_id"]
        for d in case["source_documents"]
        if d["file_name"].startswith("05_")
    )
    source = review_source(case, doc)
    text = source["excerpt"]
    start = text.index("vertenza")
    selected = text[start : start + 70]
    return {
        "id": "qual1",
        "document_id": doc,
        "start": start,
        "end": start + len(selected),
        "quote": selected if quote is None else quote,
        "period": {"start": period + "-01-01", "end": period + "-12-31"},
        "flag": "PROVISIONS_OR_LITIGATION_PRESENT",
        "outcome": "APPLICABLE",
        "reason": "Synthetic interpretation only, not an accounting conclusion.",
    }


def test_catalogue_contains_29_standards_96_prompts_and_no_generic_section_claim() -> (
    None
):
    pack = review_catalogue()
    assert len(pack["standards"]) == ORACLE["catalogue_standards"]
    assert len(pack["controls"]) == ORACLE["semantic_prompts"]
    assert pack["policy"]["section_controls_included"] is False
    assert not any("tokens" in a for a in pack["areas"])


def test_preparer_proposal_does_not_accept_plan_or_close_validation(case: dict) -> None:
    propose_area_review(case, proposal(case), "C1", case["revision_id"])
    assert build_area_review(case)["status"] == "PLAN_REQUIRED"
    assert review_validation_issues(case)[0]["rule_id"] == "AREA.REVIEW_REQUIRED"


@pytest.mark.parametrize("bad", ["missing", "duplicate", "unknown", "excluded"])
def test_population_coverage_rejects_unassigned_duplicated_unknown_or_excluded_accounts(
    case: dict, bad: str
) -> None:
    p = proposal(case)
    if bad == "missing":
        p["content"]["account_areas"].pop()
    elif bad == "duplicate":
        p["content"]["account_areas"][-1] = p["content"]["account_areas"][0]
    elif bad == "unknown":
        p["content"]["account_areas"][-1]["account_id"] = "foreign_account"
    else:
        p["content"]["account_areas"][-1]["area_id"] = "DERIVATIVES"
    with pytest.raises(ValueError, match="account|assigned"):
        propose_area_review(case, p, "C1", case["revision_id"])


@pytest.mark.parametrize(
    "field,value",
    [("source_versions_reviewed", False), ("oic_rule_pack_checksum", "wrong")],
)
def test_plan_confirmation_binds_reporting_pack_and_explicit_version_review(
    case: dict, field: str, value: object
) -> None:
    p = proposal(case)
    propose_area_review(case, p, "C1", case["revision_id"])
    payload = {
        "proposal_id": "plan1",
        "source_versions_reviewed": True,
        "oic_rule_pack_checksum": case["oic_rule_pack_checksum"],
        "reason": "Synthetic review.",
    }
    payload[field] = value
    with pytest.raises(ValueError):
        confirm_area_review(case, payload, "P1", case["revision_id"])


def test_intervening_account_change_rejects_stale_plan(case: dict) -> None:
    p = proposal(case)
    propose_area_review(case, p, "C1", case["revision_id"])
    case["trial_balance"]["entries"][0]["closing_signed"] = "999"
    with pytest.raises(ValueError, match="stale"):
        confirm_area_review(case, {"proposal_id": "plan1"}, "P1", case["revision_id"])


def test_document_only_signal_activates_area_and_prevents_exclusion(case: dict) -> None:
    q = qualitative(case)
    # Use the pack's document-only subsequent-event activation, without any account.
    propose_qualitative_evidence(case, q, "C1", case["revision_id"])
    review_qualitative_evidence(
        case,
        {
            "proposal_id": q["id"],
            "outcome": "CONFIRMED",
            "reason": "Synthetic professional interpretation.",
        },
        "P1",
        case["revision_id"],
    )
    p = proposal(case)
    with pytest.raises(ValueError, match="qualitative"):
        propose_area_review(case, p, "C1", case["revision_id"])
    next(a for a in p["content"]["areas"] if a["area_id"] == "PROVISIONS")[
        "status"
    ] = "ACTIVE"
    review = confirm(case, p)
    row = next(a for a in review["workpapers"] if a["area_id"] == "PROVISIONS")
    assert row["status"] == "ACTIVE"
    assert row["accounts"] == []
    assert row["qualitative"][0]["quote"] == q["quote"]


def test_qualitative_quote_must_match_exact_registered_source(case: dict) -> None:
    with pytest.raises(ValueError, match="Quote"):
        propose_qualitative_evidence(
            case,
            qualitative(case, quote="Fabricated accounting evidence"),
            "C1",
            case["revision_id"],
        )


def test_prior_only_qualitative_evidence_cannot_confirm_current_period(
    case: dict,
) -> None:
    q = qualitative(case, period="2024")
    propose_qualitative_evidence(case, q, "C1", case["revision_id"])
    with pytest.raises(ValueError, match="Prior-only"):
        review_qualitative_evidence(
            case,
            {
                "proposal_id": q["id"],
                "outcome": "CONFIRMED",
                "reason": "Synthetic review.",
            },
            "P1",
            case["revision_id"],
        )


def test_source_replacement_selectively_reopens_dependent_controls(
    case: dict, tmp_path: Path
) -> None:
    review = confirm(case)
    touched = {
        ORACLE["source_replacement_affected"],
        ORACLE["source_replacement_unaffected"],
    }
    for area in [a for a in review["workpapers"] if a["area_id"] in touched]:
        c = area["controls"][0]
        record_area_controls(
            case,
            {
                "area_id": area["area_id"],
                "control_id": c["id"],
                "basis_sha256": area["basis_sha256"],
                "status": "PASS",
                "reason": "Synthetic evidence-based conclusion.",
                "evidence_refs": [area["documents"][0]["document_id"]],
            },
            "P1",
            case["revision_id"],
        )
    old = next(
        d["document_id"]
        for d in case["source_documents"]
        if d["file_name"].startswith("03_")
    )
    source = tmp_path / "new-bank-contract.md"
    source.write_text("Synthetic changed financing conditions. No client data.")
    attach_supporting_document(
        case,
        source,
        "CONTRACT",
        "Changed synthetic contract",
        "C1",
        case["revision_id"],
    )
    new = case["source_documents"][-1]["document_id"]
    record_review_source_replacement(case, old, new, "C1", case["revision_id"])
    observed = build_area_review(case)
    assert (
        next(c for c in observed["controls"] if c["area_id"] == "PAYABLES_FINANCING")[
            "status"
        ]
        == "REVIEW_REQUIRED"
    )
    assert (
        next(c for c in observed["controls"] if c["area_id"] == "FIXED_ASSETS")[
            "status"
        ]
        == "PASS"
    )
    assert len(case["area_review"]["events"]) == 4
    verify_area_review(case)


def test_stale_workpaper_control_is_rejected(case: dict) -> None:
    area = next(
        a for a in confirm(case)["workpapers"] if a["area_id"] == "FIXED_ASSETS"
    )
    with pytest.raises(ValueError, match="Stale"):
        record_area_controls(
            case,
            {
                "area_id": area["area_id"],
                "control_id": area["controls"][0]["id"],
                "basis_sha256": "old",
                "status": "PASS",
                "reason": "Synthetic review.",
                "evidence_refs": [area["documents"][0]["document_id"]],
            },
            "P1",
            case["revision_id"],
        )


def test_control_hash_changes_for_account_amount_but_retains_unrelated_area(
    case: dict,
) -> None:
    before = {a["area_id"]: a["basis_sha256"] for a in confirm(case)["workpapers"]}
    case["trial_balance"]["entries"][0]["closing_signed"] = "999"
    after = {
        a["area_id"]: a["basis_sha256"] for a in build_area_review(case)["workpapers"]
    }
    assert before["FIXED_ASSETS"] != after["FIXED_ASSETS"]
    assert before["TAXES"] == after["TAXES"]


def test_ordinary_requires_cash_flow_and_full_depth(case: dict) -> None:
    case["selected_form"] = "ORDINARY"
    p = proposal(case)
    with pytest.raises(ValueError, match="cash-flow"):
        propose_area_review(case, p, "C1", case["revision_id"])
    next(a for a in p["content"]["areas"] if a["area_id"] == "CASH_FLOW")[
        "status"
    ] = "ACTIVE"
    assert confirm(case, p)["profile"] == "FULL"


def test_streamlined_groups_all_full_review_objectives_without_dropping_them(
    case: dict,
) -> None:
    p = proposal(case)
    case["closing_workflow"]["opening"]["accounting_origin"] = "CONTABILITA_INTERNA"
    # Preserve the opening integrity when building this separate synthetic scenario.
    from area_review import _hash

    case["closing_workflow"]["genesis_sha256"] = _hash(
        case["closing_workflow"]["opening"]
    )
    case["closing_workflow"]["events"] = []
    case["closing_workflow"]["head_sha256"] = case["closing_workflow"]["genesis_sha256"]
    slim = confirm(case, p)
    assert slim["profile"] == "STREAMLINED"
    expected = {
        c["objective"]
        for c in review_catalogue()["controls"]
        if c["standard_id"] == "OIC_16"
    }
    combined = next(c for c in slim["controls"] if c["id"] == "OIC_16.COMBINED")
    assert all(text in combined["objective"] for text in expected)
    case["selected_form"] = "ORDINARY"
    assert build_area_review(case)["profile"] == "FULL"


def test_pre_2024_oic_pack_does_not_activate_oic34(case: dict) -> None:
    confirm(case)
    case["rule_pack_versions"]["oic_rule_pack"] = "OIC_2016_2023.1"
    view = build_area_review(case)
    assert (
        next(s for s in view["standards"] if s["id"] == "OIC_34")["period_eligible"]
        is False
    )
    assert not any(c["id"].startswith("OIC_34.") for c in view["controls"])


def test_changed_catalogue_or_regulatory_checksum_reopens_all_controls(
    case: dict,
) -> None:
    confirm(case)
    case["oic_rule_pack_checksum"] = "b" * 64
    assert build_area_review(case)["registry_current"] is False
    assert review_validation_issues(case)


def test_area_views_paginate_rows_and_filter_exact_area(case: dict) -> None:
    confirm(case)
    view = build_review_view(case, "AREA_WORKPAPERS", offset=1, limit=2)
    assert view["records"]["page"]["returned"] == 2
    assert view["records"]["page"]["has_more"] is True
    ui = build_workspace_snapshot(case, "AREA_CONTROLS", None, 0, 30, "FIXED_ASSETS")
    assert ui["review"]["records"]["items"]
    assert {c["area_id"] for c in ui["review"]["records"]["items"]} == {"FIXED_ASSETS"}


def test_exact_source_view_is_bounded_and_does_not_read_arbitrary_paths(
    case: dict,
) -> None:
    q = qualitative(case)
    view = build_workspace_snapshot(
        case, "AREA_SOURCE", None, q["start"], 30, q["document_id"]
    )
    assert view["review"]["excerpt"].startswith(q["quote"])
    with pytest.raises(ValueError, match="Unknown"):
        review_source(case, "/etc/passwd")


def test_decision_chain_tampering_rejected_after_case_checksum_recomputed(
    case: dict, tmp_path: Path
) -> None:
    confirm(case)
    case["area_review"]["events"][0]["payload"]["reason"] = "Changed history"
    save_case(tmp_path, case)
    with pytest.raises(ValueError, match="register integrity"):
        load_case(tmp_path)


def test_workbook_uses_current_view_and_never_treats_source_text_as_formula(
    case: dict,
) -> None:
    from openpyxl import load_workbook

    confirm(case)
    case["trial_balance"]["entries"][0][
        "account_description"
    ] = '=HYPERLINK("https://example.invalid","unsafe")'
    book = load_workbook(BytesIO(build_review_workbook(case)), data_only=False)
    assert len(book.sheetnames) == 15
    assert book["Conti"]["C2"].data_type == "s"
    assert book["Conti"]["C2"].hyperlink is None
    assert book["Riepilogo"]["B4"].value == case["revision_id"]
    assert book["Controlli"].max_row > 1
    assert book["Fascicolo"].max_row > 1
    assert book["Screening"].max_row > 1
    assert book["Rettifiche"].max_row > 1


def test_service_authorization_and_revision_bound_workbook(tmp_path: Path) -> None:
    acceptance = runner.AlfaAcceptance(PLUGIN, FIXTURES, tmp_path / "service")
    acceptance.run()
    acceptance.mutate("propose_area_review", proposal(acceptance.case()))
    with pytest.raises(PermissionError):
        acceptance.mutate("confirm_area_review", {"proposal_id": "plan1"})
    acceptance.mutate(
        "confirm_area_review",
        {
            "proposal_id": "plan1",
            "source_versions_reviewed": True,
            "oic_rule_pack_checksum": acceptance.case()["oic_rule_pack_checksum"],
            "reason": "Synthetic version-specific review.",
        },
        reviewer=True,
    )
    result = acceptance.service.review_workbook(
        acceptance.reviewer, "alfa_2025", acceptance.case()["revision_id"]
    )
    assert base64.b64decode(result["content_base64"]).startswith(b"PK")
    assert (
        len(
            list(
                (
                    tmp_path / "service/cases/alfa_synthetic/alfa_2025/review-workbooks"
                ).glob("*.xlsx")
            )
        )
        == 1
    )
    with pytest.raises(ValueError, match="Stale"):
        acceptance.service.review_workbook(acceptance.reviewer, "alfa_2025", "rev_0")


def test_real_mcp_transport_accepts_plan_and_preserves_unapproved_controls(
    tmp_path: Path,
) -> None:
    acceptance = runner.AlfaAcceptance(
        PLUGIN, FIXTURES, tmp_path / "mcp", transport="mcp"
    )
    acceptance.run()
    acceptance.mutate("propose_area_review", proposal(acceptance.case()))
    acceptance.mutate(
        "confirm_area_review",
        {
            "proposal_id": "plan1",
            "source_versions_reviewed": True,
            "oic_rule_pack_checksum": acceptance.case()["oic_rule_pack_checksum"],
            "reason": "Synthetic MCP reviewer source check.",
        },
        reviewer=True,
    )
    view = acceptance.service.call(
        acceptance.reviewer,
        "xbrl_case_get_review_view",
        {"case_id": "alfa_2025", "view": "AREA_DASHBOARD", "limit": 2},
    )
    assert view["status"] == "REVIEW_REQUIRED"
    assert view["records"]["page"]["returned"] == 2
    assert acceptance.status()["register_count"] == 13


def test_registered_text_pdf_extracts_all_pages_and_image_only_page_stays_unqualified(
    case: dict, tmp_path: Path
) -> None:
    import fitz

    source = tmp_path / "contract.pdf"
    pdf = fitz.open()
    pdf.new_page().insert_text(
        (40, 60), "Synthetic contract, current-period financing conditions."
    )
    pdf.save(source)
    pdf.close()
    attach_supporting_document(
        case, source, "CONTRACT", "Synthetic PDF", "C1", case["revision_id"]
    )
    selected = review_source(case, case["source_documents"][-1]["document_id"])
    assert "current-period" in selected["excerpt"]
    partial = tmp_path / "partial.pdf"
    pdf = fitz.open()
    pdf.new_page().insert_text((40, 60), "Readable page")
    pdf.new_page()
    pdf.save(partial)
    pdf.close()
    attach_supporting_document(
        case, partial, "CONTRACT", "Partial PDF", "C1", case["revision_id"]
    )
    assert (
        review_source(case, case["source_documents"][-1]["document_id"])["status"]
        == "REQUIRES_QUALIFIED_EXTRACTION"
    )


def test_model_evidence_pages_are_bounded_and_use_exact_offsets(case: dict) -> None:
    view = build_review_view(case, "REVIEW_SOURCES", offset=0, limit=1)
    assert view["records"]["page"]["returned"] == 1
    row = view["records"]["items"][0]
    assert row["start"] == 0
    assert len(row["excerpt"]) <= 4000
    assert row["untrusted_content"] is True


def test_repeated_workbook_export_is_byte_identical(case: dict) -> None:
    confirm(case)
    assert build_review_workbook(case) == build_review_workbook(case)


def test_qualitative_replacement_retains_old_history_and_supersedes_only_reviewed_interpretation(
    case: dict, tmp_path: Path
) -> None:
    q = qualitative(case)
    propose_qualitative_evidence(case, q, "C1", case["revision_id"])
    review_qualitative_evidence(
        case,
        {
            "proposal_id": q["id"],
            "outcome": "CONFIRMED",
            "reason": "Synthetic first review.",
        },
        "P1",
        case["revision_id"],
    )
    new_source = tmp_path / "new-minutes.md"
    new_source.write_text(
        "Synthetic changed vertenza with updated support for the current period."
    )
    old = q["document_id"]
    attach_supporting_document(
        case,
        new_source,
        "CORPORATE_RESOLUTION",
        "Changed minutes",
        "C1",
        case["revision_id"],
    )
    new = case["source_documents"][-1]["document_id"]
    record_review_source_replacement(case, old, new, "C1", case["revision_id"])
    from area_review import _qualitative_rows

    assert _qualitative_rows(case)[0]["status"] == "REVIEW_REQUIRED"
    text = new_source.read_text()
    fresh = {
        **q,
        "id": "qual2",
        "document_id": new,
        "start": 0,
        "end": len(text),
        "quote": text,
        "supersedes": q["id"],
    }
    propose_qualitative_evidence(case, fresh, "C1", case["revision_id"])
    assert _qualitative_rows(case)[0]["status"] == "REVIEW_REQUIRED"
    review_qualitative_evidence(
        case,
        {
            "proposal_id": "qual2",
            "outcome": "CONFIRMED",
            "reason": "Synthetic replacement review.",
        },
        "P1",
        case["revision_id"],
    )
    assert [p["status"] for p in _qualitative_rows(case)] == [
        "SUPERSEDED",
        "APPLICABLE",
    ]
    assert len(case["area_review"]["qualitative"]) == 2
    verify_area_review(case)


def test_area_guidance_stays_bounded_and_prioritizes_missing_plan(case: dict) -> None:
    from intelligence_contract import build_intelligence_packet

    propose_area_review(case, proposal(case), "C1", case["revision_id"])
    packet = build_intelligence_packet(case, "WORKFLOW_GUIDANCE", [])
    assert packet["reviewed_context"]["next_required_action"] == "REVIEW_AREA_PLAN"
    confirm_area_review(
        case,
        {
            "proposal_id": "plan1",
            "source_versions_reviewed": True,
            "oic_rule_pack_checksum": case["oic_rule_pack_checksum"],
            "reason": "Synthetic source version check.",
        },
        "P1",
        case["revision_id"],
    )
    packet = build_intelligence_packet(case, "WORKFLOW_GUIDANCE", [])
    assert len(packet["reviewed_context"]["area_review"]["controls"]) <= 20
    assert packet["context_scope"]["available"]["area_controls"] > 20


def test_account_fact_links_reconcile_the_full_statement_population(case: dict) -> None:
    case["mappings"] = [
        {
            "account_id": "acc_000001",
            "allocations": [
                {
                    "allocation_id": "one",
                    "canonical_line": "fixed",
                    "statement_section": "ASSETS",
                    "xbrl_concept": "itcc:fixed",
                    "xbrl_sign_multiplier": 1,
                    "current_amount": "80000",
                }
            ],
        },
        {
            "account_id": "acc_000002",
            "allocations": [
                {
                    "allocation_id": "two",
                    "canonical_line": "fixed",
                    "statement_section": "ASSETS",
                    "xbrl_concept": "itcc:fixed",
                    "xbrl_sign_multiplier": 1,
                    "current_amount": "-30000",
                }
            ],
        },
    ]
    case["canonical_facts"] = [
        {
            "fact_id": "fixed-net",
            "key": "fixed",
            "statement_section": "ASSETS",
            "xbrl_concept": "itcc:fixed",
            "xbrl_sign_multiplier": 1,
            "current_value": "50000",
        }
    ]
    area = next(
        a for a in confirm(case)["workpapers"] if a["area_id"] == "FIXED_ASSETS"
    )
    assert len(area["links"]) == 2
    assert area["reconciliations"] == [
        {"fact_id": "fixed-net", "difference": "0", "status": "MATCH"}
    ]
    case["canonical_facts"][0]["current_value"] = "50001"
    changed = next(
        a
        for a in build_area_review(case)["workpapers"]
        if a["area_id"] == "FIXED_ASSETS"
    )
    assert changed["reconciliations"][0]["status"] == "MISMATCH"
    assert changed["basis_sha256"] != area["basis_sha256"]


def test_later_document_confirmation_activates_area_with_current_professional_reason(
    case: dict,
) -> None:
    confirm(case)
    q = qualitative(case)
    propose_qualitative_evidence(case, q, "C1", case["revision_id"])
    pending = next(
        a for a in build_area_review(case)["workpapers"] if a["area_id"] == "PROVISIONS"
    )
    assert pending["status"] == "REVIEW_REQUIRED"
    review_qualitative_evidence(
        case,
        {
            "proposal_id": q["id"],
            "outcome": "CONFIRMED",
            "reason": "New documentary evidence requires the provisions area.",
        },
        "P1",
        case["revision_id"],
    )
    current = next(
        a for a in build_area_review(case)["workpapers"] if a["area_id"] == "PROVISIONS"
    )
    assert current["status"] == "ACTIVE"
    assert current["reason"] == "New documentary evidence requires the provisions area."
    assert current["controls"]
    assert all(c["status"] == "OPEN" for c in current["controls"])


def test_fact_links_do_not_cross_statement_concept_or_sign_when_labels_match(
    case: dict,
) -> None:
    case["mappings"] = [
        {
            "account_id": "acc_000001",
            "allocations": [
                {
                    "allocation_id": "selected",
                    "canonical_line": "shared_label",
                    "statement_section": "ASSETS",
                    "xbrl_concept": "itcc:fixed",
                    "xbrl_sign_multiplier": 1,
                    "current_amount": "80000",
                }
            ],
        }
    ]
    case["canonical_facts"] = [
        {
            "fact_id": "correct",
            "key": "shared_label",
            "statement_section": "ASSETS",
            "xbrl_concept": "itcc:fixed",
            "xbrl_sign_multiplier": 1,
            "current_value": "80000",
        },
        {
            "fact_id": "foreign",
            "key": "shared_label",
            "statement_section": "LIABILITIES",
            "xbrl_concept": "itcc:debt",
            "xbrl_sign_multiplier": -1,
            "current_value": "80000",
        },
    ]
    area = next(
        a for a in confirm(case)["workpapers"] if a["area_id"] == "FIXED_ASSETS"
    )
    assert area["links"][0]["fact_ids"] == ["correct"]
    assert [f["fact_id"] for f in area["facts"]] == ["correct"]
