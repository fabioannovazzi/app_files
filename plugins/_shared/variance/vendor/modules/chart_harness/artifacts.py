"""Common deterministic artifact plumbing for chart-family plugins."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from modules.utilities.helpers import get_schema_and_column_names
from modules.utilities.utils import get_row_count

__all__ = [
    "CSV_EXTENSIONS",
    "EXCEL_EXTENSIONS",
    "SCHEMA_VERSION",
    "artifact_kind",
    "build_manifest_artifacts",
    "frame_profile",
    "json_safe",
    "read_json_object",
    "read_table",
    "relative_path",
    "utc_now",
    "write_json",
    "write_prepared_data_manifest",
]

SCHEMA_VERSION = "1.0"
CSV_EXTENSIONS = {".csv", ".tsv", ".psv", ".txt"}
EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}


def utc_now() -> str:
    """Return the current UTC timestamp for audit metadata."""

    return datetime.now(UTC).isoformat()


def json_safe(value: Any) -> Any:
    """Return JSON-safe values for stable artifact files."""

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, (Path, datetime, date)):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, TypeError, ValueError):
            return str(value)
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write stable, UTF-8 JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json_object(path: Path | None) -> dict[str, Any] | None:
    """Read a JSON object from ``path`` when one is provided."""

    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _collect_csv_scan(path: Path, *, separator: str) -> pl.DataFrame:
    """Read delimited input through a lazy scan and collect once."""

    lf = pl.scan_csv(path, separator=separator, infer_schema_length=10000)
    try:
        return lf.collect(engine="streaming")
    except pl.exceptions.PolarsError:
        return lf.collect()


def read_table(path: Path) -> pl.DataFrame:
    """Read supported delimited or Excel tabular inputs into Polars."""

    suffix = path.suffix.lower()
    if suffix in CSV_EXTENSIONS:
        separator = {".tsv": "\t", ".psv": "|"}.get(suffix, ",")
        return _collect_csv_scan(path, separator=separator)
    if suffix in EXCEL_EXTENSIONS:
        return pl.read_excel(path)
    raise ValueError(
        f"Unsupported input file type '{suffix}'. Use CSV, TSV, PSV, XLSX, XLSM, or XLS."
    )


def relative_path(path: Path, base: Path) -> str:
    """Return a POSIX relative path when ``path`` is inside ``base``."""

    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def artifact_kind(path: Path) -> str:
    """Return the normalized singular artifact kind for a generated file."""

    suffix = path.suffix.lower()
    if suffix in {".png", ".html", ".htm"}:
        return "chart"
    if suffix in {".csv", ".xlsx", ".xlsm"}:
        return "table"
    if suffix == ".json":
        return "context"
    if suffix == ".md":
        return "brief"
    if suffix == ".docx":
        return "report"
    return "file"


def build_manifest_artifacts(
    artifact_paths: Iterable[str | Path],
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Build manifest artifact records from existing output paths."""

    records: list[dict[str, Any]] = []
    for artifact_path in artifact_paths:
        path = Path(artifact_path)
        if not path.exists() or not path.is_file():
            continue
        records.append(
            {
                "artifact_id": path.stem,
                "kind": artifact_kind(path),
                "path": relative_path(path, output_dir),
                "status": "written",
                "bytes": path.stat().st_size,
            }
        )
    return records


def frame_profile(frame: pl.DataFrame) -> dict[str, Any]:
    """Return row, column, and schema metadata for a prepared frame."""

    columns, schema = get_schema_and_column_names(frame)
    return {
        "row_count": get_row_count(frame),
        "column_count": frame.width,
        "columns": columns,
        "schema": {name: str(schema[name]) for name in columns},
    }


def write_prepared_data_manifest(
    *,
    output_dir: Path,
    plugin: str,
    chart_family: str,
    source_file: str | Path | None,
    prepared_path: Path,
    frame: pl.DataFrame,
    recipe: dict[str, Any],
    stage: str = "canonical",
    preparation_audit: dict[str, Any] | None = None,
) -> Path:
    """Write the shared prepared-data contract for one chart-family run.

    This is deterministic because it records mechanically verifiable metadata:
    the prepared file path, schema, row/column counts, mappings, options, and
    preparation audit. Business meaning remains with the reporting layer.
    """

    manifest_path = output_dir / "prepared_data_manifest.json"
    write_json(
        manifest_path,
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "producer": {
                "plugin": plugin,
                "plugin_role": "chart_family_plugin",
                "chart_family": chart_family,
            },
            "source_file": str(source_file) if source_file is not None else None,
            "prepared_data": {
                "stage": stage,
                "path": relative_path(prepared_path, output_dir),
                **frame_profile(frame),
            },
            "mappings": recipe.get("mappings") or {},
            "options": recipe.get("options") or {},
            "preparation_audit": preparation_audit or {},
            "interpretation_boundary": {
                "prepared_data_is_model_source": True,
                "deterministic_scope": (
                    "file paths, schema, counts, mappings, options, and "
                    "preparation audit"
                ),
                "semantic_business_interpretation_owner": "reporting_consumer",
            },
        },
    )
    return manifest_path
