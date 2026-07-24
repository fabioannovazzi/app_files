#!/usr/bin/env python3
"""Protect and seal local producer outputs for Clara's real-data pilot.

These helpers are deterministic because output containment, alias prevention,
exact file sets, byte counts, and digests at the validation instant are
mechanically verifiable. The caller must stop every producer and writer before
sealing; no finite file-system scan can prove future quiescence. The caller
still owns the case-specific output-role declaration and every semantic
decision. No helper in this module interprets accounting data.
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from preparation_contract_kernel import (
    ContractValidationError,
    file_snapshot_beneath,
)
from validate_real_data_pilot_intake import (
    resolve_pilot_storage_roots,
    validate_pilot_local_run_path,
    validate_pilot_receipt_output_path,
)

__all__ = [
    "MECHANICAL_ERROR_ROLE",
    "create_fresh_pilot_output_directory",
    "seal_pilot_output_directory",
    "validate_pilot_output_receipts",
]

MECHANICAL_ERROR_ROLE = "mechanical_errors"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
OPAQUE_ARTIFACT_ROLE_PATTERN = re.compile(r"^artifact-[0-9a-f]{16}$")
OUTPUT_RECEIPT_FIELDS = frozenset(
    {
        "role",
        "relative_path",
        "byte_count",
        "sha256",
    }
)


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


def _output_role(value: Any, *, label: str) -> str:
    role = _identifier(value, label=label)
    if (
        role != MECHANICAL_ERROR_ROLE
        and OPAQUE_ARTIFACT_ROLE_PATTERN.fullmatch(role) is None
    ):
        raise ContractValidationError(
            f"{label} must be mechanical_errors or an opaque artifact role"
        )
    return role


def _relative_path(value: Any, *, label: str) -> PurePosixPath:
    text = _text(value, label=label)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ContractValidationError(
            f"{label} must be a canonical relative POSIX path"
        )
    return path


def _validate_output_leaf(
    output_directory: Path,
    *,
    declared_local_run_root: Path,
    local_run_root: Path,
    repository_root: Path,
) -> Path:
    output_path, _ = validate_pilot_receipt_output_path(
        output_directory,
        declared_local_run_root=declared_local_run_root,
        local_run_root=local_run_root,
        repository_root=repository_root,
        label="producer output directory",
    )
    if output_path == local_run_root:
        raise ContractValidationError(
            "producer output directory must be a dedicated leaf below local_run_root"
        )
    return output_path


def _validated_input_files(
    input_paths: Sequence[Path],
    *,
    local_run_root: Path,
    repository_root: Path,
) -> list[Path]:
    if (
        isinstance(input_paths, (str, bytes))
        or not isinstance(input_paths, Sequence)
        or not input_paths
    ):
        raise ContractValidationError(
            "input_paths must be a non-empty sequence of existing files"
        )

    validated: list[Path] = []
    for position, raw_input_path in enumerate(input_paths):
        if not isinstance(raw_input_path, Path):
            raise ContractValidationError(
                f"input_paths[{position}] must identify an existing file"
            )
        input_path, _ = validate_pilot_local_run_path(
            raw_input_path,
            local_run_root=local_run_root,
            repository_root=repository_root,
            label=f"input_paths[{position}]",
        )
        if not input_path.is_file():
            raise ContractValidationError(
                f"input_paths[{position}] must identify an existing file"
            )
        validated.append(input_path)

    canonical_paths = [path.as_posix() for path in validated]
    if canonical_paths != sorted(canonical_paths):
        raise ContractValidationError("input_paths must be sorted by resolved path")
    if len(set(canonical_paths)) != len(canonical_paths):
        raise ContractValidationError("input_paths must identify unique resolved files")
    return validated


def _require_no_input_aliases(
    output_path: Path,
    input_paths: Sequence[Path],
) -> None:
    for input_path in input_paths:
        if (
            output_path == input_path
            or output_path.is_relative_to(input_path)
            or input_path.is_relative_to(output_path)
        ):
            raise ContractValidationError(
                "producer output directory must not alias or contain an input"
            )


def create_fresh_pilot_output_directory(
    output_directory: Path,
    *,
    local_run_root: Path,
    repository_root: Path,
    input_paths: Sequence[Path],
) -> Path:
    """Create one fresh output leaf after containment and alias checks."""

    run_root, repo_root = resolve_pilot_storage_roots(
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    output_path = _validate_output_leaf(
        output_directory,
        declared_local_run_root=local_run_root,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    if output_path.exists() or output_path.is_symlink():
        raise ContractValidationError(
            "producer output directory must not already exist"
        )
    if not output_path.parent.is_dir():
        raise ContractValidationError(
            "producer output directory parent must be an existing directory"
        )

    validated_inputs = _validated_input_files(
        input_paths,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    _require_no_input_aliases(output_path, validated_inputs)

    output_path.mkdir(mode=0o700)
    revalidated_output_path = _validate_output_leaf(
        output_directory,
        declared_local_run_root=local_run_root,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    if revalidated_output_path != output_path:
        raise ContractValidationError(
            "producer output directory changed while it was being created"
        )
    revalidated_inputs = _validated_input_files(
        input_paths,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    if revalidated_inputs != validated_inputs:
        raise ContractValidationError(
            "input_paths changed while the output directory was being created"
        )
    _require_no_input_aliases(revalidated_output_path, revalidated_inputs)
    _require_private_output_directory(revalidated_output_path)
    return revalidated_output_path


def _registered_output_paths(
    expected_roles: Mapping[str, str],
) -> dict[str, PurePosixPath]:
    if not isinstance(expected_roles, Mapping) or not expected_roles:
        raise ContractValidationError("expected_roles must be a non-empty object")
    registered: dict[str, PurePosixPath] = {}
    seen_paths: set[PurePosixPath] = set()
    for raw_role, raw_path in expected_roles.items():
        role = _output_role(raw_role, label="expected_roles key")
        relative_path = _relative_path(
            raw_path,
            label=f"expected_roles.{role}",
        )
        expected_path = (
            PurePosixPath("mechanical_errors.json")
            if role == MECHANICAL_ERROR_ROLE
            else PurePosixPath("artifacts") / f"{role}.bin"
        )
        if relative_path != expected_path:
            raise ContractValidationError(
                f"expected_roles.{role} must use its registered generic path"
            )
        if relative_path in seen_paths:
            raise ContractValidationError(
                "expected_roles must assign each relative path once"
            )
        registered[role] = relative_path
        seen_paths.add(relative_path)
    if MECHANICAL_ERROR_ROLE not in registered:
        raise ContractValidationError(
            "expected_roles must register the mechanical_errors output"
        )
    return registered


def _actual_output_tree(output_directory: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()
    for path in output_directory.rglob("*"):
        if path.is_symlink():
            raise ContractValidationError(
                "producer output directory must not contain symlinks"
            )
        relative_path = path.relative_to(output_directory).as_posix()
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise ContractValidationError(
                    "producer output directory must not contain hard-linked files"
                )
            files.add(relative_path)
        elif path.is_dir():
            directories.add(relative_path)
        else:
            raise ContractValidationError(
                "producer output directory contains an unsupported filesystem entry"
            )
    return files, directories


def _require_private_output_directory(output_directory: Path) -> None:
    status = output_directory.stat()
    if stat.S_IMODE(status.st_mode) != 0o700:
        raise ContractValidationError("producer output directory must have mode 0700")
    if hasattr(os, "getuid") and status.st_uid != os.getuid():
        raise ContractValidationError(
            "producer output directory must be owned by the current user"
        )


def _expected_directories(paths: set[str]) -> set[str]:
    directories: set[str] = set()
    for raw_path in paths:
        parent = PurePosixPath(raw_path).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def seal_pilot_output_directory(
    output_directory: Path,
    *,
    expected_roles: Mapping[str, str],
    local_run_root: Path,
    repository_root: Path,
) -> list[dict[str, Any]]:
    """Snapshot one exact output tree after the caller has stopped its writers."""

    run_root, repo_root = resolve_pilot_storage_roots(
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    output_path = _validate_output_leaf(
        output_directory,
        declared_local_run_root=local_run_root,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    if not output_path.is_dir():
        raise ContractValidationError(
            "producer output directory must identify one existing directory"
        )
    _require_private_output_directory(output_path)
    registered = _registered_output_paths(expected_roles)
    expected_files = {path.as_posix() for path in registered.values()}
    actual_files, actual_directories = _actual_output_tree(output_path)
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        unexpected = sorted(actual_files - expected_files)
        raise ContractValidationError(
            "producer output file set does not match the registered roles: "
            f"missing={missing}, unexpected={unexpected}"
        )
    expected_directories = _expected_directories(expected_files)
    if actual_directories != expected_directories:
        missing = sorted(expected_directories - actual_directories)
        unexpected = sorted(actual_directories - expected_directories)
        raise ContractValidationError(
            "producer output directory set does not match the registered roles: "
            f"missing={missing}, unexpected={unexpected}"
        )

    receipts: list[dict[str, Any]] = []
    for role, relative_path in sorted(registered.items()):
        artifact_path, _ = validate_pilot_receipt_output_path(
            output_path / Path(relative_path.as_posix()),
            declared_local_run_root=output_path,
            local_run_root=run_root,
            repository_root=repo_root,
            label=f"producer output {role}",
        )
        byte_count, digest = file_snapshot_beneath(
            artifact_path,
            root=run_root,
        )
        receipts.append(
            {
                "role": role,
                "relative_path": relative_path.as_posix(),
                "byte_count": byte_count,
                "sha256": digest,
            }
        )
    final_files, final_directories = _actual_output_tree(output_path)
    if final_files != actual_files or final_directories != actual_directories:
        raise ContractValidationError(
            "producer output tree changed while it was being sealed"
        )
    for receipt in receipts:
        artifact_path, _ = validate_pilot_receipt_output_path(
            output_path / receipt["relative_path"],
            declared_local_run_root=output_path,
            local_run_root=run_root,
            repository_root=repo_root,
            label=f"producer output {receipt['role']}",
        )
        byte_count, digest = file_snapshot_beneath(
            artifact_path,
            root=run_root,
        )
        if byte_count != receipt["byte_count"] or digest != receipt["sha256"]:
            raise ContractValidationError(
                "producer output bytes changed while they were being sealed"
            )
    revalidated_output_path = _validate_output_leaf(
        output_directory,
        declared_local_run_root=local_run_root,
        local_run_root=run_root,
        repository_root=repo_root,
    )
    if revalidated_output_path != output_path:
        raise ContractValidationError(
            "producer output directory changed while it was being sealed"
        )
    _require_private_output_directory(revalidated_output_path)
    final_files, final_directories = _actual_output_tree(revalidated_output_path)
    if final_files != actual_files or final_directories != actual_directories:
        raise ContractValidationError(
            "producer output tree changed while it was being sealed"
        )
    return receipts


def validate_pilot_output_receipts(
    receipts: Any,
    output_directory: Path,
    *,
    local_run_root: Path,
    repository_root: Path,
) -> list[dict[str, Any]]:
    """Rehash one sealed output tree and reject receipt or byte drift."""

    if not isinstance(receipts, list) or not receipts:
        raise ContractValidationError("output receipts must be a non-empty list")
    expected_roles: dict[str, str] = {}
    normalized: list[dict[str, Any]] = []
    for position, raw_receipt in enumerate(receipts):
        if not isinstance(raw_receipt, Mapping):
            raise ContractValidationError(
                f"output receipts[{position}] must be an object"
            )
        missing = sorted(OUTPUT_RECEIPT_FIELDS - set(raw_receipt))
        unexpected = sorted(set(raw_receipt) - OUTPUT_RECEIPT_FIELDS)
        if missing or unexpected:
            raise ContractValidationError(
                f"output receipts[{position}] has invalid fields: "
                f"missing={missing}, unexpected={unexpected}"
            )
        role = _output_role(
            raw_receipt["role"],
            label=f"output receipts[{position}].role",
        )
        relative_path = _relative_path(
            raw_receipt["relative_path"],
            label=f"output receipts[{position}].relative_path",
        ).as_posix()
        byte_count = raw_receipt["byte_count"]
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
        ):
            raise ContractValidationError(
                f"output receipts[{position}].byte_count must be nonnegative"
            )
        digest = _text(
            raw_receipt["sha256"],
            label=f"output receipts[{position}].sha256",
        )
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ContractValidationError(
                f"output receipts[{position}].sha256 must be a SHA-256 digest"
            )
        if role in expected_roles:
            raise ContractValidationError("output receipts must contain unique roles")
        expected_roles[role] = relative_path
        normalized.append(
            {
                "role": role,
                "relative_path": relative_path,
                "byte_count": byte_count,
                "sha256": digest,
            }
        )
    if [receipt["role"] for receipt in normalized] != sorted(expected_roles):
        raise ContractValidationError("output receipts must be sorted by unique role")

    current = seal_pilot_output_directory(
        output_directory,
        expected_roles=expected_roles,
        local_run_root=local_run_root,
        repository_root=repository_root,
    )
    if current != normalized:
        raise ContractValidationError(
            "output receipts do not match the current output bytes"
        )
    return normalized
