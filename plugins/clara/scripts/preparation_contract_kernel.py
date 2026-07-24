#!/usr/bin/env python3
"""Mechanical primitives for Clara preparation audit contracts.

The functions in this module are deterministic because their correctness is
mechanically verifiable and auditability requires byte-for-byte reproduction.
They validate syntax, exact Decimal handling, local file receipts, references,
and status consistency. They deliberately do not select sources, interpret
business meaning, approve reviewed decisions, choose tolerances, define
financial formulas, or decide whether an analysis is economically valid.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext
from pathlib import Path
from typing import Any

__all__ = [
    "AUDIT_ENVELOPE_SCHEMA",
    "ContractValidationError",
    "ExactDecimalPolicy",
    "artifact_receipt",
    "canonical_json_bytes",
    "canonical_json_sha256",
    "decimal_text",
    "difference_within_tolerance",
    "exact_decimal_context",
    "file_snapshot",
    "file_snapshot_beneath",
    "file_sha256",
    "is_on_increment",
    "parse_decimal",
    "read_exact_csv",
    "reference_set",
    "resolve_local_file",
    "reviewed_decision_receipt",
    "strict_json_load",
    "strict_json_load_bytes",
    "strict_json_snapshot",
    "strict_json_snapshot_beneath",
    "validate_audit_envelope",
    "validate_declared_source_receipt",
    "write_json",
]

AUDIT_ENVELOPE_SCHEMA = "clara.preparation_audit_envelope.v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "case",
        "adapter",
        "local_artifacts",
        "remote_sources",
        "reviewed_decisions",
        "execution",
        "numeric_policy",
        "reconciliation",
        "lineage",
        "statuses",
        "report_ready",
        "limitations",
    }
)
REFERENCE_FIELDS = frozenset(
    {"artifact_refs", "source_refs", "decision_refs", "lineage_refs"}
)
STATUS_FIELDS = frozenset(
    {
        "validation",
        "preparation",
        "reconciliation",
        "semantic",
        "source",
        "downstream",
        "publication",
    }
)


class ContractValidationError(ValueError):
    """Raised when a mechanical preparation contract is invalid."""


@dataclass(frozen=True)
class ExactDecimalPolicy:
    """Apply optional case-owned bounds during exact Decimal handling."""

    max_digits: int | None = None
    max_scale: int | None = None
    calculation_precision: int | None = None

    def __post_init__(self) -> None:
        if self.max_digits is not None and self.max_digits <= 0:
            raise ValueError("max_digits must be positive")
        if self.max_scale is not None and self.max_scale < 0:
            raise ValueError("max_scale must not be negative")
        if self.calculation_precision is not None and self.calculation_precision <= 0:
            raise ValueError("calculation_precision must be positive")
        if (
            self.max_digits is not None
            and self.calculation_precision is not None
            and self.calculation_precision < self.max_digits
        ):
            raise ValueError(
                "calculation_precision must be at least as large as max_digits"
            )


DEFAULT_DECIMAL_POLICY = ExactDecimalPolicy()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContractValidationError(f"{label} must be a list")
    return list(value)


def _text(value: Any, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractValidationError(f"{label} must be text")
    result = value.strip()
    if not result and not allow_empty:
        raise ContractValidationError(f"{label} must be non-empty text")
    return result


def _identifier(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if result != value or ID_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a canonical identifier")
    return result


def _sha256(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if SHA256_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a lowercase SHA-256 digest")
    return result


def _iso_date(value: Any, *, label: str) -> str:
    result = _text(value, label=label)
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", result) is None:
        raise ContractValidationError(f"{label} must be an ISO date")
    try:
        date.fromisoformat(result)
    except ValueError as exc:
        raise ContractValidationError(f"{label} must be an ISO date") from exc
    return result


def _exact_fields(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
    label: str,
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required - optional)
    if missing:
        raise ContractValidationError(f"{label} is missing fields: {missing}")
    if unexpected:
        raise ContractValidationError(
            f"{label} contains unexpected fields: {unexpected}"
        )


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractValidationError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _reject_json_fraction(value: str) -> Any:
    raise ContractValidationError(
        f"JSON fractional or exponent number {value!r} is not permitted; "
        "use a Decimal string"
    )


def _reject_json_constant(value: str) -> Any:
    raise ContractValidationError(f"non-finite JSON value {value!r} is not permitted")


def strict_json_load(path: Path) -> dict[str, Any]:
    """Load one JSON object while rejecting duplicates and binary-float values."""

    payload, _, _ = strict_json_snapshot(path)
    return payload


def strict_json_load_bytes(value: bytes, *, label: str) -> dict[str, Any]:
    """Load one exact UTF-8 JSON byte snapshot with strict number/key handling."""

    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractValidationError(f"invalid UTF-8 JSON in {label}") from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_float=_reject_json_fraction,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ContractValidationError(f"invalid JSON in {label}: {exc}") from exc
    return dict(_mapping(payload, label=label))


def _snapshot_identity(stat_result: os.stat_result) -> tuple[int, ...]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_mode,
        stat_result.st_nlink,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
    )


def _require_stable_path_snapshot(
    path: Path,
    *,
    descriptor_before: os.stat_result,
    descriptor_after: os.stat_result,
) -> None:
    if _snapshot_identity(descriptor_before) != _snapshot_identity(descriptor_after):
        raise ContractValidationError(f"file changed while it was read: {path}")
    try:
        current = path.stat()
    except OSError as exc:
        raise ContractValidationError(
            f"file path changed while it was read: {path}"
        ) from exc
    if _snapshot_identity(descriptor_after) != _snapshot_identity(current):
        raise ContractValidationError(f"file path changed while it was read: {path}")


def strict_json_snapshot(path: Path) -> tuple[dict[str, Any], int, str]:
    """Read, validate, and hash one stable JSON snapshot exactly once."""

    resolved = Path(path)
    with resolved.open("rb") as handle:
        descriptor_before = os.fstat(handle.fileno())
        value = handle.read()
        descriptor_after = os.fstat(handle.fileno())
    _require_stable_path_snapshot(
        resolved,
        descriptor_before=descriptor_before,
        descriptor_after=descriptor_after,
    )
    payload = strict_json_load_bytes(value, label=str(resolved))
    return payload, len(value), hashlib.sha256(value).hexdigest()


@contextmanager
def _open_regular_file_beneath(
    path: Path,
    *,
    root: Path,
) -> Iterator[int]:
    """Open a regular file through no-follow directory descriptors."""

    root_path = Path(root).absolute()
    lexical_path = Path(path).absolute()
    try:
        relative_path = lexical_path.relative_to(root_path)
    except ValueError as exc:
        raise ContractValidationError(
            f"file must stay inside the declared root: {path}"
        ) from exc
    if not relative_path.parts:
        raise ContractValidationError(f"file must be below the declared root: {path}")
    if any(part in {"", ".", ".."} for part in relative_path.parts):
        raise ContractValidationError(
            f"file path must not traverse outside the declared root: {path}"
        )

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        directory_flags |= os.O_CLOEXEC
        file_flags |= os.O_CLOEXEC

    descriptors: list[int] = []
    try:
        current_descriptor = os.open(root_path, directory_flags)
        descriptors.append(current_descriptor)
        for part in relative_path.parts[:-1]:
            current_descriptor = os.open(
                part,
                directory_flags,
                dir_fd=current_descriptor,
            )
            descriptors.append(current_descriptor)
        file_descriptor = os.open(
            relative_path.parts[-1],
            file_flags,
            dir_fd=current_descriptor,
        )
        descriptors.append(file_descriptor)
        descriptor_before = os.fstat(file_descriptor)
        if not stat.S_ISREG(descriptor_before.st_mode):
            raise ContractValidationError(f"path must identify one file: {path}")
        if descriptor_before.st_nlink != 1:
            raise ContractValidationError(f"file must not be hard linked: {path}")
        yield file_descriptor
        descriptor_after = os.fstat(file_descriptor)
        if _snapshot_identity(descriptor_before) != _snapshot_identity(
            descriptor_after
        ):
            raise ContractValidationError(f"file changed while it was read: {path}")
        try:
            current = os.stat(
                relative_path.parts[-1],
                dir_fd=current_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ContractValidationError(
                f"file path changed while it was read: {path}"
            ) from exc
        if _snapshot_identity(descriptor_after) != _snapshot_identity(current):
            raise ContractValidationError(
                f"file path changed while it was read: {path}"
            )
        try:
            lexical_current = lexical_path.lstat()
        except OSError as exc:
            raise ContractValidationError(
                f"file path changed while it was read: {path}"
            ) from exc
        if _snapshot_identity(descriptor_after) != _snapshot_identity(lexical_current):
            raise ContractValidationError(
                f"file path changed while it was read: {path}"
            )
    except OSError as exc:
        raise ContractValidationError(
            f"could not safely open file below the declared root: {path}"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_descriptor_bytes(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def strict_json_snapshot_beneath(
    path: Path,
    *,
    root: Path,
) -> tuple[dict[str, Any], int, str]:
    """Read strict JSON through a race-resistant path below one root."""

    with _open_regular_file_beneath(path, root=root) as descriptor:
        value = _read_descriptor_bytes(descriptor)
    payload = strict_json_load_bytes(value, label=str(path))
    return payload, len(value), hashlib.sha256(value).hexdigest()


def _resolve_json_pointer(value: Any, pointer: Any, *, label: str) -> Any:
    """Resolve one RFC 6901 JSON Pointer without interpreting the located value."""

    text = _text(pointer, label=label, allow_empty=True)
    if text == "":
        return value
    if not text.startswith("/"):
        raise ContractValidationError(f"{label} must be an absolute JSON Pointer")
    current = value
    for raw_token in text[1:].split("/"):
        if re.search(r"~(?:[^01]|$)", raw_token):
            raise ContractValidationError(f"{label} contains an invalid escape")
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise ContractValidationError(f"{label} does not resolve")
            current = current[token]
            continue
        if isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            if re.fullmatch(r"0|[1-9][0-9]*", token) is None:
                raise ContractValidationError(f"{label} has an invalid array index")
            position = int(token)
            if position >= len(current):
                raise ContractValidationError(f"{label} does not resolve")
            current = current[position]
            continue
        raise ContractValidationError(f"{label} does not resolve")
    return current


def _validate_structured_value(value: Any, *, label: str = "value") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise ContractValidationError(f"{label} contains a binary floating-point value")
    if isinstance(value, Decimal):
        raise ContractValidationError(
            f"{label} contains Decimal; serialize it as a canonical string"
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractValidationError(f"{label} contains a non-text key")
            _validate_structured_value(item, label=f"{label}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for position, item in enumerate(value):
            _validate_structured_value(item, label=f"{label}[{position}]")
        return
    raise ContractValidationError(
        f"{label} contains unsupported value type {type(value).__name__}"
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return stable structured JSON bytes for hashing, not a universal standard."""

    _validate_structured_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    """Return the SHA-256 of :func:`canonical_json_bytes`."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write stable, human-readable JSON with LF termination."""

    _validate_structured_value(value)
    Path(path).write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


