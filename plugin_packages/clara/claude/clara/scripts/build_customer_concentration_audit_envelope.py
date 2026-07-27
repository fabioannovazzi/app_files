#!/usr/bin/env python3
"""Adapt customer-concentration preparation into the M3 audit-only envelope."""

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
    decimal_text,
    file_sha256,
    parse_decimal,
    reference_set,
    reviewed_decision_receipt,
    strict_json_load,
    validate_audit_envelope,
    validate_declared_source_receipt,
    write_json,
)
from prepare_customer_concentration_case import (
    ENGINE_VERSION,
    RECIPE_ID,
    RECONCILIATION_SCHEMA,
    prepare_customer_concentration_case,
)

__all__ = ["build_customer_concentration_audit_envelope", "main"]

LOGGER = logging.getLogger(__name__)
ADAPTER_ID = "customer_concentration_audit_adapter.v1"
ADAPTER_VERSION = "1.0.0"
PRODUCER_NAMES = {
    "customer_concentration_summary.csv",
    "exceptions.csv",
    "prepared_evidence_manifest.json",
    "reconciliation.json",
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
        metadata = {
            key: value
            for key, value in source.items()
            if key
            not in {
                "source_id",
                "publisher",
                "title",
                "form",
                "filed_date",
                "url",
                "byte_count",
                "sha256",
            }
        }
        receipt: dict[str, Any] = {
            "source_id": source["source_id"],
            "publisher": source["publisher"],
            "title": source["title"],
            "document_type": source["form"],
            "document_date": source["filed_date"],
            "url": source["url"],
            "byte_count": source["byte_count"],
            "sha256": source["sha256"],
            "receipt_scope": "declared_remote_receipt",
            "metadata": metadata,
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


def _errors(
    raw_errors: Sequence[Mapping[str, Any]],
    *,
    decision_refs: Sequence[str],
) -> list[dict[str, Any]]:
    return [
        {
            "error_id": f"error_{position:03d}",
            "code": str(raw_error["code"]),
            "message": str(raw_error["message"]),
            "references": reference_set(
                artifact_refs=("exceptions", "reconciliation"),
                decision_refs=decision_refs,
            ),
            "details": {
                "gate": raw_error["gate"],
                "identifiers": raw_error["identifiers"],
            },
        }
        for position, raw_error in enumerate(raw_errors, start=1)
    ]


def _replay_and_compare_output_set(
    case_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    with TemporaryDirectory(
        prefix="clara-m3-customer-concentration-replay-"
    ) as raw_dir:
        replay_dir = Path(raw_dir)
        replay = prepare_customer_concentration_case(case_path, replay_dir)
        expected_names = {"exceptions.csv", "reconciliation.json"}
        if replay["status"] == "passed":
            expected_names.update(
                {
                    "customer_concentration_summary.csv",
                    "prepared_evidence_manifest.json",
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


def _numeric_evidence(
    reconciliation: Mapping[str, Any],
    check_id: str,
) -> list[dict[str, str]]:
    metric_ids_by_check = {
        "control_values": {
            "total_revenue_control",
            "total_accounts_receivable_control",
        },
        "revenue_share_subtotals": {"disclosed_top_three_revenue_share"},
        "accounts_receivable_subtotals": {"disclosed_accounts_receivable_subtotal"},
        "accounts_receivable_coverage": {"accounts_receivable_coverage_percent"},
        "reported_share_hhi_contribution": {"reported_share_hhi_contribution"},
    }
    metric_ids = metric_ids_by_check.get(check_id, set())
    evidence: list[dict[str, str]] = []
    for row in reconciliation["summary_results"]:
        if (
            row["metric_id"] not in metric_ids
            or row["availability_status"] != "available"
        ):
            continue
        value = parse_decimal(
            row["value"],
            label=f"summary {row['summary_id']}.value",
        )
        increment = parse_decimal(
            row["reported_increment"],
            label=f"summary {row['summary_id']}.reported_increment",
            positive=True,
        )
        evidence.append(
            {
                "name": str(row["summary_id"]),
                "value": decimal_text(value),
                "unit": str(row["unit"]),
                "reported_increment": decimal_text(increment),
            }
        )
    return sorted(evidence, key=lambda item: item["name"])


def build_customer_concentration_audit_envelope(
    *,
    clara_root: Path,
    case_path: Path,
    prepared_output_dir: Path,
) -> dict[str, Any]:
    """Return a validated M3 audit view of one customer-concentration run."""

    clara_root = clara_root.resolve()
    case_path = case_path.resolve()
    output_dir = prepared_output_dir.resolve()
    case = strict_json_load(case_path)
    replay = _replay_and_compare_output_set(case_path, output_dir)
    passed = replay["status"] == "passed"
    reconciliation_path = output_dir / "reconciliation.json"
    exceptions_path = output_dir / "exceptions.csv"
    manifest_path = output_dir / "prepared_evidence_manifest.json"
    summary_path = output_dir / "customer_concentration_summary.csv"
    reconciliation = strict_json_load(reconciliation_path)
    manifest = strict_json_load(manifest_path) if passed else None
    case_id = str(case["case_id"])
    if reconciliation["case_id"] != case_id:
        raise ContractValidationError(
            "prepared reconciliation case_id does not match case contract"
        )
    if reconciliation["schema_version"] != RECONCILIATION_SCHEMA:
        raise ContractValidationError("unexpected reconciliation schema")
    if manifest is not None:
        if manifest["case_id"] != case_id:
            raise ContractValidationError(
                "prepared manifest case_id does not match case contract"
            )
        if manifest["schema_version"] != "clara.prepared_evidence_manifest.v1":
            raise ContractValidationError("unexpected prepared manifest schema")

    case_root = case_path.parent
    exact_facts_path = case_root / str(case["files"]["exact_extracted_facts"]["path"])
    control_facts_path = case_root / str(case["files"]["exact_control_facts"]["path"])
    adapter_path = Path(__file__).resolve()
    producer_path = adapter_path.with_name("prepare_customer_concentration_case.py")
    kernel_path = adapter_path.with_name("preparation_contract_kernel.py")
    schema_path = clara_root / "contracts" / "preparation_audit_envelope.v1.schema.json"
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
            control_facts_path,
            "exact_control_facts",
            "reviewed_control_input",
            "text/csv",
        ),
        (
            exact_facts_path,
            "exact_extracted_facts",
            "reviewed_fact_input",
            "text/csv",
        ),
        (
            exceptions_path,
            "exceptions",
            "diagnostic_output",
            "text/csv",
        ),
        (
            producer_path,
            "customer_concentration_preparation_engine",
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
            reconciliation_path,
            "reconciliation",
            "reconciliation",
            "application/json",
        ),
    ]
    if passed:
        artifact_specs.extend(
            [
                (
                    summary_path,
                    "customer_concentration_summary",
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
    source_ids = tuple(str(source["source_id"]) for source in sources)
    boundary = case["reviewed_boundary"]
    source_review = case["source_extraction_review"]
    reviewed_on = str(boundary["reviewed_on"])
    reviewer = str(boundary["judgement_owner"])
    decisions = sorted(
        [
            reviewed_decision_receipt(
                decision_id="claim_boundary_review",
                decision_kind="case_owned_disclosure_and_claim_boundary",
                status=str(boundary["status"]),
                version=f"{case_id}.claims.v1",
                reviewed_on=reviewed_on,
                reviewer=reviewer,
                basis=str(boundary["statement"]),
                content=boundary,
                evidence_refs=reference_set(
                    artifact_refs=("case_contract",),
                    source_refs=source_ids,
                ),
            ),
            reviewed_decision_receipt(
                decision_id="source_extraction_review",
                decision_kind="case_owned_source_and_extraction_selection",
                status=str(source_review["status"]),
                version=f"{case_id}.source-extraction.v1",
                reviewed_on=str(source_review["reviewed_on"]),
                reviewer=str(source_review["reviewer"]),
                basis=str(source_review["basis"]),
                content={
                    "source_id": source_ids[0],
                    "exact_extracted_facts_sha256": file_sha256(exact_facts_path),
                    "exact_control_facts_sha256": file_sha256(control_facts_path),
                    "authority": source_review["authority"],
                },
                evidence_refs=reference_set(
                    artifact_refs=(
                        "case_contract",
                        "exact_control_facts",
                        "exact_extracted_facts",
                    ),
                    source_refs=source_ids,
                ),
            ),
        ],
        key=lambda item: str(item["decision_id"]),
    )
    decision_ids = tuple(str(item["decision_id"]) for item in decisions)
    source_review_checks = {
        "input_contract",
        "exact_fact_set",
        "duplicate_control",
        "alias_period_metric_contract",
        "unit_increment_contract",
        "source_contract",
        "control_values",
        "revenue_share_subtotals",
        "accounts_receivable_subtotals",
        "accounts_receivable_coverage",
        "reported_share_hhi_contribution",
    }
    checks = sorted(
        [
            {
                "check_id": str(check["check_id"]),
                "check_kind": f"case_owned_{check['check_id']}",
                "required": True,
                "status": str(check["status"]),
                "references": reference_set(
                    artifact_refs=("exceptions", "reconciliation"),
                    source_refs=(
                        source_ids if check["check_id"] in source_review_checks else ()
                    ),
                    decision_refs=tuple(
                        decision_id
                        for decision_id, applies in (
                            (
                                "claim_boundary_review",
                                check["check_id"] == "claim_abstention",
                            ),
                            (
                                "source_extraction_review",
                                check["check_id"] in source_review_checks,
                            ),
                        )
                        if applies
                    ),
                ),
                "numeric_evidence": _numeric_evidence(
                    reconciliation,
                    str(check["check_id"]),
                ),
                "details": {
                    "failure_count": check["failure_count"],
                    "availability_results": (
                        reconciliation["availability_results"]
                        if check["check_id"] == "accounts_receivable_coverage"
                        else []
                    ),
                },
            }
            for check in reconciliation["checks"]
        ],
        key=lambda item: str(item["check_id"]),
    )
    recipe = case["preparation_recipe"]
    numeric_constraints = {
        "arithmetic": recipe["arithmetic"],
        "input_numeric_form": "non_negative_canonical_integer",
        "coverage_ratio_unit": recipe["coverage_ratio_unit"],
        "coverage_ratio_scale": recipe["coverage_ratio_scale"],
        "coverage_ratio_rounding": recipe["coverage_ratio_rounding"],
        "reported_share_increment": "1",
        "tolerance": "0",
    }
    artifact_lineage_ids = {
        "customer_concentration_summary": (
            "01_customer_concentration_summary_artifact"
        ),
        "exceptions": "02_exceptions_artifact",
        "prepared_evidence_manifest": "03_prepared_manifest_artifact",
        "reconciliation": "04_reconciliation_artifact",
    }
    output_artifact_ids = (
        (
            "customer_concentration_summary",
            "exceptions",
            "prepared_evidence_manifest",
            "reconciliation",
        )
        if passed
        else ("exceptions", "reconciliation")
    )
    derivation_refs = {
        "customer_concentration_summary": reference_set(
            artifact_refs=(
                "audit_schema",
                "case_contract",
                "customer_concentration_preparation_engine",
                "exact_control_facts",
                "exact_extracted_facts",
                "preparation_contract_kernel",
            ),
            source_refs=source_ids,
            decision_refs=decision_ids,
        ),
        "exceptions": reference_set(
            artifact_refs=(
                "audit_schema",
                "case_contract",
                "customer_concentration_preparation_engine",
                "exact_control_facts",
                "exact_extracted_facts",
                "preparation_contract_kernel",
            ),
            source_refs=source_ids,
            decision_refs=decision_ids,
        ),
        "reconciliation": reference_set(
            artifact_refs=(
                "audit_schema",
                "case_contract",
                "customer_concentration_preparation_engine",
                "exact_control_facts",
                "exact_extracted_facts",
                "exceptions",
                "preparation_contract_kernel",
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
                "customer_concentration_preparation_engine",
                "customer_concentration_summary",
                "exact_control_facts",
                "exact_extracted_facts",
                "exceptions",
                "preparation_contract_kernel",
                "reconciliation",
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
                "publication_status": "withheld",
            },
        }
        for artifact_id in output_artifact_ids
    ]
    if passed:
        if manifest is None:
            raise ContractValidationError("passed replay must contain a manifest")
        aggregate_level: dict[str, Any] = {
            "declared": True,
            "records": [
                {
                    "lineage_id": "10_customer_concentration_summary_aggregate",
                    "aggregate_id": "summary_metric_and_fiscal_year",
                    "output_artifact_ref": "customer_concentration_summary",
                    "evidence_artifact_ref": "prepared_evidence_manifest",
                    "evidence_json_pointer": "/lineage",
                    "aggregate_id_json_pointer": "/lineage/grain",
                    "output_artifact_id_json_pointer": "/outputs/0/artifact_id",
                    "output_sha256_json_pointer": "/outputs/0/sha256",
                    "evidence_sha256": canonical_json_sha256(manifest["lineage"]),
                    "references": reference_set(
                        artifact_refs=(
                            "customer_concentration_summary",
                            "exact_control_facts",
                            "exact_extracted_facts",
                            "prepared_evidence_manifest",
                        ),
                        source_refs=source_ids,
                        decision_refs=decision_ids,
                        lineage_refs=(
                            artifact_lineage_ids["customer_concentration_summary"],
                        ),
                    ),
                    "details": {
                        "scope": "manifest_declared_aggregate_metadata",
                        "semantic_validation": "not_assessed",
                    },
                }
            ],
            "limitations": [
                "The manifest records summary-to-fact and summary-to-control "
                "references, not cell-level source-document coordinates."
            ],
        }
    else:
        aggregate_level = {
            "declared": False,
            "records": [],
            "limitations": [
                "The failed producer run emitted no prepared summary or "
                "aggregate-lineage manifest."
            ],
        }
    producer_output_refs = tuple(output_artifact_ids)
    failed_or_passed = "passed" if passed else "failed"
    preparation_artifacts = (
        (
            "customer_concentration_preparation_engine",
            "customer_concentration_summary",
            "exceptions",
            "reconciliation",
        )
        if passed
        else (
            "customer_concentration_preparation_engine",
            "exceptions",
            "reconciliation",
        )
    )
    downstream_artifacts = (
        ("prepared_evidence_manifest",) if passed else ("reconciliation",)
    )
    publication_artifacts = (
        (
            "case_contract",
            "customer_concentration_summary",
            "prepared_evidence_manifest",
        )
        if passed
        else ("case_contract", "reconciliation")
    )
    envelope: dict[str, Any] = {
        "schema_version": AUDIT_ENVELOPE_SCHEMA,
        "case": {
            "case_id": case_id,
            "case_kind": "reviewed_public_customer_concentration_benchmark",
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
            "execution_id": RECIPE_ID,
            "producer": "prepare_customer_concentration_case.py",
            "producer_version": ENGINE_VERSION,
            "producer_sha256": file_sha256(producer_path),
            "mode": "deterministic_mechanical",
            "input_artifact_refs": sorted(
                (
                    "case_contract",
                    "exact_control_facts",
                    "exact_extracted_facts",
                )
            ),
            "output_artifact_refs": sorted(producer_output_refs),
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
                    "Preparation audit envelope v1 does not establish row- or "
                    "cell-level lineage."
                ],
            },
        },
        "statuses": {
            "validation": _status(
                failed_or_passed,
                "Deterministic replay verified the complete producer-owned "
                "output set and preserved its validation result.",
                artifact_refs=("exceptions", "reconciliation"),
                decision_refs=decision_ids,
            ),
            "preparation": _status(
                failed_or_passed,
                "The registered customer-concentration recipe was replayed and "
                "its exact success or diagnostic-only failure outputs were preserved.",
                artifact_refs=preparation_artifacts,
                lineage_refs=(
                    (artifact_lineage_ids["customer_concentration_summary"],)
                    if passed
                    else ()
                ),
            ),
            "reconciliation": _status(
                failed_or_passed,
                "All required case-owned checks and exception rows are preserved.",
                artifact_refs=("exceptions", "reconciliation"),
                source_refs=source_ids,
                decision_refs=decision_ids,
            ),
            "semantic": _status(
                "not_assessed",
                "The adapter preserves reviewed source and claim boundaries "
                "without deciding customer identity or economic meaning.",
                artifact_refs=(
                    "case_contract",
                    "exact_control_facts",
                    "exact_extracted_facts",
                ),
                decision_refs=decision_ids,
            ),
            "source": _status(
                "receipt_only",
                "The filing is represented by a declared remote receipt and a "
                "reviewed extraction; remote authenticity is not established.",
                source_refs=source_ids,
                decision_refs=("source_extraction_review",),
            ),
            "downstream": _status(
                "not_assessed",
                "Semantic compatibility, rendering, evidence sealing, and "
                "report readiness remain unassessed.",
                artifact_refs=downstream_artifacts,
            ),
            "publication": _status(
                "withheld",
                "The reviewed benchmark is audit evidence and is not approved "
                "for publication.",
                artifact_refs=publication_artifacts,
                decision_refs=("claim_boundary_review",),
            ),
        },
        "report_ready": False,
        "limitations": sorted(
            [
                {
                    "limitation_id": "01_remote_authenticity",
                    "scope": "source",
                    "statement": (
                        "The adapter validates a declared receipt and does not "
                        "fetch or authenticate current remote filing bytes."
                    ),
                },
                {
                    "limitation_id": "02_semantic_authority",
                    "scope": "semantic",
                    "statement": (
                        "Source selection, locators, anonymous-customer meaning, "
                        "and reviewer authority remain reviewed rather than "
                        "mechanically proven."
                    ),
                },
                {
                    "limitation_id": "03_rounded_revenue_shares",
                    "scope": "numeric",
                    "statement": (
                        "Whole-percentage revenue shares do not support exact "
                        "customer revenue dollars."
                    ),
                },
                {
                    "limitation_id": "04_hhi_boundary",
                    "scope": "numeric",
                    "statement": (
                        "Reported-share squared contributions are neither full "
                        "HHI nor a guaranteed HHI lower bound."
                    ),
                },
                {
                    "limitation_id": "05_2023_ar_coverage",
                    "scope": "case",
                    "statement": (
                        "2023 accounts-receivable coverage is explicitly "
                        "unavailable because the frozen control set has no 2023 "
                        "total accounts-receivable denominator."
                    ),
                },
                {
                    "limitation_id": "06_row_lineage",
                    "scope": "lineage",
                    "statement": (
                        "Aggregate manifest references do not establish "
                        "source-document cell lineage."
                    ),
                },
                {
                    "limitation_id": "07_downstream_readiness",
                    "scope": "downstream",
                    "statement": (
                        "Passing preparation does not establish semantic, "
                        "reporting, or publication readiness."
                    ),
                },
            ],
            key=lambda item: item["limitation_id"],
        ),
    }
    return validate_audit_envelope(envelope, root=clara_root)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the customer-concentration audit adapter."""

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
        envelope = build_customer_concentration_audit_envelope(
            clara_root=args.clara_root,
            case_path=args.case,
            prepared_output_dir=args.prepared_output_dir,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, envelope)
    except (ContractValidationError, KeyError, OSError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info(
        "Customer-concentration audit envelope: %s", envelope["case"]["case_id"]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
