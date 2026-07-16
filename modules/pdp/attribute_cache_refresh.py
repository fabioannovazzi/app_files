from __future__ import annotations

"""Refresh canonical PDP attribute cache files from mapped postfill outputs."""

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Sequence

import polars as pl

from modules.pdp.attribute_mapping_paths import get_attribute_mapping_dir
from modules.pdp.attribute_mapping_scope import normalize_retailer_scope

__all__ = ["refresh_pdp_attribute_cache_from_postfill"]

LOGGER = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ATTRIBUTE_CACHE_ROOT = APP_ROOT / "data" / "pdp" / "pdp_attribute_cache"
DEFAULT_POSTFILL_CACHE_DIR = get_attribute_mapping_dir() / "postfill_attribute_cache"
DEFAULT_RETAILER_FILTER_EVIDENCE_ROOT = (
    APP_ROOT / "data" / "pdp" / "retailer_filter_evidence"
)

_PLACEHOLDER_VALUES = {
    "",
    "n/a",
    "na",
    "none",
    "not in taxonomy",
    "null",
    "unknown",
}


def _read_parquet_if_exists(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _meaningful_expr(column: str) -> pl.Expr:
    text = pl.col(column).cast(pl.Utf8, strict=False).str.strip_chars()
    lowered = text.str.to_lowercase()
    return (
        pl.col(column).is_not_null()
        & lowered.is_in(sorted(_PLACEHOLDER_VALUES)).not_()
        & lowered.str.starts_with("not in taxonomy").not_()
    )


def _coalesce_legacy_column(
    df: pl.DataFrame,
    *,
    legacy_column: str,
    canonical_column: str,
) -> pl.DataFrame:
    if df.is_empty() or legacy_column not in df.columns:
        return df
    if canonical_column in df.columns:
        df = df.with_columns(
            pl.when(_meaningful_expr(canonical_column))
            .then(pl.col(canonical_column))
            .otherwise(pl.col(legacy_column))
            .alias(canonical_column)
        )
    else:
        df = df.with_columns(pl.col(legacy_column).alias(canonical_column))
    return df.drop(legacy_column)


def _canonicalize_form_columns(df: pl.DataFrame) -> pl.DataFrame:
    df = _coalesce_legacy_column(
        df,
        legacy_column="format",
        canonical_column="form",
    )
    df = _coalesce_legacy_column(
        df,
        legacy_column="format_children",
        canonical_column="form_children",
    )
    return df


def _retailer_filter(retailer: str) -> pl.Expr:
    return (
        pl.col("retailer")
        .cast(pl.Utf8, strict=False)
        .str.strip_chars()
        .str.to_lowercase()
        == retailer
    )


def _retailer_slice(df: pl.DataFrame, retailer: str) -> pl.DataFrame:
    if df.is_empty() or "retailer" not in df.columns:
        return pl.DataFrame()
    return df.filter(_retailer_filter(retailer))


def _merge_with_base_delta(
    preferred: pl.DataFrame,
    fallback: pl.DataFrame,
    *,
    key_columns: Sequence[str],
) -> pl.DataFrame:
    if preferred.is_empty():
        return fallback
    if fallback.is_empty():
        return preferred
    if any(column not in preferred.columns for column in key_columns) or any(
        column not in fallback.columns for column in key_columns
    ):
        return preferred

    key_aliases = [f"__refresh_key_{index}" for index, _ in enumerate(key_columns)]

    def _with_keys(frame: pl.DataFrame) -> pl.DataFrame:
        return frame.with_columns(
            [
                pl.col(column)
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .str.strip_chars()
                .alias(alias)
                for alias, column in zip(key_aliases, key_columns)
            ]
        )

    preferred_keys = _with_keys(preferred).select(key_aliases).unique()
    fallback_delta = (
        _with_keys(fallback)
        .join(preferred_keys, on=key_aliases, how="anti")
        .drop(key_aliases)
    )
    if fallback_delta.is_empty():
        return preferred
    return pl.concat([preferred, fallback_delta], how="diagonal_relaxed")


def _combined_frame(parents: pl.DataFrame, variants: pl.DataFrame) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    if not parents.is_empty():
        frames.append(
            parents.with_columns(
                pl.lit("parent").alias("record_type"),
                pl.col("parent_product_id").alias("product"),
                pl.lit("").alias("variant"),
            )
        )
    if not variants.is_empty():
        frames.append(
            variants.with_columns(
                pl.lit("variant").alias("record_type"),
                pl.col("parent_product_id").alias("product"),
                pl.col("variant_id").alias("variant"),
            )
        )
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _column_token(column_name: str) -> str:
    return "_".join(str(column_name or "").strip().lower().replace("/", " ").split())


def _load_retailer_filter_observations(
    evidence_root: Path,
    retailer: str,
) -> pl.DataFrame:
    path = evidence_root / retailer / "filter_observations.parquet"
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_parquet(path)
    except (OSError, pl.exceptions.PolarsError):
        LOGGER.exception("Failed to read retailer filter evidence from %s", path)
        return pl.DataFrame()


def _aggregate_retailer_filter_overrides(observations: pl.DataFrame) -> pl.DataFrame:
    required = {
        "retailer",
        "parent_product_id",
        "category_key",
        "filter_family",
        "filter_value",
    }
    if observations.is_empty() or any(
        column not in observations.columns for column in required
    ):
        return pl.DataFrame()

    filtered = observations.with_columns(
        [
            pl.col("retailer")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("retailer"),
            pl.col("parent_product_id")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .alias("parent_product_id"),
            pl.col("category_key")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_lowercase()
            .str.replace_all("-", "_")
            .alias("category_key"),
            pl.col("filter_family")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("filter_family"),
            pl.col("filter_value")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .alias("filter_value"),
        ]
    ).filter(
        (pl.col("retailer") != "")
        & (pl.col("parent_product_id") != "")
        & (pl.col("category_key") != "")
        & (pl.col("filter_family") != "")
        & _meaningful_expr("filter_value")
    )
    if filtered.is_empty():
        return pl.DataFrame()

    grouped = filtered.group_by(
        ["retailer", "parent_product_id", "category_key", "filter_family"]
    ).agg(pl.col("filter_value").unique().sort().str.join(" | ").alias("filter_value"))
    if grouped.is_empty():
        return pl.DataFrame()

    return grouped.pivot(
        values="filter_value",
        index=["retailer", "parent_product_id", "category_key"],
        on="filter_family",
        aggregate_function="first",
    )


def _apply_retailer_filter_overrides(
    frame: pl.DataFrame,
    overrides: pl.DataFrame,
    *,
    retailer: str,
) -> pl.DataFrame:
    if frame.is_empty() or overrides.is_empty():
        return frame
    required = {"retailer", "parent_product_id", "category_key"}
    if any(column not in frame.columns for column in required):
        return frame
    if any(column not in overrides.columns for column in required):
        return frame

    normalized = frame.with_columns(
        [
            pl.col("retailer")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("__filter_retailer"),
            pl.col("parent_product_id")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .alias("__filter_parent_product_id"),
            pl.col("category_key")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_lowercase()
            .str.replace_all("-", "_")
            .alias("__filter_category_key"),
        ]
    )
    override_columns = [
        column
        for column in overrides.columns
        if column not in {"retailer", "parent_product_id", "category_key"}
    ]
    if not override_columns:
        return frame

    renamed_overrides = overrides.rename(
        {
            "retailer": "__filter_retailer",
            "parent_product_id": "__filter_parent_product_id",
            "category_key": "__filter_category_key",
            **{
                column: f"__filter_override_{_column_token(column)}"
                for column in override_columns
            },
        }
    )
    joined = normalized.join(
        renamed_overrides,
        on=[
            "__filter_retailer",
            "__filter_parent_product_id",
            "__filter_category_key",
        ],
        how="left",
    )

    frame_columns = set(joined.columns)
    retailer_scope = pl.col("__filter_retailer") == retailer
    for attribute in override_columns:
        token = _column_token(attribute)
        override_column = f"__filter_override_{token}"
        if override_column not in frame_columns:
            continue
        original_expr = (
            pl.col(attribute).cast(pl.Utf8, strict=False)
            if attribute in frame_columns
            else pl.lit(None, dtype=pl.Utf8)
        )
        our_column = f"our_{token}"
        retailer_column = f"{retailer}_filter_{token}"
        source_column = f"{token}_authority_source"
        override_has_value = retailer_scope & _meaningful_expr(override_column)
        existing_our_expr = (
            pl.col(our_column).cast(pl.Utf8, strict=False)
            if our_column in frame_columns
            else pl.lit(None, dtype=pl.Utf8)
        )
        existing_source_expr = (
            pl.col(source_column).cast(pl.Utf8, strict=False)
            if source_column in frame_columns
            else pl.lit(None, dtype=pl.Utf8)
        )
        joined = joined.with_columns(
            [
                pl.when(override_has_value)
                .then(original_expr)
                .otherwise(existing_our_expr)
                .alias(our_column),
                pl.when(override_has_value)
                .then(pl.col(override_column).cast(pl.Utf8, strict=False))
                .otherwise(pl.lit(None, dtype=pl.Utf8))
                .alias(retailer_column),
                pl.when(override_has_value)
                .then(pl.col(override_column).cast(pl.Utf8, strict=False))
                .otherwise(original_expr)
                .alias(attribute),
                pl.when(override_has_value)
                .then(pl.lit(f"{retailer}_filter"))
                .otherwise(existing_source_expr)
                .alias(source_column),
            ]
        )
        frame_columns.update({attribute, our_column, retailer_column, source_column})

    drop_columns = [
        column for column in joined.columns if column.startswith("__filter_")
    ]
    return joined.drop(drop_columns)


def _load_metadata(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _target_retailers(
    *,
    retailers: Sequence[str] | str | None,
    parents: pl.DataFrame,
) -> tuple[str, ...]:
    scoped = normalize_retailer_scope(retailers)
    if scoped:
        return scoped
    if parents.is_empty() or "retailer" not in parents.columns:
        return tuple()
    values = (
        parents.select(
            pl.col("retailer")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("retailer")
        )
        .drop_nulls()
        .unique()
        .sort("retailer")
        .get_column("retailer")
        .to_list()
    )
    return tuple(value for value in values if value)


def refresh_pdp_attribute_cache_from_postfill(
    retailers: Sequence[str] | str | None = None,
    *,
    postfill_cache_dir: Path | None = None,
    attribute_cache_root: Path | None = None,
    retailer_filter_evidence_root: Path | None = None,
) -> list[Path]:
    """Materialize mapped postfill outputs into retailer-scoped PDP cache files."""

    postfill_dir = postfill_cache_dir or DEFAULT_POSTFILL_CACHE_DIR
    cache_root = attribute_cache_root or DEFAULT_ATTRIBUTE_CACHE_ROOT
    filter_evidence_root = (
        retailer_filter_evidence_root or DEFAULT_RETAILER_FILTER_EVIDENCE_ROOT
    )

    postfill_parents = _canonicalize_form_columns(
        _read_parquet_if_exists(postfill_dir / "parents.parquet")
    )
    postfill_variants = _canonicalize_form_columns(
        _read_parquet_if_exists(postfill_dir / "variants.parquet")
    )
    postfill_parents_all = _canonicalize_form_columns(
        _read_parquet_if_exists(postfill_dir / "parents_all.parquet")
    )
    if postfill_parents.is_empty() and postfill_variants.is_empty():
        LOGGER.info("Postfill attribute cache not found at %s", postfill_dir)
        return []
    if postfill_parents_all.is_empty():
        postfill_parents_all = postfill_parents

    target_retailers = _target_retailers(retailers=retailers, parents=postfill_parents)
    if not target_retailers:
        LOGGER.info("No retailers available for PDP attribute cache refresh.")
        return []

    written: list[Path] = []
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    for retailer in target_retailers:
        target_dir = cache_root / retailer
        target_dir.mkdir(parents=True, exist_ok=True)
        filter_overrides = _aggregate_retailer_filter_overrides(
            _load_retailer_filter_observations(filter_evidence_root, retailer)
        )

        base_parents = _canonicalize_form_columns(
            _read_parquet_if_exists(target_dir / "parents.parquet")
        )
        base_variants = _canonicalize_form_columns(
            _read_parquet_if_exists(target_dir / "variants.parquet")
        )
        base_parents_all = _canonicalize_form_columns(
            _read_parquet_if_exists(target_dir / "parents_all.parquet")
        )

        parents = _merge_with_base_delta(
            _retailer_slice(postfill_parents, retailer),
            _retailer_slice(base_parents, retailer),
            key_columns=("retailer", "parent_product_id", "category_key"),
        )
        variants = _merge_with_base_delta(
            _retailer_slice(postfill_variants, retailer),
            _retailer_slice(base_variants, retailer),
            key_columns=("retailer", "variant_id", "category_key"),
        )
        parents_all = _merge_with_base_delta(
            _retailer_slice(postfill_parents_all, retailer),
            _retailer_slice(base_parents_all, retailer),
            key_columns=("retailer", "parent_product_id", "category_key"),
        )
        if parents.is_empty() and variants.is_empty():
            LOGGER.info(
                "Skipping PDP attribute cache refresh for %s; no mapped rows.",
                retailer,
            )
            continue

        parents = _apply_retailer_filter_overrides(
            parents,
            filter_overrides,
            retailer=retailer,
        )
        parents_all = _apply_retailer_filter_overrides(
            parents_all,
            filter_overrides,
            retailer=retailer,
        )
        combined = _combined_frame(parents, variants)

        outputs = {
            "parents.parquet": parents,
            "variants.parquet": variants,
            "parents_all.parquet": (
                parents_all if not parents_all.is_empty() else parents
            ),
            "combined.parquet": combined,
        }
        for filename, frame in outputs.items():
            path = target_dir / filename
            frame.write_parquet(path)
            written.append(path)

        existing_metadata = _load_metadata(target_dir / "metadata.json")
        existing_metadata.update(
            {
                "generated_at": generated_at,
                "source": "postfill_attribute_cache",
            }
        )
        metadata_path = target_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(existing_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written.append(metadata_path)

    LOGGER.info(
        "Refreshed PDP attribute cache from postfill for retailers=%s files=%s",
        ",".join(target_retailers),
        len(written),
    )
    return written
