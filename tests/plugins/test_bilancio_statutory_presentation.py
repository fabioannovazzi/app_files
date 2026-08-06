from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bilancio-xbrl-it"
SCRIPTS = PLUGIN_ROOT / "scripts"
STATUTORY_FORMS = PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2026.1.json"
PACKAGE_CHECKSUM = "a" * 64
ROLE = "https://example.invalid/role/primary"


def _load_module(name: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bilancio_statutory_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


statutory_presentation = _load_module("statutory_presentation")
xbrl_case = _load_module("xbrl_case")
audit_statutory_presentation = _load_module("audit_statutory_presentation")


def _concept(
    qname: str, *, abstract: bool = False, period_type: str = "instant"
) -> dict[str, object]:
    return {
        "qname": qname,
        "type": "xbrli:stringItemType" if abstract else "xbrli:monetaryItemType",
        "period_type": period_type,
        "abstract": abstract,
        "is_item": True,
        "is_tuple": False,
        "forms": ["ABBREVIATED"],
        "label_it": qname,
    }


def _catalogue() -> dict[str, object]:
    return {
        "schema_version": 2,
        "taxonomy_id": "PCI_2018-11-04",
        "taxonomy_package_sha256": PACKAGE_CHECKSUM,
        "entry_points": {"ABBREVIATED": "https://example.invalid/abbreviated.xsd"},
        "namespaces": {"itcc": "https://example.invalid/itcc"},
        "concepts": [
            _concept("itcc:Root", abstract=True),
            _concept("itcc:Total"),
            _concept("itcc:A"),
            _concept("itcc:B"),
            _concept("itcc:UnrelatedNote"),
        ],
        "relationships": {
            "presentation": [
                {
                    "form": "ABBREVIATED",
                    "role": ROLE,
                    "from": "itcc:Root",
                    "to": "itcc:Total",
                },
                {
                    "form": "ABBREVIATED",
                    "role": ROLE,
                    "from": "itcc:Total",
                    "to": "itcc:A",
                },
                {
                    "form": "ABBREVIATED",
                    "role": ROLE,
                    "from": "itcc:Total",
                    "to": "itcc:B",
                },
            ],
            "calculation": [
                {
                    "form": "ABBREVIATED",
                    "role": ROLE,
                    "from": "itcc:Total",
                    "to": "itcc:A",
                    "weight": "1",
                },
                {
                    "form": "ABBREVIATED",
                    "role": ROLE,
                    "from": "itcc:Total",
                    "to": "itcc:B",
                    "weight": "1",
                },
            ],
        },
    }


def _presentation_rule_pack() -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": "TEST_PRESENTATION_1",
        "taxonomy_id": "PCI_2018-11-04",
        "effective_from": "2018-11-04",
        "effective_to": "2026-12-31",
        "statement_sections": {
            "ASSETS": {
                "expected_role_kind": "BALANCE_SHEET",
                "root_concept": "itcc:Total",
                "canonical_multiplier": "1",
            }
        },
        "schedule_trigger_roots": {"FIXED_ASSETS": ["itcc:A"]},
        "forms": {
            "ABBREVIATED": {
                "roles": [
                    {
                        "kind": "BALANCE_SHEET",
                        "role": ROLE,
                        "expected": {
                            "presentation_relationships": 3,
                            "calculation_relationships": 2,
                            "monetary_concepts": 3,
                            "leaf_concepts": 2,
                            "total_concepts": 1,
                        },
                    }
                ]
            }
        },
    }


def _fact(qname: str, current: str, prior: str) -> dict[str, object]:
    return {
        "fact_id": qname.replace(":", "_"),
        "xbrl_concept": qname,
        "xbrl_sign_multiplier": "1",
        "current_value": current,
        "prior_value": prior,
        "statement_section": "ASSETS",
        "status": "OBSERVED",
        "source_refs": [f"source:{qname}"],
    }


def _coverage_case(
    *facts: dict[str, object], current_total: str = "100", prior_total: str = "90"
) -> dict[str, object]:
    return {
        "selected_form": "ABBREVIATED",
        "period": {"start": "2025-01-01", "end": "2025-12-31"},
        "statements": {
            "facts": list(facts),
            "section_totals": {
                "ASSETS": {
                    "current": current_total,
                    "prior": prior_total,
                }
            },
        },
        "canonical_facts": list(facts),
        "taxonomy_facts": [],
    }


