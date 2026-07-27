#!/usr/bin/env python3
"""Adapt one working-capital preparation into the M3 audit-only envelope."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from preparation_contract_kernel import (
    AUDIT_ENVELOPE_SCHEMA,
    ContractValidationError,
    artifact_receipt,
    canonical_json_sha256,
    file_sha256,
    reference_set,
    reviewed_decision_receipt,
    strict_json_load,
    validate_audit_envelope,
    validate_declared_source_receipt,
    write_json,
)
from prepare_working_capital_case import (
    CALCULATION_PRECISION,
    MANIFEST_SCHEMA,
    MAX_INPUT_DECIMAL_DIGITS,
    MAX_INPUT_DECIMAL_SCALE,
    POLICY_SCHEMA,
    RECONCILIATION_SCHEMA,
    prepare_working_capital_case,
)

__all__ = ["build_working_capital_audit_envelope", "main"]

LOGGER = logging.getLogger(__name__)
ADAPTER_ID = "working_capital_audit_adapter.v1"
ADAPTER_VERSION = "1.0.0"
PRODUCER_NAMES = {
    "discrete_cash_flow_schedule.csv",
    "exceptions.csv",
    "prepared_evidence_manifest.json",
    "raw_fact_preservation.csv",
    "reconciliation.json",
    "stock_flow_bridge.csv",
    "working_capital_schedule.csv",
}


def _artifact(
    root: Path,
    path: Path,
    *,
    artifact_id: str,
    role: str,
    media_type: str,
) -> dict[str, Any]:
    return artifact_receipt(
        root,
        path,
        artifact_id=artifact_id,
        role=role,
        media_type=media_type,
    )


def _source_receipts(sources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for source in sources:
        receipt = {
            "source_id": source["source_id"],
            "title": source["title"],
            "document_type": source["form"],
            "url": source["url"],
            "byte_count": source["byte_count"],
            "sha256": source["sha256"],
            "receipt_scope": "declared_remote_receipt",
            "metadata": {
                "accession": source["accession"],
                "filed_date": source["filed_date"],
                "role": source["role"],
            },
        }
        receipts.append(
            validate_declared_source_receipt(
                receipt,
                label=f"source {source['source_id']}",
            )
        )
    return sorted(receipts, key=lambda item: str(item["source_id"]))


def _status(
    status: str,
    basis: str,
    *,
    artifact_refs: Sequence[str] = (),
    source_refs: Sequence[str] = (),
    decision_refs: Sequence[str] = (),
    lineage_refs: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "status": status,
        "basis": basis,
        "evidence_refs": reference_set(
            artifact_refs=artifact_refs,
            source_refs=source_refs,
            decision_refs=decision_refs,
            lineage_refs=lineage_refs,
        ),
    }


def _replay_and_compare_output_set(
    case_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Replay the registered producer and require its exact complete output set."""

    with TemporaryDirectory(prefix="clara-m3-working-capital-replay-") as raw_dir:
        replay_dir = Path(raw_dir)
        replay = prepare_working_capital_case(case_path, replay_dir)
        expected_names = {
            "exceptions.csv",
            "raw_fact_preservation.csv",
            "reconciliation.json",
        }
        if replay["status"] == "passed":
            expected_names.update(
                {
                    "discrete_cash_flow_schedule.csv",
                    "prepared_evidence_manifest.json",
                    "stock_flow_bridge.csv",
                    "working_capital_schedule.csv",
                }
            )
        supplied_names = {path.name for path in output_dir.iterdir()}
        if supplied_names != expected_names:
            raise ContractValidationError(
                "prepared output set does not match deterministic replay"
            )
        for name in sorted(expected_names):
            if (output_dir / name).read_bytes() != (replay_dir / name).read_bytes():
                raise ContractValidationError(
                    f"prepared output {name} does not match deterministic replay"
                )
    return replay


def _errors(
    raw_errors: Sequence[Mapping[str, Any]],
    *,
    decision_refs: Sequence[str],
) -> list[dict[str, Any]]:
    return [
        {
            "error_id": f"error_{position:03d}",
            "code": str(error["code"]),
            "message": str(error["message"]),
            "references": reference_set(
                artifact_refs=("reconciliation",),
                decision_refs=decision_refs,
            ),
            "details": {
                "gate": error["gate"],
                "identifiers": error["identifiers"],
            },
        }
        for position, error in enumerate(raw_errors, start=1)
    ]


