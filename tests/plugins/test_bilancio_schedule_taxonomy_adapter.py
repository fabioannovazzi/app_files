from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "bilancio-xbrl-it" / "scripts"
PACKAGE_CHECKSUM = "a" * 64
ROLE = "https://example.invalid/role/notes"


def _load_module(name: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bilancio_schedule_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load_module("schedule_taxonomy_adapter")
schedule_engine = _load_module("schedule_engine")
audit = _load_module("audit_schedule_taxonomy")


def _catalogue() -> dict[str, object]:
    return {
        "schema_version": 2,
        "taxonomy_id": "PCI_2018-11-04",
        "taxonomy_package_sha256": PACKAGE_CHECKSUM,
        "concepts": [
            {
                "qname": "itcc:ProvisionTable",
                "type": "xbrli:stringItemType",
                "period_type": "instant",
                "abstract": True,
                "is_item": True,
                "is_tuple": False,
                "label_it": "Fondi",
            },
            {
                "qname": "itcc:ProvisionOpening",
                "type": "xbrli:monetaryItemType",
                "period_type": "instant",
                "abstract": False,
                "is_item": True,
                "is_tuple": False,
                "label_it": "Saldo iniziale",
            },
            {
                "qname": "itcc:ProvisionClass",
                "type": "xbrli:stringItemType",
                "period_type": "instant",
                "abstract": False,
                "is_item": True,
                "is_tuple": False,
                "label_it": "Classe",
            },
            {
                "qname": "itcc:ProvisionTuple",
                "type": "xbrli:stringItemType",
                "period_type": None,
                "abstract": False,
                "is_item": False,
                "is_tuple": True,
                "label_it": "Contenitore righe",
            },
            {
                "qname": "itcc:OutsideTable",
                "type": "xbrli:monetaryItemType",
                "period_type": "instant",
                "abstract": False,
                "is_item": True,
                "is_tuple": False,
                "label_it": "Fuori prospetto",
            },
            {
                "qname": "itcc:TupleAmount",
                "type": "xbrli:monetaryItemType",
                "period_type": "instant",
                "abstract": False,
                "is_item": True,
                "is_tuple": False,
                "label_it": "Importo riga",
            },
            {
                "qname": "itcc:TupleLabel",
                "type": "xbrli:stringItemType",
                "period_type": "instant",
                "abstract": False,
                "is_item": True,
                "is_tuple": False,
                "label_it": "Etichetta riga",
            },
        ],
        "relationships": {
            "presentation": [
                {
                    "form": "ORDINARY",
                    "role": ROLE,
                    "from": "itcc:ProvisionTable",
                    "to": "itcc:ProvisionOpening",
                    "order": "1",
                },
                {
                    "form": "ORDINARY",
                    "role": ROLE,
                    "from": "itcc:ProvisionTable",
                    "to": "itcc:ProvisionClass",
                    "order": "2",
                },
                {
                    "form": "ORDINARY",
                    "role": ROLE,
                    "from": "itcc:ProvisionTable",
                    "to": "itcc:ProvisionTuple",
                    "order": "3",
                },
                {
                    "form": "ORDINARY",
                    "role": ROLE,
                    "from": "itcc:ProvisionTuple",
                    "to": "itcc:TupleAmount",
                    "order": "1",
                },
                {
                    "form": "ORDINARY",
                    "role": ROLE,
                    "from": "itcc:ProvisionTuple",
                    "to": "itcc:TupleLabel",
                    "order": "2",
                },
            ]
        },
    }


def _rule_pack() -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": "IT_SCHEDULE_TEST_1",
        "taxonomy_id": "PCI_2018-11-04",
        "effective_from": "2025-01-01",
        "effective_to": "2025-12-31",
        "forms": {
            "ORDINARY": {
                "PROVISIONS": {
                    "strategy": "TABLE_FACTS",
                    "table_roots": ["itcc:ProvisionTable"],
                }
            }
        },
    }


def _case() -> dict[str, object]:
    return {
        "selected_form": "ORDINARY",
        "output_language": "it",
        "statements": {"facts": []},
        "statutory_presentation": {"status": "COMPLETE", "output_facts": []},
        "taxonomy_facts": [],
        "schedules": [
            {
                "schedule_id": "provisions_1",
                "schedule_type": "PROVISIONS",
                "status": "COMPLETE",
                "rows": [
                    {
                        "row_id": "risks",
                        "source_refs": ["doc_1_row_1"],
                        "provision_class": "Fondo contenzioso",
                        "opening_amount": "10",
                        "additions": "3",
                        "uses": "1",
                        "releases": "0",
                        "other_increases": "0",
                        "other_decreases": "0",
                        "closing_amount": "12",
                    }
                ],
            }
        ],
    }


