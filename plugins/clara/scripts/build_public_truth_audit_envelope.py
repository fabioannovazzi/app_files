#!/usr/bin/env python3
"""Adapt one public-truth validation into the M3 audit-only envelope."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from preparation_contract_kernel import (
    AUDIT_ENVELOPE_SCHEMA,
    ContractValidationError,
    artifact_receipt,
    canonical_json_bytes,
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
from validate_public_truth_benchmark import validate_public_truth_case

__all__ = ["build_public_truth_audit_envelope", "main"]

LOGGER = logging.getLogger(__name__)
ADAPTER_ID = "public_truth_audit_adapter.v1"
ADAPTER_VERSION = "1.0.0"
PRODUCER_VERSION = "1.0.0"


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
                "publisher",
                "document_type",
                "published_date",
                "url",
                "byte_count",
                "sha256",
            }
        }
        receipt: dict[str, Any] = {
            "source_id": source["source_id"],
            "title": source["title"],
            "publisher": source["publisher"],
            "document_type": source["document_type"],
            "document_date": source["published_date"],
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


def _numeric_evidence(result: Mapping[str, Any]) -> list[dict[str, str]]:
    names = (
        "source_total",
        "computed_value",
        "target_value",
        "difference",
        "tolerance",
    )
    evidence: list[dict[str, str]] = []
    for name in names:
        if name not in result:
            continue
        value = parse_decimal(result[name], label=f"assertion.{name}")
        evidence.append(
            {
                "name": name,
                "value": decimal_text(value),
                "unit": str(result["unit"]),
            }
        )
    return sorted(evidence, key=lambda item: item["name"])


def _reconciliation_checks(
    report: Mapping[str, Any],
    *,
    source_ids: Sequence[str],
) -> list[dict[str, Any]]:
    counts = report["counts"]
    exact_set_failures = sum(
        int(counts[field])
        for field in ("missing", "unexpected", "mismatched", "duplicates", "errors")
    )
    checks: list[dict[str, Any]] = [
        {
            "check_id": "candidate_exact_set",
            "check_kind": "case_owned_exact_expected_set",
            "required": True,
            "status": "passed" if exact_set_failures == 0 else "failed",
            "references": reference_set(
                artifact_refs=(
                    "candidate_observations",
                    "expected_observations",
                    "validation_report",
                ),
                source_refs=source_ids,
                decision_refs=("availability_boundary",),
            ),
            "numeric_evidence": [],
            "details": {
                field: counts[field]
                for field in ("missing", "unexpected", "mismatched", "duplicates")
            },
        },
        {
            "check_id": "monthly_abstention",
            "check_kind": "case_owned_disclosure_abstention",
            "required": True,
            "status": report["abstention_result"]["status"],
            "references": reference_set(
                artifact_refs=("candidate_observations", "validation_report"),
                source_refs=source_ids,
                decision_refs=("availability_boundary",),
            ),
            "numeric_evidence": [],
            "details": report["abstention_result"],
        },
    ]
    for result in report["assertion_results"]:
        checks.append(
            {
                "check_id": result["assertion_id"],
                "check_kind": f"case_owned_{result['kind']}",
                "required": True,
                "status": result["status"],
                "references": reference_set(
                    artifact_refs=(
                        "candidate_observations",
                        "validation_report",
                    ),
                    source_refs=source_ids,
                ),
                "numeric_evidence": _numeric_evidence(result),
                "details": {
                    key: value
                    for key, value in result.items()
                    if key
                    not in {
                        "assertion_id",
                        "status",
                        "unit",
                        "source_total",
                        "computed_value",
                        "target_value",
                        "difference",
                        "tolerance",
                    }
                },
            }
        )
    return sorted(checks, key=lambda item: str(item["check_id"]))


def _reconciliation_errors(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for position, raw_error in enumerate(report["errors"], start=1):
        if isinstance(raw_error, Mapping):
            code = str(raw_error.get("code", "validation_error"))
            message = str(raw_error.get("message", raw_error))
            details: Any = dict(raw_error)
        else:
            code = "validation_error"
            message = str(raw_error)
            details = {"raw": str(raw_error)}
        errors.append(
            {
                "error_id": f"error_{position:03d}",
                "code": code,
                "message": message,
                "references": reference_set(
                    artifact_refs=("validation_report",),
                ),
                "details": details,
            }
        )
    return errors


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


def build_public_truth_audit_envelope(
    *,
    clara_root: Path,
    benchmark_path: Path,
    candidate_path: Path,
    validation_report_path: Path,
) -> dict[str, Any]:
    """Return a validated audit view without changing the M1 artifacts."""

    clara_root = clara_root.resolve()
    benchmark = strict_json_load(benchmark_path)
    report = strict_json_load(validation_report_path)
    case_id = str(benchmark["case_id"])
    if report["case_id"] != case_id:
        raise ContractValidationError("validation report case_id does not match")
    if report["schema_version"] != "clara.public_truth_validation.v1":
        raise ContractValidationError("unexpected public-truth report schema")
    replayed_report = validate_public_truth_case(benchmark_path, candidate_path)
    if canonical_json_bytes(report) != canonical_json_bytes(replayed_report):
        raise ContractValidationError(
            "validation report does not match deterministic replay"
        )

    case_root = benchmark_path.resolve().parent
    truth_path = case_root / str(benchmark["files"]["truth"]["path"])
    expected_path = case_root / str(benchmark["files"]["expected"]["path"])
    adapter_path = Path(__file__).resolve()
    producer_path = adapter_path.with_name("validate_public_truth_benchmark.py")
    kernel_path = adapter_path.with_name("preparation_contract_kernel.py")
    schema_path = (
        clara_root / "contracts" / ("preparation_audit_envelope.v1.schema.json")
    )
    artifacts = sorted(
        [
            _artifact(
                clara_root,
                adapter_path,
                artifact_id="audit_adapter",
                role="audit_adapter",
                media_type="text/x-python",
            ),
            _artifact(
                clara_root,
                schema_path,
                artifact_id="audit_schema",
                role="audit_schema",
                media_type="application/schema+json",
            ),
            _artifact(
                clara_root,
                benchmark_path,
                artifact_id="benchmark_contract",
                role="case_contract",
                media_type="application/json",
            ),
            _artifact(
                clara_root,
                candidate_path,
                artifact_id="candidate_observations",
                role="prepared_candidate",
                media_type="text/csv",
            ),
            _artifact(
                clara_root,
                expected_path,
                artifact_id="expected_observations",
                role="expected_evidence",
                media_type="text/csv",
            ),
            _artifact(
                clara_root,
                producer_path,
                artifact_id="public_truth_validator",
                role="producer",
                media_type="text/x-python",
            ),
            _artifact(
                clara_root,
                kernel_path,
                artifact_id="preparation_contract_kernel",
                role="audit_kernel",
                media_type="text/x-python",
            ),
            _artifact(
                clara_root,
                truth_path,
                artifact_id="truth_observations",
                role="reviewed_truth",
                media_type="text/csv",
            ),
            _artifact(
                clara_root,
                validation_report_path,
                artifact_id="validation_report",
                role="reconciliation",
                media_type="application/json",
            ),
        ],
        key=lambda item: str(item["artifact_id"]),
    )
    sources = _source_receipts(benchmark["sources"])
    source_ids = [str(source["source_id"]) for source in sources]
    boundary = benchmark["reviewed_boundary"]
    decisions = [
        reviewed_decision_receipt(
            decision_id="availability_boundary",
            decision_kind="case_owned_disclosure_boundary",
            status=str(boundary["status"]),
            version=f"{case_id}.availability.v1",
            reviewed_on=str(boundary["reviewed_on"]),
            reviewer=str(boundary["judgement_owner"]),
            basis=str(boundary["statement"]),
            content=boundary,
            evidence_refs=reference_set(
                artifact_refs=(
                    "benchmark_contract",
                    "expected_observations",
                ),
                source_refs=source_ids,
            ),
        )
    ]
    checks = _reconciliation_checks(report, source_ids=source_ids)
    errors = _reconciliation_errors(report)
    numeric_constraints = {
        "candidate_numeric_contract": benchmark["candidate_contract"][
            "numeric_contract"
        ],
        "comparison_policy": (
            "Exact Decimal comparison using only the case-owned assertion "
            "and tolerance contracts."
        ),
        "assertion_policy_review_status": "not_established_by_fixture",
    }
    lineage_id = "01_validation_report_artifact"
    passed = report["status"] == "passed"
    envelope: dict[str, Any] = {
        "schema_version": AUDIT_ENVELOPE_SCHEMA,
        "case": {
            "case_id": case_id,
            "case_kind": "public_truth_benchmark",
            "source_schema_version": benchmark["schema_version"],
            "case_artifact_ref": "benchmark_contract",
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
            "execution_id": "public_truth_validation",
            "producer": "validate_public_truth_benchmark.py",
            "producer_version": PRODUCER_VERSION,
            "producer_sha256": file_sha256(producer_path),
            "mode": "deterministic_mechanical",
            "input_artifact_refs": sorted(
                {
                    "benchmark_contract",
                    "candidate_observations",
                    "expected_observations",
                    "truth_observations",
                }
            ),
            "output_artifact_refs": ["validation_report"],
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
            "errors": errors,
        },
        "lineage": {
            "artifact": {
                "declared": True,
                "records": [
                    {
                        "lineage_id": lineage_id,
                        "artifact_ref": "validation_report",
                        "references": reference_set(
                            artifact_refs=(
                                "benchmark_contract",
                                "candidate_observations",
                                "expected_observations",
                                "audit_schema",
                                "preparation_contract_kernel",
                                "public_truth_validator",
                                "truth_observations",
                            ),
                            source_refs=source_ids,
                            decision_refs=("availability_boundary",),
                        ),
                        "details": {
                            "scope": "artifact_receipt_closure",
                            "fact_source_locators_preserved_in": (
                                "candidate_observations"
                            ),
                        },
                    }
                ],
                "limitations": [],
            },
            "aggregate": {
                "declared": False,
                "records": [],
                "limitations": [
                    "The public-truth benchmark does not claim aggregate lineage."
                ],
            },
            "row": {
                "declared": False,
                "records": [],
                "limitations": [
                    "Fact source locators are preserved, but no output-row or "
                    "cell derivation graph is claimed."
                ],
            },
        },
        "statuses": {
            "validation": _status(
                "passed" if passed else "failed",
                "Deterministic replay checked the frozen candidate against the "
                "current benchmark; only the disclosure boundary carries an "
                "explicit review status.",
                artifact_refs=("validation_report",),
                lineage_refs=(lineage_id,),
            ),
            "preparation": _status(
                "not_assessed",
                "M1 validates a prepared candidate; it does not execute upstream preparation.",
                artifact_refs=("candidate_observations", "validation_report"),
            ),
            "reconciliation": _status(
                "passed" if passed else "failed",
                "Required exact-set, abstention, and assertion checks were "
                "replayed; separate approval of the assertion and tolerance "
                "policy is not established.",
                artifact_refs=("validation_report",),
                decision_refs=("availability_boundary",),
            ),
            "semantic": _status(
                "not_assessed",
                "The adapter preserves the reviewed disclosure boundary without "
                "judging its correctness or reviewer authority.",
                artifact_refs=("benchmark_contract",),
                decision_refs=("availability_boundary",),
            ),
            "source": _status(
                "receipt_only",
                "Remote source bytes are not packaged; declared receipts are pinned.",
                source_refs=source_ids,
            ),
            "downstream": _status(
                "not_assessed",
                "Rendering, semantic compatibility, and report evidence are outside M1.",
                artifact_refs=("validation_report",),
            ),
            "publication": _status(
                "withheld",
                "A public-truth benchmark pass is not publication approval.",
                artifact_refs=("validation_report",),
            ),
        },
        "report_ready": False,
        "limitations": sorted(
            [
                {
                    "limitation_id": "01_remote_authenticity",
                    "scope": "source",
                    "statement": (
                        "The adapter validates declared receipts and does not "
                        "refetch or authenticate current remote bytes."
                    ),
                },
                {
                    "limitation_id": "02_preparation_not_assessed",
                    "scope": "preparation",
                    "statement": (
                        "The upstream process that produced the candidate is "
                        "outside this benchmark."
                    ),
                },
                {
                    "limitation_id": "03_semantic_correctness",
                    "scope": "semantic",
                    "statement": (
                        "Source relevance, metric meaning, and the disclosure "
                        "boundary remain reviewed judgement; the fixture does "
                        "not establish separate authorization of its assertion "
                        "or tolerance policy."
                    ),
                },
                {
                    "limitation_id": "04_row_lineage",
                    "scope": "lineage",
                    "statement": "No row- or cell-level derivation lineage is claimed.",
                },
                {
                    "limitation_id": "05_downstream_readiness",
                    "scope": "downstream",
                    "statement": (
                        "Semantic compatibility, rendering, evidence sealing, "
                        "and report readiness are not assessed."
                    ),
                },
            ],
            key=lambda item: item["limitation_id"],
        ),
    }
    return validate_audit_envelope(envelope, root=clara_root)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the public-truth audit adapter."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("validation_report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--clara-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        envelope = build_public_truth_audit_envelope(
            clara_root=args.clara_root,
            benchmark_path=args.benchmark,
            candidate_path=args.candidate,
            validation_report_path=args.validation_report,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, envelope)
    except (ContractValidationError, KeyError, OSError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Public-truth audit envelope: %s", envelope["case"]["case_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