@contextmanager
def exact_decimal_context(
    policy: ExactDecimalPolicy = DEFAULT_DECIMAL_POLICY,
    *,
    minimum_precision: int | None = None,
) -> Iterator[None]:
    """Run exact arithmetic with explicit or operation-derived precision."""

    precision = policy.calculation_precision
    if precision is None:
        if minimum_precision is None or minimum_precision <= 0:
            raise ContractValidationError(
                "exact Decimal arithmetic requires operation-derived precision "
                "or an explicit case policy"
            )
        precision = minimum_precision
    with localcontext() as context:
        context.prec = precision
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        yield


def _decimal_work_precision(*values: Decimal) -> int:
    """Return sufficient precision for exact fixed-point arithmetic."""

    if not values or any(not value.is_finite() for value in values):
        raise ContractValidationError(
            "exact Decimal arithmetic requires finite operands"
        )
    common_scale = 0
    maximum_integer_digits = 1
    for value in values:
        parts = value.as_tuple()
        if not isinstance(parts.exponent, int):
            raise ContractValidationError(
                "exact Decimal arithmetic requires finite operands"
            )
        common_scale = max(common_scale, max(-parts.exponent, 0))
        maximum_integer_digits = max(
            maximum_integer_digits,
            max(len(parts.digits) + parts.exponent, 0),
        )
    return maximum_integer_digits + common_scale + 2


