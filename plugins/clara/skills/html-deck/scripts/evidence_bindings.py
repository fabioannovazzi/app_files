#!/usr/bin/env python3
"""Resolve hash-pinned evidence into Clara deck plans without semantic choices.

This module is intentionally a transport boundary. It verifies exact evidence
bytes, resolves stable value addresses, applies explicit Decimal formatting,
and records every downstream use. It does not choose evidence, calculate
business metrics, filter populations, join datasets, or select visual types.
Those decisions must be made upstream and materialized as evidence artifacts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import logging
import os
import re
import string
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import (
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
    localcontext,
)
from pathlib import Path
from typing import Any

__all__ = [
    "EVIDENCE_BUNDLE_SCHEMA_VERSION",
    "EVIDENCE_LEDGER_ELEMENT_ID",
    "EVIDENCE_LEDGER_SCHEMA_VERSION",
    "SOURCE_BOUND_LEDGER_SCHEMA_VERSION",
    "SOURCE_BOUND_PLAN_SCHEMA_VERSION",
    "EvidenceResolution",
    "assert_no_unbound_quantitative_content",
    "canonical_json_bytes",
    "embedded_evidence_ledger_markup",
    "extract_embedded_evidence_ledger",
    "resolve_source_bound_documents",
    "seal_evidence_bundle",
    "sha256_bytes",
    "sha256_file",
    "validate_evidence_bundle",
    "validate_evidence_ledger",
]


LOGGER = logging.getLogger(__name__)
SOURCE_BOUND_PLAN_SCHEMA_VERSION = "clara.html_deck_plan.v2"
SOURCE_BOUND_LEDGER_SCHEMA_VERSION = "clara.html_deck_ledger.v2"
RESOLVED_PLAN_SCHEMA_VERSION = "clara.html_deck_plan.v1"
RESOLVED_LEDGER_SCHEMA_VERSION = "clara.html_deck_ledger.v1"
EVIDENCE_BUNDLE_SCHEMA_VERSION = "clara.evidence_bundle.v1"
EVIDENCE_LEDGER_SCHEMA_VERSION = "clara.html_deck_evidence_ledger.v1"
EVIDENCE_LEDGER_ELEMENT_ID = "claraEvidenceLedger"
EVIDENCE_LEDGER_RE = re.compile(
    rf'<script\b[^>]*id=["\']{EVIDENCE_LEDGER_ELEMENT_ID}["\'][^>]*>'
    r"(?P<payload>.*?)</script>",
    flags=re.IGNORECASE | re.DOTALL,
)
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
QUANTITATIVE_TOKEN_RE = re.compile(r"\d")
PLACEHOLDER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
SUPPORTED_MEDIA_TYPES = frozenset({"application/json", "text/csv"})
SUPPORTED_VALUE_TYPES = frozenset(
    {"boolean", "decimal", "integer", "json", "records", "string"}
)
ROUNDING_MODES = {
    "down": ROUND_DOWN,
    "half_even": ROUND_HALF_EVEN,
    "half_up": ROUND_HALF_UP,
}
STRUCTURAL_CONTENT_KEYS = frozenset(
    {
        "_fragment",
        "id",
        "renderer",
        "schema_version",
        "source_ids",
        "source_refs",
        "type",
    }
)


@dataclass(frozen=True)
class EvidenceArtifact:
    """One verified evidence file and its addressing contract."""

    artifact_id: str
    source_id: str
    path: str
    resolved_path: Path
    media_type: str
    sha256: str
    size_bytes: int
    table: Mapping[str, Any] | None
    snapshot_id: str


@dataclass(frozen=True)
class ResolvedBinding:
    """One central binding resolved once from an exact artifact address."""

    binding_id: str
    artifact: EvidenceArtifact
    definition: Mapping[str, Any]
    raw_value: Any
    display_value: str | None
    value_sha256: str


@dataclass(frozen=True)
class EvidenceResolution:
    """Source-bound plan, ledger, and deterministic evidence-use ledger."""

    resolved_plan: dict[str, Any]
    resolved_ledger: dict[str, Any]
    evidence_ledger: dict[str, Any]


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be an array")
    return list(value)


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _safe_id(value: object, label: str) -> str:
    result = _required_text(value, label)
    if not SAFE_ID_RE.fullmatch(result):
        raise ValueError(f"{label} must be a stable lowercase identifier")
    return result


def _exact_keys(
    value: Mapping[str, Any],
    *,
    allowed: set[str],
    required: set[str],
    label: str,
) -> None:
    missing = sorted(required - set(value))
    unexpected = sorted(set(value) - allowed)
    if missing:
        raise ValueError(f"{label} is missing fields: {missing}")
    if unexpected:
        raise ValueError(f"{label} has unknown fields: {unexpected}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return stable UTF-8 JSON bytes for hashing and equality checks."""

    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 digest for bytes."""

    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _publication_content_ledger(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact privacy-safe ledger payload embedded in final HTML."""

    module_path = Path(__file__).with_name("content_ledger.py")
    spec = importlib.util.spec_from_file_location(
        "clara_html_deck_evidence_content_ledger",
        module_path,
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load Clara content-ledger helper: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.publication_ledger(ledger)


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("evidence decimal values must be finite")
    if value == 0:
        return "0"

    # Decimal.normalize() obeys the active context precision and can therefore
    # round evidence before it is hashed. Render from the exact coefficient and
    # exponent instead so canonicalization is independent of ambient context.
    parts = value.as_tuple()
    exponent = parts.exponent
    if not isinstance(exponent, int):
        raise ValueError("evidence decimal values must be finite")
    digits = "".join(str(digit) for digit in parts.digits)
    if exponent >= 0:
        rendered = digits + ("0" * exponent)
    else:
        decimal_position = len(digits) + exponent
        if decimal_position > 0:
            integer_part = digits[:decimal_position]
            fractional_part = digits[decimal_position:]
        else:
            integer_part = "0"
            fractional_part = ("0" * -decimal_position) + digits
        fractional_part = fractional_part.rstrip("0")
        rendered = (
            f"{integer_part}.{fractional_part}" if fractional_part else integer_part
        )
    return f"-{rendered}" if parts.sign else rendered


def _as_decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a finite decimal")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be a finite decimal")
    return result


