"""Small package-neutral assurance contracts for Vera workflows.

The validators enforce mechanically checkable structure, exact-value closure,
and gate dependencies. They deliberately do not judge source authority,
accounting meaning, evidence sufficiency, materiality, or professional
conclusions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .money import MoneyValidationError, parse_canonical_decimal
from .serialization import canonical_json_sha256

__all__ = [
    "AssuranceContractError",
    "build_gate_register",
    "build_numeric_evidence_ledger",
    "build_source_qualification",
    "validate_gate_register",
    "validate_numeric_evidence_ledger",
    "validate_source_qualification",
]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_QUALIFICATION_STATUSES = {
    "qualified",
    "needs_review",
    "unsupported_source_layout",
}
_CONTROL_STATUSES = {"passed", "failed", "not_assessed"}
_GATE_NAMES = (
    "source",
    "preparation",
    "reconciliation",
    "semantic_review",
    "reporting",
    "publication",
)
_GATE_STATUSES = {
    "passed",
    "failed",
    "blocked",
    "not_assessed",
    "not_applicable",
    "withheld",
}
_DEFAULT_GATE_DEPENDENCIES = {
    "preparation": ("source",),
    "reconciliation": ("preparation",),
    "semantic_review": ("preparation",),
    "reporting": ("reconciliation", "semantic_review"),
    "publication": ("reporting",),
}


class AssuranceContractError(ValueError):
    """Raised when a Vera assurance contract is internally inconsistent."""


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssuranceContractError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AssuranceContractError(f"{label} must be a list")
    return list(value)


def _text(value: object, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise AssuranceContractError(f"{label} must be trimmed text")
    if not value and not allow_empty:
        raise AssuranceContractError(f"{label} must be non-empty")
    return value


def _identifier(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise AssuranceContractError(f"{label} must be a canonical identifier")
    return text


def _non_negative_int(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AssuranceContractError(f"{label} must be a non-negative integer")
    return value


def _exact_fields(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    label: str,
) -> None:
    optional = optional or set()
    missing = required - set(value)
    unexpected = set(value) - required - optional
    if missing or unexpected:
        raise AssuranceContractError(
            f"{label} fields invalid; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )


def _validated_control(control: object, *, label: str) -> dict[str, Any]:
    item = _mapping(control, label=label)
    _exact_fields(
        item,
        required={"control_id", "required", "status", "evidence_refs", "detail"},
        label=label,
    )
    control_id = _identifier(item["control_id"], label=f"{label}.control_id")
    if not isinstance(item["required"], bool):
        raise AssuranceContractError(f"{label}.required must be boolean")
    status = _text(item["status"], label=f"{label}.status")
    if status not in _CONTROL_STATUSES:
        raise AssuranceContractError(f"{label}.status is unsupported")
    evidence_refs = [
        _identifier(ref, label=f"{label}.evidence_refs[{index}]")
        for index, ref in enumerate(
            _sequence(item["evidence_refs"], label=f"{label}.evidence_refs")
        )
    ]
    if len(evidence_refs) != len(set(evidence_refs)):
        raise AssuranceContractError(f"{label}.evidence_refs must be unique")
    return {
        "control_id": control_id,
        "required": item["required"],
        "status": status,
        "evidence_refs": evidence_refs,
        "detail": _text(item["detail"], label=f"{label}.detail", allow_empty=True),
    }


def validate_source_qualification(value: object) -> dict[str, Any]:
    """Validate a pre-parser source qualification record."""

    payload = _mapping(value, label="source qualification")
    _exact_fields(
        payload,
        required={
            "schema_version",
            "qualification_id",
            "adapter_id",
            "adapter_version",
            "source_family",
            "status",
            "source_artifact_refs",
            "reviewed_mapping_ref",
            "candidate_row_count",
            "emitted_row_count",
            "controls",
            "limitations",
        },
        label="source qualification",
    )
    if payload["schema_version"] != "vera.source_qualification.v1":
        raise AssuranceContractError("unsupported source qualification schema")
    normalized: dict[str, Any] = {
        "schema_version": "vera.source_qualification.v1",
        "qualification_id": _identifier(
            payload["qualification_id"], label="qualification_id"
        ),
        "adapter_id": _identifier(payload["adapter_id"], label="adapter_id"),
        "adapter_version": _identifier(
            payload["adapter_version"], label="adapter_version"
        ),
        "source_family": _identifier(payload["source_family"], label="source_family"),
    }
    status = _text(payload["status"], label="status")
    if status not in _QUALIFICATION_STATUSES:
        raise AssuranceContractError("unsupported source qualification status")
    normalized["status"] = status
    source_refs = [
        _identifier(ref, label=f"source_artifact_refs[{index}]")
        for index, ref in enumerate(
            _sequence(payload["source_artifact_refs"], label="source_artifact_refs")
        )
    ]
    if not source_refs or len(source_refs) != len(set(source_refs)):
        raise AssuranceContractError(
            "source_artifact_refs must be non-empty and unique"
        )
    normalized["source_artifact_refs"] = source_refs
    reviewed_mapping_ref = payload["reviewed_mapping_ref"]
    if reviewed_mapping_ref is not None:
        reviewed_mapping_ref = _identifier(
            reviewed_mapping_ref, label="reviewed_mapping_ref"
        )
    normalized["reviewed_mapping_ref"] = reviewed_mapping_ref
    candidate_count = _non_negative_int(
        payload["candidate_row_count"], label="candidate_row_count"
    )
    emitted_count = _non_negative_int(
        payload["emitted_row_count"], label="emitted_row_count"
    )
    normalized["candidate_row_count"] = candidate_count
    normalized["emitted_row_count"] = emitted_count
    if emitted_count > candidate_count:
        raise AssuranceContractError(
            "emitted_row_count cannot exceed candidate_row_count"
        )
    controls = [
        _validated_control(item, label=f"controls[{index}]")
        for index, item in enumerate(_sequence(payload["controls"], label="controls"))
    ]
    control_ids = [item["control_id"] for item in controls]
    if not controls or len(control_ids) != len(set(control_ids)):
        raise AssuranceContractError("controls must be non-empty and unique")
    normalized["controls"] = controls
    normalized["limitations"] = [
        _text(item, label=f"limitations[{index}]")
        for index, item in enumerate(
            _sequence(payload["limitations"], label="limitations")
        )
    ]

    required = [item for item in controls if item["required"]]
    required_failed = [item for item in required if item["status"] == "failed"]
    required_unassessed = [
        item for item in required if item["status"] == "not_assessed"
    ]
    if status == "qualified":
        if required_failed or required_unassessed:
            raise AssuranceContractError(
                "qualified source requires every required control to pass"
            )
    elif status == "unsupported_source_layout":
        if not required_failed:
            raise AssuranceContractError(
                "unsupported layout requires a failed required control"
            )
        if emitted_count:
            raise AssuranceContractError("unsupported layout cannot emit prepared rows")
    else:
        if required_failed or not required_unassessed:
            raise AssuranceContractError(
                "needs_review requires unassessed, but no failed, required controls"
            )
        if emitted_count:
            raise AssuranceContractError(
                "needs_review source cannot emit prepared rows"
            )
    return normalized


def build_source_qualification(
    *,
    qualification_id: str,
    adapter_id: str,
    adapter_version: str,
    source_family: str,
    status: str,
    source_artifact_refs: Sequence[str],
    controls: Sequence[Mapping[str, Any]],
    candidate_row_count: int = 0,
    emitted_row_count: int = 0,
    reviewed_mapping_ref: str | None = None,
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Build and validate a source qualification record."""

    return validate_source_qualification(
        {
            "schema_version": "vera.source_qualification.v1",
            "qualification_id": qualification_id,
            "adapter_id": adapter_id,
            "adapter_version": adapter_version,
            "source_family": source_family,
            "status": status,
            "source_artifact_refs": list(source_artifact_refs),
            "reviewed_mapping_ref": reviewed_mapping_ref,
            "candidate_row_count": candidate_row_count,
            "emitted_row_count": emitted_row_count,
            "controls": [dict(item) for item in controls],
            "limitations": list(limitations),
        }
    )