def _created_case(tmp_path: Path) -> dict[str, object]:
    forms = json.loads(STATUTORY_FORMS.read_text(encoding="utf-8"))
    case = xbrl_case.create_case(
        tmp_path / "case",
        {
            "case_id": "case_statutory_2025",
            "tenant_id": "tenant_1",
            "entity": {
                "legal_name": "Statutory S.r.l.",
                "tax_identifier": "IT00000000000",
                "registered_office": "Milano (MI), Italia",
                "legal_form": "SRL",
                "accounting_framework": "OIC",
                "listed": False,
                "regulated_sector": False,
                "consolidated": False,
                "final_liquidation": False,
                "first_financial_year": False,
                "prior_year_form": "ABBREVIATED",
                "micro_exclusion_flags": [],
            },
            "period": {"start": "2025-01-01", "end": "2025-12-31"},
            "oic_rule_pack": "OIC_2024_2025.1",
            "filing_campaign_year": 2026,
            "taxonomy_checksum": PACKAGE_CHECKSUM,
        },
        forms,
        "preparer_1",
    )
    case["selected_form"] = "ABBREVIATED"
    case["form_analysis"] = {"eligible_forms": ["ABBREVIATED", "ORDINARY"]}
    case["canonical_facts"] = [
        _fact("itcc:A", "100", "90"),
        _fact("itcc:B", "-20", "-10"),
    ]
    case["statements"] = {
        "facts": deepcopy(case["canonical_facts"]),
        "section_totals": {"ASSETS": {"current": "80", "prior": "80"}},
        "reporting_precision": 0,
        "rounding_adjustments": [],
    }
    return case


def test_complete_leaf_facts_derive_official_calculation_total() -> None:
    result = statutory_presentation.build_statutory_presentation_coverage(
        _coverage_case(
            _fact("itcc:A", "100", "90"),
            _fact("itcc:B", "-20", "-10"),
            current_total="80",
            prior_total="80",
        ),
        _catalogue(),
        _presentation_rule_pack(),
        [],
        "reviewer_1",
    )

    assert result["status"] == "COMPLETE"
    assert result["summary"] == {
        "required_leaf_concepts": 2,
        "explicit_decisions": 0,
        "derived_output_facts": 1,
        "confirmed_zero_output_facts": 0,
        "missing_period_decisions": 0,
        "issues": 0,
        "semantic_issues": 0,
    }
    assert result["output_facts"] == [
        {
            "fact_id": "presentation_rollup_000001",
            "xbrl_concept": "itcc:Total",
            "current_value": "80",
            "prior_value": "80",
            "status": "DERIVED",
            "source_refs": [],
            "derivation": {
                "operation": "OFFICIAL_TAXONOMY_CALCULATION_ROLLUP",
                "inventory_sha256": result["inventory"]["inventory_sha256"],
            },
            "confirmed_by": None,
            "reason": None,
        }
    ]
    assert result["derived_schedule_triggers"] == [
        {
            "schedule_type": "FIXED_ASSETS",
            "basis": "OFFICIAL_TAXONOMY_CALCULATION_DESCENDANT",
            "fact_refs": ["itcc_A"],
            "xbrl_concepts": ["itcc:A"],
        }
    ]


def test_selected_form_taxonomy_index_exposes_only_official_primary_concepts(
    tmp_path: Path,
) -> None:
    case = _created_case(tmp_path)
    catalogue_path = tmp_path / "catalogue.json"
    catalogue_path.write_text(json.dumps(_catalogue()), encoding="utf-8")

    result = xbrl_case.record_taxonomy_mapping_index(
        case,
        catalogue_path,
        _presentation_rule_pack(),
        "reviewer_1",
        case["revision_id"],
    )

    concepts = {
        item["xbrl_concept"] for item in result["taxonomy_mapping_index"]["concepts"]
    }
    assert concepts == {"itcc:A", "itcc:B", "itcc:Total"}
    assert "itcc:UnrelatedNote" not in concepts


def test_absent_leaf_requires_explicit_period_decisions() -> None:
    result = statutory_presentation.build_statutory_presentation_coverage(
        _coverage_case(_fact("itcc:A", "100", "90")),
        _catalogue(),
        _presentation_rule_pack(),
        [],
        "reviewer_1",
    )

    assert result["status"] == "INCOMPLETE"
    assert result["missing"] == [
        {"xbrl_concept": "itcc:B", "period": "current"},
        {"xbrl_concept": "itcc:B", "period": "prior"},
    ]
    assert result["issues"] == []
    assert result["output_facts"] == []


