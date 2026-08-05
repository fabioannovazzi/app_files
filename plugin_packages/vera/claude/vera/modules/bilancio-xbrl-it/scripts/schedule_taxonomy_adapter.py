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


def _presentation_paths(
    relationships: Sequence[Mapping[str, Any]], root: str
) -> dict[str, list[tuple[str, ...]]]:
    """Return every acyclic presentation path below one root within one role."""

    children: dict[str, set[str]] = defaultdict(set)
    for relationship in relationships:
        children[str(relationship["from"])].add(str(relationship["to"]))
    result: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    pending = [(root, (root,))]
    while pending:
        parent, path = pending.pop()
        for child in children.get(parent, set()):
            if child in path:
                raise ValueError("Official presentation graph contains a cycle")
            child_path = (*path, child)
            if child_path not in result[child]:
                result[child].append(child_path)
                pending.append((child, child_path))
    return dict(result)


def _is_reportable_item(concept: Mapping[str, Any]) -> bool:
    """Return whether a catalogue concept may legally become an item fact."""

    return (
        concept.get("abstract") is not True
        and concept.get("is_item") is True
        and concept.get("is_tuple") is False
        and concept.get("period_type") in {"instant", "duration"}
    )


def build_schedule_table_inventory(
    catalogue: Mapping[str, Any],
    rule_pack: Mapping[str, Any],
    selected_form: str,
) -> dict[str, Any]:
    """Return the checksum-bound note-table concepts allowed for one form."""

    form = selected_form.upper()
    if catalogue.get("schema_version") != 2:
        raise ValueError("Schedule adapter requires taxonomy catalogue schema 2")
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
        allowed_bindings: dict[str, list[dict[str, Any]]] = defaultdict(list)
        tables = []
        for root in roots:
            concept = concepts.get(root)
            if concept is None or concept.get("abstract") is not True:
                raise ValueError(
                    f"Schedule table root is unknown or non-abstract: {root}"
                )
            roles = sorted(
                {
                    str(item["role"])
                    for item in form_relationships
                    if str(item["from"]) == root
                }
            )
            if not roles:
                raise ValueError(
                    f"Official presentation graph has no {form} table below {root}"
                )
            fact_concepts: set[str] = set()
            for role in roles:
                role_relationships = [
                    item for item in form_relationships if str(item.get("role")) == role
                ]
                paths = _presentation_paths(role_relationships, root)
                for qname, concept_paths in paths.items():
                    if qname not in concepts or not _is_reportable_item(
                        concepts[qname]
                    ):
                        continue
                    fact_concepts.add(qname)
                    for path in concept_paths:
                        binding = {
                            "table_root": root,
                            "role": role,
                            "tuple_path": [
                                node
                                for node in path[1:-1]
                                if concepts[node].get("is_tuple") is True
                            ],
                        }
                        if binding not in allowed_bindings[qname]:
                            allowed_bindings[qname].append(binding)
            if not fact_concepts:
                raise ValueError(f"Schedule table has no reportable facts: {root}")
            tables.append(
                {
                    "root": root,
                    "label_it": str(concept.get("label_it") or root),
                    "roles": roles,
                    "fact_concepts": sorted(fact_concepts),
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
                    "table_bindings": sorted(
                        allowed_bindings[qname], key=lambda item: _canonical_json(item)
                    ),
                }
                for qname in sorted(allowed_bindings)
            ],
        }
    inventory = {
        "schema_version": 2,
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
    generated_keys: set[tuple[str, str, str]] = set()
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
            bindings = list(concept.get("table_bindings", []))
            requested_root = output.get("table_root")
            requested_role = output.get("role")
            if requested_root is not None:
                bindings = [
                    item
                    for item in bindings
                    if str(item["table_root"]) == str(requested_root)
                ]
            if requested_role is not None:
                bindings = [
                    item
                    for item in bindings
                    if str(item["role"]) == str(requested_role)
                ]
            if len(bindings) != 1:
                raise ValueError(
                    f"Schedule concept requires one unambiguous table binding: {qname}"
                )
            table_binding = dict(bindings[0])
            tuple_path = [str(item) for item in table_binding["tuple_path"]]
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
            input_row_ids: set[str] = set()
            monetary = "monetaryItemType" in str(concept["type"])
            if monetary:
                value = Decimal("0")
                for raw_input in inputs:
                    fact_id = str(raw_input.get("schedule_fact_id", ""))
                    record = records.get(fact_id)
                    if record is None or record["fact_type"] != "MONETARY":
                        raise ValueError(f"Invalid monetary schedule input: {fact_id}")
                    if fact_id in input_ids:
                        raise ValueError(
                            f"Schedule output repeats source fact: {fact_id}"
                        )
                    multiplier = _decimal(
                        raw_input.get("multiplier", "1"), "multiplier"
                    )
                    if multiplier not in {Decimal("1"), Decimal("-1")}:
                        raise ValueError(
                            "Schedule monetary multipliers must be explicit sign conventions"
                        )
                    value += _decimal(record["value"], fact_id) * multiplier
                    used.add(fact_id)
                    input_ids.append(fact_id)
                    input_row_ids.add(str(record["row_id"]))
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
                if _decimal(inputs[0].get("multiplier", "1"), "multiplier") != 1:
                    raise ValueError("Text schedule inputs cannot be scaled")
                used.add(fact_id)
                input_ids.append(fact_id)
                input_row_ids.add(str(record["row_id"]))
                source_refs.update(str(item) for item in record["source_refs"])
                fact_type = "TEXT"
                output_value = str(record["value"])
            tuple_instance_id = None
            if tuple_path:
                if len(input_row_ids) != 1:
                    raise ValueError(
                        "Tuple table outputs must derive from exactly one schedule row"
                    )
                tuple_instance_id = (
                    f"{schedule['schedule_id']}:{next(iter(input_row_ids))}"
                )
            generated_key = (qname, period, tuple_instance_id or "")
            if generated_key in generated_keys:
                raise ValueError(f"Duplicate generated schedule fact: {qname} {period}")
            generated_keys.add(generated_key)
            derivation = {
                "kind": "SCHEDULE_TAXONOMY_ADAPTER",
                "schedule_id": str(schedule["schedule_id"]),
                "schedule_type": schedule_type,
                "input_fact_ids": sorted(input_ids),
                "table_binding": table_binding,
                "expression": [
                    {
                        "schedule_fact_id": str(item["schedule_fact_id"]),
                        "multiplier": str(item.get("multiplier", "1")),
                    }
                    for item in inputs
                ],
            }
            existing_key = (qname, period)
            if not tuple_path and existing_key in existing:
                if fact_type != "MONETARY" or existing[existing_key] != _decimal(
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
                "tuple_path": tuple_path,
                "tuple_instance_id": tuple_instance_id,
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
        "schema_version": 2,
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
