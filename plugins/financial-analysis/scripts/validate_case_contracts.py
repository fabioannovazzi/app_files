#!/usr/bin/env python3
"""Validate one complete Vera financial-analysis case contract stack."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = ["FinancialAnalysisCaseError", "main", "validate_case_contracts"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _activate_assurance() -> None:
    """Add the installed or source-tree assurance root to the import path."""

    candidates = (
        PLUGIN_ROOT / "vendor" / "modules",
        PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
    )
    for candidate in candidates:
        if (candidate / "vera_financial_analysis" / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    raise RuntimeError("Vera assurance module is unavailable.")


_activate_assurance()

from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)
from vera_financial_analysis import (  # noqa: E402
    FinancialAnalysisContractError,
    canonical_json_sha256,
    validate_analysis_pack_request,
    validate_crosswalk_manifest,
    validate_data_package_manifest,
    validate_dataset_contract,
    validate_prepared_evidence_manifest,
    validate_reconciliation_result,
    validate_relationship_contract,
)


class FinancialAnalysisCaseError(ValueError):
    """Raised when individually valid contracts do not close as a case."""


def _unique_by(
    values: Sequence[Mapping[str, Any]],
    key: str,
    *,
    label: str,
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for value in values:
        identity = value[key]
        if identity in indexed:
            raise FinancialAnalysisCaseError(f"duplicate {label}: {identity}")
        indexed[identity] = value
    return indexed


def _require_equal(
    actual: object,
    expected: object,
    *,
    label: str,
) -> None:
    if actual != expected:
        raise FinancialAnalysisCaseError(
            f"{label} does not close; expected={expected!r}, actual={actual!r}"
        )


def _require_refs(
    refs: Sequence[str],
    available: Mapping[str, object],
    *,
    label: str,
) -> None:
    missing = sorted(set(refs) - set(available))
    if missing:
        raise FinancialAnalysisCaseError(f"{label} has unknown references: {missing}")


def validate_case_contracts(
    *,
    package: Mapping[str, Any],
    datasets: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
    crosswalks: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    prepared_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate contract schemas and exact reference closure for one case."""

    validated_package = validate_data_package_manifest(package)
    validated_datasets = [validate_dataset_contract(item) for item in datasets]
    validated_relationships = [
        validate_relationship_contract(item) for item in relationships
    ]
    validated_crosswalks = [validate_crosswalk_manifest(item) for item in crosswalks]
    validated_request = validate_analysis_pack_request(request)
    validated_reconciliation = validate_reconciliation_result(reconciliation)
    validated_prepared = validate_prepared_evidence_manifest(prepared_manifest)

    dataset_index = _unique_by(
        validated_datasets,
        "dataset_contract_id",
        label="dataset contract id",
    )
    relationship_index = _unique_by(
        validated_relationships,
        "relationship_id",
        label="relationship id",
    )
    crosswalk_index = _unique_by(
        validated_crosswalks,
        "crosswalk_id",
        label="crosswalk id",
    )

    package_dataset_refs = [
        source["dataset_contract_ref"] for source in validated_package["sources"]
    ]
    _require_refs(package_dataset_refs, dataset_index, label="data package")
    for source in validated_package["sources"]:
        _require_equal(
            source["snapshot_id"],
            validated_package["snapshot_id"],
            label=f"source {source['source_id']} snapshot",
        )
    request_dataset_refs = validated_request["dataset_refs"]
    request_relationship_refs = validated_request["relationship_refs"]
    request_crosswalk_refs = validated_request["crosswalk_refs"]
    _require_refs(request_dataset_refs, dataset_index, label="analysis request")
    _require_refs(
        request_relationship_refs,
        relationship_index,
        label="analysis request",
    )
    _require_refs(
        request_crosswalk_refs,
        crosswalk_index,
        label="analysis request",
    )

    package_artifact_refs = {
        source["artifact_ref"] for source in validated_package["sources"]
    }
    for dataset in validated_datasets:
        missing_artifacts = sorted(
            set(dataset["source_artifact_refs"]) - package_artifact_refs
        )
        if missing_artifacts:
            raise FinancialAnalysisCaseError(
                f"dataset {dataset['dataset_contract_id']} references source "
                f"artifacts outside the package: {missing_artifacts}"
            )
    for relationship in validated_relationships:
        _require_refs(
            [
                relationship["left_dataset_ref"],
                relationship["right_dataset_ref"],
            ],
            dataset_index,
            label=f"relationship {relationship['relationship_id']}",
        )
        crosswalk_ref = relationship["crosswalk_ref"]
        left_dataset = dataset_index[relationship["left_dataset_ref"]]
        right_dataset = dataset_index[relationship["right_dataset_ref"]]
        left_fields = {field["name"] for field in left_dataset["fields"]}
        right_fields = {field["name"] for field in right_dataset["fields"]}
        if not set(relationship["left_keys"]) <= left_fields:
            raise FinancialAnalysisCaseError(
                f"relationship {relationship['relationship_id']} has unknown left keys"
            )
        if not set(relationship["right_keys"]) <= right_fields:
            raise FinancialAnalysisCaseError(
                f"relationship {relationship['relationship_id']} has unknown right keys"
            )
        if (
            relationship["left_dataset_ref"] not in request_dataset_refs
            or relationship["right_dataset_ref"] not in request_dataset_refs
        ):
            raise FinancialAnalysisCaseError(
                f"relationship {relationship['relationship_id']} uses a dataset "
                "outside the analysis request"
            )
        if crosswalk_ref is not None:
            _require_refs(
                [crosswalk_ref],
                crosswalk_index,
                label=f"relationship {relationship['relationship_id']}",
            )
    for crosswalk in validated_crosswalks:
        _require_refs(
            [
                crosswalk["source_dataset_ref"],
                crosswalk["target_dataset_ref"],
            ],
            dataset_index,
            label=f"crosswalk {crosswalk['crosswalk_id']}",
        )
        if crosswalk["artifact_ref"] not in package_artifact_refs:
            raise FinancialAnalysisCaseError(
                f"crosswalk {crosswalk['crosswalk_id']} artifact is outside the package"
            )
        source_dataset = dataset_index[crosswalk["source_dataset_ref"]]
        target_dataset = dataset_index[crosswalk["target_dataset_ref"]]
        source_fields = {field["name"] for field in source_dataset["fields"]}
        target_fields = {field["name"] for field in target_dataset["fields"]}
        if not set(crosswalk["source_key_fields"]) <= source_fields:
            raise FinancialAnalysisCaseError(
                f"crosswalk {crosswalk['crosswalk_id']} has unknown source keys"
            )
        if not set(crosswalk["target_key_fields"]) <= target_fields:
            raise FinancialAnalysisCaseError(
                f"crosswalk {crosswalk['crosswalk_id']} has unknown target keys"
            )
        if (
            crosswalk["source_dataset_ref"] not in request_dataset_refs
            or crosswalk["target_dataset_ref"] not in request_dataset_refs
        ):
            raise FinancialAnalysisCaseError(
                f"crosswalk {crosswalk['crosswalk_id']} uses a dataset outside "
                "the analysis request"
            )
        source_receipt = next(
            source
            for source in validated_package["sources"]
            if source["artifact_ref"] == crosswalk["artifact_ref"]
        )
        _require_equal(
            crosswalk["artifact_sha256"],
            source_receipt["sha256"],
            label=f"crosswalk {crosswalk['crosswalk_id']} source digest",
        )
        _require_equal(
            crosswalk["byte_count"],
            source_receipt["byte_count"],
            label=f"crosswalk {crosswalk['crosswalk_id']} source byte count",
        )

    for relationship in validated_relationships:
        crosswalk_ref = relationship["crosswalk_ref"]
        if crosswalk_ref is None:
            continue
        crosswalk = crosswalk_index[crosswalk_ref]
        _require_equal(
            crosswalk["source_dataset_ref"],
            relationship["left_dataset_ref"],
            label=f"relationship {relationship['relationship_id']} crosswalk source",
        )
        _require_equal(
            crosswalk["target_dataset_ref"],
            relationship["right_dataset_ref"],
            label=f"relationship {relationship['relationship_id']} crosswalk target",
        )
        _require_equal(
            crosswalk["source_key_fields"],
            relationship["left_keys"],
            label=f"relationship {relationship['relationship_id']} crosswalk source keys",
        )
        _require_equal(
            crosswalk["target_key_fields"],
            relationship["right_keys"],
            label=f"relationship {relationship['relationship_id']} crosswalk target keys",
        )

    _require_equal(
        validated_reconciliation["request_ref"],
        validated_request["request_id"],
        label="reconciliation request reference",
    )
    _require_equal(
        validated_prepared["request_ref"],
        validated_request["request_id"],
        label="prepared request reference",
    )
    _require_equal(
        validated_prepared["package_ref"],
        validated_package["package_id"],
        label="prepared package reference",
    )
    _require_equal(
        validated_prepared["reconciliation_ref"],
        validated_reconciliation["reconciliation_id"],
        label="prepared reconciliation reference",
    )
    _require_equal(
        validated_prepared["dataset_contract_refs"],
        request_dataset_refs,
        label="prepared dataset references",
    )
    _require_equal(
        validated_prepared["relationship_contract_refs"],
        request_relationship_refs,
        label="prepared relationship references",
    )
    _require_equal(
        validated_prepared["crosswalk_refs"],
        request_crosswalk_refs,
        label="prepared crosswalk references",
    )
    _require_equal(
        validated_prepared["input_artifact_refs"],
        sorted(package_artifact_refs),
        label="prepared input artifact references",
    )
    _require_equal(
        validated_prepared["recipe"]["pack_id"],
        validated_request["pack_id"],
        label="prepared pack id",
    )
    _require_equal(
        validated_prepared["recipe"]["version"],
        validated_request["recipe_version"],
        label="prepared recipe version",
    )
    _require_equal(
        validated_prepared["recipe"]["parameters_sha256"],
        canonical_json_sha256(validated_request["parameters"]),
        label="prepared parameter digest",
    )
    _require_equal(
        sorted({output["role"] for output in validated_prepared["output_artifacts"]}),
        sorted(validated_request["requested_outputs"]),
        label="prepared output roles",
    )
    _require_equal(
        validated_prepared["replay"]["output_set_sha256"],
        canonical_json_sha256(validated_prepared["output_artifacts"]),
        label="prepared replay output-set digest",
    )
    if (
        validated_prepared["preparation_status"] == "passed"
        and validated_reconciliation["status"] != "passed"
    ):
        raise FinancialAnalysisCaseError(
            "passed preparation requires a passed reconciliation"
        )
    if (
        validated_prepared["preparation_status"] == "qualified"
        and validated_reconciliation["status"] == "failed"
    ):
        raise FinancialAnalysisCaseError(
            "qualified preparation cannot rely on a failed reconciliation"
        )

    known_evidence_refs = {
        *package_artifact_refs,
        *dataset_index,
        *relationship_index,
        *crosswalk_index,
    }
    for evidence_item in [
        *validated_reconciliation["checks"],
        *validated_reconciliation["exceptions"],
    ]:
        missing_evidence = sorted(
            set(evidence_item["evidence_refs"]) - known_evidence_refs
        )
        if missing_evidence:
            raise FinancialAnalysisCaseError(
                "reconciliation evidence has unknown references: " f"{missing_evidence}"
            )

    contract_digests = {
        "data_package": validated_package["content_sha256"],
        "datasets": sorted(item["content_sha256"] for item in validated_datasets),
        "relationships": sorted(
            item["content_sha256"] for item in validated_relationships
        ),
        "crosswalks": sorted(item["content_sha256"] for item in validated_crosswalks),
        "request": validated_request["content_sha256"],
        "reconciliation": validated_reconciliation["content_sha256"],
        "prepared_manifest": validated_prepared["content_sha256"],
    }
    audit_content = {
        "schema_version": "vera.financial_analysis_contract_audit.v2",
        "status": "passed",
        "pack_id": validated_request["pack_id"],
        "recipe_version": validated_request["recipe_version"],
        "request_ref": validated_request["request_id"],
        "package_ref": validated_package["package_id"],
        "reconciliation_status": validated_reconciliation["status"],
        "preparation_status": validated_prepared["preparation_status"],
        "counts": {
            "datasets": len(validated_datasets),
            "relationships": len(validated_relationships),
            "crosswalks": len(validated_crosswalks),
            "input_artifacts": len(package_artifact_refs),
            "output_artifacts": len(validated_prepared["output_artifacts"]),
        },
        "contract_digests": contract_digests,
        "report_ready": False,
        "limitations": [
            "Contract closure does not establish accounting meaning or professional approval.",
            "Prepared evidence is not a report-ready conclusion.",
        ],
    }
    return {
        **audit_content,
        "content_sha256": canonical_json_sha256(audit_content),
    }


