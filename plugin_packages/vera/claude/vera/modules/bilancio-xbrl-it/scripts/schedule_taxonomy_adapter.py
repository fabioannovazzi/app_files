#!/usr/bin/env python3
"""Compile reviewed schedules into official PCI note-table facts.

The presentation graph and arithmetic are mechanically verifiable.  Selecting
which client schedule row belongs to which statutory concept remains an
explicit professional decision.  This module validates that decision and
derives the XBRL values; it never classifies rows from their labels.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from schedule_engine import schedule_adapter_records

__all__ = [
    "build_schedule_table_inventory",
    "compile_schedule_taxonomy_adapter",
]

SUPPORTED_STRATEGIES = {"TABLE_FACTS", "TEXT_ONLY"}
REVIEWED_OMISSION_STATUSES = {
    "NOT_APPLICABLE_CONFIRMED",
    "REPRESENTED_ELSEWHERE_CONFIRMED",
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid adapter decimal in {field}") from exc


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _descendants(relationships: Sequence[Mapping[str, Any]], root: str) -> set[str]:
    children: dict[str, set[str]] = defaultdict(set)
    for relationship in relationships:
        children[str(relationship["from"])].add(str(relationship["to"]))
    result = {root}
    pending = [root]
    while pending:
        parent = pending.pop()
        for child in children.get(parent, set()):
            if child not in result:
                result.add(child)
                pending.append(child)
    return result


def build_schedule_table_inventory(
    catalogue: Mapping[str, Any],
    rule_pack: Mapping[str, Any],
    selected_form: str,
) -> dict[str, Any]:
    """Return the checksum-bound note-table concepts allowed for one form."""

    form = selected_form.upper()
    if str(catalogue.get("taxonomy_id")) != str(rule_pack.get("taxonomy_id")):
        raise ValueError("Schedule adapter and catalogue taxonomy differ")
    form_policies = rule_pack.get("forms")
    if not isinstance(form_policies, Mapping) or form not in form_policies:
        raise ValueError(f"Schedule adapter does not support form {form}")
    raw_policies = form_policies[form]
    if not isinstance(raw_policies, Mapping):
        raise ValueError("Schedule adapter form policy must be an object")

    concepts = {str(item["qname"]): item for item in catalogue.get("concepts", [])}
    presentation = list((catalogue.get("relationships") or {}).get("presentation", []))
    form_relationships = [
        item for item in presentation if str(item.get("form", "")).upper() == form
    ]
    inventories: dict[str, Any] = {}
    for raw_schedule_type, raw_policy in sorted(raw_policies.items()):
        schedule_type = str(raw_schedule_type).upper()
        if not isinstance(raw_policy, Mapping):
            raise ValueError(f"Schedule policy {schedule_type} must be an object")
        strategy = str(raw_policy.get("strategy", "")).upper()
        if strategy not in SUPPORTED_STRATEGIES:
            raise ValueError(f"Unsupported schedule adapter strategy: {strategy}")
        roots = sorted({str(item) for item in raw_policy.get("table_roots", [])})
        if strategy == "TABLE_FACTS" and not roots:
            raise ValueError(f"Schedule {schedule_type} requires table roots")
        if strategy == "TEXT_ONLY" and roots:
            raise ValueError(f"Text-only schedule {schedule_type} cannot have roots")
        allowed: set[str] = set()
        tables = []
        for root in roots:
            concept = concepts.get(root)
            if concept is None or concept.get("abstract") is not True:
                raise ValueError(
                    f"Schedule table root is unknown or non-abstract: {root}"
                )
            nodes = _descendants(form_relationships, root)
            if len(nodes) == 1:
                raise ValueError(
                    f"Official presentation graph has no {form} table below {root}"
                )
            fact_concepts = sorted(
                qname
                for qname in nodes
                if qname in concepts and concepts[qname].get("abstract") is not True
            )
            if not fact_concepts:
                raise ValueError(f"Schedule table has no reportable facts: {root}")
            allowed.update(fact_concepts)
            tables.append(
                {
                    "root": root,
                    "label_it": str(concept.get("label_it") or root),
                    "fact_concepts": fact_concepts,
                }
            )
        inventories[schedule_type] = {
            "strategy": strategy,
            "tables": tables,
            "allowed_concepts": [
                {
                    "xbrl_concept": qname,
                    "label_it": str(concepts[qname].get("label_it") or qname),
                    "period_type": str(concepts[qname].get("period_type")),
                    "type": str(concepts[qname].get("type")),
                }
                for qname in sorted(allowed)
            ],
        }
    inventory = {
        "schema_version": 1,
        "rule_pack_id": str(rule_pack["id"]),
        "taxonomy_id": str(catalogue["taxonomy_id"]),
        "taxonomy_package_sha256": str(catalogue["taxonomy_package_sha256"]),
        "selected_form": form,
        "schedules": inventories,
    }
    inventory["inventory_sha256"] = _sha256(inventory)
    return inventory


def _existing_facts(case: Mapping[str, Any]) -> dict[tuple[str, str], Decimal]:
    existing: dict[tuple[str, str], Decimal] = {}

    def add(qname: str, period: str, value: Any) -> None:
        key = (qname, period)
        normalized = _decimal(value, qname)
        if key in existing and existing[key] != normalized:
            raise ValueError(f"Existing XBRL facts conflict for {qname} {period}")
        existing[key] = normalized

    presentation = case.get("statutory_presentation") or {}
    presentation_concepts = {
        str(item["xbrl_concept"]): item
        for item in [
            *(presentation.get("inventory") or {}).get("requirements", []),
            *(presentation.get("inventory") or {}).get("totals", []),
        ]
    }
    for fact in presentation.get("output_facts", []):
        qname = str(fact["xbrl_concept"])
        concept = presentation_concepts.get(qname)
        if concept is None and fact.get("period_type") is None:
            raise ValueError(f"Presentation inventory is missing output fact {qname}")
        period_type = str(
            fact.get("period_type")
            if fact.get("period_type") is not None
            else concept["period_type"]
        )
        for period, value in (
            (f"current_{period_type}", fact.get("current_value")),
            (f"prior_{period_type}", fact.get("prior_value")),
        ):
            if value is not None:
                add(qname, period, value)
    for fact in case.get("taxonomy_facts", []):
        if fact.get("fact_type") == "MONETARY" and not fact.get("dimensions"):
            add(str(fact["xbrl_concept"]), str(fact["period"]), fact["value"])
    return existing


def compile_schedule_taxonomy_adapter(
    case: Mapping[str, Any],
    catalogue: Mapping[str, Any],
    rule_pack: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
    actor: str,
) -> dict[str, Any]:
    """Validate professional bindings and derive render-ready schedule facts."""

    if not actor.strip():
        raise ValueError("A schedule taxonomy reviewer identity is required")
    if isinstance(decisions, (str, bytes)) or not isinstance(decisions, Sequence):
        raise ValueError("Schedule taxonomy decisions must be a list")
    selected_form = str(case.get("selected_form") or "")
    if not selected_form or not case.get("statements"):
        raise ValueError("Selected form and statements are required")
    if (case.get("statutory_presentation") or {}).get("status") != "COMPLETE":
        raise ValueError("Complete statutory presentation is required")
    inventory = build_schedule_table_inventory(catalogue, rule_pack, selected_form)
    schedules = [
        item
        for item in case.get("schedules", [])
        if str(item.get("schedule_type", "")).upper() != "CASH_FLOW"
    ]
    if any(item.get("status") != "COMPLETE" for item in schedules):
        raise ValueError("Only complete schedules can enter the taxonomy adapter")
    schedule_lookup = {str(item["schedule_type"]).upper(): item for item in schedules}
    if len(schedule_lookup) != len(schedules):
        raise ValueError("Only one schedule per type can enter the taxonomy adapter")
    decision_lookup: dict[str, Mapping[str, Any]] = {}
    for decision in decisions:
        schedule_type = str(decision.get("schedule_type", "")).upper()
        if schedule_type in decision_lookup:
            raise ValueError(f"Duplicate schedule taxonomy decision: {schedule_type}")
        decision_lookup[schedule_type] = decision
    if set(decision_lookup) != set(schedule_lookup):
        raise ValueError("Every non-cash schedule requires one taxonomy decision")

    existing = _existing_facts(case)
    generated: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    generated_keys: set[tuple[str, str]] = set()
    for schedule_type, schedule in sorted(schedule_lookup.items()):
        policy = inventory["schedules"].get(schedule_type)
        if policy is None:
            raise ValueError(f"No active taxonomy policy for schedule {schedule_type}")
        decision = decision_lookup[schedule_type]
        records = {
            str(item["fact_id"]): item for item in schedule_adapter_records(schedule)
        }
        strategy = str(policy["strategy"])
        if str(decision.get("strategy", "")).upper() != strategy:
            raise ValueError(
                f"Schedule {schedule_type} uses the wrong adapter strategy"
            )
        omissions: dict[str, dict[str, str]] = {}
        for raw_omission in decision.get("omissions", []):
            fact_id = str(raw_omission.get("schedule_fact_id", ""))
            status = str(raw_omission.get("status", "")).upper()
            reason = str(raw_omission.get("reason", "")).strip()
            if fact_id not in records or fact_id in omissions:
                raise ValueError(f"Invalid or duplicate schedule omission: {fact_id}")
            if status not in REVIEWED_OMISSION_STATUSES or len(reason) < 12:
                raise ValueError(
                    "Schedule omissions require a reviewed status and reason"
                )
            omissions[fact_id] = {"status": status, "reason": reason}

        outputs = list(decision.get("outputs", []))
        if strategy == "TEXT_ONLY" and outputs:
            raise ValueError("Text-only schedule policy cannot emit table facts")
        if strategy == "TABLE_FACTS" and not outputs:
            raise ValueError("Table schedule policy requires at least one mapped fact")
        allowed = {
            str(item["xbrl_concept"]): item for item in policy["allowed_concepts"]
        }
        used: set[str] = set()
        reconciled: list[dict[str, Any]] = []
        schedule_generated: list[str] = []
        for output_index, output in enumerate(outputs, start=1):
            qname = str(output.get("xbrl_concept", ""))
            concept = allowed.get(qname)
            if concept is None:
                raise ValueError(
                    f"Concept is outside the active schedule tables: {qname}"
                )
            period = str(output.get("period", ""))
            if period not in {"current_instant", "current_duration"}:
                raise ValueError("Schedule table outputs must use a current period")
            if not period.endswith(f"_{concept['period_type']}"):
                raise ValueError(f"Schedule output period does not match {qname}")
            inputs = list(output.get("inputs", []))
            if not inputs:
                raise ValueError("Schedule table outputs require source schedule facts")
            source_refs: set[str] = set()
            input_ids: list[str] = []
            monetary = "monetaryItemType" in str(concept["type"])
            if monetary:
                value = Decimal("0")
                for raw_input in inputs:
                    fact_id = str(raw_input.get("schedule_fact_id", ""))
                    record = records.get(fact_id)
                    if record is None or record["fact_type"] != "MONETARY":
                        raise ValueError(f"Invalid monetary schedule input: {fact_id}")
                    multiplier = _decimal(
                        raw_input.get("multiplier", "1"), "multiplier"
                    )
                    value += _decimal(record["value"], fact_id) * multiplier
                    used.add(fact_id)
                    input_ids.append(fact_id)
                    source_refs.update(str(item) for item in record["source_refs"])
                fact_type = "MONETARY"
                output_value = _decimal_text(value)
            else:
                if len(inputs) != 1:
                    raise ValueError(
                        "Text schedule outputs require exactly one source cell"
                    )
                fact_id = str(inputs[0].get("schedule_fact_id", ""))
                record = records.get(fact_id)
                if record is None or record["fact_type"] != "TEXT":
                    raise ValueError(f"Invalid text schedule input: {fact_id}")
                used.add(fact_id)
                input_ids.append(fact_id)
                source_refs.update(str(item) for item in record["source_refs"])
                fact_type = "TEXT"
                output_value = str(record["value"])
            key = (qname, period)
            if key in generated_keys:
                raise ValueError(f"Duplicate generated schedule fact: {qname} {period}")
            generated_keys.add(key)
            derivation = {
                "kind": "SCHEDULE_TAXONOMY_ADAPTER",
                "schedule_id": str(schedule["schedule_id"]),
                "schedule_type": schedule_type,
                "input_fact_ids": sorted(input_ids),
                "expression": [
                    {
                        "schedule_fact_id": str(item["schedule_fact_id"]),
                        "multiplier": str(item.get("multiplier", "1")),
                    }
                    for item in inputs
                ],
            }
            if key in existing:
                if fact_type != "MONETARY" or existing[key] != _decimal(
                    output_value, qname
                ):
                    raise ValueError(
                        f"Schedule output does not reconcile to existing fact {qname}"
                    )
                reconciled.append(
                    {
                        "xbrl_concept": qname,
                        "period": period,
                        "value": output_value,
                        "derivation": derivation,
                    }
                )
                continue
            fact_id = f"schedule_taxonomy_{schedule_type.lower()}_{output_index:04d}"
            generated_fact = {
                "fact_id": fact_id,
                "xbrl_concept": qname,
                "period": period,
                "fact_type": fact_type,
                "value": output_value,
                "currency": "EUR" if fact_type == "MONETARY" else None,
                "language": (
                    str(case.get("output_language", "it"))
                    if fact_type == "TEXT"
                    else None
                ),
                "status": "DERIVED",
                "source_refs": sorted(source_refs),
                "derivation": derivation,
                "dimensions": {},
                "nil_reason": None,
                "confirmed_by": actor,
            }
            generated.append(generated_fact)
            schedule_generated.append(fact_id)
        overlap = used & omissions.keys()
        if overlap:
            raise ValueError(
                f"Schedule cells cannot be mapped and omitted: {sorted(overlap)}"
            )
        uncovered = sorted(set(records) - used - omissions.keys())
        if uncovered:
            raise ValueError(
                f"Schedule taxonomy coverage is incomplete for {schedule_type}: {uncovered[:5]}"
            )
        coverage.append(
            {
                "schedule_id": str(schedule["schedule_id"]),
                "schedule_type": schedule_type,
                "strategy": strategy,
                "input_fact_count": len(records),
                "mapped_input_count": len(used),
                "omitted_input_count": len(omissions),
                "generated_fact_ids": schedule_generated,
                "reconciled_existing_facts": reconciled,
                "omissions": [
                    {"schedule_fact_id": fact_id, **omissions[fact_id]}
                    for fact_id in sorted(omissions)
                ],
                "status": "COMPLETE",
            }
        )
    result = {
        "schema_version": 1,
        "rule_pack_id": str(rule_pack["id"]),
        "rule_pack_sha256": _sha256(rule_pack),
        "inventory": inventory,
        "coverage": coverage,
        "generated_facts": generated,
        "reviewed_by": actor,
        "status": "COMPLETE",
    }
    result["adapter_sha256"] = _sha256(result)
    return result
