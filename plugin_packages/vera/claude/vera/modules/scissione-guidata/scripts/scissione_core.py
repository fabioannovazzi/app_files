"""Mechanical identities, dependency review and exact scissione schedules."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from typing import Any

__all__ = [
    "ScissioneError",
    "digest",
    "decimal",
    "validate_case",
    "build_revision",
    "simple_exchange",
]
KINDS = {
    "fact",
    "allocation",
    "liability",
    "ownership",
    "valuation",
    "tax_position",
    "rule",
    "decision",
    "deadline",
    "document",
}
ROUNDING = {"half_even": ROUND_HALF_EVEN, "half_up": ROUND_HALF_UP}
# Bump when calculation or review semantics change; historical approvals bind it.
ENGINE_VERSION = "0.1.0"
SCOPE = {
    "jurisdiction": "IT",
    "accounting": "OIC",
    "operation": "partial_proportional",
    "beneficiary": "new",
}


class ScissioneError(ValueError):
    """The supplied mechanical contract cannot be executed."""


def digest(value: Any) -> str:
    """Hash canonical JSON; identities and exact arithmetic justify fixed logic."""
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def decimal(value: Any) -> Decimal:
    """Require finite decimal strings; unknown is never zero."""
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"-?\d+(?:\.\d+)?", value)
        or len(value) > 36
    ):
        raise ScissioneError("Amounts and shares require bounded decimal strings")
    return Decimal(value)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScissioneError(f"Missing {label}")
    return value


def _index(rows: Any, label: str) -> dict[str, dict]:
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ScissioneError(f"{label} must be a record array")
    for row in rows:
        if not isinstance(row["id"], str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_-]{0,79}", row["id"]
        ):
            raise ScissioneError("Invalid stable identifier")
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        raise ScissioneError(f"Duplicate {label} identifier")
    return result


def _refs(values: Any, available: dict, label: str, *, required: bool = False) -> None:
    if (
        not isinstance(values, list)
        or not all(isinstance(v, str) for v in values)
        or len(set(values)) != len(values)
    ):
        raise ScissioneError(f"Invalid {label} references")
    if set(values) - available.keys() or (required and not values):
        raise ScissioneError(f"Missing or unknown {label} reference")


def _no_floats(value: Any) -> None:
    if isinstance(value, float):
        raise ScissioneError("Floating point case values are not permitted")
    if isinstance(value, dict):
        for child in value.values():
            _no_floats(child)
    elif isinstance(value, list):
        for child in value:
            _no_floats(child)


def _fingerprints(case: dict, records: dict) -> dict[str, str]:
    evidence = _index(case["evidence"], "evidence")
    entities = _index(case["entities"], "entity")
    result: dict[str, str] = {}
    visiting: set[str] = set()

    def visit(key: str) -> str:
        if key in visiting:
            raise ScissioneError("Cyclic case dependency")
        if key not in result:
            visiting.add(key)
            row = records[key]
            result[key] = digest(
                {
                    "record": row,
                    "case_date": case["as_of"],
                    "purpose": case["purpose"],
                    "operation_id": case["operation_id"],
                    "dependencies": {ref: visit(ref) for ref in row["depends_on"]},
                    "engine_version": ENGINE_VERSION,
                    "evidence": {
                        ref: {k: v for k, v in evidence[ref].items() if k != "path"}
                        for ref in row["evidence_ids"]
                    },
                    "entities": {ref: entities[ref] for ref in row["entity_ids"]},
                }
            )
            visiting.remove(key)
        return result[key]

    for key in records:
        visit(key)
    return result


def validate_case(case: dict) -> dict[str, dict]:
    """Check structure and relations; evidence sufficiency remains a judgment."""
    _no_floats(case)
    if case["schema_version"] != "vera.scissione.v1":
        raise ScissioneError("Unsupported case schema")
    _text(case["operation_id"], "operation identity")
    _text(case["purpose"], "operation purpose")
    date.fromisoformat(case["as_of"])
    if case["currency"] != "EUR":
        raise ScissioneError("The initial calculation contract requires EUR")
    entities = _index(case["entities"], "entity")
    if len(entities) < 2:
        raise ScissioneError("Identify the scissa and beneficiary")
    for entity in entities.values():
        _text(entity["name"], "entity name")
        for field in ("confirmed_by", "scope"):
            _text(entity["authorization"][field], f"entity authorization {field}")
        date.fromisoformat(entity["authorization"]["confirmed_on"])
    evidence = _index(case["evidence"], "evidence")
    for item in evidence.values():
        _refs(item["entity_ids"], entities, "evidence entity", required=True)
        _text(item["path"], "receipted evidence path")
        _text(item["locator"], "evidence locator or explicit whole-file scope")
        date.fromisoformat(item["as_of"])
        if not isinstance(item["sha256"], str) or not re.fullmatch(
            r"[a-f0-9]{64}", item["sha256"]
        ):
            raise ScissioneError("Evidence requires its captured SHA-256")
    records = _index(case["records"], "case record")
    for record in records.values():
        if record["kind"] not in KINDS or record["status"] not in {
            "known",
            "unknown",
            "contested",
        }:
            raise ScissioneError("Invalid record kind or evidence status")
        if type(record["material"]) is not bool or not isinstance(record["data"], dict):
            raise ScissioneError("Explicit materiality and data required")
        _refs(record["entity_ids"], entities, "record entity", required=True)
        _refs(record["evidence_ids"], evidence, "record evidence")
        _refs(record["depends_on"], records, "record dependency")
        for ref in record["evidence_ids"]:
            if not set(evidence[ref]["entity_ids"]).issubset(record["entity_ids"]):
                raise ScissioneError("Evidence entity is outside the record perimeter")
        if record["status"] == "known" and not (
            record["evidence_ids"] or record["depends_on"]
        ):
            raise ScissioneError(
                "Known records require evidence or derived dependencies"
            )
        data = record["data"]
        if record["kind"] == "allocation":
            if (
                data["from_entity"] not in record["entity_ids"]
                or data["to_entity"] not in record["entity_ids"]
            ):
                raise ScissioneError(
                    "Allocation entity is outside its declared perimeter"
                )
            if data["side"] not in {"asset", "liability"}:
                raise ScissioneError("Distinguish assets and liabilities")
            for basis in ("book", "tax", "economic"):
                amounts = data[basis]
                if set(amounts) != {"before", "transferred", "remaining"}:
                    raise ScissioneError("Each value basis requires a complete bridge")
                for amount in amounts.values():
                    if amount is not None and decimal(amount) < 0:
                        raise ScissioneError("Use a side with nonnegative amounts")
        elif record["kind"] == "rule":
            if data["state"] not in {
                "candidate",
                "source_checked",
                "professional_review_pending",
                "superseded",
                "withdrawn",
            }:
                raise ScissioneError(
                    "Rule approval is recorded separately for an exact version"
                )
            for key in (
                "act",
                "article",
                "paragraph",
                "version",
                "scope",
                "source_status",
            ):
                _text(data[key], f"rule {key}")
            for key in ("effective_from", "applicable_from"):
                if data[key] is not None:
                    date.fromisoformat(data[key])
        elif record["kind"] == "decision":
            for key in ("choice", "rationale", "alternatives"):
                _text(data[key], f"decision {key}")
        elif record["kind"] == "deadline":
            if (
                data.get("completed_on")
                and data.get("receipt_evidence_id") not in record["evidence_ids"]
            ):
                raise ScissioneError("A completed event requires receipt evidence")
    for field in ("route_record", "perimeter_record", "calculation_record"):
        if case[field] not in records or records[case[field]]["kind"] != "decision":
            raise ScissioneError(f"{field} must identify a decision")
    if set(records[case["route_record"]]["data"]["scope"]) != set(SCOPE):
        raise ScissioneError(
            "Explicit jurisdiction, accounting, operation and beneficiary required"
        )
    perimeter = records[case["perimeter_record"]]
    _refs(
        perimeter["data"]["required_records"],
        records,
        "material perimeter",
        required=True,
    )
    if not set(perimeter["data"]["required_records"]).issubset(perimeter["depends_on"]):
        raise ScissioneError("Perimeter must depend on its required records")
    _fingerprints(case, records)
    return records


def simple_exchange(
    *,
    beneficiary_value: str,
    transferred_value: str,
    existing_units: str,
    nominal_value: str,
    homogeneous_rights: bool,
    reciprocal_holdings: bool,
    own_shares: bool,
    separate_synergies: bool,
    cash_adjustment: bool,
) -> dict[str, str]:
    """Conditional example A arithmetic; this does not approve an operation."""
    if homogeneous_rights is not True or any(
        flag is not False
        for flag in (
            reciprocal_holdings,
            own_shares,
            separate_synergies,
            cash_adjustment,
        )
    ):
        raise ScissioneError("The simple exchange assumptions are not satisfied")
    b, t, n, nominal = map(
        decimal, (beneficiary_value, transferred_value, existing_units, nominal_value)
    )
    if min(b, t, n, nominal) <= 0:
        raise ScissioneError("Positive values and units are required")
    with localcontext() as context:
        context.prec = 100
        units = n * t / b
        return {
            "new_units": str(units),
            "new_share": str(t / (b + t)),
            "old_share": str(b / (b + t)),
            "nominal_increase": str(units * nominal),
            "economic_transfer": str(t),
        }


def _dependencies(records: dict, keys: list[str] | set[str]) -> set[str]:
    """Include every explicitly declared ancestor without semantic classification."""
    pending, visited = list(keys), set()
    while pending:
        key = pending.pop()
        if key not in visited:
            visited.add(key)
            pending.extend(records[key]["depends_on"])
    return visited


def _schedule(case: dict, records: dict, approvals: dict) -> tuple[dict, list[str]]:
    issues: list[str] = []
    calculation = records[case["calculation_record"]]
    request = calculation["data"]
    refs = [
        case["route_record"],
        request["ownership_id"],
        request["valuation_id"],
        *request["allocation_ids"],
    ]
    _refs(refs, records, "calculation")
    if not set(refs).issubset(calculation["depends_on"]):
        raise ScissioneError(
            "Calculation inputs and route must be declared dependencies"
        )
    for key in sorted(_dependencies(records, [case["calculation_record"], *refs])):
        if key not in approvals or records[key]["status"] != "known":
            issues.append(f"Calculation awaits exact-version review: {key}")
    if issues:
        return {}, issues
    if (
        records[request["ownership_id"]]["kind"] != "ownership"
        or records[request["valuation_id"]]["kind"] != "valuation"
    ):
        raise ScissioneError("Calculation requires ownership and valuation records")
    rounding = request["rounding"]
    if rounding not in ROUNDING:
        raise ScissioneError("Explicit supported rounding policy required")
    quantum, units = decimal(request["unit_quantum"]), decimal(request["new_units"])
    if quantum <= 0 or units <= 0 or units % quantum:
        raise ScissioneError(
            "Positive new units must be a multiple of positive quantum"
        )
    owners = records[request["ownership_id"]]["data"]["owners"]
    indexed_owners = _index(owners, "owner")
    if (
        not owners
        or any(decimal(row["share"]) <= 0 for row in owners)
        or sum(decimal(row["share"]) for row in owners) != 1
    ):
        raise ScissioneError("Positive owner fractions must sum exactly to one")
    values = records[request["valuation_id"]]["data"]
    before, transferred, remaining = (
        decimal(values[key]) for key in ("before", "transferred", "remaining")
    )
    bridge = decimal(values["bridge"])
    if (
        min(before, transferred, remaining) <= 0
        or before + bridge != transferred + remaining
    ):
        raise ScissioneError(
            "Positive economic values require a reconciled explicit bridge"
        )
    if (
        values["homogeneous_rights"] is not True
        or values["reciprocal_holdings"] is not False
    ):
        raise ScissioneError("The first path requires reviewed homogeneous rights")
    rows = []
    for key, owner in indexed_owners.items():
        share = decimal(owner["share"])
        exact = units * share
        rounded = (exact / quantum).quantize(
            Decimal("1"), rounding=ROUNDING[rounding]
        ) * quantum
        rows.append(
            {
                "owner_id": key,
                "share_before": str(share),
                "share_after": str(share),
                "units_exact": str(exact),
                "units_rounded": str(rounded),
                "unit_residual": str(exact - rounded),
                "economic_before": str(before * share),
                "economic_remaining": str(remaining * share),
                "economic_transferred": str(transferred * share),
                "economic_bridge": str(bridge * share),
                "shareholder_tax_cost": owner["tax_cost"],
            }
        )
        if exact != rounded:
            issues.append(f"Unresolved fractional allocation for owner {key}")
        if owner["tax_cost"] is not None:
            decimal(owner["tax_cost"])
    allocations, seen = [], set()
    for key in request["allocation_ids"]:
        row = records[key]
        if row["kind"] != "allocation":
            raise ScissioneError("Schedule requires allocation records")
        data = row["data"]
        if data["item_id"] in seen:
            raise ScissioneError("Duplicate inventory allocation")
        seen.add(data["item_id"])
        for basis in ("book", "tax", "economic"):
            amounts = data[basis]
            if any(value is None for value in amounts.values()):
                issues.append(f"Missing {basis} amount for {key}")
            elif decimal(amounts["before"]) != decimal(
                amounts["transferred"]
            ) + decimal(amounts["remaining"]):
                issues.append(f"Unreconciled {basis} allocation for {key}")
        allocations.append({"record_id": key, **data})
    if not allocations:
        issues.append("No reviewed inventory allocations")
    totals = {}
    for basis in ("book", "tax", "economic"):
        totals[basis] = {}
        for field in ("before", "transferred", "remaining"):
            amounts = [entry[basis][field] for entry in allocations]
            totals[basis][field] = (
                None
                if any(amount is None for amount in amounts)
                else str(
                    sum(
                        (
                            decimal(entry[basis][field])
                            * (1 if entry["side"] == "asset" else -1)
                            for entry in allocations
                        ),
                        Decimal("0"),
                    )
                )
            )
    for field, value in (
        ("before", before),
        ("transferred", transferred),
        ("remaining", remaining),
    ):
        total = totals["economic"][field]
        if total is None or decimal(total) != value:
            issues.append(
                f"Economic inventory does not reconcile to valuation: {field}"
            )
    return {
        "owners": rows,
        "allocations": allocations,
        "net_totals": totals,
        "units_residual": str(
            units - sum(decimal(row["units_rounded"]) for row in rows)
        ),
        "currency": case["currency"],
        "filing_status": "not_performed",
        "professional_conclusion": "not_issued",
    }, issues


def build_revision(
    case: dict, *, previous: dict | None = None, review: dict | None = None
) -> dict:
    """Preserve unrelated approvals and reopen exact transitive dependants."""
    case = copy.deepcopy(case)
    records = validate_case(case)
    fingerprints = _fingerprints(case, records)
    old = previous["fingerprints"] if previous else {}
    changed = sorted(
        key
        for key in set(old) | set(fingerprints)
        if old.get(key) != fingerprints.get(key)
    )
    if previous and case["operation_id"] != previous["case"]["operation_id"]:
        raise ScissioneError("Cannot replace the operation identity")
    approvals = {
        key: value
        for key, value in (previous["approvals"].items() if previous else [])
        if key not in changed
    }
    if review is not None:
        if (
            previous is None
            or digest(case) != digest(previous["case"])
            or review["revision_sha256"] != previous["revision_sha256"]
        ):
            raise ScissioneError("Stale review: show the exact current revision")
        for field in ("reviewer", "role", "rationale"):
            _text(review[field], f"review {field}")
        if datetime.fromisoformat(review["reviewed_at"]).tzinfo is None:
            raise ScissioneError("Review timestamp requires a timezone")
        _refs(review["record_ids"], records, "review", required=True)
        for key in review["record_ids"]:
            row = records[key]
            if row["kind"] == "document" and not previous["schedule"]:
                raise ScissioneError(
                    "Review the generated schedules before approving documents"
                )
            for dependency_id in _dependencies(records, [key]):
                dependency = records[dependency_id]
                if dependency["status"] != "known":
                    raise ScissioneError(
                        "Unknown or contested dependencies cannot be approved"
                    )
                if dependency["kind"] == "rule" and (
                    dependency["data"]["state"]
                    in {"candidate", "superseded", "withdrawn"}
                    or dependency["data"]["source_status"] != "original_checked"
                ):
                    raise ScissioneError(
                        "A rule needs its original checked source before approval"
                    )
            approvals[key] = {
                "fingerprint": fingerprints[key],
                **{
                    field: review[field]
                    for field in ("reviewer", "role", "rationale", "reviewed_at")
                },
                "scope": row["data"].get("scope"),
                "reviewed_revision": review["revision_sha256"],
            }
    issues = []
    required = set(records[case["perimeter_record"]]["data"]["required_records"]) | {
        case[field]
        for field in ("route_record", "perimeter_record", "calculation_record")
    }
    required |= {key for key, row in records.items() if row["material"]}
    required = _dependencies(records, required)
    for key in sorted(required):
        if records[key]["status"] != "known":
            issues.append(f"Material evidence {records[key]['status']}: {key}")
        if key not in approvals:
            issues.append(f"Professional review pending: {key}")
    supported = records[case["route_record"]]["data"]["scope"] == SCOPE
    if not supported:
        issues.append(
            "Route outside initial Italian OIC partial proportional/new-beneficiary path"
        )
        schedule = {}
    else:
        with localcontext() as context:
            context.prec = 100
            schedule, calculation_issues = _schedule(case, records, approvals)
        issues.extend(calculation_issues)
    result = {
        "schema_version": "vera.scissione_revision.v1",
        "engine_version": ENGINE_VERSION,
        "case": case,
        "fingerprints": fingerprints,
        "approvals": approvals,
        "previous_sha256": previous["revision_sha256"] if previous else None,
        "change_impact": {
            "invalidated_ids": changed if previous else [],
            "invalidated_approval_ids": (
                sorted(set(changed) & set(previous["approvals"])) if previous else []
            ),
            "preserved_approval_ids": sorted(
                set(approvals) - set(review["record_ids"] if review else [])
            ),
        },
        "status": (
            "unsupported"
            if not supported
            else "partial" if issues else "prepared_for_review"
        ),
        "issues": issues,
        "schedule": schedule,
        "filing_status": "not_performed",
        "legal_validation": "not_certified",
    }
    result["revision_sha256"] = digest(result)
    return result