def _contained_file(base_dir: Path, relative: object, label: str) -> tuple[str, Path]:
    relative_text = _required_text(relative, label)
    relative_path = Path(relative_text)
    if relative_path.is_absolute():
        raise ValueError(f"{label} must be relative")
    lexical = base_dir / relative_path
    if lexical.is_symlink():
        raise ValueError(f"{label} may not be a symbolic link")
    resolved_base = base_dir.resolve()
    resolved = lexical.resolve()
    try:
        resolved.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside {resolved_base}") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} does not exist: {relative_text}")
    return relative_path.as_posix(), resolved


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r} is not permitted")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r} is not permitted")
        result[key] = value
    return result


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_float=Decimal,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is not valid JSON: {exc}") from exc


def _validate_table_contract(
    raw: object,
    *,
    media_type: str,
    label: str,
) -> dict[str, Any]:
    table = dict(_mapping(raw, label))
    _exact_keys(
        table,
        allowed={"key_fields", "order_by", "records_pointer"},
        required={"key_fields", "order_by"},
        label=label,
    )
    key_fields = [
        _required_text(item, f"{label}.key_fields[]")
        for item in _sequence(table["key_fields"], f"{label}.key_fields")
    ]
    order_by = [
        _required_text(item, f"{label}.order_by[]")
        for item in _sequence(table["order_by"], f"{label}.order_by")
    ]
    if not key_fields or len(key_fields) != len(set(key_fields)):
        raise ValueError(f"{label}.key_fields must contain unique field names")
    if not order_by or len(order_by) != len(set(order_by)):
        raise ValueError(f"{label}.order_by must contain unique field names")
    records_pointer = table.get("records_pointer", "")
    if media_type == "text/csv" and records_pointer not in {"", None}:
        raise ValueError(f"{label}.records_pointer is only valid for JSON")
    if records_pointer not in {"", None}:
        records_pointer = _required_text(records_pointer, f"{label}.records_pointer")
        if not records_pointer.startswith("/"):
            raise ValueError(f"{label}.records_pointer must be a JSON Pointer")
    return {
        "key_fields": key_fields,
        "order_by": order_by,
        "records_pointer": records_pointer or "",
    }


def _load_bundle(
    *,
    base_dir: Path,
    bundle_ref: Mapping[str, Any],
) -> tuple[dict[str, Any], str, str, dict[str, EvidenceArtifact]]:
    _exact_keys(
        bundle_ref,
        allowed={"path", "sha256"},
        required={"path", "sha256"},
        label="deck_plan.evidence.bundle",
    )
    bundle_path_text, bundle_path = _contained_file(
        base_dir,
        bundle_ref["path"],
        "deck_plan.evidence.bundle.path",
    )
    expected_sha = _required_text(
        bundle_ref["sha256"], "deck_plan.evidence.bundle.sha256"
    )
    if not SHA256_RE.fullmatch(expected_sha):
        raise ValueError(
            "deck_plan.evidence.bundle.sha256 must be a lowercase SHA-256 value"
        )
    actual_sha = sha256_file(bundle_path)
    if actual_sha != expected_sha:
        raise ValueError(
            "evidence bundle hash mismatch: "
            f"expected {expected_sha}, found {actual_sha}"
        )
    raw_bundle = _mapping(_load_json(bundle_path, "evidence bundle"), "evidence bundle")
    bundle = dict(raw_bundle)
    _exact_keys(
        bundle,
        allowed={"schema_version", "bundle_id", "description", "artifacts"},
        required={"schema_version", "bundle_id", "artifacts"},
        label="evidence bundle",
    )
    if bundle.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported evidence bundle schema: {bundle.get('schema_version')!r}"
        )
    _safe_id(bundle.get("bundle_id"), "evidence bundle.bundle_id")
    if "description" in bundle and not isinstance(bundle["description"], str):
        raise ValueError("evidence bundle.description must be text")

    artifacts: dict[str, EvidenceArtifact] = {}
    source_ids: set[str] = set()
    bundle_dir = bundle_path.parent
    for index, raw_artifact in enumerate(
        _sequence(bundle["artifacts"], "evidence bundle.artifacts")
    ):
        label = f"evidence bundle.artifacts[{index}]"
        artifact = _mapping(raw_artifact, label)
        _exact_keys(
            artifact,
            allowed={
                "id",
                "source_id",
                "path",
                "media_type",
                "sha256",
                "size_bytes",
                "snapshot_id",
                "description",
                "provenance",
                "table",
            },
            required={
                "id",
                "source_id",
                "path",
                "media_type",
                "sha256",
                "size_bytes",
            },
            label=label,
        )
        artifact_id = _safe_id(artifact.get("id"), f"{label}.id")
        source_id = _safe_id(artifact.get("source_id"), f"{label}.source_id")
        if artifact_id in artifacts:
            raise ValueError(f"duplicate evidence artifact ID: {artifact_id}")
        if source_id in source_ids:
            raise ValueError(f"duplicate evidence artifact source ID: {source_id}")
        source_ids.add(source_id)
        media_type = _required_text(artifact.get("media_type"), f"{label}.media_type")
        if media_type not in SUPPORTED_MEDIA_TYPES:
            raise ValueError(f"{label}.media_type is unsupported: {media_type!r}")
        path_text, path = _contained_file(
            bundle_dir,
            artifact.get("path"),
            f"{label}.path",
        )
        expected_artifact_sha = _required_text(
            artifact.get("sha256"), f"{label}.sha256"
        )
        if not SHA256_RE.fullmatch(expected_artifact_sha):
            raise ValueError(f"{label}.sha256 must be a lowercase SHA-256 value")
        actual_artifact_sha = sha256_file(path)
        if actual_artifact_sha != expected_artifact_sha:
            raise ValueError(
                f"evidence artifact {artifact_id!r} hash mismatch: "
                f"expected {expected_artifact_sha}, found {actual_artifact_sha}"
            )
        expected_size = artifact.get("size_bytes")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
        ):
            raise ValueError(f"{label}.size_bytes must be a non-negative integer")
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            raise ValueError(
                f"evidence artifact {artifact_id!r} size mismatch: "
                f"expected {expected_size}, found {actual_size}"
            )
        table = (
            _validate_table_contract(
                artifact["table"],
                media_type=media_type,
                label=f"{label}.table",
            )
            if "table" in artifact
            else None
        )
        snapshot_id = str(artifact.get("snapshot_id", "")).strip()
        artifacts[artifact_id] = EvidenceArtifact(
            artifact_id=artifact_id,
            source_id=source_id,
            path=path_text,
            resolved_path=path,
            media_type=media_type,
            sha256=actual_artifact_sha,
            size_bytes=actual_size,
            table=table,
            snapshot_id=snapshot_id,
        )
    return bundle, bundle_path_text, actual_sha, artifacts


