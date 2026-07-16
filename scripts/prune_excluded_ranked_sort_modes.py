from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.models import ListingObservation
from modules.pdp.postgres_compat import connect_pdp_database, pdp_database_exists
from modules.pdp.review_constants import add_pdp_store_path_argument
from modules.pdp.sort_sequence_quality import EXCLUDED_RANKED_SORT_MODES
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.utils import get_row_count
from scripts.run_retailer_listing_discovery_cdp import _classification_to_frame

LOGGER = logging.getLogger(__name__)
DEFAULT_ROOTS = (
    Path("data/pdp/discovery_runs/cdp"),
    Path("data/pdp/discovery_runs/ulta"),
)

__all__ = ["main"]


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove default and promotion sort rows from retailer listing artifacts."
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--roots",
        nargs="*",
        type=Path,
        default=list(DEFAULT_ROOTS),
        help="Discovery artifact roots to scan.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _excluded_values() -> tuple[str, ...]:
    return tuple(sorted(value for value in EXCLUDED_RANKED_SORT_MODES if value))


def _prune_pdp_store(pdp_store_path: Path) -> int:
    if not pdp_database_exists(pdp_store_path):
        return 0
    excluded = _excluded_values()
    placeholders = ",".join("?" for _ in excluded)
    with connect_pdp_database(pdp_store_path) as conn:
        cursor = conn.execute(
            f"""
            DELETE FROM retailer_listing_observations
            WHERE lower(sort_mode) IN ({placeholders})
            """,
            excluded,
        )
        conn.commit()
    return int(cursor.rowcount or 0)


def _prune_listing_csv(path: Path) -> int:
    frame = pl.read_csv(path, infer_schema_length=0)
    if frame.is_empty() or "sort_mode" not in frame.columns:
        return 0
    before = get_row_count(frame)
    filtered = frame.filter(
        ~pl.col("sort_mode")
        .cast(pl.Utf8, strict=False)
        .fill_null("")
        .str.to_lowercase()
        .is_in(list(EXCLUDED_RANKED_SORT_MODES))
    )
    removed = before - get_row_count(filtered)
    if removed:
        filtered.write_csv(path)
    return removed


def _read_summary(run_dir: Path) -> dict[str, object]:
    summary_path = run_dir / "summary.json"
    if not summary_path.is_file():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _first_string(frame: pl.DataFrame, column: str) -> str:
    if column not in frame.columns or frame.is_empty():
        return ""
    values = frame.get_column(column).drop_nulls().to_list()
    return str(values[0]).strip() if values else ""


def _safe_int(value: object, *, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "t", "yes", "y"}


def _safe_float(value: object, *, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _listing_observations_from_frame(
    frame: pl.DataFrame,
) -> tuple[ListingObservation, ...]:
    if frame.is_empty():
        return ()
    observations: list[ListingObservation] = []
    for row in frame.to_dicts():
        observations.append(
            ListingObservation(
                retailer=str(row.get("retailer") or "").strip(),
                category_key=str(row.get("category_key") or "").strip(),
                source_surface=str(row.get("source_surface") or "category").strip(),
                sort_mode=str(row.get("sort_mode") or "").strip(),
                page=_safe_int(row.get("page"), fallback=1),
                position=_safe_int(row.get("position"), fallback=1),
                pdp_url=str(row.get("pdp_url") or "").strip(),
                parent_product_id=(
                    str(row.get("parent_product_id")).strip()
                    if row.get("parent_product_id") is not None
                    else None
                ),
                product_name=(
                    str(row.get("product_name")).strip()
                    if row.get("product_name") is not None
                    else None
                ),
                brand=(
                    str(row.get("brand")).strip()
                    if row.get("brand") is not None
                    else None
                ),
                has_new_badge=_safe_bool(row.get("has_new_badge")),
                listing_url=(
                    str(row.get("listing_url")).strip()
                    if row.get("listing_url") is not None
                    else None
                ),
            )
        )
    return tuple(observations)


def _regenerate_classification_csv(path: Path) -> int:
    listing_path = path.with_name("retailer_listing_observations.csv")
    if not listing_path.is_file() or not path.is_file():
        return 0
    listing_frame = pl.read_csv(listing_path, infer_schema_length=0)
    if listing_frame.is_empty():
        return 0
    summary = _read_summary(path.parent)
    crawl_ts = str(summary.get("crawl_ts") or _first_string(listing_frame, "crawl_ts"))
    recent_share = _safe_float(summary.get("recent_share"), fallback=0.20)
    observations = _listing_observations_from_frame(listing_frame)
    try:
        regenerated = _classification_to_frame(
            observations,
            crawl_ts=crawl_ts,
            recent_share=recent_share,
        )
    except ValueError:
        LOGGER.warning(
            "Skipping classification regeneration for unsupported retailer in %s",
            path,
        )
        return 0
    regenerated.write_csv(path)
    return get_row_count(regenerated)


def _update_summary(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    sort_modes = payload.get("sort_modes")
    if not isinstance(sort_modes, list):
        return 0
    kept = [
        str(sort_mode)
        for sort_mode in sort_modes
        if str(sort_mode or "").strip().lower() not in EXCLUDED_RANKED_SORT_MODES
    ]
    removed = [str(sort_mode) for sort_mode in sort_modes if str(sort_mode) not in kept]
    if kept == sort_modes:
        return 0
    payload["sort_modes"] = kept
    existing_removed = payload.get("removed_sort_modes")
    removed_values = (
        list(existing_removed) if isinstance(existing_removed, list) else []
    )
    for sort_mode in removed:
        if sort_mode not in removed_values:
            removed_values.append(sort_mode)
    payload["removed_sort_modes"] = removed_values
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(removed)


def _prune_roots(roots: Sequence[Path]) -> dict[str, int]:
    counts = {
        "csv_rows": 0,
        "classification_rows": 0,
        "summary_modes": 0,
        "csv_files": 0,
        "classification_files": 0,
        "summary_files": 0,
    }
    for root in roots:
        if not root.is_dir():
            continue
        for csv_path in sorted(root.rglob("retailer_listing_observations.csv")):
            removed = _prune_listing_csv(csv_path)
            if removed:
                counts["csv_rows"] += removed
                counts["csv_files"] += 1
                LOGGER.info("Removed %s excluded sort rows from %s", removed, csv_path)
        for classification_path in sorted(
            root.rglob("retailer_listing_classification.csv")
        ):
            regenerated = _regenerate_classification_csv(classification_path)
            if regenerated:
                counts["classification_rows"] += regenerated
                counts["classification_files"] += 1
                LOGGER.info(
                    "Regenerated %s classification rows in %s",
                    regenerated,
                    classification_path,
                )
        for summary_path in sorted(root.rglob("summary.json")):
            removed = _update_summary(summary_path)
            if removed:
                counts["summary_modes"] += removed
                counts["summary_files"] += 1
                LOGGER.info(
                    "Removed %s excluded sort mode(s) from %s",
                    removed,
                    summary_path,
                )
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_env_from_secrets_file()
    pdp_store_rows = _prune_pdp_store(args.pdp_store_path)
    artifact_counts = _prune_roots(tuple(args.roots))
    LOGGER.info(
        "Pruned excluded ranked sort modes: pdp_store_rows=%s artifact_counts=%s",
        pdp_store_rows,
        artifact_counts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