@pytest.mark.parametrize(
    ("status", "expected_b_fact"),
    [
        ("ZERO_CONFIRMED", True),
        ("NOT_APPLICABLE_CONFIRMED", False),
    ],
)
def test_reviewed_absence_resolves_coverage_without_silent_zero(
    status: str, expected_b_fact: bool
) -> None:
    result = statutory_presentation.build_statutory_presentation_coverage(
        _coverage_case(_fact("itcc:A", "100", "90")),
        _catalogue(),
        _presentation_rule_pack(),
        [
            {
                "xbrl_concept": "itcc:B",
                "current_status": status,
                "prior_status": status,
                "reason": "Confermato dal professionista sul fascicolo annuale.",
                "source_refs": ["review:annual-close"],
            }
        ],
        "reviewer_1",
    )

    assert result["status"] == "COMPLETE"
    output = {item["xbrl_concept"]: item for item in result["output_facts"]}
    assert ("itcc:B" in output) is expected_b_fact
    assert output["itcc:Total"]["current_value"] == "100"
    assert output["itcc:Total"]["prior_value"] == "90"


def test_inconsistent_existing_total_is_a_blocking_coverage_issue() -> None:
    result = statutory_presentation.build_statutory_presentation_coverage(
        _coverage_case(
            _fact("itcc:A", "100", "90"),
            _fact("itcc:B", "-20", "-10"),
            _fact("itcc:Total", "81", "79"),
            current_total="80",
            prior_total="80",
        ),
        _catalogue(),
        _presentation_rule_pack(),
        [],
        "reviewer_1",
    )

    assert result["status"] == "INCOMPLETE"
    assert [item["period"] for item in result["issues"]] == [
        "current",
        "prior",
        "current",
        "prior",
    ]
    assert {item["code"] for item in result["issues"]} == {
        "TOTAL_MISMATCH",
        "STATEMENT_XBRL_ROOT_MISMATCH",
    }


def test_valid_non_primary_concept_cannot_replace_statement_presentation() -> None:
    decisions = [
        {
            "xbrl_concept": concept,
            "current_status": "ZERO_CONFIRMED",
            "prior_status": "ZERO_CONFIRMED",
            "reason": "Controlled negative test confirmation.",
            "source_refs": ["review:controlled-negative"],
        }
        for concept in ("itcc:A", "itcc:B")
    ]

    result = statutory_presentation.build_statutory_presentation_coverage(
        _coverage_case(_fact("itcc:UnrelatedNote", "100", "90")),
        _catalogue(),
        _presentation_rule_pack(),
        decisions,
        "reviewer_1",
    )

    assert result["status"] == "INCOMPLETE"
    assert result["semantic_reconciliation"]["status"] == "FAIL"
    assert {item["code"] for item in result["semantic_reconciliation"]["issues"]} == {
        "SUBSTANTIVE_TAXONOMY_MISMATCH",
        "STATEMENT_XBRL_ROOT_MISMATCH",
    }


def test_canonical_statement_fact_requires_an_xbrl_concept() -> None:
    unmapped = _fact("itcc:UnrelatedNote", "100", "90")
    unmapped["xbrl_concept"] = None
    decisions = [
        {
            "xbrl_concept": concept,
            "current_status": "ZERO_CONFIRMED",
            "prior_status": "ZERO_CONFIRMED",
            "reason": "Controlled negative test confirmation.",
            "source_refs": ["review:controlled-negative"],
        }
        for concept in ("itcc:A", "itcc:B")
    ]

    result = statutory_presentation.build_statutory_presentation_coverage(
        _coverage_case(unmapped),
        _catalogue(),
        _presentation_rule_pack(),
        decisions,
        "reviewer_1",
    )

    assert result["status"] == "INCOMPLETE"
    assert result["semantic_reconciliation"]["issues"][0]["code"] == (
        "CANONICAL_FACT_XBRL_CONCEPT_REQUIRED"
    )


def test_decision_contract_rejects_unsupported_authoritative_field() -> None:
    with pytest.raises(ValueError, match="unsupported fields"):
        statutory_presentation.build_statutory_presentation_coverage(
            _coverage_case(_fact("itcc:A", "100", "90")),
            _catalogue(),
            _presentation_rule_pack(),
            [
                {
                    "xbrl_concept": "itcc:B",
                    "current_status": "ZERO_CONFIRMED",
                    "prior_status": "ZERO_CONFIRMED",
                    "reason": "Confermato dal professionista.",
                    "accepted": True,
                }
            ],
            "reviewer_1",
        )


