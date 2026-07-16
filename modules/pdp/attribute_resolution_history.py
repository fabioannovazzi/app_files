from __future__ import annotations

import datetime as dt
import os
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

import polars as pl

from modules.pdp.review_constants import DEFAULT_PDP_STORE_PATH, enforce_default_pdp_store_path
from modules.pdp.store import PDPStore

DEFAULT_RESOLUTION_LEDGER_DIR: Path | None = None
DEFAULT_RESOLUTION_CONSENSUS_PATH: Path | None = None

_PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "n/a",
        "na",
        "none",
        "unknown",
        "not stated",
        "n/a (not stated)",
        "not in taxonomy",
    }
)
_RECENT_WINDOW_RUNS = 4
_MIN_SURE_SUPPORT_RUNS = 3
_EXCLUDED_RUN_IDS_ENV = "ATTRIBUTE_RESOLUTION_EXCLUDED_RUN_IDS"

_LEDGER_SCHEMA: dict[str, pl.DataType] = {
    "run_id": pl.Utf8,
    "recorded_at": pl.Utf8,
    "step": pl.Utf8,
    "source": pl.Utf8,
    "decision_rule": pl.Utf8,
    "row_type": pl.Utf8,
    "retailer": pl.Utf8,
    "parent_product_id": pl.Utf8,
    "variant_id": pl.Utf8,
    "canonical_id": pl.Utf8,
    "category_key": pl.Utf8,
    "attribute_id": pl.Utf8,
    "value": pl.Utf8,
    "confidence": pl.Float64,
    "evidence_url": pl.Utf8,
}
_LEDGER_COLUMNS = list(_LEDGER_SCHEMA.keys())

_CONSENSUS_SCHEMA: dict[str, pl.DataType] = {
    "row_type": pl.Utf8,
    "retailer": pl.Utf8,
    "parent_product_id": pl.Utf8,
    "variant_id": pl.Utf8,
    "canonical_id": pl.Utf8,
    "category_key": pl.Utf8,
    "attribute_id": pl.Utf8,
    "consensus_value": pl.Utf8,
    "support_runs": pl.Int64,
    "total_runs": pl.Int64,
    "agreement_rate": pl.Float64,
    "step_count": pl.Int64,
    "supporting_steps": pl.List(pl.Utf8),
    "certainty_class": pl.Utf8,
    "max_confidence": pl.Float64,
    "last_seen_at": pl.Utf8,
    "last_recorded_at": pl.Utf8,
}
_CONSENSUS_COLUMNS = list(_CONSENSUS_SCHEMA.keys())

_CONSENSUS_GROUP_KEYS = [
    "row_type",
    "retailer",
    "parent_product_id",
    "variant_id",
    "canonical_id",
    "category_key",
    "attribute_id",
]


def _empty_ledger_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=_LEDGER_SCHEMA)


