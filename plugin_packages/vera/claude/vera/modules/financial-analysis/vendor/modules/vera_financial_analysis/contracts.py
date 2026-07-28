"""Case-level contracts for Vera financial analysis preparation.

These contracts are deterministic because identity, hashes, key declarations,
cardinality policies, exact reconciliation arithmetic, and reference closure
are mechanically verifiable. They do not decide accounting meaning, source
authority, reporting perimeter, acceptable tolerances, or professional
conclusions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from vera_assurance.money import decimal_text, parse_canonical_decimal
from vera_assurance.serialization import canonical_json_sha256

from .registry import FDD_PACK_RECIPES

__all__ = [
    "FinancialAnalysisContractError",
    "REGISTERED_ANALYSIS_PACKS",
    "REGISTERED_ANALYSIS_PACK_RECIPES",
    "build_analysis_pack_request",
    "build_crosswalk_manifest",
    "build_data_package_manifest",
    "build_dataset_contract",
    "build_prepared_evidence_manifest",
    "build_reconciliation_result",
    "build_relationship_contract",
    "validate_analysis_pack_request",
    "validate_crosswalk_manifest",
    "validate_data_package_manifest",
    "validate_dataset_contract",
    "validate_prepared_evidence_manifest",
    "validate_reconciliation_result",
    "validate_relationship_contract",
]

REGISTERED_ANALYSIS_PACK_RECIPES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "monthly_pnl": frozenset({"monthly_pnl_from_reviewed_mapping.v1"}),
        "working_capital": frozenset(
            {"public_working_capital_from_reviewed_policy.v1"}
        ),
        "customer_concentration": frozenset(
            {"customer_concentration_from_reviewed_public_disclosure.v1"}
        ),
        **{
            pack_id: frozenset({recipe_id})
            for pack_id, recipe_id in FDD_PACK_RECIPES.items()
        },
    }
)
REGISTERED_ANALYSIS_PACKS = frozenset(REGISTERED_ANALYSIS_PACK_RECIPES)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVITY = {"public", "internal", "confidential", "restricted"}
_DATA_TYPES = {"boolean", "date", "decimal", "integer", "text"}
_AGGREGATIONS = {
    "count",
    "first",
    "last",
    "max",
    "min",
    "none",
    "sum",
    "weighted_average",
}
_PERIOD_ROLES = {
    "event_date",
    "none",
    "period_end",
    "period_start",
    "snapshot_date",
}
_CARDINALITIES = {"many_to_many", "many_to_one", "one_to_many", "one_to_one"}
_JOIN_TYPES = {"full", "inner", "left", "right"}
_REVIEW_POLICIES = {"allow", "fail", "qualify"}
_PERIOD_ALIGNMENTS = {"exact", "nearest_prior", "not_applicable", "same_period"}
_RECONCILIATION_STATUSES = {"failed", "not_applicable", "passed", "qualified"}
_CHECK_STATUSES = {"failed", "not_applicable", "passed", "qualified"}
_EXCEPTION_SEVERITIES = {"blocking", "info", "warning"}
_PREPARATION_STATUSES = {"failed", "passed", "qualified"}


class FinancialAnalysisContractError(ValueError):
    """Raised when a financial-analysis contract is inconsistent."""


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FinancialAnalysisContractError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FinancialAnalysisContractError(f"{label} must be a list")
    return list(value)


def _text(value: object, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise FinancialAnalysisContractError(f"{label} must be trimmed text")
    if not value and not allow_empty:
        raise FinancialAnalysisContractError(f"{label} must be non-empty")
    return value


def _identifier(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise FinancialAnalysisContractError(f"{label} must be a canonical identifier")
    return text


def _identifier_list(
    value: object,
    *,
    label: str,
    allow_empty: bool = False,
) -> list[str]:
    items = [
        _identifier(item, label=f"{label}[{index}]")
        for index, item in enumerate(_sequence(value, label=label))
    ]
    if (not items and not allow_empty) or len(items) != len(set(items)):
        qualifier = "unique" if allow_empty else "non-empty and unique"
        raise FinancialAnalysisContractError(f"{label} must be {qualifier}")
    return items


def _non_negative_int(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise FinancialAnalysisContractError(f"{label} must be a non-negative integer")
    return value


def _sha256(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _SHA256_RE.fullmatch(text) is None:
        raise FinancialAnalysisContractError(f"{label} must be lowercase SHA-256 text")
    return text


def _iso_date(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise FinancialAnalysisContractError(f"{label} must be an ISO date") from exc
    return text


def _exact_fields(
    value: Mapping[str, Any],
    *,
    required: set[str],
    label: str,
) -> None:
    missing = required - set(value)
    unexpected = set(value) - required
    if missing or unexpected:
        raise FinancialAnalysisContractError(
            f"{label} fields invalid; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )


def _sealed_content(
    value: Mapping[str, Any],
    *,
    schema_version: str,
    required: set[str],
    label: str,
) -> dict[str, Any]:
    _exact_fields(
        value,
        required={"schema_version", *required, "content_sha256"},
        label=label,
    )
    if value["schema_version"] != schema_version:
        raise FinancialAnalysisContractError(f"unsupported {label} schema")
    content = {key: value[key] for key in value if key != "content_sha256"}
    expected = canonical_json_sha256(content)
    if value["content_sha256"] != expected:
        raise FinancialAnalysisContractError(f"{label} content digest is stale")
    return content


def _seal(content: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(content)
    return {**normalized, "content_sha256": canonical_json_sha256(normalized)}


def _limitations(value: object, *, label: str = "limitations") -> list[str]:
    return [
        _text(item, label=f"{label}[{index}]")
        for index, item in enumerate(_sequence(value, label=label))
    ]


def validate_data_package_manifest(value: object) -> dict[str, Any]:
    """Validate source identities and a reviewed reporting perimeter."""

    payload = _mapping(value, label="data package manifest")
    content = _sealed_content(
        payload,
        schema_version="vera.data_package_manifest.v1",
        required={
            "package_id",
            "reporting_perimeter",
            "sensitivity",
            "snapshot_id",
            "sources",
        },
        label="data package manifest",
    )
    perimeter = _mapping(content["reporting_perimeter"], label="reporting_perimeter")
    _exact_fields(
        perimeter,
        required={
            "currency_refs",
            "entity_refs",
            "period_end",
            "period_start",
        },
        label="reporting_perimeter",
    )
    period_start = _iso_date(
        perimeter["period_start"], label="reporting_perimeter.period_start"
    )
    period_end = _iso_date(
        perimeter["period_end"], label="reporting_perimeter.period_end"
    )
    if period_end < period_start:
        raise FinancialAnalysisContractError(
            "reporting_perimeter period_end precedes period_start"
        )
    sensitivity = _text(content["sensitivity"], label="sensitivity")
    if sensitivity not in _SENSITIVITY:
        raise FinancialAnalysisContractError("unsupported sensitivity")
    sources = []
    for index, raw_source in enumerate(_sequence(content["sources"], label="sources")):
        label = f"sources[{index}]"
        source = _mapping(raw_source, label=label)
        _exact_fields(
            source,
            required={
                "artifact_ref",
                "byte_count",
                "dataset_contract_ref",
                "file_name",
                "locator",
                "sha256",
                "snapshot_id",
                "source_id",
            },
            label=label,
        )
        file_name = _text(source["file_name"], label=f"{label}.file_name")
        if "/" in file_name or "\\" in file_name:
            raise FinancialAnalysisContractError(
                f"{label}.file_name must not contain a path"
            )
        sources.append(
            {
                "source_id": _identifier(
                    source["source_id"], label=f"{label}.source_id"
                ),
                "artifact_ref": _identifier(
                    source["artifact_ref"], label=f"{label}.artifact_ref"
                ),
                "file_name": file_name,
                "locator": _text(source["locator"], label=f"{label}.locator"),
                "byte_count": _non_negative_int(
                    source["byte_count"], label=f"{label}.byte_count"
                ),
                "sha256": _sha256(source["sha256"], label=f"{label}.sha256"),
                "snapshot_id": _identifier(
                    source["snapshot_id"], label=f"{label}.snapshot_id"
                ),
                "dataset_contract_ref": _identifier(
                    source["dataset_contract_ref"],
                    label=f"{label}.dataset_contract_ref",
                ),
            }
        )
    source_ids = [item["source_id"] for item in sources]
    if not sources or len(source_ids) != len(set(source_ids)):
        raise FinancialAnalysisContractError(
            "sources must be non-empty with unique source_id values"
        )
    artifact_refs = [item["artifact_ref"] for item in sources]
    if len(artifact_refs) != len(set(artifact_refs)):
        raise FinancialAnalysisContractError(
            "sources must have unique artifact_ref values"
        )
    snapshot_id = _identifier(content["snapshot_id"], label="snapshot_id")
    if any(item["snapshot_id"] != snapshot_id for item in sources):
        raise FinancialAnalysisContractError(
            "every source snapshot_id must match the package snapshot_id"
        )
    normalized = {
        "schema_version": "vera.data_package_manifest.v1",
        "package_id": _identifier(content["package_id"], label="package_id"),
        "snapshot_id": snapshot_id,
        "reporting_perimeter": {
            "entity_refs": _identifier_list(
                perimeter["entity_refs"],
                label="reporting_perimeter.entity_refs",
            ),
            "period_start": period_start,
            "period_end": period_end,
            "currency_refs": _identifier_list(
                perimeter["currency_refs"],
                label="reporting_perimeter.currency_refs",
            ),
        },
        "sensitivity": sensitivity,
        "sources": sources,
    }
    if normalized != content:
        raise FinancialAnalysisContractError("data package manifest is not canonical")
    return _seal(normalized)


def build_data_package_manifest(
    *,
    package_id: str,
    snapshot_id: str,
    reporting_perimeter: Mapping[str, Any],
    sensitivity: str,
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build and seal a data-package manifest."""

    return validate_data_package_manifest(
        _seal(
            {
                "schema_version": "vera.data_package_manifest.v1",
                "package_id": package_id,
                "snapshot_id": snapshot_id,
                "reporting_perimeter": dict(reporting_perimeter),
                "sensitivity": sensitivity,
                "sources": [dict(item) for item in sources],
            }
        )
    )


