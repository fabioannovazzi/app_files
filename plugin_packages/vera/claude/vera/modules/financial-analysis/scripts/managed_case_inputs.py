#!/usr/bin/env python3
"""Resolve case-declared local inputs without opening the declared files."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = ["ManagedCaseInputError", "declared_case_input_paths"]

_FILE_KEYS: Mapping[str, tuple[str, ...]] = {
    "monthly_pnl": (
        "synthetic_monthly_trial_balance",
        "reviewed_coa_mapping",
        "public_statement_facts",
    ),
    "working_capital": (
        "public_working_capital_facts",
        "reviewed_working_capital_policy",
    ),
    "customer_concentration": (
        "exact_extracted_facts",
        "exact_control_facts",
    ),
}
_FDD_PACK_IDS = frozenset(
    {
        "quality_of_earnings",
        "net_debt",
        "normalized_working_capital",
        "capex",
        "deal_bridges",
    }
)


class ManagedCaseInputError(ValueError):
    """Raised when a managed case cannot identify its nested local inputs."""


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManagedCaseInputError(f"case JSON contains duplicate field: {key}")
        result[key] = value
    return result


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ManagedCaseInputError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ManagedCaseInputError(f"{label} must be an array")
    return value


def _load_case(case_path: Path) -> tuple[Path, Mapping[str, Any]]:
    resolved = Path(case_path).resolve()
    try:
        value = json.loads(
            resolved.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagedCaseInputError(f"case JSON is unreadable: {exc}") from exc
    return resolved, _mapping(value, label="case")


def _declared_path(root: Path, value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ManagedCaseInputError(f"{label} must be a non-empty path")
    if "\\" in value:
        raise ManagedCaseInputError(f"{label} must use POSIX separators")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {".", ".."} for part in relative.parts)
    ):
        raise ManagedCaseInputError(f"{label} must be a canonical relative path")
    return root.joinpath(*relative.parts)


def _file_input_paths(
    case: Mapping[str, Any],
    *,
    case_root: Path,
    pack_id: str,
) -> tuple[Path, ...]:
    files = _mapping(case.get("files"), label="case.files")
    required = _FILE_KEYS[pack_id]
    if set(files) != set(required):
        raise ManagedCaseInputError(
            f"case.files must contain exactly {sorted(required)} for {pack_id}"
        )
    paths: list[Path] = []
    for file_id in required:
        receipt = _mapping(files[file_id], label=f"case.files.{file_id}")
        paths.append(
            _declared_path(
                case_root,
                receipt.get("path"),
                label=f"case.files.{file_id}.path",
            )
        )
    return tuple(paths)


def _fdd_source_paths(
    bundle: Mapping[str, Any], *, case_root: Path
) -> tuple[Path, ...]:
    package = _mapping(bundle.get("package"), label="case.package")
    sources = _sequence(package.get("sources"), label="case.package.sources")
    if not sources:
        raise ManagedCaseInputError("case.package.sources must not be empty")
    paths: list[Path] = []
    for index, raw_source in enumerate(sources):
        source = _mapping(raw_source, label=f"case.package.sources[{index}]")
        paths.append(
            _declared_path(
                case_root,
                source.get("locator"),
                label=f"case.package.sources[{index}].locator",
            )
        )
    return tuple(paths)


def declared_case_input_paths(case_path: Path, pack_id: str) -> tuple[Path, ...]:
    """Return every nested local input declared by an authorized pack case.

    The returned paths are lexical candidates. Callers must pass all of them to
    ``validate_client_workflow_run`` before any engine opens or hashes them.
    """

    resolved_case, case = _load_case(case_path)
    if pack_id in _FILE_KEYS:
        return _file_input_paths(
            case,
            case_root=resolved_case.parent,
            pack_id=pack_id,
        )
    if pack_id in _FDD_PACK_IDS:
        return _fdd_source_paths(case, case_root=resolved_case.parent)
    raise ManagedCaseInputError(f"unsupported financial-analysis pack: {pack_id}")
