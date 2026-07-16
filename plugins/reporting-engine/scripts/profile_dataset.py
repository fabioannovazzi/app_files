"""Profile a tabular dataset into chart-useful mechanical role candidates."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import polars as pl

__all__ = ["profile_dataset", "main"]

SAMPLE_LIMIT = 8
LOW_CARDINALITY_MAX = 30
IDENTIFIER_CARDINALITY_RATIO = 0.85
PERIOD_NAME_RE = re.compile(r"(date|month|week|year|period|quarter)", re.I)
IDENTIFIER_NAME_RE = re.compile(r"(^id$|_id$|sku|barcode|product_id|key)", re.I)
RATE_NAME_RE = re.compile(r"(rate|ratio|pct|percent|share|margin)", re.I)
COUNT_NAME_RE = re.compile(r"(count|qty|quantity|units|volume)", re.I)
VALUE_NAME_RE = re.compile(r"(sales|revenue|amount|value|price|cost|profit)", re.I)


def _read_frame(path: Path) -> pl.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pl.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pl.read_parquet(path)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pl.read_excel(path)
    raise ValueError(f"Unsupported dataset format: {path.suffix}")


def _sample_values(series: pl.Series) -> list[str]:
    values = series.drop_nulls().unique().head(SAMPLE_LIMIT).to_list()
    return [str(value) for value in values]


def _physical_type(dtype: pl.DataType) -> str:
    return str(dtype)


def _is_numeric(dtype: pl.DataType) -> bool:
    return dtype.is_numeric()


def _is_temporal(dtype: pl.DataType) -> bool:
    return dtype in {pl.Date, pl.Datetime, pl.Time}


def _cardinality_class(distinct_count: int, row_count: int) -> str:
    if distinct_count <= LOW_CARDINALITY_MAX:
        return "low"
    if row_count and distinct_count / row_count >= IDENTIFIER_CARDINALITY_RATIO:
        return "identifier_like"
    return "medium" if distinct_count <= 500 else "high"


def _metric_class(name: str, dtype: pl.DataType) -> str | None:
    if not _is_numeric(dtype):
        return None
    if RATE_NAME_RE.search(name):
        return "rate_or_share"
    if COUNT_NAME_RE.search(name):
        return "count"
    if VALUE_NAME_RE.search(name):
        return "additive_value"
    return "numeric_observation"


def _role_for_column(
    name: str,
    dtype: pl.DataType,
    *,
    distinct_count: int,
    row_count: int,
) -> tuple[str, str, list[str]]:
    reasons: list[str] = []
    if _is_temporal(dtype) or PERIOD_NAME_RE.search(name):
        reasons.append("temporal type or period-like name")
        return "period", "high" if _is_temporal(dtype) else "medium", reasons
    if _metric_class(name, dtype) is not None:
        reasons.append("numeric metric-compatible column")
        return "metric", "high", reasons
    if IDENTIFIER_NAME_RE.search(name) or (
        distinct_count > LOW_CARDINALITY_MAX
        and row_count
        and distinct_count / row_count >= IDENTIFIER_CARDINALITY_RATIO
    ):
        reasons.append("name or cardinality suggests identifier")
        return "identifier", "high", reasons
    reasons.append("categorical-compatible column")
    return (
        "dimension",
        "high" if distinct_count <= LOW_CARDINALITY_MAX else "medium",
        reasons,
    )


def _period_parseability(series: pl.Series, dtype: pl.DataType) -> dict[str, Any]:
    samples = _sample_values(series)
    if _is_temporal(dtype):
        return {
            "is_parseable": True,
            "parser": "native_temporal_dtype",
            "sample_count": len(samples),
            "parse_success_count": len(samples),
            "parse_success_ratio": 1.0 if samples else 0.0,
            "inferred_grain": "unknown",
        }
    parsed = 0
    for value in samples:
        try:
            pl.Series([value]).str.strptime(pl.Date, strict=False)
        except (pl.exceptions.PolarsError, TypeError, ValueError):
            continue
        parsed += 1
    return {
        "is_parseable": bool(samples) and parsed == len(samples),
        "parser": "string_date_probe",
        "sample_count": len(samples),
        "parse_success_count": parsed,
        "parse_success_ratio": parsed / len(samples) if samples else 0.0,
        "inferred_grain": "unknown",
    }


def profile_dataset(path: Path, *, dataset_id: str | None = None) -> dict[str, Any]:
    """Return a non-semantic dataset profile for chart compatibility checks."""

    frame = _read_frame(path)
    row_count = frame.height
    columns: dict[str, Any] = {}
    roles: dict[str, list[str]] = {
        "period": [],
        "metric": [],
        "dimension": [],
        "identifier": [],
    }
    metric_classes: dict[str, list[str]] = {}
    role_candidates: dict[str, list[str]] = {
        "period_axis": [],
        "comparison_metric": [],
        "dimension_member": [],
        "panel_dimension": [],
        "identifier": [],
    }
    for name, dtype in frame.schema.items():
        series = frame[name]
        null_count = series.null_count()
        distinct_count = series.n_unique()
        role, confidence, reasons = _role_for_column(
            name,
            dtype,
            distinct_count=distinct_count,
            row_count=row_count,
        )
        metric_class = _metric_class(name, dtype)
        columns[name] = {
            "physical_type": _physical_type(dtype),
            "null_count": null_count,
            "null_ratio": null_count / row_count if row_count else 0.0,
            "distinct_count": distinct_count,
            "sample_values": _sample_values(series),
            "period_parseability": _period_parseability(series, dtype),
            "role": role,
            "role_confidence": confidence,
            "cardinality_class": _cardinality_class(distinct_count, row_count),
            "inference_reasons": reasons,
        }
        roles[role].append(name)
        if role == "period":
            role_candidates["period_axis"].append(name)
        elif role == "metric":
            role_candidates["comparison_metric"].append(name)
            metric_classes.setdefault(metric_class or "numeric_observation", []).append(
                name
            )
        elif role == "dimension":
            role_candidates["dimension_member"].append(name)
            if distinct_count <= LOW_CARDINALITY_MAX:
                role_candidates["panel_dimension"].append(name)
        elif role == "identifier":
            role_candidates["identifier"].append(name)
    return {
        "schema_version": "0.2",
        "dataset_id": dataset_id or path.stem,
        "source": {
            "format": path.suffix.lower().lstrip("."),
            "path": str(path.resolve()),
        },
        "row_count": row_count,
        "column_count": frame.width,
        "columns": columns,
        "roles": roles,
        "metric_classes": metric_classes,
        "role_candidates": role_candidates,
        "selector_boundary": (
            "Mechanical dataset profile only. It does not decide whether an "
            "analysis makes business sense."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Write a dataset profile JSON file."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--dataset-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    profile = profile_dataset(args.dataset, dataset_id=args.dataset_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