def validate_dataset_contract(value: object) -> dict[str, Any]:
    """Validate reviewed grain, key, field, unit, and period declarations."""

    payload = _mapping(value, label="dataset contract")
    content = _sealed_content(
        payload,
        schema_version="vera.dataset_contract.v1",
        required={
            "dataset_contract_id",
            "dataset_id",
            "fields",
            "grain",
            "keys",
            "limitations",
            "period",
            "review_status",
            "source_artifact_refs",
            "version",
        },
        label="dataset contract",
    )
    if content["review_status"] != "reviewed":
        raise FinancialAnalysisContractError(
            "dataset contract must have reviewed status"
        )
    period = _mapping(content["period"], label="period")
    _exact_fields(
        period,
        required={"calendar", "end", "grain", "start"},
        label="period",
    )
    period_start = _iso_date(period["start"], label="period.start")
    period_end = _iso_date(period["end"], label="period.end")
    if period_end < period_start:
        raise FinancialAnalysisContractError("period.end precedes period.start")
    fields = []
    for index, raw_field in enumerate(_sequence(content["fields"], label="fields")):
        label = f"fields[{index}]"
        field = _mapping(raw_field, label=label)
        _exact_fields(
            field,
            required={
                "aggregation",
                "concept_id",
                "currency",
                "data_type",
                "name",
                "nullable",
                "period_role",
                "unit",
            },
            label=label,
        )
        data_type = _text(field["data_type"], label=f"{label}.data_type")
        if data_type not in _DATA_TYPES:
            raise FinancialAnalysisContractError(f"{label}.data_type is unsupported")
        aggregation = _text(field["aggregation"], label=f"{label}.aggregation")
        if aggregation not in _AGGREGATIONS:
            raise FinancialAnalysisContractError(f"{label}.aggregation is unsupported")
        period_role = _text(field["period_role"], label=f"{label}.period_role")
        if period_role not in _PERIOD_ROLES:
            raise FinancialAnalysisContractError(f"{label}.period_role is unsupported")
        if not isinstance(field["nullable"], bool):
            raise FinancialAnalysisContractError(f"{label}.nullable must be boolean")
        currency = field["currency"]
        if currency is not None:
            currency = _identifier(currency, label=f"{label}.currency")
        fields.append(
            {
                "name": _identifier(field["name"], label=f"{label}.name"),
                "concept_id": _identifier(
                    field["concept_id"], label=f"{label}.concept_id"
                ),
                "data_type": data_type,
                "nullable": field["nullable"],
                "unit": _identifier(field["unit"], label=f"{label}.unit"),
                "currency": currency,
                "aggregation": aggregation,
                "period_role": period_role,
            }
        )
    field_names = [item["name"] for item in fields]
    if not fields or len(field_names) != len(set(field_names)):
        raise FinancialAnalysisContractError(
            "fields must be non-empty with unique names"
        )
    keys = _identifier_list(content["keys"], label="keys")
    if not set(keys) <= set(field_names):
        raise FinancialAnalysisContractError("keys reference unknown fields")
    normalized = {
        "schema_version": "vera.dataset_contract.v1",
        "dataset_contract_id": _identifier(
            content["dataset_contract_id"], label="dataset_contract_id"
        ),
        "dataset_id": _identifier(content["dataset_id"], label="dataset_id"),
        "version": _identifier(content["version"], label="version"),
        "review_status": "reviewed",
        "grain": _text(content["grain"], label="grain"),
        "keys": keys,
        "fields": fields,
        "period": {
            "calendar": _identifier(period["calendar"], label="period.calendar"),
            "grain": _identifier(period["grain"], label="period.grain"),
            "start": period_start,
            "end": period_end,
        },
        "source_artifact_refs": _identifier_list(
            content["source_artifact_refs"], label="source_artifact_refs"
        ),
        "limitations": _limitations(content["limitations"]),
    }
    if normalized != content:
        raise FinancialAnalysisContractError("dataset contract is not canonical")
    return _seal(normalized)


