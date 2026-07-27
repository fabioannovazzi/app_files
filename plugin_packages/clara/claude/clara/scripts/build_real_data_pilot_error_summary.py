#!/usr/bin/env python3
"""Build a retention-reviewed, sanitized M6 mechanical error summary.

The workflow is deliberately two phase. First, deterministic code derives a
canonical, path-free candidate from a fully replay-validated mechanical
register. A local declaration then records approval of that exact candidate
digest. Finally, this module emits a retained receipt that embeds the declared
candidate and binds the local declaration by digest.

Reviewer role, basis, paths, messages, labels, row identifiers, amounts, and
semantic findings remain in local artifacts and are never copied into the
retained receipt.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from preparation_contract_kernel import (
    ContractValidationError,
    canonical_json_sha256,
    file_sha256,
    strict_json_snapshot_beneath,
)
from validate_real_data_pilot_intake import (
    PILOT_ID_PATTERN,
    resolve_pilot_storage_roots,
    validate_pilot_local_run_path,
)
from validate_real_data_pilot_mechanical_errors import (
    BINDING_FIELDS,
    EXECUTION_ID_PATTERN,
    MECHANICAL_CLASSES,
    validate_real_data_pilot_mechanical_error_register_value,
)

__all__ = [
    "RETENTION_APPROVAL_SCHEMA",
    "SANITIZED_CANDIDATE_SCHEMA",
    "SANITIZED_SUMMARY_SCHEMA",
    "build_real_data_pilot_sanitized_error_summary",
    "build_real_data_pilot_sanitized_error_summary_candidate",
    "validate_real_data_pilot_sanitized_error_summary",
    "validate_real_data_pilot_sanitized_error_summary_candidate",
]

RETENTION_APPROVAL_SCHEMA = "clara.real_data_pilot_retention_approval.v1"
SANITIZED_CANDIDATE_SCHEMA = (
    "clara.real_data_pilot_sanitized_error_class_summary_candidate.v1"
)
SANITIZED_SUMMARY_SCHEMA = "clara.real_data_pilot_sanitized_error_class_summary.v1"
RETENTION_REVIEW_VERSION_PATTERN = re.compile(r"^retention-review-[0-9a-f]{16}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VALIDATOR_ID = "real_data_pilot_sanitized_error_summary_validator.v1"
VALIDATOR_VERSION = "1.0.0"
PROHIBITED_CONTENT = (
    "account_or_entity_labels",
    "amounts",
    "error_messages_or_descriptions",
    "file_paths",
    "row_identifiers",
    "reversible_identifier_encodings",
    "semantic_findings",
)
DOES_NOT_ESTABLISH = (
    "accounting_semantic_correctness",
    "approval_or_review_authenticity",
    "error_completeness",
    "future_storage_or_copy_behavior",
    "identifier_nonidentifiability_or_anonymization",
    "mechanical_classification_correctness",
    "publication_authorization",
    "report_readiness",
    "reviewer_identity_or_authority",
    "unlinkability",
)
CANDIDATE_CONTENT_POLICY = {
    "free_text_in_candidate": False,
    "paths_in_candidate": False,
    "row_level_values_in_candidate": False,
    "semantic_findings_in_candidate": False,
}
CANDIDATE_FIELDS = frozenset(
    {
        "schema_version",
        "pilot_id",
        "execution_id",
        "mechanical_register_sha256",
        "bindings",
        "mechanical_status",
        "check_counts",
        "error_count",
        "class_counts",
        "content_policy",
        "publication_status",
        "report_ready",
        "does_not_establish",
    }
)
SUMMARY_FIELDS = frozenset(
    {
        "schema_version",
        "validation_date",
        "candidate",
        "candidate_summary_sha256",
        "retention_approval_sha256",
        "retention",
        "validator",
    }
)
CLARA_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = Path(__file__).resolve().parent
DEPENDENCY_PATHS = {
    "intake_validator": SCRIPT_ROOT / "validate_real_data_pilot_intake.py",
    "mechanical_error_register_schema": (
        CLARA_ROOT
        / "contracts"
        / "real_data_pilot_mechanical_error_register.v1.schema.json"
    ),
    "mechanical_error_validator": (
        SCRIPT_ROOT / "validate_real_data_pilot_mechanical_errors.py"
    ),
    "output_boundary": SCRIPT_ROOT / "real_data_pilot_output_boundary.py",
    "preparation_contract_kernel": SCRIPT_ROOT / "preparation_contract_kernel.py",
    "retention_approval_schema": (
        CLARA_ROOT / "contracts" / "real_data_pilot_retention_approval.v1.schema.json"
    ),
    "sanitized_candidate_schema": (
        CLARA_ROOT
        / "contracts"
        / "real_data_pilot_sanitized_error_class_summary_candidate.v1.schema.json"
    ),
    "sanitized_summary_schema": (
        CLARA_ROOT
        / "contracts"
        / "real_data_pilot_sanitized_error_class_summary.v1.schema.json"
    ),
}


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


def _iso_date(value: Any, *, label: str) -> date:
    result = _text(value, label=label)
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", result) is None:
        raise ContractValidationError(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(result)
    except ValueError as exc:
        raise ContractValidationError(f"{label} must be an ISO date") from exc


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


def _nonnegative_integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractValidationError(f"{label} must be a nonnegative integer")
    return value


def _current_dependency_sha256() -> dict[str, str]:
    return {
        dependency_id: file_sha256(path)
        for dependency_id, path in sorted(DEPENDENCY_PATHS.items())
    }


def _validate_bindings(
    value: Any,
    *,
    expected_bindings: Mapping[str, str],
    label: str,
) -> dict[str, str]:
    bindings = _mapping(value, label=label)
    _exact_fields(bindings, required=BINDING_FIELDS, label=label)
    if set(expected_bindings) != set(BINDING_FIELDS):
        raise ContractValidationError(
            "expected_bindings must contain the registered binding fields"
        )
    validated: dict[str, str] = {}
    for field in sorted(BINDING_FIELDS):
        digest = _sha256(bindings[field], label=f"{label}.{field}")
        expected_digest = _sha256(
            expected_bindings[field],
            label=f"expected_bindings.{field}",
        )
        if digest != expected_digest:
            raise ContractValidationError(f"{label}.{field} does not match")
        validated[field] = digest
    return validated


def _validate_counts(
    value: Any,
    *,
    registered_fields: Sequence[str],
    label: str,
) -> dict[str, int]:
    counts = _mapping(value, label=label)
    _exact_fields(
        counts,
        required=frozenset(registered_fields),
        label=label,
    )
    return {
        field: _nonnegative_integer(counts[field], label=f"{label}.{field}")
        for field in registered_fields
    }


def _derived_mechanical_status(check_counts: Mapping[str, int]) -> str:
    if check_counts["failed"] > 0:
        return "failed"
    if check_counts["not_run"] > 0:
        return "incomplete"
    return "passed"


def _validate_local_json_path(
    path: Path,
    *,
    local_run_root: Path,
    repository_root: Path,
    label: str,
) -> Path:
    validated_path, _ = validate_pilot_local_run_path(
        path,
        local_run_root=local_run_root,
        repository_root=repository_root,
        label=label,
    )
    if not validated_path.is_file():
        raise ContractValidationError(f"{label} must identify one existing file")
    return validated_path


def _require_unchanged_local_snapshot(
    path: Path,
    *,
    expected_byte_count: int,
    expected_sha256: str,
    local_run_root: Path,
    repository_root: Path,
    label: str,
) -> None:
    current_path = _validate_local_json_path(
        path,
        local_run_root=local_run_root,
        repository_root=repository_root,
        label=label,
    )
    _, current_byte_count, current_sha256 = strict_json_snapshot_beneath(
        current_path,
        root=local_run_root,
    )
    if current_byte_count != expected_byte_count or current_sha256 != expected_sha256:
        raise ContractValidationError(f"{label} changed while it was being validated")


def validate_real_data_pilot_sanitized_error_summary_candidate(
    value: Any,
    *,
    expected_pilot_id: str,
    expected_execution_id: str,
    expected_register_sha256: str,
    expected_bindings: Mapping[str, str],
) -> dict[str, Any]:
    """Validate one canonical candidate against replay-derived expectations."""

    expected_pilot_id = _opaque_identifier(
        expected_pilot_id,
        pattern=PILOT_ID_PATTERN,
        label="expected_pilot_id",
    )
    expected_execution_id = _opaque_identifier(
        expected_execution_id,
        pattern=EXECUTION_ID_PATTERN,
        label="expected_execution_id",
    )
    expected_register_sha256 = _sha256(
        expected_register_sha256,
        label="expected_register_sha256",
    )
    candidate = _mapping(value, label="sanitized summary candidate")
    _exact_fields(
        candidate,
        required=CANDIDATE_FIELDS,
        label="sanitized summary candidate",
    )
    _require_constant(
        candidate["schema_version"],
        expected=SANITIZED_CANDIDATE_SCHEMA,
        label="sanitized summary candidate.schema_version",
    )
    _require_constant(
        _opaque_identifier(
            candidate["pilot_id"],
            pattern=PILOT_ID_PATTERN,
            label="sanitized summary candidate.pilot_id",
        ),
        expected=expected_pilot_id,
        label="sanitized summary candidate.pilot_id",
    )
    _require_constant(
        _opaque_identifier(
            candidate["execution_id"],
            pattern=EXECUTION_ID_PATTERN,
            label="sanitized summary candidate.execution_id",
        ),
        expected=expected_execution_id,
        label="sanitized summary candidate.execution_id",
    )
    _require_constant(
        _sha256(
            candidate["mechanical_register_sha256"],
            label="sanitized summary candidate.mechanical_register_sha256",
        ),
        expected=expected_register_sha256,
        label="sanitized summary candidate.mechanical_register_sha256",
    )
    _validate_bindings(
        candidate["bindings"],
        expected_bindings=expected_bindings,
        label="sanitized summary candidate.bindings",
    )
    check_counts = _validate_counts(
        candidate["check_counts"],
        registered_fields=("passed", "failed", "not_run"),
        label="sanitized summary candidate.check_counts",
    )
    if sum(check_counts.values()) == 0:
        raise ContractValidationError(
            "sanitized summary candidate.check_counts must describe at least one check"
        )
    expected_status = _derived_mechanical_status(check_counts)
    _require_constant(
        candidate["mechanical_status"],
        expected=expected_status,
        label="sanitized summary candidate.mechanical_status",
    )
    error_count = _nonnegative_integer(
        candidate["error_count"],
        label="sanitized summary candidate.error_count",
    )
    class_counts = _validate_counts(
        candidate["class_counts"],
        registered_fields=MECHANICAL_CLASSES,
        label="sanitized summary candidate.class_counts",
    )
    if sum(class_counts.values()) != error_count:
        raise ContractValidationError(
            "sanitized summary candidate.class_counts must sum to error_count"
        )
    if check_counts["failed"] == 0 and error_count != 0:
        raise ContractValidationError(
            "sanitized summary candidate cannot record errors without a failed check"
        )
    if error_count < check_counts["failed"]:
        raise ContractValidationError(
            "sanitized summary candidate needs an error for every failed check"
        )
    _require_constant(
        dict(
            _mapping(
                candidate["content_policy"],
                label="sanitized summary candidate.content_policy",
            )
        ),
        expected=CANDIDATE_CONTENT_POLICY,
        label="sanitized summary candidate.content_policy",
    )
    _require_constant(
        candidate["publication_status"],
        expected="withheld",
        label="sanitized summary candidate.publication_status",
    )
    _require_constant(
        candidate["report_ready"],
        expected=False,
        label="sanitized summary candidate.report_ready",
    )
    _require_constant(
        _sequence(
            candidate["does_not_establish"],
            label="sanitized summary candidate.does_not_establish",
        ),
        expected=list(DOES_NOT_ESTABLISH),
        label="sanitized summary candidate.does_not_establish",
    )
    return dict(candidate)


def _validate_retention_approval(
    value: Any,
    *,
    expected_pilot_id: str,
    expected_execution_id: str,
    expected_register_sha256: str,
    expected_candidate_sha256: str,
    as_of: date,
) -> None:
    approval = _mapping(value, label="retention approval")
    _exact_fields(
        approval,
        required=frozenset(
            {
                "schema_version",
                "pilot_id",
                "execution_id",
                "review_version",
                "reviewed_on",
                "reviewer_role",
                "basis",
                "mechanical_register_sha256",
                "candidate_summary_sha256",
                "status",
                "decision",
                "scope",
                "prohibited_content",
                "publication_status",
                "report_ready",
            }
        ),
        label="retention approval",
    )
    _require_constant(
        approval["schema_version"],
        expected=RETENTION_APPROVAL_SCHEMA,
        label="retention approval.schema_version",
    )
    _require_constant(
        _opaque_identifier(
            approval["pilot_id"],
            pattern=PILOT_ID_PATTERN,
            label="retention approval.pilot_id",
        ),
        expected=expected_pilot_id,
        label="retention approval.pilot_id",
    )
    _require_constant(
        _opaque_identifier(
            approval["execution_id"],
            pattern=EXECUTION_ID_PATTERN,
            label="retention approval.execution_id",
        ),
        expected=expected_execution_id,
        label="retention approval.execution_id",
    )
    _opaque_identifier(
        approval["review_version"],
        pattern=RETENTION_REVIEW_VERSION_PATTERN,
        label="retention approval.review_version",
    )
    reviewed_on = _iso_date(
        approval["reviewed_on"],
        label="retention approval.reviewed_on",
    )
    if reviewed_on > as_of:
        raise ContractValidationError(
            "retention approval cannot postdate summary validation"
        )
    _text(approval["reviewer_role"], label="retention approval.reviewer_role")
    _text(approval["basis"], label="retention approval.basis")
    _require_constant(
        _sha256(
            approval["mechanical_register_sha256"],
            label="retention approval.mechanical_register_sha256",
        ),
        expected=expected_register_sha256,
        label="retention approval.mechanical_register_sha256",
    )
    _require_constant(
        _sha256(
            approval["candidate_summary_sha256"],
            label="retention approval.candidate_summary_sha256",
        ),
        expected=expected_candidate_sha256,
        label="retention approval.candidate_summary_sha256",
    )
    for field, expected in (
        ("status", "reviewed"),
        ("decision", "approved"),
        ("scope", "sanitized_error_class_summary_only"),
        ("publication_status", "withheld"),
        ("report_ready", False),
    ):
        _require_constant(
            approval[field],
            expected=expected,
            label=f"retention approval.{field}",
        )
    _require_constant(
        _sequence(
            approval["prohibited_content"],
            label="retention approval.prohibited_content",
        ),
        expected=list(PROHIBITED_CONTENT),
        label="retention approval.prohibited_content",
    )


def _validate_retention_block(value: Any) -> None:
    retention = _mapping(value, label="sanitized error summary.retention")
    _exact_fields(
        retention,
        required=frozenset({"status", "scope", "content_policy", "assurance"}),
        label="sanitized error summary.retention",
    )
    for field, expected in (
        ("status", "declared_reviewed_for_exact_candidate"),
        ("scope", "sanitized_error_class_summary_only"),
        (
            "assurance",
            "declaration_presence_only_not_review_authenticity_or_authority",
        ),
    ):
        _require_constant(
            retention[field],
            expected=expected,
            label=f"sanitized error summary.retention.{field}",
        )
    content_policy = _mapping(
        retention["content_policy"],
        label="sanitized error summary.retention.content_policy",
    )
    expected_policy = {
        "free_text_in_summary": False,
        "paths_in_summary": False,
        "row_level_values_in_summary": False,
        "semantic_findings_in_summary": False,
    }
    _require_constant(
        dict(content_policy),
        expected=expected_policy,
        label="sanitized error summary.retention.content_policy",
    )


def _validate_validator_block(value: Any) -> None:
    validator = _mapping(value, label="sanitized error summary.validator")
    _exact_fields(
        validator,
        required=frozenset(
            {
                "validator_id",
                "validator_version",
                "implementation_sha256",
                "dependency_sha256",
                "mode",
            }
        ),
        label="sanitized error summary.validator",
    )
    _require_constant(
        validator["validator_id"],
        expected=VALIDATOR_ID,
        label="sanitized error summary.validator.validator_id",
    )
    _require_constant(
        validator["validator_version"],
        expected=VALIDATOR_VERSION,
        label="sanitized error summary.validator.validator_version",
    )
    _require_constant(
        _sha256(
            validator["implementation_sha256"],
            label="sanitized error summary.validator.implementation_sha256",
        ),
        expected=file_sha256(Path(__file__).resolve()),
        label="sanitized error summary.validator.implementation_sha256",
    )
    dependencies = _mapping(
        validator["dependency_sha256"],
        label="sanitized error summary.validator.dependency_sha256",
    )
    _exact_fields(
        dependencies,
        required=frozenset(DEPENDENCY_PATHS),
        label="sanitized error summary.validator.dependency_sha256",
    )
    for dependency_id, expected_digest in _current_dependency_sha256().items():
        _require_constant(
            _sha256(
                dependencies[dependency_id],
                label=(
                    "sanitized error summary.validator."
                    f"dependency_sha256.{dependency_id}"
                ),
            ),
            expected=expected_digest,
            label=(
                "sanitized error summary.validator."
                f"dependency_sha256.{dependency_id}"
            ),
        )
    _require_constant(
        validator["mode"],
        expected="deterministic_mechanical_replay",
        label="sanitized error summary.validator.mode",
    )


def _validate_real_data_pilot_sanitized_error_summary_receipt(
    value: Any,
    *,
    expected_candidate: Mapping[str, Any],
    expected_pilot_id: str,
    expected_execution_id: str,
    expected_register_sha256: str,
    expected_validation_date: str,
    expected_retention_approval_sha256: str,
    expected_bindings: Mapping[str, str],
) -> dict[str, Any]:
    """Validate a receipt against evidence already replayed by the public API."""

    validated_expected_candidate = (
        validate_real_data_pilot_sanitized_error_summary_candidate(
            expected_candidate,
            expected_pilot_id=expected_pilot_id,
            expected_execution_id=expected_execution_id,
            expected_register_sha256=expected_register_sha256,
            expected_bindings=expected_bindings,
        )
    )
    expected_candidate_sha256 = canonical_json_sha256(validated_expected_candidate)
    expected_retention_approval_sha256 = _sha256(
        expected_retention_approval_sha256,
        label="expected_retention_approval_sha256",
    )
    summary = _mapping(value, label="sanitized error summary")
    _exact_fields(summary, required=SUMMARY_FIELDS, label="sanitized error summary")
    _require_constant(
        summary["schema_version"],
        expected=SANITIZED_SUMMARY_SCHEMA,
        label="sanitized error summary.schema_version",
    )
    validation_date = _iso_date(
        summary["validation_date"],
        label="sanitized error summary.validation_date",
    )
    _require_constant(
        validation_date,
        expected=_iso_date(
            expected_validation_date,
            label="expected_validation_date",
        ),
        label="sanitized error summary.validation_date",
    )
    candidate = validate_real_data_pilot_sanitized_error_summary_candidate(
        summary["candidate"],
        expected_pilot_id=expected_pilot_id,
        expected_execution_id=expected_execution_id,
        expected_register_sha256=expected_register_sha256,
        expected_bindings=expected_bindings,
    )
    _require_constant(
        candidate,
        expected=validated_expected_candidate,
        label="sanitized error summary.candidate",
    )
    _require_constant(
        _sha256(
            summary["candidate_summary_sha256"],
            label="sanitized error summary.candidate_summary_sha256",
        ),
        expected=expected_candidate_sha256,
        label="sanitized error summary.candidate_summary_sha256",
    )
    _require_constant(
        canonical_json_sha256(candidate),
        expected=expected_candidate_sha256,
        label="sanitized error summary candidate digest",
    )
    _require_constant(
        _sha256(
            summary["retention_approval_sha256"],
            label="sanitized error summary.retention_approval_sha256",
        ),
        expected=expected_retention_approval_sha256,
        label="sanitized error summary.retention_approval_sha256",
    )
    _validate_retention_block(summary["retention"])
    _validate_validator_block(summary["validator"])
    return dict(summary)


def _validated_retention_approval_snapshot(
    retention_approval_path: Path,
    *,
    candidate: Mapping[str, Any],
    validation_date: date,
    local_run_root: Path,
    repository_root: Path,
) -> tuple[dict[str, Any], str]:
    approval_path = _validate_local_json_path(
        retention_approval_path,
        local_run_root=local_run_root,
        repository_root=repository_root,
        label="retention approval path",
    )
    approval, approval_byte_count, approval_sha256 = strict_json_snapshot_beneath(
        approval_path,
        root=local_run_root,
    )
    _validate_retention_approval(
        approval,
        expected_pilot_id=candidate["pilot_id"],
        expected_execution_id=candidate["execution_id"],
        expected_register_sha256=candidate["mechanical_register_sha256"],
        expected_candidate_sha256=canonical_json_sha256(candidate),
        as_of=validation_date,
    )
    current_path = _validate_local_json_path(
        approval_path,
        local_run_root=local_run_root,
        repository_root=repository_root,
        label="retention approval path",
    )
    _, current_byte_count, current_sha256 = strict_json_snapshot_beneath(
        current_path,
        root=local_run_root,
    )
    if current_byte_count != approval_byte_count or current_sha256 != approval_sha256:
        raise ContractValidationError(
            "retention approval path changed while it was being validated"
        )
    return dict(approval), approval_sha256


def validate_real_data_pilot_sanitized_error_summary(
    value: Any,
    mechanical_register_path: Path,
    retention_approval_path: Path,
    *,
    expected_pilot_id: str,
    expected_execution_id: str,
    expected_bindings: Mapping[str, str],
    output_receipts: Any,
    output_directory: Path,
    as_of_date: str,
    local_run_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Replay local evidence and validate one retained summary receipt."""

    run_root, repo_root = resolve_pilot_storage_roots(
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    validation_date = _iso_date(as_of_date, label="as_of_date")
    candidate = build_real_data_pilot_sanitized_error_summary_candidate(
        mechanical_register_path,
        expected_pilot_id=expected_pilot_id,
        expected_execution_id=expected_execution_id,
        expected_bindings=expected_bindings,
        output_receipts=output_receipts,
        output_directory=output_directory,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    _approval, approval_sha256 = _validated_retention_approval_snapshot(
        retention_approval_path,
        candidate=candidate,
        validation_date=validation_date,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    return _validate_real_data_pilot_sanitized_error_summary_receipt(
        value,
        expected_candidate=candidate,
        expected_pilot_id=expected_pilot_id,
        expected_execution_id=expected_execution_id,
        expected_register_sha256=candidate["mechanical_register_sha256"],
        expected_validation_date=validation_date.isoformat(),
        expected_retention_approval_sha256=approval_sha256,
        expected_bindings=expected_bindings,
    )


def build_real_data_pilot_sanitized_error_summary_candidate(
    mechanical_register_path: Path,
    *,
    expected_pilot_id: str,
    expected_execution_id: str,
    expected_bindings: Mapping[str, str],
    output_receipts: Any,
    output_directory: Path,
    local_run_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Derive one canonical review candidate from exact local output bytes."""

    run_root, repo_root = resolve_pilot_storage_roots(
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    register_path = _validate_local_json_path(
        mechanical_register_path,
        local_run_root=run_root,
        repository_root=repo_root,
        label="mechanical register path",
    )
    register, register_byte_count, register_sha256 = strict_json_snapshot_beneath(
        register_path,
        root=run_root,
    )
    register_path = _validate_local_json_path(
        register_path,
        local_run_root=run_root,
        repository_root=repo_root,
        label="mechanical register path",
    )
    validated_register = validate_real_data_pilot_mechanical_error_register_value(
        register,
        register_path=register_path,
        register_byte_count=register_byte_count,
        register_sha256=register_sha256,
        expected_pilot_id=expected_pilot_id,
        expected_execution_id=expected_execution_id,
        expected_bindings=expected_bindings,
        output_receipts=output_receipts,
        output_directory=output_directory,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    _require_unchanged_local_snapshot(
        register_path,
        expected_byte_count=register_byte_count,
        expected_sha256=register_sha256,
        local_run_root=run_root,
        repository_root=repo_root,
        label="mechanical register path",
    )

    candidate = {
        "schema_version": SANITIZED_CANDIDATE_SCHEMA,
        "pilot_id": validated_register["pilot_id"],
        "execution_id": validated_register["execution_id"],
        "mechanical_register_sha256": register_sha256,
        "bindings": dict(validated_register["bindings"]),
        "mechanical_status": validated_register["summary"]["overall_status"],
        "check_counts": dict(validated_register["summary"]["check_counts"]),
        "error_count": validated_register["summary"]["error_count"],
        "class_counts": dict(validated_register["summary"]["class_counts"]),
        "content_policy": dict(CANDIDATE_CONTENT_POLICY),
        "publication_status": "withheld",
        "report_ready": False,
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }
    return validate_real_data_pilot_sanitized_error_summary_candidate(
        candidate,
        expected_pilot_id=expected_pilot_id,
        expected_execution_id=expected_execution_id,
        expected_register_sha256=register_sha256,
        expected_bindings=expected_bindings,
    )


def build_real_data_pilot_sanitized_error_summary(
    mechanical_register_path: Path,
    retention_approval_path: Path,
    *,
    expected_pilot_id: str,
    expected_execution_id: str,
    expected_bindings: Mapping[str, str],
    output_receipts: Any,
    output_directory: Path,
    as_of_date: str,
    local_run_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Build one retained receipt after approval of the exact candidate digest."""

    run_root, repo_root = resolve_pilot_storage_roots(
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    candidate = build_real_data_pilot_sanitized_error_summary_candidate(
        mechanical_register_path,
        expected_pilot_id=expected_pilot_id,
        expected_execution_id=expected_execution_id,
        expected_bindings=expected_bindings,
        output_receipts=output_receipts,
        output_directory=output_directory,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    candidate_sha256 = canonical_json_sha256(candidate)
    validation_date = _iso_date(as_of_date, label="as_of_date")

    _approval, approval_sha256 = _validated_retention_approval_snapshot(
        retention_approval_path,
        candidate=candidate,
        validation_date=validation_date,
        local_run_root=run_root,
        repository_root=repo_root,
    )

    summary = {
        "schema_version": SANITIZED_SUMMARY_SCHEMA,
        "validation_date": validation_date.isoformat(),
        "candidate": candidate,
        "candidate_summary_sha256": candidate_sha256,
        "retention_approval_sha256": approval_sha256,
        "retention": {
            "status": "declared_reviewed_for_exact_candidate",
            "scope": "sanitized_error_class_summary_only",
            "content_policy": {
                "free_text_in_summary": False,
                "paths_in_summary": False,
                "row_level_values_in_summary": False,
                "semantic_findings_in_summary": False,
            },
            "assurance": (
                "declaration_presence_only_not_review_authenticity_or_authority"
            ),
        },
        "validator": {
            "validator_id": VALIDATOR_ID,
            "validator_version": VALIDATOR_VERSION,
            "implementation_sha256": file_sha256(Path(__file__).resolve()),
            "dependency_sha256": _current_dependency_sha256(),
            "mode": "deterministic_mechanical_replay",
        },
    }
    return validate_real_data_pilot_sanitized_error_summary(
        summary,
        mechanical_register_path,
        retention_approval_path,
        expected_pilot_id=expected_pilot_id,
        expected_execution_id=expected_execution_id,
        expected_bindings=expected_bindings,
        output_receipts=output_receipts,
        output_directory=output_directory,
        as_of_date=validation_date.isoformat(),
        local_run_root=run_root,
        repository_root=repo_root,
    )