def _json_pointer(payload: Any, pointer: object, label: str) -> Any:
    pointer_text = _required_text(pointer, label)
    if not pointer_text.startswith("/"):
        raise ValueError(f"{label} must be a JSON Pointer")
    current = payload
    for raw_token in pointer_text[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            raise ValueError(
                f"{label} may not address an array position; materialize a keyed object"
            )
        if not isinstance(current, Mapping) or token not in current:
            raise ValueError(f"{label} does not resolve at token {token!r}")
        current = current[token]
    return current


def _artifact_payload(
    artifact: EvidenceArtifact,
    cache: dict[str, Any],
) -> Any:
    if artifact.artifact_id in cache:
        return cache[artifact.artifact_id]
    if artifact.media_type == "application/json":
        payload = _load_json(
            artifact.resolved_path,
            f"evidence artifact {artifact.artifact_id!r}",
        )
    else:
        with artifact.resolved_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or any(not field for field in reader.fieldnames):
                raise ValueError(
                    f"evidence artifact {artifact.artifact_id!r} has invalid headers"
                )
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError(
                    f"evidence artifact {artifact.artifact_id!r} has duplicate headers"
                )
            payload = [dict(row) for row in reader]
    cache[artifact.artifact_id] = payload
    return payload


def _table_rows(
    artifact: EvidenceArtifact,
    cache: dict[str, Any],
) -> list[dict[str, Any]]:
    if artifact.table is None:
        raise ValueError(
            f"evidence artifact {artifact.artifact_id!r} has no table contract"
        )
    payload = _artifact_payload(artifact, cache)
    pointer = artifact.table.get("records_pointer", "")
    if pointer:
        payload = _json_pointer(
            payload,
            pointer,
            f"artifact {artifact.artifact_id!r}.table.records_pointer",
        )
    raw_rows = _sequence(payload, f"evidence artifact {artifact.artifact_id!r} rows")
    rows = [
        dict(_mapping(row, f"evidence artifact {artifact.artifact_id!r} rows[{index}]"))
        for index, row in enumerate(raw_rows)
    ]
    key_fields = list(artifact.table["key_fields"])
    order_fields = list(artifact.table["order_by"])
    required_fields = set(key_fields) | set(order_fields)
    seen_keys: set[tuple[str, ...]] = set()
    for index, row in enumerate(rows):
        missing = sorted(required_fields - set(row))
        if missing:
            raise ValueError(
                f"evidence artifact {artifact.artifact_id!r} row {index} "
                f"is missing table fields: {missing}"
            )
        row_key = tuple(str(row[field]) for field in key_fields)
        if row_key in seen_keys:
            raise ValueError(
                f"evidence artifact {artifact.artifact_id!r} has duplicate "
                f"table key {row_key}"
            )
        seen_keys.add(row_key)
    return sorted(
        rows,
        key=lambda row: tuple(
            str(row[field]) for field in [*order_fields, *key_fields]
        ),
    )


def _coerce_value_type(value: Any, value_type: str, label: str) -> Any:
    if value_type not in SUPPORTED_VALUE_TYPES:
        raise ValueError(f"{label}.value_type is unsupported: {value_type!r}")
    if value is None:
        raise ValueError(f"{label} resolved to null")
    if value_type == "decimal":
        return _canonical_decimal(_as_decimal(value, label))
    if value_type == "integer":
        decimal = _as_decimal(value, label)
        integral = decimal.to_integral_value()
        if decimal != integral:
            raise ValueError(f"{label} must resolve to an integer")
        return int(integral)
    if value_type == "string":
        if not isinstance(value, str):
            raise ValueError(f"{label} must resolve to text")
        return value
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{label} must resolve to a boolean")
        return value
    if value_type == "records":
        records = _sequence(value, label)
        if any(not isinstance(record, Mapping) for record in records):
            raise ValueError(f"{label} must resolve to an array of objects")
        return _json_safe(records)
    return _json_safe(value)


def _display_affix(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    if any(character.isnumeric() for character in value):
        raise ValueError(f"{label} may not contain numeric characters")
    return value


def _format_decimal(value: Any, spec: object, label: str) -> str:
    display = _mapping(spec, label)
    _exact_keys(
        display,
        allowed={
            "decimals",
            "scale",
            "rounding",
            "grouping",
            "sign",
            "prefix",
            "suffix",
            "negative_style",
            "trim_trailing_zeros",
        },
        required={"decimals"},
        label=label,
    )
    decimals = display.get("decimals")
    if (
        not isinstance(decimals, int)
        or isinstance(decimals, bool)
        or not 0 <= decimals <= 12
    ):
        raise ValueError(f"{label}.decimals must be an integer from 0 to 12")
    scale = _as_decimal(display.get("scale", "1"), f"{label}.scale")
    rounding_name = str(display.get("rounding", "half_up"))
    if rounding_name not in ROUNDING_MODES:
        raise ValueError(f"{label}.rounding is unsupported: {rounding_name!r}")
    grouping = display.get("grouping", False)
    trim = display.get("trim_trailing_zeros", False)
    if not isinstance(grouping, bool):
        raise ValueError(f"{label}.grouping must be a boolean")
    if not isinstance(trim, bool):
        raise ValueError(f"{label}.trim_trailing_zeros must be a boolean")
    sign = str(display.get("sign", "auto"))
    if sign not in {"always", "auto"}:
        raise ValueError(f"{label}.sign must be 'always' or 'auto'")
    negative_style = str(display.get("negative_style", "minus"))
    if negative_style not in {"minus", "parentheses"}:
        raise ValueError(f"{label}.negative_style must be 'minus' or 'parentheses'")
    # Prefix and suffix are the only free-form display fields. Keep them useful
    # for units and currencies without allowing manually supplied quantities.
    prefix = _display_affix(display.get("prefix", ""), f"{label}.prefix")
    suffix = _display_affix(display.get("suffix", ""), f"{label}.suffix")
    numeric_value = _as_decimal(value, label)
    exact_product_precision = (
        len(numeric_value.as_tuple().digits) + len(scale.as_tuple().digits) + 2
    )
    with localcontext() as context:
        context.prec = max(exact_product_precision, decimals + 2)
        scaled = numeric_value * scale
        rounded_precision = max(scaled.adjusted() + 1, 1) + decimals + 2
        context.prec = max(context.prec, rounded_precision)
        quantum = Decimal(1).scaleb(-decimals)
        rounded = scaled.quantize(
            quantum,
            rounding=ROUNDING_MODES[rounding_name],
        )
    if rounded == 0:
        rounded = rounded.copy_abs()
    magnitude = rounded.copy_abs()
    number = f"{magnitude:,.{decimals}f}" if grouping else f"{magnitude:.{decimals}f}"
    if trim and "." in number:
        number = number.rstrip("0").rstrip(".")
    if rounded < 0 and negative_style == "parentheses":
        return f"({prefix}{number}{suffix})"
    sign_text = "-" if rounded < 0 else "+" if sign == "always" else ""
    return f"{sign_text}{prefix}{number}{suffix}"


def _resolve_binding_definition(
    *,
    binding_id: str,
    raw_definition: object,
    artifacts: Mapping[str, EvidenceArtifact],
    payload_cache: dict[str, Any],
) -> ResolvedBinding:
    label = f"deck_plan.evidence.bindings.{binding_id}"
    definition = _mapping(raw_definition, label)
    allowed_common = {"kind", "artifact_id", "value_type", "display"}
    kind = _required_text(definition.get("kind"), f"{label}.kind")
    if kind == "json_pointer":
        allowed = allowed_common | {"pointer"}
        required = {"kind", "artifact_id", "pointer", "value_type"}
    elif kind == "table_cell":
        allowed = allowed_common | {"row_key", "field"}
        required = {"kind", "artifact_id", "row_key", "field", "value_type"}
    elif kind == "table_rows":
        allowed = allowed_common | {"fields"}
        required = {"kind", "artifact_id", "fields", "value_type"}
    else:
        raise ValueError(f"{label}.kind is unsupported: {kind!r}")
    _exact_keys(definition, allowed=allowed, required=required, label=label)
    artifact_id = _safe_id(definition.get("artifact_id"), f"{label}.artifact_id")
    artifact = artifacts.get(artifact_id)
    if artifact is None:
        raise ValueError(f"{label} references unknown artifact {artifact_id!r}")
    value_type = _required_text(definition.get("value_type"), f"{label}.value_type")
    payload = _artifact_payload(artifact, payload_cache)

    if kind == "json_pointer":
        if artifact.media_type != "application/json":
            raise ValueError(f"{label} json_pointer requires a JSON artifact")
        raw_value = _json_pointer(payload, definition["pointer"], f"{label}.pointer")
    elif kind == "table_cell":
        rows = _table_rows(artifact, payload_cache)
        if artifact.table is None:
            raise ValueError(f"{label} requires an artifact with a table contract")
        row_key = _mapping(definition["row_key"], f"{label}.row_key")
        key_fields = list(artifact.table["key_fields"])
        if set(row_key) != set(key_fields):
            raise ValueError(
                f"{label}.row_key must contain exactly the table key fields "
                f"{key_fields}"
            )
        matches = [
            row
            for row in rows
            if all(str(row[field]) == str(row_key[field]) for field in key_fields)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"{label} must resolve exactly one table row; found {len(matches)}"
            )
        field = _required_text(definition["field"], f"{label}.field")
        if field not in matches[0]:
            raise ValueError(f"{label}.field is missing from the resolved row: {field}")
        raw_value = matches[0][field]
    else:
        rows = _table_rows(artifact, payload_cache)
        fields = _mapping(definition["fields"], f"{label}.fields")
        if not fields:
            raise ValueError(f"{label}.fields cannot be empty")
        normalized_fields = {
            _required_text(output_field, f"{label}.fields output"): _required_text(
                source_field,
                f"{label}.fields.{output_field}",
            )
            for output_field, source_field in fields.items()
        }
        missing_fields = sorted(
            {
                source_field
                for source_field in normalized_fields.values()
                if any(source_field not in row for row in rows)
            }
        )
        if missing_fields:
            raise ValueError(
                f"{label}.fields are missing from table rows: {missing_fields}"
            )
        raw_value = [
            {
                output_field: row[source_field]
                for output_field, source_field in normalized_fields.items()
            }
            for row in rows
        ]

    normalized_value = _coerce_value_type(raw_value, value_type, label)
    if kind == "table_rows" and value_type != "records":
        raise ValueError(f"{label}.value_type must be 'records' for table_rows")
    display_value = None
    if "display" in definition:
        if value_type not in {"decimal", "integer"}:
            raise ValueError(f"{label}.display requires a numeric value_type")
        display_value = _format_decimal(
            normalized_value,
            definition["display"],
            f"{label}.display",
        )
    return ResolvedBinding(
        binding_id=binding_id,
        artifact=artifact,
        definition=dict(definition),
        raw_value=normalized_value,
        display_value=display_value,
        value_sha256=sha256_bytes(canonical_json_bytes(normalized_value)),
    )


def _pointer_path(parts: Sequence[str]) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)


def _binding_reference(value: object, label: str) -> tuple[str, str]:
    reference = _mapping(value, label)
    _exact_keys(
        reference,
        allowed={"id", "mode"},
        required={"id", "mode"},
        label=label,
    )
    binding_id = _safe_id(reference.get("id"), f"{label}.id")
    mode = _required_text(reference.get("mode"), f"{label}.mode")
    if mode not in {"display", "raw"}:
        raise ValueError(f"{label}.mode must be 'display' or 'raw'")
    return binding_id, mode


def _resolved_use(
    *,
    binding_id: str,
    mode: str,
    bindings: Mapping[str, ResolvedBinding],
    consumer: str,
    path: str,
    uses: list[dict[str, Any]],
) -> Any:
    binding = bindings.get(binding_id)
    if binding is None:
        raise ValueError(f"{consumer}{path} references unknown binding {binding_id!r}")
    if mode == "display":
        if binding.display_value is None:
            raise ValueError(
                f"binding {binding_id!r} has no display contract for {consumer}{path}"
            )
        resolved = binding.display_value
    else:
        resolved = binding.raw_value
    uses.append(
        {
            "binding_id": binding_id,
            "consumer": consumer,
            "path": path,
            "mode": mode,
            "artifact_id": binding.artifact.artifact_id,
            "artifact_sha256": binding.artifact.sha256,
            "source_id": binding.artifact.source_id,
            "address": {
                key: _json_safe(value)
                for key, value in binding.definition.items()
                if key != "value_type"
            },
            "value_type": binding.definition["value_type"],
            "value_sha256": binding.value_sha256,
            "raw_value": _json_safe(binding.raw_value),
            "resolved_value": _json_safe(resolved),
        }
    )
    return _json_safe(resolved)


def _template_placeholders(template: str, label: str) -> list[str]:
    placeholders: list[str] = []
    formatter = string.Formatter()
    try:
        parsed = list(formatter.parse(template))
    except ValueError as exc:
        raise ValueError(f"{label}.text has invalid braces") from exc
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if (
            not PLACEHOLDER_RE.fullmatch(field_name)
            or format_spec
            or conversion is not None
        ):
            raise ValueError(
                f"{label}.text placeholders must be simple names without "
                "format specs or conversions"
            )
        placeholders.append(field_name)
    if len(placeholders) != len(set(placeholders)):
        raise ValueError(f"{label}.text may reference each placeholder only once")
    return placeholders


def _resolve_tree(
    value: Any,
    *,
    bindings: Mapping[str, ResolvedBinding],
    consumer: str,
    path_parts: list[str],
    uses: list[dict[str, Any]],
) -> Any:
    path = _pointer_path(path_parts)
    if isinstance(value, Mapping) and "$binding" in value:
        if set(value) != {"$binding"}:
            raise ValueError(f"{consumer}{path} binding object has sibling fields")
        binding_id, mode = _binding_reference(
            value["$binding"], f"{consumer}{path}.$binding"
        )
        return _resolved_use(
            binding_id=binding_id,
            mode=mode,
            bindings=bindings,
            consumer=consumer,
            path=path,
            uses=uses,
        )
    if isinstance(value, Mapping) and "$template" in value:
        if set(value) != {"$template"}:
            raise ValueError(f"{consumer}{path} template object has sibling fields")
        template = _mapping(value["$template"], f"{consumer}{path}.$template")
        _exact_keys(
            template,
            allowed={"text", "bindings"},
            required={"text", "bindings"},
            label=f"{consumer}{path}.$template",
        )
        text_value = _required_text(
            template["text"], f"{consumer}{path}.$template.text"
        )
        placeholders = _template_placeholders(text_value, f"{consumer}{path}.$template")
        template_bindings = _mapping(
            template["bindings"], f"{consumer}{path}.$template.bindings"
        )
        if set(placeholders) != set(template_bindings):
            raise ValueError(
                f"{consumer}{path} template placeholders and bindings differ; "
                f"placeholders={sorted(placeholders)}, "
                f"bindings={sorted(template_bindings)}"
            )
        replacements: dict[str, str] = {}
        for placeholder in placeholders:
            binding_id, mode = _binding_reference(
                template_bindings[placeholder],
                f"{consumer}{path}.$template.bindings.{placeholder}",
            )
            resolved = _resolved_use(
                binding_id=binding_id,
                mode=mode,
                bindings=bindings,
                consumer=consumer,
                path=f"{path}#{placeholder}",
                uses=uses,
            )
            if isinstance(resolved, (Mapping, Sequence)) and not isinstance(
                resolved, str
            ):
                raise ValueError(
                    f"{consumer}{path} template binding {placeholder!r} "
                    "must resolve to a scalar"
                )
            replacements[placeholder] = str(resolved)
        return text_value.format_map(replacements)
    if isinstance(value, Mapping):
        return {
            str(key): _resolve_tree(
                item,
                bindings=bindings,
                consumer=consumer,
                path_parts=[*path_parts, str(key)],
                uses=uses,
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _resolve_tree(
                item,
                bindings=bindings,
                consumer=consumer,
                path_parts=[*path_parts, str(index)],
                uses=uses,
            )
            for index, item in enumerate(value)
        ]
    return value


def _scan_quantitative_literals(
    value: Any,
    *,
    label: str,
    path_parts: list[str],
) -> list[str]:
    path = _pointer_path(path_parts)
    if isinstance(value, Mapping) and "$binding" in value:
        return []
    if isinstance(value, Mapping) and "$template" in value:
        template = _mapping(value["$template"], f"{label}{path}.$template")
        text_value = template.get("text")
        if isinstance(text_value, str) and QUANTITATIVE_TOKEN_RE.search(text_value):
            return [f"{label}{path}.$template.text"]
        return []
    if isinstance(value, Mapping):
        found: list[str] = []
        for key, item in value.items():
            if str(key) in STRUCTURAL_CONTENT_KEYS:
                continue
            found.extend(
                _scan_quantitative_literals(
                    item,
                    label=label,
                    path_parts=[*path_parts, str(key)],
                )
            )
        return found
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        found = []
        for index, item in enumerate(value):
            found.extend(
                _scan_quantitative_literals(
                    item,
                    label=label,
                    path_parts=[*path_parts, str(index)],
                )
            )
        return found
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float, Decimal)):
        return [f"{label}{path}"]
    if isinstance(value, str) and QUANTITATIVE_TOKEN_RE.search(value):
        return [f"{label}{path}"]
    return []


