"""Exact transitive implementation receipts for Report Builder assurance.

The contract covers code and UI assets that can parse, calculate, serialize,
render, authorize, or close an assured Report Builder run.  Byte identity and
set membership are consistency controls; they do not establish professional
correctness of the implementation or its conclusions.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from .implementation_bootstrap import (
        IMPLEMENTATION_CONTRACT,
        validate_implementation_tree,
    )
except ImportError:  # pragma: no cover - direct script/importlib support
    from implementation_bootstrap import (  # type: ignore
        IMPLEMENTATION_CONTRACT,
        validate_implementation_tree,
    )

__all__ = [
    "PLUGIN_IMPLEMENTATION_PATHS",
    "SHARED_IMPLEMENTATION_PATHS",
    "build_implementation_receipts",
    "implementation_artifact_roots",
    "validate_implementation_contract",
]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SHARED_ROOT = (
    PLUGIN_ROOT / "vendor" / "modules" / "vera_assurance"
    if (PLUGIN_ROOT / "vendor" / "modules" / "vera_assurance").is_dir()
    else PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules" / "vera_assurance"
)

PLUGIN_IMPLEMENTATION_PATHS = (
    ".codex-plugin/plugin.json",
    ".app.json",
    ".mcp.json",
    "assets/icon.svg",
    "assets/report-builder-review-widget.html",
    "assets/review-workbench-adapter.json",
    "mcp/server.cjs",
    "scripts/apply_review_edits.py",
    "scripts/build_report.py",
    "scripts/check_dependencies.py",
    "scripts/implementation_bootstrap.py",
    "scripts/implementation_contract.py",
    "scripts/inspect_inputs.py",
    "scripts/physical_output_set.py",
    "scripts/prepared_contract.py",
    "scripts/report_builder_core.py",
    "scripts/report_builder_integrity.py",
    "scripts/report_gates.py",
    "scripts/review_successor.py",
    "scripts/review_numeric_measures.py",
    "scripts/review_session.py",
    "scripts/seal_review_integrity.py",
    "scripts/validate_review_integrity.py",
)
SHARED_IMPLEMENTATION_PATHS = (
    "__init__.py",
    "contracts.py",
    "decisions.py",
    "envelope.py",
    "money.py",
    "relationships.py",
    "review_output_transaction.cjs",
    "serialization.py",
)


def implementation_artifact_roots() -> dict[str, Path]:
    """Return the roots used by the persisted implementation receipts."""

    return {
        "implementation": PLUGIN_ROOT,
        "assurance_implementation": SHARED_ROOT,
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
    declared_contract = (
        *(("plugin", path) for path in PLUGIN_IMPLEMENTATION_PATHS),
        *(("shared_assurance", path) for path in SHARED_IMPLEMENTATION_PATHS),
    )
    if declared_contract != IMPLEMENTATION_CONTRACT:
        raise RuntimeError(
            "Report Builder receipt and execution-boundary contracts diverged."
        )
    return [
        {
            "artifact_id": _artifact_id("report_builder", relative_path),
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


def _ordinary_file(root: Path, relative_path: str) -> Path:
    root_entry = root.lstat()
    if not stat.S_ISDIR(root_entry.st_mode) or stat.S_ISLNK(root_entry.st_mode):
        raise ValueError("Report Builder implementation root must be a real directory.")
    current = root
    parts = Path(relative_path).parts
    for index, part in enumerate(parts):
        current = current / part
        observed = current.lstat()
        if stat.S_ISLNK(observed.st_mode):
            raise ValueError(
                "Report Builder implementation contract cannot contain symlinks."
            )
        if index < len(parts) - 1:
            if not stat.S_ISDIR(observed.st_mode):
                raise ValueError(
                    "Report Builder implementation parent must be a directory."
                )
            continue
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise ValueError(
                "Report Builder implementation must be an ordinary single-link " "file."
            )
    return current


def _snapshot(path: Path) -> tuple[int, str]:
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        content = handle.read()
        after = os.fstat(handle.fileno())
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        or len(content) != after.st_size
    ):
        raise ValueError(
            "Report Builder implementation changed while its receipt was read."
        )
    return len(content), hashlib.sha256(content).hexdigest()


def build_implementation_receipts() -> list[dict[str, Any]]:
    """Receipt the exact transitive implementation set in canonical order."""

    roots = implementation_artifact_roots()
    validate_implementation_tree(
        str(roots["implementation"]),
        shared_assurance_root=str(roots["assurance_implementation"]),
    )
    receipts: list[dict[str, Any]] = []
    for specification in _specifications():
        path = _ordinary_file(
            roots[specification["root_id"]],
            specification["path"],
        )
        byte_count, digest = _snapshot(path)
        receipts.append(
            {
                **specification,
                "role": "implementation",
                "byte_count": byte_count,
                "sha256": digest,
            }
        )
    return receipts


def validate_implementation_contract(
    implementation_artifact_refs: object,
    implementation_receipts: object,
    *,
    artifact_roots: Mapping[str, Path] | None = None,
) -> list[dict[str, Any]]:
    """Replay the exact ordered receipt set and reject aliases or expansion."""

    if not isinstance(implementation_artifact_refs, Sequence) or isinstance(
        implementation_artifact_refs, (str, bytes, bytearray)
    ):
        raise ValueError("Report Builder implementation references are missing.")
    if not isinstance(implementation_receipts, Sequence) or isinstance(
        implementation_receipts, (str, bytes, bytearray)
    ):
        raise ValueError("Report Builder implementation receipts are missing.")
    specifications = _specifications()
    expected_ids = [specification["artifact_id"] for specification in specifications]
    if list(implementation_artifact_refs) != expected_ids:
        raise ValueError("Report Builder implementation reference set is not exact.")
    receipts = [
        receipt
        for receipt in implementation_receipts
        if isinstance(receipt, Mapping) and receipt.get("role") == "implementation"
    ]
    if len(receipts) != len(specifications):
        raise ValueError("Report Builder implementation receipt set is not exact.")
    if [receipt.get("artifact_id") for receipt in receipts] != expected_ids:
        raise ValueError("Report Builder implementation receipt order is not exact.")
    receipt_by_id = {str(receipt.get("artifact_id")): receipt for receipt in receipts}
    if len(receipt_by_id) != len(receipts) or set(receipt_by_id) != set(expected_ids):
        raise ValueError(
            "Report Builder implementation receipt identities are not exact."
        )
    roots = dict(artifact_roots or implementation_artifact_roots())
    if set(roots) != {"implementation", "assurance_implementation"}:
        raise ValueError("Report Builder implementation roots are not exact.")
    validate_implementation_tree(
        str(roots["implementation"]),
        shared_assurance_root=str(roots["assurance_implementation"]),
    )
    validated: list[dict[str, Any]] = []
    for specification in specifications:
        receipt = receipt_by_id[specification["artifact_id"]]
        expected_fields = {
            **specification,
            "role": "implementation",
        }
        if any(receipt.get(key) != value for key, value in expected_fields.items()):
            raise ValueError(
                "Report Builder implementation receipt contract is malformed."
            )
        path = _ordinary_file(
            roots[specification["root_id"]],
            specification["path"],
        )
        byte_count, digest = _snapshot(path)
        if receipt.get("byte_count") != byte_count or receipt.get("sha256") != digest:
            raise ValueError(
                "Report Builder implementation receipt does not match current "
                f"bytes: {specification['artifact_id']}"
            )
        validated.append(dict(receipt))
    return validated