def validate_gate_register(value: object) -> dict[str, Any]:
    """Validate independent assurance gates and their declared dependencies."""

    payload = _mapping(value, label="gate register")
    _exact_fields(
        payload,
        required={"schema_version", "gates", "report_ready"},
        label="gate register",
    )
    if payload["schema_version"] != "vera.assurance_gates.v1":
        raise AssuranceContractError("unsupported gate-register schema")
    gates = _mapping(payload["gates"], label="gates")
    if set(gates) != set(_GATE_NAMES):
        raise AssuranceContractError(f"gates must contain exactly {_GATE_NAMES}")
    normalized_gates: dict[str, Any] = {}
    for gate_name in _GATE_NAMES:
        gate = _mapping(gates[gate_name], label=f"gates.{gate_name}")
        _exact_fields(
            gate,
            required={"status", "evidence_refs", "limitations"},
            label=f"gates.{gate_name}",
        )
        status = _text(gate["status"], label=f"gates.{gate_name}.status")
        if status not in _GATE_STATUSES:
            raise AssuranceContractError(f"gates.{gate_name}.status is unsupported")
        evidence_refs = [
            _identifier(ref, label=f"gates.{gate_name}.evidence_refs[{index}]")
            for index, ref in enumerate(
                _sequence(
                    gate["evidence_refs"], label=f"gates.{gate_name}.evidence_refs"
                )
            )
        ]
        if len(evidence_refs) != len(set(evidence_refs)):
            raise AssuranceContractError(
                f"gates.{gate_name}.evidence_refs must be unique"
            )
        limitations = [
            _text(item, label=f"gates.{gate_name}.limitations[{index}]")
            for index, item in enumerate(
                _sequence(gate["limitations"], label=f"gates.{gate_name}.limitations")
            )
        ]
        if status == "passed" and not evidence_refs:
            raise AssuranceContractError(
                f"passed gate {gate_name} requires evidence_refs"
            )
        normalized_gates[gate_name] = {
            "status": status,
            "evidence_refs": evidence_refs,
            "limitations": limitations,
        }
    for gate_name, dependencies in _DEFAULT_GATE_DEPENDENCIES.items():
        if normalized_gates[gate_name]["status"] != "passed":
            continue
        for dependency in dependencies:
            if normalized_gates[dependency]["status"] not in {
                "passed",
                "not_applicable",
            }:
                raise AssuranceContractError(
                    f"passed gate {gate_name} requires {dependency} to pass "
                    "or be not_applicable"
                )
    if not isinstance(payload["report_ready"], bool):
        raise AssuranceContractError("report_ready must be boolean")
    ready_statuses = {
        normalized_gates[name]["status"]
        for name in (
            "source",
            "preparation",
            "reconciliation",
            "semantic_review",
            "reporting",
        )
    }
    computed_ready = ready_statuses <= {"passed", "not_applicable"}
    if payload["report_ready"] != computed_ready:
        raise AssuranceContractError("report_ready does not match gate statuses")
    return {
        "schema_version": "vera.assurance_gates.v1",
        "gates": normalized_gates,
        "report_ready": computed_ready,
    }