def assert_no_unbound_quantitative_content(
    plan: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> None:
    """Reject visible numeric content that does not use an evidence binding."""

    found: list[str] = []
    for index, raw_slide in enumerate(
        _sequence(plan.get("slides"), "deck_plan.slides")
    ):
        slide = _mapping(raw_slide, f"deck_plan.slides[{index}]")
        if slide.get("layout_id") == "bespoke" or "bespoke_html" in slide:
            raise ValueError(
                "source-bound plans do not permit bespoke_html because its "
                "numeric content cannot be traced structurally"
            )
        for field in ("title", "chapter_label", "notes", "slots"):
            if field in slide:
                found.extend(
                    _scan_quantitative_literals(
                        slide[field],
                        label="deck_plan",
                        path_parts=["slides", str(index), field],
                    )
                )
    for slide_index, raw_slide in enumerate(
        _sequence(ledger.get("slides"), "content_ledger.slides")
    ):
        slide = _mapping(raw_slide, f"content_ledger.slides[{slide_index}]")
        if "basis_note" in slide:
            found.extend(
                _scan_quantitative_literals(
                    slide["basis_note"],
                    label="content_ledger",
                    path_parts=["slides", str(slide_index), "basis_note"],
                )
            )
        for claim_index, raw_claim in enumerate(
            _sequence(
                slide.get("claims", []),
                f"content_ledger.slides[{slide_index}].claims",
            )
        ):
            claim = _mapping(
                raw_claim,
                f"content_ledger.slides[{slide_index}].claims[{claim_index}]",
            )
            for field in ("statement", "basis_note", "qualification"):
                if field in claim:
                    found.extend(
                        _scan_quantitative_literals(
                            claim[field],
                            label="content_ledger",
                            path_parts=[
                                "slides",
                                str(slide_index),
                                "claims",
                                str(claim_index),
                                field,
                            ],
                        )
                    )
    if found:
        preview = ", ".join(found[:8])
        remainder = f" (+{len(found) - 8} more)" if len(found) > 8 else ""
        raise ValueError(
            "source-bound plans require evidence bindings for every quantitative "
            f"content value; unbound values at {preview}{remainder}"
        )


def _validate_source_links(
    *,
    plan: Mapping[str, Any],
    ledger: Mapping[str, Any],
    uses: Sequence[Mapping[str, Any]],
    artifacts: Mapping[str, EvidenceArtifact],
) -> None:
    raw_sources = _sequence(ledger.get("sources"), "content_ledger.sources")
    ledger_sources: dict[str, Mapping[str, Any]] = {}
    for index, raw_source in enumerate(raw_sources):
        source = _mapping(raw_source, f"content_ledger.sources[{index}]")
        source_id = _safe_id(source.get("id"), f"content_ledger.sources[{index}].id")
        ledger_sources[source_id] = source

    used_artifact_ids = {str(use["artifact_id"]) for use in uses}
    for artifact_id in sorted(used_artifact_ids):
        artifact = artifacts[artifact_id]
        source = ledger_sources.get(artifact.source_id)
        if source is None:
            raise ValueError(
                f"used evidence artifact {artifact_id!r} requires ledger source "
                f"{artifact.source_id!r}"
            )
        ledger_sha = str(source.get("sha256", "")).strip()
        if ledger_sha != artifact.sha256:
            raise ValueError(
                f"ledger source {artifact.source_id!r} must carry artifact "
                f"{artifact_id!r} SHA-256 {artifact.sha256}; found {ledger_sha!r}"
            )

    plan_slides = _sequence(plan.get("slides"), "deck_plan.slides")
    ledger_slides = _sequence(ledger.get("slides"), "content_ledger.slides")
    for use in uses:
        consumer = str(use["consumer"])
        path = str(use["path"])
        source_id = str(use["source_id"])
        parts = path.lstrip("/").split("/")
        if len(parts) < 2 or parts[0] != "slides" or not parts[1].isdigit():
            raise ValueError(
                f"evidence binding use must belong to a slide: {consumer}{path}"
            )
        slide_index = int(parts[1])
        if consumer == "deck_plan":
            slide = _mapping(
                plan_slides[slide_index],
                f"deck_plan.slides[{slide_index}]",
            )
            refs = {
                str(item)
                for item in _sequence(
                    slide.get("source_refs", []),
                    f"deck_plan.slides[{slide_index}].source_refs",
                )
            }
            if source_id not in refs:
                raise ValueError(
                    f"{consumer}{path} uses source {source_id!r}, but the slide "
                    "does not include it in source_refs"
                )
            continue

        slide = _mapping(
            ledger_slides[slide_index],
            f"content_ledger.slides[{slide_index}]",
        )
        claims = _sequence(
            slide.get("claims", []),
            f"content_ledger.slides[{slide_index}].claims",
        )
        if len(parts) >= 4 and parts[2] == "claims" and parts[3].isdigit():
            claim_index = int(parts[3])
            claim = _mapping(
                claims[claim_index],
                f"content_ledger.slides[{slide_index}].claims[{claim_index}]",
            )
            refs = {
                str(item)
                for item in _sequence(
                    claim.get("source_ids", []),
                    f"content_ledger claim {claim_index}.source_ids",
                )
            }
        else:
            refs = {
                str(item)
                for raw_claim in claims
                for item in _sequence(
                    _mapping(raw_claim, "content_ledger claim").get("source_ids", []),
                    "content_ledger claim.source_ids",
                )
            }
        if source_id not in refs:
            raise ValueError(
                f"{consumer}{path} uses source {source_id!r}, but its claim "
                "does not cite that source"
            )


def resolve_source_bound_documents(
    *,
    plan: Mapping[str, Any],
    ledger: Mapping[str, Any],
    base_dir: Path,
) -> EvidenceResolution:
    """Resolve a v2 plan and ledger from a sealed domain-neutral evidence bundle."""

    if plan.get("schema_version") != SOURCE_BOUND_PLAN_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported source-bound deck plan schema: "
            f"{plan.get('schema_version')!r}"
        )
    _exact_keys(
        plan,
        allowed={"schema_version", "allow_bespoke_html", "evidence", "slides"},
        required={"schema_version", "evidence", "slides"},
        label="deck_plan",
    )
    if ledger.get("schema_version") != SOURCE_BOUND_LEDGER_SCHEMA_VERSION:
        raise ValueError(
            f"source-bound deck plans require content ledger schema "
            f"{SOURCE_BOUND_LEDGER_SCHEMA_VERSION!r}"
        )
    evidence = _mapping(plan.get("evidence"), "deck_plan.evidence")
    _exact_keys(
        evidence,
        allowed={"bundle", "bindings", "numeric_policy"},
        required={"bundle", "bindings", "numeric_policy"},
        label="deck_plan.evidence",
    )
    if evidence.get("numeric_policy") != "require_bindings":
        raise ValueError("deck_plan.evidence.numeric_policy must be 'require_bindings'")
    allow_bespoke = plan.get("allow_bespoke_html", False)
    if not isinstance(allow_bespoke, bool):
        raise ValueError("deck_plan.allow_bespoke_html must be a boolean")
    if allow_bespoke:
        raise ValueError("source-bound plans do not permit allow_bespoke_html")

    assert_no_unbound_quantitative_content(plan, ledger)
    bundle, bundle_path, bundle_sha, artifacts = _load_bundle(
        base_dir=base_dir,
        bundle_ref=_mapping(evidence["bundle"], "deck_plan.evidence.bundle"),
    )
    raw_bindings = _mapping(evidence["bindings"], "deck_plan.evidence.bindings")
    if not raw_bindings:
        raise ValueError("deck_plan.evidence.bindings cannot be empty")
    payload_cache: dict[str, Any] = {}
    bindings: dict[str, ResolvedBinding] = {}
    for raw_binding_id, definition in raw_bindings.items():
        binding_id = _safe_id(
            raw_binding_id,
            "deck_plan.evidence.bindings binding ID",
        )
        bindings[binding_id] = _resolve_binding_definition(
            binding_id=binding_id,
            raw_definition=definition,
            artifacts=artifacts,
            payload_cache=payload_cache,
        )

    uses: list[dict[str, Any]] = []
    plan_body = {
        key: value
        for key, value in plan.items()
        if key not in {"schema_version", "evidence"}
    }
    resolved_plan = _resolve_tree(
        plan_body,
        bindings=bindings,
        consumer="deck_plan",
        path_parts=[],
        uses=uses,
    )
    resolved_plan = {
        "schema_version": RESOLVED_PLAN_SCHEMA_VERSION,
        **resolved_plan,
    }
    ledger_body = {
        key: value for key, value in ledger.items() if key != "schema_version"
    }
    resolved_ledger = _resolve_tree(
        ledger_body,
        bindings=bindings,
        consumer="content_ledger",
        path_parts=[],
        uses=uses,
    )
    resolved_ledger = {
        "schema_version": RESOLVED_LEDGER_SCHEMA_VERSION,
        **resolved_ledger,
    }
    used_binding_ids = {str(use["binding_id"]) for use in uses}
    unused = sorted(set(bindings) - used_binding_ids)
    if unused:
        raise ValueError(
            f"deck_plan.evidence.bindings contains unused bindings: {unused}"
        )
    _validate_source_links(
        plan=plan,
        ledger=ledger,
        uses=uses,
        artifacts=artifacts,
    )

    used_artifact_ids = sorted({str(use["artifact_id"]) for use in uses})
    evidence_ledger = {
        "schema_version": EVIDENCE_LEDGER_SCHEMA_VERSION,
        "status": "verified",
        "bundle": {
            "id": str(bundle["bundle_id"]),
            "path": bundle_path,
            "sha256": bundle_sha,
        },
        "artifacts": [
            {
                "id": artifacts[artifact_id].artifact_id,
                "source_id": artifacts[artifact_id].source_id,
                "path": artifacts[artifact_id].path,
                "media_type": artifacts[artifact_id].media_type,
                "sha256": artifacts[artifact_id].sha256,
                "size_bytes": artifacts[artifact_id].size_bytes,
                "snapshot_id": artifacts[artifact_id].snapshot_id,
            }
            for artifact_id in used_artifact_ids
        ],
        "bindings": sorted(
            uses,
            key=lambda item: (
                str(item["consumer"]),
                str(item["path"]),
                str(item["binding_id"]),
            ),
        ),
        "resolved": {
            "deck_plan_sha256": sha256_bytes(canonical_json_bytes(resolved_plan)),
            "content_ledger_sha256": sha256_bytes(
                canonical_json_bytes(_publication_content_ledger(resolved_ledger))
            ),
        },
        "boundary": (
            "Verified transport and deterministic display fidelity only. Evidence "
            "selection, upstream calculations, and interpretation remain reviewed "
            "model or human judgments."
        ),
    }
    return EvidenceResolution(
        resolved_plan=dict(resolved_plan),
        resolved_ledger=dict(resolved_ledger),
        evidence_ledger=evidence_ledger,
    )


