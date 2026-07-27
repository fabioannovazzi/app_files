#!/usr/bin/env python3
"""Validate a reviewer-owned semantic register for Clara's real-data pilot.

The validator checks structure, review coverage, reference closure, exact
receipts, and reviewer-declared blocking flags. It does not decide accounting
meaning, create an issue, resolve an issue, or promote semantic correctness.
Mechanical errors remain a separate producer-owned artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from preparation_contract_kernel import (
    ContractValidationError,
    file_sha256,
    file_snapshot_beneath,
    strict_json_snapshot_beneath,
)
from validate_real_data_pilot_intake import (
    INTAKE_RECEIPT_SCHEMA,
    INTAKE_RECEIPT_SCHEMA_V2,
    PILOT_ID_PATTERN,
    REQUIRED_SEMANTIC_REVIEWS,
    STORAGE_RELATIONS,
    pinned_pilot_receipt_output,
    resolve_pilot_storage_roots,
    validate_pilot_local_run_path,
    validate_pilot_receipt_output_path,
    validate_real_data_pilot_intake_receipt,
    validate_real_data_pilot_intake_receipt_v2,
)

__all__ = [
    "SEMANTIC_REVIEW_RECEIPT_SCHEMA",
    "SEMANTIC_REVIEW_SCHEMA",
    "validate_real_data_pilot_semantic_review_receipt",
    "validate_real_data_pilot_semantic_review",
    "main",
]

LOGGER = logging.getLogger(__name__)

SEMANTIC_REVIEW_SCHEMA = "clara.real_data_pilot_semantic_review.v1"
SEMANTIC_REVIEW_RECEIPT_SCHEMA = "clara.real_data_pilot_semantic_review_receipt.v1"
VALIDATOR_VERSION = "1.0.0"
VALIDATOR_ID = "real_data_pilot_semantic_review_validator.v1"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REVIEW_VERSION_PATTERN = re.compile(r"^review-[0-9a-f]{16}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ISSUE_STATUSES = frozenset({"accepted_limitation", "open", "resolved"})
REQUIRED_REVIEW_IDS_BY_TOPIC = {
    topic: f"topic-review-{position:02d}"
    for position, topic in enumerate(REQUIRED_SEMANTIC_REVIEWS, start=1)
}
DOES_NOT_ESTABLISH = (
    "accounting_semantic_correctness",
    "current_authorization_at_later_execution",
    "downstream_compatibility",
    "evidence_sufficiency",
    "future_storage_or_copy_behavior",
    "issue_completeness",
    "publication_authorization",
    "receipt_authenticity_or_signer_identity",
    "retention_or_deletion",
    "report_readiness",
    "reviewer_identity_or_authority",
)
SEMANTIC_REVIEW_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "pilot_id",
        "review_version",
        "reviewed_on",
        "validation_date",
        "semantic_review_sha256",
        "intake_receipt_sha256",
        "review_summary",
        "error_separation",
        "readiness",
        "validator",
    }
)
CLARA_ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_VALIDATOR_DEPENDENCY_PATHS = {
    "intake_receipt_schema": (
        CLARA_ROOT / "contracts" / "real_data_pilot_intake_receipt.v1.schema.json",
        CLARA_ROOT / "contracts" / "real_data_pilot_intake_receipt.v2.schema.json",
    ),
    "intake_schema": (
        CLARA_ROOT / "contracts" / "real_data_pilot_intake.v1.schema.json",
        CLARA_ROOT / "contracts" / "real_data_pilot_intake.v2.schema.json",
    ),
    "intake_validator": (
        Path(__file__).resolve().with_name("validate_real_data_pilot_intake.py"),
    ),
    "preparation_contract_kernel": (
        Path(__file__).resolve().with_name("preparation_contract_kernel.py"),
    ),
    "semantic_review_receipt_schema": (
        CLARA_ROOT
        / "contracts"
        / "real_data_pilot_semantic_review_receipt.v1.schema.json",
    ),
    "semantic_review_schema": (
        CLARA_ROOT / "contracts" / "real_data_pilot_semantic_review.v1.schema.json",
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


def _current_date() -> date:
    """Return the CLI validation date through a testable time seam."""

    return date.today()


def _sha256(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if SHA256_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a lowercase SHA-256 digest")
    return result


def _current_dependency_sha256() -> dict[str, str]:
    """Return hashes for every file that can change semantic validation."""

    return {
        dependency_id: _dependency_group_sha256(paths)
        for dependency_id, paths in sorted(SEMANTIC_VALIDATOR_DEPENDENCY_PATHS.items())
    }


def _dependency_group_sha256(paths: Sequence[Path]) -> str:
    """Bind one stable dependency field to one or more versioned files."""

    if len(paths) == 1:
        return file_sha256(paths[0])
    digest = hashlib.sha256()
    digest.update(b"clara.semantic-validator-dependency-group.v1\0")
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _validate_dependency_sha256(value: Any, *, label: str) -> dict[str, str]:
    dependencies = _mapping(value, label=label)
    _exact_fields(
        dependencies,
        required=frozenset(SEMANTIC_VALIDATOR_DEPENDENCY_PATHS),
        label=label,
    )
    expected = _current_dependency_sha256()
    validated: dict[str, str] = {}
    for dependency_id, expected_digest in expected.items():
        digest = _sha256(
            dependencies[dependency_id],
            label=f"{label}.{dependency_id}",
        )
        if digest != expected_digest:
            raise ContractValidationError(f"{label}.{dependency_id} is not current")
        validated[dependency_id] = digest
    return validated


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


def _unique_texts(value: Any, *, label: str) -> list[str]:
    items = [_text(item, label=f"{label}[]") for item in _sequence(value, label=label)]
    if not items:
        raise ContractValidationError(f"{label} must not be empty")
    if len(items) != len(set(items)):
        raise ContractValidationError(f"{label} must contain unique values")
    return items


def _validate_intake_receipt(
    path: Path,
    *,
    expected_pilot_id: str,
    expected_sha256: str,
    local_run_root: Path,
) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise ContractValidationError(
            "intake receipt path must identify one existing file"
        )
    receipt, _, actual_sha256 = strict_json_snapshot_beneath(
        path,
        root=local_run_root,
    )
    if actual_sha256 != expected_sha256:
        raise ContractValidationError(
            "intake_receipt_sha256 does not match the supplied receipt"
        )
    receipt_mapping = _mapping(receipt, label="intake receipt")
    receipt_schema = receipt_mapping.get("schema_version")
    if receipt_schema == INTAKE_RECEIPT_SCHEMA:
        receipt = validate_real_data_pilot_intake_receipt(receipt_mapping)
    elif receipt_schema == INTAKE_RECEIPT_SCHEMA_V2:
        receipt = validate_real_data_pilot_intake_receipt_v2(receipt_mapping)
    else:
        raise ContractValidationError(
            "intake receipt.schema_version is not a supported exact version"
        )
    if receipt.get("pilot_id") != expected_pilot_id:
        raise ContractValidationError(
            "semantic review pilot_id does not match the intake receipt"
        )
    eligibility = _mapping(receipt.get("eligibility"), label="intake eligibility")
    _require_constant(
        eligibility.get("status"),
        expected="declared_boundary_passed_for_local_pilot_intake",
        label="intake eligibility.status",
    )
    _require_constant(
        eligibility.get("publication_status"),
        expected="withheld",
        label="intake eligibility.publication_status",
    )
    _require_constant(
        eligibility.get("report_ready"),
        expected=False,
        label="intake eligibility.report_ready",
    )
    _iso_date(receipt.get("validation_date"), label="intake validation_date")
    return receipt


def _validate_evidence_registry(
    value: Any,
    *,
    review_root: Path,
    local_run_root: Path,
    repository_root: Path,
) -> set[str]:
    registry = _mapping(value, label="evidence_registry")
    if not registry:
        raise ContractValidationError("evidence_registry must not be empty")
    evidence_ids: set[str] = set()
    for raw_evidence_id, raw_record in registry.items():
        evidence_id = _identifier(
            raw_evidence_id,
            label="evidence_registry key",
        )
        record = _mapping(
            raw_record,
            label=f"evidence_registry.{evidence_id}",
        )
        _exact_fields(
            record,
            required=frozenset(
                {
                    "path",
                    "media_type",
                    "byte_count",
                    "sha256",
                }
            ),
            label=f"evidence_registry.{evidence_id}",
        )
        relative_path = Path(
            _text(
                record["path"],
                label=f"evidence_registry.{evidence_id}.path",
            )
        )
        if relative_path.is_absolute():
            raise ContractValidationError(
                f"evidence_registry.{evidence_id}.path must be relative"
            )
        evidence_path, _ = validate_pilot_local_run_path(
            review_root / relative_path,
            local_run_root=local_run_root,
            repository_root=repository_root,
            label=f"evidence_registry.{evidence_id}.path",
        )
        if not evidence_path.is_file():
            raise ContractValidationError(
                f"evidence_registry.{evidence_id}.path must identify one file"
            )
        _text(
            record["media_type"],
            label=f"evidence_registry.{evidence_id}.media_type",
        )
        byte_count = record["byte_count"]
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count <= 0
        ):
            raise ContractValidationError(
                f"evidence_registry.{evidence_id}.byte_count must be positive"
            )
        actual_byte_count, actual_digest = file_snapshot_beneath(
            evidence_path,
            root=local_run_root,
        )
        if actual_byte_count != byte_count:
            raise ContractValidationError(
                f"evidence_registry.{evidence_id}.byte_count does not match"
            )
        digest = _sha256(
            record["sha256"],
            label=f"evidence_registry.{evidence_id}.sha256",
        )
        if actual_digest != digest:
            raise ContractValidationError(
                f"evidence_registry.{evidence_id}.sha256 does not match"
            )
        evidence_ids.add(evidence_id)
    return evidence_ids


def _require_closed_evidence_refs(
    value: Any,
    *,
    evidence_ids: set[str],
    label: str,
) -> None:
    refs = _unique_texts(value, label=label)
    unresolved = sorted(set(refs) - evidence_ids)
    if unresolved:
        raise ContractValidationError(
            f"{label} contains unresolved evidence references: {unresolved}"
        )


def _validate_required_reviews(
    value: Any,
    *,
    evidence_ids: set[str],
) -> list[dict[str, Any]]:
    raw_reviews = _sequence(value, label="required_reviews")
    reviews: list[dict[str, Any]] = []
    for position, raw_review in enumerate(raw_reviews):
        label = f"required_reviews[{position}]"
        review = _mapping(raw_review, label=label)
        _exact_fields(
            review,
            required=frozenset(
                {
                    "review_id",
                    "topic",
                    "status",
                    "decision",
                    "basis",
                    "evidence_refs",
                }
            ),
            label=label,
        )
        review_id = _identifier(review["review_id"], label=f"{label}.review_id")
        topic = _text(review["topic"], label=f"{label}.topic")
        if topic not in REQUIRED_SEMANTIC_REVIEWS:
            raise ContractValidationError(f"{label}.topic is not registered")
        _require_constant(
            review["status"],
            expected="reviewed",
            label=f"{label}.status",
        )
        _require_constant(
            review_id,
            expected=REQUIRED_REVIEW_IDS_BY_TOPIC[topic],
            label=f"{label}.review_id",
        )
        _text(review["decision"], label=f"{label}.decision")
        _text(review["basis"], label=f"{label}.basis")
        _require_closed_evidence_refs(
            review["evidence_refs"],
            evidence_ids=evidence_ids,
            label=f"{label}.evidence_refs",
        )
        reviews.append({"review_id": review_id, "topic": topic})

    topics = [review["topic"] for review in reviews]
    if len(topics) != len(REQUIRED_SEMANTIC_REVIEWS) or set(topics) != set(
        REQUIRED_SEMANTIC_REVIEWS
    ):
        raise ContractValidationError(
            "required_reviews must cover each registered topic exactly once"
        )
    return sorted(
        reviews,
        key=lambda item: REQUIRED_SEMANTIC_REVIEWS.index(item["topic"]),
    )


def _validate_issues(
    value: Any,
    *,
    evidence_ids: set[str],
) -> list[dict[str, Any]]:
    raw_issues = _mapping(value, label="issues")
    issues: list[dict[str, Any]] = []
    for raw_issue_id, raw_issue in sorted(raw_issues.items()):
        issue_id = _identifier(raw_issue_id, label="issues key")
        label = f"issues.{issue_id}"
        issue = _mapping(raw_issue, label=label)
        _exact_fields(
            issue,
            required=frozenset(
                {
                    "topic",
                    "status",
                    "blocking",
                    "description",
                    "basis",
                    "evidence_refs",
                    "resolution",
                }
            ),
            label=label,
        )
        topic = _text(issue["topic"], label=f"{label}.topic")
        if topic not in REQUIRED_SEMANTIC_REVIEWS:
            raise ContractValidationError(f"{label}.topic is not registered")
        status = _text(issue["status"], label=f"{label}.status")
        if status not in ISSUE_STATUSES:
            raise ContractValidationError(f"{label}.status is not registered")
        blocking = issue["blocking"]
        if not isinstance(blocking, bool):
            raise ContractValidationError(f"{label}.blocking must be boolean")
        _text(issue["description"], label=f"{label}.description")
        _text(issue["basis"], label=f"{label}.basis")
        _require_closed_evidence_refs(
            issue["evidence_refs"],
            evidence_ids=evidence_ids,
            label=f"{label}.evidence_refs",
        )
        resolution = issue["resolution"]
        if status == "open":
            if resolution is not None:
                raise ContractValidationError(
                    f"{label}.resolution must be null while the issue is open"
                )
        else:
            _text(resolution, label=f"{label}.resolution")
            if blocking:
                raise ContractValidationError(
                    f"{label}.blocking must be false after disposition"
                )
        issues.append(
            {
                "issue_id": issue_id,
                "topic": topic,
                "status": status,
                "blocking": blocking,
            }
        )

    return issues


def _issue_counts(issues: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "open_blocking": sum(
            1
            for issue in issues
            if issue["status"] == "open" and issue["blocking"] is True
        ),
        "open_nonblocking": sum(
            1
            for issue in issues
            if issue["status"] == "open" and issue["blocking"] is False
        ),
        "resolved": sum(1 for issue in issues if issue["status"] == "resolved"),
        "accepted_limitation": sum(
            1 for issue in issues if issue["status"] == "accepted_limitation"
        ),
    }


def _nonnegative_integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractValidationError(f"{label} must be a nonnegative integer")
    return value


def validate_real_data_pilot_semantic_review_receipt(
    value: Any,
) -> dict[str, Any]:
    """Validate every field and derived invariant in one semantic receipt."""

    receipt = _mapping(value, label="semantic review receipt")
    _exact_fields(
        receipt,
        required=SEMANTIC_REVIEW_RECEIPT_FIELDS,
        label="semantic review receipt",
    )
    _require_constant(
        receipt["schema_version"],
        expected=SEMANTIC_REVIEW_RECEIPT_SCHEMA,
        label="semantic review receipt.schema_version",
    )
    _opaque_identifier(
        receipt["pilot_id"],
        pattern=PILOT_ID_PATTERN,
        label="semantic review receipt.pilot_id",
    )
    _opaque_identifier(
        receipt["review_version"],
        pattern=REVIEW_VERSION_PATTERN,
        label="semantic review receipt.review_version",
    )
    reviewed_on = _iso_date(
        receipt["reviewed_on"],
        label="semantic review receipt.reviewed_on",
    )
    validation_date = _iso_date(
        receipt["validation_date"],
        label="semantic review receipt.validation_date",
    )
    if reviewed_on > validation_date:
        raise ContractValidationError(
            "semantic review receipt cannot postdate its validation"
        )
    for field in ("semantic_review_sha256", "intake_receipt_sha256"):
        _sha256(
            receipt[field],
            label=f"semantic review receipt.{field}",
        )

    summary = _mapping(
        receipt["review_summary"],
        label="semantic review receipt.review_summary",
    )
    _exact_fields(
        summary,
        required=frozenset(
            {
                "evidence_count",
                "required_review_count",
                "issue_counts",
            }
        ),
        label="semantic review receipt.review_summary",
    )
    evidence_count = summary["evidence_count"]
    if (
        isinstance(evidence_count, bool)
        or not isinstance(evidence_count, int)
        or evidence_count <= 0
    ):
        raise ContractValidationError(
            "semantic review receipt.review_summary.evidence_count "
            "must be a positive integer"
        )
    _require_constant(
        summary["required_review_count"],
        expected=len(REQUIRED_SEMANTIC_REVIEWS),
        label="semantic review receipt.review_summary.required_review_count",
    )
    issue_counts = _mapping(
        summary["issue_counts"],
        label="semantic review receipt.review_summary.issue_counts",
    )
    issue_count_fields = frozenset(
        {
            "open_blocking",
            "open_nonblocking",
            "resolved",
            "accepted_limitation",
        }
    )
    _exact_fields(
        issue_counts,
        required=issue_count_fields,
        label="semantic review receipt.review_summary.issue_counts",
    )
    validated_counts = {
        field: _nonnegative_integer(
            issue_counts[field],
            label=f"semantic review receipt.review_summary.issue_counts.{field}",
        )
        for field in issue_count_fields
    }
    error_separation = _mapping(
        receipt["error_separation"],
        label="semantic review receipt.error_separation",
    )
    _exact_fields(
        error_separation,
        required=frozenset(
            {
                "semantic_register",
                "mechanical_register",
                "semantic_content_in_receipt",
                "storage_location_check",
            }
        ),
        label="semantic review receipt.error_separation",
    )
    for field, expected in (
        ("semantic_register", "reviewer_owned_hash_bound_local_artifact"),
        ("mechanical_register", "producer_owned_separate_artifact"),
        ("semantic_content_in_receipt", False),
    ):
        _require_constant(
            error_separation[field],
            expected=expected,
            label=f"semantic review receipt.error_separation.{field}",
        )
    location = _mapping(
        error_separation["storage_location_check"],
        label="semantic review receipt.error_separation.storage_location_check",
    )
    _exact_fields(
        location,
        required=frozenset(
            {
                "status",
                "semantic_register_relation",
                "intake_receipt_relation",
                "resolved_path_containment_enforced",
                "git_ignore_required_inside_repository",
            }
        ),
        label="semantic review receipt.error_separation.storage_location_check",
    )
    for field, expected in (
        ("status", "passed_at_validation"),
        ("resolved_path_containment_enforced", True),
        ("git_ignore_required_inside_repository", True),
    ):
        _require_constant(
            location[field],
            expected=expected,
            label=(
                "semantic review receipt.error_separation."
                f"storage_location_check.{field}"
            ),
        )
    for field in ("semantic_register_relation", "intake_receipt_relation"):
        relation = _text(
            location[field],
            label=(
                "semantic review receipt.error_separation."
                f"storage_location_check.{field}"
            ),
        )
        if relation not in STORAGE_RELATIONS:
            raise ContractValidationError(
                "semantic review receipt storage relation is not registered"
            )

    readiness = _mapping(
        receipt["readiness"],
        label="semantic review receipt.readiness",
    )
    _exact_fields(
        readiness,
        required=frozenset(
            {
                "status",
                "mechanical_preparation_allowed",
                "semantic_status_for_audit_envelope",
                "publication_status",
                "report_ready",
                "execution_revalidation_required",
                "does_not_establish",
            }
        ),
        label="semantic review receipt.readiness",
    )
    preparation_allowed = validated_counts["open_blocking"] == 0
    expected_status = (
        "ready_for_mechanical_preparation_only"
        if preparation_allowed
        else "blocked_by_reviewed_semantic_issues"
    )
    for field, expected in (
        ("status", expected_status),
        ("mechanical_preparation_allowed", preparation_allowed),
        ("semantic_status_for_audit_envelope", "not_assessed"),
        ("publication_status", "withheld"),
        ("report_ready", False),
        ("execution_revalidation_required", True),
    ):
        _require_constant(
            readiness[field],
            expected=expected,
            label=f"semantic review receipt.readiness.{field}",
        )
    does_not_establish = _sequence(
        readiness["does_not_establish"],
        label="semantic review receipt.readiness.does_not_establish",
    )
    if any(not isinstance(item, str) for item in does_not_establish):
        raise ContractValidationError(
            "semantic review receipt.readiness.does_not_establish "
            "must contain text values"
        )
    _require_constant(
        does_not_establish,
        expected=list(DOES_NOT_ESTABLISH),
        label="semantic review receipt.readiness.does_not_establish",
    )

    validator = _mapping(
        receipt["validator"],
        label="semantic review receipt.validator",
    )
    _exact_fields(
        validator,
        required=frozenset(
            {
                "dependency_sha256",
                "validator_id",
                "validator_version",
                "implementation_sha256",
                "mode",
            }
        ),
        label="semantic review receipt.validator",
    )
    _require_constant(
        validator["validator_id"],
        expected=VALIDATOR_ID,
        label="semantic review receipt.validator.validator_id",
    )
    _require_constant(
        validator["validator_version"],
        expected=VALIDATOR_VERSION,
        label="semantic review receipt.validator.validator_version",
    )
    implementation_sha256 = _sha256(
        validator["implementation_sha256"],
        label="semantic review receipt.validator.implementation_sha256",
    )
    if implementation_sha256 != file_sha256(Path(__file__).resolve()):
        raise ContractValidationError(
            "semantic review receipt validator implementation is not current"
        )
    _validate_dependency_sha256(
        validator["dependency_sha256"],
        label="semantic review receipt.validator.dependency_sha256",
    )
    _require_constant(
        validator["mode"],
        expected="deterministic_mechanical",
        label="semantic review receipt.validator.mode",
    )
    return dict(receipt)


def validate_real_data_pilot_semantic_review(
    review_path: Path,
    intake_receipt_path: Path,
    *,
    as_of_date: str,
    local_run_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Return a sanitized readiness receipt for one reviewer-owned register."""

    run_root, repo_root = resolve_pilot_storage_roots(
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    review_path, review_relation = validate_pilot_local_run_path(
        review_path,
        local_run_root=run_root,
        repository_root=repo_root,
        label="semantic review path",
    )
    intake_receipt_path, intake_receipt_relation = validate_pilot_local_run_path(
        intake_receipt_path,
        local_run_root=run_root,
        repository_root=repo_root,
        label="intake receipt path",
    )
    if not review_path.is_file():
        raise ContractValidationError(
            "semantic review path must identify one existing file"
        )
    review, _, semantic_review_sha256 = strict_json_snapshot_beneath(
        review_path,
        root=run_root,
    )
    _exact_fields(
        review,
        required=frozenset(
            {
                "schema_version",
                "pilot_id",
                "review_version",
                "review_status",
                "reviewed_on",
                "reviewer_role",
                "intake_receipt_sha256",
                "evidence_registry",
                "required_reviews",
                "issues",
                "mechanical_error_register_policy",
                "publication_status",
                "report_ready",
            }
        ),
        label="semantic review",
    )
    _require_constant(
        review["schema_version"],
        expected=SEMANTIC_REVIEW_SCHEMA,
        label="semantic review.schema_version",
    )
    pilot_id = _opaque_identifier(
        review["pilot_id"],
        pattern=PILOT_ID_PATTERN,
        label="semantic review.pilot_id",
    )
    review_version = _opaque_identifier(
        review["review_version"],
        pattern=REVIEW_VERSION_PATTERN,
        label="semantic review.review_version",
    )
    _require_constant(
        review["review_status"],
        expected="reviewed",
        label="semantic review.review_status",
    )
    reviewed_on = _iso_date(
        review["reviewed_on"],
        label="semantic review.reviewed_on",
    )
    _text(review["reviewer_role"], label="semantic review.reviewer_role")
    intake_receipt_sha256 = _sha256(
        review["intake_receipt_sha256"],
        label="semantic review.intake_receipt_sha256",
    )
    intake_receipt = _validate_intake_receipt(
        intake_receipt_path,
        expected_pilot_id=pilot_id,
        expected_sha256=intake_receipt_sha256,
        local_run_root=run_root,
    )
    intake_validation_date = _iso_date(
        intake_receipt["validation_date"],
        label="intake validation_date",
    )
    as_of = _iso_date(as_of_date, label="as_of_date")
    if intake_validation_date != as_of:
        raise ContractValidationError(
            "semantic review requires an intake receipt revalidated on "
            "the semantic-review date"
        )
    if reviewed_on < intake_validation_date:
        raise ContractValidationError(
            "semantic review cannot predate the validated intake"
        )
    if reviewed_on > as_of:
        raise ContractValidationError(
            "semantic review cannot postdate its validation date"
        )
    evidence_ids = _validate_evidence_registry(
        review["evidence_registry"],
        review_root=review_path.parent,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    reviews = _validate_required_reviews(
        review["required_reviews"],
        evidence_ids=evidence_ids,
    )
    issues = _validate_issues(
        review["issues"],
        evidence_ids=evidence_ids,
    )
    _require_constant(
        review["mechanical_error_register_policy"],
        expected="producer_owned_separate_artifact",
        label="semantic review.mechanical_error_register_policy",
    )
    _require_constant(
        review["publication_status"],
        expected="withheld",
        label="semantic review.publication_status",
    )
    _require_constant(
        review["report_ready"],
        expected=False,
        label="semantic review.report_ready",
    )

    counts = _issue_counts(issues)
    preparation_allowed = counts["open_blocking"] == 0
    readiness_status = (
        "ready_for_mechanical_preparation_only"
        if preparation_allowed
        else "blocked_by_reviewed_semantic_issues"
    )
    receipt = {
        "schema_version": SEMANTIC_REVIEW_RECEIPT_SCHEMA,
        "pilot_id": pilot_id,
        "review_version": review_version,
        "reviewed_on": reviewed_on.isoformat(),
        "validation_date": as_of.isoformat(),
        "semantic_review_sha256": semantic_review_sha256,
        "intake_receipt_sha256": intake_receipt_sha256,
        "review_summary": {
            "evidence_count": len(evidence_ids),
            "required_review_count": len(reviews),
            "issue_counts": counts,
        },
        "error_separation": {
            "semantic_register": "reviewer_owned_hash_bound_local_artifact",
            "mechanical_register": "producer_owned_separate_artifact",
            "semantic_content_in_receipt": False,
            "storage_location_check": {
                "status": "passed_at_validation",
                "semantic_register_relation": review_relation,
                "intake_receipt_relation": intake_receipt_relation,
                "resolved_path_containment_enforced": True,
                "git_ignore_required_inside_repository": True,
            },
        },
        "readiness": {
            "status": readiness_status,
            "mechanical_preparation_allowed": preparation_allowed,
            "semantic_status_for_audit_envelope": "not_assessed",
            "publication_status": "withheld",
            "report_ready": False,
            "execution_revalidation_required": True,
            "does_not_establish": list(DOES_NOT_ESTABLISH),
        },
        "validator": {
            "dependency_sha256": _current_dependency_sha256(),
            "validator_id": VALIDATOR_ID,
            "validator_version": VALIDATOR_VERSION,
            "implementation_sha256": file_sha256(Path(__file__).resolve()),
            "mode": "deterministic_mechanical",
        },
    }
    return validate_real_data_pilot_semantic_review_receipt(receipt)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate one semantic register and write its sanitized receipt."""

    parser = argparse.ArgumentParser(
        description="Validate Clara's real-data pilot semantic-review boundary."
    )
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--intake-receipt", required=True, type=Path)
    parser.add_argument("--local-run-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    run_root, repo_root = resolve_pilot_storage_roots(
        local_run_root=args.local_run_root,
        repository_root=args.repository_root,
    )
    output_path, _ = validate_pilot_receipt_output_path(
        args.output,
        declared_local_run_root=args.local_run_root,
        local_run_root=run_root,
        repository_root=repo_root,
        label="output path",
    )
    review_path = args.review.resolve()
    intake_receipt_path = args.intake_receipt.resolve()
    if output_path in {review_path, intake_receipt_path}:
        raise ContractValidationError(
            "output path must not equal the semantic review or intake receipt path"
        )
    if not output_path.parent.is_dir():
        raise ContractValidationError(
            "output path parent must be an existing directory"
        )
    with pinned_pilot_receipt_output(
        output_path,
        local_run_root=run_root,
    ) as pinned_output:
        pinned_output.require_absent()
        receipt = validate_real_data_pilot_semantic_review(
            review_path,
            intake_receipt_path,
            as_of_date=_current_date().isoformat(),
            local_run_root=run_root,
            repository_root=repo_root,
        )
        pinned_output.write_json(receipt)
    LOGGER.info(
        "Real-data pilot semantic review %s: %s",
        receipt["pilot_id"],
        receipt["readiness"]["status"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
