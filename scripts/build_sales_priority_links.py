from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Sequence

import polars as pl

from modules.pdp.sales_dataset_paths import (
    DEFAULT_SALES_DATASET,
    get_sales_dataset_dir,
    get_sales_dataset_join_dir,
    get_sales_dataset_name,
)
from modules.utilities.utils import get_row_count

__all__ = [
    "build_category_sales_plan",
    "canonicalize_amazon_link",
    "merge_category_links",
    "select_count_for_target_coverage",
    "main",
]

LOGGER = logging.getLogger(__name__)
AMAZON_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
AMAZON_ASIN_IN_URL_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})", re.IGNORECASE)
DEFAULT_LINKS_PATH = Path("data/pdp/links.json")
EPSILON = 1e-9
DEFAULT_RECENT_MONTHS = 2
DEFAULT_RECENT_TOP_SKUS = 20
DEFAULT_RECENT_MIN_CATEGORY_SHARE_PCT = 0.1

_CATEGORY_SALES_ALIASES: dict[str, tuple[str, ...]] = {
    "blush": ("blush",),
    "bronzer": ("bronzer",),
    "color_corrector": ("color corrector", "color correcting"),
    "concealer": ("concealer", "under-eye concealer"),
    "contour": ("contour", "contouring"),
    "eyebrow": ("eyebrow",),
    "eyeliner": ("eyeliner",),
    "eyeshadow": ("eyeshadow",),
    "face_primer": ("face primer",),
    "foundation": ("foundation",),
    "highlighter": ("highlighter",),
    "lip_gloss": ("lip gloss",),
    "lip_oil": ("lip oil",),
    "lipstick": ("lipstick", "liquid lipstick"),
    "mascara": ("mascara",),
    "setting_spray_powder": ("setting spray & powder",),
}


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build Amazon PDP links from top sales SKUs (by cumulative sales coverage) "
            "and merge them into data/pdp/links.json."
        )
    )
    parser.add_argument(
        "--retailer",
        default="amazon",
        help="Retailer key in links.json and sales data (default: amazon).",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        help=(
            "Category keys to update. Defaults to all categories already present for "
            "the retailer in links.json."
        ),
    )
    parser.add_argument(
        "--target-coverage-pct",
        type=float,
        default=90.0,
        help="Target cumulative sales coverage percentage per category (default: 90).",
    )
    parser.add_argument(
        "--max-urls-per-category",
        type=int,
        default=0,
        help=(
            "Optional hard cap for selected URLs per category (0 means no cap, "
            "default: 0)."
        ),
    )
    parser.add_argument(
        "--recent-months",
        type=int,
        default=DEFAULT_RECENT_MONTHS,
        help=(
            "Recent window in months for launch booster picks (default: 2). "
            "Set to 0 to disable recent booster."
        ),
    )
    parser.add_argument(
        "--recent-top-skus",
        type=int,
        default=DEFAULT_RECENT_TOP_SKUS,
        help=(
            "Maximum recent-window SKUs to add beyond core coverage picks "
            "(default: 20). Set to 0 to disable."
        ),
    )
    parser.add_argument(
        "--recent-min-category-share-pct",
        type=float,
        default=DEFAULT_RECENT_MIN_CATEGORY_SHARE_PCT,
        help=(
            "Minimum recent-window sales share (percent of category recent sales) "
            "for a SKU to qualify as launch booster pick (default: 0.1)."
        ),
    )
    parser.add_argument(
        "--replace-category-links",
        action="store_true",
        help=(
            "Replace category links with the sales-selected set. By default, selected "
            "URLs are appended to existing links."
        ),
    )
    parser.add_argument(
        "--dataset",
        help=(
            "Sales dataset name. Defaults to PDP_SALES_DATASET env or "
            f"'{DEFAULT_SALES_DATASET}'."
        ),
    )
    parser.add_argument(
        "--links-path",
        type=Path,
        default=DEFAULT_LINKS_PATH,
        help="Path to links.json (default: data/pdp/links.json).",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        help=(
            "Directory for run report files. Defaults to sales dataset directory "
            "(e.g., data/pdp/sales_data)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and report changes without writing links.json.",
    )
    return parser.parse_args(argv)


def _normalize_category_key(value: str | None) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _empty_selection_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rank": pl.Int64,
            "sku": pl.Utf8,
            "url": pl.Utf8,
            "sales_sum": pl.Float64,
            "cumulative_sales": pl.Float64,
            "cumulative_coverage_pct": pl.Float64,
            "selection_source": pl.Utf8,
            "recent_sales_share_pct": pl.Float64,
        }
    )