def _read_json(
    path: Path,
    validator: Callable[[object], dict[str, Any]] | None = None,
) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise FinancialAnalysisCaseError(f"{path} must contain a JSON object")
    return validator(value) if validator is not None else value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, validate the case, and write a sealed audit."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, action="append", required=True)
    parser.add_argument("--relationship", type=Path, action="append", default=[])
    parser.add_argument("--crosswalk", type=Path, action="append", default=[])
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        input_paths = [
            args.package,
            *args.dataset,
            *args.relationship,
            *args.crosswalk,
            args.request,
            args.reconciliation,
            args.prepared_manifest,
        ]
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="financial-analysis",
            input_paths=input_paths,
            output_dir=args.output,
        )
        audit = validate_case_contracts(
            package=_read_json(args.package),
            datasets=[_read_json(path) for path in args.dataset],
            relationships=[_read_json(path) for path in args.relationship],
            crosswalks=[_read_json(path) for path in args.crosswalk],
            request=_read_json(args.request),
            reconciliation=_read_json(args.reconciliation),
            prepared_manifest=_read_json(args.prepared_manifest),
        )
        _write_json(args.output, audit)
    except (
        AssuranceContractError,
        FinancialAnalysisCaseError,
        FinancialAnalysisContractError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        LOGGER.error("FAILED: %s", exc)
        return 1
    LOGGER.info("PASSED: %s", args.output)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
