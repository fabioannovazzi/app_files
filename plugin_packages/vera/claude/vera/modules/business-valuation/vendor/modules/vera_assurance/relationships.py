"""Exact relationship, allocation, and conservation controls."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from .money import MoneyValidationError, decimal_text, parse_canonical_decimal
from .serialization import canonical_json_sha256

__all__ = [
    "RelationshipContractError",
    "build_allocation_ledger",
    "validate_allocation_ledger",
]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RELATIONSHIP_SHAPES = {"one_to_one", "one_to_many", "many_to_one", "many_to_many"}


class RelationshipContractError(ValueError):
    """Raised when allocation identity or conservation does not close."""


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RelationshipContractError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise RelationshipContractError(f"{label} must be a list")
    return list(value)


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RelationshipContractError(f"{label} must be non-empty trimmed text")
    return value


def _identifier(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise RelationshipContractError(f"{label} must be a canonical identifier")
    return text


def _decimal(value: object, *, label: str, non_negative: bool = True) -> Decimal:
    try:
        result = parse_canonical_decimal(value, label=label)
    except MoneyValidationError as exc:
        raise RelationshipContractError(str(exc)) from exc
    if non_negative and result < 0:
        raise RelationshipContractError(f"{label} must not be negative")
    return result


def _optional_identifier(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, label=label)


def _record(value: object, *, label: str) -> dict[str, Any]:
    item = _mapping(value, label=label)
    required = {
        "record_id",
        "amount",
        "currency",
        "unit",
        "entity_ref",
        "party_ref",
    }
    if set(item) != required:
        raise RelationshipContractError(f"{label} has invalid fields")
    amount = _decimal(item["amount"], label=f"{label}.amount")
    return {
        "record_id": _identifier(item["record_id"], label=f"{label}.record_id"),
        "amount": decimal_text(amount),
        "currency": _identifier(item["currency"], label=f"{label}.currency"),
        "unit": _identifier(item["unit"], label=f"{label}.unit"),
        "entity_ref": _optional_identifier(
            item["entity_ref"], label=f"{label}.entity_ref"
        ),
        "party_ref": _optional_identifier(
            item["party_ref"], label=f"{label}.party_ref"
        ),
    }


def _policy(value: object) -> dict[str, Any]:
    policy = _mapping(value, label="policy")
    required = {
        "relationship_shape",
        "require_same_currency",
        "require_same_unit",
        "require_same_entity",
        "require_same_party",
        "allow_evidence_reuse",
        "tolerance",
    }
    if set(policy) != required:
        raise RelationshipContractError("policy has invalid fields")
    shape = _text(policy["relationship_shape"], label="policy.relationship_shape")
    if shape not in _RELATIONSHIP_SHAPES:
        raise RelationshipContractError("unsupported relationship shape")
    normalized: dict[str, Any] = {"relationship_shape": shape}
    for field in (
        "require_same_currency",
        "require_same_unit",
        "require_same_entity",
        "require_same_party",
        "allow_evidence_reuse",
    ):
        if not isinstance(policy[field], bool):
            raise RelationshipContractError(f"policy.{field} must be boolean")
        normalized[field] = policy[field]
    if not normalized["require_same_currency"]:
        raise RelationshipContractError(
            "v1 allocation policy requires same currency; conversion is unsupported"
        )
    if not normalized["require_same_unit"]:
        raise RelationshipContractError(
            "v1 allocation policy requires same unit; conversion is unsupported"
        )
    tolerance = _decimal(policy["tolerance"], label="policy.tolerance")
    normalized["tolerance"] = decimal_text(tolerance)
    return normalized


def _allocation(value: object, *, label: str) -> dict[str, Any]:
    item = _mapping(value, label=label)
    required = {
        "allocation_id",
        "source_record_ref",
        "target_record_ref",
        "amount",
        "currency",
        "unit",
        "evidence_refs",
    }
    if set(item) != required:
        raise RelationshipContractError(f"{label} has invalid fields")
    evidence_refs = [
        _identifier(ref, label=f"{label}.evidence_refs[{index}]")
        for index, ref in enumerate(
            _sequence(item["evidence_refs"], label=f"{label}.evidence_refs")
        )
    ]
    if not evidence_refs or len(evidence_refs) != len(set(evidence_refs)):
        raise RelationshipContractError(
            f"{label}.evidence_refs must be non-empty and unique"
        )
    amount = _decimal(item["amount"], label=f"{label}.amount")
    return {
        "allocation_id": _identifier(
            item["allocation_id"], label=f"{label}.allocation_id"
        ),
        "source_record_ref": _identifier(
            item["source_record_ref"], label=f"{label}.source_record_ref"
        ),
        "target_record_ref": _identifier(
            item["target_record_ref"], label=f"{label}.target_record_ref"
        ),
        "amount": decimal_text(amount),
        "currency": _identifier(item["currency"], label=f"{label}.currency"),
        "unit": _identifier(item["unit"], label=f"{label}.unit"),
        "evidence_refs": evidence_refs,
    }


def _residual_rows(
    records: Sequence[Mapping[str, Any]],
    totals: Mapping[str, Decimal],
) -> list[dict[str, str]]:
    rows = []
    for record in records:
        record_id = str(record["record_id"])
        amount = parse_canonical_decimal(str(record["amount"]))
        residual = amount - totals.get(record_id, Decimal("0"))
        rows.append({"record_ref": record_id, "residual": decimal_text(residual)})
    return rows


def validate_allocation_ledger(value: object) -> dict[str, Any]:
    """Validate allocation identity, cardinality, and exact conservation."""

    payload = _mapping(value, label="allocation ledger")
    required = {
        "schema_version",
        "ledger_id",
        "policy",
        "source_records",
        "target_records",
        "allocations",
        "source_residuals",
        "target_residuals",
        "balanced",
        "content_sha256",
    }
    if set(payload) != required:
        raise RelationshipContractError("allocation ledger has invalid fields")
    if payload["schema_version"] != "vera.allocation_ledger.v1":
        raise RelationshipContractError("unsupported allocation-ledger schema")
    ledger_id = _identifier(payload["ledger_id"], label="ledger_id")
    policy = _policy(payload["policy"])
    source_records = [
        _record(item, label=f"source_records[{index}]")
        for index, item in enumerate(
            _sequence(payload["source_records"], label="source_records")
        )
    ]
    target_records = [
        _record(item, label=f"target_records[{index}]")
        for index, item in enumerate(
            _sequence(payload["target_records"], label="target_records")
        )
    ]
    if not source_records or not target_records:
        raise RelationshipContractError(
            "source_records and target_records must be non-empty"
        )
    source_by_id = {str(item["record_id"]): item for item in source_records}
    target_by_id = {str(item["record_id"]): item for item in target_records}
    if len(source_by_id) != len(source_records) or len(target_by_id) != len(
        target_records
    ):
        raise RelationshipContractError("record IDs must be unique per population")
    allocations = [
        _allocation(item, label=f"allocations[{index}]")
        for index, item in enumerate(
            _sequence(payload["allocations"], label="allocations")
        )
    ]
    allocation_ids = [str(item["allocation_id"]) for item in allocations]
    if len(allocation_ids) != len(set(allocation_ids)):
        raise RelationshipContractError("allocation IDs must be unique")

    source_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()
    source_totals: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    target_totals: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    used_evidence: set[str] = set()
    for allocation in allocations:
        source_ref = str(allocation["source_record_ref"])
        target_ref = str(allocation["target_record_ref"])
        if source_ref not in source_by_id or target_ref not in target_by_id:
            raise RelationshipContractError(
                "allocation references an unknown population record"
            )
        source = source_by_id[source_ref]
        target = target_by_id[target_ref]
        if policy["require_same_currency"]:
            currencies = {
                str(source["currency"]),
                str(target["currency"]),
                str(allocation["currency"]),
            }
            if len(currencies) != 1:
                raise RelationshipContractError("allocation currency mismatch")
        if policy["require_same_unit"]:
            units = {
                str(source["unit"]),
                str(target["unit"]),
                str(allocation["unit"]),
            }
            if len(units) != 1:
                raise RelationshipContractError("allocation unit mismatch")
        if policy["require_same_entity"]:
            if (
                source["entity_ref"] is None
                or target["entity_ref"] is None
                or source["entity_ref"] != target["entity_ref"]
            ):
                raise RelationshipContractError("allocation entity mismatch")
        if policy["require_same_party"]:
            if (
                source["party_ref"] is None
                or target["party_ref"] is None
                or source["party_ref"] != target["party_ref"]
            ):
                raise RelationshipContractError("allocation party mismatch")
        for evidence_ref in allocation["evidence_refs"]:
            if not policy["allow_evidence_reuse"] and evidence_ref in used_evidence:
                raise RelationshipContractError("allocation evidence was reused")
            used_evidence.add(str(evidence_ref))
        amount = parse_canonical_decimal(str(allocation["amount"]))
        source_counts[source_ref] += 1
        target_counts[target_ref] += 1
        source_totals[source_ref] += amount
        target_totals[target_ref] += amount

    shape = str(policy["relationship_shape"])
    if shape in {"one_to_one", "many_to_one"} and any(
        count > 1 for count in source_counts.values()
    ):
        raise RelationshipContractError(f"{shape} relationship reuses a source record")
    if shape in {"one_to_one", "one_to_many"} and any(
        count > 1 for count in target_counts.values()
    ):
        raise RelationshipContractError(f"{shape} relationship reuses a target record")

    tolerance = parse_canonical_decimal(str(policy["tolerance"]))
    source_residuals = _residual_rows(source_records, source_totals)
    target_residuals = _residual_rows(target_records, target_totals)
    for residual in (*source_residuals, *target_residuals):
        if parse_canonical_decimal(residual["residual"]) < -tolerance:
            raise RelationshipContractError(
                "allocated amount exceeds a population record"
            )
    balanced = all(
        abs(parse_canonical_decimal(item["residual"])) <= tolerance
        for item in (*source_residuals, *target_residuals)
    )
    if payload["source_residuals"] != source_residuals:
        raise RelationshipContractError("source residuals are stale")
    if payload["target_residuals"] != target_residuals:
        raise RelationshipContractError("target residuals are stale")
    if payload["balanced"] is not balanced:
        raise RelationshipContractError("balanced status is stale")
    content = {
        "schema_version": "vera.allocation_ledger.v1",
        "ledger_id": ledger_id,
        "policy": policy,
        "source_records": source_records,
        "target_records": target_records,
        "allocations": allocations,
        "source_residuals": source_residuals,
        "target_residuals": target_residuals,
        "balanced": balanced,
    }
    expected_digest = canonical_json_sha256(content)
    if payload["content_sha256"] != expected_digest:
        raise RelationshipContractError("allocation ledger content digest is stale")
    return {**content, "content_sha256": expected_digest}


def build_allocation_ledger(
    *,
    ledger_id: str,
    policy: Mapping[str, Any],
    source_records: Sequence[Mapping[str, Any]],
    target_records: Sequence[Mapping[str, Any]],
    allocations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build and seal an exact allocation ledger."""

    normalized_policy = _policy(policy)
    normalized_sources = [
        _record(item, label=f"source_records[{index}]")
        for index, item in enumerate(source_records)
    ]
    normalized_targets = [
        _record(item, label=f"target_records[{index}]")
        for index, item in enumerate(target_records)
    ]
    normalized_allocations = [
        _allocation(item, label=f"allocations[{index}]")
        for index, item in enumerate(allocations)
    ]
    source_totals: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    target_totals: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for allocation in normalized_allocations:
        amount = parse_canonical_decimal(str(allocation["amount"]))
        source_totals[str(allocation["source_record_ref"])] += amount
        target_totals[str(allocation["target_record_ref"])] += amount
    content = {
        "schema_version": "vera.allocation_ledger.v1",
        "ledger_id": ledger_id,
        "policy": normalized_policy,
        "source_records": normalized_sources,
        "target_records": normalized_targets,
        "allocations": normalized_allocations,
        "source_residuals": _residual_rows(normalized_sources, source_totals),
        "target_residuals": _residual_rows(normalized_targets, target_totals),
        "balanced": False,
    }
    tolerance = parse_canonical_decimal(str(normalized_policy["tolerance"]))
    content["balanced"] = all(
        abs(parse_canonical_decimal(item["residual"])) <= tolerance
        for item in (*content["source_residuals"], *content["target_residuals"])
    )
    return validate_allocation_ledger(
        {**content, "content_sha256": canonical_json_sha256(content)}
    )
