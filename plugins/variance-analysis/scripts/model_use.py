#!/usr/bin/env python3
"""Seal and extract purpose-bound post-mapping context for Variance Analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from vera_assurance import AssuranceContractError, load_client_engagement_context_file

SCHEMA_VERSION = "vera.model_use_manifest.v1"
REQUEST_SCHEMA_VERSION = "vera.model_use_request.v1"
MANIFEST_NAME = "model_use_manifest.json"
REQUEST_DIR_NAME = "model_drilldowns"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ModelUseError(ValueError):
    """Raised when a model-use manifest or drilldown request is invalid."""


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot(path: Path) -> dict[str, Any]:
    resolved = Path(path).resolve(strict=True)
    digest = hashlib.sha256()
    byte_count = 0
    with resolved.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            byte_count += len(block)
            digest.update(block)
    return {"byte_count": byte_count, "sha256": digest.hexdigest()}


def _mapped_columns(recipe: Mapping[str, Any]) -> list[str]:
    mappings = recipe.get("mappings")
    if not isinstance(mappings, Mapping):
        raise ModelUseError("Variance recipe mappings must be an object")
    names: list[str] = []
    for key in (
        "period_column",
        "amount_column",
        "units_column",
        "discount_column",
        "cogs_column",
        "date_column",
    ):
        value = mappings.get(key)
        if isinstance(value, str) and value:
            names.append(value)
    for key in ("dimensions", "calculation_grain"):
        values = mappings.get(key)
        if isinstance(values, list):
            names.extend(str(value) for value in values if str(value))
    return list(dict.fromkeys(names))


def write_model_use_manifest(
    *,
    input_path: Path,
    output_dir: Path,
    recipe: Mapping[str, Any],
    recipe_path: Path,
    source_population_rows: int,
    in_scope_rows: int,
    default_artifact_paths: Sequence[Path],
) -> Path:
    """Write a hash-bound post-mapping model-use manifest."""

    output_dir = Path(output_dir).resolve()
    recipe_snapshot = _snapshot(recipe_path)
    source_columns = _source_columns(input_path)
    mapped_columns = _mapped_columns(recipe)
    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for artifact_path in default_artifact_paths:
        path = Path(artifact_path).resolve()
        if not path.is_file() or path.name in {MANIFEST_NAME, "variance_audit.json"}:
            continue
        try:
            relative = path.relative_to(output_dir).as_posix()
        except ValueError as exc:
            raise ModelUseError("default model artifact is outside the run output") from exc
        if relative in seen or path.suffix.lower() not in {".csv", ".json", ".md", ".xlsx"}:
            continue
        seen.add(relative)
        artifacts.append(
            {
                "artifact_id": path.stem,
                "path": relative,
                **_snapshot(path),
                "purpose": "mapped_result_context_or_lineage",
            }
        )
    content: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": "variance-analysis",
        "phase": "post_semantic_mapping",
        "source_population": {
            "processing_scope": "complete_reviewed_in_scope_population",
            "source_input_rows": int(source_population_rows),
            "in_scope_rows": int(in_scope_rows),
            "source_snapshot": _snapshot(input_path),
            "source_column_count": len(source_columns),
        },
        "semantic_boundary": {
            "status": "reviewed_recipe_mapping_and_filters",
            "recipe_snapshot": recipe_snapshot,
            "mapped_columns": mapped_columns,
            "unmapped_column_count": sum(
                column not in mapped_columns for column in source_columns
            ),
            "default_source_access": "mapped_results_and_contexts_first",
            "automatic_anonymization": False,
            "automatic_pseudonymization": False,
        },
        "default_model_use": {
            "artifacts": artifacts,
            "raw_source_rows_included": False,
        },
        "evidence_drilldown": {
            "mode": "explicit_exact_filter_over_in_scope_source",
            "request_schema_version": REQUEST_SCHEMA_VERSION,
            "receipt_directory": REQUEST_DIR_NAME,
            "requires": [
                "specific_professional_question",
                "at_least_one_exact_row_filter",
                "explicit_mapped_output_columns",
                "reason",
            ],
            "allowed_columns": mapped_columns,
            "match_behavior": "all_exact_matches_no_sampling",
        },
        "runtime_account_boundary": {
            "selected_by": "firm_or_user",
            "verified_by_vera": False,
            "per_case_record_required": False,
        },
    }
    manifest = {**content, "content_sha256": _canonical_json_sha256(content)}
    path = output_dir / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _source_columns(path: Path) -> list[str]:
    from variance_core import get_schema_and_column_names, read_table

    columns, _schema = get_schema_and_column_names(read_table(Path(path)))
    return columns


def validate_manifest(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelUseError("model-use manifest must be an object")
    manifest = dict(value)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ModelUseError("model-use manifest schema_version is invalid")
    if manifest.get("workflow_id") != "variance-analysis":
        raise ModelUseError("model-use manifest workflow_id is invalid")
    supplied = manifest.pop("content_sha256", None)
    if not isinstance(supplied, str) or not SHA256_RE.fullmatch(supplied):
        raise ModelUseError("model-use manifest content_sha256 is invalid")
    if _canonical_json_sha256(manifest) != supplied:
        raise ModelUseError("model-use manifest content_sha256 is stale")
    manifest["content_sha256"] = supplied
    return manifest


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _filters(values: Sequence[str]) -> list[tuple[str, str]]:
    filters: list[tuple[str, str]] = []
    for value in values:
        column, separator, expected = value.partition("=")
        column = column.strip()
        if not separator or not column:
            raise ModelUseError("each --where must use column=exact_value")
        filters.append((column, expected))
    return filters


def extract_source_rows(
    *,
    manifest_path: Path,
    input_path: Path,
    recipe_path: Path,
    reason: str,
    where: Sequence[str],
    columns: Sequence[str],
) -> dict[str, Any]:
    """Write all exact in-scope source matches for one bounded question."""

    from variance_core import prepare_period_comparison_buckets, read_table
    from modules.chart_harness import apply_recipe_cohorts, apply_recipe_filters

    manifest_path = Path(manifest_path).resolve()
    manifest = validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    input_path = Path(input_path).resolve(strict=True)
    if _snapshot(input_path) != manifest["source_population"]["source_snapshot"]:
        raise ModelUseError("Variance source no longer matches the sealed manifest")
    reason = reason.strip()
    if not reason or len(reason) > 1_000:
        raise ModelUseError("reason must contain 1 to 1000 characters")
    exact_filters = _filters(where)
    requested_columns = list(dict.fromkeys(item.strip() for item in columns if item.strip()))
    if not exact_filters:
        raise ModelUseError("at least one --where is required")
    if not requested_columns:
        raise ModelUseError("at least one --column is required")
    if len(exact_filters) > 20 or len(requested_columns) > 30:
        raise ModelUseError("drilldown request exceeds the supported selector bounds")
    allowed = set(manifest["evidence_drilldown"]["allowed_columns"])
    referenced = {*requested_columns, *(column for column, _value in exact_filters)}
    unknown = sorted(referenced - allowed)
    if unknown:
        raise ModelUseError(f"drilldown columns are not in the reviewed mapping: {unknown}")
    recipe = json.loads(Path(recipe_path).read_text(encoding="utf-8"))
    if not isinstance(recipe, dict):
        raise ModelUseError("used recipe must be an object")
    if _snapshot(recipe_path) != manifest["semantic_boundary"].get(
        "recipe_snapshot"
    ):
        raise ModelUseError("Variance recipe no longer matches the reviewed recipe")
    frame = read_table(input_path)
    source_rows = frame.height
    frame, recipe = prepare_period_comparison_buckets(frame, recipe)
    frame, _filter_audit = apply_recipe_filters(frame, recipe)
    frame, _cohort_audit = apply_recipe_cohorts(
        frame,
        recipe,
        period_column=str(recipe["mappings"]["period_column"]),
        value_column=str(recipe["mappings"]["amount_column"]),
        current_period=str(recipe["mappings"]["comparison_period"]),
        previous_period=str(recipe["mappings"]["baseline_period"]),
    )
    in_scope_rows = frame.height
    import polars as pl

    for column, expected in exact_filters:
        frame = frame.filter(pl.col(column).cast(pl.Utf8) == expected)
    matched = [
        {column: _json_safe(row[column]) for column in requested_columns}
        for row in frame.select(requested_columns).to_dicts()
    ]
    request = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "workflow_id": "variance-analysis",
        "manifest_sha256": manifest["content_sha256"],
        "reason": reason,
        "where": [{"column": column, "value": value} for column, value in exact_filters],
        "columns": requested_columns,
    }
    request_sha256 = _canonical_json_sha256(request)
    content = {
        **request,
        "request_sha256": request_sha256,
        "full_source_rows_scanned_locally": source_rows,
        "in_scope_rows_scanned_locally": in_scope_rows,
        "matched_row_count": len(matched),
        "match_behavior": "all_exact_matches_no_sampling",
        "rows": matched,
    }
    output = {**content, "content_sha256": _canonical_json_sha256(content)}
    request_dir = manifest_path.parent / REQUEST_DIR_NAME
    request_dir.mkdir(parents=True, exist_ok=True)
    output_path = request_dir / f"source_rows_{request_sha256[:24]}.json"
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
        "full_source_rows_scanned_locally": source_rows,
        "in_scope_rows_scanned_locally": in_scope_rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--where", action="append", default=[])
    parser.add_argument("--column", action="append", default=[])
    parser.add_argument("--client-engagement", type=Path)
    args = parser.parse_args(argv)
    try:
        from variance_core import is_vera_managed_host

        if is_vera_managed_host() and args.client_engagement is None:
            raise ModelUseError("Vera source drilldown requires --client-engagement")
        if args.client_engagement is not None:
            load_client_engagement_context_file(
                args.client_engagement,
                expected_workflow_id="variance-analysis",
                input_paths=[args.input, args.recipe, args.manifest],
                output_dir=args.manifest.parent,
            )
        result = extract_source_rows(
            manifest_path=args.manifest,
            input_path=args.input,
            recipe_path=args.recipe,
            reason=args.reason,
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