def test_decision_cannot_overwrite_an_existing_period_fact() -> None:
    case = _coverage_case(_fact("itcc:A", "100", "90"))
    case["taxonomy_facts"] = [
        {
            "xbrl_concept": "itcc:B",
            "fact_type": "MONETARY",
            "period": "current_instant",
            "value": "10",
            "dimensions": {},
        }
    ]

    with pytest.raises(ValueError, match="unnecessary for existing current"):
        statutory_presentation.build_statutory_presentation_coverage(
            case,
            _catalogue(),
            _presentation_rule_pack(),
            [
                {
                    "xbrl_concept": "itcc:B",
                    "current_status": "ZERO_CONFIRMED",
                    "prior_status": "NOT_APPLICABLE_CONFIRMED",
                    "reason": "Confermato dal professionista.",
                }
            ],
            "reviewer_1",
        )


def test_inventory_count_guard_detects_official_network_drift() -> None:
    rule_pack = _presentation_rule_pack()
    rule_pack["forms"]["ABBREVIATED"]["roles"][0]["expected"]["leaf_concepts"] = 3

    with pytest.raises(ValueError, match="inventory count changed"):
        statutory_presentation.build_primary_presentation_inventory(
            _catalogue(), rule_pack, "ABBREVIATED"
        )


def test_coverage_rejects_rule_pack_outside_reporting_period() -> None:
    case = _coverage_case(_fact("itcc:A", "100", "90"))
    case["period"] = {"start": "2027-01-01", "end": "2027-12-31"}

    with pytest.raises(ValueError, match="not effective"):
        statutory_presentation.build_statutory_presentation_coverage(
            case,
            _catalogue(),
            _presentation_rule_pack(),
            [],
            "reviewer_1",
        )


def test_controlled_catalogue_audit_closes_every_configured_form() -> None:
    report = audit_statutory_presentation.audit_statutory_presentation(
        _catalogue(), _presentation_rule_pack()
    )

    assert report["test_nature"] == "CONTROLLED_STRUCTURAL_ZERO_COVERAGE_ONLY"
    assert report["forms"][0]["controlled_closure"] == {
        "status": "COMPLETE",
        "explicit_decisions": 2,
        "output_fact_count": 3,
        "missing_period_decisions": 0,
        "issues": 0,
    }
    assert len(report["report_sha256"]) == 64


def test_production_case_defaults_to_required_statutory_review(tmp_path: Path) -> None:
    case = _created_case(tmp_path)

    validation = xbrl_case.validate_case(case)

    assert case["statutory_presentation_required"] is True
    assert any(
        issue["rule_id"] == "STATEMENT.STATUTORY_PRESENTATION_REQUIRED"
        for issue in validation["issues"]
    )


def test_recorded_complete_coverage_is_rendered_into_approved_xbrl(
    tmp_path: Path,
) -> None:
    case = _created_case(tmp_path)
    catalogue_path = tmp_path / "catalogue.json"
    catalogue_path.write_text(json.dumps(_catalogue()), encoding="utf-8")

    case = xbrl_case.record_taxonomy_mapping_index(
        case,
        catalogue_path,
        _presentation_rule_pack(),
        "reviewer_1",
        case["revision_id"],
    )

    result = xbrl_case.record_statutory_presentation(
        case,
        catalogue_path,
        _presentation_rule_pack(),
        [],
        "reviewer_1",
        case["revision_id"],
    )
    snapshot = xbrl_case._case_payload_for_hash(result)
    result["approval"] = {
        "snapshot": snapshot,
        "snapshot_hash": xbrl_case._sha256_bytes(xbrl_case._canonical_json(snapshot)),
    }
    result["state"] = "APPROVED"

    root = etree.fromstring(xbrl_case.render_xbrl(result, catalogue_path))

    assert result["statutory_presentation"]["status"] == "COMPLETE"
    totals = root.findall("{https://example.invalid/itcc}Total")
    assert [(item.get("contextRef"), item.text) for item in totals] == [
        ("current_instant", "80.00"),
        ("prior_instant", "80.00"),
    ]


def test_renderer_rejects_approved_snapshot_without_statutory_review(
    tmp_path: Path,
) -> None:
    case = _created_case(tmp_path)
    catalogue_path = tmp_path / "catalogue.json"
    catalogue_path.write_text(json.dumps(_catalogue()), encoding="utf-8")
    snapshot = xbrl_case._case_payload_for_hash(case)
    case["approval"] = {
        "snapshot": snapshot,
        "snapshot_hash": xbrl_case._sha256_bytes(xbrl_case._canonical_json(snapshot)),
    }
    case["state"] = "APPROVED"

    with pytest.raises(ValueError, match="complete primary statutory"):
        xbrl_case.render_xbrl(case, catalogue_path)