def build_dataset_contract(
    *,
    dataset_contract_id: str,
    dataset_id: str,
    version: str,
    grain: str,
    keys: Sequence[str],
    fields: Sequence[Mapping[str, Any]],
    period: Mapping[str, Any],
    source_artifact_refs: Sequence[str],
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Build and seal a reviewed dataset contract."""

    return validate_dataset_contract(
        _seal(
            {
                "schema_version": "vera.dataset_contract.v1",
                "dataset_contract_id": dataset_contract_id,
                "dataset_id": dataset_id,
                "version": version,
                "review_status": "reviewed",
                "grain": grain,
                "keys": list(keys),
                "fields": [dict(item) for item in fields],
                "period": dict(period),
                "source_artifact_refs": list(source_artifact_refs),
                "limitations": list(limitations),
            }
        )
    )


def validate_relationship_contract(value: object) -> dict[str, Any]:
    """Validate a reviewed cross-dataset relationship and join policy."""

    payload = _mapping(value, label="relationship contract")
    content = _sealed_content(
        payload,
        schema_version="vera.dataset_relationship.v1",
        required={
            "cardinality",
            "crosswalk_ref",
            "duplicate_policy",
            "join_type",
            "left_dataset_ref",
            "left_keys",
            "limitations",
            "null_policy",
            "period_alignment",
            "relationship_id",
            "review_status",
            "right_dataset_ref",
            "right_keys",
            "unmatched_policy",
            "version",
        },
        label="relationship contract",
    )
    if content["review_status"] != "reviewed":
        raise FinancialAnalysisContractError(
            "relationship contract must have reviewed status"
        )
    cardinality = _text(content["cardinality"], label="cardinality")
    if cardinality not in _CARDINALITIES:
        raise FinancialAnalysisContractError("unsupported cardinality")
    join_type = _text(content["join_type"], label="join_type")
    if join_type not in _JOIN_TYPES:
        raise FinancialAnalysisContractError("unsupported join_type")
    policies = {}
    for name in ("duplicate_policy", "null_policy", "unmatched_policy"):
        policy = _text(content[name], label=name)
        if policy not in _REVIEW_POLICIES:
            raise FinancialAnalysisContractError(f"unsupported {name}")
        policies[name] = policy
    period_alignment = _text(content["period_alignment"], label="period_alignment")
    if period_alignment not in _PERIOD_ALIGNMENTS:
        raise FinancialAnalysisContractError("unsupported period_alignment")
    left_keys = _identifier_list(content["left_keys"], label="left_keys")
    right_keys = _identifier_list(content["right_keys"], label="right_keys")
    if len(left_keys) != len(right_keys):
        raise FinancialAnalysisContractError(
            "left_keys and right_keys must have equal lengths"
        )
    crosswalk_ref = content["crosswalk_ref"]
    if crosswalk_ref is not None:
        crosswalk_ref = _identifier(crosswalk_ref, label="crosswalk_ref")
    if cardinality == "many_to_many" and crosswalk_ref is None:
        raise FinancialAnalysisContractError(
            "many_to_many relationships require an explicit crosswalk_ref"
        )
    normalized = {
        "schema_version": "vera.dataset_relationship.v1",
        "relationship_id": _identifier(
            content["relationship_id"], label="relationship_id"
        ),
        "version": _identifier(content["version"], label="version"),
        "review_status": "reviewed",
        "left_dataset_ref": _identifier(
            content["left_dataset_ref"], label="left_dataset_ref"
        ),
        "right_dataset_ref": _identifier(
            content["right_dataset_ref"], label="right_dataset_ref"
        ),
        "left_keys": left_keys,
        "right_keys": right_keys,
        "cardinality": cardinality,
        "join_type": join_type,
        "unmatched_policy": policies["unmatched_policy"],
        "null_policy": policies["null_policy"],
        "duplicate_policy": policies["duplicate_policy"],
        "period_alignment": period_alignment,
        "crosswalk_ref": crosswalk_ref,
        "limitations": _limitations(content["limitations"]),
    }
    if normalized != content:
        raise FinancialAnalysisContractError("relationship contract is not canonical")
    return _seal(normalized)


def build_relationship_contract(
    *,
    relationship_id: str,
    version: str,
    left_dataset_ref: str,
    right_dataset_ref: str,
    left_keys: Sequence[str],
    right_keys: Sequence[str],
    cardinality: str,
    join_type: str,
    unmatched_policy: str,
    null_policy: str,
    duplicate_policy: str,
    period_alignment: str,
    crosswalk_ref: str | None = None,
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Build and seal a reviewed dataset-relationship contract."""

    return validate_relationship_contract(
        _seal(
            {
                "schema_version": "vera.dataset_relationship.v1",
                "relationship_id": relationship_id,
                "version": version,
                "review_status": "reviewed",
                "left_dataset_ref": left_dataset_ref,
                "right_dataset_ref": right_dataset_ref,
                "left_keys": list(left_keys),
                "right_keys": list(right_keys),
                "cardinality": cardinality,
                "join_type": join_type,
                "unmatched_policy": unmatched_policy,
                "null_policy": null_policy,
                "duplicate_policy": duplicate_policy,
                "period_alignment": period_alignment,
                "crosswalk_ref": crosswalk_ref,
                "limitations": list(limitations),
            }
        )
    )


def validate_crosswalk_manifest(value: object) -> dict[str, Any]:
    """Validate the receipt and key policy for a reviewed crosswalk asset."""

    payload = _mapping(value, label="crosswalk manifest")
    content = _sealed_content(
        payload,
        schema_version="vera.crosswalk_manifest.v1",
        required={
            "artifact_ref",
            "artifact_sha256",
            "byte_count",
            "crosswalk_id",
            "duplicate_source_policy",
            "mapping_row_count",
            "review_status",
            "source_dataset_ref",
            "source_key_fields",
            "target_dataset_ref",
            "target_key_fields",
            "unmatched_source_policy",
            "version",
        },
        label="crosswalk manifest",
    )
    if content["review_status"] != "reviewed":
        raise FinancialAnalysisContractError(
            "crosswalk manifest must have reviewed status"
        )
    policies = {}
    for name in ("duplicate_source_policy", "unmatched_source_policy"):
        policy = _text(content[name], label=name)
        if policy not in _REVIEW_POLICIES:
            raise FinancialAnalysisContractError(f"unsupported {name}")
        policies[name] = policy
    source_keys = _identifier_list(
        content["source_key_fields"], label="source_key_fields"
    )
    target_keys = _identifier_list(
        content["target_key_fields"], label="target_key_fields"
    )
    if len(source_keys) != len(target_keys):
        raise FinancialAnalysisContractError(
            "source_key_fields and target_key_fields must have equal lengths"
        )
    normalized = {
        "schema_version": "vera.crosswalk_manifest.v1",
        "crosswalk_id": _identifier(content["crosswalk_id"], label="crosswalk_id"),
        "version": _identifier(content["version"], label="version"),
        "review_status": "reviewed",
        "artifact_ref": _identifier(content["artifact_ref"], label="artifact_ref"),
        "artifact_sha256": _sha256(content["artifact_sha256"], label="artifact_sha256"),
        "byte_count": _non_negative_int(content["byte_count"], label="byte_count"),
        "source_dataset_ref": _identifier(
            content["source_dataset_ref"], label="source_dataset_ref"
        ),
        "target_dataset_ref": _identifier(
            content["target_dataset_ref"], label="target_dataset_ref"
        ),
        "source_key_fields": source_keys,
        "target_key_fields": target_keys,
        "mapping_row_count": _non_negative_int(
            content["mapping_row_count"], label="mapping_row_count"
        ),
        "duplicate_source_policy": policies["duplicate_source_policy"],
        "unmatched_source_policy": policies["unmatched_source_policy"],
    }
    if normalized != content:
        raise FinancialAnalysisContractError("crosswalk manifest is not canonical")
    return _seal(normalized)


def build_crosswalk_manifest(
    *,
    crosswalk_id: str,
    version: str,
    artifact_ref: str,
    artifact_sha256: str,
    byte_count: int,
    source_dataset_ref: str,
    target_dataset_ref: str,
    source_key_fields: Sequence[str],
    target_key_fields: Sequence[str],
    mapping_row_count: int,
    duplicate_source_policy: str,
    unmatched_source_policy: str,
) -> dict[str, Any]:
    """Build and seal a reviewed crosswalk manifest."""

    return validate_crosswalk_manifest(
        _seal(
            {
                "schema_version": "vera.crosswalk_manifest.v1",
                "crosswalk_id": crosswalk_id,
                "version": version,
                "review_status": "reviewed",
                "artifact_ref": artifact_ref,
                "artifact_sha256": artifact_sha256,
                "byte_count": byte_count,
                "source_dataset_ref": source_dataset_ref,
                "target_dataset_ref": target_dataset_ref,
                "source_key_fields": list(source_key_fields),
                "target_key_fields": list(target_key_fields),
                "mapping_row_count": mapping_row_count,
                "duplicate_source_policy": duplicate_source_policy,
                "unmatched_source_policy": unmatched_source_policy,
            }
        )
    )


def validate_analysis_pack_request(value: object) -> dict[str, Any]:
    """Validate an explicit request for one registered deterministic pack."""

    payload = _mapping(value, label="analysis pack request")
    content = _sealed_content(
        payload,
        schema_version="vera.analysis_pack_request.v1",
        required={
            "crosswalk_refs",
            "dataset_refs",
            "pack_id",
            "parameters",
            "recipe_version",
            "relationship_refs",
            "request_id",
            "requested_outputs",
            "review_status",
        },
        label="analysis pack request",
    )
    pack_id = _identifier(content["pack_id"], label="pack_id")
    if pack_id not in REGISTERED_ANALYSIS_PACKS:
        raise FinancialAnalysisContractError("analysis pack is not registered")
    if content["review_status"] != "reviewed":
        raise FinancialAnalysisContractError(
            "analysis pack request must have reviewed status"
        )
    parameters = _mapping(content["parameters"], label="parameters")
    canonical_json_sha256(parameters)
    recipe_version = _identifier(content["recipe_version"], label="recipe_version")
    if recipe_version not in REGISTERED_ANALYSIS_PACK_RECIPES[pack_id]:
        raise FinancialAnalysisContractError(
            "analysis recipe version is not registered for the selected pack"
        )
    normalized = {
        "schema_version": "vera.analysis_pack_request.v1",
        "request_id": _identifier(content["request_id"], label="request_id"),
        "pack_id": pack_id,
        "recipe_version": recipe_version,
        "review_status": "reviewed",
        "dataset_refs": _identifier_list(content["dataset_refs"], label="dataset_refs"),
        "relationship_refs": _identifier_list(
            content["relationship_refs"],
            label="relationship_refs",
            allow_empty=True,
        ),
        "crosswalk_refs": _identifier_list(
            content["crosswalk_refs"], label="crosswalk_refs", allow_empty=True
        ),
        "parameters": dict(parameters),
        "requested_outputs": _identifier_list(
            content["requested_outputs"], label="requested_outputs"
        ),
    }
    if normalized != content:
        raise FinancialAnalysisContractError("analysis pack request is not canonical")
    return _seal(normalized)


def build_analysis_pack_request(
    *,
    request_id: str,
    pack_id: str,
    recipe_version: str,
    dataset_refs: Sequence[str],
    relationship_refs: Sequence[str] = (),
    crosswalk_refs: Sequence[str] = (),
    parameters: Mapping[str, Any],
    requested_outputs: Sequence[str],
) -> dict[str, Any]:
    """Build and seal a reviewed request for a registered analysis pack."""

    return validate_analysis_pack_request(
        _seal(
            {
                "schema_version": "vera.analysis_pack_request.v1",
                "request_id": request_id,
                "pack_id": pack_id,
                "recipe_version": recipe_version,
                "review_status": "reviewed",
                "dataset_refs": list(dataset_refs),
                "relationship_refs": list(relationship_refs),
                "crosswalk_refs": list(crosswalk_refs),
                "parameters": dict(parameters),
                "requested_outputs": list(requested_outputs),
            }
        )
    )


def _optional_decimal(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return decimal_text(parse_canonical_decimal(value, label=label))


def validate_reconciliation_result(value: object) -> dict[str, Any]:
    """Validate exact checks, exceptions, and the aggregate result status."""

    payload = _mapping(value, label="reconciliation result")
    content = _sealed_content(
        payload,
        schema_version="vera.reconciliation_result.v1",
        required={
            "checks",
            "exceptions",
            "reconciliation_id",
            "request_ref",
            "status",
        },
        label="reconciliation result",
    )
    status = _text(content["status"], label="status")
    if status not in _RECONCILIATION_STATUSES:
        raise FinancialAnalysisContractError("unsupported reconciliation status")
    checks = []
    for index, raw_check in enumerate(_sequence(content["checks"], label="checks")):
        label = f"checks[{index}]"
        check = _mapping(raw_check, label=label)
        _exact_fields(
            check,
            required={
                "actual",
                "check_id",
                "detail",
                "difference",
                "evidence_refs",
                "expected",
                "required",
                "status",
                "tolerance",
            },
            label=label,
        )
        check_status = _text(check["status"], label=f"{label}.status")
        if check_status not in _CHECK_STATUSES:
            raise FinancialAnalysisContractError(f"{label}.status is unsupported")
        if not isinstance(check["required"], bool):
            raise FinancialAnalysisContractError(f"{label}.required must be boolean")
        expected = _optional_decimal(check["expected"], label=f"{label}.expected")
        actual = _optional_decimal(check["actual"], label=f"{label}.actual")
        difference = _optional_decimal(check["difference"], label=f"{label}.difference")
        tolerance = _optional_decimal(check["tolerance"], label=f"{label}.tolerance")
        numeric_values = (expected, actual, difference, tolerance)
        if any(item is None for item in numeric_values) and any(
            item is not None for item in numeric_values
        ):
            raise FinancialAnalysisContractError(
                f"{label} numeric evidence must be complete or absent"
            )
        if expected is not None:
            calculated = parse_canonical_decimal(actual) - parse_canonical_decimal(
                expected
            )
            if decimal_text(calculated) != difference:
                raise FinancialAnalysisContractError(f"{label}.difference is stale")
            within_tolerance = abs(calculated) <= parse_canonical_decimal(tolerance)
            if check_status == "passed" and not within_tolerance:
                raise FinancialAnalysisContractError(
                    f"{label} cannot pass outside tolerance"
                )
            if check_status == "failed" and within_tolerance:
                raise FinancialAnalysisContractError(
                    f"{label} cannot fail within tolerance"
                )
        checks.append(
            {
                "check_id": _identifier(check["check_id"], label=f"{label}.check_id"),
                "required": check["required"],
                "status": check_status,
                "expected": expected,
                "actual": actual,
                "difference": difference,
                "tolerance": tolerance,
                "evidence_refs": _identifier_list(
                    check["evidence_refs"],
                    label=f"{label}.evidence_refs",
                    allow_empty=check_status == "not_applicable",
                ),
                "detail": _text(
                    check["detail"], label=f"{label}.detail", allow_empty=True
                ),
            }
        )
    check_ids = [item["check_id"] for item in checks]
    if not checks or len(check_ids) != len(set(check_ids)):
        raise FinancialAnalysisContractError(
            "checks must be non-empty with unique check_id values"
        )
    exceptions = []
    for index, raw_exception in enumerate(
        _sequence(content["exceptions"], label="exceptions")
    ):
        label = f"exceptions[{index}]"
        exception = _mapping(raw_exception, label=label)
        _exact_fields(
            exception,
            required={"detail", "evidence_refs", "exception_id", "severity"},
            label=label,
        )
        severity = _text(exception["severity"], label=f"{label}.severity")
        if severity not in _EXCEPTION_SEVERITIES:
            raise FinancialAnalysisContractError(f"{label}.severity is unsupported")
        exceptions.append(
            {
                "exception_id": _identifier(
                    exception["exception_id"], label=f"{label}.exception_id"
                ),
                "severity": severity,
                "evidence_refs": _identifier_list(
                    exception["evidence_refs"],
                    label=f"{label}.evidence_refs",
                ),
                "detail": _text(exception["detail"], label=f"{label}.detail"),
            }
        )
    exception_ids = [item["exception_id"] for item in exceptions]
    if len(exception_ids) != len(set(exception_ids)):
        raise FinancialAnalysisContractError(
            "exceptions must have unique exception_id values"
        )
    required_statuses = {item["status"] for item in checks if item["required"]}
    has_blocking = any(item["severity"] == "blocking" for item in exceptions)
    if status == "passed" and (
        required_statuses - {"passed", "not_applicable"} or has_blocking
    ):
        raise FinancialAnalysisContractError(
            "passed reconciliation has unresolved required evidence"
        )
    if status == "failed" and "failed" not in required_statuses and not has_blocking:
        raise FinancialAnalysisContractError(
            "failed reconciliation requires a required failure or blocking exception"
        )
    if status == "qualified" and (
        "failed" in required_statuses
        or (
            "qualified" not in required_statuses
            and not any(item["severity"] == "warning" for item in exceptions)
        )
    ):
        raise FinancialAnalysisContractError(
            "qualified reconciliation requires a qualification without failure"
        )
    if status == "not_applicable" and required_statuses != {"not_applicable"}:
        raise FinancialAnalysisContractError(
            "not_applicable reconciliation requires every required check to be not_applicable"
        )
    normalized = {
        "schema_version": "vera.reconciliation_result.v1",
        "reconciliation_id": _identifier(
            content["reconciliation_id"], label="reconciliation_id"
        ),
        "request_ref": _identifier(content["request_ref"], label="request_ref"),
        "status": status,
        "checks": checks,
        "exceptions": exceptions,
    }
    if normalized != content:
        raise FinancialAnalysisContractError("reconciliation result is not canonical")
    return _seal(normalized)


def build_reconciliation_result(
    *,
    reconciliation_id: str,
    request_ref: str,
    status: str,
    checks: Sequence[Mapping[str, Any]],
    exceptions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build and seal a reconciliation result."""

    return validate_reconciliation_result(
        _seal(
            {
                "schema_version": "vera.reconciliation_result.v1",
                "reconciliation_id": reconciliation_id,
                "request_ref": request_ref,
                "status": status,
                "checks": [dict(item) for item in checks],
                "exceptions": [dict(item) for item in exceptions],
            }
        )
    )


def validate_prepared_evidence_manifest(value: object) -> dict[str, Any]:
    """Validate a reproducible prepared-output set and its contract bindings."""

    payload = _mapping(value, label="prepared evidence manifest")
    content = _sealed_content(
        payload,
        schema_version="vera.prepared_evidence_manifest.v1",
        required={
            "crosswalk_refs",
            "dataset_contract_refs",
            "input_artifact_refs",
            "manifest_id",
            "output_artifacts",
            "package_ref",
            "preparation_status",
            "recipe",
            "reconciliation_ref",
            "relationship_contract_refs",
            "replay",
            "report_ready",
            "request_ref",
        },
        label="prepared evidence manifest",
    )
    status = _text(content["preparation_status"], label="preparation_status")
    if status not in _PREPARATION_STATUSES:
        raise FinancialAnalysisContractError("unsupported preparation_status")
    if content["report_ready"] is not False:
        raise FinancialAnalysisContractError(
            "prepared evidence alone cannot establish report readiness"
        )
    recipe = _mapping(content["recipe"], label="recipe")
    _exact_fields(
        recipe,
        required={
            "implementation_refs",
            "pack_id",
            "parameters_sha256",
            "version",
        },
        label="recipe",
    )
    pack_id = _identifier(recipe["pack_id"], label="recipe.pack_id")
    if pack_id not in REGISTERED_ANALYSIS_PACKS:
        raise FinancialAnalysisContractError("recipe pack is not registered")
    recipe_version = _identifier(recipe["version"], label="recipe.version")
    if recipe_version not in REGISTERED_ANALYSIS_PACK_RECIPES[pack_id]:
        raise FinancialAnalysisContractError(
            "prepared recipe version is not registered for the selected pack"
        )
    replay = _mapping(content["replay"], label="replay")
    _exact_fields(
        replay,
        required={"output_set_sha256", "status"},
        label="replay",
    )
    replay_status = _text(replay["status"], label="replay.status")
    if replay_status not in {"failed", "passed"}:
        raise FinancialAnalysisContractError("unsupported replay.status")
    if status == "passed" and replay_status != "passed":
        raise FinancialAnalysisContractError(
            "passed preparation requires passed deterministic replay"
        )
    outputs = []
    for index, raw_output in enumerate(
        _sequence(content["output_artifacts"], label="output_artifacts")
    ):
        label = f"output_artifacts[{index}]"
        output = _mapping(raw_output, label=label)
        _exact_fields(
            output,
            required={
                "artifact_ref",
                "byte_count",
                "role",
                "row_count",
                "sha256",
            },
            label=label,
        )
        outputs.append(
            {
                "artifact_ref": _identifier(
                    output["artifact_ref"], label=f"{label}.artifact_ref"
                ),
                "role": _identifier(output["role"], label=f"{label}.role"),
                "row_count": _non_negative_int(
                    output["row_count"], label=f"{label}.row_count"
                ),
                "byte_count": _non_negative_int(
                    output["byte_count"], label=f"{label}.byte_count"
                ),
                "sha256": _sha256(output["sha256"], label=f"{label}.sha256"),
            }
        )
    output_refs = [item["artifact_ref"] for item in outputs]
    if status == "passed" and not outputs:
        raise FinancialAnalysisContractError(
            "passed preparation requires output artifacts"
        )
    if len(output_refs) != len(set(output_refs)):
        raise FinancialAnalysisContractError(
            "output_artifacts must have unique artifact_ref values"
        )
    normalized = {
        "schema_version": "vera.prepared_evidence_manifest.v1",
        "manifest_id": _identifier(content["manifest_id"], label="manifest_id"),
        "request_ref": _identifier(content["request_ref"], label="request_ref"),
        "package_ref": _identifier(content["package_ref"], label="package_ref"),
        "dataset_contract_refs": _identifier_list(
            content["dataset_contract_refs"], label="dataset_contract_refs"
        ),
        "relationship_contract_refs": _identifier_list(
            content["relationship_contract_refs"],
            label="relationship_contract_refs",
            allow_empty=True,
        ),
        "crosswalk_refs": _identifier_list(
            content["crosswalk_refs"], label="crosswalk_refs", allow_empty=True
        ),
        "input_artifact_refs": _identifier_list(
            content["input_artifact_refs"], label="input_artifact_refs"
        ),
        "recipe": {
            "pack_id": pack_id,
            "version": recipe_version,
            "implementation_refs": _identifier_list(
                recipe["implementation_refs"],
                label="recipe.implementation_refs",
            ),
            "parameters_sha256": _sha256(
                recipe["parameters_sha256"], label="recipe.parameters_sha256"
            ),
        },
        "reconciliation_ref": _identifier(
            content["reconciliation_ref"], label="reconciliation_ref"
        ),
        "preparation_status": status,
        "output_artifacts": outputs,
        "replay": {
            "status": replay_status,
            "output_set_sha256": _sha256(
                replay["output_set_sha256"], label="replay.output_set_sha256"
            ),
        },
        "report_ready": False,
    }
    if normalized != content:
        raise FinancialAnalysisContractError(
            "prepared evidence manifest is not canonical"
        )
    return _seal(normalized)


def build_prepared_evidence_manifest(
    *,
    manifest_id: str,
    request_ref: str,
    package_ref: str,
    dataset_contract_refs: Sequence[str],
    relationship_contract_refs: Sequence[str],
    crosswalk_refs: Sequence[str],
    input_artifact_refs: Sequence[str],
    recipe: Mapping[str, Any],
    reconciliation_ref: str,
    preparation_status: str,
    output_artifacts: Sequence[Mapping[str, Any]],
    replay: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and seal a prepared-evidence manifest."""

    return validate_prepared_evidence_manifest(
        _seal(
            {
                "schema_version": "vera.prepared_evidence_manifest.v1",
                "manifest_id": manifest_id,
                "request_ref": request_ref,
                "package_ref": package_ref,
                "dataset_contract_refs": list(dataset_contract_refs),
                "relationship_contract_refs": list(relationship_contract_refs),
                "crosswalk_refs": list(crosswalk_refs),
                "input_artifact_refs": list(input_artifact_refs),
                "recipe": dict(recipe),
                "reconciliation_ref": reconciliation_ref,
                "preparation_status": preparation_status,
                "output_artifacts": [dict(item) for item in output_artifacts],
                "replay": dict(replay),
                "report_ready": False,
            }
        )
    )