def _empty_consensus_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=_CONSENSUS_SCHEMA)


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_float(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _resolve_excluded_run_ids(excluded_run_ids: Sequence[str] | None) -> set[str]:
    raw_values: list[str] = []
    if excluded_run_ids:
        raw_values.extend(str(item) for item in excluded_run_ids)
    env_value = os.environ.get(_EXCLUDED_RUN_IDS_ENV, "")
    if env_value.strip():
        raw_values.extend(env_value.replace("\n", ",").split(","))

    resolved: set[str] = set()
    for raw in raw_values:
        text = str(raw).strip()
        if text:
            resolved.add(text)
    return resolved


def _exclude_selected_runs(
    df: pl.DataFrame, excluded_run_ids: set[str]
) -> pl.DataFrame:
    if df.is_empty() or not excluded_run_ids:
        return df
    run_id_expr = pl.col("run_id").cast(pl.Utf8, strict=False).fill_null("")
    return df.filter(~run_id_expr.is_in(list(excluded_run_ids)))


def _coerce_ledger_frame(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return _empty_ledger_frame()
    missing = [col for col in _LEDGER_COLUMNS if col not in df.columns]
    if missing:
        df = df.with_columns([pl.lit(None).alias(col) for col in missing])
    cast_exprs = [
        pl.col(column).cast(dtype, strict=False).alias(column)
        for column, dtype in _LEDGER_SCHEMA.items()
    ]
    return df.select(_LEDGER_COLUMNS).with_columns(cast_exprs)


def _coerce_consensus_frame(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return _empty_consensus_frame()
    missing = [col for col in _CONSENSUS_COLUMNS if col not in df.columns]
    if missing:
        df = df.with_columns([pl.lit(None).alias(col) for col in missing])
    cast_exprs = [
        pl.col(column).cast(dtype, strict=False).alias(column)
        for column, dtype in _CONSENSUS_SCHEMA.items()
    ]
    return df.select(_CONSENSUS_COLUMNS).with_columns(cast_exprs)


def build_run_id(prefix: str) -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_prefix = _normalize_text(prefix) or "attribute-resolution"
    return f"{safe_prefix}-{timestamp}-{uuid.uuid4().hex[:10]}"


def _store() -> PDPStore:
    return PDPStore(enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH))


def append_resolution_ledger_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    ledger_dir: Path | None = DEFAULT_RESOLUTION_LEDGER_DIR,
) -> Path | None:
    if not rows:
        return None

    normalized_rows: list[dict[str, Any]] = []
    fallback_run_id = build_run_id("attribute-resolution")
    for raw_row in rows:
        run_id = _normalize_text(raw_row.get("run_id")) or fallback_run_id
        normalized_rows.append(
            {
                "run_id": run_id,
                "recorded_at": _normalize_text(raw_row.get("recorded_at")),
                "step": _normalize_text(raw_row.get("step")),
                "source": _normalize_text(raw_row.get("source")),
                "decision_rule": _normalize_text(raw_row.get("decision_rule")),
                "row_type": _normalize_text(raw_row.get("row_type")),
                "retailer": _normalize_text(raw_row.get("retailer")),
                "parent_product_id": _normalize_text(raw_row.get("parent_product_id")),
                "variant_id": _normalize_text(raw_row.get("variant_id")),
                "canonical_id": _normalize_text(raw_row.get("canonical_id")),
                "category_key": _normalize_text(raw_row.get("category_key")),
                "attribute_id": _normalize_text(raw_row.get("attribute_id")),
                "value": _normalize_text(raw_row.get("value")),
                "confidence": _normalize_float(raw_row.get("confidence")),
                "evidence_url": _normalize_text(raw_row.get("evidence_url")),
            }
        )

    frame = _coerce_ledger_frame(
        pl.from_dicts(
            normalized_rows,
            schema=_LEDGER_SCHEMA,
            strict=False,
            infer_schema_length=None,
        )
    )
    if frame.is_empty():
        return None

    if ledger_dir is None:
        _store().append_attribute_resolution_ledger_rows(frame.to_dicts())
        return None

    ledger_dir.mkdir(parents=True, exist_ok=True)
    chunk_name = (
        f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        f"_{uuid.uuid4().hex[:10]}.parquet"
    )
    chunk_path = ledger_dir / chunk_name
    frame.write_parquet(chunk_path)
    return chunk_path


def read_resolution_ledger(
    *,
    ledger_dir: Path | None = DEFAULT_RESOLUTION_LEDGER_DIR,
) -> pl.DataFrame:
    if ledger_dir is None:
        rows = _store().read_attribute_resolution_ledger_rows()
        if not rows:
            return _empty_ledger_frame()
        return _coerce_ledger_frame(
            pl.from_dicts(
                rows,
                schema=_LEDGER_SCHEMA,
                strict=False,
                infer_schema_length=None,
            )
        )

    if not ledger_dir.exists():
        return _empty_ledger_frame()
    chunk_paths = sorted(ledger_dir.glob("*.parquet"))
    if not chunk_paths:
        return _empty_ledger_frame()
    frames = [pl.read_parquet(path) for path in chunk_paths]
    merged = pl.concat(frames, how="diagonal_relaxed") if len(frames) > 1 else frames[0]
    return _coerce_ledger_frame(merged)


def read_resolution_consensus(
    *,
    output_path: Path | None = DEFAULT_RESOLUTION_CONSENSUS_PATH,
) -> pl.DataFrame:
    if output_path is None:
        rows = _store().read_attribute_resolution_consensus_rows()
        if not rows:
            return _empty_consensus_frame()
        return _coerce_consensus_frame(
            pl.from_dicts(
                rows,
                schema=_CONSENSUS_SCHEMA,
                strict=False,
                infer_schema_length=None,
            )
        )

    if not output_path.exists():
        return _empty_consensus_frame()
    try:
        frame = pl.read_parquet(output_path)
    except Exception:
        return _empty_consensus_frame()
    return _coerce_consensus_frame(frame)


def write_resolution_consensus(
    *,
    ledger_dir: Path | None = DEFAULT_RESOLUTION_LEDGER_DIR,
    output_path: Path | None = DEFAULT_RESOLUTION_CONSENSUS_PATH,
    excluded_run_ids: Sequence[str] | None = None,
) -> pl.DataFrame:
    ledger = read_resolution_ledger(ledger_dir=ledger_dir)
    if ledger.is_empty():
        empty = _empty_consensus_frame()
        if output_path is None:
            _store().write_attribute_resolution_consensus_rows([])
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            empty.write_parquet(output_path)
        return empty

    meaningful = ledger.with_columns(
        [
            *[
                pl.col(column).cast(pl.Utf8, strict=False).fill_null("").alias(column)
                for column in _CONSENSUS_GROUP_KEYS
            ],
            pl.col("value")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .alias("_value_norm"),
        ]
    ).filter(
        pl.col("_value_norm").is_not_null()
        & (pl.col("_value_norm") != "")
        & (~pl.col("_value_norm").str.to_lowercase().is_in(list(_PLACEHOLDER_VALUES)))
    )
    meaningful = _exclude_selected_runs(
        meaningful, _resolve_excluded_run_ids(excluded_run_ids)
    )

    if meaningful.is_empty():
        empty = _empty_consensus_frame()
        if output_path is None:
            _store().write_attribute_resolution_consensus_rows([])
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            empty.write_parquet(output_path)
        return empty

    latest_per_run = (
        meaningful.sort(
            [*_CONSENSUS_GROUP_KEYS, "run_id", "recorded_at", "step"],
            descending=[False] * len(_CONSENSUS_GROUP_KEYS) + [False, True, True],
        )
        .group_by([*_CONSENSUS_GROUP_KEYS, "run_id"], maintain_order=True)
        .agg(
            [
                pl.col("_value_norm").first().alias("_value_norm"),
                pl.col("recorded_at").first().alias("recorded_at"),
                pl.col("step").first().alias("step"),
                pl.col("confidence").max().alias("confidence"),
            ]
        )
    )

    recent_runs = (
        latest_per_run.sort(
            [*_CONSENSUS_GROUP_KEYS, "recorded_at"],
            descending=[False] * len(_CONSENSUS_GROUP_KEYS) + [True],
        )
        .group_by(_CONSENSUS_GROUP_KEYS, maintain_order=True)
        .agg(
            [
                pl.col("run_id").head(_RECENT_WINDOW_RUNS).alias("run_id"),
                pl.col("_value_norm").head(_RECENT_WINDOW_RUNS).alias("_value_norm"),
                pl.col("recorded_at").head(_RECENT_WINDOW_RUNS).alias("recorded_at"),
                pl.col("step").head(_RECENT_WINDOW_RUNS).alias("step"),
                pl.col("confidence").head(_RECENT_WINDOW_RUNS).alias("confidence"),
            ]
        )
        .explode(["run_id", "_value_norm", "recorded_at", "step", "confidence"])
    )

    value_support = recent_runs.group_by([*_CONSENSUS_GROUP_KEYS, "_value_norm"]).agg(
        [
            pl.col("run_id").n_unique().alias("support_runs"),
            pl.col("recorded_at").max().alias("last_seen_at"),
            pl.col("confidence").max().alias("max_confidence"),
            pl.col("step").drop_nulls().unique().sort().alias("supporting_steps"),
        ]
    )

    run_totals = recent_runs.group_by(_CONSENSUS_GROUP_KEYS).agg(
        [
            pl.col("run_id").n_unique().alias("total_runs"),
            pl.col("recorded_at").max().alias("last_recorded_at"),
        ]
    )

    ranked = value_support.join(
        run_totals, on=_CONSENSUS_GROUP_KEYS, how="left"
    ).with_columns(
        (
            pl.col("support_runs").cast(pl.Float64)
            / pl.col("total_runs").cast(pl.Float64)
        ).alias("agreement_rate")
    )

    sort_by = [
        *_CONSENSUS_GROUP_KEYS,
        "support_runs",
        "agreement_rate",
        "last_seen_at",
        "_value_norm",
    ]
    descending = [False] * len(_CONSENSUS_GROUP_KEYS) + [True, True, True, False]
    ranked = ranked.sort(sort_by, descending=descending)

    consensus = (
        ranked.group_by(_CONSENSUS_GROUP_KEYS, maintain_order=True)
        .agg(
            [
                pl.col("_value_norm").first().alias("consensus_value"),
                pl.col("support_runs").first().alias("support_runs"),
                pl.col("total_runs").first().alias("total_runs"),
                pl.col("agreement_rate").first().alias("agreement_rate"),
                pl.col("supporting_steps").first().alias("supporting_steps"),
                pl.col("max_confidence").first().alias("max_confidence"),
                pl.col("last_seen_at").first().alias("last_seen_at"),
                pl.col("last_recorded_at").first().alias("last_recorded_at"),
            ]
        )
        .with_columns(
            [
                pl.col("supporting_steps")
                .list.len()
                .cast(pl.Int64)
                .alias("step_count"),
                pl.when(pl.col("support_runs") >= _MIN_SURE_SUPPORT_RUNS)
                .then(pl.lit("sure"))
                .otherwise(pl.lit("uncertain"))
                .alias("certainty_class"),
            ]
        )
    )

    consensus = _coerce_consensus_frame(consensus)
    if output_path is None:
        _store().write_attribute_resolution_consensus_rows(consensus.to_dicts())
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        consensus.write_parquet(output_path)
    return consensus


__all__ = [
    "DEFAULT_RESOLUTION_CONSENSUS_PATH",
    "DEFAULT_RESOLUTION_LEDGER_DIR",
    "append_resolution_ledger_rows",
    "build_run_id",
    "read_resolution_consensus",
    "read_resolution_ledger",
    "write_resolution_consensus",
]
