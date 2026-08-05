from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bilancio-xbrl-it"
SCRIPTS = PLUGIN_ROOT / "scripts"
SUITE = PLUGIN_ROOT / "evals" / "golden_cases.json"


def _load_module(name: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bilancio_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


golden = _load_module("run_golden_cases")


def _suite_payload() -> dict[str, object]:
    return json.loads(SUITE.read_text(encoding="utf-8"))


def _fake_catalogue(suite: dict[str, object], checksum: str) -> dict[str, object]:
    concepts: dict[str, dict[str, object]] = {
        "itcc-ci:TotaleAttivo": {
            "qname": "itcc-ci:TotaleAttivo",
            "abstract": False,
            "type": "xbrli:monetaryItemType",
            "period_type": "instant",
            "forms": ["ORDINARY", "ABBREVIATED", "MICRO"],
        },
        "itcc-ci:TotalePassivo": {
            "qname": "itcc-ci:TotalePassivo",
            "abstract": False,
            "type": "xbrli:monetaryItemType",
            "period_type": "instant",
            "forms": ["ORDINARY", "ABBREVIATED", "MICRO"],
        },
        "itcc-ci:TotaleDisponibilitaLiquide": {
            "qname": "itcc-ci:TotaleDisponibilitaLiquide",
            "abstract": False,
            "type": "xbrli:monetaryItemType",
            "period_type": "instant",
            "balance": "debit",
            "forms": ["ORDINARY", "ABBREVIATED", "MICRO"],
        },
        "itcc-ci:DisponibilitaLiquideDepositiBancariPostali": {
            "qname": "itcc-ci:DisponibilitaLiquideDepositiBancariPostali",
            "abstract": False,
            "type": "xbrli:monetaryItemType",
            "period_type": "instant",
            "balance": "debit",
            "forms": ["ORDINARY"],
        },
        "itcc-ci:PassivoRateiRisconti": {
            "qname": "itcc-ci:PassivoRateiRisconti",
            "abstract": False,
            "type": "xbrli:monetaryItemType",
            "period_type": "instant",
            "balance": "credit",
            "forms": ["ORDINARY", "ABBREVIATED", "MICRO"],
        },
        "itcc-ci:UtilePerditaEsercizio": {
            "qname": "itcc-ci:UtilePerditaEsercizio",
            "abstract": False,
            "type": "xbrli:monetaryItemType",
            "period_type": "duration",
            "forms": ["ORDINARY", "ABBREVIATED", "MICRO"],
        },
        "itcc-ci:GoldenIncomeLeaf": {
            "qname": "itcc-ci:GoldenIncomeLeaf",
            "abstract": False,
            "type": "xbrli:monetaryItemType",
            "period_type": "duration",
            "forms": ["ORDINARY", "ABBREVIATED", "MICRO"],
        },
        "itcc-ci:IncrementoDecrementoDisponibilitaLiquide": {
            "qname": "itcc-ci:IncrementoDecrementoDisponibilitaLiquide",
            "abstract": False,
            "type": "xbrli:monetaryItemType",
            "period_type": "duration",
            "forms": ["ORDINARY"],
        },
        "itcc-ci:GoldenCashFlowLeaf": {
            "qname": "itcc-ci:GoldenCashFlowLeaf",
            "abstract": False,
            "type": "xbrli:monetaryItemType",
            "period_type": "duration",
            "forms": ["ORDINARY"],
        },
    }
    for qname in golden.NOTE_SECTION_CONCEPTS.values():
        concepts[qname] = {
            "qname": qname,
            "abstract": False,
            "type": "nonnum:textBlockItemType",
            "period_type": "instant",
            "forms": ["ORDINARY", "ABBREVIATED", "MICRO"],
        }
    for fixture in suite["cases"]:
        marker = fixture.get("marker")
        if marker:
            qname = marker["concept"]
            concepts[qname] = {
                "qname": qname,
                "abstract": False,
                "type": "xbrli:monetaryItemType",
                "period_type": (
                    "duration"
                    if qname == "itcc-ci:IncrementoDecrementoDisponibilitaLiquide"
                    else "instant"
                ),
                "forms": ["ORDINARY", "ABBREVIATED", "MICRO"],
            }
        narrative = fixture.get("narrative")
        if narrative:
            qname = narrative["concept"]
            concepts[qname] = {
                "qname": qname,
                "abstract": False,
                "type": "nonnum:textBlockItemType",
                "period_type": "instant",
                "forms": ["ORDINARY", "ABBREVIATED", "MICRO"],
            }
    presentation = []
    calculation = []
    role_by_form = {
        "ORDINARY": ("balance-ordinary", "income-ordinary", "cash-ordinary"),
        "ABBREVIATED": ("balance-abbreviated", "income-abbreviated", None),
        "MICRO": ("balance-micro", "income-micro", None),
    }
    for form, (balance_role, income_role, cash_role) in role_by_form.items():
        for order, (parent, child) in enumerate(
            (
                (
                    "itcc-ci:TotaleAttivo",
                    (
                        "itcc-ci:DisponibilitaLiquideDepositiBancariPostali"
                        if form == "ORDINARY"
                        else "itcc-ci:TotaleDisponibilitaLiquide"
                    ),
                ),
                ("itcc-ci:TotalePassivo", "itcc-ci:PassivoRateiRisconti"),
            ),
            start=1,
        ):
            row = {
                "form": form,
                "role": balance_role,
                "from": parent,
                "to": child,
                "order": str(order),
                "weight": "1",
            }
            presentation.append(row)
            calculation.append(row)
        income_row = {
            "form": form,
            "role": income_role,
            "from": "itcc-ci:UtilePerditaEsercizio",
            "to": "itcc-ci:GoldenIncomeLeaf",
            "order": "1",
            "weight": "1",
        }
        presentation.append(income_row)
        calculation.append(income_row)
        if cash_role:
            cash_row = {
                "form": form,
                "role": cash_role,
                "from": "itcc-ci:IncrementoDecrementoDisponibilitaLiquide",
                "to": "itcc-ci:GoldenCashFlowLeaf",
                "order": "1",
                "weight": "1",
            }
            presentation.append(cash_row)
            calculation.append(cash_row)
    for schedule_type in golden.GOLDEN_SCHEDULE_BINDINGS:
        root = f"itcc-ci:Golden{schedule_type.title().replace('_', '')}Table"
        fact = f"itcc-ci:Golden{schedule_type.title().replace('_', '')}Fact"
        concepts[root] = {
            "qname": root,
            "abstract": True,
            "type": "xbrli:stringItemType",
            "period_type": "instant",
            "forms": ["ORDINARY", "ABBREVIATED"],
        }
        concepts[fact] = {
            "qname": fact,
            "abstract": False,
            "type": "xbrli:monetaryItemType",
            "period_type": "duration",
            "forms": ["ORDINARY", "ABBREVIATED"],
        }
        for form in ("ORDINARY", "ABBREVIATED"):
            presentation.append(
                {
                    "form": form,
                    "role": f"schedule-{form.lower()}-{schedule_type.lower()}",
                    "from": root,
                    "to": fact,
                    "order": "1",
                    "weight": None,
                }
            )
    for concept in concepts.values():
        concept["is_item"] = True
        concept["is_tuple"] = False
    return {
        "schema_version": 2,
        "taxonomy_id": "PCI_2018-11-04",
        "taxonomy_package_sha256": checksum,
        "entry_points": {
            "ORDINARY": "taxonomy/ordinary.xsd",
            "ABBREVIATED": "taxonomy/abbreviated.xsd",
            "MICRO": "taxonomy/micro.xsd",
        },
        "namespaces": {"itcc-ci": "https://example.invalid/itcc-ci"},
        "concepts": list(concepts.values()),
        "relationships": {
            "presentation": presentation,
            "calculation": calculation,
            "dimension_domain": [],
            "domain_member": [],
        },
    }


def _fake_presentation_rule_pack(path: Path) -> Path:
    role_by_form = {
        "ORDINARY": [
            {"kind": "BALANCE_SHEET", "role": "balance-ordinary"},
            {"kind": "INCOME_STATEMENT", "role": "income-ordinary"},
            {"kind": "CASH_FLOW_INDIRECT", "role": "cash-ordinary"},
        ],
        "ABBREVIATED": [
            {"kind": "BALANCE_SHEET", "role": "balance-abbreviated"},
            {"kind": "INCOME_STATEMENT", "role": "income-abbreviated"},
        ],
        "MICRO": [
            {"kind": "BALANCE_SHEET", "role": "balance-micro"},
            {"kind": "INCOME_STATEMENT", "role": "income-micro"},
        ],
    }
    payload = {
        "schema_version": 1,
        "id": "TEST_PRESENTATION_2026.1",
        "effective_from": "2018-11-04",
        "effective_to": "2026-12-31",
        "taxonomy_id": "PCI_2018-11-04",
        "statement_sections": {
            "ASSETS": {
                "expected_role_kind": "BALANCE_SHEET",
                "root_concept": "itcc-ci:TotaleAttivo",
                "canonical_multiplier": "1",
            },
            "LIABILITIES_EQUITY": {
                "expected_role_kind": "BALANCE_SHEET",
                "root_concept": "itcc-ci:TotalePassivo",
                "canonical_multiplier": "-1",
            },
            "INCOME_RESULT": {
                "expected_role_kind": "INCOME_STATEMENT",
                "root_concept": "itcc-ci:UtilePerditaEsercizio",
                "canonical_multiplier": "1",
            },
        },
        "schedule_trigger_roots": {"TAXES": ["itcc-ci:NotInInventory"]},
        "cash_flow_contract": {
            "form": "ORDINARY",
            "net_change_root_concept": "itcc-ci:IncrementoDecrementoDisponibilitaLiquide",
        },
        "forms": {form: {"roles": roles} for form, roles in role_by_form.items()},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fake_schedule_taxonomy_rule_pack(path: Path) -> Path:
    schedules = {}
    for schedule_type in golden.GOLDEN_SCHEDULE_BINDINGS:
        root = f"itcc-ci:Golden{schedule_type.title().replace('_', '')}Table"
        schedules[schedule_type] = {
            "strategy": "TABLE_FACTS",
            "table_roots": [root],
        }
    payload = {
        "schema_version": 1,
        "id": "TEST_SCHEDULE_TAXONOMY_2026.1",
        "taxonomy_id": "PCI_2018-11-04",
        "effective_from": "2024-09-25",
        "effective_to": "2026-12-31",
        "forms": {
            "ORDINARY": schedules,
            "ABBREVIATED": schedules,
            "MICRO": {
                schedule_type: {"strategy": "TEXT_ONLY", "table_roots": []}
                for schedule_type in schedules
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _passing_validator(
    instance: Path,
    report: Path,
    taxonomy_package: Path | None,
    expected_taxonomy_sha256: str | None,
) -> dict[str, object]:
    result = {
        "status": "PASS",
        "instance": instance.name,
        "taxonomy_package": taxonomy_package.name if taxonomy_package else None,
        "taxonomy_package_sha256": expected_taxonomy_sha256,
    }
    report.write_text(json.dumps(result) + "\n", encoding="utf-8")
    return result


def test_golden_registry_covers_all_specification_scenarios() -> None:
    suite = golden.load_suite(SUITE)

    assert [item["number"] for item in suite["cases"]] == list(range(1, 25))
    assert sum(item["mode"] == "XBRL" for item in suite["cases"]) == 20
    assert sum(item["mode"] == "BOUNDARY" for item in suite["cases"]) == 4
    assert suite["cases"][0]["selected_form"] == "ABBREVIATED"
    assert suite["cases"][1]["selected_form"] == "ORDINARY"
    assert suite["cases"][2]["selected_form"] == "MICRO"
    assert (
        suite["cases"][23]["prior_narrative_text"]
        != suite["cases"][23]["narrative"]["text"]
    )


def test_golden_runner_renders_and_records_all_cases(tmp_path: Path) -> None:
    suite = _suite_payload()
    package = tmp_path / "taxonomy.zip"
    package.write_bytes(b"synthetic taxonomy package")
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(json.dumps(_fake_catalogue(suite, checksum)), encoding="utf-8")
    output = tmp_path / "run"
    presentation_pack = _fake_presentation_rule_pack(
        tmp_path / "presentation-rule-pack.json"
    )
    schedule_taxonomy_pack = _fake_schedule_taxonomy_rule_pack(
        tmp_path / "schedule-taxonomy-rule-pack.json"
    )

    manifest = golden.run_suite(
        SUITE,
        catalogue,
        package,
        output,
        validator=_passing_validator,
        presentation_rule_pack_path=presentation_pack,
        schedule_taxonomy_rule_pack_path=schedule_taxonomy_pack,
    )

    assert manifest["status"] == "PASS"
    assert manifest["case_count"] == 24
    assert manifest["passed_count"] == 24
    assert manifest["failed_count"] == 0
    assert manifest["external_tebeni_status"] == "NOT_RUN_USER_CONTROLLED"
    xbrl_results = [item for item in manifest["results"] if item["mode"] == "XBRL"]
    assert all(
        item["workflow_checks"]["public_lifecycle_executed"] for item in xbrl_results
    )
    assert all(
        item["workflow_checks"]["statutory_presentation_status"] == "COMPLETE"
        for item in xbrl_results
    )
    assert all(
        item["workflow_checks"]["disclosure_triggered_count"]
        == item["workflow_checks"]["disclosure_complete_count"]
        for item in xbrl_results
    )
    assert manifest["results"][1]["workflow_checks"]["schedule_types"] == ["CASH_FLOW"]
    assert set(manifest["results"][13]["workflow_checks"]["schedule_types"]) == {
        "CASH_FLOW",
        "PROVISIONS",
        "TFR",
    }
    assert (output / "golden-run-manifest.json").is_file()
    assert manifest["results"][19]["observation"] == ("PROFESSIONAL_TREATMENT_RECORDED")
    assert manifest["results"][20]["observation"] == (
        "UNSUPPORTED_ACCOUNTING_FRAMEWORK"
    )
    assert manifest["results"][21]["observation"] == "EVIDENCE_KEPT_UNTRUSTED"
    assert manifest["results"][22]["observation"] == "PARSER_CONFIRMATION_BLOCKED"
    assert (
        manifest["results"][23]["rendered_checks"]["stale_narrative_review"][
            "prior_text_not_reused"
        ]
        is True
    )
    assert (
        manifest["results"][23]["workflow_checks"]["prior_narrative_redline_recorded"]
        is True
    )


def test_golden_runner_refuses_nonempty_output_directory(tmp_path: Path) -> None:
    suite = _suite_payload()
    package = tmp_path / "taxonomy.zip"
    package.write_bytes(b"synthetic taxonomy package")
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(json.dumps(_fake_catalogue(suite, checksum)), encoding="utf-8")
    output = tmp_path / "run"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="must be empty"):
        golden.run_suite(
            SUITE,
            catalogue,
            package,
            output,
            validator=_passing_validator,
            presentation_rule_pack_path=_fake_presentation_rule_pack(
                tmp_path / "presentation-rule-pack.json"
            ),
        )

    assert (output / "existing.txt").read_text(encoding="utf-8") == "keep"


def test_official_golden_schedule_rejects_missing_semantic_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = {
        "schedules": {
            "EQUITY": {
                "strategy": "TABLE_FACTS",
                "allowed_concepts": [
                    {
                        "xbrl_concept": "itcc-ci:UnrelatedMonetaryFact",
                        "type": "xbrli:monetaryItemType",
                        "period_type": "duration",
                    }
                ],
            }
        }
    }
    monkeypatch.setattr(
        golden,
        "build_schedule_table_inventory",
        lambda *_args: inventory,
    )
    monkeypatch.setattr(
        golden,
        "schedule_adapter_records",
        lambda _schedule: [
            {
                "fact_id": "equity_contributions",
                "fact_type": "MONETARY",
                "key": "contributions",
            }
        ],
    )

    with pytest.raises(ValueError, match="Official golden schedule binding"):
        golden._schedule_taxonomy_decisions(
            {
                "selected_form": "ORDINARY",
                "schedules": [{"schedule_type": "EQUITY"}],
            },
            {"official_source": "https://example.invalid/official-taxonomy.zip"},
            {},
        )
