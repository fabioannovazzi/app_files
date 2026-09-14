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
from pathlib import Path

import pytest

from tests.plugins._teaching_release import record_native_check
from tests.plugins.test_teaching_kit_execution import _bound_case

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
def test_oic_kit_prepares_current_statements_and_retains_missing_evidence(
    tmp_path, monkeypatch, language, phase, record_property
):
    catalogue = Path(os.environ["TEACHING_TAXONOMY_CATALOGUE"])
    assert catalogue.is_file(), "Build the official checksum-verified taxonomy first"
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "bilancio-oic",
        "bilancio-xbrl-it",
        phase,
        language=language,
    )
    xbrl = _native(monkeypatch)
    output = Path(run["output_dir"])
    inputs = Path(run["context"]["run_root"]) / "inputs"
    source = next(inputs.rglob("*.csv"))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    registry = _read(MODULE / "taxonomy/PCI_2018-11-04.registry.json")
    rules = _read(MODULE / "rulepacks/it/statutory-forms-2026.1.json")
    payload = {
        "case_id": f"teaching_{language}_{phase}",
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
    case = xbrl.create_case(output / "accounts", payload, rules, actor)
    case = xbrl.ingest_trial_balance(case, source, actor, case["revision_id"])
    assert case["trial_balance"]["calibration"]["unmatched_rows"] == 0
    assert len(case["trial_balance"]["entries"]) == 7
    case = xbrl.confirm_parser(
        case, "TURNOVER_EXCLUDES_OPENING", actor, case["revision_id"]
    )
    case = xbrl.determine_forms(
        case,
        [{"year": 2025, "assets": "27000", "revenue": "25000", "employees": "1"}],
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
        "400": ("ValoreProduzioneRicaviVenditePrestazioni", "INCOME_STATEMENT", "-1"),
        "500": ("CostiProduzioneGodimentoBeniTerzi", "INCOME_STATEMENT", "1"),
        "510": ("CostiProduzioneServizi", "INCOME_STATEMENT", "1"),
    }
    suggestions = []
    decisions = []
    for account in packet["untrusted_evidence"]["accounts"]:
        concept, section, sign = selections[account["account_code"]]
        suggestions.append(
            {
                "account_id": account["account_id"],
                "candidate_concept": "itcc-ci:" + concept,
                "canonical_line": account["account_description"],
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
                        "canonical_line": account["account_description"],
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
        "-14000.00" if phase == "demo" else "-13800.00"
    )
    assert all(fact["prior_value"] is None for fact in case["statements"]["facts"])
    case = xbrl.activate_disclosures(
        case,
        _read(MODULE / "rulepacks/it/disclosures-2026.1.json"),
        actor,
        case["revision_id"],
    )
    assert case["disclosure_coverage"]["triggered_count"] > 0
    case = xbrl.run_validation(case, actor, case["revision_id"])
    case = xbrl.create_preview(
        case, output / "draft-accounts.html", actor, case["revision_id"]
    )
    case = xbrl.run_validation(case, actor, case["revision_id"])
    assert any(issue["severity"] == "BLOCKER" for issue in case["validation"]["issues"])
    for name, value in (
        ("statements.json", case["statements"]),
        ("validation.json", case["validation"]),
    ):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))
    preview = (output / "draft-accounts.html").read_text()
    assert ("Costi per servizi" if language == "it" else "Service expense") in preview
    assert ("5200.00" if phase == "practice" else "5000.00") in preview
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert case["approval"] is None
    xbrl.save_case(output / "accounts", case)
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="bilancio-oic",
        language=language,
        phase=phase,
    )