def _month_date_expr(column_name: str = "month") -> pl.Expr:
    month_text = pl.col(column_name).cast(pl.Utf8).str.strip_chars()
    return pl.coalesce(
        [
            pl.col(column_name).cast(pl.Date, strict=False),
            month_text.str.strptime(pl.Date, format="%Y-%m-%d", strict=False),
            month_text.str.strptime(pl.Date, format="%m/%d/%Y", strict=False),
            month_text.str.strptime(pl.Date, format="%Y-%m", strict=False),
            month_text.str.strptime(pl.Date, format="%Y", strict=False),
        ]
    )


def _sales_aliases_for_category(category_key: str) -> tuple[str, ...]:
    normalized = _normalize_category_key(category_key)
    configured = _CATEGORY_SALES_ALIASES.get(normalized, ())
    if configured:
        return tuple(
            str(item).strip().lower() for item in configured if str(item).strip()
        )
    fallback = normalized.replace("_", " ").strip()
    return (fallback,) if fallback else ()


def _extract_asin(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    upper_text = text.upper()
    if AMAZON_ASIN_RE.fullmatch(upper_text):
        return upper_text
    match = AMAZON_ASIN_IN_URL_RE.search(text)
    if not match:
        return None
    return match.group(1).upper()


def canonicalize_amazon_link(value: str) -> str:
    asin = _extract_asin(value)
    if not asin:
        return str(value).strip()
    return f"https://www.amazon.com/dp/{asin}"


def _dedupe_keep_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def merge_category_links(
    existing_links: Sequence[str],
    selected_links: Sequence[str],
    *,
    replace_category_links: bool,
) -> list[str]:
    canonical_existing = _dedupe_keep_order(
        [canonicalize_amazon_link(link) for link in existing_links]
    )
    canonical_selected = _dedupe_keep_order(
        [canonicalize_amazon_link(link) for link in selected_links]
    )
    if replace_category_links:
        return canonical_selected
    return _dedupe_keep_order([*canonical_existing, *canonical_selected])


def select_count_for_target_coverage(
    cumulative_coverage_pct: Sequence[float],
    *,
    target_coverage_pct: float,
) -> int:
    if not cumulative_coverage_pct:
        return 0
    threshold = max(float(target_coverage_pct), 0.0)
    for idx, value in enumerate(cumulative_coverage_pct, start=1):
        if float(value) + EPSILON >= threshold:
            return idx
    return len(cumulative_coverage_pct)


def build_category_sales_plan(
    sales_df: pl.DataFrame,
    *,
    retailer: str,
    category_key: str,
    target_coverage_pct: float,
    max_urls_per_category: int,
    recent_months: int = DEFAULT_RECENT_MONTHS,
    recent_top_skus: int = DEFAULT_RECENT_TOP_SKUS,
    recent_min_category_share_pct: float = DEFAULT_RECENT_MIN_CATEGORY_SHARE_PCT,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    retailer_key = str(retailer).strip().lower()
    category_norm = _normalize_category_key(category_key)
    category_aliases = _sales_aliases_for_category(category_norm)
    if not category_aliases:
        empty = _empty_selection_frame()
        return (
            empty,
            {
                "retailer": retailer_key,
                "category": category_norm,
                "sales_category_aliases": [],
                "sales_rows": 0,
                "sku_total": 0,
                "sku_valid_asin": 0,
                "selected_url_count": 0,
                "coverage_pct": 0.0,
                "coverage_pct_core": 0.0,
                "total_sales": 0.0,
                "selected_sales": 0.0,
                "selected_sales_core": 0.0,
                "recent_window_months": int(max(recent_months, 0)),
                "recent_top_skus": int(max(recent_top_skus, 0)),
                "recent_min_category_share_pct": float(
                    max(recent_min_category_share_pct, 0.0)
                ),
                "recent_total_sales": 0.0,
                "recent_candidate_count": 0,
                "recent_selected_count": 0,
            },
        )

    filtered = sales_df.filter(
        (pl.col("merchant") == retailer_key)
        & pl.col("category").is_in(list(category_aliases))
    )
    sales_rows = get_row_count(filtered)
    if filtered.is_empty():
        empty = _empty_selection_frame()
        return (
            empty,
            {
                "retailer": retailer_key,
                "category": category_norm,
                "sales_category_aliases": list(category_aliases),
                "sales_rows": sales_rows,
                "sku_total": 0,
                "sku_valid_asin": 0,
                "selected_url_count": 0,
                "coverage_pct": 0.0,
                "coverage_pct_core": 0.0,
                "total_sales": 0.0,
                "selected_sales": 0.0,
                "selected_sales_core": 0.0,
                "recent_window_months": int(max(recent_months, 0)),
                "recent_top_skus": int(max(recent_top_skus, 0)),
                "recent_min_category_share_pct": float(
                    max(recent_min_category_share_pct, 0.0)
                ),
                "recent_total_sales": 0.0,
                "recent_candidate_count": 0,
                "recent_selected_count": 0,
            },
        )

    working = filtered.with_columns(
        pl.col("sku").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("sku")
    ).filter(
        pl.col("sku").is_not_null()
        & (pl.col("sku") != "")
        & pl.col("sku").str.contains(AMAZON_ASIN_RE.pattern)
    )

    sku_sales = (
        working.group_by("sku")
        .agg(pl.col("sales").sum().alias("sales_sum"))
        .sort("sales_sum", descending=True)
    )
    if sku_sales.is_empty():
        empty = _empty_selection_frame()
        return (
            empty,
            {
                "retailer": retailer_key,
                "category": category_norm,
                "sales_category_aliases": list(category_aliases),
                "sales_rows": sales_rows,
                "sku_total": 0,
                "sku_valid_asin": 0,
                "selected_url_count": 0,
                "coverage_pct": 0.0,
                "coverage_pct_core": 0.0,
                "total_sales": 0.0,
                "selected_sales": 0.0,
                "selected_sales_core": 0.0,
                "recent_window_months": int(max(recent_months, 0)),
                "recent_top_skus": int(max(recent_top_skus, 0)),
                "recent_min_category_share_pct": float(
                    max(recent_min_category_share_pct, 0.0)
                ),
                "recent_total_sales": 0.0,
                "recent_candidate_count": 0,
                "recent_selected_count": 0,
            },
        )

    total_sales_value = float(sku_sales.get_column("sales_sum").sum() or 0.0)
    sku_sales_ranked = sku_sales.with_row_index("rank", offset=1)
    sku_sales_ranked = sku_sales_ranked.with_columns(
        [
            pl.col("sales_sum").cum_sum().alias("cumulative_sales"),
            (
                pl.when(pl.lit(total_sales_value) > 0.0)
                .then(
                    (pl.col("sales_sum").cum_sum() / pl.lit(total_sales_value)) * 100.0
                )
                .otherwise(pl.lit(0.0))
            ).alias("cumulative_coverage_pct"),
            pl.concat_str([pl.lit("https://www.amazon.com/dp/"), pl.col("sku")]).alias(
                "url"
            ),
        ]
    ).select(
        [
            "rank",
            "sku",
            "url",
            "sales_sum",
            "cumulative_sales",
            "cumulative_coverage_pct",
        ]
    )

    coverage_series = [
        float(value)
        for value in sku_sales_ranked.get_column("cumulative_coverage_pct").to_list()
        if value is not None
    ]
    core_selected_count = select_count_for_target_coverage(
        coverage_series,
        target_coverage_pct=target_coverage_pct,
    )
    if max_urls_per_category > 0:
        core_selected_count = min(core_selected_count, max_urls_per_category)

    core_selected = (
        sku_sales_ranked.head(core_selected_count)
        .with_columns(
            [
                pl.lit("core_coverage").alias("selection_source"),
                pl.lit(None, dtype=pl.Float64).alias("recent_sales_share_pct"),
            ]
        )
        .select(
            [
                "rank",
                "sku",
                "url",
                "sales_sum",
                "cumulative_sales",
                "cumulative_coverage_pct",
                "selection_source",
                "recent_sales_share_pct",
            ]
        )
    )

    if core_selected.is_empty():
        core_selected_sales = 0.0
        core_coverage_pct = 0.0
    else:
        core_selected_sales = float(core_selected.get_column("sales_sum").sum() or 0.0)
        core_coverage_pct = float(
            core_selected.get_column("cumulative_coverage_pct").tail(1).item() or 0.0
        )

    recent_total_sales = 0.0
    recent_candidate_count = 0
    recent_selected_count = 0
    recent_selected = _empty_selection_frame()
    recent_window_size = int(max(recent_months, 0))
    recent_cap = int(max(recent_top_skus, 0))
    recent_min_share = float(max(recent_min_category_share_pct, 0.0))

    recent_enabled = (
        recent_window_size > 0 and recent_cap > 0 and "month" in working.columns
    )
    if recent_enabled:
        recent_base = (
            working.with_columns(_month_date_expr("month").alias("_month_date"))
            .drop_nulls(subset=["_month_date"])
            .with_columns(
                (
                    pl.col("_month_date").dt.year() * 12
                    + pl.col("_month_date").dt.month()
                    - 1
                ).alias("_month_index")
            )
        )
        if not recent_base.is_empty():
            latest_month_index = recent_base.get_column("_month_index").max()
            if latest_month_index is not None:
                cutoff_month_index = int(latest_month_index) - recent_window_size + 1
                recent_window = recent_base.filter(
                    pl.col("_month_index") >= cutoff_month_index
                )
                recent_sku_sales = (
                    recent_window.group_by("sku")
                    .agg(pl.col("sales").sum().alias("recent_sales"))
                    .sort("recent_sales", descending=True)
                )
                if not recent_sku_sales.is_empty():
                    recent_total_sales = float(
                        recent_sku_sales.get_column("recent_sales").sum() or 0.0
                    )
                    recent_sku_sales = recent_sku_sales.with_columns(
                        (
                            pl.when(pl.lit(recent_total_sales) > 0.0)
                            .then(
                                (pl.col("recent_sales") / pl.lit(recent_total_sales))
                                * 100.0
                            )
                            .otherwise(pl.lit(0.0))
                        ).alias("recent_sales_share_pct")
                    )
                    if recent_min_share > 0.0:
                        recent_sku_sales = recent_sku_sales.filter(
                            pl.col("recent_sales_share_pct")
                            >= (pl.lit(recent_min_share) - EPSILON)
                        )
                    if not core_selected.is_empty():
                        core_skus = core_selected.get_column("sku").to_list()
                        recent_sku_sales = recent_sku_sales.filter(
                            ~pl.col("sku").is_in(core_skus)
                        )
                    recent_candidate_count = int(get_row_count(recent_sku_sales))
                    recent_limit = recent_cap
                    if max_urls_per_category > 0:
                        open_slots = max(
                            int(max_urls_per_category)
                            - int(get_row_count(core_selected)),
                            0,
                        )
                        recent_limit = min(recent_limit, open_slots)
                    recent_take = (
                        recent_sku_sales.head(recent_limit)
                        if recent_limit > 0
                        else recent_sku_sales.head(0)
                    )
                    recent_selected_count = int(get_row_count(recent_take))
                    if not recent_take.is_empty():
                        recent_selected = recent_take.with_columns(
                            [
                                pl.concat_str(
                                    [
                                        pl.lit("https://www.amazon.com/dp/"),
                                        pl.col("sku"),
                                    ]
                                ).alias("url"),
                                pl.col("recent_sales").alias("sales_sum"),
                                pl.lit(None, dtype=pl.Float64).alias(
                                    "cumulative_sales"
                                ),
                                pl.lit(None, dtype=pl.Float64).alias(
                                    "cumulative_coverage_pct"
                                ),
                                pl.lit("recent_launch").alias("selection_source"),
                            ]
                        ).select(
                            [
                                "sku",
                                "url",
                                "sales_sum",
                                "cumulative_sales",
                                "cumulative_coverage_pct",
                                "selection_source",
                                "recent_sales_share_pct",
                            ]
                        )

    selected_parts: list[pl.DataFrame] = [core_selected.drop("rank")]
    if not recent_selected.is_empty():
        selected_parts.append(recent_selected)
    selected = (
        pl.concat(selected_parts, how="vertical").with_row_index("rank", offset=1)
        if selected_parts
        else _empty_selection_frame()
    )

    selected_skus = (
        selected.get_column("sku").to_list() if not selected.is_empty() else []
    )
    if selected_skus:
        selected_sales = float(
            sku_sales.filter(pl.col("sku").is_in(selected_skus))
            .get_column("sales_sum")
            .sum()
            or 0.0
        )
    else:
        selected_sales = 0.0
    coverage_pct = (
        (selected_sales / total_sales_value) * 100.0 if total_sales_value > 0.0 else 0.0
    )

    summary = {
        "retailer": retailer_key,
        "category": category_norm,
        "sales_category_aliases": list(category_aliases),
        "sales_rows": sales_rows,
        "sku_total": int(get_row_count(sku_sales_ranked)),
        "sku_valid_asin": int(get_row_count(sku_sales_ranked)),
        "selected_url_count": int(get_row_count(selected)),
        "coverage_pct": coverage_pct,
        "coverage_pct_core": core_coverage_pct,
        "total_sales": total_sales_value,
        "selected_sales": selected_sales,
        "selected_sales_core": core_selected_sales,
        "recent_window_months": recent_window_size,
        "recent_top_skus": recent_cap,
        "recent_min_category_share_pct": recent_min_share,
        "recent_total_sales": recent_total_sales,
        "recent_candidate_count": recent_candidate_count,
        "recent_selected_count": recent_selected_count,
    }
    return selected, summary


def _read_links_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _write_links_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_sales_dataframe(dataset: str | None) -> tuple[pl.DataFrame, str]:
    dataset_name = get_sales_dataset_name(dataset)
    parquet_candidates = [
        get_sales_dataset_join_dir(dataset_name) / "full_sales.parquet",
        get_sales_dataset_dir(dataset_name) / "full_sales.parquet",
        Path("data") / "pdp" / "sales_data" / "full_sales.parquet",
    ]
    seen_paths: set[Path] = set()
    for path in parquet_candidates:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        if path.exists():
            frame = pl.read_parquet(path)
            required = {"merchant", "category", "sku", "sales"}
            if required.issubset(set(frame.columns)):
                LOGGER.info("Loaded sales frame from %s", path)
                return frame, dataset_name

    from modules.pdp import prejoin_sales as prejoin_mod

    prejoin_mod._configure_sales_paths(dataset_name)  # type: ignore[attr-defined]
    sales_raw, _paths = prejoin_mod._load_sales_csvs()  # type: ignore[attr-defined]
    normalized = prejoin_mod._normalize_sales(sales_raw)  # type: ignore[attr-defined]
    LOGGER.info(
        "Loaded sales frame from normalized CSVs for dataset=%s (rows=%s)",
        dataset_name,
        get_row_count(normalized),
    )
    return normalized, dataset_name


def _resolve_category_keys(
    *,
    retailer_payload: dict[str, Any],
    requested_categories: Sequence[str] | None,
) -> list[str]:
    if requested_categories:
        resolved = [_normalize_category_key(item) for item in requested_categories]
        return [item for item in resolved if item]
    existing = [_normalize_category_key(key) for key in retailer_payload.keys()]
    return sorted([item for item in existing if item])


def _timestamp_slug() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    retailer_key = str(args.retailer).strip().lower()
    if retailer_key != "amazon":
        LOGGER.error("This script currently supports --retailer amazon only.")
        return 1
    if args.target_coverage_pct <= 0.0:
        LOGGER.error("--target-coverage-pct must be > 0.")
        return 1
    if args.max_urls_per_category < 0:
        LOGGER.error("--max-urls-per-category must be >= 0.")
        return 1
    if args.recent_months < 0:
        LOGGER.error("--recent-months must be >= 0.")
        return 1
    if args.recent_top_skus < 0:
        LOGGER.error("--recent-top-skus must be >= 0.")
        return 1
    if args.recent_min_category_share_pct < 0.0:
        LOGGER.error("--recent-min-category-share-pct must be >= 0.")
        return 1

    payload = _read_links_payload(args.links_path)
    retailer_payload_raw = payload.get(retailer_key)
    if isinstance(retailer_payload_raw, dict):
        retailer_payload: dict[str, Any] = retailer_payload_raw
    else:
        retailer_payload = {}
        payload[retailer_key] = retailer_payload

    category_keys = _resolve_category_keys(
        retailer_payload=retailer_payload,
        requested_categories=args.categories,
    )
    if not category_keys:
        LOGGER.error(
            "No category keys resolved. Provide --categories or ensure links.json has %s categories.",
            retailer_key,
        )
        return 1

    sales_df, dataset_name = _load_sales_dataframe(args.dataset)
    required_cols = {"merchant", "category", "sku", "sales"}
    if not required_cols.issubset(set(sales_df.columns)):
        LOGGER.error(
            "Sales frame missing required columns %s (found=%s).",
            sorted(required_cols),
            sales_df.columns,
        )
        return 1
    sales_df = sales_df.with_columns(
        [
            pl.col("merchant")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("merchant"),
            pl.col("category")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("category"),
            pl.col("sales").cast(pl.Float64).alias("sales"),
        ]
    )

    run_rows: list[dict[str, Any]] = []
    selection_frames: list[pl.DataFrame] = []
    for category_key in category_keys:
        selected, summary = build_category_sales_plan(
            sales_df,
            retailer=retailer_key,
            category_key=category_key,
            target_coverage_pct=args.target_coverage_pct,
            max_urls_per_category=args.max_urls_per_category,
            recent_months=args.recent_months,
            recent_top_skus=args.recent_top_skus,
            recent_min_category_share_pct=args.recent_min_category_share_pct,
        )
        selected_urls = (
            selected.get_column("url").to_list() if "url" in selected.columns else []
        )
        existing_links_raw = retailer_payload.get(category_key, [])
        existing_links = (
            [str(item) for item in existing_links_raw]
            if isinstance(existing_links_raw, list)
            else []
        )
        merged_links = merge_category_links(
            existing_links,
            selected_urls,
            replace_category_links=args.replace_category_links,
        )

        run_row = dict(summary)
        run_row.update(
            {
                "existing_links": len(existing_links),
                "final_links": len(merged_links),
                "added_links": max(len(merged_links) - len(existing_links), 0),
                "replace_mode": bool(args.replace_category_links),
            }
        )
        run_rows.append(run_row)

        if not selected.is_empty():
            selection_frames.append(
                selected.with_columns(
                    [
                        pl.lit(retailer_key).alias("retailer"),
                        pl.lit(category_key).alias("category"),
                    ]
                ).select(
                    [
                        "retailer",
                        "category",
                        "rank",
                        "sku",
                        "url",
                        "sales_sum",
                        "cumulative_sales",
                        "cumulative_coverage_pct",
                        "selection_source",
                        "recent_sales_share_pct",
                    ]
                )
            )

        if not args.dry_run:
            retailer_payload[category_key] = merged_links

    timestamp = _timestamp_slug()
    report_dir = args.report_dir or get_sales_dataset_dir(dataset_name)
    report_dir.mkdir(parents=True, exist_ok=True)

    summary_payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "dataset": dataset_name,
        "retailer": retailer_key,
        "target_coverage_pct": float(args.target_coverage_pct),
        "max_urls_per_category": int(args.max_urls_per_category),
        "recent_months": int(args.recent_months),
        "recent_top_skus": int(args.recent_top_skus),
        "recent_min_category_share_pct": float(args.recent_min_category_share_pct),
        "replace_category_links": bool(args.replace_category_links),
        "dry_run": bool(args.dry_run),
        "categories": run_rows,
    }
    summary_path = (
        report_dir / f"{retailer_key}_sales_priority_links_summary_{timestamp}.json"
    )
    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if selection_frames:
        selections_df = pl.concat(selection_frames, how="vertical")
    else:
        selections_df = pl.DataFrame(
            schema={
                "retailer": pl.Utf8,
                "category": pl.Utf8,
                "rank": pl.Int64,
                "sku": pl.Utf8,
                "url": pl.Utf8,
                "sales_sum": pl.Float64,
                "cumulative_sales": pl.Float64,
                "cumulative_coverage_pct": pl.Float64,
                "selection_source": pl.Utf8,
                "recent_sales_share_pct": pl.Float64,
            }
        )
    selections_path = (
        report_dir / f"{retailer_key}_sales_priority_links_selected_{timestamp}.csv"
    )
    selections_df.write_csv(selections_path)

    if not args.dry_run:
        _write_links_payload(args.links_path, payload)
        LOGGER.info("Updated %s", args.links_path)
    else:
        LOGGER.info("Dry run: links.json not modified.")

    LOGGER.info("Wrote summary report: %s", summary_path)
    LOGGER.info("Wrote selected SKU report: %s", selections_path)
    for row in run_rows:
        LOGGER.info(
            "%s/%s: selected=%s coverage=%.2f%% (core=%.2f%%, recent_added=%s) existing=%s final=%s",
            row["retailer"],
            row["category"],
            row["selected_url_count"],
            row["coverage_pct"],
            row["coverage_pct_core"],
            row["recent_selected_count"],
            row["existing_links"],
            row["final_links"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
