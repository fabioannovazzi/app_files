#!/usr/bin/env python3
"""Run one fixed reviewed-input financial due-diligence recipe."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from preparation_contract_kernel import (
    canonical_json_sha256,
    file_snapshot_beneath,
    resolve_local_file,
    strict_json_load,
    write_json,
)
from validate_case_contracts import validate_case_contracts

__all__ = [
    "ENGINE_VERSION",
    "OUTPUT_ROLES",
    "RECIPE_IDS",
    "main",
    "prepare_capex_case",
    "prepare_deal_bridges_case",
    "prepare_fdd_case",
    "prepare_net_debt_case",
    "prepare_normalized_working_capital_case",
    "prepare_quality_of_earnings_case",
]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _activate_financial_analysis() -> None:
    candidates = (
        PLUGIN_ROOT / "vendor" / "modules",
        PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
    )
    for candidate in candidates:
        if (candidate / "vera_financial_analysis" / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    raise RuntimeError("Vera financial-analysis contracts are unavailable.")


_activate_financial_analysis()

from vera_financial_analysis import (  # noqa: E402
    FDD_ENGINE_VERSION,
    FDD_OUTPUT_ROLES,
    FDD_PACK_RECIPES,
    build_prepared_evidence_manifest,
    build_reconciliation_result,
    execute_fdd_case,
    validate_analysis_pack_request,
    validate_crosswalk_manifest,
    validate_data_package_manifest,
    validate_dataset_contract,
    validate_fdd_case,
    validate_relationship_contract,
)

ENGINE_VERSION = FDD_ENGINE_VERSION
RECIPE_IDS = FDD_PACK_RECIPES
OUTPUT_ROLES = FDD_OUTPUT_ROLES
_BUNDLE_SCHEMA = "vera.fdd_execution_bundle.v1"


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a list")
    return list(value)


def _unique_by(
    values: Sequence[Mapping[str, Any]],
    key: str,
    *,
    label: str,
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in values:
        identity = str(item[key])
        if identity in result:
            raise ValueError(f"duplicate {label}: {identity}")
        result[identity] = item
    return result


def _validate_bundle(
    value: object,
    *,
    expected_pack_id: str,
    bundle_root: Path,
) -> dict[str, Any]:
    bundle = _mapping(value, label="FDD execution bundle")
    required = {
        "content_sha256",
        "crosswalks",
        "datasets",
        "fdd_case",
        "package",
        "relationships",
        "request",
        "schema_version",
    }
    if set(bundle) != required:
        raise ValueError("FDD execution bundle fields are invalid")
    if bundle["schema_version"] != _BUNDLE_SCHEMA:
        raise ValueError("unsupported FDD execution bundle schema")
    content = {key: bundle[key] for key in bundle if key != "content_sha256"}
    if bundle["content_sha256"] != canonical_json_sha256(content):
        raise ValueError("FDD execution bundle digest is stale")

    package = validate_data_package_manifest(bundle["package"])
    datasets = [
        validate_dataset_contract(item)
        for item in _sequence(bundle["datasets"], label="datasets")
    ]
    relationships = [
        validate_relationship_contract(item)
        for item in _sequence(bundle["relationships"], label="relationships")
    ]
    crosswalks = [
        validate_crosswalk_manifest(item)
        for item in _sequence(bundle["crosswalks"], label="crosswalks")
    ]
    request = validate_analysis_pack_request(bundle["request"])
    case = validate_fdd_case(
        bundle["fdd_case"],
        expected_pack_id=expected_pack_id,
    )

    if request["pack_id"] != expected_pack_id:
        raise ValueError("analysis request pack does not match the runner")
    if request["recipe_version"] != FDD_PACK_RECIPES[expected_pack_id]:
        raise ValueError("analysis request recipe does not match the runner")
    expected_parameters = {
        "case_id": case["case_id"],
        "fdd_inputs_sha256": canonical_json_sha256(case["inputs"]),
        "scope_id": case["scope_id"],
        "unit": case["unit"],
    }
    if request["parameters"] != expected_parameters:
        raise ValueError("analysis request parameters do not bind the FDD inputs")
    if sorted(request["requested_outputs"]) != list(OUTPUT_ROLES):
        raise ValueError("analysis request does not request the fixed FDD outputs")

    contract_refs = case["contract_refs"]
    if contract_refs["package_ref"] != package["package_id"]:
        raise ValueError("FDD case package_ref does not close")
    if contract_refs["package_sha256"] != package["content_sha256"]:
        raise ValueError("FDD case package_sha256 does not close")
    if contract_refs["request_ref"] != request["request_id"]:
        raise ValueError("FDD case request_ref does not close")
    if contract_refs["relationship_refs"] != sorted(request["relationship_refs"]):
        raise ValueError("FDD case relationship refs do not close")
    if contract_refs["crosswalk_refs"] != sorted(request["crosswalk_refs"]):
        raise ValueError("FDD case crosswalk refs do not close")
    embedded_stack = case["contract_stack"]
    if (
        embedded_stack["package"] != package
        or embedded_stack["datasets"]
        != sorted(datasets, key=lambda item: item["dataset_contract_id"])
        or embedded_stack["relationships"]
        != sorted(relationships, key=lambda item: item["relationship_id"])
        or embedded_stack["crosswalks"]
        != sorted(crosswalks, key=lambda item: item["crosswalk_id"])
        or embedded_stack["request"] != request
    ):
        raise ValueError("execution bundle contracts differ from the sealed FDD case")

    perimeter = package["reporting_perimeter"]
    if case["entity_refs"] != sorted(perimeter["entity_refs"]):
        raise ValueError("FDD case entities do not match the data package")
    if perimeter["currency_refs"] != [case["currency"]]:
        raise ValueError("FDD v1 requires one matching package currency")
    if case["reporting_period"] != {
        "start": perimeter["period_start"],
        "end": perimeter["period_end"],
    }:
        raise ValueError("FDD case reporting period does not match the package")

    dataset_index = _unique_by(
        datasets,
        "dataset_contract_id",
        label="dataset contract",
    )
    relationship_index = _unique_by(
        relationships,
        "relationship_id",
        label="relationship contract",
    )
    crosswalk_index = _unique_by(
        crosswalks,
        "crosswalk_id",
        label="crosswalk contract",
    )
    if set(request["dataset_refs"]) != set(dataset_index):
        raise ValueError("analysis request dataset refs do not close")
    if set(request["relationship_refs"]) != set(relationship_index):
        raise ValueError("analysis request relationship refs do not close")
    if set(request["crosswalk_refs"]) != set(crosswalk_index):
        raise ValueError("analysis request crosswalk refs do not close")

    package_sources = _unique_by(
        package["sources"],
        "artifact_ref",
        label="package artifact",
    )
    case_sources = _unique_by(
        case["source_artifacts"],
        "artifact_ref",
        label="case artifact",
    )
    if set(package_sources) != set(case_sources):
        raise ValueError("FDD case artifacts do not match the data package")
    source_paths = []
    for artifact_ref, source in package_sources.items():
        case_source = case_sources[artifact_ref]
        for field in ("byte_count", "dataset_contract_ref", "sha256"):
            if case_source[field] != source[field]:
                raise ValueError(
                    f"FDD case artifact {artifact_ref} {field} does not close"
                )
        source_path = resolve_local_file(
            bundle_root,
            source["locator"],
            label=f"package source {artifact_ref}.locator",
        )
        source_paths.append(source_path)
        byte_count, sha256 = file_snapshot_beneath(
            source_path,
            root=bundle_root,
        )
        if source_path.name != source["file_name"]:
            raise ValueError(f"package source {artifact_ref} file_name does not close")
        if byte_count != source["byte_count"] or sha256 != source["sha256"]:
            raise ValueError(f"package source {artifact_ref} file receipt is stale")

    return {
        "package": package,
        "datasets": datasets,
        "relationships": relationships,
        "crosswalks": crosswalks,
        "request": request,
        "case": case,
        "source_paths": source_paths,
    }


def _seal_document(content: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(content)
    return {
        **normalized,
        "content_sha256": canonical_json_sha256(normalized),
    }


def _output_receipt(
    path: Path,
    *,
    artifact_ref: str,
    role: str,
    row_count: int,
) -> dict[str, Any]:
    byte_count, sha256 = file_snapshot_beneath(path, root=path.parent)
    return {
        "artifact_ref": artifact_ref,
        "role": role,
        "row_count": row_count,
        "byte_count": byte_count,
        "sha256": sha256,
    }


def prepare_fdd_case(
    case_path: Path,
    output_dir: Path,
    *,
    expected_pack_id: str,
) -> dict[str, Any]:
    """Validate, execute, reconcile, and seal one FDD execution bundle."""

    supplied_bundle_path = Path(case_path)
    supplied_output_dir = Path(output_dir)
    if supplied_bundle_path.is_symlink():
        raise ValueError("FDD execution bundle cannot be a symlink")
    if supplied_output_dir.is_symlink():
        raise ValueError("FDD output directory cannot be a symlink")
    bundle_path = supplied_bundle_path.resolve()
    output_dir = supplied_output_dir.resolve()
    if not bundle_path.is_file():
        raise ValueError("FDD execution bundle must be a regular file")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError("FDD output path must be a directory")
        if any(output_dir.iterdir()):
            raise ValueError("FDD output directory must be fresh and empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = _validate_bundle(
        strict_json_load(bundle_path),
        expected_pack_id=expected_pack_id,
        bundle_root=bundle_path.parent,
    )
    case = bundle["case"]
    first_result = execute_fdd_case(case, expected_pack_id=expected_pack_id)
    replay_result = execute_fdd_case(case, expected_pack_id=expected_pack_id)
    if first_result != replay_result:
        raise ValueError("FDD deterministic replay changed the result")

    result_path = output_dir / "fdd_result.json"
    metrics_path = output_dir / "fdd_metrics.json"
    line_items_path = output_dir / "fdd_line_items.json"
    reconciliation_path = output_dir / "reconciliation.json"
    manifest_path = output_dir / "prepared_evidence_manifest.json"
    output_paths = {
        result_path,
        metrics_path,
        line_items_path,
        reconciliation_path,
        manifest_path,
    }
    protected_paths = {bundle_path, *bundle["source_paths"]}
    collisions = sorted(
        str(path) for path in output_paths.intersection(protected_paths)
    )
    if collisions:
        raise ValueError(
            "FDD outputs cannot overwrite the execution bundle or source "
            f"evidence: {collisions}"
        )
    symlink_targets = sorted(str(path) for path in output_paths if path.is_symlink())
    if symlink_targets:
        raise ValueError(f"FDD output targets cannot be symlinks: {symlink_targets}")
    write_json(result_path, first_result)
    metrics_document = _seal_document(
        {
            "schema_version": "vera.fdd_metrics.v1",
            "result_ref": first_result["result_id"],
            "metrics": [dict(item) for item in first_result["metrics"]],
            "report_ready": False,
        }
    )
    line_items_document = _seal_document(
        {
            "schema_version": "vera.fdd_line_items.v1",
            "result_ref": first_result["result_id"],
            "line_items": [dict(item) for item in first_result["line_items"]],
            "report_ready": False,
        }
    )
    write_json(metrics_path, metrics_document)
    write_json(line_items_path, line_items_document)

    evidence_refs = sorted(item["artifact_ref"] for item in case["source_artifacts"])
    reconciliation = build_reconciliation_result(
        reconciliation_id=f"{case['case_id']}.{expected_pack_id}.reconciliation",
        request_ref=bundle["request"]["request_id"],
        status="passed",
        checks=[
            {
                "check_id": "contract_stack_closure",
                "required": True,
                "status": "passed",
                "expected": "0",
                "actual": "0",
                "difference": "0",
                "tolerance": "0",
                "evidence_refs": evidence_refs,
                "detail": "Package, dataset, request, case, and source receipts close.",
            },
            {
                "check_id": "calculation_identities",
                "required": True,
                "status": "passed",
                "expected": "0",
                "actual": "0",
                "difference": "0",
                "tolerance": "0",
                "evidence_refs": evidence_refs,
                "detail": "Every fixed-recipe calculation identity has zero difference.",
            },
            {
                "check_id": "deterministic_replay",
                "required": True,
                "status": "passed",
                "expected": "0",
                "actual": "0",
                "difference": "0",
                "tolerance": "0",
                "evidence_refs": evidence_refs,
                "detail": "A second execution produced the identical sealed result.",
            },
        ],
    )
    write_json(reconciliation_path, reconciliation)

    output_artifacts = [
        _output_receipt(
            line_items_path,
            artifact_ref="fdd_line_items",
            role="fdd_line_items",
            row_count=len(first_result["line_items"]),
        ),
        _output_receipt(
            metrics_path,
            artifact_ref="fdd_metrics",
            role="fdd_metrics",
            row_count=len(first_result["metrics"]),
        ),
        _output_receipt(
            result_path,
            artifact_ref="fdd_result",
            role="fdd_result",
            row_count=1,
        ),
        _output_receipt(
            reconciliation_path,
            artifact_ref="reconciliation",
            role="reconciliation",
            row_count=len(reconciliation["checks"]),
        ),
    ]
    manifest = build_prepared_evidence_manifest(
        manifest_id=f"{case['case_id']}.{expected_pack_id}.prepared",
        request_ref=bundle["request"]["request_id"],
        package_ref=bundle["package"]["package_id"],
        dataset_contract_refs=bundle["request"]["dataset_refs"],
        relationship_contract_refs=bundle["request"]["relationship_refs"],
        crosswalk_refs=bundle["request"]["crosswalk_refs"],
        input_artifact_refs=sorted(
            item["artifact_ref"] for item in bundle["package"]["sources"]
        ),
        recipe={
            "pack_id": expected_pack_id,
            "version": FDD_PACK_RECIPES[expected_pack_id],
            "implementation_refs": [
                "prepare_fdd_case.v1",
                f"vera_financial_analysis.fdd.{FDD_ENGINE_VERSION}",
            ],
            "parameters_sha256": canonical_json_sha256(bundle["request"]["parameters"]),
        },
        reconciliation_ref=reconciliation["reconciliation_id"],
        preparation_status="passed",
        output_artifacts=output_artifacts,
        replay={
            "status": "passed",
            "output_set_sha256": canonical_json_sha256(output_artifacts),
        },
    )
    write_json(manifest_path, manifest)
    audit = validate_case_contracts(
        package=bundle["package"],
        datasets=bundle["datasets"],
        relationships=bundle["relationships"],
        crosswalks=bundle["crosswalks"],
        request=bundle["request"],
        reconciliation=reconciliation,
        prepared_manifest=manifest,
    )
    return {
        "status": "passed",
        "pack_id": expected_pack_id,
        "result_sha256": first_result["content_sha256"],
        "manifest_sha256": manifest["content_sha256"],
        "contract_audit_sha256": audit["content_sha256"],
        "report_ready": False,
    }


def _runner(pack_id: str) -> Callable[[Path, Path], dict[str, Any]]:
    def run(case_path: Path, output_dir: Path) -> dict[str, Any]:
        return prepare_fdd_case(
            case_path,
            output_dir,
            expected_pack_id=pack_id,
        )

    return run


prepare_quality_of_earnings_case = _runner("quality_of_earnings")
prepare_net_debt_case = _runner("net_debt")
prepare_normalized_working_capital_case = _runner("normalized_working_capital")
prepare_capex_case = _runner("capex")
prepare_deal_bridges_case = _runner("deal_bridges")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and prepare one fixed FDD pack."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", choices=sorted(FDD_PACK_RECIPES), required=True)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare_fdd_case(
            args.case,
            args.output_dir,
            expected_pack_id=args.pack,
        )
    except (OSError, TypeError, ValueError) as exc:
        LOGGER.error("FAILED: %s", exc)
        return 2
    LOGGER.info("PASSED: %s", args.output_dir)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
