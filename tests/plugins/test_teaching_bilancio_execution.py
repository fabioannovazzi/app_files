"""Run the OIC teaching inputs through the actual local accounts workflow.

Parser, form and mapping decisions below are synthetic regression fixtures.
They do not stand for a learner's participation or professional approval. The
official taxonomy must be supplied to this integration check, never fabricated.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from tests.plugins._teaching_release import record_native_check
from tests.plugins.test_teaching_kit_execution import (
    _bound_case,
    _complete_teaching_case,
    _write,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "plugins/bilancio-xbrl-it"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _native(monkeypatch):
    monkeypatch.syspath_prepend(str(MODULE / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "teaching_bilancio_case", MODULE / "scripts/xbrl_case.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("language", ["it", "en"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_oic_kit_prepares_reviewable_accounts_and_retains_prior_version(
    tmp_path, monkeypatch, language, phase, record_property
):
    catalogue = Path(os.environ["TEACHING_TAXONOMY_CATALOGUE"])
    assert catalogue.is_file(), "Build the official checksum-verified taxonomy first"
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "bilancio-oic",
        "bilancio-xbrl-it",
        "demo",
        language=language,
    )
    xbrl = _native(monkeypatch)
    ledger = _execute_oic_run(run, language, "demo", xbrl, catalogue, tmp_path / "case")
    results = [{"phase": "demo", "run": run}]
    if phase == "practice":
        from courseware.library import CourseLibrary

        context = run["context"]
        original = {
            path: path.read_bytes()
            for path in Path(context["run_root"]).rglob("*")
            if path.is_file()
        }
        prior_case = Path(run["output_dir"]) / "accounts"
        prior_record = _read(prior_case / "case.json")
        kit = CourseLibrary(ROOT / "plugins/vera", {"bilancio-oic"}).render(
            "bilancio-oic", language, tmp_path / "practice-kit"
        )
        imports = [
            ledger.import_document(
                tmp_path / "case",
                context["client_id"],
                context["engagement_id"],
                Path(path),
                "source",
            )
            for path in kit["practice_files"]
        ]
        version = _read(ROOT / "plugins/vera/.codex-plugin/plugin.json")["version"]
        prepared = ledger.prepare_run(
            tmp_path / "case",
            context["client_id"],
            context["engagement_id"],
            "bilancio-xbrl-it",
            version,
            input_ids=[item["receipt"]["input_id"] for item in imports],
            purpose="Update the fictional accounts while retaining the first version",
        )
        updated = ledger.start_run(
            tmp_path / "case", context["engagement_id"], prepared["run"]["run_id"]
        )
        _execute_oic_run(
            updated,
            language,
            "practice",
            xbrl,
            catalogue,
            tmp_path / "case",
            prior_case_root=prior_case,
        )
        updated_case = _read(Path(updated["output_dir"]) / "accounts/case.json")
        assert updated_case["case_id"] == prior_record["case_id"]
        assert int(updated_case["revision_id"].split("_")[-1]) > int(
            prior_record["revision_id"].split("_")[-1]
        )
        assert updated["context"]["engagement_id"] == context["engagement_id"]
        assert updated["context"]["run_id"] != context["run_id"]
        assert all(path.read_bytes() == content for path, content in original.items())
        results.append({"phase": "practice", "run": updated})
    _write(tmp_path / "execution.json", {"language": language, "results": results})
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="bilancio-oic",
        language=language,
        phase=phase,
    )


def _execute_oic_run(
    run, language, phase, xbrl, catalogue, client_root, *, prior_case_root=None
):
    """Run the current case engine; all review decisions here are test fixtures."""
    output = Path(run["output_dir"])
    inputs = Path(run["context"]["run_root"]) / "inputs"
    source = next(inputs.rglob("*.csv"))
    support = next(inputs.rglob("year-end*.txt"))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    registry = _read(MODULE / "taxonomy/PCI_2018-11-04.registry.json")
    rules = _read(MODULE / "rulepacks/it/statutory-forms-2026.1.json")
    payload = {
        "case_id": f"teaching_{language}",
        "tenant_id": "fictional_teaching_studio",
        "entity": {
            "legal_name": "Servizi Riva S.r.l.",
            "tax_identifier": "IT00000000000",
            "registered_office": "Milano, Italia",
            "legal_form": "SRL",
            "accounting_framework": "OIC",
            "listed": False,
            "regulated_sector": False,
            "consolidated": False,
            "final_liquidation": False,
            "first_financial_year": True,
            "micro_exclusion_flags": [],
        },
        "period": {"start": "2025-01-01", "end": "2025-12-31"},
        "oic_rule_pack": "OIC_2024_2025.1",
        "filing_campaign_year": 2026,
        "taxonomy_checksum": registry["taxonomy_package_sha256"],
        "output_language": language,
    }
    actor = "synthetic-integration-fixture-not-human-approval"
    case = (
        xbrl.load_case(prior_case_root)
        if prior_case_root is not None
        else xbrl.create_case(output / "accounts", payload, rules, actor)
    )
    case = xbrl.ingest_trial_balance(case, source, actor, case["revision_id"])
    case = xbrl.attach_supporting_document(
        case,
        support,
        "SUPPORTING_EVIDENCE",
        "Fictional year-end declarations and supplied tax information",
        actor,
        case["revision_id"],
    )
    support_ref = case["source_documents"][-1]["document_id"]
    assert case["trial_balance"]["calibration"]["unmatched_rows"] == 0
    assert len(case["trial_balance"]["entries"]) == 9
    case = xbrl.confirm_parser(
        case, "TURNOVER_EXCLUDES_OPENING", actor, case["revision_id"]
    )
    case = xbrl.determine_forms(
        case,
        [{"year": 2025, "assets": "27000", "revenue": "25000", "employees": "0"}],
        rules,
        actor,
        case["revision_id"],
    )
    case = xbrl.select_form(case, "MICRO", actor, case["revision_id"])
    presentation = _read(MODULE / "rulepacks/it/statutory-presentation-2026.1.json")
    case = xbrl.record_taxonomy_mapping_index(
        case, catalogue, presentation, actor, case["revision_id"]
    )
    (output / "mapping-index.json").write_text(
        json.dumps(case["taxonomy_mapping_index"], ensure_ascii=False, indent=2)
    )
    subjects = [row["account_id"] for row in case["trial_balance"]["entries"]]
    packet = xbrl.build_intelligence_packet(case, "ACCOUNT_MAPPING", subjects)
    (output / "mapping-packet.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2)
    )
    selections = {
        "100": ("TotaleDisponibilitaLiquide", "ASSETS", "1"),
        "110": ("CreditiEsigibiliEntroEsercizioSuccessivo", "ASSETS", "1"),
        "200": ("PatrimonioNettoCapitale", "LIABILITIES_EQUITY", "-1"),
        "210": ("DebitiEsigibiliEntroEsercizioSuccessivo", "LIABILITIES_EQUITY", "-1"),
        "220": ("DebitiEsigibiliEntroEsercizioSuccessivo", "LIABILITIES_EQUITY", "-1"),
        "400": ("ValoreProduzioneRicaviVenditePrestazioni", "INCOME_STATEMENT", "-1"),
        "500": ("CostiProduzioneGodimentoBeniTerzi", "INCOME_STATEMENT", "1"),
        "510": ("CostiProduzioneServizi", "INCOME_STATEMENT", "1"),
        "600": (
            "ImposteRedditoEsercizioCorrentiDifferiteAnticipateImposteCorrenti",
            "INCOME_STATEMENT",
            "1",
        ),
    }
    suggestions = []
    decisions = []
    for account in packet["untrusted_evidence"]["accounts"]:
        concept, section, sign = selections[account["account_code"]]
        canonical_line = (
            (
                "Debiti entro dodici mesi"
                if language == "it"
                else "Payables due within twelve months"
            )
            if account["account_code"] in {"210", "220"}
            else account["account_description"]
        )
        if account["account_code"] == "200":
            canonical_line = "Patrimonio netto" if language == "it" else "Equity"
        suggestions.append(
            {
                "account_id": account["account_id"],
                "candidate_concept": "itcc-ci:" + concept,
                "canonical_line": canonical_line,
                "statement_section": section,
                "confidence_band": "HIGH",
                "rationale": "Fixed interpretation of this fictional labelled account; review the actual source before applying.",
                "evidence_refs": account["source_refs"],
                "risk_flags": ["SYNTHETIC_INTEGRATION_FIXTURE"],
                "alternatives": [],
            }
        )
        decisions.append(
            {
                "account_id": account["account_id"],
                "decision": "ACCEPTED",
                "allocations": [
                    {
                        "canonical_line": canonical_line,
                        "statement_section": section,
                        "xbrl_concept": "itcc-ci:" + concept,
                        "xbrl_sign_multiplier": sign,
                        "current_amount": account["closing_signed"],
                        "evidence_status": "OBSERVED",
                    }
                ],
            }
        )
    case = xbrl.record_intelligence_suggestion(
        case,
        "ACCOUNT_MAPPING",
        subjects,
        {"suggestions": suggestions},
        {
            "provider": "regression-fixture",
            "model": "fixed-interpretation-not-live-model",
            "prompt_template_version": "bilancio-teaching-fixture-v1",
        },
        actor,
        case["revision_id"],
    )
    assert case["mappings"] == []
    assert case["intelligence_runs"][-1]["status"] == "MODEL_SUGGESTED"
    case = xbrl.apply_mapping_decisions(case, decisions, actor, case["revision_id"])
    case = xbrl.build_statements(case, actor, case["revision_id"])
    totals = case["statements"]["section_totals"]
    assert totals["ASSETS"]["current"] == "27000.00"
    assert totals["INCOME_STATEMENT"]["current"] == (
        "-10500.00" if phase == "demo" else "-10350.00"
    )
    assert all(fact["prior_value"] is None for fact in case["statements"]["facts"])
    case = _prepare_reviewable_accounts(
        xbrl,
        case,
        catalogue,
        presentation,
        support_ref,
        support.name,
        actor,
        language,
        phase,
    )
    assert case["disclosure_coverage"]["triggered_count"] > 0
    case = xbrl.run_validation(case, actor, case["revision_id"])
    case = xbrl.create_preview(
        case, output / "draft-accounts.html", actor, case["revision_id"]
    )
    case = xbrl.run_validation(case, actor, case["revision_id"])
    assert case["validation"]["status"] == "PASS", case["validation"]["issues"]
    case = xbrl.prepare_xbrl_review(
        case,
        catalogue,
        Path(os.environ["TEACHING_TAXONOMY_PACKAGE"]),
        output / "xbrl-review",
        actor,
        case["revision_id"],
    )
    assert case["xbrl_review"]["status"] == "PASS", _read(
        output / "xbrl-review/local-xbrl-validation.json"
    )
    assert "arelle" in case["xbrl_review"]["processor"].lower()
    assert case["validation"]["status"] == "PASS", case["validation"]["issues"]
    for name, value in (
        ("statements.json", case["statements"]),
        ("validation.json", case["validation"]),
    ):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))
    preview = (output / "draft-accounts.html").read_text()
    assert ("Costi per servizi" if language == "it" else "Service expense") in preview
    expected_amounts = {
        ("it", "demo"): "5.000,00",
        ("it", "practice"): "5.200,00",
        ("en", "demo"): "5,000.00",
        ("en", "practice"): "5,200.00",
    }
    assert expected_amounts[(language, phase)] in preview
    assert f'<html lang="{language}">' in preview
    assert "REVIEW.PREVIEW_REQUIRED" not in preview
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert case["approval"] is None
    xbrl.save_case(output / "accounts", case)
    return _complete_teaching_case(run, client_root)


def _prepare_reviewable_accounts(
    xbrl,
    case,
    catalogue,
    presentation,
    support_ref,
    support_name,
    actor,
    language,
    phase,
):
    """Apply authored test decisions to the full fictional source, never bundle them."""
    italian = language == "it"
    source_label = f"{support_name}, A–G"
    income = -Decimal(
        case["statements"]["section_totals"]["INCOME_STATEMENT"]["current"]
    )
    assert income == (Decimal("10500") if phase == "demo" else Decimal("10350"))
    source_refs = sorted(
        {
            ref
            for fact in case["statements"]["facts"]
            if fact["statement_section"] == "INCOME_STATEMENT"
            for ref in fact["source_refs"]
        }
    )
    # The source expressly excludes closing entries. The reviewed presentation
    # bridge shows the calculated result in the P&L and in equity; it does not
    # post anything to a ledger or change the supplied account balances.
    case = xbrl.record_adjustments(
        case,
        [
            {
                "adjustment_id": "result_presentation",
                "reason": (
                    "Presentare il risultato calcolato dai conti rivisti: il file esclude le scritture di chiusura. Decisione sintetica di test."
                    if italian
                    else "Present the result calculated from reviewed accounts: the source excludes closing entries. Synthetic test decision."
                ),
                "lines": [
                    {
                        "canonical_line": (
                            "Risultato dell’esercizio"
                            if italian
                            else "Result for the year"
                        ),
                        "statement_section": "INCOME_RESULT",
                        "xbrl_concept": "itcc-ci:UtilePerditaEsercizio",
                        "xbrl_sign_multiplier": "1",
                        "current_amount": str(income),
                        "source_refs": [*source_refs, support_ref],
                    },
                    {
                        "canonical_line": ("Patrimonio netto" if italian else "Equity"),
                        "statement_section": "EQUITY_RESULT",
                        "xbrl_concept": "itcc-ci:PatrimonioNettoUtilePerditaEsercizio",
                        "xbrl_sign_multiplier": "-1",
                        "current_amount": str(-income),
                        "source_refs": [*source_refs, support_ref],
                    },
                ],
            }
        ],
        actor,
        case["revision_id"],
    )
    case = xbrl.build_statements(case, actor, case["revision_id"])
    assert (
        case["statements"]["section_totals"]["LIABILITIES_EQUITY"]["current"]
        == "-27000.00"
    )
    present = {fact["xbrl_concept"] for fact in case["canonical_facts"]}
    # These are explicit test-review dispositions supported by the declaration
    # of all non-zero balances and the absent categories in A–F. No production
    # code turns an absent account into a zero decision.
    decisions = [
        {
            "xbrl_concept": concept["xbrl_concept"],
            "current_status": "ZERO_CONFIRMED",
            "reason": (
                "Nessun saldo per questa voce dopo la revisione della popolazione completa e delle categorie assenti dichiarate in "
                if italian
                else "No balance for this item after reviewing the complete population and declared absent categories in "
            )
            + source_label
            + ". Synthetic regression decision.",
            "source_refs": [support_ref],
        }
        for concept in case["taxonomy_mapping_index"]["concepts"]
        if concept["mapping_allowed"] is True and concept["xbrl_concept"] not in present
    ]
    case = xbrl.record_statutory_presentation(
        case, catalogue, presentation, decisions, actor, case["revision_id"]
    )
    assert case["statutory_presentation"]["status"] == "COMPLETE", case[
        "statutory_presentation"
    ]["issues"]
    footer_reasons = {
        "guarantees_commitments_contingencies": (
            "La dichiarazione E esclude garanzie, impegni e passività potenziali.",
            "Declaration E states there are no guarantees, commitments or contingent liabilities.",
        ),
        "director_auditor_compensation": (
            "La dichiarazione E indica un amministratore non remunerato e nessun compenso ai revisori.",
            "Declaration E identifies an unpaid director and no auditor compensation.",
        ),
        "own_and_parent_shares": (
            "La dichiarazione E esclude azioni proprie o della controllante.",
            "Declaration E states there are no own or parent-company shares.",
        ),
    }
    case = xbrl.record_micro_reporting(
        case,
        {
            "mode": "FOOTER_ONLY",
            "footer_items": [
                {
                    "key": key,
                    "status": "NOT_APPLICABLE_CONFIRMED",
                    "reason": value[0 if italian else 1],
                    "source_refs": [support_ref],
                }
                for key, value in footer_reasons.items()
            ],
        },
        actor,
        case["revision_id"],
    )
    case = _record_teaching_schedules(
        xbrl, case, catalogue, support_ref, actor, language, phase, income
    )
    rule_pack = _read(MODULE / "rulepacks/it/disclosures-2026.1.json")
    case = xbrl.activate_disclosures(case, rule_pack, actor, case["revision_id"])
    flag_reasons = {
        "EMPLOYEES_OR_BODIES_PRESENT": "E: one unpaid director, no employees",
        "FINANCE_LEASES_PRESENT": "C/E: ordinary office rent, no finance leases",
        "GROUP_OR_PARTICIPATIONS_PRESENT": "C/E: no participations and no group",
        "OTHER_STATUTORY_DISCLOSURES_REQUIRED": "E/F: reviewed declared absence of other events or obligations",
        "REVENUE_OR_EXCEPTIONAL_DETAIL_REQUIRED": "B/E: ordinary fixed-fee services, no exceptional components",
    }
    assert set(xbrl.manual_disclosure_flags(rule_pack)) == set(flag_reasons)
    case = xbrl.record_disclosure_trigger_decisions(
        case,
        [
            {
                "flag": flag,
                "status": (
                    "TRIGGERED"
                    if flag == "EMPLOYEES_OR_BODIES_PRESENT"
                    else "NOT_APPLICABLE_CONFIRMED"
                ),
                "reason": f"Synthetic test review of {support_name}, {reason}",
                "source_refs": [support_ref],
            }
            for flag, reason in flag_reasons.items()
        ],
        actor,
        case["revision_id"],
    )
    negative_reasons = {
        "guarantees_and_commitments": "E: no guarantees or commitments",
        "contingent_liabilities": "E: no contingent liabilities or litigation",
        "related_party_transactions": "E: no relevant related-party transactions",
        "off_balance_sheet_arrangements": "E: no off-balance-sheet agreements",
        "derivatives": "E: no derivatives",
        "post_closing_events": "F: no material subsequent event",
        "accounting_policy_changes": "A/F: first year, no policy change",
        "prior_period_errors": "A/F: no prior year or prior-period error",
        "going_concern_uncertainties": "F: management cash estimate and statement of no uncertainty",
        "non_market_transactions": "E: no non-market transactions",
        "double_format_events": "F: no reported substantive representation difference",
    }
    positive = {
        "basis_of_preparation": {
            "first_year": True,
            "form": "MICRO",
            "period": "2025",
            "source": "A",
        },
        "accounting_policies": {
            "basis": "nominal short-term balances, no financing components or adjustments",
            "source": "B/C",
        },
        "oic34_revenue_policy_review": {
            "services_completed": True,
            "fixed_fees": True,
            "unperformed_obligations": False,
            "source": "B",
        },
        "employees_corporate_bodies": {
            "average_employees": 0,
            "directors": 1,
            "compensation": "0",
            "source": "E",
        },
        "taxes_review": {
            "current_tax": "3500" if phase == "demo" else "3450",
            "deferred_tax": "0",
            "source": "D",
        },
        "result_allocation": {
            "proposal": (
                "Trattenere il risultato in azienda: quota prevista a riserva legale e residuo a nuovo, senza dividendi. Proposta ancora da rivedere e deliberare."
                if italian
                else "Retain the result: required legal-reserve allocation and the remainder carried forward, with no dividend. Proposal still subject to review and resolution."
            ),
            "resolution_approved": False,
            "source": "G",
        },
    }
    active = {
        q["answer_key"] for q in case["questionnaire"] if q["state"] != "NOT_TRIGGERED"
    }
    unanswered = active - negative_reasons.keys() - positive.keys()
    assert not unanswered, sorted(unanswered)
    answers = [
        {
            "key": key,
            "status": "NOT_APPLICABLE_CONFIRMED",
            "value": False,
            "reason": f"Synthetic test review of {support_name}, {reason}",
            "source_refs": [support_ref],
        }
        for key, reason in negative_reasons.items()
    ]
    answers.extend(
        {
            "key": key,
            "status": "ACCEPTED",
            "value": positive[key],
            "reason": f"Synthetic test interpretation of {support_name}, {positive[key]['source']}",
            "source_refs": [support_ref],
        }
        for key in sorted(active - negative_reasons.keys())
    )
    related = next(
        item for item in answers if item["key"] == "related_party_transactions"
    )
    related.update(
        {
            "status": "ACCEPTED",
            "value": {
                "owner_capital_contribution": "10000",
                "other_transactions": False,
            },
            "reason": f"Synthetic review of {support_name}, B/E/G: paid-in capital is disclosed; no other related-party transaction.",
        }
    )
    return xbrl.record_disclosure_answers(case, answers, actor, case["revision_id"])


def _record_teaching_schedules(
    xbrl, case, catalogue, support_ref, actor, language, phase, income
):
    """Replay explicit fictional schedule interpretations; no live review claim."""
    from schedule_engine import schedule_adapter_records

    italian = language == "it"
    tax = "3500" if phase == "demo" else "3450"
    purchases = "5000" if phase == "demo" else "5200"
    payable = "3000" if phase == "demo" else "3200"
    maturity = {
        "opening_amount": "0",
        "reclassifications": "0",
        "exchange_effects": "0",
        "other_movements": "0",
        "due_after_next_year": "0",
        "over_five_years": "0",
        "geography": "ITALY",
        "related_party_class": "NONE_CONFIRMED",
        "currency": "EUR",
    }
    receivable_row = {
        **maturity,
        "row_id": "customers",
        "label": "Clienti" if italian else "Customers",
        "increases": "25000",
        "decreases": "17000",
        "closing_amount": "8000",
        "due_within_next_year": "8000",
        "gross_closing_amount": "8000",
        "allowance_opening": "0",
        "allowance_additions": "0",
        "allowance_uses": "0",
        "allowance_releases": "0",
        "allowance_other_movements": "0",
        "allowance_closing": "0",
        "receivable_class": "TRADE",
        "factoring_status": "NOT_FACTORED_CONFIRMED",
        "measurement_basis": "NOMINAL_VALUE",
        "tax_class": "NON_TAX",
    }
    payable_terms = {
        **maturity,
        "secured_amount": "0",
        "security_type": "NONE_CONFIRMED",
        "guarantee_asset": "NONE_CONFIRMED",
        "covenant_status": "NONE_CONFIRMED",
        "shareholder_financing_status": "NONE_CONFIRMED",
    }
    payable_rows = [
        {
            **payable_terms,
            "row_id": "suppliers",
            "label": "Fornitori" if italian else "Suppliers",
            "increases": purchases,
            "decreases": "2000",
            "closing_amount": payable,
            "due_within_next_year": payable,
            "payable_class": "TRADE",
        },
        {
            **payable_terms,
            "row_id": "current_tax",
            "label": "Erario" if italian else "Tax authority",
            "increases": tax,
            "decreases": "0",
            "closing_amount": tax,
            "due_within_next_year": tax,
            "payable_class": "CURRENT_TAX",
        },
    ]
    equity_terms = {
        "opening_amount": "0",
        "prior_result_allocation": "0",
        "reductions": "0",
        "dividends": "0",
        "transfers_in": "0",
        "transfers_out": "0",
        "reserve_uses": "0",
        "other_movements": "0",
        "prior_uses": "NONE_CONFIRMED",
        "treasury_shares_status": "NONE_CONFIRMED",
        "fair_value_reserve_status": "NONE_CONFIRMED",
    }
    equity_rows = [
        {
            **equity_terms,
            "row_id": "capital",
            "label": "Capitale sociale" if italian else "Share capital",
            "contributions": "10000",
            "current_year_result": "0",
            "closing_amount": "10000",
            "equity_class": "SHARE_CAPITAL",
            "origin": "OWNER_CONTRIBUTIONS",
            "availability": "SHARE_CAPITAL",
            "distributability": "NOT_DISTRIBUTABLE_AS_PROFIT",
        },
        {
            **equity_terms,
            "row_id": "result",
            "label": "Risultato dell’esercizio" if italian else "Result for the year",
            "contributions": "0",
            "current_year_result": str(income),
            "closing_amount": str(income),
            "equity_class": "CURRENT_YEAR_RESULT",
            "origin": "REVIEWED_CURRENT_YEAR_ACCOUNTS",
            "availability": "ALLOCATION_PENDING",
            "distributability": "RESOLUTION_PENDING_NO_DISTRIBUTION",
        },
    ]
    tax_row = {
        "row_id": "tax",
        "label": "Imposte correnti" if italian else "Current tax",
        "opening_amount": "0",
        "increases": tax,
        "decreases": "0",
        "closing_amount": tax,
        "current_tax_expense": tax,
        "tax_base": "14000" if phase == "demo" else "13800",
        "temporary_difference": "0",
        "recognised_amount": tax,
        "unrecognised_amount": "0",
        "tax_type": "CURRENT_TAX",
        "jurisdiction": "IT",
        "recoverability_assessment": "NOT_APPLICABLE_CURRENT_TAX_EXPENSE",
    }
    account_lines = {
        item["account_id"]: item["allocations"][0]["canonical_line"]
        for item in case["mappings"]
    }
    code_lines = {
        item["account_code"]: account_lines[item["account_id"]]
        for item in case["trial_balance"]["entries"]
    }
    for kind, line, multiplier, rows in [
        ("RECEIVABLES", code_lines["110"], "1", [receivable_row]),
        ("PAYABLES", code_lines["210"], "-1", payable_rows),
        ("EQUITY", code_lines["200"], "-1", equity_rows),
        ("TAXES", code_lines["600"], "1", [tax_row]),
    ]:
        refs = sorted(
            {
                support_ref,
                *(
                    ref
                    for fact in case["canonical_facts"]
                    if fact["key"] == line
                    for ref in fact["source_refs"]
                ),
            }
        )
        case = xbrl.record_schedule(
            case,
            {
                "schedule_id": f"teaching_{kind.lower()}",
                "schedule_type": kind,
                "statement_line": line,
                "statement_multiplier": multiplier,
                "rows": [
                    {**row, "evidence_status": "USER_CONFIRMED", "source_refs": refs}
                    for row in rows
                ],
            },
            actor,
            case["revision_id"],
        )
        assert case["schedules"][-1]["status"] == "COMPLETE", case["schedules"][-1][
            "issues"
        ]
    adapter = _read(MODULE / "rulepacks/it/schedule-taxonomy-2026.1.json")
    decisions = []
    for schedule in case["schedules"]:
        kind = schedule["schedule_type"]
        # The reviewed micro/footnote choice has no separate note-table facts.
        # Preserve every supporting cell and record its explicit disposition.
        decisions.append(
            {
                "schedule_type": kind,
                "strategy": "TEXT_ONLY",
                "outputs": [],
                "omissions": [
                    {
                        "schedule_fact_id": item["fact_id"],
                        "status": "NOT_APPLICABLE_CONFIRMED",
                        "reason": (
                            "Dato conservato nel prospetto di supporto; la forma micro con informazioni in calce scelta per questo caso non prevede una tabella di nota separata per questo dato. "
                            if italian
                            else "Cell retained in the supporting schedule; the micro form with statutory footnotes chosen for this case has no separate note-table fact for this cell. "
                        )
                        + str(item["key"]),
                    }
                    for item in schedule_adapter_records(schedule)
                ],
            }
        )
    return xbrl.record_schedule_taxonomy_adapter(
        case, catalogue, adapter, decisions, actor, case["revision_id"]
    )