def build_working_capital_audit_envelope(
    *,
    clara_root: Path,
    case_path: Path,
    prepared_output_dir: Path,
) -> dict[str, Any]:
    """Return a validated M3 audit view without changing producer outputs."""

    clara_root = Path(clara_root).resolve()
    case_path = Path(case_path).resolve()
    output_dir = Path(prepared_output_dir).resolve()
    case = strict_json_load(case_path)
    replay = _replay_and_compare_output_set(case_path, output_dir)
    passed = replay["status"] == "passed"
    reconciliation_path = output_dir / "reconciliation.json"
    reconciliation = strict_json_load(reconciliation_path)
    if reconciliation["schema_version"] != RECONCILIATION_SCHEMA:
        raise ContractValidationError(
            "unexpected working-capital reconciliation schema"
        )
    if reconciliation["case_id"] != case["case_id"]:
        raise ContractValidationError("working-capital reconciliation case_id mismatch")
    manifest_path = output_dir / "prepared_evidence_manifest.json"
    manifest = strict_json_load(manifest_path) if passed else None
    if manifest is not None:
        if manifest["schema_version"] != MANIFEST_SCHEMA:
            raise ContractValidationError("unexpected working-capital manifest schema")
        if manifest["case_id"] != case["case_id"]:
            raise ContractValidationError("working-capital manifest case_id mismatch")

    case_root = case_path.parent
    facts_path = case_root / str(case["files"]["public_working_capital_facts"]["path"])
    policy_path = case_root / str(
        case["files"]["reviewed_working_capital_policy"]["path"]
    )
    policy = strict_json_load(policy_path)
    if policy["schema_version"] != POLICY_SCHEMA:
        raise ContractValidationError("unexpected working-capital policy schema")
    if policy["review"]["status"] != "reviewed":
        raise ContractValidationError("working-capital policy is not reviewed")

    raw_facts_output = output_dir / "raw_fact_preservation.csv"
    exceptions_path = output_dir / "exceptions.csv"
    discrete_cash_flow_path = output_dir / "discrete_cash_flow_schedule.csv"
    schedule_path = output_dir / "working_capital_schedule.csv"
    bridge_path = output_dir / "stock_flow_bridge.csv"
    adapter_path = Path(__file__).resolve()
    producer_path = adapter_path.with_name("prepare_working_capital_case.py")
    kernel_path = adapter_path.with_name("preparation_contract_kernel.py")
    schema_path = clara_root / "contracts" / "preparation_audit_envelope.v1.schema.json"
    artifact_specs = [
        (adapter_path, "audit_adapter", "audit_adapter", "text/x-python"),
        (schema_path, "audit_schema", "audit_schema", "application/schema+json"),
        (case_path, "case_contract", "case_contract", "application/json"),
        (
            kernel_path,
            "preparation_contract_kernel",
            "audit_kernel",
            "text/x-python",
        ),
        (
            facts_path,
            "public_working_capital_facts",
            "public_control_input",
            "text/csv",
        ),
        (
            exceptions_path,
            "exceptions",
            "diagnostic_output",
            "text/csv",
        ),
        (
            raw_facts_output,
            "raw_fact_preservation",
            "diagnostic_output",
            "text/csv",
        ),
        (
            reconciliation_path,
            "reconciliation",
            "reconciliation",
            "application/json",
        ),
        (
            policy_path,
            "reviewed_working_capital_policy",
            "reviewed_contract",
            "application/json",
        ),
        (
            producer_path,
            "working_capital_preparation_engine",
            "preparation_engine",
            "text/x-python",
        ),
    ]
    if passed:
        artifact_specs.extend(
            [
                (
                    discrete_cash_flow_path,
                    "discrete_cash_flow_schedule",
                    "prepared_output",
                    "text/csv",
                ),
                (
                    manifest_path,
                    "prepared_evidence_manifest",
                    "aggregate_lineage_evidence",
                    "application/json",
                ),
                (
                    bridge_path,
                    "stock_flow_bridge",
                    "prepared_output",
                    "text/csv",
                ),
                (
                    schedule_path,
                    "working_capital_schedule",
                    "prepared_output",
                    "text/csv",
                ),
            ]
        )
    artifacts = sorted(
        [
            _artifact(
                clara_root,
                path,
                artifact_id=artifact_id,
                role=role,
                media_type=media_type,
            )
            for path, artifact_id, role, media_type in artifact_specs
        ],
        key=lambda item: str(item["artifact_id"]),
    )

    sources = _source_receipts(case["sources"])
    source_ids = tuple(str(source["source_id"]) for source in sources)
    decision = reviewed_decision_receipt(
        decision_id="working_capital_policy_review",
        decision_kind="case_owned_working_capital_policy",
        status=str(policy["review"]["status"]),
        version=str(policy["policy_version"]),
        reviewed_on=str(policy["review"]["reviewed_on"]),
        reviewer=str(policy["review"]["reviewer"]),
        basis=str(policy["basis"]),
        content={
            "policy": policy,
            "policy_file_sha256": file_sha256(policy_path),
        },
        evidence_refs=reference_set(
            artifact_refs=(
                "case_contract",
                "reviewed_working_capital_policy",
            ),
            source_refs=source_ids,
        ),
    )
    decisions = [decision]
    decision_ids = ("working_capital_policy_review",)

    checks = [
        {
            "check_id": str(check["check_id"]),
            "check_kind": f"case_owned_{check['check_id']}",
            "required": True,
            "status": str(check["status"]),
            "references": reference_set(
                artifact_refs=(
                    "exceptions",
                    "reconciliation",
                    "raw_fact_preservation",
                ),
                source_refs=source_ids,
                decision_refs=decision_ids,
            ),
            "numeric_evidence": [],
            "details": {"failure_count": check["failure_count"]},
        }
        for check in reconciliation["checks"]
    ]
    checks.sort(key=lambda item: str(item["check_id"]))

    output_artifact_ids = (
        (
            "discrete_cash_flow_schedule",
            "exceptions",
            "prepared_evidence_manifest",
            "raw_fact_preservation",
            "reconciliation",
            "stock_flow_bridge",
            "working_capital_schedule",
        )
        if passed
        else ("exceptions", "raw_fact_preservation", "reconciliation")
    )
    artifact_lineage_ids = {
        artifact_id: f"{position:02d}_{artifact_id}_artifact"
        for position, artifact_id in enumerate(output_artifact_ids, start=1)
    }
    common_derivation_refs = reference_set(
        artifact_refs=(
            "case_contract",
            "preparation_contract_kernel",
            "public_working_capital_facts",
            "reviewed_working_capital_policy",
            "working_capital_preparation_engine",
        ),
        source_refs=source_ids,
        decision_refs=decision_ids,
    )
    artifact_lineage = [
        {
            "lineage_id": artifact_lineage_ids[artifact_id],
            "artifact_ref": artifact_id,
            "references": common_derivation_refs,
            "details": {
                "scope": "artifact_receipt_closure",
                "row_lineage_declared": False,
            },
        }
        for artifact_id in output_artifact_ids
    ]
    artifact_lineage.sort(key=lambda item: str(item["lineage_id"]))

    failed_or_passed = "passed" if passed else "failed"
    numeric_constraints = {
        "arithmetic": "decimal_exact",
        "maximum_input_digits": MAX_INPUT_DECIMAL_DIGITS,
        "maximum_input_scale": MAX_INPUT_DECIMAL_SCALE,
        "calculation_precision": CALCULATION_PRECISION,
        "reported_increment": case["preparation_recipe"]["reported_increment"],
        "tolerance": case["fixture_controls"]["tolerance"],
        "residual_allocation": "forbidden",
    }
    envelope: dict[str, Any] = {
        "schema_version": AUDIT_ENVELOPE_SCHEMA,
        "case": {
            "case_id": case["case_id"],
            "case_kind": "public_working_capital_fixture",
            "source_schema_version": case["schema_version"],
            "case_artifact_ref": "case_contract",
        },
        "adapter": {
            "adapter_id": ADAPTER_ID,
            "adapter_version": ADAPTER_VERSION,
            "implementation_sha256": file_sha256(adapter_path),
            "normalization_scope": "audit_only",
        },
        "local_artifacts": artifacts,
        "remote_sources": sources,
        "reviewed_decisions": decisions,
        "execution": {
            "execution_id": case["preparation_recipe"]["recipe_id"],
            "producer": producer_path.name,
            "producer_version": case["preparation_recipe"]["engine_version"],
            "producer_sha256": file_sha256(producer_path),
            "mode": "deterministic_mechanical",
            "input_artifact_refs": sorted(
                (
                    "case_contract",
                    "public_working_capital_facts",
                    "reviewed_working_capital_policy",
                )
            ),
            "output_artifact_refs": sorted(output_artifact_ids),
        },
        "numeric_policy": {
            "representation": "decimal_string",
            "finite_only": True,
            "binary_float_allowed": False,
            "exponent_notation_allowed": False,
            "canonical_serialization_required": True,
            "case_constraints": numeric_constraints,
            "case_constraints_sha256": canonical_json_sha256(numeric_constraints),
        },
        "reconciliation": {
            "checks": checks,
            "errors": _errors(
                reconciliation["errors"],
                decision_refs=decision_ids,
            ),
        },
        "lineage": {
            "artifact": {
                "declared": True,
                "records": artifact_lineage,
                "limitations": [],
            },
            "aggregate": {
                "declared": False,
                "records": [],
                "limitations": [
                    "The manifest pins aggregate formulas and outputs but the M5b "
                    "slice does not claim M3 aggregate-lineage authority."
                ],
            },
            "row": {
                "declared": False,
                "records": [],
                "limitations": [
                    "No output row claims reviewable source-row lineage authority."
                ],
            },
        },
        "statuses": {
            "validation": _status(
                failed_or_passed,
                "Exact replay verified the complete producer-owned output set.",
                artifact_refs=(
                    "exceptions",
                    "reconciliation",
                    "raw_fact_preservation",
                ),
                decision_refs=decision_ids,
            ),
            "preparation": _status(
                failed_or_passed,
                "Reviewed arithmetic was replayed without semantic inference.",
                artifact_refs=output_artifact_ids,
                lineage_refs=tuple(artifact_lineage_ids.values()),
            ),
            "reconciliation": _status(
                failed_or_passed,
                "Case-owned checks preserve exact success or failure evidence.",
                artifact_refs=("reconciliation",),
                source_refs=source_ids,
                decision_refs=decision_ids,
            ),
            "semantic": _status(
                "not_assessed",
                "The adapter records the reviewed policy but does not prove its "
                "economic meaning, suitability, or reviewer authority.",
                artifact_refs=(
                    "case_contract",
                    "reviewed_working_capital_policy",
                ),
                decision_refs=decision_ids,
            ),
            "source": _status(
                "receipt_only",
                "SEC filing receipts are declared; remote bytes and authority are "
                "not authenticated by this adapter.",
                source_refs=source_ids,
            ),
            "downstream": _status(
                "not_assessed",
                "Reporting compatibility and report readiness are outside M5b.",
                artifact_refs=("reconciliation",),
            ),
            "publication": _status(
                "withheld",
                "Non-zero residuals remain unexplained and publication is withheld.",
                artifact_refs=("case_contract", "reconciliation"),
                decision_refs=decision_ids,
            ),
        },
        "report_ready": False,
        "limitations": [
            {
                "limitation_id": "01_remote_source_receipts",
                "scope": "source",
                "statement": (
                    "Remote SEC files are represented by declared receipts; source "
                    "authority and current remote bytes are unproven."
                ),
            },
            {
                "limitation_id": "02_policy_authority",
                "scope": "semantic",
                "statement": (
                    "A reviewed policy is present, but its semantic suitability and "
                    "reviewer authority are not mechanically proven."
                ),
            },
            {
                "limitation_id": "03_caption_cardinality",
                "scope": "reconciliation",
                "statement": (
                    "Cash-flow Other assets is not equated to balance-sheet Other "
                    "current assets, and combined AP/accrued cash flow is not split."
                ),
            },
            {
                "limitation_id": "04_unexplained_residual",
                "scope": "reconciliation",
                "statement": (
                    "Stock-flow residuals are recomputed exactly but remain "
                    "unallocated and unexplained."
                ),
            },
            {
                "limitation_id": "05_row_lineage",
                "scope": "lineage",
                "statement": "The M5b fixture does not claim row lineage.",
            },
            {
                "limitation_id": "06_report_readiness",
                "scope": "downstream",
                "statement": (
                    "No ratios, targets, normalization, reporting compatibility, "
                    "or publication readiness are assessed."
                ),
            },
        ],
    }
    return validate_audit_envelope(envelope, root=clara_root)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the working-capital audit adapter CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("prepared_output_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--clara-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        args.output.unlink(missing_ok=True)
        envelope = build_working_capital_audit_envelope(
            clara_root=args.clara_root,
            case_path=args.case,
            prepared_output_dir=args.prepared_output_dir,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, envelope)
    except (ContractValidationError, KeyError, OSError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Working-capital audit envelope: %s", envelope["case"]["case_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
