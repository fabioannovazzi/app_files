#!/usr/bin/env python3
"""Form-aware statutory presentation coverage and taxonomy rollups.

The engine derives its concept inventory and arithmetic from a checksum-bound
taxonomy catalogue. It never interprets an absent concept as zero: every absent
leaf requires a professional period-by-period ZERO_CONFIRMED or
NOT_APPLICABLE_CONFIRMED decision before totals may be derived.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Sequence

__all__ = [
    "build_primary_presentation_inventory",
    "build_statutory_presentation_coverage",
]

DECISION_STATUSES = {"ZERO_CONFIRMED", "NOT_APPLICABLE_CONFIRMED"}
PERIODS = ("current", "prior")
STATEMENT_SECTION_KEYS = {
    "expected_role_kind",
    "root_concept",
    "canonical_multiplier",
}
SUPPORTED_SCHEDULE_TRIGGERS = {
    "EQUITY",
    "FIXED_ASSETS",
    "PAYABLES",
    "PROVISIONS",
    "RECEIVABLES",
    "TAXES",
    "TFR",
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _is_monetary(concept: Mapping[str, Any]) -> bool:
    return (
        concept.get("abstract") is not True
        and concept.get("is_item") is True
        and concept.get("is_tuple") is False
        and concept.get("period_type") in {"instant", "duration"}
        and "monetaryItemType" in str(concept.get("type", ""))
    )


def build_primary_presentation_inventory(
    catalogue: Mapping[str, Any],
    rule_pack: Mapping[str, Any],
    selected_form: str,
) -> dict[str, Any]:
    """Build the exact primary-statement inventory for one statutory form."""

    form = selected_form.upper()
    if catalogue.get("schema_version") != 2:
        raise ValueError("Statutory presentation requires taxonomy catalogue schema 2")
    if str(catalogue.get("taxonomy_id")) != str(rule_pack.get("taxonomy_id")):
        raise ValueError("Presentation rule pack and catalogue taxonomy differ")
    forms = rule_pack.get("forms")
    if not isinstance(forms, Mapping) or form not in forms:
        raise ValueError(f"Presentation rule pack does not support form {form}")
    form_policy = forms[form]
    if not isinstance(form_policy, Mapping):
        raise ValueError("Presentation form policy must be an object")
    role_policies = form_policy.get("roles")
    if not isinstance(role_policies, list) or not role_policies:
        raise ValueError("Presentation form policy requires role definitions")
    concepts = {str(item["qname"]): item for item in catalogue.get("concepts", [])}
    presentation_rows = list(
        (catalogue.get("relationships") or {}).get("presentation", [])
    )
    calculation_rows = list(
        (catalogue.get("relationships") or {}).get("calculation", [])
    )
    requirements: dict[str, dict[str, Any]] = {}
    totals: dict[str, dict[str, Any]] = {}
    formulas: list[dict[str, Any]] = []
    roles: list[dict[str, Any]] = []
    for raw_policy in role_policies:
        if not isinstance(raw_policy, Mapping):
            raise ValueError("Presentation role policy must be an object")
        role = str(raw_policy["role"])
        role_kind = str(raw_policy["kind"])
        role_presentation = [
            row
            for row in presentation_rows
            if str(row.get("form")) == form and str(row.get("role")) == role
        ]
        if not role_presentation:
            raise ValueError(f"Official catalogue has no presentation role {role}")
        role_calculation = [
            row
            for row in calculation_rows
            if str(row.get("form")) == form and str(row.get("role")) == role
        ]
        node_qnames = {
            str(row[key])
            for row in [*role_presentation, *role_calculation]
            for key in ("from", "to")
        }
        missing_concepts = sorted(node_qnames - concepts.keys())
        if missing_concepts:
            raise ValueError(
                f"Presentation role references unknown concepts: {missing_concepts[:5]}"
            )
        monetary = {qname for qname in node_qnames if _is_monetary(concepts[qname])}
        parent_qnames = {
            str(row["from"]) for row in role_calculation if str(row["from"]) in monetary
        }
        leaf_qnames = monetary - parent_qnames
        roots = sorted(
            {str(row["from"]) for row in role_presentation}
            - {str(row["to"]) for row in role_presentation}
        )
        expected = raw_policy.get("expected") or {}
        observed_counts = {
            "presentation_relationships": len(role_presentation),
            "calculation_relationships": len(role_calculation),
            "monetary_concepts": len(monetary),
            "leaf_concepts": len(leaf_qnames),
            "total_concepts": len(parent_qnames),
        }
        for key, expected_value in expected.items():
            if (
                key not in observed_counts
                or int(expected_value) != observed_counts[key]
            ):
                raise ValueError(
                    f"Official presentation inventory count changed for {role_kind}: "
                    f"{key} expected {expected_value}, observed {observed_counts.get(key)}"
                )
        roles.append(
            {
                "kind": role_kind,
                "role": role,
                "roots": roots,
                **observed_counts,
            }
        )
        for qname in sorted(leaf_qnames):
            item = requirements.setdefault(
                qname,
                {
                    "xbrl_concept": qname,
                    "label_it": str(concepts[qname].get("label_it") or qname),
                    "period_type": str(concepts[qname].get("period_type")),
                    "balance": concepts[qname].get("balance"),
                    "roles": [],
                    "role_kinds": [],
                },
            )
            item["roles"].append(role)
            item["role_kinds"].append(role_kind)
        for qname in sorted(parent_qnames):
            item = totals.setdefault(
                qname,
                {
                    "xbrl_concept": qname,
                    "label_it": str(concepts[qname].get("label_it") or qname),
                    "period_type": str(concepts[qname].get("period_type")),
                    "balance": concepts[qname].get("balance"),
                    "roles": [],
                    "role_kinds": [],
                },
            )
            item["roles"].append(role)
            item["role_kinds"].append(role_kind)
        formula_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in role_calculation:
            parent = str(row["from"])
            child = str(row["to"])
            if parent not in monetary or child not in monetary:
                continue
            formula_groups[parent].append(
                {"child": child, "weight": str(row.get("weight") or "1")}
            )
        for parent, children in sorted(formula_groups.items()):
            formulas.append(
                {
                    "role": role,
                    "role_kind": role_kind,
                    "parent": parent,
                    "children": sorted(
                        children, key=lambda item: (item["child"], item["weight"])
                    ),
                }
            )
    for collection in (requirements, totals):
        for item in collection.values():
            item["roles"] = sorted(set(item["roles"]))
            item["role_kinds"] = sorted(set(item["role_kinds"]))
    # A QName can be a calculation parent in one official role and a leaf in
    # another. It represents one XBRL fact, so the calculated value must satisfy
    # every role; asking the reviewer to confirm a second zero/non-applicable
    # value would create a contradictory duplicate fact.
    for qname in set(requirements) & set(totals):
        requirements.pop(qname)
    concept_inventory = {**requirements, **totals}
    raw_statement_sections = rule_pack.get("statement_sections")
    if not isinstance(raw_statement_sections, Mapping) or not raw_statement_sections:
        raise ValueError("Presentation rule pack requires statement section contracts")
    statement_sections: dict[str, dict[str, str]] = {}
    for raw_section, raw_contract in raw_statement_sections.items():
        section = str(raw_section).upper()
        if not isinstance(raw_contract, Mapping) or set(raw_contract) != (
            STATEMENT_SECTION_KEYS
        ):
            raise ValueError(
                f"Statement section contract {section} must contain exactly "
                f"{sorted(STATEMENT_SECTION_KEYS)}"
            )
        expected_role_kind = str(raw_contract["expected_role_kind"]).upper()
        root_concept = str(raw_contract["root_concept"])
        multiplier = str(raw_contract["canonical_multiplier"])
        if multiplier not in {"1", "-1"}:
            raise ValueError(
                f"Statement section contract {section} has an invalid multiplier"
            )
        root = concept_inventory.get(root_concept)
        if root is None or root_concept not in totals:
            raise ValueError(
                f"Statement section contract {section} references a non-total concept"
            )
        if expected_role_kind not in root["role_kinds"]:
            raise ValueError(
                f"Statement section contract {section} references the wrong role kind"
            )
        statement_sections[section] = {
            "expected_role_kind": expected_role_kind,
            "root_concept": root_concept,
            "canonical_multiplier": multiplier,
        }
    raw_schedule_roots = rule_pack.get("schedule_trigger_roots")
    if not isinstance(raw_schedule_roots, Mapping) or not raw_schedule_roots:
        raise ValueError("Presentation rule pack requires schedule trigger roots")
    calculation_children: dict[str, set[str]] = defaultdict(set)
    for formula in formulas:
        calculation_children[str(formula["parent"])].update(
            str(child["child"]) for child in formula["children"]
        )
    schedule_trigger_concepts: dict[str, list[str]] = {}
    for raw_schedule_type, raw_roots in raw_schedule_roots.items():
        schedule_type = str(raw_schedule_type).upper()
        if schedule_type not in SUPPORTED_SCHEDULE_TRIGGERS:
            raise ValueError(
                f"Unsupported presentation schedule trigger: {schedule_type}"
            )
        if not isinstance(raw_roots, list) or not raw_roots:
            raise ValueError(f"Schedule trigger {schedule_type} requires root concepts")
        roots = {str(item) for item in raw_roots if str(item) in concept_inventory}
        descendants = set(roots)
        pending = list(roots)
        while pending:
            parent = pending.pop()
            for child in calculation_children.get(parent, set()):
                if child not in descendants:
                    descendants.add(child)
                    pending.append(child)
        schedule_trigger_concepts[schedule_type] = sorted(descendants)
    cash_flow_contract = None
    raw_cash_flow_contract = rule_pack.get("cash_flow_contract")
    if raw_cash_flow_contract is not None:
        if not isinstance(raw_cash_flow_contract, Mapping) or set(
            raw_cash_flow_contract
        ) != {"form", "net_change_root_concept"}:
            raise ValueError("Cash-flow contract has an invalid shape")
        contract_form = str(raw_cash_flow_contract["form"]).upper()
        root_concept = str(raw_cash_flow_contract["net_change_root_concept"])
        if contract_form not in forms:
            raise ValueError("Cash-flow contract references an unsupported form")
        if form == contract_form:
            root = concept_inventory.get(root_concept)
            if (
                root_concept not in totals
                or root is None
                or not any(
                    role_kind.startswith("CASH_FLOW")
                    for role_kind in root["role_kinds"]
                )
            ):
                raise ValueError(
                    "Cash-flow contract must reference a calculated cash-flow root"
                )
            cash_flow_contract = {
                "form": contract_form,
                "net_change_root_concept": root_concept,
            }
    inventory = {
        "schema_version": 1,
        "rule_pack_id": str(rule_pack["id"]),
        "taxonomy_id": str(catalogue["taxonomy_id"]),
        "taxonomy_package_sha256": str(catalogue["taxonomy_package_sha256"]),
        "selected_form": form,
        "roles": roles,
        "statement_sections": statement_sections,
        "schedule_trigger_concepts": schedule_trigger_concepts,
        "cash_flow_contract": cash_flow_contract,
        "requirements": sorted(
            requirements.values(), key=lambda item: item["xbrl_concept"]
        ),
        "totals": sorted(totals.values(), key=lambda item: item["xbrl_concept"]),
        "formulas": formulas,
    }
    inventory["inventory_sha256"] = hashlib.sha256(
        _canonical_json(inventory)
    ).hexdigest()
    return inventory


def _fact_values(case: Mapping[str, Any]) -> dict[str, dict[str, Decimal]]:
    values: dict[str, dict[str, Decimal]] = defaultdict(dict)

    def add(qname: str, period: str, value: Decimal) -> None:
        if period in values[qname]:
            raise ValueError(f"Duplicate primary-statement fact: {qname} {period}")
        values[qname][period] = value

    for fact in case.get("canonical_facts", []):
        qname = fact.get("xbrl_concept")
        if not qname:
            continue
        multiplier = Decimal(str(fact.get("xbrl_sign_multiplier", "")))
        add(str(qname), "current", Decimal(str(fact["current_value"])) * multiplier)
        add(str(qname), "prior", Decimal(str(fact["prior_value"])) * multiplier)
    for fact in case.get("taxonomy_facts", []):
        if fact.get("fact_type") != "MONETARY" or fact.get("dimensions"):
            continue
        period_key = str(fact.get("period", ""))
        if period_key.startswith("current_"):
            period = "current"
        elif period_key.startswith("prior_"):
            period = "prior"
        else:
            continue
        add(str(fact["xbrl_concept"]), period, Decimal(str(fact["value"])))
    return values


def build_statutory_presentation_coverage(
    case: Mapping[str, Any],
    catalogue: Mapping[str, Any],
    rule_pack: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
    actor: str,
) -> dict[str, Any]:
    """Resolve leaves, derive totals, and report exact primary coverage."""

    if not actor.strip():
        raise ValueError("A presentation reviewer identity is required")
    if isinstance(decisions, (str, bytes)) or not isinstance(decisions, Sequence):
        raise ValueError("Presentation decisions must be a list")
    form = str(case.get("selected_form") or "")
    if not form or not case.get("statements"):
        raise ValueError("Selected form and computed statements are required")
    period = case.get("period")
    if not isinstance(period, Mapping):
        raise ValueError("A reporting period is required for presentation policy")
    period_start = date.fromisoformat(str(period["start"]))
    effective_from = date.fromisoformat(str(rule_pack["effective_from"]))
    effective_to = date.fromisoformat(str(rule_pack["effective_to"]))
    if not effective_from <= period_start <= effective_to:
        raise ValueError(
            "Statutory presentation rule pack is not effective for the case period"
        )
    inventory = build_primary_presentation_inventory(catalogue, rule_pack, form)
    requirement_lookup = {
        item["xbrl_concept"]: item for item in inventory["requirements"]
    }
    total_lookup = {item["xbrl_concept"]: item for item in inventory["totals"]}
    relevant = set(requirement_lookup) | set(total_lookup)
    base_values = _fact_values(case)
    semantic_issues: list[dict[str, Any]] = []
    concept_roles: dict[str, set[str]] = defaultdict(set)
    for item in [*inventory["requirements"], *inventory["totals"]]:
        concept_roles[str(item["xbrl_concept"])].update(item["role_kinds"])
    for fact in case.get("canonical_facts", []):
        fact_id = str(fact.get("fact_id", ""))
        qname = str(fact.get("xbrl_concept") or "")
        section = str(fact.get("statement_section") or "").upper()
        if not qname:
            semantic_issues.append(
                {
                    "code": "CANONICAL_FACT_XBRL_CONCEPT_REQUIRED",
                    "fact_id": fact_id,
                    "statement_section": section,
                }
            )
            continue
        if qname not in relevant:
            semantic_issues.append(
                {
                    "code": "SUBSTANTIVE_TAXONOMY_MISMATCH",
                    "fact_id": fact_id,
                    "statement_section": section,
                    "xbrl_concept": qname,
                }
            )
            continue
        section_contract = inventory["statement_sections"].get(section)
        if section_contract and section_contract["expected_role_kind"] not in (
            concept_roles[qname]
        ):
            semantic_issues.append(
                {
                    "code": "STATEMENT_ROLE_MISMATCH",
                    "fact_id": fact_id,
                    "statement_section": section,
                    "xbrl_concept": qname,
                    "expected_role_kind": section_contract["expected_role_kind"],
                    "observed_role_kinds": sorted(concept_roles[qname]),
                }
            )
    values: dict[str, dict[str, Decimal | None]] = {
        qname: dict(periods)
        for qname, periods in base_values.items()
        if qname in relevant
    }
    derived_schedule_triggers: list[dict[str, Any]] = []
    for schedule_type, concepts in inventory["schedule_trigger_concepts"].items():
        concept_set = set(concepts)
        triggering_facts = [
            fact
            for fact in case.get("canonical_facts", [])
            if fact.get("xbrl_concept") in concept_set
            and any(
                Decimal(str(fact[value_key])) != 0
                for value_key in ("current_value", "prior_value")
            )
        ]
        if triggering_facts:
            derived_schedule_triggers.append(
                {
                    "schedule_type": schedule_type,
                    "basis": "OFFICIAL_TAXONOMY_CALCULATION_DESCENDANT",
                    "fact_refs": sorted(
                        str(fact["fact_id"]) for fact in triggering_facts
                    ),
                    "xbrl_concepts": sorted(
                        {str(fact["xbrl_concept"]) for fact in triggering_facts}
                    ),
                }
            )
    decision_lookup: dict[str, Mapping[str, Any]] = {}
    for raw in decisions:
        if not isinstance(raw, Mapping):
            raise ValueError("Each presentation decision must be an object")
        allowed_keys = {
            "xbrl_concept",
            "current_status",
            "prior_status",
            "reason",
            "source_refs",
        }
        if set(raw) - allowed_keys:
            raise ValueError("Presentation decision contains unsupported fields")
        qname = str(raw["xbrl_concept"])
        if qname in decision_lookup or qname not in requirement_lookup:
            raise ValueError(f"Unknown or duplicate presentation decision: {qname}")
        decision_lookup[qname] = raw
    normalized_decisions: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    output_by_qname: dict[str, dict[str, Any]] = {}
    for qname, requirement in sorted(requirement_lookup.items()):
        raw = decision_lookup.get(qname)
        statuses: dict[str, str] = {}
        reason = str((raw or {}).get("reason", "")).strip()
        raw_source_refs = (raw or {}).get("source_refs", [])
        if not isinstance(raw_source_refs, list) or not all(
            isinstance(item, str) and item.strip() for item in raw_source_refs
        ):
            raise ValueError("Presentation source_refs must be non-empty strings")
        source_refs = sorted(set(raw_source_refs))
        needed_decision = False
        for period in PERIODS:
            if period in values.get(qname, {}):
                if str((raw or {}).get(f"{period}_status", "")).strip():
                    raise ValueError(
                        f"Presentation decision is unnecessary for existing {period} "
                        f"fact: {qname}"
                    )
                statuses[period] = "FACT_PRESENT"
                continue
            needed_decision = True
            status = str((raw or {}).get(f"{period}_status", "")).upper()
            if status not in DECISION_STATUSES:
                missing.append({"xbrl_concept": qname, "period": period})
                statuses[period] = "MISSING"
                continue
            if not reason:
                raise ValueError(
                    f"Presentation decision for {qname} requires a professional reason"
                )
            statuses[period] = status
            values.setdefault(qname, {})[period] = (
                Decimal("0") if status == "ZERO_CONFIRMED" else None
            )
            if status == "ZERO_CONFIRMED":
                item = output_by_qname.setdefault(
                    qname,
                    {
                        "fact_id": f"presentation_zero_{len(output_by_qname) + 1:06d}",
                        "xbrl_concept": qname,
                        "current_value": None,
                        "prior_value": None,
                        "status": "USER_CONFIRMED",
                        "source_refs": source_refs,
                        "derivation": None,
                        "confirmed_by": actor,
                        "reason": reason,
                    },
                )
                item[f"{period}_value"] = "0"
        if raw is not None and not needed_decision:
            raise ValueError(
                f"Presentation decision is unnecessary because both facts exist: {qname}"
            )
        if needed_decision:
            normalized_decisions.append(
                {
                    "xbrl_concept": qname,
                    "label_it": requirement["label_it"],
                    "current_status": statuses["current"],
                    "prior_status": statuses["prior"],
                    "reason": reason,
                    "source_refs": source_refs,
                    "confirmed_by": actor,
                }
            )
    issues: list[dict[str, Any]] = list(semantic_issues)
    derived_periods: dict[str, set[str]] = defaultdict(set)
    verified_totals: list[dict[str, Any]] = []
    unresolved = list(inventory["formulas"])
    while unresolved:
        next_unresolved: list[dict[str, Any]] = []
        progress = False
        for formula in unresolved:
            parent = str(formula["parent"])
            resolved_formula = True
            for period in PERIODS:
                children = formula["children"]
                if not all(
                    period in values.get(str(child["child"]), {}) for child in children
                ):
                    resolved_formula = False
                    break
                calculated = sum(
                    (values[str(child["child"])][period] or Decimal("0"))
                    * Decimal(str(child["weight"]))
                    for child in children
                )
                existing = values.get(parent, {}).get(period, "MISSING")
                if existing == "MISSING":
                    values.setdefault(parent, {})[period] = calculated
                    derived_periods[parent].add(period)
                    progress = True
                elif existing is None or existing != calculated:
                    issues.append(
                        {
                            "code": "TOTAL_MISMATCH",
                            "role": formula["role"],
                            "xbrl_concept": parent,
                            "period": period,
                            "expected": _decimal_text(calculated),
                            "observed": (
                                None if existing is None else _decimal_text(existing)
                            ),
                        }
                    )
                else:
                    verified_totals.append(
                        {
                            "role": formula["role"],
                            "xbrl_concept": parent,
                            "period": period,
                            "value": _decimal_text(calculated),
                        }
                    )
            if not resolved_formula:
                next_unresolved.append(formula)
        if not next_unresolved:
            break
        if not progress:
            # Missing leaf confirmations already identify the professional action.
            # An unresolved total is a separate structural issue only when no leaf
            # decision is outstanding.
            if missing:
                break
            for formula in next_unresolved:
                issues.append(
                    {
                        "code": "TOTAL_UNRESOLVED",
                        "role": formula["role"],
                        "xbrl_concept": formula["parent"],
                    }
                )
            break
        unresolved = next_unresolved
    for qname, periods in sorted(derived_periods.items()):
        item = output_by_qname.setdefault(
            qname,
            {
                "fact_id": f"presentation_rollup_{len(output_by_qname) + 1:06d}",
                "xbrl_concept": qname,
                "current_value": None,
                "prior_value": None,
                "status": "DERIVED",
                "source_refs": [],
                "derivation": {
                    "operation": "OFFICIAL_TAXONOMY_CALCULATION_ROLLUP",
                    "inventory_sha256": inventory["inventory_sha256"],
                },
                "confirmed_by": None,
                "reason": None,
            },
        )
        for period in periods:
            value = values[qname][period]
            if value is not None:
                item[f"{period}_value"] = _decimal_text(value)
    reconciliation_checks: list[dict[str, Any]] = []
    section_totals = (case.get("statements") or {}).get("section_totals") or {}
    for section, contract in inventory["statement_sections"].items():
        root_concept = contract["root_concept"]
        multiplier = Decimal(contract["canonical_multiplier"])
        for period in PERIODS:
            raw_canonical = (section_totals.get(section) or {}).get(period, "0")
            canonical_value = Decimal(str(raw_canonical)) * multiplier
            xbrl_value = values.get(root_concept, {}).get(period, "MISSING")
            check = {
                "statement_section": section,
                "period": period,
                "root_concept": root_concept,
                "canonical_value": _decimal_text(canonical_value),
                "xbrl_value": (
                    None
                    if xbrl_value in {"MISSING", None}
                    else _decimal_text(xbrl_value)
                ),
            }
            if xbrl_value == canonical_value:
                check["status"] = "PASS"
            elif not missing:
                check["status"] = "FAIL"
                issue = {
                    "code": "STATEMENT_XBRL_ROOT_MISMATCH",
                    **{key: value for key, value in check.items() if key != "status"},
                }
                issues.append(issue)
                semantic_issues.append(issue)
            else:
                check["status"] = "PENDING_COVERAGE"
            reconciliation_checks.append(check)
    status = "COMPLETE" if not missing and not issues else "INCOMPLETE"
    cash_flow_contract = inventory.get("cash_flow_contract")
    cash_flow_values = None
    if cash_flow_contract:
        root_concept = str(cash_flow_contract["net_change_root_concept"])
        root_values = values.get(root_concept, {})
        cash_flow_values = {
            "xbrl_concept": root_concept,
            "current_value": (
                None
                if root_values.get("current") is None
                else _decimal_text(root_values["current"])
            ),
            "prior_value": (
                None
                if root_values.get("prior") is None
                else _decimal_text(root_values["prior"])
            ),
        }
    return {
        "schema_version": 1,
        "status": status,
        "selected_form": form,
        "inventory": inventory,
        "decisions": normalized_decisions,
        "output_facts": sorted(
            output_by_qname.values(), key=lambda item: item["xbrl_concept"]
        ),
        "verified_totals": sorted(
            verified_totals,
            key=lambda item: (item["xbrl_concept"], item["period"], item["role"]),
        ),
        "semantic_reconciliation": {
            "status": "PASS" if not semantic_issues else "FAIL",
            "checks": reconciliation_checks,
            "issues": semantic_issues,
        },
        "derived_schedule_triggers": derived_schedule_triggers,
        "cash_flow_values": cash_flow_values,
        "missing": missing,
        "issues": issues,
        "summary": {
            "required_leaf_concepts": len(requirement_lookup),
            "explicit_decisions": len(normalized_decisions),
            "derived_output_facts": sum(
                item["status"] == "DERIVED" for item in output_by_qname.values()
            ),
            "confirmed_zero_output_facts": sum(
                item["status"] == "USER_CONFIRMED" for item in output_by_qname.values()
            ),
            "missing_period_decisions": len(missing),
            "issues": len(issues),
            "semantic_issues": len(semantic_issues),
        },
    }