def build_gate_register(
    gates: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a gate register and derive report readiness."""

    raw = {
        "schema_version": "vera.assurance_gates.v1",
        "gates": {name: dict(value) for name, value in gates.items()},
        "report_ready": all(
            gates.get(name, {}).get("status") in {"passed", "not_applicable"}
            for name in (
                "source",
                "preparation",
                "reconciliation",
                "semantic_review",
                "reporting",
            )
        ),
    }
    return validate_gate_register(raw)


def _validated_locator(value: object, *, label: str) -> dict[str, str]:
    locator = _mapping(value, label=label)
    _exact_fields(
        locator,
        required={"artifact_ref", "locator", "value"},
        label=label,
    )
    return {
        "artifact_ref": _identifier(
            locator["artifact_ref"], label=f"{label}.artifact_ref"
        ),
        "locator": _text(locator["locator"], label=f"{label}.locator"),
        "value": _canonical_value(locator["value"], label=f"{label}.value"),
    }


def _canonical_value(value: object, *, label: str) -> str:
    try:
        parse_canonical_decimal(value, label=label)
    except MoneyValidationError as exc:
        raise AssuranceContractError(str(exc)) from exc
    return str(value)


def validate_numeric_evidence_ledger(value: object) -> dict[str, Any]:
    """Validate exact source-prepared-output numeric closure."""

    payload = _mapping(value, label="numeric evidence ledger")
    _exact_fields(
        payload,
        required={"schema_version", "ledger_id", "entries", "content_sha256"},
        label="numeric evidence ledger",
    )
    if payload["schema_version"] != "vera.numeric_evidence_ledger.v1":
        raise AssuranceContractError("unsupported numeric-evidence schema")
    ledger_id = _identifier(payload["ledger_id"], label="ledger_id")
    entries: list[dict[str, Any]] = []
    for index, raw_entry in enumerate(_sequence(payload["entries"], label="entries")):
        label = f"entries[{index}]"
        entry = _mapping(raw_entry, label=label)
        _exact_fields(
            entry,
            required={
                "evidence_id",
                "value",
                "unit",
                "currency",
                "source",
                "prepared",
                "outputs",
                "calculation_ref",
                "decision_ref",
                "limitations",
            },
            label=label,
        )
        value_text = _canonical_value(entry["value"], label=f"{label}.value")
        source = _validated_locator(entry["source"], label=f"{label}.source")
        if source["value"] != value_text:
            raise AssuranceContractError(
                f"{label}.source.value does not equal the ledger value"
            )
        prepared = _mapping(entry["prepared"], label=f"{label}.prepared")
        _exact_fields(
            prepared,
            required={"artifact_ref", "locator", "value"},
            label=f"{label}.prepared",
        )
        prepared_value = _canonical_value(
            prepared["value"], label=f"{label}.prepared.value"
        )
        if prepared_value != value_text:
            raise AssuranceContractError(
                f"{label}.prepared.value does not equal the ledger value"
            )
        outputs: list[dict[str, str]] = []
        for output_index, output_value in enumerate(
            _sequence(entry["outputs"], label=f"{label}.outputs")
        ):
            output_label = f"{label}.outputs[{output_index}]"
            output = _mapping(output_value, label=output_label)
            _exact_fields(
                output,
                required={"artifact_ref", "locator", "value"},
                label=output_label,
            )
            rendered_value = _canonical_value(
                output["value"], label=f"{output_label}.value"
            )
            if rendered_value != value_text:
                raise AssuranceContractError(
                    f"{output_label}.value does not equal the ledger value"
                )
            outputs.append(
                {
                    "artifact_ref": _identifier(
                        output["artifact_ref"],
                        label=f"{output_label}.artifact_ref",
                    ),
                    "locator": _text(
                        output["locator"], label=f"{output_label}.locator"
                    ),
                    "value": rendered_value,
                }
            )
        if not outputs:
            raise AssuranceContractError(f"{label}.outputs must be non-empty")
        calculation_ref = entry["calculation_ref"]
        if calculation_ref is not None:
            calculation_ref = _identifier(
                calculation_ref, label=f"{label}.calculation_ref"
            )
        decision_ref = entry["decision_ref"]
        if decision_ref is not None:
            decision_ref = _identifier(decision_ref, label=f"{label}.decision_ref")
        entries.append(
            {
                "evidence_id": _identifier(
                    entry["evidence_id"], label=f"{label}.evidence_id"
                ),
                "value": value_text,
                "unit": _text(entry["unit"], label=f"{label}.unit"),
                "currency": (
                    None
                    if entry["currency"] is None
                    else _text(entry["currency"], label=f"{label}.currency")
                ),
                "source": source,
                "prepared": {
                    "artifact_ref": _identifier(
                        prepared["artifact_ref"],
                        label=f"{label}.prepared.artifact_ref",
                    ),
                    "locator": _text(
                        prepared["locator"], label=f"{label}.prepared.locator"
                    ),
                    "value": prepared_value,
                },
                "outputs": outputs,
                "calculation_ref": calculation_ref,
                "decision_ref": decision_ref,
                "limitations": [
                    _text(item, label=f"{label}.limitations[{item_index}]")
                    for item_index, item in enumerate(
                        _sequence(entry["limitations"], label=f"{label}.limitations")
                    )
                ],
            }
        )
    ids = [entry["evidence_id"] for entry in entries]
    if not entries or len(ids) != len(set(ids)):
        raise AssuranceContractError(
            "numeric evidence IDs must be non-empty and unique"
        )
    content = {
        "schema_version": "vera.numeric_evidence_ledger.v1",
        "ledger_id": ledger_id,
        "entries": entries,
    }
    digest = _text(payload["content_sha256"], label="content_sha256")
    expected = canonical_json_sha256(content)
    if digest != expected:
        raise AssuranceContractError("numeric evidence content_sha256 is stale")
    return {**content, "content_sha256": expected}


def build_numeric_evidence_ledger(
    entries: Sequence[Mapping[str, Any]],
    *,
    ledger_id: str = "numeric_evidence",
) -> dict[str, Any]:
    """Build and seal a numeric evidence ledger."""

    content = {
        "schema_version": "vera.numeric_evidence_ledger.v1",
        "ledger_id": ledger_id,
        "entries": [dict(entry) for entry in entries],
    }
    return validate_numeric_evidence_ledger(
        {**content, "content_sha256": canonical_json_sha256(content)}
    )