def _decisions() -> list[dict[str, object]]:
    prefix = "schedule:provisions_1:risks:"
    mapped = {"opening_amount", "provision_class"}
    all_fields = {
        "opening_amount",
        "additions",
        "uses",
        "releases",
        "other_increases",
        "other_decreases",
        "closing_amount",
        "provision_class",
    }
    return [
        {
            "schedule_type": "PROVISIONS",
            "strategy": "TABLE_FACTS",
            "outputs": [
                {
                    "xbrl_concept": "itcc:ProvisionOpening",
                    "period": "current_instant",
                    "inputs": [
                        {
                            "schedule_fact_id": f"{prefix}opening_amount",
                            "multiplier": "1",
                        }
                    ],
                },
                {
                    "xbrl_concept": "itcc:ProvisionClass",
                    "period": "current_instant",
                    "inputs": [{"schedule_fact_id": f"{prefix}provision_class"}],
                },
            ],
            "omissions": [
                {
                    "schedule_fact_id": f"{prefix}{field}",
                    "status": "REPRESENTED_ELSEWHERE_CONFIRMED",
                    "reason": "Not represented by this controlled miniature table.",
                }
                for field in sorted(all_fields - mapped)
            ],
        }
    ]


def test_compile_schedule_taxonomy_adapter_derives_reviewed_table_facts() -> None:
    result = adapter.compile_schedule_taxonomy_adapter(
        _case(), _catalogue(), _rule_pack(), _decisions(), "reviewer_1"
    )

    assert result["status"] == "COMPLETE"
    assert result["coverage"][0]["input_fact_count"] == 8
    assert result["coverage"][0]["mapped_input_count"] == 2
    assert {
        (fact["xbrl_concept"], fact["fact_type"], fact["value"])
        for fact in result["generated_facts"]
    } == {
        ("itcc:ProvisionOpening", "MONETARY", "10"),
        ("itcc:ProvisionClass", "TEXT", "Fondo contenzioso"),
    }


def test_schedule_inventory_excludes_non_item_tuple_containers() -> None:
    result = adapter.build_schedule_table_inventory(
        _catalogue(), _rule_pack(), "ORDINARY"
    )

    allowed = {
        item["xbrl_concept"]
        for item in result["schedules"]["PROVISIONS"]["allowed_concepts"]
    }
    assert "itcc:ProvisionTuple" not in allowed


def test_schedule_adapter_rejects_arbitrary_monetary_scaling() -> None:
    decisions = _decisions()
    decisions[0]["outputs"][0]["inputs"][0]["multiplier"] = "0.5"

    with pytest.raises(ValueError, match="explicit sign conventions"):
        adapter.compile_schedule_taxonomy_adapter(
            _case(), _catalogue(), _rule_pack(), decisions, "reviewer_1"
        )


def test_schedule_adapter_rejects_duplicate_inputs_in_one_output() -> None:
    decisions = _decisions()
    repeated = dict(decisions[0]["outputs"][0]["inputs"][0])
    decisions[0]["outputs"][0]["inputs"].append(repeated)

    with pytest.raises(ValueError, match="repeats source fact"):
        adapter.compile_schedule_taxonomy_adapter(
            _case(), _catalogue(), _rule_pack(), decisions, "reviewer_1"
        )


def test_schedule_adapter_preserves_repeated_tuple_rows() -> None:
    case = _case()
    second_row = deepcopy(case["schedules"][0]["rows"][0])
    second_row.update(
        {
            "row_id": "legal",
            "source_refs": ["doc_1_row_2"],
            "provision_class": "Fondo legale",
            "opening_amount": "20",
        }
    )
    case["schedules"][0]["rows"].append(second_row)
    mapped_fields = {"opening_amount", "provision_class"}
    all_fields = {
        "opening_amount",
        "additions",
        "uses",
        "releases",
        "other_increases",
        "other_decreases",
        "closing_amount",
        "provision_class",
    }
    outputs = []
    omissions = []
    for row_id in ("risks", "legal"):
        prefix = f"schedule:provisions_1:{row_id}:"
        outputs.extend(
            [
                {
                    "xbrl_concept": "itcc:TupleAmount",
                    "period": "current_instant",
                    "inputs": [
                        {
                            "schedule_fact_id": f"{prefix}opening_amount",
                            "multiplier": "1",
                        }
                    ],
                },
                {
                    "xbrl_concept": "itcc:TupleLabel",
                    "period": "current_instant",
                    "inputs": [{"schedule_fact_id": f"{prefix}provision_class"}],
                },
            ]
        )
        omissions.extend(
            {
                "schedule_fact_id": f"{prefix}{field}",
                "status": "REPRESENTED_ELSEWHERE_CONFIRMED",
                "reason": "Not represented by this controlled miniature table.",
            }
            for field in sorted(all_fields - mapped_fields)
        )
    decisions = [
        {
            "schedule_type": "PROVISIONS",
            "strategy": "TABLE_FACTS",
            "outputs": outputs,
            "omissions": omissions,
        }
    ]

    result = adapter.compile_schedule_taxonomy_adapter(
        case, _catalogue(), _rule_pack(), decisions, "reviewer_1"
    )

    assert len(result["generated_facts"]) == 4
    assert {fact["tuple_instance_id"] for fact in result["generated_facts"]} == {
        "provisions_1:risks",
        "provisions_1:legal",
    }
    assert all(
        fact["tuple_path"] == ["itcc:ProvisionTuple"]
        for fact in result["generated_facts"]
    )


