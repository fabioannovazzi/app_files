"""Replayable assurance envelopes for Vera workflow runs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .contracts import (
    validate_gate_register,
    validate_numeric_evidence_ledger,
    validate_source_qualification,
)
from .decisions import validate_reviewed_decision_receipt
from .relationships import validate_allocation_ledger
from .serialization import (
    canonical_json_sha256,
    validate_artifact_receipt,
)

__all__ = [
    "AssuranceEnvelopeError",
    "build_assurance_envelope",
    "validate_assurance_envelope",
]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SEMANTIC_DECISION_TYPES = {
    "accounting_conclusion",
    "audit_conclusion",
    "check_entries_review_actions",
    "evidence_sufficiency_review",
    "journal_bank_review_application",
    "professional_review",
    "semantic_review",
}


class AssuranceEnvelopeError(ValueError):
    """Raised when an assurance envelope cannot be replayed exactly."""


def _identifier(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or _IDENTIFIER_RE.fullmatch(value) is None
    ):
        raise AssuranceEnvelopeError(f"{label} must be a canonical identifier")
    return value


def _sequence(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AssuranceEnvelopeError(f"{label} must be a list")
    return list(value)


def _unique_by(
    items: Sequence[Mapping[str, Any]],
    *,
    field: str,
    label: str,
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(items):
        item_id = _identifier(item.get(field), label=f"{label}[{index}].{field}")
        if item_id in indexed:
            raise AssuranceEnvelopeError(f"{label} contains duplicate {field}")
        indexed[item_id] = item
    return indexed


def _has_artifact_role(
    evidence_refs: Sequence[str],
    artifact_by_id: Mapping[str, Mapping[str, Any]],
    *,
    roles: set[str],
) -> bool:
    """Return whether gate evidence includes an artifact with an allowed role."""

    return any(
        reference in artifact_by_id and artifact_by_id[reference]["role"] in roles
        for reference in evidence_refs
    )


def validate_assurance_envelope(
    value: object,
    *,
    artifact_roots: Path | Mapping[str, Path],
) -> dict[str, Any]:
    """Validate contract closure and replay every local artifact receipt."""

    if not isinstance(value, Mapping):
        raise AssuranceEnvelopeError("assurance envelope must be an object")
    required = {
        "schema_version",
        "run_id",
        "workflow_id",
        "workflow_version",
        "artifact_receipts",
        "implementation_artifact_refs",
        "reviewed_decisions",
        "source_qualifications",
        "allocation_ledgers",
        "numeric_evidence_ledgers",
        "gate_register",
        "limitations",
        "content_sha256",
    }
    missing = required - set(value)
    unexpected = set(value) - required
    if missing or unexpected:
        raise AssuranceEnvelopeError(
            f"assurance envelope fields invalid; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    if value["schema_version"] != "vera.assurance_envelope.v1":
        raise AssuranceEnvelopeError("unsupported assurance-envelope schema")

    raw_artifacts = _sequence(value["artifact_receipts"], label="artifact_receipts")
    artifacts = []
    for index, receipt in enumerate(raw_artifacts):
        if not isinstance(receipt, Mapping):
            raise AssuranceEnvelopeError(
                f"artifact_receipts[{index}] must be an object"
            )
        try:
            artifacts.append(validate_artifact_receipt(artifact_roots, receipt))
        except ValueError as exc:
            raise AssuranceEnvelopeError(str(exc)) from exc
    artifact_by_id = _unique_by(
        artifacts, field="artifact_id", label="artifact_receipts"
    )
    artifact_paths: set[tuple[str, str]] = set()
    for artifact in artifacts:
        artifact_path = (str(artifact["root_id"]), str(artifact["path"]))
        if artifact_path in artifact_paths:
            raise AssuranceEnvelopeError(
                "artifact_receipts cannot assign multiple identities to one path"
            )
        artifact_paths.add(artifact_path)
    implementation_refs = [
        _identifier(ref, label=f"implementation_artifact_refs[{index}]")
        for index, ref in enumerate(
            _sequence(
                value["implementation_artifact_refs"],
                label="implementation_artifact_refs",
            )
        )
    ]
    if not implementation_refs or len(implementation_refs) != len(
        set(implementation_refs)
    ):
        raise AssuranceEnvelopeError(
            "implementation_artifact_refs must be non-empty and unique"
        )
    if not set(implementation_refs) <= set(artifact_by_id):
        raise AssuranceEnvelopeError(
            "implementation_artifact_refs contain an unknown artifact"
        )
    if any(
        artifact_by_id[reference]["role"] != "implementation"
        for reference in implementation_refs
    ):
        raise AssuranceEnvelopeError(
            "implementation_artifact_refs must reference implementation artifacts"
        )

    decisions = []
    for index, raw_decision in enumerate(
        _sequence(value["reviewed_decisions"], label="reviewed_decisions")
    ):
        try:
            decisions.append(validate_reviewed_decision_receipt(raw_decision))
        except ValueError as exc:
            raise AssuranceEnvelopeError(f"reviewed_decisions[{index}]: {exc}") from exc
    decision_by_id = _unique_by(
        decisions, field="decision_id", label="reviewed_decisions"
    )
    for decision in decisions:
        if not set(decision["source_artifact_refs"]) <= set(artifact_by_id):
            raise AssuranceEnvelopeError(
                "reviewed decision references an unknown source artifact"
            )
        if any(
            artifact_by_id[reference]["role"] != "source"
            for reference in decision["source_artifact_refs"]
        ):
            raise AssuranceEnvelopeError(
                "reviewed decision source refs must reference source artifacts"
            )

    qualifications = []
    for index, raw_qualification in enumerate(
        _sequence(value["source_qualifications"], label="source_qualifications")
    ):
        try:
            qualifications.append(validate_source_qualification(raw_qualification))
        except ValueError as exc:
            raise AssuranceEnvelopeError(
                f"source_qualifications[{index}]: {exc}"
            ) from exc
    qualification_by_id = _unique_by(
        qualifications,
        field="qualification_id",
        label="source_qualifications",
    )
    for qualification in qualifications:
        if not set(qualification["source_artifact_refs"]) <= set(artifact_by_id):
            raise AssuranceEnvelopeError(
                "source qualification references an unknown artifact"
            )
        if any(
            artifact_by_id[reference]["role"] != "source"
            for reference in qualification["source_artifact_refs"]
        ):
            raise AssuranceEnvelopeError(
                "source qualification refs must reference source artifacts"
            )
        mapping_ref = qualification["reviewed_mapping_ref"]
        if mapping_ref is not None:
            if mapping_ref not in decision_by_id:
                raise AssuranceEnvelopeError(
                    "source qualification references an unknown decision"
                )
            decision = decision_by_id[mapping_ref]
            try:
                validate_reviewed_decision_receipt(
                    decision,
                    expected_source_artifact_refs=qualification["source_artifact_refs"],
                    expected_adapter_id=qualification["adapter_id"],
                    expected_adapter_version=qualification["adapter_version"],
                    require_reviewed=True,
                )
            except ValueError as exc:
                raise AssuranceEnvelopeError(
                    "source qualification uses a stale mapping decision"
                ) from exc

    allocation_ledgers = []
    for index, raw_ledger in enumerate(
        _sequence(value["allocation_ledgers"], label="allocation_ledgers")
    ):
        try:
            allocation_ledgers.append(validate_allocation_ledger(raw_ledger))
        except ValueError as exc:
            raise AssuranceEnvelopeError(f"allocation_ledgers[{index}]: {exc}") from exc
    allocation_by_id = _unique_by(
        allocation_ledgers, field="ledger_id", label="allocation_ledgers"
    )

    numeric_ledgers = []
    for index, raw_ledger in enumerate(
        _sequence(
            value["numeric_evidence_ledgers"],
            label="numeric_evidence_ledgers",
        )
    ):
        try:
            numeric_ledgers.append(validate_numeric_evidence_ledger(raw_ledger))
        except ValueError as exc:
            raise AssuranceEnvelopeError(
                f"numeric_evidence_ledgers[{index}]: {exc}"
            ) from exc
    numeric_by_id = _unique_by(
        numeric_ledgers, field="ledger_id", label="numeric_evidence_ledgers"
    )
    for ledger in numeric_ledgers:
        for entry in ledger["entries"]:
            artifact_refs = {
                entry["source"]["artifact_ref"],
                entry["prepared"]["artifact_ref"],
                *(output["artifact_ref"] for output in entry["outputs"]),
            }
            if not artifact_refs <= set(artifact_by_id):
                raise AssuranceEnvelopeError(
                    "numeric evidence references an unknown artifact"
                )
            if artifact_by_id[entry["source"]["artifact_ref"]]["role"] != "source":
                raise AssuranceEnvelopeError(
                    "numeric evidence source must reference a source artifact"
                )
            if artifact_by_id[entry["prepared"]["artifact_ref"]]["role"] != "prepared":
                raise AssuranceEnvelopeError(
                    "numeric evidence prepared value must reference a prepared artifact"
                )
            if any(
                artifact_by_id[output["artifact_ref"]]["role"]
                not in {"output", "report", "workpaper", "rendered"}
                for output in entry["outputs"]
            ):
                raise AssuranceEnvelopeError(
                    "numeric evidence output must reference an output artifact"
                )
            decision_ref = entry["decision_ref"]
            if decision_ref is not None and decision_ref not in decision_by_id:
                raise AssuranceEnvelopeError(
                    "numeric evidence references an unknown decision"
                )

    try:
        gate_register = validate_gate_register(value["gate_register"])
    except ValueError as exc:
        raise AssuranceEnvelopeError(f"gate_register: {exc}") from exc
    known_refs = (
        set(artifact_by_id)
        | set(decision_by_id)
        | set(qualification_by_id)
        | set(allocation_by_id)
        | set(numeric_by_id)
    )
    allocation_evidence_refs = (
        set(artifact_by_id)
        | set(decision_by_id)
        | set(qualification_by_id)
        | set(numeric_by_id)
    )
    for ledger in allocation_ledgers:
        for allocation in ledger["allocations"]:
            unknown = set(allocation["evidence_refs"]) - allocation_evidence_refs
            if unknown:
                raise AssuranceEnvelopeError(
                    "allocation references unknown evidence: " f"{sorted(unknown)}"
                )
    for gate_name, gate in gate_register["gates"].items():
        unknown = set(gate["evidence_refs"]) - known_refs
        if unknown:
            raise AssuranceEnvelopeError(
                f"gate {gate_name} references unknown evidence: {sorted(unknown)}"
            )
    source_gate = gate_register["gates"]["source"]
    if source_gate["status"] == "passed":
        if not qualifications or any(
            qualification["status"] != "qualified" for qualification in qualifications
        ):
            raise AssuranceEnvelopeError(
                "passed source gate requires every source qualification to be qualified"
            )
        missing_qualification_refs = set(qualification_by_id) - set(
            source_gate["evidence_refs"]
        )
        if missing_qualification_refs:
            raise AssuranceEnvelopeError(
                "passed source gate omits source qualifications: "
                f"{sorted(missing_qualification_refs)}"
            )
    semantic_gate = gate_register["gates"]["semantic_review"]
    if semantic_gate["status"] == "passed":
        reviewed_refs = {
            reference
            for reference in semantic_gate["evidence_refs"]
            if reference in decision_by_id
            and decision_by_id[reference]["status"] == "reviewed"
            and decision_by_id[reference]["decision_type"] in _SEMANTIC_DECISION_TYPES
        }
        if not reviewed_refs:
            raise AssuranceEnvelopeError(
                "passed semantic-review gate requires a reviewed professional "
                "or semantic decision"
            )
    preparation_gate = gate_register["gates"]["preparation"]
    if preparation_gate["status"] == "passed" and not _has_artifact_role(
        preparation_gate["evidence_refs"],
        artifact_by_id,
        roles={"prepared", "output", "workpaper"},
    ):
        raise AssuranceEnvelopeError(
            "passed preparation gate requires prepared or work-product evidence"
        )
    reconciliation_gate = gate_register["gates"]["reconciliation"]
    if reconciliation_gate["status"] == "passed":
        reconciliation_refs = set(reconciliation_gate["evidence_refs"])
        if not (
            reconciliation_refs & (set(allocation_by_id) | set(numeric_by_id))
            or _has_artifact_role(
                reconciliation_gate["evidence_refs"],
                artifact_by_id,
                roles={"output", "workpaper"},
            )
        ):
            raise AssuranceEnvelopeError(
                "passed reconciliation gate requires a relationship ledger, "
                "numeric evidence ledger, or reconciliation work product"
            )
    reporting_gate = gate_register["gates"]["reporting"]
    if reporting_gate["status"] == "passed":
        reporting_refs = set(reporting_gate["evidence_refs"])
        if not (
            reporting_refs & set(numeric_by_id)
            or _has_artifact_role(
                reporting_gate["evidence_refs"],
                artifact_by_id,
                roles={"output", "report", "rendered", "workpaper"},
            )
        ):
            raise AssuranceEnvelopeError(
                "passed reporting gate requires report or numeric-ledger evidence"
            )
    publication_gate = gate_register["gates"]["publication"]
    if publication_gate["status"] == "passed":
        reviewed_publication_refs = {
            reference
            for reference in publication_gate["evidence_refs"]
            if reference in decision_by_id
            and decision_by_id[reference]["status"] == "reviewed"
            and decision_by_id[reference]["decision_type"] == "publication_authority"
        }
        if not (
            reviewed_publication_refs
            or _has_artifact_role(
                publication_gate["evidence_refs"],
                artifact_by_id,
                roles={"publication", "published"},
            )
        ):
            raise AssuranceEnvelopeError(
                "passed publication gate requires publication evidence or "
                "reviewed publication authority"
            )

    raw_limitations = _sequence(value["limitations"], label="limitations")
    limitations = []
    for index, item in enumerate(raw_limitations):
        if not isinstance(item, str) or not item or item != item.strip():
            raise AssuranceEnvelopeError(
                f"limitations[{index}] must be non-empty trimmed text"
            )
        limitations.append(item)
    content = {
        "schema_version": "vera.assurance_envelope.v1",
        "run_id": _identifier(value["run_id"], label="run_id"),
        "workflow_id": _identifier(value["workflow_id"], label="workflow_id"),
        "workflow_version": _identifier(
            value["workflow_version"], label="workflow_version"
        ),
        "artifact_receipts": artifacts,
        "implementation_artifact_refs": implementation_refs,
        "reviewed_decisions": decisions,
        "source_qualifications": qualifications,
        "allocation_ledgers": allocation_ledgers,
        "numeric_evidence_ledgers": numeric_ledgers,
        "gate_register": gate_register,
        "limitations": limitations,
    }
    expected_digest = canonical_json_sha256(content)
    if value["content_sha256"] != expected_digest:
        raise AssuranceEnvelopeError("assurance envelope content digest is stale")
    return {**content, "content_sha256": expected_digest}


def build_assurance_envelope(
    *,
    run_id: str,
    workflow_id: str,
    workflow_version: str,
    artifact_receipts: Sequence[Mapping[str, Any]],
    implementation_artifact_refs: Sequence[str],
    reviewed_decisions: Sequence[Mapping[str, Any]],
    source_qualifications: Sequence[Mapping[str, Any]],
    allocation_ledgers: Sequence[Mapping[str, Any]],
    numeric_evidence_ledgers: Sequence[Mapping[str, Any]],
    gate_register: Mapping[str, Any],
    limitations: Sequence[str],
    artifact_roots: Path | Mapping[str, Path],
) -> dict[str, Any]:
    """Build, seal, and immediately replay an assurance envelope."""

    content = {
        "schema_version": "vera.assurance_envelope.v1",
        "run_id": run_id,
        "workflow_id": workflow_id,
        "workflow_version": workflow_version,
        "artifact_receipts": [dict(item) for item in artifact_receipts],
        "implementation_artifact_refs": list(implementation_artifact_refs),
        "reviewed_decisions": [dict(item) for item in reviewed_decisions],
        "source_qualifications": [dict(item) for item in source_qualifications],
        "allocation_ledgers": [dict(item) for item in allocation_ledgers],
        "numeric_evidence_ledgers": [dict(item) for item in numeric_evidence_ledgers],
        "gate_register": dict(gate_register),
        "limitations": list(limitations),
    }
    return validate_assurance_envelope(
        {**content, "content_sha256": canonical_json_sha256(content)},
        artifact_roots=artifact_roots,
    )
