"""Maintain Clara's mechanical advisory evidence and claim lineage records."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator

__all__ = [
    "CLAIM_REGISTER_FILENAME",
    "EVIDENCE_MAP_FILENAME",
    "EVIDENCE_REGISTER_FILENAME",
    "LineageError",
    "add_claim_appearances",
    "bind_claim_appearances",
    "initialize_lineage",
    "record_claims",
    "record_evidence",
    "render_evidence_map",
    "validate_lineage",
    "validate_lineage_payloads",
]

LOGGER = logging.getLogger(__name__)

CLARA_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = CLARA_ROOT / "contracts"
EVIDENCE_SCHEMA_PATH = CONTRACTS_ROOT / "advisory_evidence_register.v1.schema.json"
CLAIM_SCHEMA_PATH = CONTRACTS_ROOT / "advisory_claim_register.v1.schema.json"

EVIDENCE_REGISTER_FILENAME = "advisory_evidence_register.json"
CLAIM_REGISTER_FILENAME = "advisory_claim_register.json"
EVIDENCE_MAP_FILENAME = "advisory_evidence_map.md"
MATERIAL_REGISTER_FILENAME = "material_registry.json"
SCHEMA_VERSION = "1.0"


class LineageError(ValueError):
    """Raised when a lineage mutation would make the records ambiguous."""


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            handle.flush()
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_errors(payload: Any, schema_path: Path, label: str) -> list[str]:
    try:
        schema = _read_json(schema_path)
        Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{label}: cannot load schema: {exc}"]
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    return [
        f"{label}{'.' if error.absolute_path else ': '}{'.'.join(str(part) for part in error.absolute_path)}: {error.message}"
        for error in errors
    ]


def _iso_timestamp_error(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if value == "" and allow_empty:
        return ""
    if not isinstance(value, str) or not value.strip():
        return f"{label}: timestamp is required"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return f"{label}: timestamp must be ISO 8601"
    if parsed.tzinfo is None:
        return f"{label}: timestamp must include a timezone"
    return ""


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _resolve_artifact(case_dir: Path, receipt: Mapping[str, Any]) -> Path:
    path = Path(str(receipt.get("path", ""))).expanduser()
    if receipt.get("path_reference") == "case_relative":
        return (case_dir / path).resolve()
    return path.resolve()


def _artifact_errors(
    case_dir: Path,
    receipt: Mapping[str, Any],
    label: str,
) -> list[str]:
    path = _resolve_artifact(case_dir, receipt)
    if not path.is_file():
        return [f"{label}: artifact does not exist: {path}"]
    errors: list[str] = []
    if path.stat().st_size != receipt.get("byte_count"):
        errors.append(f"{label}: byte_count does not match: {path}")
    if _sha256(path) != receipt.get("sha256"):
        errors.append(f"{label}: sha256 does not match: {path}")
    return errors


def _material_ids(case_dir: Path) -> set[str] | None:
    path = case_dir / MATERIAL_REGISTER_FILENAME
    if not path.is_file():
        return None
    payload = _read_json(path)
    materials = payload.get("materials") if isinstance(payload, dict) else None
    if not isinstance(materials, list):
        return set()
    return {
        str(item.get("id"))
        for item in materials
        if isinstance(item, dict) and item.get("id")
    }


def _cycle(graph: Mapping[str, Sequence[str]]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def visit(node: str) -> list[str]:
        if node in visited:
            return []
        if node in visiting:
            return [*path[path.index(node) :], node]
        visiting.add(node)
        path.append(node)
        for dependency in graph.get(node, []):
            found = visit(dependency)
            if found:
                return found
        path.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in graph:
        found = visit(node)
        if found:
            return found
    return []


def _duplicate_values(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def validate_lineage(
    case_dir: Path,
    *,
    verify_artifacts: bool = True,
) -> dict[str, Any]:
    """Validate declared lineage shape, references, graph, and artifact identity.

    These checks are deterministic because IDs, file bytes, hashes, and graph
    integrity are mechanically verifiable. They do not assess claim meaning,
    materiality, semantic support, or reasoning quality.
    """

    evidence_path = case_dir / EVIDENCE_REGISTER_FILENAME
    claim_path = case_dir / CLAIM_REGISTER_FILENAME
    errors: list[str] = []
    if not evidence_path.is_file():
        errors.append(f"missing {EVIDENCE_REGISTER_FILENAME}")
    if not claim_path.is_file():
        errors.append(f"missing {CLAIM_REGISTER_FILENAME}")
    if errors:
        return {
            "schema_version": SCHEMA_VERSION,
            "valid": False,
            "errors": errors,
            "counts": {"evidence": 0, "claims": 0, "active_claims": 0},
        }

    try:
        evidence_register = _read_json(evidence_path)
        claim_register = _read_json(claim_path)
    except json.JSONDecodeError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "valid": False,
            "errors": [f"invalid lineage JSON: {exc}"],
            "counts": {"evidence": 0, "claims": 0, "active_claims": 0},
        }

    return validate_lineage_payloads(
        case_dir,
        evidence_register,
        claim_register,
        verify_artifacts=verify_artifacts,
    )


def validate_lineage_payloads(
    case_dir: Path,
    evidence_register: Any,
    claim_register: Any,
    *,
    verify_artifacts: bool = True,
    known_material_ids_override: set[str] | None = None,
) -> dict[str, Any]:
    """Validate candidate register payloads before committing them to disk.

    Candidate validation is deterministic because it checks declared shape,
    references, timestamps, artifact bytes, and graph state only. It enables
    callers to fail before a multi-file mutation becomes visible.
    """

    errors: list[str] = []
    errors.extend(
        _schema_errors(
            evidence_register,
            EVIDENCE_SCHEMA_PATH,
            EVIDENCE_REGISTER_FILENAME,
        )
    )
    errors.extend(
        _schema_errors(
            claim_register,
            CLAIM_SCHEMA_PATH,
            CLAIM_REGISTER_FILENAME,
        )
    )
    evidence = (
        evidence_register.get("evidence", [])
        if isinstance(evidence_register, dict)
        else []
    )
    claims = (
        claim_register.get("claims", []) if isinstance(claim_register, dict) else []
    )
    if not isinstance(evidence, list):
        evidence = []
    if not isinstance(claims, list):
        claims = []

    evidence_ids = [
        str(item.get("id"))
        for item in evidence
        if isinstance(item, dict) and item.get("id")
    ]
    claim_ids = [
        str(item.get("id"))
        for item in claims
        if isinstance(item, dict) and item.get("id")
    ]
    for duplicate in sorted(_duplicate_values(evidence_ids)):
        errors.append(f"duplicate evidence id: {duplicate}")
    for duplicate in sorted(_duplicate_values(claim_ids)):
        errors.append(f"duplicate claim id: {duplicate}")

    known_evidence = set(evidence_ids)
    known_claims = set(claim_ids)
    evidence_by_id = {
        str(item.get("id")): item
        for item in evidence
        if isinstance(item, dict) and item.get("id")
    }
    claim_by_id = {
        str(item.get("id")): item
        for item in claims
        if isinstance(item, dict) and item.get("id")
    }
    known_materials = (
        known_material_ids_override
        if known_material_ids_override is not None
        else _material_ids(case_dir)
    )
    evidence_history_graph: dict[str, list[str]] = {}
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            continue
        label = f"evidence[{index}]"
        item_id = str(item.get("id", ""))
        timestamp_error = _iso_timestamp_error(
            item.get("recorded_at"), f"{label}.recorded_at"
        )
        if timestamp_error:
            errors.append(timestamp_error)
        verification = item.get("verification")
        if isinstance(verification, dict):
            status = verification.get("status")
            checked_error = _iso_timestamp_error(
                verification.get("checked_at"),
                f"{label}.verification.checked_at",
                allow_empty=status == "not_checked",
            )
            if checked_error:
                errors.append(checked_error)
            if status == "not_checked" and verification.get("checked_at"):
                errors.append(f"{label}: unchecked evidence cannot have checked_at")
            if status != "not_checked" and not verification.get("method"):
                errors.append(f"{label}: checked evidence requires verification.method")
        history_refs: list[str] = []
        for reference_field in ("rechecks_evidence_id", "supersedes_evidence_id"):
            reference = str(item.get(reference_field, ""))
            if reference and reference not in known_evidence:
                errors.append(
                    f"{label}.{reference_field}: unknown evidence id {reference}"
                )
            if reference and reference == item_id:
                errors.append(f"{label}.{reference_field}: cannot reference itself")
            if reference:
                history_refs.append(reference)
                predecessor = evidence_by_id.get(reference)
                current_time = _timestamp(item.get("recorded_at"))
                predecessor_time = (
                    _timestamp(predecessor.get("recorded_at"))
                    if isinstance(predecessor, dict)
                    else None
                )
                if (
                    current_time is not None
                    and predecessor_time is not None
                    and current_time <= predecessor_time
                ):
                    errors.append(
                        f"{label}.{reference_field}: successor must be recorded after {reference}"
                    )
        evidence_history_graph[item_id] = history_refs
        if item.get("rechecks_evidence_id") and item.get("supersedes_evidence_id"):
            errors.append(
                f"{label}: a receipt cannot both recheck and supersede another receipt"
            )
        if item.get("rechecks_evidence_id"):
            verification = item.get("verification")
            recheck_status = (
                verification.get("status") if isinstance(verification, dict) else None
            )
            if recheck_status not in {"rechecked_unchanged", "rechecked_changed"}:
                errors.append(
                    f"{label}: a recheck receipt requires rechecked_unchanged or rechecked_changed verification"
                )
            predecessor = evidence_by_id.get(str(item["rechecks_evidence_id"]))
            if isinstance(predecessor, dict) and predecessor.get(
                "evidence_type"
            ) != item.get("evidence_type"):
                errors.append(
                    f"{label}: a recheck receipt must keep the predecessor evidence_type"
                )
        source = item.get("source")
        if isinstance(source, dict):
            if known_materials is not None:
                for material_id in source.get("material_ids", []):
                    if material_id not in known_materials:
                        errors.append(f"{label}: unknown material id {material_id}")
            artifact_refs = source.get("artifact_refs", [])
            if verify_artifacts and isinstance(artifact_refs, list):
                for artifact_index, receipt in enumerate(artifact_refs):
                    if isinstance(receipt, dict):
                        errors.extend(
                            _artifact_errors(
                                case_dir,
                                receipt,
                                f"{label}.source.artifact_refs[{artifact_index}]",
                            )
                        )
            if item.get("capture_status") == "captured" and not (
                source.get("material_ids")
                or source.get("url")
                or source.get("artifact_refs")
            ):
                errors.append(f"{label}: captured evidence requires source identity")
            if item.get("evidence_type") == "calculation_run":
                artifact_paths = {
                    str(receipt.get("path"))
                    for receipt in artifact_refs
                    if isinstance(receipt, dict) and receipt.get("path")
                }
                calculation = item.get("calculation")
                if isinstance(calculation, dict):
                    declared_paths = {
                        str(path)
                        for field in (
                            "input_artifact_paths",
                            "output_artifact_paths",
                            "verification_artifact_paths",
                        )
                        for path in calculation.get(field, [])
                    }
                    missing_paths = sorted(declared_paths - artifact_paths)
                    if missing_paths:
                        errors.append(
                            f"{label}: calculation paths missing from source.artifact_refs: "
                            + ", ".join(missing_paths)
                        )

    if not any("unknown evidence id" in error for error in errors):
        found_cycle = _cycle(evidence_history_graph)
        if found_cycle:
            errors.append("evidence history cycle: " + " -> ".join(found_cycle))

    dependency_graph: dict[str, list[str]] = {}
    supersession_graph: dict[str, list[str]] = {}
    successor_by_predecessor: dict[str, str] = {}
    for index, item in enumerate(claims):
        if not isinstance(item, dict):
            continue
        label = f"claims[{index}]"
        item_id = str(item.get("id", ""))
        timestamp_error = _iso_timestamp_error(
            item.get("recorded_at"), f"{label}.recorded_at"
        )
        if timestamp_error:
            errors.append(timestamp_error)
        evidence_links = item.get("evidence_links", [])
        for link in evidence_links:
            if isinstance(link, dict) and link.get("evidence_id") not in known_evidence:
                errors.append(f"{label}: unknown evidence id {link.get('evidence_id')}")
        dependency = item.get("dependency")
        if isinstance(dependency, dict):
            dependency_ids = dependency.get("claim_ids", [])
            if not isinstance(dependency_ids, list):
                dependency_ids = []
            dependency_graph[item_id] = [str(value) for value in dependency_ids]
            mode = dependency.get("mode")
            if mode == "none" and dependency_ids:
                errors.append(f"{label}: dependency mode none requires no claim_ids")
            if mode in {"all_of", "any_of"} and not dependency_ids:
                errors.append(f"{label}: dependency mode {mode} requires claim_ids")
            if mode == "none" and not evidence_links:
                errors.append(
                    f"{label}: a direct claim requires at least one evidence link"
                )
            if (
                mode in {"all_of", "any_of"}
                and dependency.get("derivation_type") == "direct"
            ):
                errors.append(
                    f"{label}: a dependent claim cannot use direct derivation"
                )
            for dependency_id in dependency_ids:
                if dependency_id == item_id:
                    errors.append(f"{label}: claim cannot depend on itself")
                elif dependency_id not in known_claims:
                    errors.append(
                        f"{label}: unknown dependency claim id {dependency_id}"
                    )
            calculation_evidence_id = str(dependency.get("calculation_evidence_id", ""))
            if (
                calculation_evidence_id
                and calculation_evidence_id not in known_evidence
            ):
                errors.append(
                    f"{label}: unknown calculation evidence id {calculation_evidence_id}"
                )
            claim_type = item.get("claim_type")
            derivation_type = dependency.get("derivation_type")
            if claim_type == "calculation" or derivation_type == "calculation":
                if not calculation_evidence_id:
                    errors.append(
                        f"{label}: calculation claim requires calculation_evidence_id"
                    )
                calculation_receipt = evidence_by_id.get(calculation_evidence_id)
                if (
                    isinstance(calculation_receipt, dict)
                    and calculation_receipt.get("evidence_type") != "calculation_run"
                ):
                    errors.append(
                        f"{label}: calculation_evidence_id must reference a calculation_run receipt"
                    )
                linked_ids = {
                    str(link.get("evidence_id"))
                    for link in evidence_links
                    if isinstance(link, dict)
                }
                if (
                    calculation_evidence_id
                    and calculation_evidence_id not in linked_ids
                ):
                    errors.append(
                        f"{label}: calculation_evidence_id must also appear in evidence_links"
                    )
            if claim_type == "quotation" or derivation_type == "quotation":
                transcript_links = [
                    link
                    for link in evidence_links
                    if isinstance(link, dict)
                    and isinstance(
                        evidence_by_id.get(str(link.get("evidence_id"))), dict
                    )
                    and evidence_by_id[str(link.get("evidence_id"))].get(
                        "evidence_type"
                    )
                    == "interview_transcript"
                ]
                if not transcript_links:
                    errors.append(
                        f"{label}: quotation claim requires an interview_transcript evidence link"
                    )
        supersedes = str(item.get("supersedes_claim_id", ""))
        if supersedes and supersedes not in known_claims:
            errors.append(f"{label}: unknown superseded claim id {supersedes}")
        if supersedes and supersedes == item_id:
            errors.append(f"{label}: claim cannot supersede itself")
        supersession_graph[item_id] = [supersedes] if supersedes else []
        if supersedes:
            previous_successor = successor_by_predecessor.get(supersedes)
            if previous_successor and previous_successor != item_id:
                errors.append(
                    f"{label}: claim {supersedes} already has successor {previous_successor}"
                )
            successor_by_predecessor[supersedes] = item_id
            predecessor = claim_by_id.get(supersedes)
            if (
                isinstance(predecessor, dict)
                and predecessor.get("state") != "superseded"
            ):
                errors.append(
                    f"{label}: superseded predecessor {supersedes} must have state superseded"
                )
            current_time = _timestamp(item.get("recorded_at"))
            predecessor_time = (
                _timestamp(predecessor.get("recorded_at"))
                if isinstance(predecessor, dict)
                else None
            )
            if (
                current_time is not None
                and predecessor_time is not None
                and current_time <= predecessor_time
            ):
                errors.append(f"{label}: successor must be recorded after {supersedes}")
        for appearance_index, appearance in enumerate(item.get("appearances", [])):
            if not isinstance(appearance, dict):
                continue
            timestamp_error = _iso_timestamp_error(
                appearance.get("recorded_at"),
                f"{label}.appearances[{appearance_index}].recorded_at",
            )
            if timestamp_error:
                errors.append(timestamp_error)
            if verify_artifacts:
                receipt = {
                    "path": appearance.get("artifact", ""),
                    "path_reference": appearance.get("path_reference", ""),
                    "sha256": appearance.get("artifact_sha256", ""),
                    "byte_count": appearance.get("artifact_byte_count", -1),
                }
                errors.extend(
                    _artifact_errors(
                        case_dir,
                        receipt,
                        f"{label}.appearances[{appearance_index}]",
                    )
                )

    if not any("unknown dependency claim id" in error for error in errors):
        found_cycle = _cycle(dependency_graph)
        if found_cycle:
            errors.append("claim dependency cycle: " + " -> ".join(found_cycle))
    if not any("unknown superseded claim id" in error for error in errors):
        found_cycle = _cycle(supersession_graph)
        if found_cycle:
            errors.append("claim supersession cycle: " + " -> ".join(found_cycle))
    for claim_id, claim in claim_by_id.items():
        if (
            claim.get("state") == "superseded"
            and claim_id not in successor_by_predecessor
        ):
            errors.append(
                f"claim {claim_id}: superseded state requires a declared successor"
            )

    active_claims = sum(
        1 for item in claims if isinstance(item, dict) and item.get("state") == "active"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": not errors,
        "errors": errors,
        "counts": {
            "evidence": len(evidence),
            "claims": len(claims),
            "active_claims": active_claims,
        },
    }


def initialize_lineage(case_dir: Path, *, overwrite: bool = False) -> dict[str, Path]:
    """Create empty lineage registers without changing existing records."""

    case_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = case_dir / EVIDENCE_REGISTER_FILENAME
    claim_path = case_dir / CLAIM_REGISTER_FILENAME
    if overwrite and (evidence_path.exists() or claim_path.exists()):
        existing_evidence = (
            _read_json(evidence_path).get("evidence", [])
            if evidence_path.exists()
            else []
        )
        existing_claims = (
            _read_json(claim_path).get("claims", []) if claim_path.exists() else []
        )
        if existing_evidence or existing_claims:
            raise LineageError(
                "refusing to overwrite non-empty append-only advisory lineage"
            )
    if overwrite or not evidence_path.exists():
        _write_json(evidence_path, {"schema_version": SCHEMA_VERSION, "evidence": []})
    if overwrite or not claim_path.exists():
        _write_json(claim_path, {"schema_version": SCHEMA_VERSION, "claims": []})
    map_path = render_evidence_map(case_dir)
    return {
        "evidence_register": evidence_path,
        "claim_register": claim_path,
        "evidence_map": map_path,
    }


def _records(payload: Any, key: str) -> list[dict[str, Any]]:
    values = payload.get(key) if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise LineageError(f"input must be a list or an object with {key}")
    if not all(isinstance(item, dict) for item in values):
        raise LineageError(f"{key} must contain objects")
    return [dict(item) for item in values]


def _append_immutable(
    existing: list[dict[str, Any]],
    incoming: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> int:
    by_id = {str(item.get("id")): item for item in existing}
    added = 0
    for raw_item in incoming:
        item = dict(raw_item)
        item_id = str(item.get("id", ""))
        current = by_id.get(item_id)
        if current is not None:
            if current != item:
                raise LineageError(
                    f"{label} id {item_id!r} already exists with different content"
                )
            continue
        existing.append(item)
        by_id[item_id] = item
        added += 1
    return added


def record_evidence(case_dir: Path, records: Sequence[Mapping[str, Any]]) -> int:
    """Append immutable model-authored evidence receipts and validate the result."""

    path = case_dir / EVIDENCE_REGISTER_FILENAME
    if not path.exists():
        initialize_lineage(case_dir)
    payload = _read_json(path)
    values = payload.get("evidence")
    if not isinstance(values, list):
        raise LineageError("evidence register is malformed")
    candidate = json.loads(json.dumps(payload))
    added = _append_immutable(candidate["evidence"], records, label="evidence")
    claim_payload = _read_json(case_dir / CLAIM_REGISTER_FILENAME)
    audit = validate_lineage_payloads(case_dir, candidate, claim_payload)
    if not audit["valid"]:
        raise LineageError("; ".join(audit["errors"]))
    _write_json(path, candidate)
    render_evidence_map(case_dir)
    return added


def record_claims(case_dir: Path, records: Sequence[Mapping[str, Any]]) -> int:
    """Append immutable model-authored claims and supersede declared predecessors."""

    path = case_dir / CLAIM_REGISTER_FILENAME
    if not path.exists():
        initialize_lineage(case_dir)
    payload = _read_json(path)
    values = payload.get("claims")
    if not isinstance(values, list):
        raise LineageError("claim register is malformed")
    candidate = json.loads(json.dumps(payload))
    added = _append_immutable(candidate["claims"], records, label="claim")
    by_id = {str(item.get("id")): item for item in candidate["claims"]}
    for record in records:
        supersedes = str(record.get("supersedes_claim_id", ""))
        if supersedes and supersedes in by_id:
            by_id[supersedes]["state"] = "superseded"
    evidence_payload = _read_json(case_dir / EVIDENCE_REGISTER_FILENAME)
    audit = validate_lineage_payloads(case_dir, evidence_payload, candidate)
    if not audit["valid"]:
        raise LineageError("; ".join(audit["errors"]))
    _write_json(path, candidate)
    render_evidence_map(case_dir)
    return added


def add_claim_appearances(
    case_dir: Path,
    appearances: Sequence[Mapping[str, Any]],
) -> int:
    """Attach exact output locations to existing claims without changing meaning."""

    path = case_dir / CLAIM_REGISTER_FILENAME
    payload = _read_json(path)
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise LineageError("claim register is malformed")
    candidate = json.loads(json.dumps(payload))
    candidate_claims = candidate["claims"]
    by_id = {
        str(item.get("id")): item for item in candidate_claims if isinstance(item, dict)
    }
    added = 0
    for record in appearances:
        claim_id = str(record.get("claim_id", ""))
        appearance = record.get("appearance")
        claim = by_id.get(claim_id)
        if claim is None:
            raise LineageError(f"unknown claim id: {claim_id}")
        if not isinstance(appearance, dict):
            raise LineageError(f"appearance for {claim_id} must be an object")
        current = claim.get("appearances")
        if not isinstance(current, list):
            raise LineageError(f"appearances for {claim_id} must be an array")
        if appearance not in current:
            current.append(dict(appearance))
            added += 1
    evidence_payload = _read_json(case_dir / EVIDENCE_REGISTER_FILENAME)
    audit = validate_lineage_payloads(case_dir, evidence_payload, candidate)
    if not audit["valid"]:
        raise LineageError("; ".join(audit["errors"]))
    _write_json(path, candidate)
    render_evidence_map(case_dir)
    return added


def bind_claim_appearances(
    case_dir: Path,
    artifact: Path,
    locations: Sequence[Mapping[str, Any]],
    *,
    recorded_at: str | None = None,
) -> int:
    """Hash one completed output and bind model-declared claim locations to it."""

    resolved = artifact.expanduser().resolve()
    if not resolved.is_file():
        raise LineageError(f"claim appearance artifact does not exist: {resolved}")
    try:
        artifact_reference = resolved.relative_to(case_dir.resolve()).as_posix()
        path_reference = "case_relative"
    except ValueError:
        artifact_reference = str(resolved)
        path_reference = "absolute"
    timestamp = (
        recorded_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    records: list[dict[str, Any]] = []
    for index, location in enumerate(locations):
        claim_id = str(location.get("claim_id", "")).strip()
        locator = str(location.get("locator", "")).strip()
        if not claim_id or not locator:
            raise LineageError(f"claim location {index} requires claim_id and locator")
        appearance = {
            "artifact": artifact_reference,
            "path_reference": path_reference,
            "artifact_sha256": _sha256(resolved),
            "artifact_byte_count": resolved.stat().st_size,
            "locator": locator,
            "recorded_at": timestamp,
        }
        format_claim_id = str(location.get("format_claim_id", "")).strip()
        if format_claim_id:
            appearance["format_claim_id"] = format_claim_id
        records.append({"claim_id": claim_id, "appearance": appearance})
    return add_claim_appearances(case_dir, records)


def render_evidence_map(case_dir: Path) -> Path:
    """Render a readable control view without making semantic judgments."""

    evidence_path = case_dir / EVIDENCE_REGISTER_FILENAME
    claim_path = case_dir / CLAIM_REGISTER_FILENAME
    evidence_register = (
        _read_json(evidence_path) if evidence_path.exists() else {"evidence": []}
    )
    claim_register = _read_json(claim_path) if claim_path.exists() else {"claims": []}
    evidence = evidence_register.get("evidence", [])
    claims = claim_register.get("claims", [])
    if not isinstance(evidence, list):
        evidence = []
    if not isinstance(claims, list):
        claims = []

    lines = [
        "# Advisory evidence map",
        "",
        "This is a readable view of the structured evidence and claim registers. It records declared provenance; it does not prove that a claim is correct.",
        "",
        "## Evidence",
        "",
    ]
    if not evidence:
        lines.append("- No evidence receipts recorded.")
    for item in evidence:
        if not isinstance(item, dict):
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        verification = (
            item.get("verification")
            if isinstance(item.get("verification"), dict)
            else {}
        )
        lines.extend(
            [
                f"### {item.get('id', 'evidence')} — {item.get('evidence_type', 'other')}",
                "",
                f"- Observation: {item.get('observation', '')}",
                f"- Source: {source.get('locator', '')}",
                f"- Capture: {item.get('capture_status', '')}",
                f"- Verification: {verification.get('status', '')}",
                f"- Scope: {item.get('scope', '')}",
                f"- Limitations: {'; '.join(item.get('limitations', [])) or 'none recorded'}",
                "",
            ]
        )
    lines.extend(["## Claims", ""])
    if not claims:
        lines.append("- No claims recorded.")
    for item in claims:
        if not isinstance(item, dict):
            continue
        dependency = (
            item.get("dependency") if isinstance(item.get("dependency"), dict) else {}
        )
        lines.extend(
            [
                f"### {item.get('id', 'claim')} — {item.get('claim_type', 'assertion')}",
                "",
                f"- Statement: {item.get('statement', '')}",
                f"- Decision use: {item.get('decision_use', '')}",
                f"- Depends on ({dependency.get('mode', 'none')}): {', '.join(dependency.get('claim_ids', [])) or 'none'}",
                f"- Derivation: {dependency.get('derivation_type', '')} — {dependency.get('explanation', '')}",
                f"- Decision implication: {item.get('decision_implication', '') or 'not recorded'}",
                f"- Evidence that would change the position: {item.get('missing_evidence_that_would_change_position', '') or 'not recorded'}",
                f"- Uncertainty: {'; '.join(item.get('uncertainty', [])) or 'none recorded'}",
                f"- State: {item.get('state', '')}",
                "",
            ]
        )
        links = item.get("evidence_links", [])
        if isinstance(links, list) and links:
            lines.extend(["#### Evidence relationships", ""])
            for link in links:
                if not isinstance(link, dict):
                    continue
                lines.extend(
                    [
                        f"- {link.get('evidence_id', '')} — {link.get('relationship', '')}",
                        f"  - Analysis: {link.get('analysis', '')}",
                        f"  - Proves: {link.get('proves', '')}",
                        f"  - Does not prove: {link.get('does_not_prove', '')}",
                        f"  - Directness: {link.get('directness', 'not recorded')}",
                        f"  - Reliability: {link.get('reliability', 'not recorded')}",
                        f"  - Corroboration: {link.get('corroboration', 'not recorded')}",
                        f"  - Bias or limitation: {link.get('bias_or_limitation', '') or 'not recorded'}",
                    ]
                )
        else:
            lines.extend(["#### Evidence relationships", "", "- None recorded."])
        appearances = item.get("appearances", [])
        lines.extend(["", "#### Output appearances", ""])
        if not isinstance(appearances, list) or not appearances:
            lines.append("- None recorded.")
        else:
            for appearance in appearances:
                if not isinstance(appearance, dict):
                    continue
                lines.append(
                    f"- {appearance.get('artifact', '')} — {appearance.get('locator', '')} "
                    f"(SHA-256 {appearance.get('artifact_sha256', '')})"
                )
        lines.append("")
    output = case_dir / EVIDENCE_MAP_FILENAME
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output


def _command_payload(path: Path, key: str) -> list[dict[str, Any]]:
    return _records(_read_json(path), key)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    initialize = subparsers.add_parser("init", help="Initialize lineage files.")
    initialize.add_argument("case_dir", type=Path)
    initialize.add_argument("--overwrite", action="store_true")
    add_evidence = subparsers.add_parser(
        "add-evidence", help="Append evidence receipts."
    )
    add_evidence.add_argument("case_dir", type=Path)
    add_evidence.add_argument("records_json", type=Path)
    add_claims = subparsers.add_parser("add-claims", help="Append claim records.")
    add_claims.add_argument("case_dir", type=Path)
    add_claims.add_argument("records_json", type=Path)
    link = subparsers.add_parser(
        "link-appearances", help="Link claims to output locations."
    )
    link.add_argument("case_dir", type=Path)
    link.add_argument("records_json", type=Path)
    bind = subparsers.add_parser(
        "bind-output",
        help="Hash one completed output and bind declared claim locations.",
    )
    bind.add_argument("case_dir", type=Path)
    bind.add_argument("artifact", type=Path)
    bind.add_argument("locations_json", type=Path)
    validate = subparsers.add_parser("validate", help="Validate lineage records.")
    validate.add_argument("case_dir", type=Path)
    validate.add_argument("--audit", type=Path)
    validate.add_argument("--skip-artifact-hashes", action="store_true")
    render = subparsers.add_parser("render", help="Render the readable evidence map.")
    render.add_argument("case_dir", type=Path)
    return parser


def main() -> int:
    """Run the mechanical lineage helper."""

    parser = _parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.command == "init":
            paths = initialize_lineage(args.case_dir, overwrite=args.overwrite)
            LOGGER.info("Lineage ready: %s", paths["claim_register"])
            return 0
        if args.command == "add-evidence":
            added = record_evidence(
                args.case_dir,
                _command_payload(args.records_json, "evidence"),
            )
            LOGGER.info("Evidence receipts added: %s", added)
            return 0
        if args.command == "add-claims":
            added = record_claims(
                args.case_dir,
                _command_payload(args.records_json, "claims"),
            )
            LOGGER.info("Claims added: %s", added)
            return 0
        if args.command == "link-appearances":
            added = add_claim_appearances(
                args.case_dir,
                _command_payload(args.records_json, "appearances"),
            )
            LOGGER.info("Claim appearances added: %s", added)
            return 0
        if args.command == "bind-output":
            added = bind_claim_appearances(
                args.case_dir,
                args.artifact,
                _command_payload(args.locations_json, "appearances"),
            )
            LOGGER.info("Claim appearances bound: %s", added)
            return 0
        if args.command == "render":
            path = render_evidence_map(args.case_dir)
            LOGGER.info("Evidence map rendered: %s", path)
            return 0
        audit = validate_lineage(
            args.case_dir,
            verify_artifacts=not args.skip_artifact_hashes,
        )
        if args.audit:
            _write_json(args.audit, audit)
        if not audit["valid"]:
            for error in audit["errors"]:
                LOGGER.error("validation_error: %s", error)
            return 1
        LOGGER.info("validation_errors=[]")
        return 0
    except (LineageError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