def test_compile_schedule_taxonomy_adapter_reconciles_existing_primary_fact() -> None:
    case = _case()
    case["statutory_presentation"] = {
        "status": "COMPLETE",
        "output_facts": [
            {
                "xbrl_concept": "itcc:ProvisionOpening",
                "period_type": "instant",
                "current_value": "10",
                "prior_value": "0",
            }
        ],
    }

    result = adapter.compile_schedule_taxonomy_adapter(
        case, _catalogue(), _rule_pack(), _decisions(), "reviewer_1"
    )

    assert [fact["xbrl_concept"] for fact in result["generated_facts"]] == [
        "itcc:ProvisionClass"
    ]
    assert (
        result["coverage"][0]["reconciled_existing_facts"][0]["xbrl_concept"]
        == "itcc:ProvisionOpening"
    )


def test_compile_schedule_taxonomy_adapter_rejects_uncovered_schedule_cell() -> None:
    decisions = _decisions()
    decisions[0]["omissions"] = decisions[0]["omissions"][1:]

    with pytest.raises(ValueError, match="coverage is incomplete"):
        adapter.compile_schedule_taxonomy_adapter(
            _case(), _catalogue(), _rule_pack(), decisions, "reviewer_1"
        )


def test_compile_schedule_taxonomy_adapter_rejects_concept_outside_table() -> None:
    decisions = _decisions()
    decisions[0]["outputs"][0]["xbrl_concept"] = "itcc:OutsideTable"

    with pytest.raises(ValueError, match="outside the active schedule tables"):
        adapter.compile_schedule_taxonomy_adapter(
            _case(), _catalogue(), _rule_pack(), decisions, "reviewer_1"
        )


def test_compile_schedule_taxonomy_adapter_rejects_all_cells_omitted() -> None:
    decisions = _decisions()
    prefix = "schedule:provisions_1:risks:"
    decisions[0]["outputs"] = []
    decisions[0]["omissions"].extend(
        [
            {
                "schedule_fact_id": f"{prefix}opening_amount",
                "status": "REPRESENTED_ELSEWHERE_CONFIRMED",
                "reason": "Controlled reviewer attempted to omit the whole table.",
            },
            {
                "schedule_fact_id": f"{prefix}provision_class",
                "status": "REPRESENTED_ELSEWHERE_CONFIRMED",
                "reason": "Controlled reviewer attempted to omit the whole table.",
            },
        ]
    )

    with pytest.raises(ValueError, match="at least one mapped fact"):
        adapter.compile_schedule_taxonomy_adapter(
            _case(), _catalogue(), _rule_pack(), decisions, "reviewer_1"
        )


def test_payable_schedule_rejects_secured_amount_above_closing_balance() -> None:
    row = {field: "0" for field in schedule_engine.schedule_template_fields("PAYABLES")}
    row.update(
        {
            "row_id": "bank",
            "source_refs": ["loan_plan_1"],
            "evidence_status": "OBSERVED",
            "opening_amount": "10",
            "closing_amount": "10",
            "due_within_next_year": "10",
            "secured_amount": "11",
            "payable_class": "BANK",
            "geography": "ITALY",
            "related_party_class": "NONE_CONFIRMED",
            "security_type": "MORTGAGE",
            "guarantee_asset": "PROPERTY",
            "covenant_status": "REVIEWED",
            "shareholder_financing_status": "NONE_CONFIRMED",
            "currency": "EUR",
        }
    )
    payload = {
        "schedule_id": "payables_1",
        "schedule_type": "PAYABLES",
        "statement_line": "DEBT",
        "rows": [row],
    }
    statement_facts = [
        {"canonical_line": "DEBT", "current_value": "10", "prior_value": "10"}
    ]

    result = schedule_engine.normalize_schedule(payload, statement_facts)

    assert result["status"] == "INCOMPLETE"
    assert "SCHEDULE.PAYABLES_SECURED_AMOUNT" in {
        issue["rule_id"] for issue in result["issues"]
    }


def test_schedule_taxonomy_audit_reports_missing_configured_families() -> None:
    catalogue = _catalogue()
    ordinary_relationships = list(catalogue["relationships"]["presentation"])
    catalogue["relationships"]["presentation"].extend(
        [
            {**relationship, "form": form}
            for form in ("ABBREVIATED", "MICRO")
            for relationship in ordinary_relationships
        ]
    )
    result = audit.audit_schedule_taxonomy(
        catalogue,
        {
            **_rule_pack(),
            "forms": {
                form: _rule_pack()["forms"]["ORDINARY"]
                for form in ("ORDINARY", "ABBREVIATED", "MICRO")
            },
        },
    )

    assert result["status"] == "FAIL"
    assert any("schedule types differ" in issue for issue in result["issues"])
