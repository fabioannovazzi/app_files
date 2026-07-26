"""Exact transitive implementation contract for Check Entries assurance.

The contract lists code and UI assets that can parse, calculate, serialize,
render, authorize, or close an assured Check Entries run.  File membership and
byte identity are deterministic controls; they do not establish that the code
is correct or that its accounting conclusions are professionally sufficient.
"""

from __future__ import annotations

import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import vera_assurance as vera_assurance_package
from implementation_bootstrap import (
    IMPLEMENTATION_CONTRACT,
    validate_implementation_tree,
)
from vera_assurance import artifact_receipt, validate_artifact_receipt

__all__ = [
    "PLUGIN_IMPLEMENTATION_PATHS",
    "SHARED_IMPLEMENTATION_PATHS",
    "build_implementation_receipts",
    "implementation_artifact_roots",
    "validate_implementation_contract",
]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ASSURANCE_IMPLEMENTATION_ROOT = Path(vera_assurance_package.__file__).resolve().parent

PLUGIN_IMPLEMENTATION_PATHS = tuple(
    path for root_id, path in IMPLEMENTATION_CONTRACT if root_id == "implementation"
)
SHARED_IMPLEMENTATION_PATHS = tuple(
    path
    for root_id, path in IMPLEMENTATION_CONTRACT
    if root_id == "assurance_implementation"
)


def implementation_artifact_roots() -> dict[str, Path]:
    """Return the two implementation roots used by the assurance envelope."""

    return {
        "implementation": PLUGIN_ROOT,
        "assurance_implementation": ASSURANCE_IMPLEMENTATION_ROOT,
    }


def _media_type(relative_path: str) -> str:
    suffix = Path(relative_path).suffix.lower()
    return {
        ".cjs": "text/javascript",
        ".html": "text/html",
        ".json": "application/json",
        ".py": "text/x-python",
        ".svg": "image/svg+xml",
    }[suffix]


def _artifact_id(namespace: str, relative_path: str) -> str:
    return f"implementation.{namespace}.{relative_path.replace('/', '.')}"


def _specifications() -> list[dict[str, str]]:
    return [
        {
            "artifact_id": _artifact_id("check_entries", relative_path),
            "root_id": "implementation",
            "path": relative_path,
            "media_type": _media_type(relative_path),
        }
        for relative_path in PLUGIN_IMPLEMENTATION_PATHS
    ] + [
        {
            "artifact_id": _artifact_id("vera_assurance", relative_path),
            "root_id": "assurance_implementation",
            "path": relative_path,
            "media_type": _media_type(relative_path),
        }
        for relative_path in SHARED_IMPLEMENTATION_PATHS
    ]


def _validate_ordinary_file(root: Path, relative_path: str) -> Path:
    root_entry = root.lstat()
    if not stat.S_ISDIR(root_entry.st_mode) or stat.S_ISLNK(root_entry.st_mode):
        raise ValueError("Check Entries implementation root must be a real directory.")
    current = root
    parts = Path(relative_path).parts
    for index, part in enumerate(parts):
        current = current / part
        observed = current.lstat()
        if stat.S_ISLNK(observed.st_mode):
            raise ValueError(
                "Check Entries implementation contract cannot contain symlinks."
            )
        if index < len(parts) - 1:
            if not stat.S_ISDIR(observed.st_mode):
                raise ValueError(
                    "Check Entries implementation parent must be a directory."
                )
            continue
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise ValueError(
                "Check Entries implementation must be an ordinary single-link file."
            )
    return current


def build_implementation_receipts() -> list[dict[str, Any]]:
    """Receipt the exact transitive implementation set in canonical order."""

    roots = implementation_artifact_roots()
    validate_implementation_tree(
        str(roots["implementation"]),
        shared_assurance_root=str(roots["assurance_implementation"]),
    )
    receipts: list[dict[str, Any]] = []
    for specification in _specifications():
        path = _validate_ordinary_file(
            roots[specification["root_id"]],
            specification["path"],
        )
        receipts.append(
            artifact_receipt(
                roots[specification["root_id"]],
                path,
                artifact_id=specification["artifact_id"],
                root_id=specification["root_id"],
                role="implementation",
                media_type=specification["media_type"],
            )
        )
    return receipts


def validate_implementation_contract(
    envelope: Mapping[str, Any],
    *,
    artifact_roots: Mapping[str, Path] | None = None,
) -> list[dict[str, Any]]:
    """Replay the exact implementation receipt set and reject aliases."""

    raw_receipts = envelope.get("artifact_receipts")
    raw_references = envelope.get("implementation_artifact_refs")
    if not isinstance(raw_receipts, Sequence) or isinstance(
        raw_receipts, (str, bytes, bytearray)
    ):
        raise ValueError("Check Entries implementation receipts are missing.")
    if not isinstance(raw_references, Sequence) or isinstance(
        raw_references, (str, bytes, bytearray)
    ):
        raise ValueError("Check Entries implementation references are missing.")
    specifications = _specifications()
    expected_ids = [specification["artifact_id"] for specification in specifications]
    if list(raw_references) != expected_ids:
        raise ValueError("Check Entries implementation reference set is not exact.")
    implementation_receipts = [
        receipt
        for receipt in raw_receipts
        if isinstance(receipt, Mapping) and receipt.get("role") == "implementation"
    ]
    if len(implementation_receipts) != len(specifications):
        raise ValueError("Check Entries implementation receipt set is not exact.")
    if [
        receipt.get("artifact_id") for receipt in implementation_receipts
    ] != expected_ids:
        raise ValueError("Check Entries implementation receipt order is not canonical.")
    receipt_by_id = {
        str(receipt.get("artifact_id")): receipt for receipt in implementation_receipts
    }
    if set(receipt_by_id) != set(expected_ids):
        raise ValueError(
            "Check Entries implementation receipt identities are not exact."
        )
    roots = dict(artifact_roots or implementation_artifact_roots())
    try:
        validate_implementation_tree(
            str(roots["implementation"]),
            shared_assurance_root=str(roots["assurance_implementation"]),
        )
    except (KeyError, OSError, RuntimeError) as exc:
        raise ValueError(str(exc)) from exc
    validated: list[dict[str, Any]] = []
    for specification in specifications:
        receipt = receipt_by_id[specification["artifact_id"]]
        for field_name in ("artifact_id", "root_id", "path", "media_type"):
            if receipt.get(field_name) != specification[field_name]:
                raise ValueError(
                    "Check Entries implementation receipt contract is malformed."
                )
        if receipt.get("role") != "implementation":
            raise ValueError("Check Entries implementation receipt role is malformed.")
        _validate_ordinary_file(
            roots[specification["root_id"]],
            specification["path"],
        )
        validated.append(validate_artifact_receipt(roots, receipt))
    return validated
