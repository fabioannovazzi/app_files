"""Bind authored narrative to inspected records without judging semantic truth.

Reference identity, exact numeric equality and review freshness are mechanical.
Whether the cited evidence supports the prose remains a professional judgment.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from valuation_case import digest, fields, indexed, require, reviewed, text
from valuation_engine import decimal

__all__ = ["build_claims"]


def _references(value: Any) -> list[str]:
    require(
        isinstance(value, list) and len(value) <= 2000,
        "Expected bounded claim reference list",
    )
    require(
        all(isinstance(ref, str) and ref.strip() for ref in value),
        "Invalid claim reference",
    )
    require(len(set(value)) == len(value), "Duplicate claim reference")
    return value


def build_claims(
    case: dict,
    inputs: dict,
    sources: dict,
    calculations: list,
    methods: list,
    sensitivity: list,
    normalizations: dict,
    mandate_dependency: str,
    statements: dict,
) -> list[dict]:
    """Preserve missing, inconsistent or unreviewed claims as explicit workpapers."""
    amounts = {row["id"]: row for row in calculations}
    method_map = {row["method_id"]: row for row in methods}
    scenarios = {row["id"]: row for row in sensitivity}
    scenario_methods = {
        row["id"]: row["method_id"] for row in case.get("sensitivity", [])
    }
    result = []
    for claim in indexed(case.get("claims", [])).values():
        fields(
            claim,
            {
                "id",
                "kind",
                "text",
                "location",
                "basis",
                "source_ids",
                "input_ids",
                "calculation_ids",
                "method_ids",
                "limitations",
            },
            {"values", "review"},
        )
        for key in ("kind", "text", "location", "basis"):
            text(claim[key], key)
        require(
            claim["kind"] in {"fact", "assumption", "hypothesis", "opinion"},
            "Choose the claim kind explicitly",
        )
        require(
            isinstance(claim["limitations"], list)
            and all(
                isinstance(value, str) and value.strip()
                for value in claim["limitations"]
            ),
            "Invalid claim limitations",
        )
        selected = {
            key: _references(claim[key])
            for key in ("source_ids", "input_ids", "calculation_ids", "method_ids")
        }
        require(any(selected.values()), "A claim needs evidence references")
        issues = []
        closure: set[str] = set()
        pending = list(selected["calculation_ids"])
        while pending:
            ref = pending.pop()
            if ref in closure:
                continue
            if ref not in amounts:
                issues.append(f"Unavailable calculation: {ref}")
                continue
            closure.add(ref)
            pending.extend(amounts[ref]["arguments"])
        used_scenarios = {ref.split("/", 1)[0] for ref in closure} & scenarios.keys()
        used_methods = (
            set(selected["method_ids"])
            | ({ref.split("/", 1)[0] for ref in closure} & method_map.keys())
            | {scenario_methods[ref] for ref in used_scenarios}
        )
        for ref in sorted(used_methods):
            if ref not in method_map or method_map[ref]["status"] in {
                "blocked",
                "excluded",
            }:
                issues.append(f"Unavailable method: {ref}")
        used_inputs = (
            set(selected["input_ids"])
            | {ref for key in closure for ref in amounts[key]["input_ids"]}
            | {
                ref
                for key in used_methods
                if key in method_map
                for ref in method_map[key].get("input_ids", [])
            }
        )
        used_groups = [
            group
            for target, group in sorted(normalizations.items())
            if target in used_inputs
            or any(ref.startswith(f"normalization/{group['id']}/") for ref in closure)
        ]
        used_inputs.update(ref for group in used_groups for ref in group["input_ids"])
        used_statements = [
            group
            for group in statements.values()
            if set(group["bound_input_ids"]) & used_inputs
            or any(ref.startswith(f"statement/{group['id']}/") for ref in closure)
        ]
        used_inputs.update(
            ref for group in used_statements for ref in group["input_ids"]
        )
        used_sources = (
            set(selected["source_ids"])
            | {
                ref
                for key in used_inputs
                if key in inputs
                for ref in inputs[key]["source_ids"]
            }
            | {ref for key in closure for ref in amounts[key]["source_ids"]}
            | {ref for group in used_groups for ref in group["source_ids"]}
            | {ref for group in used_statements for ref in group["source_ids"]}
            | {
                ref
                for key in used_methods
                if key in method_map
                for ref in method_map[key].get("source_ids", [])
            }
        )
        for ref in sorted(used_inputs):
            if ref not in inputs or inputs[ref]["value"] is None:
                issues.append(f"Unavailable input: {ref}")
        for ref in sorted(used_sources - sources.keys()):
            issues.append(f"Unavailable source: {ref}")
        for group in used_groups:
            if group["status"] == "blocked":
                issues.append(f"Unreconciled normalization: {group['id']}")
        for group in used_statements:
            if group["status"] == "blocked":
                issues.append(f"Unreconciled statement: {group['id']}")
        values = claim.get("values", [])
        require(
            isinstance(values, list) and len(values) <= 2000,
            "Expected bounded claim numeric bindings",
        )
        bound_values = []
        seen_values: set[str] = set()
        for value in values:
            fields(value, {"calculation_id", "value", "unit"})
            ref = text(value["calculation_id"], "numeric claim calculation ID")
            text(value["unit"], "numeric claim unit")
            asserted = decimal(value["value"])
            require(ref not in seen_values, "Duplicate claim numeric binding")
            seen_values.add(ref)
            if ref not in selected["calculation_ids"] or ref not in amounts:
                issues.append(
                    f"Numeric binding requires a declared available calculation: {ref}"
                )
                continue
            actual = amounts[ref]
            if asserted != decimal(actual["value"]) or value["unit"] != actual["unit"]:
                issues.append(
                    f"Numeric claim differs from calculation value or unit: {ref}"
                )
            bound_values.append(
                {
                    "calculation_id": ref,
                    "value": actual["value"],
                    "unit": actual["unit"],
                    "asserted_value": value["value"],
                    "asserted_unit": value["unit"],
                }
            )
        dependency = digest(
            {
                "case_id": case["case_id"],
                "entity_name": case["entity_name"],
                "mandate": case["mandate"],
                "mandate_details_sha256": mandate_dependency,
                "audience": case["audience"],
                "currency": case["currency"],
                "synthetic": case["synthetic"],
                "claim": {
                    key: value for key, value in claim.items() if key != "review"
                },
                "calculations": [amounts[ref] for ref in sorted(closure)],
                "inputs": [inputs[ref] for ref in sorted(used_inputs) if ref in inputs],
                "sources": [
                    sources[ref] for ref in sorted(used_sources) if ref in sources
                ],
                "methods": [
                    method_map[ref] for ref in sorted(used_methods) if ref in method_map
                ],
                "scenarios": [scenarios[ref] for ref in sorted(used_scenarios)],
                "normalizations": used_groups,
                "statements": used_statements,
            }
        )
        complete = (
            not issues
            and all(inputs[ref]["status"] == "confirmed" for ref in used_inputs)
            and all(sources[ref]["status"] == "reviewed" for ref in used_sources)
            and all(group["status"] == "accepted_workpaper" for group in used_groups)
            and all(
                group["status"] == "accepted_workpaper" for group in used_statements
            )
        )
        eligible = complete and all(
            method_map[ref]["status"] == "accepted_workpaper" for ref in used_methods
        )
        accepted = eligible and reviewed(claim.get("review"), dependency)
        result.append(
            {
                **deepcopy(claim),
                "dependency_sha256": dependency,
                "status": (
                    "blocked"
                    if issues
                    else (
                        "accepted_workpaper"
                        if accepted
                        else "ready_for_professional_review" if complete else "partial"
                    )
                ),
                "review_dependencies_ready": eligible,
                "stale_review": bool(claim.get("review"))
                and not reviewed(claim["review"], dependency),
                "issues": issues,
                "resolved_values": bound_values,
                "resolved_input_ids": sorted(used_inputs),
                "resolved_source_ids": sorted(used_sources),
                "resolved_calculation_ids": sorted(closure),
                "resolved_method_ids": sorted(used_methods),
                "scenario_ids": sorted(used_scenarios),
                "semantic_support": (
                    "locally_attested_not_independently_verified"
                    if accepted
                    else "requires_professional_review"
                ),
            }
        )
    return result
