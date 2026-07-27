#!/usr/bin/env python3
"""Validate a producer-owned mechanical error register for the M6 pilot.

The register contains only registered mechanical classes, opaque check/code
IDs, closed output-receipt references, and derived counts. It deliberately
contains no error prose, semantic findings, row identifiers, labels, or
amounts. A producer assigns a fixed class at the exact gate where an error is
detected; this generic validator checks that declaration but never infers a
class.

Receipt closure is deterministic because exact paths, bytes, hashes, and
cross-run identities are mechanically verifiable. To avoid an impossible
self-hash cycle, the closure digest preserves the ``mechanical_errors`` role
and relative path but omits only that self receipt's byte count and SHA-256.
The full replay-validated self receipt must still resolve to the exact register
path and match its current bytes. Every non-self receipt is fully byte-bound.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from preparation_contract_kernel import (
    ContractValidationError,
    canonical_json_sha256,
    strict_json_snapshot_beneath,
)
from real_data_pilot_output_boundary import validate_pilot_output_receipts
from validate_real_data_pilot_intake import (
    PILOT_ID_PATTERN,
    resolve_pilot_storage_roots,
    validate_pilot_receipt_output_path,
)

__all__ = [
    "BINDING_FIELDS",
    "EXECUTION_ID_PATTERN",
    "MECHANICAL_CLASSES",
    "MECHANICAL_ERROR_REGISTER_SCHEMA",
    "output_receipt_closure_sha256",
    "validate_real_data_pilot_mechanical_error_register",
    "validate_real_data_pilot_mechanical_error_register_value",
]

MECHANICAL_ERROR_REGISTER_SCHEMA = "clara.real_data_pilot_mechanical_error_register.v1"
EXECUTION_ID_PATTERN = re.compile(r"^execution-[0-9a-f]{16}$")
CHECK_ID_PATTERN = re.compile(r"^check-[0-9a-f]{16}$")
ERROR_ID_PATTERN = re.compile(r"^error-[0-9a-f]{16}$")
ERROR_CODE_PATTERN = re.compile(r"^code-[0-9a-f]{16}$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CHECK_STATUSES = frozenset({"failed", "not_run", "passed"})
MECHANICAL_ERROR_ROLE = "mechanical_errors"
OUTPUT_RECEIPT_FIELDS = frozenset(
    {
        "role",
        "relative_path",
        "byte_count",
        "sha256",
    }
)
MECHANICAL_CLASSES = (
    "contract",
    "mapping_execution",
    "numeric",
    "output_integrity",
    "period",
    "reconciliation",
    "replay",
    "source_structure",
    "storage",
)
BINDING_FIELDS = frozenset(
    {
        "case_contract_sha256",
        "intake_receipt_sha256",
        "output_receipt_closure_sha256",
        "producer_contract_sha256",
        "producer_implementation_sha256",
        "semantic_review_receipt_sha256",
    }
)
LIMITATIONS = (
    "error_completeness_not_established",
    "identifier_nonidentifiability_not_established",
    "mechanical_classification_is_producer_declared_at_registered_gate",
    "producer_quiescence_not_mechanically_established",
    "publication_not_authorized",
    "report_readiness_not_established",
    "semantic_correctness_not_assessed",
)
TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "pilot_id",
        "execution_id",
        "bindings",
        "check_registry",
        "error_registry",
        "summary",
        "content_policy",
        "publication_status",
        "report_ready",
        "limitations",
    }
)


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContractValidationError(f"{label} must be a list")
    return list(value)


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ContractValidationError(
            f"{label} must be canonical non-empty text without edge whitespace"
        )
    return value


def _identifier(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if ID_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a canonical identifier")
    return result


def _opaque_identifier(
    value: Any,
    *,
    pattern: re.Pattern[str],
    label: str,
) -> str:
    result = _text(value, label=label)
    if pattern.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be an opaque digest-shaped ID")
    return result


def _sha256(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if SHA256_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a lowercase SHA-256 digest")
    return result


def _exact_fields(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    label: str,
) -> None:
    missing = sorted(required - set(value))
    unexpected = sorted(set(value) - required)
    if missing:
        raise ContractValidationError(f"{label} is missing fields: {missing}")
    if unexpected:
        raise ContractValidationError(
            f"{label} contains unexpected fields: {unexpected}"
        )


def _require_constant(value: Any, *, expected: Any, label: str) -> None:
    if type(value) is not type(expected) or value != expected:
        raise ContractValidationError(f"{label} must equal {expected!r}")


def _sorted_unique_identifiers(value: Any, *, label: str) -> list[str]:
    identifiers = [
        _identifier(item, label=f"{label}[]") for item in _sequence(value, label=label)
    ]
    if identifiers != sorted(set(identifiers)):
        raise ContractValidationError(f"{label} must be sorted and unique")
    return identifiers


def _sorted_unique_opaque_identifiers(
    value: Any,
    *,
    pattern: re.Pattern[str],
    label: str,
) -> list[str]:
    identifiers = [
        _opaque_identifier(
            item,
            pattern=pattern,
            label=f"{label}[]",
        )
        for item in _sequence(value, label=label)
    ]
    if not identifiers or identifiers != sorted(set(identifiers)):
        raise ContractValidationError(f"{label} must be non-empty, sorted, and unique")
    return identifiers


def _nonnegative_integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractValidationError(f"{label} must be a nonnegative integer")
    return value


def _validate_bindings(
    value: Any,
    *,
    expected_bindings: Mapping[str, str],
) -> dict[str, str]:
    bindings = _mapping(value, label="mechanical register.bindings")
    _exact_fields(
        bindings,
        required=BINDING_FIELDS,
        label="mechanical register.bindings",
    )
    if set(expected_bindings) != set(BINDING_FIELDS):
        raise ContractValidationError(
            "expected_bindings must contain the registered binding fields"
        )
    validated: dict[str, str] = {}
    for field in sorted(BINDING_FIELDS):
        digest = _sha256(
            bindings[field],
            label=f"mechanical register.bindings.{field}",
        )
        expected_digest = _sha256(
            expected_bindings[field],
            label=f"expected_bindings.{field}",
        )
        if digest != expected_digest:
            raise ContractValidationError(
                f"mechanical register.bindings.{field} does not match"
            )
        validated[field] = digest
    return validated


def _normalize_output_receipts(value: Any) -> list[dict[str, Any]]:
    receipts = _sequence(value, label="output receipts")
    if not receipts:
        raise ContractValidationError("output receipts must not be empty")
    normalized: list[dict[str, Any]] = []
    for position, raw_receipt in enumerate(receipts):
        label = f"output receipts[{position}]"
        receipt = _mapping(raw_receipt, label=label)
        _exact_fields(
            receipt,
            required=OUTPUT_RECEIPT_FIELDS,
            label=label,
        )
        role = _identifier(receipt["role"], label=f"{label}.role")
        relative_path = _text(
            receipt["relative_path"],
            label=f"{label}.relative_path",
        )
        byte_count = _nonnegative_integer(
            receipt["byte_count"],
            label=f"{label}.byte_count",
        )
        digest = _sha256(receipt["sha256"], label=f"{label}.sha256")
        normalized.append(
            {
                "role": role,
                "relative_path": relative_path,
                "byte_count": byte_count,
                "sha256": digest,
            }
        )
    roles = [receipt["role"] for receipt in normalized]
    if roles != sorted(set(roles)):
        raise ContractValidationError("output receipts must be sorted by unique role")
    if roles.count(MECHANICAL_ERROR_ROLE) != 1:
        raise ContractValidationError(
            "output receipts must contain exactly one mechanical_errors receipt"
        )
    return normalized


def output_receipt_closure_sha256(value: Any) -> str:
    """Hash exact output receipts using one explicit non-circular projection.

    Every non-self receipt contributes all four fields. The sole
    ``mechanical_errors`` self receipt contributes only its role and relative
    path; full self bytes are checked separately against the exact register
    snapshot by the authoritative validator.
    """

    receipts = _normalize_output_receipts(value)
    projection = [
        (
            {
                "role": receipt["role"],
                "relative_path": receipt["relative_path"],
            }
            if receipt["role"] == MECHANICAL_ERROR_ROLE
            else receipt
        )
        for receipt in receipts
    ]
    return canonical_json_sha256(projection)


def _validate_output_receipt_closure(
    *,
    register_path: Path,
    register_byte_count: int,
    register_sha256: str,
    output_receipts: Any,
    output_directory: Path,
    local_run_root: Path,
    repository_root: Path,
) -> tuple[list[dict[str, Any]], set[str], str]:
    validated_receipts = validate_pilot_output_receipts(
        output_receipts,
        output_directory,
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    receipts = _normalize_output_receipts(validated_receipts)
    self_receipt = next(
        receipt for receipt in receipts if receipt["role"] == MECHANICAL_ERROR_ROLE
    )
    expected_self_path = (
        Path(output_directory).resolve() / self_receipt["relative_path"]
    ).resolve()
    if expected_self_path != Path(register_path).resolve():
        raise ContractValidationError(
            "mechanical_errors receipt must point to the exact register path"
        )
    expected_byte_count = _nonnegative_integer(
        register_byte_count,
        label="register_byte_count",
    )
    expected_digest = _sha256(register_sha256, label="register_sha256")
    if (
        self_receipt["byte_count"] != expected_byte_count
        or self_receipt["sha256"] != expected_digest
    ):
        raise ContractValidationError(
            "mechanical_errors receipt must match the exact register snapshot"
        )
    roles = {receipt["role"] for receipt in receipts}
    return receipts, roles, output_receipt_closure_sha256(receipts)


def _validated_register_storage(
    register_path: Path,
    *,
    output_directory: Path,
    local_run_root: Path,
    repository_root: Path,
) -> tuple[Path, Path, Path, Path]:
    run_root, repo_root = resolve_pilot_storage_roots(
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    output_path, _ = validate_pilot_receipt_output_path(
        output_directory,
        declared_local_run_root=local_run_root,
        local_run_root=run_root,
        repository_root=repo_root,
        label="producer output directory",
    )
    if output_path == run_root or not output_path.is_dir():
        raise ContractValidationError(
            "producer output directory must be one existing dedicated leaf"
        )
    validated_register_path, _ = validate_pilot_receipt_output_path(
        register_path,
        declared_local_run_root=output_path,
        local_run_root=run_root,
        repository_root=repo_root,
        label="mechanical register path",
    )
    if validated_register_path != output_path / "mechanical_errors.json":
        raise ContractValidationError(
            "mechanical register must use the registered output path"
        )
    return validated_register_path, output_path, run_root, repo_root


def _validate_artifact_refs(
    value: Any,
    *,
    available_roles: set[str],
    label: str,
) -> list[str]:
    refs = _sorted_unique_identifiers(value, label=label)
    unresolved = sorted(set(refs) - available_roles)
    if unresolved:
        raise ContractValidationError(
            f"{label} contains unresolved artifact roles: {unresolved}"
        )
    return refs


def _validate_checks(
    value: Any,
    *,
    available_roles: set[str],
) -> dict[str, dict[str, Any]]:
    registry = _mapping(value, label="mechanical register.check_registry")
    if not registry:
        raise ContractValidationError(
            "mechanical register.check_registry must not be empty"
        )
    checks: dict[str, dict[str, Any]] = {}
    for raw_check_id, raw_check in registry.items():
        check_id = _opaque_identifier(
            raw_check_id,
            pattern=CHECK_ID_PATTERN,
            label="mechanical register.check_registry key",
        )
        label = f"mechanical register.check_registry.{check_id}"
        check = _mapping(raw_check, label=label)
        _exact_fields(
            check,
            required=frozenset(
                {
                    "mechanical_class",
                    "error_codes",
                    "status",
                    "artifact_refs",
                }
            ),
            label=label,
        )
        mechanical_class = _text(
            check["mechanical_class"],
            label=f"{label}.mechanical_class",
        )
        if mechanical_class not in MECHANICAL_CLASSES:
            raise ContractValidationError(f"{label}.mechanical_class is not registered")
        error_codes = _sorted_unique_opaque_identifiers(
            check["error_codes"],
            pattern=ERROR_CODE_PATTERN,
            label=f"{label}.error_codes",
        )
        status = _text(check["status"], label=f"{label}.status")
        if status not in CHECK_STATUSES:
            raise ContractValidationError(f"{label}.status is not registered")
        artifact_refs = _validate_artifact_refs(
            check["artifact_refs"],
            available_roles=available_roles,
            label=f"{label}.artifact_refs",
        )
        checks[check_id] = {
            "mechanical_class": mechanical_class,
            "error_codes": error_codes,
            "status": status,
            "artifact_refs": artifact_refs,
        }
    return checks


def _validate_errors(
    value: Any,
    *,
    checks: Mapping[str, Mapping[str, Any]],
    available_roles: set[str],
) -> dict[str, dict[str, Any]]:
    registry = _mapping(value, label="mechanical register.error_registry")
    errors: dict[str, dict[str, Any]] = {}
    for raw_error_id, raw_error in registry.items():
        error_id = _opaque_identifier(
            raw_error_id,
            pattern=ERROR_ID_PATTERN,
            label="mechanical register.error_registry key",
        )
        label = f"mechanical register.error_registry.{error_id}"
        error = _mapping(raw_error, label=label)
        _exact_fields(
            error,
            required=frozenset(
                {
                    "check_id",
                    "error_code",
                    "mechanical_class",
                    "artifact_refs",
                }
            ),
            label=label,
        )
        check_id = _opaque_identifier(
            error["check_id"],
            pattern=CHECK_ID_PATTERN,
            label=f"{label}.check_id",
        )
        if check_id not in checks:
            raise ContractValidationError(
                f"{label}.check_id does not resolve to a registered check"
            )
        check = checks[check_id]
        error_code = _opaque_identifier(
            error["error_code"],
            pattern=ERROR_CODE_PATTERN,
            label=f"{label}.error_code",
        )
        mechanical_class = _text(
            error["mechanical_class"],
            label=f"{label}.mechanical_class",
        )
        if error_code not in check["error_codes"]:
            raise ContractValidationError(
                f"{label}.error_code is not registered for its check"
            )
        if mechanical_class != check["mechanical_class"]:
            raise ContractValidationError(
                f"{label}.mechanical_class does not match its registered check"
            )
        artifact_refs = _validate_artifact_refs(
            error["artifact_refs"],
            available_roles=available_roles,
            label=f"{label}.artifact_refs",
        )
        if not set(artifact_refs).issubset(set(check["artifact_refs"])):
            raise ContractValidationError(
                f"{label}.artifact_refs must be declared by its registered check"
            )
        errors[error_id] = {
            "check_id": check_id,
            "error_code": error_code,
            "mechanical_class": mechanical_class,
            "artifact_refs": artifact_refs,
        }
    return errors


def _derived_summary(
    checks: Mapping[str, Mapping[str, Any]],
    errors: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    errors_by_check = {
        check_id: sum(1 for error in errors.values() if error["check_id"] == check_id)
        for check_id in checks
    }
    for check_id, check in checks.items():
        error_count = errors_by_check[check_id]
        if check["status"] == "failed" and error_count == 0:
            raise ContractValidationError(
                f"failed check {check_id!r} must have at least one error"
            )
        if check["status"] != "failed" and error_count != 0:
            raise ContractValidationError(
                f"non-failed check {check_id!r} must not have errors"
            )

    check_counts = {
        status: sum(1 for check in checks.values() if check["status"] == status)
        for status in ("passed", "failed", "not_run")
    }
    class_counts = {
        mechanical_class: sum(
            1
            for error in errors.values()
            if error["mechanical_class"] == mechanical_class
        )
        for mechanical_class in MECHANICAL_CLASSES
    }
    if check_counts["failed"] > 0:
        overall_status = "failed"
    elif check_counts["not_run"] > 0:
        overall_status = "incomplete"
    else:
        overall_status = "passed"
    return {
        "overall_status": overall_status,
        "check_counts": check_counts,
        "error_count": len(errors),
        "class_counts": class_counts,
    }


def _validate_summary(value: Any, *, expected: Mapping[str, Any]) -> None:
    summary = _mapping(value, label="mechanical register.summary")
    _exact_fields(
        summary,
        required=frozenset(
            {
                "overall_status",
                "check_counts",
                "error_count",
                "class_counts",
            }
        ),
        label="mechanical register.summary",
    )
    _require_constant(
        summary["overall_status"],
        expected=expected["overall_status"],
        label="mechanical register.summary.overall_status",
    )
    _require_constant(
        _nonnegative_integer(
            summary["error_count"],
            label="mechanical register.summary.error_count",
        ),
        expected=expected["error_count"],
        label="mechanical register.summary.error_count",
    )
    for field, registered_values in (
        ("check_counts", ("passed", "failed", "not_run")),
        ("class_counts", MECHANICAL_CLASSES),
    ):
        counts = _mapping(
            summary[field],
            label=f"mechanical register.summary.{field}",
        )
        _exact_fields(
            counts,
            required=frozenset(registered_values),
            label=f"mechanical register.summary.{field}",
        )
        for key in registered_values:
            actual = _nonnegative_integer(
                counts[key],
                label=f"mechanical register.summary.{field}.{key}",
            )
            _require_constant(
                actual,
                expected=expected[field][key],
                label=f"mechanical register.summary.{field}.{key}",
            )


def validate_real_data_pilot_mechanical_error_register(
    register_path: Path,
    *,
    expected_pilot_id: str,
    expected_execution_id: str,
    expected_bindings: Mapping[str, str],
    output_receipts: Any,
    output_directory: Path,
    local_run_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate one register against its exact current output-receipt closure."""

    register_path, output_path, run_root, repo_root = _validated_register_storage(
        register_path,
        output_directory=output_directory,
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    if not register_path.is_file():
        raise ContractValidationError(
            "mechanical register path must identify one existing file"
        )
    register, byte_count, digest = strict_json_snapshot_beneath(
        register_path,
        root=run_root,
    )
    return validate_real_data_pilot_mechanical_error_register_value(
        register,
        register_path=register_path,
        register_byte_count=byte_count,
        register_sha256=digest,
        expected_pilot_id=expected_pilot_id,
        expected_execution_id=expected_execution_id,
        expected_bindings=expected_bindings,
        output_receipts=output_receipts,
        output_directory=output_path,
        local_run_root=run_root,
        repository_root=repo_root,
    )


def validate_real_data_pilot_mechanical_error_register_value(
    value: Any,
    *,
    register_path: Path,
    register_byte_count: int,
    register_sha256: str,
    expected_pilot_id: str,
    expected_execution_id: str,
    expected_bindings: Mapping[str, str],
    output_receipts: Any,
    output_directory: Path,
    local_run_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate one captured register and the exact replayed output receipts."""

    register_path, output_path, run_root, repo_root = _validated_register_storage(
        register_path,
        output_directory=output_directory,
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    register = _mapping(value, label="mechanical register")
    current_register, current_byte_count, current_sha256 = strict_json_snapshot_beneath(
        register_path,
        root=run_root,
    )
    _require_constant(
        current_register,
        expected=dict(register),
        label="mechanical register snapshot value",
    )
    _require_constant(
        _nonnegative_integer(
            register_byte_count,
            label="register_byte_count",
        ),
        expected=current_byte_count,
        label="register_byte_count",
    )
    _require_constant(
        _sha256(register_sha256, label="register_sha256"),
        expected=current_sha256,
        label="register_sha256",
    )
    _exact_fields(
        register,
        required=TOP_LEVEL_FIELDS,
        label="mechanical register",
    )
    _require_constant(
        register["schema_version"],
        expected=MECHANICAL_ERROR_REGISTER_SCHEMA,
        label="mechanical register.schema_version",
    )
    pilot_id = _opaque_identifier(
        register["pilot_id"],
        pattern=PILOT_ID_PATTERN,
        label="mechanical register.pilot_id",
    )
    expected_pilot = _opaque_identifier(
        expected_pilot_id,
        pattern=PILOT_ID_PATTERN,
        label="expected_pilot_id",
    )
    _require_constant(
        pilot_id,
        expected=expected_pilot,
        label="mechanical register.pilot_id",
    )
    execution_id = _opaque_identifier(
        register["execution_id"],
        pattern=EXECUTION_ID_PATTERN,
        label="mechanical register.execution_id",
    )
    expected_execution = _opaque_identifier(
        expected_execution_id,
        pattern=EXECUTION_ID_PATTERN,
        label="expected_execution_id",
    )
    _require_constant(
        execution_id,
        expected=expected_execution,
        label="mechanical register.execution_id",
    )
    bindings = _validate_bindings(
        register["bindings"],
        expected_bindings=expected_bindings,
    )
    _receipts, available_roles, closure_digest = _validate_output_receipt_closure(
        register_path=register_path,
        register_byte_count=register_byte_count,
        register_sha256=register_sha256,
        output_receipts=output_receipts,
        output_directory=output_path,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    if bindings["output_receipt_closure_sha256"] != closure_digest:
        raise ContractValidationError(
            "mechanical register output-receipt closure digest does not match"
        )
    checks = _validate_checks(
        register["check_registry"],
        available_roles=available_roles,
    )
    errors = _validate_errors(
        register["error_registry"],
        checks=checks,
        available_roles=available_roles,
    )
    derived_summary = _derived_summary(checks, errors)
    _validate_summary(register["summary"], expected=derived_summary)

    content_policy = _mapping(
        register["content_policy"],
        label="mechanical register.content_policy",
    )
    _exact_fields(
        content_policy,
        required=frozenset(
            {
                "error_messages_in_register",
                "row_level_values_in_register",
                "semantic_findings_in_register",
            }
        ),
        label="mechanical register.content_policy",
    )
    for field in (
        "error_messages_in_register",
        "row_level_values_in_register",
        "semantic_findings_in_register",
    ):
        _require_constant(
            content_policy[field],
            expected=False,
            label=f"mechanical register.content_policy.{field}",
        )
    _require_constant(
        register["publication_status"],
        expected="withheld",
        label="mechanical register.publication_status",
    )
    _require_constant(
        register["report_ready"],
        expected=False,
        label="mechanical register.report_ready",
    )
    _require_constant(
        _sequence(register["limitations"], label="mechanical register.limitations"),
        expected=list(LIMITATIONS),
        label="mechanical register.limitations",
    )
    return dict(register)
