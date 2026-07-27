#!/usr/bin/env python3
"""Adapt one monthly-P&L preparation into the M3 audit-only envelope."""

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
    read_exact_csv,
    reference_set,
    reviewed_decision_receipt,
    strict_json_load,
    validate_audit_envelope,
    validate_declared_source_receipt,
    write_json,
)
from prepare_monthly_pnl_case import (
    CALCULATION_PRECISION,
    MAX_INPUT_DECIMAL_DIGITS,
    MAX_INPUT_DECIMAL_SCALE,
    prepare_monthly_pnl_case,
)

__all__ = ["build_monthly_pnl_audit_envelope", "main"]

LOGGER = logging.getLogger(__name__)
ADAPTER_ID = "monthly_pnl_audit_adapter.v1"
ADAPTER_VERSION = "1.0.0"
MAPPING_COLUMNS = (
    "mapping_row_id",
    "mapping_version",
    "scope_id",
    "entity_id",
    "account_code",
    "account_name",
    "mapping_action",
    "statement_line_id",
    "presentation_multiplier",
    "effective_start",
    "effective_end",
    "status",
    "reviewed_on",
    "evidence",
)


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
        metadata = {
            key: value
            for key, value in source.items()
            if key
            not in {
                "source_id",
                "title",
                "form",
                "url",
                "byte_count",
                "sha256",
            }
        }
        receipt: dict[str, Any] = {
            "source_id": source["source_id"],
            "title": source["title"],
            "document_type": str(source["form"]),
            "url": source["url"],
            "byte_count": source["byte_count"],
            "sha256": source["sha256"],
            "receipt_scope": "declared_remote_receipt",
        }
        if metadata:
            receipt["metadata"] = metadata
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