def parse_decimal(
    value: Any,
    *,
    label: str,
    policy: ExactDecimalPolicy = DEFAULT_DECIMAL_POLICY,
    positive: bool = False,
    non_negative: bool = False,
    canonical: bool = False,
) -> Decimal:
    """Parse one finite non-exponent Decimal under optional case-owned bounds."""

    text = _text(value, label=label)
    if DECIMAL_PATTERN.fullmatch(text) is None:
        raise ContractValidationError(f"{label} must be a Decimal string")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ContractValidationError(f"{label} must be a Decimal string") from exc
    if not result.is_finite():
        raise ContractValidationError(f"{label} must be finite")
    parts = result.as_tuple()
    if not isinstance(parts.exponent, int):
        raise ContractValidationError(f"{label} must be finite")
    if policy.max_digits is not None and len(parts.digits) > policy.max_digits:
        raise ContractValidationError(
            f"{label} must contain at most {policy.max_digits} digits"
        )
    if policy.max_scale is not None and max(-parts.exponent, 0) > policy.max_scale:
        raise ContractValidationError(
            f"{label} must contain at most {policy.max_scale} decimal places"
        )
    if positive and result <= 0:
        raise ContractValidationError(f"{label} must be positive")
    if non_negative and result < 0:
        raise ContractValidationError(f"{label} must not be negative")
    if canonical and decimal_text(result) != text:
        raise ContractValidationError(f"{label} must use canonical Decimal text")
    return result


def decimal_text(value: Decimal) -> str:
    """Return a finite Decimal without exponent, trailing zeros, or negative zero."""

    if not value.is_finite():
        raise ContractValidationError("output Decimal values must be finite")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def is_on_increment(
    value: Decimal,
    increment: Decimal,
    *,
    policy: ExactDecimalPolicy = DEFAULT_DECIMAL_POLICY,
) -> bool:
    """Return whether a value lies on a declared positive increment grid."""

    minimum_precision = _decimal_work_precision(value, increment)
    if increment <= 0:
        raise ContractValidationError("increment must be positive")
    with exact_decimal_context(
        policy,
        minimum_precision=minimum_precision,
    ):
        return value % increment == 0


def difference_within_tolerance(
    actual: Decimal,
    expected: Decimal,
    tolerance: Decimal,
    *,
    policy: ExactDecimalPolicy = DEFAULT_DECIMAL_POLICY,
) -> bool:
    """Apply, but never select, one declared non-negative tolerance."""

    minimum_precision = _decimal_work_precision(actual, expected, tolerance)
    if tolerance < 0:
        raise ContractValidationError("tolerance must not be negative")
    with exact_decimal_context(
        policy,
        minimum_precision=minimum_precision,
    ):
        return abs(actual - expected) <= tolerance


