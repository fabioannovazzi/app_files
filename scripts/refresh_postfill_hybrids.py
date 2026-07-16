from __future__ import annotations

"""Refresh deterministic hybrid flags in postfill attribute cache parquet files."""

import argparse
import logging
from pathlib import Path

import polars as pl

from modules.pdp.attribute_mapping_paths import get_attribute_mapping_dir
from modules.pdp.hybrid_overlay import annotate_market_hybrid_claims


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute deterministic hybrid overlay columns (also_*) inside "
            "postfill attribute cache parquet files."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print counts without writing parquet files.",
    )
    return parser.parse_args()


def _resolve_mapping_dir() -> Path:
    return get_attribute_mapping_dir()


def _load_required_frames(cache_dir: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    parents_path = cache_dir / "parents.parquet"
    variants_path = cache_dir / "variants.parquet"
    if not parents_path.is_file() or not variants_path.is_file():
        raise SystemExit(
            f"Missing required postfill files in {cache_dir}: "
            f"parents={parents_path.exists()} variants={variants_path.exists()}"
        )
    return pl.read_parquet(parents_path), pl.read_parquet(variants_path)


def _build_combined(
    parents_df: pl.DataFrame, variants_df: pl.DataFrame
) -> pl.DataFrame:
    parent_id_expr = (
        pl.col("parent_product_id")
        if "parent_product_id" in parents_df.columns
        else pl.lit("")
    )
    parent_rows = parents_df.with_columns(
        pl.lit("parent").alias("record_type"),
        parent_id_expr.cast(pl.Utf8).alias("product"),
        pl.lit("").alias("variant"),
    )

    variant_parent_expr = (
        pl.col("parent_product_id")
        if "parent_product_id" in variants_df.columns
        else pl.lit("")
    )
    variant_id_expr = (
        pl.col("variant_id") if "variant_id" in variants_df.columns else pl.lit("")
    )
    variant_rows = variants_df.with_columns(
        pl.lit("variant").alias("record_type"),
        variant_parent_expr.cast(pl.Utf8).alias("product"),
        variant_id_expr.cast(pl.Utf8).alias("variant"),
    )
    return pl.concat([parent_rows, variant_rows], how="diagonal_relaxed")


def _true_count(df: pl.DataFrame, column_name: str) -> int:
    if column_name not in df.columns:
        return 0
    return int(
        df.filter(
            pl.col(column_name).cast(pl.Boolean, strict=False).fill_null(False)
        ).height
    )


def _log_summary(parents_df: pl.DataFrame, variants_df: pl.DataFrame) -> None:
    hybrid_keys = sorted(
        {
            column_name
            for column_name in parents_df.columns + variants_df.columns
            if column_name.startswith("also_")
            and not column_name.endswith("_source")
            and not column_name.endswith("_evidence")
            and not column_name.endswith("_secondary_category")
        }
    )
    if not hybrid_keys:
        logging.info("No hybrid key columns found after refresh.")
        return
    for key in hybrid_keys:
        logging.info(
            "Hybrid %s: parents_true=%s variants_true=%s",
            key,
            _true_count(parents_df, key),
            _true_count(variants_df, key),
        )


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    mapping_dir = _resolve_mapping_dir()
    cache_dir = mapping_dir / "postfill_attribute_cache"
    logging.info("Using postfill cache directory: %s", cache_dir)

    parents_df, variants_df = _load_required_frames(cache_dir)
    logging.info(
        "Loaded postfill frames: parents_rows=%s variants_rows=%s",
        parents_df.height,
        variants_df.height,
    )

    parents_refreshed = annotate_market_hybrid_claims(parents_df, record_type="parent")
    variants_refreshed = annotate_market_hybrid_claims(
        variants_df, record_type="variant"
    )

    parents_all_path = cache_dir / "parents_all.parquet"
    if parents_all_path.is_file():
        parents_all_df = pl.read_parquet(parents_all_path)
        parents_all_refreshed = annotate_market_hybrid_claims(
            parents_all_df, record_type="parent"
        )
    else:
        parents_all_refreshed = parents_refreshed

    combined_refreshed = _build_combined(parents_refreshed, variants_refreshed)
    _log_summary(parents_refreshed, variants_refreshed)

    if args.dry_run:
        logging.info("Dry run complete; no files written.")
        return 0

    parents_refreshed.write_parquet(cache_dir / "parents.parquet")
    variants_refreshed.write_parquet(cache_dir / "variants.parquet")
    parents_all_refreshed.write_parquet(cache_dir / "parents_all.parquet")
    combined_refreshed.write_parquet(cache_dir / "combined.parquet")
    logging.info("Wrote refreshed postfill hybrid overlays to %s", cache_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
