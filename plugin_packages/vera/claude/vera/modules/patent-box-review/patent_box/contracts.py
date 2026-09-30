"""Closed JSON contracts; no remote schema resolution or runtime dependencies."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "ContractError",
    "canonical_hash",
    "file_hash",
    "read_json",
    "validate",
    "indexed",
    "verify_evidence",
]

ROOT = Path(__file__).resolve().parents[1]


class ContractError(ValueError):
    pass


def canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: str | Path) -> Any:
    def invalid(value):
        raise ContractError(f"Non-finite JSON number: {value}")

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_pairs,
        parse_constant=invalid,
    )


def validate(value: Any, schema_name: str) -> None:
    """Validate the exact vocabulary used by the bundled Draft 2020-12 schemas.

    Not a general-purpose JSON Schema implementation. Unknown validation keywords
    fail closed, rather than being silently ignored. Can be replaced with a full
    Draft202012Validator without changing the published input contracts.
    """
    schema = read_json(ROOT / "schemas" / schema_name)
    vocabulary = {
        "$schema",
        "$id",
        "$defs",
        "$ref",
        "title",
        "description",
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "anyOf",
        "format",
    }

    def check(node, spec, location):
        unknown = set(spec) - vocabulary
        if unknown:
            raise ContractError(f"Unsupported schema keywords: {sorted(unknown)}")
        if "$ref" in spec:
            target = spec["$ref"]
            if not target.startswith("#/$defs/"):
                raise ContractError("Only local $defs references are supported")
            check(node, schema["$defs"][target.split("/")[-1]], location)
            return
        if "anyOf" in spec:
            for candidate in spec["anyOf"]:
                try:
                    check(node, candidate, location)
                    break
                except ContractError:
                    continue
            else:
                raise ContractError(f"{location}: does not match any allowed shape")
        expected = spec.get("type")
        matches = {
            "object": type(node) is dict,
            "array": type(node) is list,
            "string": type(node) is str,
            "integer": type(node) is int,
            "boolean": type(node) is bool,
            "null": node is None,
        }
        if expected and not matches.get(expected, False):
            raise ContractError(f"{location}: expected {expected}")
        if "const" in spec and node != spec["const"]:
            raise ContractError(f"{location}: wrong constant")
        if "enum" in spec and node not in spec["enum"]:
            raise ContractError(f"{location}: unexpected enum value {node!r}")
        if type(node) is dict:
            for key in spec.get("required", []):
                if key not in node:
                    raise ContractError(f"{location}: missing {key}")
            props = spec.get("properties", {})
            if spec.get("additionalProperties") is False and set(node) - set(props):
                raise ContractError(
                    f"{location}: unknown fields {sorted(set(node)-set(props))}"
                )
            for key in node.keys() & props.keys():
                check(node[key], props[key], f"{location}.{key}")
        if type(node) is list:
            if len(node) < spec.get("minItems", 0) or len(node) > spec.get(
                "maxItems", 10**9
            ):
                raise ContractError(f"{location}: invalid array length")
            if spec.get("uniqueItems") and len(
                {canonical_hash(x) for x in node}
            ) != len(node):
                raise ContractError(f"{location}: duplicate items")
            if "items" in spec:
                for i, item in enumerate(node):
                    check(item, spec["items"], f"{location}[{i}]")
        if type(node) is str:
            if len(node) < spec.get("minLength", 0) or len(node) > spec.get(
                "maxLength", 10**9
            ):
                raise ContractError(f"{location}: invalid string length")
            if "pattern" in spec and not re.fullmatch(spec["pattern"], node):
                raise ContractError(f"{location}: invalid format")
            try:
                if spec.get("format") == "date":
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", node):
                        raise ValueError()
                    date.fromisoformat(node)
                if spec.get("format") == "date-time":
                    parsed = datetime.fromisoformat(node.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        raise ValueError()
            except ValueError as exc:
                raise ContractError(f"{location}: invalid date or timezone") from exc
        if type(node) is int:
            if node < spec.get("minimum", node) or node > spec.get("maximum", node):
                raise ContractError(f"{location}: integer out of range")

    check(value, schema, "$")


def indexed(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        if row[key] in result:
            raise ContractError(f"Duplicate {key}: {row[key]}")
        result[row[key]] = row
    return result


def verify_evidence(
    records: list[dict[str, Any]], root: str | Path
) -> dict[str, dict[str, Any]]:
    base = Path(root).resolve(strict=True)
    evidence = indexed(records, "evidence_id")
    for record in records:
        relative = Path(record["path"])
        if relative.is_absolute():
            raise ContractError("Evidence paths must be relative")
        try:
            path = (base / relative).resolve(strict=True)
        except OSError as exc:
            raise ContractError(f"Evidence not found: {record['evidence_id']}") from exc
        if not path.is_relative_to(base) or not path.is_file():
            raise ContractError(
                "Evidence escaped its declared root or is not a regular file"
            )
        if file_hash(path) != record["sha256"]:
            raise ContractError(f"Evidence changed: {record['evidence_id']}")
    return evidence
