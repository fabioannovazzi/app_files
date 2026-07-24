#!/usr/bin/env python3
"""Validate the declared authorization boundary for a real-data pilot.

The checks in this module are deterministic because exact source binding,
declared purpose, dates, and fixed privacy/publication boundaries are
mechanically verifiable. They do not establish that an authorizer has legal
authority, that data is sufficiently anonymized, or that accounting semantics
are correct. Those remain reviewed human judgements.
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil

# The only subprocess is a fixed, shell-free git check-ignore invocation.
import subprocess  # nosec B404
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from preparation_contract_kernel import (
    ContractValidationError,
    canonical_json_sha256,
    file_sha256,
    file_snapshot_beneath,
    strict_json_snapshot,
    strict_json_snapshot_beneath,
    write_json,
)

__all__ = [
    "INTAKE_RECEIPT_SCHEMA",
    "INTAKE_SCHEMA",
    "PILOT_ID_PATTERN",
    "clear_owned_pilot_receipt_output",
    "resolve_pilot_storage_roots",
    "validate_pilot_receipt_output_path",
    "validate_pilot_local_run_path",
    "validate_real_data_pilot_intake_receipt",
    "validate_real_data_pilot_intake",
    "main",
]

LOGGER = logging.getLogger(__name__)

INTAKE_SCHEMA = "clara.real_data_pilot_intake.v1"
INTAKE_RECEIPT_SCHEMA = "clara.real_data_pilot_intake_receipt.v1"
VALIDATOR_VERSION = "1.0.0"
VALIDATOR_ID = "real_data_pilot_intake_validator.v1"
PURPOSE = "local_due_diligence_preparation_evaluation"
SOURCE_KIND = "commercial_trial_balance"
DATA_CLASSIFICATIONS = frozenset({"anonymized_real", "consented_real"})
AUTHORIZATION_BASES = frozenset(
    {
        "explicit_authorized_user_instruction",
        "public_owner_license",
        "written_data_owner_permission",
    }
)
PERMITTED_ACTIONS = (
    "codex_model_processing",
    "local_deterministic_processing",
)
PROHIBITED_ACTIONS = (
    "commit_raw_or_row_level_data",
    "package_raw_or_row_level_data",
    "publish_raw_or_row_level_data",
)
REQUIRED_SEMANTIC_REVIEWS = (
    "account_mapping",
    "control_equivalence_and_tolerance",
    "currency_unit_and_fx",
    "dataset_identity_and_grain",
    "period_calendar_and_value_basis",
    "scope_entity_and_eliminations",
    "sign_convention",
)
DOES_NOT_ESTABLISH = (
    "accounting_semantic_correctness",
    "anonymization_sufficiency",
    "authorizer_identity_or_authority",
    "commercial_origin_or_authenticity",
    "current_authorization_at_later_execution",
    "downstream_compatibility",
    "future_storage_or_copy_behavior",
    "legal_permission",
    "publication_authorization",
    "receipt_authenticity_or_signer_identity",
    "retention_or_deletion",
    "report_readiness",
)
PILOT_ID_PATTERN = re.compile(r"^pilot-[0-9a-f]{16}$")
SOURCE_ID_PATTERN = re.compile(r"^source-[0-9a-f]{16}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MEDIA_TYPES = frozenset(
    {
        "application/vnd.ms-excel",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
    }
)
STORAGE_RELATIONS = frozenset(
    {
        "inside_repository_git_ignored",
        "outside_repository_within_run_root",
    }
)
INTAKE_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "pilot_id",
        "validation_date",
        "intake_contract_sha256",
        "source_receipt",
        "authorization_receipt",
        "privacy_boundary",
        "deidentification_review",
        "semantic_review",
        "eligibility",
        "validator",
    }
)
CLARA_ROOT = Path(__file__).resolve().parents[1]
INTAKE_VALIDATOR_DEPENDENCY_PATHS = {
    "intake_receipt_schema": (
        CLARA_ROOT / "contracts" / "real_data_pilot_intake_receipt.v1.schema.json"
    ),
    "intake_schema": (
        CLARA_ROOT / "contracts" / "real_data_pilot_intake.v1.schema.json"
    ),
    "preparation_contract_kernel": (
        Path(__file__).resolve().with_name("preparation_contract_kernel.py")
    ),
}


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


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


def _iso_date(value: Any, *, label: str) -> date:
    result = _text(value, label=label)
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", result) is None:
        raise ContractValidationError(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(result)
    except ValueError as exc:
        raise ContractValidationError(f"{label} must be an ISO date") from exc


def _optional_iso_date(value: Any, *, label: str) -> date | None:
    if value is None:
        return None
    return _iso_date(value, label=label)


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


def _exact_text_list(
    value: Any,
    *,
    expected: tuple[str, ...],
    label: str,
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractValidationError(f"{label} must be a list of text values")
    if value != list(expected):
        raise ContractValidationError(
            f"{label} must equal the registered ordered values"
        )
    return list(value)


def _require_constant(value: Any, *, expected: Any, label: str) -> None:
    if type(value) is not type(expected) or value != expected:
        raise ContractValidationError(f"{label} must equal {expected!r}")


def _current_dependency_sha256() -> dict[str, str]:
    """Return hashes for every file that can change intake validation behavior."""

    return {
        dependency_id: file_sha256(path)
        for dependency_id, path in sorted(INTAKE_VALIDATOR_DEPENDENCY_PATHS.items())
    }


def _validate_dependency_sha256(value: Any, *, label: str) -> dict[str, str]:
    dependencies = _mapping(value, label=label)
    _exact_fields(
        dependencies,
        required=frozenset(INTAKE_VALIDATOR_DEPENDENCY_PATHS),
        label=label,
    )
    expected = _current_dependency_sha256()
    validated: dict[str, str] = {}
    for dependency_id, expected_digest in expected.items():
        digest = _receipt_sha256(
            dependencies[dependency_id],
            label=f"{label}.{dependency_id}",
        )
        if digest != expected_digest:
            raise ContractValidationError(f"{label}.{dependency_id} is not current")
        validated[dependency_id] = digest
    return validated


def _current_date() -> date:
    """Return the CLI validation date through a testable time seam."""

    return date.today()


def _enclosing_git_worktree(path: Path) -> Path | None:
    resolved_path = Path(path).resolve()
    for candidate in (resolved_path, *resolved_path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def resolve_pilot_storage_roots(
    *,
    local_run_root: Path,
    repository_root: Path,
) -> tuple[Path, Path]:
    run_root = Path(local_run_root).resolve()
    repo_root = Path(repository_root).resolve()
    if not run_root.is_dir():
        raise ContractValidationError("local_run_root must be an existing directory")
    if not repo_root.is_dir() or not (repo_root / ".git").exists():
        raise ContractValidationError(
            "repository_root must identify an existing Git worktree"
        )
    enclosing_worktree = _enclosing_git_worktree(run_root)
    if enclosing_worktree is not None and enclosing_worktree != repo_root:
        raise ContractValidationError(
            "repository_root must match the Git worktree enclosing local_run_root"
        )
    return run_root, repo_root


def _require_git_ignored(path: Path, *, repository_root: Path, label: str) -> None:
    git_path = shutil.which("git")
    if git_path is None:
        raise ContractValidationError(
            f"{label} is inside the repository but Git is unavailable"
        )
    relative_path = path.relative_to(repository_root)
    # The executable is resolved locally and argv is fixed; no shell is used.
    result = subprocess.run(  # nosec B603
        [
            git_path,
            "-C",
            str(repository_root),
            "check-ignore",
            "--quiet",
            "--",
            str(relative_path),
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode == 1:
        raise ContractValidationError(
            f"{label} is inside the repository but is not Git-ignored"
        )
    if result.returncode != 0:
        raise ContractValidationError(
            f"Git could not verify the ignored status of {label}"
        )


def validate_pilot_local_run_path(
    path: Path,
    *,
    local_run_root: Path,
    repository_root: Path,
    label: str,
) -> tuple[Path, str]:
    resolved_path = Path(path).resolve()
    if not resolved_path.is_relative_to(local_run_root):
        raise ContractValidationError(
            f"{label} must resolve inside the declared local run root"
        )
    if resolved_path.is_file() and resolved_path.stat().st_nlink != 1:
        raise ContractValidationError(f"{label} must not be a hard-linked file")
    enclosing_worktree = _enclosing_git_worktree(resolved_path)
    if enclosing_worktree is not None and enclosing_worktree != repository_root:
        raise ContractValidationError(
            f"{label} must not be inside an undeclared Git worktree"
        )
    if enclosing_worktree == repository_root:
        _require_git_ignored(
            resolved_path,
            repository_root=repository_root,
            label=label,
        )
        return resolved_path, "inside_repository_git_ignored"
    return resolved_path, "outside_repository_within_run_root"


def validate_pilot_receipt_output_path(
    path: Path,
    *,
    declared_local_run_root: Path,
    local_run_root: Path,
    repository_root: Path,
    label: str,
) -> tuple[Path, str]:
    """Resolve one output path while rejecting symlinks below its declared root."""

    lexical_root = Path(declared_local_run_root).absolute()
    lexical_path = Path(path).absolute()
    if lexical_root.is_symlink():
        raise ContractValidationError("local_run_root must not identify a symlink")
    try:
        relative_parts = lexical_path.relative_to(lexical_root).parts
    except ValueError:
        relative_parts = ()
    cursor = lexical_root
    for part in relative_parts:
        cursor /= part
        if cursor.is_symlink():
            raise ContractValidationError(
                f"{label} must not use a symlink below local_run_root"
            )
    if lexical_path.is_symlink():
        raise ContractValidationError(f"{label} must not identify a symlink")
    return validate_pilot_local_run_path(
        lexical_path,
        local_run_root=local_run_root,
        repository_root=repository_root,
        label=label,
    )


def clear_owned_pilot_receipt_output(
    output_path: Path,
    *,
    schema_version: str,
    validator_id: str,
    required_fields: frozenset[str],
) -> None:
    """Remove only a positively identified prior receipt owned by this CLI."""

    output_path = Path(output_path)
    if not output_path.exists():
        return
    if not output_path.is_file() or output_path.stat().st_nlink != 1:
        raise ContractValidationError(
            "existing output must be one non-linked regular receipt file"
        )
    try:
        payload, _, _ = strict_json_snapshot(output_path)
        validator = _mapping(
            payload.get("validator"), label="existing output validator"
        )
    except (ContractValidationError, OSError, TypeError, ValueError) as exc:
        raise ContractValidationError(
            "existing output is not an owned prior receipt"
        ) from exc
    if (
        set(payload) != set(required_fields)
        or payload.get("schema_version") != schema_version
        or validator.get("validator_id") != validator_id
    ):
        raise ContractValidationError("existing output is not an owned prior receipt")
    output_path.unlink()


def _validate_source_declaration(value: Any) -> dict[str, Any]:
    source = _mapping(value, label="source")
    _exact_fields(
        source,
        required=frozenset(
            {
                "source_id",
                "data_kind",
                "data_classification",
                "media_type",
                "byte_count",
                "sha256",
            }
        ),
        label="source",
    )
    source_id = _opaque_identifier(
        source["source_id"],
        pattern=SOURCE_ID_PATTERN,
        label="source.source_id",
    )
    _require_constant(
        source["data_kind"],
        expected=SOURCE_KIND,
        label="source.data_kind",
    )
    data_classification = _text(
        source["data_classification"],
        label="source.data_classification",
    )
    if data_classification not in DATA_CLASSIFICATIONS:
        raise ContractValidationError(
            "source.data_classification must be anonymized_real or consented_real"
        )
    media_type = _text(source["media_type"], label="source.media_type")
    if media_type not in MEDIA_TYPES:
        raise ContractValidationError("source.media_type is not registered")
    byte_count = source["byte_count"]
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count <= 0
    ):
        raise ContractValidationError("source.byte_count must be a positive integer")
    digest = _text(source["sha256"], label="source.sha256")
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise ContractValidationError(
            "source.sha256 must be a lowercase SHA-256 digest"
        )

    return {
        "source_id": source_id,
        "data_kind": SOURCE_KIND,
        "data_classification": data_classification,
        "media_type": media_type,
        "byte_count": byte_count,
        "sha256": digest,
    }


def _bind_source_file(
    source: Mapping[str, Any],
    *,
    source_path: Path,
    local_run_root: Path,
) -> dict[str, Any]:
    source_path = Path(source_path)
    if not source_path.is_file():
        raise ContractValidationError("source path must identify one existing file")
    actual_byte_count, actual_digest = file_snapshot_beneath(
        source_path,
        root=local_run_root,
    )
    if source["byte_count"] != actual_byte_count:
        raise ContractValidationError(
            "source.byte_count does not match the exact supplied file"
        )
    if source["sha256"] != actual_digest:
        raise ContractValidationError("source.sha256 does not match the supplied file")
    return {
        "source_id": source["source_id"],
        "declared_data_kind": source["data_kind"],
        "declared_data_classification": source["data_classification"],
        "media_type": source["media_type"],
        "byte_count": source["byte_count"],
        "sha256": source["sha256"],
    }


def _validate_authorization(
    value: Any,
    *,
    source_sha256: str,
    as_of: date,
) -> dict[str, Any]:
    authorization = _mapping(value, label="authorization")
    _exact_fields(
        authorization,
        required=frozenset(
            {
                "status",
                "basis",
                "authority_assertion",
                "evidence_reference",
                "authorizing_role",
                "authorized_on",
                "valid_from",
                "valid_until",
                "purpose",
                "authorized_source_sha256",
                "permitted_actions",
                "prohibited_actions",
                "terms_summary",
            }
        ),
        label="authorization",
    )
    _require_constant(
        authorization["status"],
        expected="reviewed",
        label="authorization.status",
    )
    basis = _text(authorization["basis"], label="authorization.basis")
    if basis not in AUTHORIZATION_BASES:
        raise ContractValidationError("authorization.basis is not registered")
    _require_constant(
        authorization["authority_assertion"],
        expected="authorizer_has_right_to_permit_this_use",
        label="authorization.authority_assertion",
    )
    _text(
        authorization["evidence_reference"],
        label="authorization.evidence_reference",
    )
    _text(
        authorization["authorizing_role"],
        label="authorization.authorizing_role",
    )
    authorized_on = _iso_date(
        authorization["authorized_on"],
        label="authorization.authorized_on",
    )
    valid_from = _iso_date(
        authorization["valid_from"],
        label="authorization.valid_from",
    )
    valid_until = _optional_iso_date(
        authorization["valid_until"],
        label="authorization.valid_until",
    )
    if authorized_on > as_of:
        raise ContractValidationError(
            "authorization.authorized_on cannot follow the validation date"
        )
    if valid_from > as_of:
        raise ContractValidationError("authorization is not yet effective")
    if valid_until is not None and valid_until < valid_from:
        raise ContractValidationError(
            "authorization.valid_until cannot precede valid_from"
        )
    if valid_until is not None and valid_until < as_of:
        raise ContractValidationError("authorization has expired")
    _require_constant(
        authorization["purpose"],
        expected=PURPOSE,
        label="authorization.purpose",
    )
    _require_constant(
        authorization["authorized_source_sha256"],
        expected=source_sha256,
        label="authorization.authorized_source_sha256",
    )
    _exact_text_list(
        authorization["permitted_actions"],
        expected=PERMITTED_ACTIONS,
        label="authorization.permitted_actions",
    )
    _exact_text_list(
        authorization["prohibited_actions"],
        expected=PROHIBITED_ACTIONS,
        label="authorization.prohibited_actions",
    )
    _text(authorization["terms_summary"], label="authorization.terms_summary")
    return {
        "status": "declared_reviewed",
        "basis": basis,
        "authorized_on": authorized_on.isoformat(),
        "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat() if valid_until is not None else None,
        "purpose": PURPOSE,
        "authorized_source_sha256": source_sha256,
        "permitted_actions": list(PERMITTED_ACTIONS),
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "authorization_content_sha256": canonical_json_sha256(authorization),
        "assurance": ("declaration_bound_to_exact_source_not_independently_verified"),
    }


def _validate_privacy(value: Any) -> dict[str, Any]:
    privacy = _mapping(value, label="privacy")
    _exact_fields(
        privacy,
        required=frozenset(
            {
                "codex_context_acknowledged",
                "automatic_anonymization_claimed",
                "clara_external_recipient_added",
                "raw_and_row_level_storage",
                "repository_recording_policy",
            }
        ),
        label="privacy",
    )
    _require_constant(
        privacy["codex_context_acknowledged"],
        expected=True,
        label="privacy.codex_context_acknowledged",
    )
    _require_constant(
        privacy["automatic_anonymization_claimed"],
        expected=False,
        label="privacy.automatic_anonymization_claimed",
    )
    _require_constant(
        privacy["clara_external_recipient_added"],
        expected=False,
        label="privacy.clara_external_recipient_added",
    )
    _require_constant(
        privacy["raw_and_row_level_storage"],
        expected="local_run_root_only",
        label="privacy.raw_and_row_level_storage",
    )
    _require_constant(
        privacy["repository_recording_policy"],
        expected="sanitized_summary_and_receipts_only",
        label="privacy.repository_recording_policy",
    )
    return {
        "codex_context_acknowledged": True,
        "automatic_anonymization_claimed": False,
        "clara_external_recipient_added": False,
        "declared_raw_and_row_level_storage": "local_run_root_only",
        "repository_recording_policy": "sanitized_summary_and_receipts_only",
    }


def _validate_deidentification_review(
    value: Any,
    *,
    data_classification: str,
) -> dict[str, Any]:
    review = _mapping(value, label="deidentification_review")
    _exact_fields(
        review,
        required=frozenset(
            {
                "status",
                "basis",
                "reidentification_risk_review_status",
            }
        ),
        label="deidentification_review",
    )
    status = _text(review["status"], label="deidentification_review.status")
    risk_status = _text(
        review["reidentification_risk_review_status"],
        label="deidentification_review.reidentification_risk_review_status",
    )
    basis = _text(review["basis"], label="deidentification_review.basis")
    if data_classification == "anonymized_real":
        if status != "reviewed" or risk_status != "reviewed":
            raise ContractValidationError(
                "anonymized_real requires reviewed de-identification and "
                "re-identification-risk records"
            )
    elif (status, risk_status) not in {
        ("not_applicable", "not_applicable"),
        ("reviewed", "reviewed"),
    }:
        raise ContractValidationError(
            "consented_real de-identification and re-identification-risk "
            "review statuses must match"
        )
    return {
        "status": status,
        "reidentification_risk_review_status": risk_status,
        "review_content_sha256": canonical_json_sha256(review),
        "assurance": "review_presence_only_not_anonymization_certification",
        "basis_recorded": bool(basis),
    }


def _validate_semantic_review_plan(value: Any) -> dict[str, Any]:
    plan = _mapping(value, label="semantic_review_plan")
    _exact_fields(
        plan,
        required=frozenset(
            {
                "status",
                "required_reviews",
                "automatic_mapping_allowed",
                "unresolved_blocking_issues_block_preparation",
            }
        ),
        label="semantic_review_plan",
    )
    _require_constant(
        plan["status"],
        expected="pending",
        label="semantic_review_plan.status",
    )
    required_reviews = _exact_text_list(
        plan["required_reviews"],
        expected=REQUIRED_SEMANTIC_REVIEWS,
        label="semantic_review_plan.required_reviews",
    )
    _require_constant(
        plan["automatic_mapping_allowed"],
        expected=False,
        label="semantic_review_plan.automatic_mapping_allowed",
    )
    _require_constant(
        plan["unresolved_blocking_issues_block_preparation"],
        expected=True,
        label="semantic_review_plan.unresolved_blocking_issues_block_preparation",
    )
    return {
        "status": "not_assessed",
        "required_review_count": len(required_reviews),
        "automatic_mapping_allowed": False,
        "unresolved_blocking_issues_block_preparation": True,
    }


def _receipt_sha256(value: Any, *, label: str) -> str:
    digest = _text(value, label=label)
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise ContractValidationError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def validate_real_data_pilot_intake_receipt(value: Any) -> dict[str, Any]:
    """Validate every field in one sanitized intake receipt."""

    receipt = _mapping(value, label="intake receipt")
    _exact_fields(
        receipt,
        required=INTAKE_RECEIPT_FIELDS,
        label="intake receipt",
    )
    _require_constant(
        receipt["schema_version"],
        expected=INTAKE_RECEIPT_SCHEMA,
        label="intake receipt.schema_version",
    )
    _opaque_identifier(
        receipt["pilot_id"],
        pattern=PILOT_ID_PATTERN,
        label="intake receipt.pilot_id",
    )
    validation_date = _iso_date(
        receipt["validation_date"],
        label="intake receipt.validation_date",
    )
    _receipt_sha256(
        receipt["intake_contract_sha256"],
        label="intake receipt.intake_contract_sha256",
    )

    source = _mapping(receipt["source_receipt"], label="intake receipt.source_receipt")
    _exact_fields(
        source,
        required=frozenset(
            {
                "source_id",
                "declared_data_kind",
                "declared_data_classification",
                "media_type",
                "byte_count",
                "sha256",
            }
        ),
        label="intake receipt.source_receipt",
    )
    _opaque_identifier(
        source["source_id"],
        pattern=SOURCE_ID_PATTERN,
        label="intake receipt.source_receipt.source_id",
    )
    _require_constant(
        source["declared_data_kind"],
        expected=SOURCE_KIND,
        label="intake receipt.source_receipt.declared_data_kind",
    )
    data_classification = _text(
        source["declared_data_classification"],
        label="intake receipt.source_receipt.declared_data_classification",
    )
    if data_classification not in DATA_CLASSIFICATIONS:
        raise ContractValidationError(
            "intake receipt source classification is not registered"
        )
    media_type = _text(
        source["media_type"],
        label="intake receipt.source_receipt.media_type",
    )
    if media_type not in MEDIA_TYPES:
        raise ContractValidationError(
            "intake receipt source media_type is not registered"
        )
    byte_count = source["byte_count"]
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count <= 0
    ):
        raise ContractValidationError(
            "intake receipt source byte_count must be a positive integer"
        )
    _receipt_sha256(
        source["sha256"],
        label="intake receipt.source_receipt.sha256",
    )

    authorization = _mapping(
        receipt["authorization_receipt"],
        label="intake receipt.authorization_receipt",
    )
    _exact_fields(
        authorization,
        required=frozenset(
            {
                "status",
                "basis",
                "authorized_on",
                "valid_from",
                "valid_until",
                "purpose",
                "authorized_source_sha256",
                "permitted_actions",
                "prohibited_actions",
                "authorization_content_sha256",
                "assurance",
            }
        ),
        label="intake receipt.authorization_receipt",
    )
    _require_constant(
        authorization["status"],
        expected="declared_reviewed",
        label="intake receipt.authorization_receipt.status",
    )
    basis = _text(
        authorization["basis"],
        label="intake receipt.authorization_receipt.basis",
    )
    if basis not in AUTHORIZATION_BASES:
        raise ContractValidationError(
            "intake receipt authorization basis is not registered"
        )
    authorized_on = _iso_date(
        authorization["authorized_on"],
        label="intake receipt.authorization_receipt.authorized_on",
    )
    valid_from = _iso_date(
        authorization["valid_from"],
        label="intake receipt.authorization_receipt.valid_from",
    )
    valid_until = _optional_iso_date(
        authorization["valid_until"],
        label="intake receipt.authorization_receipt.valid_until",
    )
    if authorized_on > validation_date or valid_from > validation_date:
        raise ContractValidationError(
            "intake receipt authorization was not current at validation"
        )
    if valid_until is not None and (
        valid_until < valid_from or valid_until < validation_date
    ):
        raise ContractValidationError(
            "intake receipt authorization was expired at validation"
        )
    _require_constant(
        authorization["purpose"],
        expected=PURPOSE,
        label="intake receipt.authorization_receipt.purpose",
    )
    authorized_source_sha256 = _receipt_sha256(
        authorization["authorized_source_sha256"],
        label="intake receipt.authorization_receipt.authorized_source_sha256",
    )
    if authorized_source_sha256 != source["sha256"]:
        raise ContractValidationError(
            "intake receipt authorization is not bound to the source digest"
        )
    _exact_text_list(
        authorization["permitted_actions"],
        expected=PERMITTED_ACTIONS,
        label="intake receipt.authorization_receipt.permitted_actions",
    )
    _exact_text_list(
        authorization["prohibited_actions"],
        expected=PROHIBITED_ACTIONS,
        label="intake receipt.authorization_receipt.prohibited_actions",
    )
    _receipt_sha256(
        authorization["authorization_content_sha256"],
        label="intake receipt.authorization_receipt.authorization_content_sha256",
    )
    _require_constant(
        authorization["assurance"],
        expected="declaration_bound_to_exact_source_not_independently_verified",
        label="intake receipt.authorization_receipt.assurance",
    )

    privacy = _mapping(
        receipt["privacy_boundary"],
        label="intake receipt.privacy_boundary",
    )
    _exact_fields(
        privacy,
        required=frozenset(
            {
                "codex_context_acknowledged",
                "automatic_anonymization_claimed",
                "clara_external_recipient_added",
                "declared_raw_and_row_level_storage",
                "repository_recording_policy",
                "storage_location_check",
            }
        ),
        label="intake receipt.privacy_boundary",
    )
    for field, expected in (
        ("codex_context_acknowledged", True),
        ("automatic_anonymization_claimed", False),
        ("clara_external_recipient_added", False),
        ("declared_raw_and_row_level_storage", "local_run_root_only"),
        ("repository_recording_policy", "sanitized_summary_and_receipts_only"),
    ):
        _require_constant(
            privacy[field],
            expected=expected,
            label=f"intake receipt.privacy_boundary.{field}",
        )
    location = _mapping(
        privacy["storage_location_check"],
        label="intake receipt.privacy_boundary.storage_location_check",
    )
    _exact_fields(
        location,
        required=frozenset(
            {
                "status",
                "source_relation",
                "intake_relation",
                "resolved_path_containment_enforced",
                "git_ignore_required_inside_repository",
            }
        ),
        label="intake receipt.privacy_boundary.storage_location_check",
    )
    _require_constant(
        location["status"],
        expected="passed_at_validation",
        label="intake receipt storage status",
    )
    for field in ("source_relation", "intake_relation"):
        relation = _text(
            location[field],
            label=f"intake receipt storage {field}",
        )
        if relation not in STORAGE_RELATIONS:
            raise ContractValidationError(
                f"intake receipt storage {field} is not registered"
            )
    for field in (
        "resolved_path_containment_enforced",
        "git_ignore_required_inside_repository",
    ):
        _require_constant(
            location[field],
            expected=True,
            label=f"intake receipt storage {field}",
        )

    deidentification = _mapping(
        receipt["deidentification_review"],
        label="intake receipt.deidentification_review",
    )
    _exact_fields(
        deidentification,
        required=frozenset(
            {
                "status",
                "reidentification_risk_review_status",
                "review_content_sha256",
                "assurance",
                "basis_recorded",
            }
        ),
        label="intake receipt.deidentification_review",
    )
    deidentification_status = _text(
        deidentification["status"],
        label="intake receipt.deidentification_review.status",
    )
    risk_status = _text(
        deidentification["reidentification_risk_review_status"],
        label=(
            "intake receipt.deidentification_review."
            "reidentification_risk_review_status"
        ),
    )
    allowed_deidentification_pairs = {
        ("not_applicable", "not_applicable"),
        ("reviewed", "reviewed"),
    }
    if (deidentification_status, risk_status) not in allowed_deidentification_pairs:
        raise ContractValidationError(
            "intake receipt de-identification statuses must match"
        )
    if data_classification == "anonymized_real" and (
        deidentification_status,
        risk_status,
    ) != ("reviewed", "reviewed"):
        raise ContractValidationError(
            "anonymized intake receipt requires reviewed de-identification"
        )
    _receipt_sha256(
        deidentification["review_content_sha256"],
        label="intake receipt.deidentification_review.review_content_sha256",
    )
    _require_constant(
        deidentification["assurance"],
        expected="review_presence_only_not_anonymization_certification",
        label="intake receipt.deidentification_review.assurance",
    )
    _require_constant(
        deidentification["basis_recorded"],
        expected=True,
        label="intake receipt.deidentification_review.basis_recorded",
    )

    semantic = _mapping(
        receipt["semantic_review"],
        label="intake receipt.semantic_review",
    )
    _exact_fields(
        semantic,
        required=frozenset(
            {
                "status",
                "required_review_count",
                "automatic_mapping_allowed",
                "unresolved_blocking_issues_block_preparation",
            }
        ),
        label="intake receipt.semantic_review",
    )
    for field, expected in (
        ("status", "not_assessed"),
        ("required_review_count", len(REQUIRED_SEMANTIC_REVIEWS)),
        ("automatic_mapping_allowed", False),
        ("unresolved_blocking_issues_block_preparation", True),
    ):
        _require_constant(
            semantic[field],
            expected=expected,
            label=f"intake receipt.semantic_review.{field}",
        )

    eligibility = _mapping(
        receipt["eligibility"],
        label="intake receipt.eligibility",
    )
    _exact_fields(
        eligibility,
        required=frozenset(
            {
                "status",
                "purpose",
                "publication_status",
                "report_ready",
                "execution_revalidation_required",
                "does_not_establish",
            }
        ),
        label="intake receipt.eligibility",
    )
    for field, expected in (
        ("status", "declared_boundary_passed_for_local_pilot_intake"),
        ("purpose", PURPOSE),
        ("publication_status", "withheld"),
        ("report_ready", False),
        ("execution_revalidation_required", True),
    ):
        _require_constant(
            eligibility[field],
            expected=expected,
            label=f"intake receipt.eligibility.{field}",
        )
    _exact_text_list(
        eligibility["does_not_establish"],
        expected=DOES_NOT_ESTABLISH,
        label="intake receipt.eligibility.does_not_establish",
    )

    validator = _mapping(
        receipt["validator"],
        label="intake receipt.validator",
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
        label="intake receipt.validator",
    )
    _require_constant(
        validator["validator_id"],
        expected=VALIDATOR_ID,
        label="intake receipt.validator.validator_id",
    )
    _require_constant(
        validator["validator_version"],
        expected=VALIDATOR_VERSION,
        label="intake receipt.validator.validator_version",
    )
    implementation_sha256 = _receipt_sha256(
        validator["implementation_sha256"],
        label="intake receipt.validator.implementation_sha256",
    )
    if implementation_sha256 != file_sha256(Path(__file__).resolve()):
        raise ContractValidationError(
            "intake receipt validator implementation is not current"
        )
    _validate_dependency_sha256(
        validator["dependency_sha256"],
        label="intake receipt.validator.dependency_sha256",
    )
    _require_constant(
        validator["mode"],
        expected="deterministic_mechanical",
        label="intake receipt.validator.mode",
    )
    return dict(receipt)


def validate_real_data_pilot_intake(
    intake_path: Path,
    source_path: Path,
    *,
    as_of_date: str,
    local_run_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Return a source-bound intake receipt without reading accounting meaning."""

    run_root, repo_root = resolve_pilot_storage_roots(
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    intake_path, intake_relation = validate_pilot_local_run_path(
        intake_path,
        local_run_root=run_root,
        repository_root=repo_root,
        label="intake path",
    )
    source_path, source_relation = validate_pilot_local_run_path(
        source_path,
        local_run_root=run_root,
        repository_root=repo_root,
        label="source path",
    )
    if not intake_path.is_file():
        raise ContractValidationError("intake path must identify one existing file")
    intake, _, intake_contract_sha256 = strict_json_snapshot_beneath(
        intake_path,
        root=run_root,
    )
    _exact_fields(
        intake,
        required=frozenset(
            {
                "schema_version",
                "pilot_id",
                "purpose",
                "source",
                "authorization",
                "privacy",
                "deidentification_review",
                "semantic_review_plan",
                "publication_status",
                "report_ready",
            }
        ),
        label="intake",
    )
    _require_constant(
        intake["schema_version"],
        expected=INTAKE_SCHEMA,
        label="intake.schema_version",
    )
    pilot_id = _opaque_identifier(
        intake["pilot_id"],
        pattern=PILOT_ID_PATTERN,
        label="intake.pilot_id",
    )
    _require_constant(intake["purpose"], expected=PURPOSE, label="intake.purpose")
    source = _validate_source_declaration(intake["source"])
    as_of = _iso_date(as_of_date, label="as_of_date")
    authorization = _validate_authorization(
        intake["authorization"],
        source_sha256=source["sha256"],
        as_of=as_of,
    )
    privacy = _validate_privacy(intake["privacy"])
    deidentification_review = _validate_deidentification_review(
        intake["deidentification_review"],
        data_classification=source["data_classification"],
    )
    semantic_review = _validate_semantic_review_plan(intake["semantic_review_plan"])
    _require_constant(
        intake["publication_status"],
        expected="withheld",
        label="intake.publication_status",
    )
    _require_constant(
        intake["report_ready"],
        expected=False,
        label="intake.report_ready",
    )
    source_receipt = _bind_source_file(
        source,
        source_path=source_path,
        local_run_root=run_root,
    )
    privacy_boundary = {
        **privacy,
        "storage_location_check": {
            "status": "passed_at_validation",
            "source_relation": source_relation,
            "intake_relation": intake_relation,
            "resolved_path_containment_enforced": True,
            "git_ignore_required_inside_repository": True,
        },
    }

    receipt = {
        "schema_version": INTAKE_RECEIPT_SCHEMA,
        "pilot_id": pilot_id,
        "validation_date": as_of.isoformat(),
        "intake_contract_sha256": intake_contract_sha256,
        "source_receipt": source_receipt,
        "authorization_receipt": authorization,
        "privacy_boundary": privacy_boundary,
        "deidentification_review": deidentification_review,
        "semantic_review": semantic_review,
        "eligibility": {
            "status": "declared_boundary_passed_for_local_pilot_intake",
            "purpose": PURPOSE,
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
    return validate_real_data_pilot_intake_receipt(receipt)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate one intake contract and write its sanitized receipt."""

    parser = argparse.ArgumentParser(
        description="Validate Clara's real-data pilot intake boundary."
    )
    parser.add_argument("--intake", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
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
    source_path = args.source.resolve()
    intake_path = args.intake.resolve()
    if output_path in {source_path, intake_path}:
        raise ContractValidationError(
            "output path must not equal the source or intake path"
        )
    if not output_path.parent.is_dir():
        raise ContractValidationError(
            "output path parent must be an existing directory"
        )
    clear_owned_pilot_receipt_output(
        output_path,
        schema_version=INTAKE_RECEIPT_SCHEMA,
        validator_id=VALIDATOR_ID,
        required_fields=INTAKE_RECEIPT_FIELDS,
    )

    receipt = validate_real_data_pilot_intake(
        intake_path,
        source_path,
        as_of_date=_current_date().isoformat(),
        local_run_root=run_root,
        repository_root=repo_root,
    )
    write_json(output_path, receipt)
    LOGGER.info(
        "Real-data pilot intake %s: %s",
        receipt["pilot_id"],
        receipt["eligibility"]["status"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