def file_sha256(path: Path) -> str:
    """Hash a local file without loading it wholly into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_snapshot(path: Path) -> tuple[int, str]:
    """Return byte count and digest from one stable file-descriptor snapshot."""

    resolved = Path(path)
    digest = hashlib.sha256()
    byte_count = 0
    with resolved.open("rb") as handle:
        descriptor_before = os.fstat(handle.fileno())
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            byte_count += len(chunk)
            digest.update(chunk)
        descriptor_after = os.fstat(handle.fileno())
    _require_stable_path_snapshot(
        resolved,
        descriptor_before=descriptor_before,
        descriptor_after=descriptor_after,
    )
    if byte_count != descriptor_after.st_size:
        raise ContractValidationError(f"file size changed while it was read: {path}")
    return byte_count, digest.hexdigest()


def file_snapshot_beneath(
    path: Path,
    *,
    root: Path,
) -> tuple[int, str]:
    """Hash a stable regular file opened beneath one no-follow root."""

    digest = hashlib.sha256()
    byte_count = 0
    with _open_regular_file_beneath(path, root=root) as descriptor:
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            byte_count += len(chunk)
            digest.update(chunk)
        descriptor_status = os.fstat(descriptor)
        if byte_count != descriptor_status.st_size:
            raise ContractValidationError(
                f"file size changed while it was read: {path}"
            )
    return byte_count, digest.hexdigest()


def resolve_local_file(root: Path, relative_path: Any, *, label: str) -> Path:
    """Resolve one required file while preventing absolute and symlink escapes."""

    root = Path(root).resolve()
    relative = Path(_text(relative_path, label=label))
    if relative.is_absolute():
        raise ContractValidationError(f"{label} must be relative")
    if "\\" in relative.as_posix():
        raise ContractValidationError(f"{label} must use POSIX separators")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ContractValidationError(f"{label} must stay inside the declared root")
    if not resolved.is_file():
        raise ContractValidationError(f"{label} does not exist: {relative.as_posix()}")
    return resolved


def artifact_receipt(
    root: Path,
    path: Path,
    *,
    artifact_id: str,
    role: str,
    media_type: str | None = None,
) -> dict[str, Any]:
    """Build one exact local artifact receipt using a root-relative path."""

    root = Path(root).resolve()
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ContractValidationError("artifact path must be a file inside root")
    byte_count, digest = file_snapshot(resolved)
    receipt: dict[str, Any] = {
        "artifact_id": _identifier(artifact_id, label="artifact_id"),
        "role": _text(role, label="artifact role"),
        "path": resolved.relative_to(root).as_posix(),
        "byte_count": byte_count,
        "sha256": digest,
    }
    if media_type is not None:
        receipt["media_type"] = _text(media_type, label="artifact media_type")
    return receipt


def read_exact_csv(
    path: Path,
    *,
    columns: tuple[str, ...],
    label: str,
    require_rows: bool = True,
) -> list[dict[str, str]]:
    """Read exact ordered CSV columns and reject truncated or surplus cells."""

    rows: list[dict[str, str]] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != columns:
            raise ContractValidationError(f"{label} columns must equal {list(columns)}")
        for position, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                raise ContractValidationError(
                    f"{label} row {position} contains surplus cells"
                )
            if any(value is None for value in raw_row.values()):
                raise ContractValidationError(
                    f"{label} row {position} contains truncated cells"
                )
            rows.append({column: str(raw_row[column]) for column in columns})
    if require_rows and not rows:
        raise ContractValidationError(f"{label} must contain at least one row")
    return rows


def reference_set(
    *,
    artifact_refs: Sequence[str] = (),
    source_refs: Sequence[str] = (),
    decision_refs: Sequence[str] = (),
    lineage_refs: Sequence[str] = (),
) -> dict[str, list[str]]:
    """Build one sorted, duplicate-free reference set."""

    result = {
        "artifact_refs": sorted(
            {_identifier(item, label="artifact reference") for item in artifact_refs}
        ),
        "source_refs": sorted(
            {_identifier(item, label="source reference") for item in source_refs}
        ),
        "decision_refs": sorted(
            {_identifier(item, label="decision reference") for item in decision_refs}
        ),
        "lineage_refs": sorted(
            {_identifier(item, label="lineage reference") for item in lineage_refs}
        ),
    }
    if not any(result.values()):
        raise ContractValidationError("a reference set must not be empty")
    return result


def validate_declared_source_receipt(
    value: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    """Validate declared remote metadata without asserting source authenticity."""

    source = _mapping(value, label=label)
    _exact_fields(
        source,
        required=frozenset(
            {
                "source_id",
                "title",
                "document_type",
                "url",
                "byte_count",
                "sha256",
                "receipt_scope",
            }
        ),
        optional=frozenset({"publisher", "document_date", "metadata"}),
        label=label,
    )
    source_id = _identifier(source["source_id"], label=f"{label}.source_id")
    url = _text(source["url"], label=f"{label}.url")
    if not url.startswith("https://"):
        raise ContractValidationError(f"{label}.url must use https")
    byte_count = source["byte_count"]
    if type(byte_count) is not int or byte_count <= 0:
        raise ContractValidationError(f"{label}.byte_count must be positive")
    if source["receipt_scope"] != "declared_remote_receipt":
        raise ContractValidationError(
            f"{label}.receipt_scope must be declared_remote_receipt"
        )
    normalized: dict[str, Any] = {
        "source_id": source_id,
        "title": _text(source["title"], label=f"{label}.title"),
        "document_type": _text(source["document_type"], label=f"{label}.document_type"),
        "url": url,
        "byte_count": byte_count,
        "sha256": _sha256(source["sha256"], label=f"{label}.sha256"),
        "receipt_scope": "declared_remote_receipt",
    }
    if "publisher" in source:
        normalized["publisher"] = _text(source["publisher"], label=f"{label}.publisher")
    if "document_date" in source:
        normalized["document_date"] = _iso_date(
            source["document_date"], label=f"{label}.document_date"
        )
    if "metadata" in source:
        _validate_structured_value(source["metadata"], label=f"{label}.metadata")
        normalized["metadata"] = source["metadata"]
    return normalized


def reviewed_decision_receipt(
    *,
    decision_id: str,
    decision_kind: str,
    status: str,
    reviewed_on: str | None,
    basis: str,
    content: Any,
    evidence_refs: Mapping[str, Any],
    version: str | None = None,
    reviewer: str | None = None,
) -> dict[str, Any]:
    """Build a reviewed-decision presence receipt without interpreting content."""

    _validate_structured_value(content, label="reviewed decision content")
    if status != "reviewed":
        raise ContractValidationError(
            "reviewed decision receipt cannot promote a non-reviewed decision"
        )
    result: dict[str, Any] = {
        "decision_id": _identifier(decision_id, label="decision_id"),
        "decision_kind": _text(decision_kind, label="decision_kind"),
        "status": status,
        "basis": _text(basis, label="basis"),
        "content": content,
        "content_digest_basis": "canonical_json_utf8",
        "content_sha256": canonical_json_sha256(content),
        "evidence_refs": dict(evidence_refs),
    }
    if reviewed_on is not None:
        result["reviewed_on"] = _iso_date(reviewed_on, label="reviewed_on")
    if version is not None:
        result["version"] = _text(version, label="decision version")
    if reviewer is not None:
        result["reviewer"] = _text(reviewer, label="reviewer")
    return result


def _require_unique_ids(
    rows: Sequence[Mapping[str, Any]],
    *,
    field: str,
    label: str,
) -> set[str]:
    identifiers: list[str] = [
        _identifier(row.get(field), label=f"{label}[{position}].{field}")
        for position, row in enumerate(rows)
    ]
    duplicates = sorted(
        identifier
        for identifier in set(identifiers)
        if identifiers.count(identifier) > 1
    )
    if duplicates:
        raise ContractValidationError(f"{label} contains duplicate IDs: {duplicates}")
    if identifiers != sorted(identifiers):
        raise ContractValidationError(f"{label} must be sorted by {field}")
    return set(identifiers)


def _validate_reference_set(
    value: Any,
    *,
    label: str,
    artifact_ids: set[str],
    source_ids: set[str],
    decision_ids: set[str],
    lineage_ids: set[str],
    allow_empty: bool = False,
) -> None:
    references = _mapping(value, label=label)
    _exact_fields(references, required=REFERENCE_FIELDS, label=label)
    targets = {
        "artifact_refs": artifact_ids,
        "source_refs": source_ids,
        "decision_refs": decision_ids,
        "lineage_refs": lineage_ids,
    }
    populated = False
    for field, known in targets.items():
        raw_items = _sequence(references[field], label=f"{label}.{field}")
        items = [_identifier(item, label=f"{label}.{field}[]") for item in raw_items]
        if items != sorted(items) or len(items) != len(set(items)):
            raise ContractValidationError(
                f"{label}.{field} must be sorted and duplicate-free"
            )
        unknown = sorted(set(items) - known)
        if unknown:
            raise ContractValidationError(
                f"{label}.{field} contains unknown references: {unknown}"
            )
        populated = populated or bool(items)
    if not populated and not allow_empty:
        raise ContractValidationError(f"{label} must contain at least one reference")


def _validate_artifacts(
    values: Any,
    *,
    root: Path,
) -> tuple[list[Mapping[str, Any]], set[str]]:
    rows = [
        _mapping(item, label=f"local_artifacts[{position}]")
        for position, item in enumerate(_sequence(values, label="local_artifacts"))
    ]
    if not rows:
        raise ContractValidationError("local_artifacts must not be empty")
    artifact_ids = _require_unique_ids(
        rows, field="artifact_id", label="local_artifacts"
    )
    for position, artifact in enumerate(rows):
        label = f"local_artifacts[{position}]"
        _exact_fields(
            artifact,
            required=frozenset({"artifact_id", "role", "path", "byte_count", "sha256"}),
            optional=frozenset({"media_type"}),
            label=label,
        )
        _text(artifact["role"], label=f"{label}.role")
        path = resolve_local_file(root, artifact["path"], label=f"{label}.path")
        byte_count = artifact["byte_count"]
        if type(byte_count) is not int or byte_count < 0:
            raise ContractValidationError(f"{label}.byte_count must not be negative")
        actual_byte_count, actual_digest = file_snapshot(path)
        if actual_byte_count != byte_count:
            raise ContractValidationError(f"{label}.byte_count does not match file")
        if actual_digest != _sha256(artifact["sha256"], label=f"{label}.sha256"):
            raise ContractValidationError(f"{label}.sha256 does not match file")
        if "media_type" in artifact:
            _text(artifact["media_type"], label=f"{label}.media_type")
    return rows, artifact_ids


def _validate_sources(values: Any) -> tuple[list[dict[str, Any]], set[str]]:
    rows = [
        validate_declared_source_receipt(
            _mapping(item, label=f"remote_sources[{position}]"),
            label=f"remote_sources[{position}]",
        )
        for position, item in enumerate(_sequence(values, label="remote_sources"))
    ]
    if not rows:
        raise ContractValidationError("remote_sources must not be empty")
    source_ids = _require_unique_ids(rows, field="source_id", label="remote_sources")
    return rows, source_ids


def _validate_decisions(
    values: Any,
) -> tuple[list[Mapping[str, Any]], set[str]]:
    rows = [
        _mapping(item, label=f"reviewed_decisions[{position}]")
        for position, item in enumerate(_sequence(values, label="reviewed_decisions"))
    ]
    if not rows:
        raise ContractValidationError("reviewed_decisions must not be empty")
    decision_ids = _require_unique_ids(
        rows, field="decision_id", label="reviewed_decisions"
    )
    for position, decision in enumerate(rows):
        label = f"reviewed_decisions[{position}]"
        _exact_fields(
            decision,
            required=frozenset(
                {
                    "decision_id",
                    "decision_kind",
                    "status",
                    "basis",
                    "content",
                    "content_digest_basis",
                    "content_sha256",
                    "evidence_refs",
                }
            ),
            optional=frozenset({"version", "reviewed_on", "reviewer"}),
            label=label,
        )
        _text(decision["decision_kind"], label=f"{label}.decision_kind")
        if decision["status"] != "reviewed":
            raise ContractValidationError(f"{label}.status must be reviewed")
        if "reviewed_on" in decision:
            _iso_date(decision["reviewed_on"], label=f"{label}.reviewed_on")
        _text(decision["basis"], label=f"{label}.basis")
        _validate_structured_value(decision["content"], label=f"{label}.content")
        if decision["content_digest_basis"] != "canonical_json_utf8":
            raise ContractValidationError(
                f"{label}.content_digest_basis must be canonical_json_utf8"
            )
        expected = canonical_json_sha256(decision["content"])
        if (
            _sha256(decision["content_sha256"], label=f"{label}.content_sha256")
            != expected
        ):
            raise ContractValidationError(
                f"{label}.content_sha256 does not match content"
            )
        if "version" in decision:
            _text(decision["version"], label=f"{label}.version")
        if "reviewer" in decision:
            _text(decision["reviewer"], label=f"{label}.reviewer")
    return rows, decision_ids


def _lineage_rows(
    lineage: Mapping[str, Any],
) -> tuple[list[tuple[str, Mapping[str, Any]]], set[str]]:
    _exact_fields(
        lineage,
        required=frozenset({"artifact", "aggregate", "row"}),
        label="lineage",
    )
    collected: list[tuple[str, Mapping[str, Any]]] = []
    identifiers: list[str] = []
    for level in ("artifact", "aggregate", "row"):
        level_value = _mapping(lineage[level], label=f"lineage.{level}")
        _exact_fields(
            level_value,
            required=frozenset({"declared", "records", "limitations"}),
            label=f"lineage.{level}",
        )
        if type(level_value["declared"]) is not bool:
            raise ContractValidationError(f"lineage.{level}.declared must be boolean")
        records = [
            _mapping(item, label=f"lineage.{level}.records[{position}]")
            for position, item in enumerate(
                _sequence(level_value["records"], label=f"lineage.{level}.records")
            )
        ]
        limitations = [
            _text(item, label=f"lineage.{level}.limitations[]")
            for item in _sequence(
                level_value["limitations"], label=f"lineage.{level}.limitations"
            )
        ]
        if level == "artifact" and not level_value["declared"]:
            raise ContractValidationError("artifact lineage must be declared")
        if level == "row" and level_value["declared"]:
            raise ContractValidationError(
                "row lineage is not supported by preparation audit envelope v1"
            )
        if level_value["declared"] and not records:
            raise ContractValidationError(
                f"lineage.{level}.records must not be empty when declared"
            )
        if not level_value["declared"] and records:
            raise ContractValidationError(
                f"lineage.{level}.records must be empty when not declared"
            )
        if not level_value["declared"] and not limitations:
            raise ContractValidationError(
                f"lineage.{level}.limitations must explain unavailable lineage"
            )
        for record in records:
            identifiers.append(
                _identifier(
                    record.get("lineage_id"),
                    label=f"lineage.{level}.records[].lineage_id",
                )
            )
            collected.append((level, record))
    duplicates = sorted(
        identifier
        for identifier in set(identifiers)
        if identifiers.count(identifier) > 1
    )
    if duplicates:
        raise ContractValidationError(f"lineage contains duplicate IDs: {duplicates}")
    if identifiers != sorted(identifiers):
        raise ContractValidationError("lineage records must be globally ID-sorted")
    return collected, set(identifiers)


def validate_audit_envelope(
    envelope: Mapping[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    """Validate one audit envelope and all mechanically checkable references.

    Successful validation proves only contract integrity. It does not prove
    source authority, semantic correctness, reviewer authorization, report
    readiness, or publication eligibility.
    """

    payload = _mapping(envelope, label="envelope")
    _exact_fields(payload, required=TOP_LEVEL_FIELDS, label="envelope")
    if payload["schema_version"] != AUDIT_ENVELOPE_SCHEMA:
        raise ContractValidationError(f"schema_version must be {AUDIT_ENVELOPE_SCHEMA}")

    artifacts, artifact_ids = _validate_artifacts(
        payload["local_artifacts"], root=Path(root)
    )
    artifact_by_id = {str(artifact["artifact_id"]): artifact for artifact in artifacts}
    schema_artifacts = [
        artifact for artifact in artifacts if artifact["role"] == "audit_schema"
    ]
    if len(schema_artifacts) != 1:
        raise ContractValidationError(
            "exactly one audit_schema artifact must bind the envelope contract"
        )
    schema_document = strict_json_load(
        resolve_local_file(
            Path(root),
            schema_artifacts[0]["path"],
            label="audit schema artifact",
        )
    )
    try:
        schema_identifier = schema_document["properties"]["schema_version"]["const"]
    except (KeyError, TypeError) as exc:
        raise ContractValidationError(
            "audit_schema artifact does not declare the envelope schema version"
        ) from exc
    if schema_identifier != AUDIT_ENVELOPE_SCHEMA:
        raise ContractValidationError(
            "audit_schema artifact does not match schema_version"
        )
    _sources, source_ids = _validate_sources(payload["remote_sources"])
    decisions, decision_ids = _validate_decisions(payload["reviewed_decisions"])

    case = _mapping(payload["case"], label="case")
    _exact_fields(
        case,
        required=frozenset(
            {"case_id", "case_kind", "source_schema_version", "case_artifact_ref"}
        ),
        label="case",
    )
    _identifier(case["case_id"], label="case.case_id")
    _text(case["case_kind"], label="case.case_kind")
    _text(case["source_schema_version"], label="case.source_schema_version")
    case_ref = _identifier(case["case_artifact_ref"], label="case.case_artifact_ref")
    if case_ref not in artifact_ids:
        raise ContractValidationError("case.case_artifact_ref is unknown")

    adapter = _mapping(payload["adapter"], label="adapter")
    _exact_fields(
        adapter,
        required=frozenset(
            {
                "adapter_id",
                "adapter_version",
                "implementation_sha256",
                "normalization_scope",
            }
        ),
        label="adapter",
    )
    _identifier(adapter["adapter_id"], label="adapter.adapter_id")
    _text(adapter["adapter_version"], label="adapter.adapter_version")
    adapter_sha = _sha256(
        adapter["implementation_sha256"], label="adapter.implementation_sha256"
    )
    if adapter["normalization_scope"] != "audit_only":
        raise ContractValidationError("adapter.normalization_scope must be audit_only")
    matching_adapters = [
        artifact
        for artifact in artifacts
        if artifact["role"] == "audit_adapter" and artifact["sha256"] == adapter_sha
    ]
    if len(matching_adapters) != 1:
        raise ContractValidationError(
            "adapter implementation must match exactly one audit_adapter artifact"
        )

    execution = _mapping(payload["execution"], label="execution")
    _exact_fields(
        execution,
        required=frozenset(
            {
                "execution_id",
                "producer",
                "producer_version",
                "producer_sha256",
                "mode",
                "input_artifact_refs",
                "output_artifact_refs",
            }
        ),
        label="execution",
    )
    _identifier(execution["execution_id"], label="execution.execution_id")
    _text(execution["producer"], label="execution.producer")
    _text(execution["producer_version"], label="execution.producer_version")
    producer_sha = _sha256(
        execution["producer_sha256"], label="execution.producer_sha256"
    )
    if execution["mode"] != "deterministic_mechanical":
        raise ContractValidationError("execution.mode must be deterministic_mechanical")
    producer_matches = [
        artifact
        for artifact in artifacts
        if artifact["sha256"] == producer_sha
        and artifact["role"] in {"producer", "preparation_engine"}
    ]
    if len(producer_matches) != 1:
        raise ContractValidationError(
            "execution producer must match exactly one producer artifact"
        )
    execution_output_refs: frozenset[str] = frozenset()
    for field in ("input_artifact_refs", "output_artifact_refs"):
        refs = [
            _identifier(item, label=f"execution.{field}[]")
            for item in _sequence(execution[field], label=f"execution.{field}")
        ]
        if not refs or refs != sorted(refs) or len(refs) != len(set(refs)):
            raise ContractValidationError(
                f"execution.{field} must be non-empty, sorted, and duplicate-free"
            )
        unknown = sorted(set(refs) - artifact_ids)
        if unknown:
            raise ContractValidationError(
                f"execution.{field} contains unknown artifacts: {unknown}"
            )
        if field == "output_artifact_refs":
            execution_output_refs = frozenset(refs)

    numeric_policy = _mapping(payload["numeric_policy"], label="numeric_policy")
    _exact_fields(
        numeric_policy,
        required=frozenset(
            {
                "representation",
                "finite_only",
                "binary_float_allowed",
                "exponent_notation_allowed",
                "canonical_serialization_required",
                "case_constraints",
                "case_constraints_sha256",
            }
        ),
        label="numeric_policy",
    )
    expected_numeric_constants = {
        "representation": "decimal_string",
        "finite_only": True,
        "binary_float_allowed": False,
        "exponent_notation_allowed": False,
        "canonical_serialization_required": True,
    }
    for field, expected in expected_numeric_constants.items():
        if numeric_policy[field] != expected:
            raise ContractValidationError(
                f"numeric_policy.{field} must equal {expected!r}"
            )
    _validate_structured_value(
        numeric_policy["case_constraints"],
        label="numeric_policy.case_constraints",
    )
    if _sha256(
        numeric_policy["case_constraints_sha256"],
        label="numeric_policy.case_constraints_sha256",
    ) != canonical_json_sha256(numeric_policy["case_constraints"]):
        raise ContractValidationError(
            "numeric_policy.case_constraints_sha256 does not match constraints"
        )

    lineage = _mapping(payload["lineage"], label="lineage")
    lineage_rows, lineage_ids = _lineage_rows(lineage)

    for position, decision in enumerate(decisions):
        _validate_reference_set(
            decision["evidence_refs"],
            label=f"reviewed_decisions[{position}].evidence_refs",
            artifact_ids=artifact_ids,
            source_ids=source_ids,
            decision_ids=decision_ids,
            lineage_ids=lineage_ids,
        )

    for level, record in lineage_rows:
        label = f"lineage.{level}.{record['lineage_id']}"
        if level == "artifact":
            _exact_fields(
                record,
                required=frozenset(
                    {"lineage_id", "artifact_ref", "references", "details"}
                ),
                label=label,
            )
            primary_ref = _identifier(
                record["artifact_ref"], label=f"{label}.artifact_ref"
            )
        elif level == "aggregate":
            _exact_fields(
                record,
                required=frozenset(
                    {
                        "lineage_id",
                        "aggregate_id",
                        "output_artifact_ref",
                        "evidence_artifact_ref",
                        "evidence_json_pointer",
                        "aggregate_id_json_pointer",
                        "output_artifact_id_json_pointer",
                        "output_sha256_json_pointer",
                        "evidence_sha256",
                        "references",
                        "details",
                    }
                ),
                label=label,
            )
            _identifier(record["aggregate_id"], label=f"{label}.aggregate_id")
            primary_ref = _identifier(
                record["output_artifact_ref"],
                label=f"{label}.output_artifact_ref",
            )
            evidence_ref = _identifier(
                record["evidence_artifact_ref"],
                label=f"{label}.evidence_artifact_ref",
            )
            if evidence_ref not in artifact_ids:
                raise ContractValidationError(
                    f"{label} references unknown aggregate evidence artifact"
                )
            if primary_ref not in execution_output_refs:
                raise ContractValidationError(
                    f"{label} output artifact must be an execution output"
                )
            if evidence_ref not in execution_output_refs:
                raise ContractValidationError(
                    f"{label} evidence artifact must be an execution output"
                )
            evidence_artifact = artifact_by_id[evidence_ref]
            if evidence_artifact["role"] != "aggregate_lineage_evidence":
                raise ContractValidationError(
                    f"{label} evidence artifact must have role "
                    "aggregate_lineage_evidence"
                )
            evidence_path = resolve_local_file(
                Path(root),
                evidence_artifact["path"],
                label=f"{label}.evidence_artifact",
            )
            evidence_payload = strict_json_load(evidence_path)
            evidence_value = _resolve_json_pointer(
                evidence_payload,
                record["evidence_json_pointer"],
                label=f"{label}.evidence_json_pointer",
            )
            if _sha256(
                record["evidence_sha256"],
                label=f"{label}.evidence_sha256",
            ) != canonical_json_sha256(evidence_value):
                raise ContractValidationError(
                    f"{label}.evidence_sha256 does not match located evidence"
                )
            evidence_aggregate_id = _resolve_json_pointer(
                evidence_payload,
                record["aggregate_id_json_pointer"],
                label=f"{label}.aggregate_id_json_pointer",
            )
            if evidence_aggregate_id != record["aggregate_id"]:
                raise ContractValidationError(
                    f"{label} aggregate_id does not match located evidence"
                )
            evidence_output_id = _resolve_json_pointer(
                evidence_payload,
                record["output_artifact_id_json_pointer"],
                label=f"{label}.output_artifact_id_json_pointer",
            )
            if evidence_output_id != primary_ref:
                raise ContractValidationError(
                    f"{label} output artifact does not match located evidence"
                )
            evidence_output_sha = _sha256(
                _resolve_json_pointer(
                    evidence_payload,
                    record["output_sha256_json_pointer"],
                    label=f"{label}.output_sha256_json_pointer",
                ),
                label=f"{label}.located_output_sha256",
            )
            if evidence_output_sha != artifact_by_id[primary_ref]["sha256"]:
                raise ContractValidationError(
                    f"{label} output digest does not match located evidence"
                )
            evidence_refs = _mapping(
                record["references"],
                label=f"{label}.references",
            ).get("artifact_refs")
            if evidence_ref not in _sequence(
                evidence_refs,
                label=f"{label}.references.artifact_refs",
            ):
                raise ContractValidationError(
                    f"{label}.references must include its evidence artifact"
                )
            if primary_ref not in _sequence(
                evidence_refs,
                label=f"{label}.references.artifact_refs",
            ):
                raise ContractValidationError(
                    f"{label}.references must include its output artifact"
                )
        else:
            _exact_fields(
                record,
                required=frozenset(
                    {"lineage_id", "row_id", "artifact_ref", "references", "details"}
                ),
                label=label,
            )
            _identifier(record["row_id"], label=f"{label}.row_id")
            primary_ref = _identifier(
                record["artifact_ref"], label=f"{label}.artifact_ref"
            )
        if primary_ref not in artifact_ids:
            raise ContractValidationError(f"{label} references unknown artifact")
        _validate_structured_value(record["details"], label=f"{label}.details")
        _validate_reference_set(
            record["references"],
            label=f"{label}.references",
            artifact_ids=artifact_ids,
            source_ids=source_ids,
            decision_ids=decision_ids,
            lineage_ids=lineage_ids,
        )

    reconciliation = _mapping(payload["reconciliation"], label="reconciliation")
    _exact_fields(
        reconciliation,
        required=frozenset({"checks", "errors"}),
        label="reconciliation",
    )
    checks = [
        _mapping(item, label=f"reconciliation.checks[{position}]")
        for position, item in enumerate(
            _sequence(reconciliation["checks"], label="reconciliation.checks")
        )
    ]
    if not checks:
        raise ContractValidationError("reconciliation.checks must not be empty")
    _require_unique_ids(checks, field="check_id", label="reconciliation.checks")
    for position, check in enumerate(checks):
        label = f"reconciliation.checks[{position}]"
        _exact_fields(
            check,
            required=frozenset(
                {
                    "check_id",
                    "check_kind",
                    "required",
                    "status",
                    "references",
                    "numeric_evidence",
                    "details",
                }
            ),
            label=label,
        )
        _text(check["check_kind"], label=f"{label}.check_kind")
        if check["required"] is not True:
            raise ContractValidationError(f"{label}.required must be true")
        if check["status"] not in {"passed", "failed", "not_run"}:
            raise ContractValidationError(f"{label}.status is invalid")
        _validate_reference_set(
            check["references"],
            label=f"{label}.references",
            artifact_ids=artifact_ids,
            source_ids=source_ids,
            decision_ids=decision_ids,
            lineage_ids=lineage_ids,
        )
        evidence_rows = [
            _mapping(item, label=f"{label}.numeric_evidence[{evidence_position}]")
            for evidence_position, item in enumerate(
                _sequence(
                    check["numeric_evidence"],
                    label=f"{label}.numeric_evidence",
                )
            )
        ]
        for evidence_position, evidence in enumerate(evidence_rows):
            evidence_label = f"{label}.numeric_evidence[{evidence_position}]"
            _exact_fields(
                evidence,
                required=frozenset({"name", "value", "unit"}),
                optional=frozenset({"reported_increment"}),
                label=evidence_label,
            )
            _text(evidence["name"], label=f"{evidence_label}.name")
            parse_decimal(
                evidence["value"],
                label=f"{evidence_label}.value",
                canonical=True,
            )
            _text(evidence["unit"], label=f"{evidence_label}.unit")
            if "reported_increment" in evidence:
                parse_decimal(
                    evidence["reported_increment"],
                    label=f"{evidence_label}.reported_increment",
                    positive=True,
                    canonical=True,
                )
        _validate_structured_value(check["details"], label=f"{label}.details")

    errors = [
        _mapping(item, label=f"reconciliation.errors[{position}]")
        for position, item in enumerate(
            _sequence(reconciliation["errors"], label="reconciliation.errors")
        )
    ]
    if errors:
        _require_unique_ids(errors, field="error_id", label="reconciliation.errors")
    for position, error in enumerate(errors):
        label = f"reconciliation.errors[{position}]"
        _exact_fields(
            error,
            required=frozenset(
                {"error_id", "code", "message", "references", "details"}
            ),
            label=label,
        )
        _text(error["code"], label=f"{label}.code")
        _text(error["message"], label=f"{label}.message")
        _validate_reference_set(
            error["references"],
            label=f"{label}.references",
            artifact_ids=artifact_ids,
            source_ids=source_ids,
            decision_ids=decision_ids,
            lineage_ids=lineage_ids,
        )
        _validate_structured_value(error["details"], label=f"{label}.details")

    statuses = _mapping(payload["statuses"], label="statuses")
    _exact_fields(statuses, required=STATUS_FIELDS, label="statuses")
    allowed_statuses = {
        "validation": {"not_assessed", "passed", "failed", "blocked"},
        "preparation": {"not_assessed", "passed", "failed", "blocked"},
        "reconciliation": {"not_assessed", "passed", "failed", "blocked"},
        "semantic": {"not_assessed"},
        "source": {"not_assessed", "receipt_only", "failed", "blocked"},
        "downstream": {"not_assessed"},
        "publication": {
            "not_assessed",
            "withheld",
            "failed",
            "blocked",
        },
    }
    for status_name in sorted(STATUS_FIELDS):
        status = _mapping(statuses[status_name], label=f"statuses.{status_name}")
        _exact_fields(
            status,
            required=frozenset({"status", "basis", "evidence_refs"}),
            label=f"statuses.{status_name}",
        )
        if status_name == "publication" and status["status"] == "emitted":
            raise ContractValidationError(
                "an audit envelope cannot establish external publication"
            )
        if status["status"] not in allowed_statuses[status_name]:
            raise ContractValidationError(f"statuses.{status_name}.status is invalid")
        _text(status["basis"], label=f"statuses.{status_name}.basis")
        _validate_reference_set(
            status["evidence_refs"],
            label=f"statuses.{status_name}.evidence_refs",
            artifact_ids=artifact_ids,
            source_ids=source_ids,
            decision_ids=decision_ids,
            lineage_ids=lineage_ids,
        )

    reconciliation_status = statuses["reconciliation"]["status"]
    failed_checks = [check for check in checks if check["status"] != "passed"]
    if reconciliation_status == "passed" and (failed_checks or errors):
        raise ContractValidationError(
            "passed reconciliation cannot contain failed checks or errors"
        )
    if reconciliation_status == "failed" and not (failed_checks or errors):
        raise ContractValidationError(
            "failed reconciliation must contain a failed check or error"
        )
    if statuses["source"]["status"] == "receipt_only" and not source_ids:
        raise ContractValidationError("receipt_only source status requires receipts")
    if type(payload["report_ready"]) is not bool or payload["report_ready"]:
        raise ContractValidationError(
            "preparation audit envelopes cannot claim report readiness"
        )
    limitations = [
        _mapping(item, label=f"limitations[{position}]")
        for position, item in enumerate(
            _sequence(payload["limitations"], label="limitations")
        )
    ]
    if not limitations:
        raise ContractValidationError("limitations must not be empty")
    _require_unique_ids(limitations, field="limitation_id", label="limitations")
    allowed_scopes = {
        "case",
        "adapter",
        "source",
        "validation",
        "preparation",
        "numeric",
        "reconciliation",
        "semantic",
        "lineage",
        "downstream",
        "publication",
    }
    for position, limitation in enumerate(limitations):
        label = f"limitations[{position}]"
        _exact_fields(
            limitation,
            required=frozenset({"limitation_id", "scope", "statement"}),
            optional=frozenset({"related_refs"}),
            label=label,
        )
        if limitation["scope"] not in allowed_scopes:
            raise ContractValidationError(f"{label}.scope is invalid")
        _text(limitation["statement"], label=f"{label}.statement")
        if "related_refs" in limitation:
            _validate_reference_set(
                limitation["related_refs"],
                label=f"{label}.related_refs",
                artifact_ids=artifact_ids,
                source_ids=source_ids,
                decision_ids=decision_ids,
                lineage_ids=lineage_ids,
            )

    return dict(payload)
