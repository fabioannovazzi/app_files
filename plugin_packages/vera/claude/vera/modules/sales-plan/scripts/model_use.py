#!/usr/bin/env python3
"""Seal and extract purpose-bound post-mapping context for Sales Plan."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent

for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from plan_contract_kernel import canonical_json_sha256, file_snapshot_beneath  # noqa: E402
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

SCHEMA_VERSION = "vera.model_use_manifest.v1"
REQUEST_SCHEMA_VERSION = "vera.model_use_request.v1"
MANIFEST_NAME = "model_use_manifest.json"
REQUEST_DIR_NAME = "model_drilldowns"
SCENARIO_NAME = "sales_plan_scenario.csv"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ModelUseError(ValueError):
    """Raised when a model-use manifest or drilldown request is invalid."""


def is_vera_managed_host() -> bool:
    root = PLUGIN_ROOT.resolve()
    host_manifest = root.parent.parent / ".codex-plugin" / "plugin.json"
    return (
        root.name == "sales-plan"
        and root.parent.name == "modules"
        and root.parent.parent.name == "vera"
    ) or (
        host_manifest.is_file()
        and json.loads(host_manifest.read_text(encoding="utf-8")).get("name")
        == "vera"
    )


def _snapshot(path: Path) -> dict[str, Any]:
    byte_count, sha256 = file_snapshot_beneath(path, root=path.parent)
    return {"byte_count": byte_count, "sha256": sha256}


def _case_mapping(case_path: Path) -> tuple[list[str], list[str]]:
    value = json.loads(Path(case_path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ModelUseError("Plan case must be an object")
    recipe = value.get("preparation_recipe")
    if not isinstance(recipe, Mapping):
        raise ModelUseError("Plan case preparation_recipe must be an object")
    dimensions = recipe.get("dimension_columns")
    metrics = recipe.get("metric_columns")
    if not isinstance(dimensions, list) or not isinstance(metrics, Mapping):
        raise ModelUseError("Plan case semantic mapping is invalid")
    selected = [str(item) for item in dimensions]
    selected.extend(str(item) for item in metrics.values())
    return [str(item) for item in dimensions], list(dict.fromkeys(selected))


def build_manifest(
    *,
    case_path: Path,
    case_sha256: str,
    source_byte_count: int,
    source_sha256: str,
    output_artifacts: Sequence[Mapping[str, Any]],
    result: Mapping[str, Any],
    status: str,
) -> dict[str, Any]:
    """Build the sealed post-assumption model-use contract."""

    dimensions, selected_columns = _case_mapping(case_path)
    artifacts = {
        str(item["path"]): {
            "artifact_id": str(item["artifact_ref"]),
            "path": str(item["path"]),
            "byte_count": int(item["byte_count"]),
            "sha256": str(item["sha256"]),
        }
        for item in output_artifacts
    }
    default_names = (
        "assumption_application_ledger.csv",
        "scenario_summary.csv",
        "reconciliation.json",
        "prepared_evidence_manifest.json",
    )
    default_artifacts = [
        {
            **artifacts[name],
            "purpose": (
                "assumption_lineage"
                if name == "assumption_application_ledger.csv"
                else "decision_summary_and_reconciliation"
            ),
        }
        for name in default_names
        if name in artifacts
    ]
    detailed = artifacts.get(SCENARIO_NAME)
    counts = result.get("counts") if isinstance(result.get("counts"), Mapping) else {}
    content: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": "sales-plan",
        "phase": "post_reviewed_assumption_application",
        "status": status,
        "source_population": {
            "processing_scope": "complete_reviewed_in_scope_population",
            "source_rows": int(counts.get("source_rows", 0)),
            "scenario_rows": int(counts.get("scenario_rows", 0)),
            "case_sha256": case_sha256,
            "actual_sales": {
                "byte_count": source_byte_count,
                "sha256": source_sha256,
                "selected_columns": selected_columns,
                "excluded_unmapped_columns": "rejected_by_exact_header_contract",
            },
        },
        "semantic_boundary": {
            "status": "reviewed_dimensions_metrics_periods_and_assumptions",
            "dimension_columns": dimensions,
            "default_source_access": "summary_lineage_and_reconciliation_first",
            "automatic_anonymization": False,
            "automatic_pseudonymization": False,
        },
        "default_model_use": {
            "artifacts": default_artifacts,
            "row_level_scenario_included": False,
            "raw_actual_sales_included": False,
        },
        "evidence_drilldown": {
            "mode": "explicit_exact_filter_over_prepared_scenario",
            "request_schema_version": REQUEST_SCHEMA_VERSION,
            "receipt_directory": REQUEST_DIR_NAME,
            "detailed_artifact": detailed,
            "requires": [
                "specific_professional_question",
                "at_least_one_exact_row_filter",
                "explicit_output_columns",
                "reason",
            ],
            "match_behavior": "all_exact_matches_no_sampling",
        },
        "runtime_account_boundary": {
            "selected_by": "firm_or_user",
            "verified_by_vera": False,
            "per_case_record_required": False,
        },
    }
    return {**content, "content_sha256": canonical_json_sha256(content)}


def validate_manifest(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelUseError("model-use manifest must be an object")
    manifest = dict(value)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ModelUseError("model-use manifest schema_version is invalid")
    if manifest.get("workflow_id") != "sales-plan":
        raise ModelUseError("model-use manifest workflow_id is invalid")
    supplied = manifest.pop("content_sha256", None)
    if not isinstance(supplied, str) or not SHA256_RE.fullmatch(supplied):
        raise ModelUseError("model-use manifest content_sha256 is invalid")
    if canonical_json_sha256(manifest) != supplied:
        raise ModelUseError("model-use manifest content_sha256 is stale")
    manifest["content_sha256"] = supplied
    return manifest


def write_manifest(output_boundary: Any, manifest: Mapping[str, Any]) -> None:
    validate_manifest(manifest)
    output_boundary.write_json_exclusive(MANIFEST_NAME, dict(manifest))


def _filters(values: Sequence[str]) -> list[tuple[str, str]]:
    filters: list[tuple[str, str]] = []
    for value in values:
        column, separator, expected = value.partition("=")
        column = column.strip()
        if not separator or not column:
            raise ModelUseError("each --where must use column=exact_value")
        filters.append((column, expected))
    return filters


def extract_scenario_rows(
    *,
    manifest_path: Path,
    reason: str,
    source_row_ids: Sequence[str],
    where: Sequence[str],
    columns: Sequence[str],
) -> dict[str, Any]:
    """Write all exact prepared-scenario matches for one bounded question."""

    manifest_path = Path(manifest_path).resolve()
    manifest = validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    reason = reason.strip()
    if not reason or len(reason) > 1_000:
        raise ModelUseError("reason must contain 1 to 1000 characters")
    requested_ids = sorted({item.strip() for item in source_row_ids if item.strip()})
    exact_filters = _filters(where)
    requested_columns = list(dict.fromkeys(item.strip() for item in columns if item.strip()))
    if not requested_ids and not exact_filters:
        raise ModelUseError("at least one --source-row-id or --where is required")
    if not requested_columns:
        raise ModelUseError("at least one --column is required")
    if len(requested_ids) > 500 or len(exact_filters) > 20 or len(requested_columns) > 30:
        raise ModelUseError("drilldown request exceeds the supported selector bounds")
    detailed = manifest.get("evidence_drilldown", {}).get("detailed_artifact")
    if not isinstance(detailed, Mapping):
        raise ModelUseError("prepared scenario is unavailable for this run")
    scenario_path = manifest_path.parent / str(detailed.get("path"))
    current = _snapshot(scenario_path)
    if current != {
        "byte_count": detailed.get("byte_count"),
        "sha256": detailed.get("sha256"),
    }:
        raise ModelUseError("prepared scenario no longer matches the sealed manifest")
    with scenario_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        requested_names = ["source_row_id", "scenario", *requested_columns]
        output_columns = list(dict.fromkeys(requested_names))
        referenced = {
            *output_columns,
            *(column for column, _value in exact_filters),
        }
        unknown = sorted(referenced - set(headers))
        if unknown:
            raise ModelUseError(f"unknown prepared scenario columns: {unknown}")
        matched: list[dict[str, str]] = []
        population_rows = 0
        requested_id_set = set(requested_ids)
        for row in reader:
            population_rows += 1
            if requested_id_set and row["source_row_id"] not in requested_id_set:
                continue
            if any(row[column] != expected for column, expected in exact_filters):
                continue
            matched.append({column: row[column] for column in output_columns})
    request = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "workflow_id": "sales-plan",
        "manifest_sha256": manifest["content_sha256"],
        "reason": reason,
        "source_row_ids": requested_ids,
        "where": [{"column": column, "value": value} for column, value in exact_filters],
        "columns": output_columns,
    }
    request_sha256 = canonical_json_sha256(request)
    content = {
        **request,
        "request_sha256": request_sha256,
        "full_population_rows_scanned_locally": population_rows,
        "matched_row_count": len(matched),
        "match_behavior": "all_exact_matches_no_sampling",
        "rows": matched,
    }
    output = {**content, "content_sha256": canonical_json_sha256(content)}
    request_dir = manifest_path.parent / REQUEST_DIR_NAME
    request_dir.mkdir(parents=True, exist_ok=True)
    output_path = request_dir / f"scenario_rows_{request_sha256[:24]}.json"
    rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output_path.exists() and output_path.read_text(encoding="utf-8") != rendered:
        raise ModelUseError("existing drilldown artifact does not match")
    if not output_path.exists():
        output_path.write_text(rendered, encoding="utf-8")
    return {
        "ok": True,
        "artifact_path": str(output_path),
        "request_sha256": request_sha256,
        "matched_row_count": len(matched),
        "full_population_rows_scanned_locally": population_rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--source-row-id", action="append", default=[])
    parser.add_argument("--where", action="append", default=[])
    parser.add_argument("--column", action="append", default=[])
    parser.add_argument("--client-engagement", type=Path)
    args = parser.parse_args(argv)
    try:
        if is_vera_managed_host() and args.client_engagement is None:
            raise ModelUseError("Vera scenario drilldown requires --client-engagement")
        if args.client_engagement is not None:
            manifest_path = args.manifest.resolve()
            manifest = validate_manifest(
                json.loads(manifest_path.read_text(encoding="utf-8"))
            )
            detailed = manifest.get("evidence_drilldown", {}).get(
                "detailed_artifact"
            )
            if not isinstance(detailed, Mapping):
                raise ModelUseError("prepared scenario is unavailable for this run")
            load_client_engagement_context_file(
                args.client_engagement,
                expected_workflow_id="sales-plan",
                input_paths=[
                    manifest_path,
                    manifest_path.parent / str(detailed["path"]),
                ],
                output_dir=manifest_path.parent,
            )
        result = extract_scenario_rows(
            manifest_path=args.manifest,
            reason=args.reason,
            source_row_ids=args.source_row_id,
            where=args.where,
            columns=args.column,
        )
    except (AssuranceContractError, ModelUseError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