def embedded_evidence_ledger_markup(ledger: Mapping[str, Any] | None) -> str:
    """Return safe embedded JSON for a verified evidence ledger."""

    if ledger is None:
        payload: Mapping[str, Any] = {
            "schema_version": EVIDENCE_LEDGER_SCHEMA_VERSION,
            "status": "not_verified",
        }
    else:
        payload = ledger
    serialized = json.dumps(
        _json_safe(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    serialized = (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return (
        f'<script type="application/json" id="{EVIDENCE_LEDGER_ELEMENT_ID}">'
        f"{serialized}</script>"
    )


def validate_evidence_ledger(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the sanitized evidence ledger embedded in a publication."""

    if ledger.get("schema_version") != EVIDENCE_LEDGER_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported evidence ledger schema: {ledger.get('schema_version')!r}"
        )
    status = _required_text(ledger.get("status"), "evidence ledger.status")
    if status == "not_verified":
        _exact_keys(
            ledger,
            allowed={"schema_version", "status"},
            required={"schema_version", "status"},
            label="evidence ledger",
        )
        return {
            "schema_version": EVIDENCE_LEDGER_SCHEMA_VERSION,
            "status": "not_verified",
        }
    if status != "verified":
        raise ValueError(f"unsupported evidence ledger status: {status!r}")
    _exact_keys(
        ledger,
        allowed={
            "schema_version",
            "status",
            "bundle",
            "artifacts",
            "bindings",
            "resolved",
            "boundary",
        },
        required={
            "schema_version",
            "status",
            "bundle",
            "artifacts",
            "bindings",
            "resolved",
            "boundary",
        },
        label="evidence ledger",
    )
    bundle = _mapping(ledger["bundle"], "evidence ledger.bundle")
    _exact_keys(
        bundle,
        allowed={"id", "path", "sha256"},
        required={"id", "path", "sha256"},
        label="evidence ledger.bundle",
    )
    _safe_id(bundle["id"], "evidence ledger.bundle.id")
    if not SHA256_RE.fullmatch(
        _required_text(bundle["sha256"], "evidence ledger.bundle.sha256")
    ):
        raise ValueError("evidence ledger.bundle.sha256 must be a SHA-256 value")

    artifact_ids: set[str] = set()
    source_ids: set[str] = set()
    artifact_index: dict[str, Mapping[str, Any]] = {}
    normalized_artifacts: list[dict[str, Any]] = []
    for index, raw_artifact in enumerate(
        _sequence(ledger["artifacts"], "evidence ledger.artifacts")
    ):
        label = f"evidence ledger.artifacts[{index}]"
        artifact = _mapping(raw_artifact, label)
        _exact_keys(
            artifact,
            allowed={
                "id",
                "source_id",
                "path",
                "media_type",
                "sha256",
                "size_bytes",
                "snapshot_id",
            },
            required={
                "id",
                "source_id",
                "path",
                "media_type",
                "sha256",
                "size_bytes",
                "snapshot_id",
            },
            label=label,
        )
        artifact_id = _safe_id(artifact["id"], f"{label}.id")
        source_id = _safe_id(artifact["source_id"], f"{label}.source_id")
        if artifact_id in artifact_ids or source_id in source_ids:
            raise ValueError("evidence ledger artifact and source IDs must be unique")
        artifact_ids.add(artifact_id)
        source_ids.add(source_id)
        artifact_index[artifact_id] = artifact
        sha = _required_text(artifact["sha256"], f"{label}.sha256")
        if not SHA256_RE.fullmatch(sha):
            raise ValueError(f"{label}.sha256 must be a SHA-256 value")
        size = artifact["size_bytes"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"{label}.size_bytes must be non-negative")
        normalized_artifacts.append(dict(artifact))
    if not normalized_artifacts:
        raise ValueError("verified evidence ledger must include artifacts")

    normalized_bindings: list[dict[str, Any]] = []
    for index, raw_binding in enumerate(
        _sequence(ledger["bindings"], "evidence ledger.bindings")
    ):
        label = f"evidence ledger.bindings[{index}]"
        binding = _mapping(raw_binding, label)
        required = {
            "binding_id",
            "consumer",
            "path",
            "mode",
            "artifact_id",
            "artifact_sha256",
            "source_id",
            "address",
            "value_type",
            "value_sha256",
            "raw_value",
            "resolved_value",
        }
        _exact_keys(binding, allowed=required, required=required, label=label)
        artifact_id = _safe_id(binding["artifact_id"], f"{label}.artifact_id")
        source_id = _safe_id(binding["source_id"], f"{label}.source_id")
        if artifact_id not in artifact_ids or source_id not in source_ids:
            raise ValueError(f"{label} references an unknown artifact or source")
        for field in ("artifact_sha256", "value_sha256"):
            if not SHA256_RE.fullmatch(
                _required_text(binding[field], f"{label}.{field}")
            ):
                raise ValueError(f"{label}.{field} must be a SHA-256 value")
        expected_value_sha = sha256_bytes(canonical_json_bytes(binding["raw_value"]))
        if binding["value_sha256"] != expected_value_sha:
            raise ValueError(
                f"{label}.value_sha256 does not match its canonical raw_value"
            )
        mode = _required_text(binding["mode"], f"{label}.mode")
        if mode not in {"display", "raw"}:
            raise ValueError(f"{label}.mode must be 'display' or 'raw'")
        value_type = _required_text(binding["value_type"], f"{label}.value_type")
        address = _mapping(binding["address"], f"{label}.address")
        if address.get("artifact_id") != artifact_id:
            raise ValueError(f"{label}.address does not match its evidence artifact")
        if mode == "display":
            if value_type not in {"decimal", "integer"} or "display" not in address:
                raise ValueError(
                    f"{label} display use is missing its numeric formatting contract"
                )
            expected_resolved_value: Any = _format_decimal(
                binding["raw_value"],
                address["display"],
                f"{label}.address.display",
            )
        else:
            expected_resolved_value = binding["raw_value"]
        if canonical_json_bytes(binding["resolved_value"]) != canonical_json_bytes(
            expected_resolved_value
        ):
            raise ValueError(
                f"{label}.resolved_value does not match its raw value and mode"
            )
        artifact = artifact_index[artifact_id]
        if (
            binding["artifact_sha256"] != artifact["sha256"]
            or source_id != artifact["source_id"]
        ):
            raise ValueError(f"{label} does not match its evidence artifact")
        normalized_bindings.append(dict(binding))
    if not normalized_bindings:
        raise ValueError("verified evidence ledger must include binding uses")

    resolved = _mapping(ledger["resolved"], "evidence ledger.resolved")
    _exact_keys(
        resolved,
        allowed={"deck_plan_sha256", "content_ledger_sha256"},
        required={"deck_plan_sha256", "content_ledger_sha256"},
        label="evidence ledger.resolved",
    )
    if any(
        not SHA256_RE.fullmatch(
            _required_text(value, f"evidence ledger.resolved.{field}")
        )
        for field, value in resolved.items()
    ):
        raise ValueError("evidence ledger resolved digests must be SHA-256 values")
    return dict(ledger)


def extract_embedded_evidence_ledger(html_text: str) -> dict[str, Any] | None:
    """Extract and validate the evidence ledger from standalone deck HTML."""

    match = EVIDENCE_LEDGER_RE.search(html_text)
    if not match:
        return None
    try:
        payload = json.loads(
            match.group("payload"),
            object_pairs_hook=_unique_json_object,
            parse_float=Decimal,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"embedded evidence ledger is not valid JSON: {exc}") from exc
    return validate_evidence_ledger(_mapping(payload, "embedded evidence ledger"))


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    data = (
        json.dumps(
            _json_safe(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except OSError:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def seal_evidence_bundle(path: Path) -> dict[str, Any]:
    """Fill exact byte hashes and sizes for a draft evidence bundle in place."""

    resolved_path = path.expanduser().resolve()
    bundle = dict(
        _mapping(_load_json(resolved_path, "evidence bundle"), "evidence bundle")
    )
    if bundle.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported evidence bundle schema: {bundle.get('schema_version')!r}"
        )
    artifacts = _sequence(bundle.get("artifacts"), "evidence bundle.artifacts")
    sealed_artifacts: list[dict[str, Any]] = []
    for index, raw_artifact in enumerate(artifacts):
        artifact = dict(_mapping(raw_artifact, f"evidence bundle.artifacts[{index}]"))
        _, artifact_path = _contained_file(
            resolved_path.parent,
            artifact.get("path"),
            f"evidence bundle.artifacts[{index}].path",
        )
        artifact["sha256"] = sha256_file(artifact_path)
        artifact["size_bytes"] = artifact_path.stat().st_size
        sealed_artifacts.append(artifact)
    bundle["artifacts"] = sealed_artifacts
    _atomic_write_json(resolved_path, bundle)
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "bundle": str(resolved_path),
        "sha256": sha256_file(resolved_path),
        "artifact_count": len(sealed_artifacts),
    }


def validate_evidence_bundle(path: Path) -> dict[str, Any]:
    """Validate one sealed bundle and return portable artifact receipts."""

    bundle_path = path.expanduser()
    if not bundle_path.is_absolute():
        bundle_path = Path.cwd() / bundle_path
    bundle_path = bundle_path.absolute()
    bundle_sha256 = sha256_file(bundle_path)
    bundle, _, actual_sha256, artifacts = _load_bundle(
        base_dir=bundle_path.parent,
        bundle_ref={
            "path": bundle_path.name,
            "sha256": bundle_sha256,
        },
    )

    payload_cache: dict[str, Any] = {}
    for artifact in artifacts.values():
        if artifact.table is not None:
            _table_rows(artifact, payload_cache)

    receipts = [
        {
            "id": artifact.artifact_id,
            "source_id": artifact.source_id,
            "path": artifact.path,
            "media_type": artifact.media_type,
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
            "snapshot_id": artifact.snapshot_id,
            "table": dict(artifact.table) if artifact.table is not None else None,
        }
        for artifact in sorted(
            artifacts.values(),
            key=lambda item: item.artifact_id,
        )
    ]
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "bundle_id": str(bundle["bundle_id"]),
        "sha256": actual_sha256,
        "artifact_count": len(receipts),
        "artifacts": receipts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    seal_parser = subparsers.add_parser(
        "seal",
        help="Compute artifact hashes and rewrite a draft evidence bundle.",
    )
    seal_parser.add_argument("bundle", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.command == "seal":
            result = seal_evidence_bundle(args.bundle)
            LOGGER.info(
                "%s",
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            )
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        LOGGER.error("error: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