def _errors(
    raw_errors: Sequence[Mapping[str, Any]],
    *,
    decision_refs: Sequence[str],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for position, raw_error in enumerate(raw_errors, start=1):
        identifiers = raw_error.get("identifiers", [])
        errors.append(
            {
                "error_id": f"error_{position:03d}",
                "code": str(raw_error["code"]),
                "message": str(raw_error["message"]),
                "references": reference_set(
                    artifact_refs=("reconciliation",),
                    decision_refs=decision_refs,
                ),
                "details": {
                    "gate": raw_error["gate"],
                    "identifiers": identifiers,
                },
            }
        )
    return errors


def _replay_and_compare_output_set(
    case_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Replay the registered producer and require its complete exact output set."""

    producer_names = {
        "monthly_pnl.csv",
        "prepared_evidence_manifest.json",
        "reconciliation.json",
        "unmapped_accounts.csv",
    }
    with TemporaryDirectory(prefix="clara-m3-monthly-pnl-replay-") as raw_dir:
        replay_dir = Path(raw_dir)
        replay = prepare_monthly_pnl_case(case_path, replay_dir)
        expected_names = {
            "reconciliation.json",
            "unmapped_accounts.csv",
        }
        if replay["status"] == "passed":
            expected_names.update(
                {"monthly_pnl.csv", "prepared_evidence_manifest.json"}
            )
        supplied_names = {
            name for name in producer_names if (output_dir / name).is_file()
        }
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


def build_monthly_pnl_audit_envelope(
    *,
    clara_root: Path,
    case_path: Path,
    prepared_output_dir: Path,
) -> dict[str, Any]:
    """Return a validated audit view without changing the M2 output set."""

    clara_root = clara_root.resolve()
    case_path = case_path.resolve()
    case = strict_json_load(case_path)
    output_dir = prepared_output_dir.resolve()
    replay = _replay_and_compare_output_set(case_path, output_dir)
    reconciliation_path = output_dir / "reconciliation.json"
    manifest_path = output_dir / "prepared_evidence_manifest.json"
    reconciliation = strict_json_load(reconciliation_path)
    passed = replay["status"] == "passed"
    manifest = strict_json_load(manifest_path) if passed else None
    case_id = str(case["case_id"])
    if reconciliation["case_id"] != case_id:
        raise ContractValidationError("M2 output case_id does not match case contract")
    if manifest is not None and manifest["case_id"] != case_id:
        raise ContractValidationError(
            "M2 manifest case_id does not match case contract"
        )
    if reconciliation["schema_version"] != "clara.reconciliation_result.v1":
        raise ContractValidationError("unexpected M2 reconciliation schema")
    if (
        manifest is not None
        and manifest["schema_version"] != "clara.prepared_evidence_manifest.v1"
    ):
        raise ContractValidationError("unexpected M2 manifest schema")

    case_root = case_path.parent
    trial_balance_path = case_root / str(
        case["files"]["synthetic_monthly_trial_balance"]["path"]
    )
    mapping_path = case_root / str(case["files"]["reviewed_coa_mapping"]["path"])
    public_facts_path = case_root / str(case["files"]["public_statement_facts"]["path"])
    monthly_pnl_path = output_dir / "monthly_pnl.csv"
    unmapped_path = output_dir / "unmapped_accounts.csv"
    adapter_path = Path(__file__).resolve()
    producer_path = adapter_path.with_name("prepare_monthly_pnl_case.py")
    kernel_path = adapter_path.with_name("preparation_contract_kernel.py")
    schema_path = (
        clara_root / "contracts" / ("preparation_audit_envelope.v1.schema.json")
    )
    artifact_specs = [
        (
            adapter_path,
            "audit_adapter",
            "audit_adapter",
            "text/x-python",
        ),
        (
            schema_path,
            "audit_schema",
            "audit_schema",
            "application/schema+json",
        ),
        (
            case_path,
            "case_contract",
            "case_contract",
            "application/json",
        ),
        (
            producer_path,
            "monthly_pnl_preparation_engine",
            "preparation_engine",
            "text/x-python",
        ),
        (
            kernel_path,
            "preparation_contract_kernel",
            "audit_kernel",
            "text/x-python",
        ),
        (
            public_facts_path,
            "public_statement_facts",
            "public_control_input",
            "text/csv",
        ),
        (
            reconciliation_path,
            "reconciliation",
            "reconciliation",
            "application/json",
        ),
        (
            mapping_path,
            "reviewed_coa_mapping",
            "reviewed_contract",
            "text/csv",
        ),
        (
            trial_balance_path,
            "synthetic_monthly_trial_balance",
            "prepared_input",
            "text/csv",
        ),
        (
            unmapped_path,
            "unmapped_accounts",
            "diagnostic_output",
            "text/csv",
        ),
    ]
    if passed:
        artifact_specs.extend(
            [
                (
                    monthly_pnl_path,
                    "monthly_pnl",
                    "prepared_output",
                    "text/csv",
                ),
                (
                    manifest_path,
                    "prepared_evidence_manifest",
                    "aggregate_lineage_evidence",
                    "application/json",
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
    source_ids = [str(source["source_id"]) for source in sources]
    mapping_rows = read_exact_csv(
        mapping_path,
        columns=MAPPING_COLUMNS,
        label="reviewed COA mapping",
    )
    reviewed_dates = sorted({row["reviewed_on"] for row in mapping_rows})
    if len(reviewed_dates) != 1:
        raise ContractValidationError(
            "reviewed COA mapping must have one review date for this fixture"
        )
    mapping_contract = case["reviewed_mapping"]
    mapping_status = str(mapping_contract["required_status"])
    mapping_version = str(mapping_contract["mapping_version"])
    if mapping_status != "reviewed":
        raise ContractValidationError("mapping contract is not reviewed")
    if {row["status"] for row in mapping_rows} != {mapping_status}:
        raise ContractValidationError(
            "mapping rows do not preserve the reviewed contract status"
        )
    if {row["mapping_version"] for row in mapping_rows} != {mapping_version}:
        raise ContractValidationError(
            "mapping rows do not preserve the reviewed contract version"
        )
    scope_relationship = case["reviewed_scope_relationship"]
    scope_status = str(scope_relationship["status"])
    if scope_status != "reviewed":
        raise ContractValidationError("scope relationship is not reviewed")
    decisions = sorted(
        [
            reviewed_decision_receipt(
                decision_id="coa_mapping_review",
                decision_kind="case_owned_coa_mapping",
                status=mapping_status,
                version=mapping_version,
                reviewed_on=reviewed_dates[0],
                basis=str(mapping_contract["review_basis"]),
                content={
                    "reviewed_mapping": mapping_contract,
                    "reviewed_mapping_asset_sha256": file_sha256(mapping_path),
                },
                evidence_refs=reference_set(
                    artifact_refs=("case_contract", "reviewed_coa_mapping"),
                ),
            ),
            reviewed_decision_receipt(
                decision_id="scope_relationship_review",
                decision_kind="case_owned_scope_relationship",
                status=scope_status,
                reviewed_on=None,
                basis=str(scope_relationship["statement"]),
                content=scope_relationship,
                evidence_refs=reference_set(
                    artifact_refs=("case_contract",),
                    source_refs=source_ids,
                ),
            ),
        ],
        key=lambda item: str(item["decision_id"]),
    )
    decision_ids = tuple(str(item["decision_id"]) for item in decisions)
    mapping_check_ids = {
        "leaf_aggregation_conservation",
        "mapping_contract",
        "monthly_statement_identities",
        "public_tie_outs",
        "sign_contract",
        "source_row_conservation",
    }
    scope_check_ids = {"public_tie_outs", "scope_contract"}
    source_check_ids = {"input_contract", "public_tie_outs"}
    checks = sorted(
        [
            {
                "check_id": str(check["check_id"]),
                "check_kind": f"case_owned_{check['check_id']}",
                "required": True,
                "status": str(check["status"]),
                "references": reference_set(
                    artifact_refs=("reconciliation",),
                    source_refs=(
                        source_ids if check["check_id"] in source_check_ids else ()
                    ),
                    decision_refs=tuple(
                        decision_id
                        for decision_id, applies in (
                            (
                                "coa_mapping_review",
                                check["check_id"] in mapping_check_ids,
                            ),
                            (
                                "scope_relationship_review",
                                check["check_id"] in scope_check_ids,
                            ),
                        )
                        if applies
                    ),
                ),
                "numeric_evidence": [],
                "details": {"failure_count": check["failure_count"]},
            }
            for check in reconciliation["checks"]
        ],
        key=lambda item: str(item["check_id"]),
    )
    numeric_constraints = {
        "arithmetic": case["preparation_recipe"]["arithmetic"],
        "maximum_input_digits": MAX_INPUT_DECIMAL_DIGITS,
        "maximum_input_scale": MAX_INPUT_DECIMAL_SCALE,
        "calculation_precision": CALCULATION_PRECISION,
        "rounding_traps": ["Inexact", "Rounded"],
        "tolerance_selection": "case_owned",
    }
    artifact_lineage_ids = {
        "monthly_pnl": "01_monthly_pnl_artifact",
        "prepared_evidence_manifest": "02_prepared_manifest_artifact",
        "reconciliation": "03_reconciliation_artifact",
        "unmapped_accounts": "04_unmapped_accounts_artifact",
    }
    output_artifact_ids = (
        (
            "monthly_pnl",
            "prepared_evidence_manifest",
            "reconciliation",
            "unmapped_accounts",
        )
        if passed
        else ("reconciliation", "unmapped_accounts")
    )
    aggregate_lineage_id = "10_statement_line_period_aggregate"
    derivation_refs = {
        "monthly_pnl": reference_set(
            artifact_refs=(
                "audit_schema",
                "case_contract",
                "monthly_pnl_preparation_engine",
                "preparation_contract_kernel",
                "reviewed_coa_mapping",
                "synthetic_monthly_trial_balance",
            ),
            decision_refs=("coa_mapping_review",),
        ),
        "unmapped_accounts": reference_set(
            artifact_refs=(
                "audit_schema",
                "case_contract",
                "monthly_pnl_preparation_engine",
                "preparation_contract_kernel",
                "reviewed_coa_mapping",
                "synthetic_monthly_trial_balance",
            ),
            decision_refs=("coa_mapping_review",),
        ),
        "reconciliation": reference_set(
            artifact_refs=(
                "audit_schema",
                "case_contract",
                "monthly_pnl_preparation_engine",
                "preparation_contract_kernel",
                "public_statement_facts",
                "reviewed_coa_mapping",
                "synthetic_monthly_trial_balance",
            ),
            source_refs=source_ids,
            decision_refs=decision_ids,
        ),
    }
    if passed:
        derivation_refs["prepared_evidence_manifest"] = reference_set(
            artifact_refs=(
                "audit_schema",
                "case_contract",
                "monthly_pnl",
                "monthly_pnl_preparation_engine",
                "preparation_contract_kernel",
                "public_statement_facts",
                "reconciliation",
                "reviewed_coa_mapping",
                "synthetic_monthly_trial_balance",
                "unmapped_accounts",
            ),
            source_refs=source_ids,
            decision_refs=decision_ids,
        )
    artifact_lineage_records = [
        {
            "lineage_id": artifact_lineage_ids[artifact_id],
            "artifact_ref": artifact_id,
            "references": derivation_refs[artifact_id],
            "details": {
                "scope": "artifact_receipt_closure",
                "publication_classification": "synthetic_benchmark_only",
            },
        }
        for artifact_id in output_artifact_ids
    ]
    aggregate_level: dict[str, Any]
    if passed:
        if manifest is None:
            raise ContractValidationError("passed replay must contain a manifest")
        aggregate_level = {
            "declared": True,
            "records": [
                {
                    "lineage_id": aggregate_lineage_id,
                    "aggregate_id": "statement_line_and_period",
                    "output_artifact_ref": "monthly_pnl",
                    "evidence_artifact_ref": "prepared_evidence_manifest",
                    "evidence_json_pointer": "/lineage",
                    "aggregate_id_json_pointer": "/lineage/grain",
                    "output_artifact_id_json_pointer": "/outputs/0/artifact_id",
                    "output_sha256_json_pointer": "/outputs/0/sha256",
                    "evidence_sha256": canonical_json_sha256(manifest["lineage"]),
                    "references": reference_set(
                        artifact_refs=(
                            "monthly_pnl",
                            "prepared_evidence_manifest",
                            "reviewed_coa_mapping",
                            "synthetic_monthly_trial_balance",
                        ),
                        decision_refs=("coa_mapping_review",),
                        lineage_refs=(artifact_lineage_ids["monthly_pnl"],),
                    ),
                    "details": {
                        "scope": "manifest_declared_aggregate_metadata",
                        "semantic_validation": "not_assessed",
                    },
                }
            ],
            "limitations": [
                "The located manifest evidence records account-to-line and "
                "dependency aggregates, not cell-to-source-row derivation edges."
            ],
        }
    else:
        aggregate_level = {
            "declared": False,
            "records": [],
            "limitations": [
                "The failed producer run emitted no prepared manifest or "
                "aggregate-lineage evidence."
            ],
        }
    producer_input_refs = (
        "case_contract",
        "public_statement_facts",
        "reviewed_coa_mapping",
        "synthetic_monthly_trial_balance",
    )
    failed_or_passed = "passed" if passed else "failed"
    preparation_status_artifacts = (
        ("monthly_pnl", "monthly_pnl_preparation_engine", "reconciliation")
        if passed
        else (
            "monthly_pnl_preparation_engine",
            "reconciliation",
            "unmapped_accounts",
        )
    )
    downstream_artifacts = (
        ("prepared_evidence_manifest",) if passed else ("reconciliation",)
    )
    publication_artifacts = (
        ("monthly_pnl", "prepared_evidence_manifest")
        if passed
        else ("case_contract", "reconciliation")
    )
    envelope: dict[str, Any] = {
        "schema_version": AUDIT_ENVELOPE_SCHEMA,
        "case": {
            "case_id": case_id,
            "case_kind": "synthetic_monthly_pnl_benchmark",
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
            "execution_id": str(case["preparation_recipe"]["recipe_id"]),
            "producer": "prepare_monthly_pnl_case.py",
            "producer_version": str(case["preparation_recipe"]["engine_version"]),
            "producer_sha256": file_sha256(producer_path),
            "mode": "deterministic_mechanical",
            "input_artifact_refs": sorted(producer_input_refs),
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
                "records": artifact_lineage_records,
                "limitations": [],
            },
            "aggregate": aggregate_level,
            "row": {
                "declared": False,
                "records": [],
                "limitations": [
                    "The M2 fixture does not expose reviewable output-cell-to-source-row "
                    "lineage."
                ],
            },
        },
        "statuses": {
            "validation": _status(
                failed_or_passed,
                "Deterministic replay verified the complete producer-owned "
                "output set and preserved its validation result.",
                artifact_refs=("reconciliation",),
                decision_refs=decision_ids,
            ),
            "preparation": _status(
                failed_or_passed,
                "The registered monthly-P&L fixture recipe was replayed and "
                "its exact success or failure outputs were preserved.",
                artifact_refs=preparation_status_artifacts,
                lineage_refs=((artifact_lineage_ids["monthly_pnl"],) if passed else ()),
            ),
            "reconciliation": _status(
                failed_or_passed,
                "All required case-owned checks and errors are preserved.",
                artifact_refs=("reconciliation",),
                source_refs=source_ids,
                decision_refs=decision_ids,
            ),
            "semantic": _status(
                "not_assessed",
                "The adapter preserves explicit mapping and scope reviews and "
                "does not judge their correctness, authority, or meaning.",
                artifact_refs=("case_contract", "reviewed_coa_mapping"),
                decision_refs=decision_ids,
            ),
            "source": _status(
                "receipt_only",
                "Remote filing bytes are not packaged; declared receipts are pinned.",
                source_refs=source_ids,
            ),
            "downstream": _status(
                "not_assessed",
                "Semantic compatibility, full evidence binding, and report readiness remain M4.",
                artifact_refs=downstream_artifacts,
            ),
            "publication": _status(
                "withheld",
                "Synthetic monthly values are benchmark evidence, never issuer actuals.",
                artifact_refs=publication_artifacts,
                decision_refs=decision_ids,
            ),
        },
        "report_ready": False,
        "limitations": sorted(
            [
                {
                    "limitation_id": "01_synthetic_monthly_values",
                    "scope": "case",
                    "statement": (
                        "Monthly phasing, accounts, splits, mapping, and clearing "
                        "rows are synthetic."
                    ),
                },
                {
                    "limitation_id": "02_remote_authenticity",
                    "scope": "source",
                    "statement": (
                        "The adapter validates declared receipts and does not "
                        "authenticate current remote filing bytes."
                    ),
                },
                {
                    "limitation_id": "03_semantic_correctness",
                    "scope": "semantic",
                    "statement": (
                        "Mapping and scope carry declared reviews; period "
                        "membership, economic meaning, and reviewer authority "
                        "remain outside mechanical validation."
                    ),
                },
                {
                    "limitation_id": "04_row_lineage",
                    "scope": "lineage",
                    "statement": (
                        "Aggregate account and dependency lineage does not prove "
                        "row- or cell-level derivation."
                    ),
                },
                {
                    "limitation_id": "05_downstream_readiness",
                    "scope": "downstream",
                    "statement": (
                        "Complete semantic, reporting, and source-bound publication "
                        "readiness is not assessed."
                    ),
                },
            ],
            key=lambda item: item["limitation_id"],
        ),
    }
    return validate_audit_envelope(envelope, root=clara_root)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the monthly-P&L audit adapter."""

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
        envelope = build_monthly_pnl_audit_envelope(
            clara_root=args.clara_root,
            case_path=args.case,
            prepared_output_dir=args.prepared_output_dir,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, envelope)
    except (ContractValidationError, KeyError, OSError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Monthly-P&L audit envelope: %s", envelope["case"]["case_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
