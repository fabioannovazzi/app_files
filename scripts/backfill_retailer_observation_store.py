from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.models import FilterObservation, FilterSurface, ListingObservation
from modules.pdp.review_constants import add_pdp_store_path_argument
from modules.pdp.store import PDPStore
from modules.utilities.utils import get_schema_and_column_names

LOGGER = logging.getLogger(__name__)
DEFAULT_DISCOVERY_ROOT = Path("data/pdp/discovery_runs/cdp")
DEFAULT_EVIDENCE_ROOT = Path("data/pdp/retailer_filter_evidence")

__all__ = ["main"]


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill generic retailer listing/filter observation store tables "
            "from existing retailer discovery CSV artifacts."
        )
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--discovery-root",
        type=Path,
        default=DEFAULT_DISCOVERY_ROOT,
        help="CDP discovery run root to scan.",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=DEFAULT_EVIDENCE_ROOT,
        help="Latest retailer filter evidence root to scan.",
    )
    parser.add_argument(
        "--retailers",
        nargs="*",
        default=None,
        help="Optional retailer keys to backfill.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _read_summary(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        LOGGER.warning("Failed to read summary JSON: %s", path)
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv(path: Path) -> pl.DataFrame | None:
    if not path.is_file():
        return None
    try:
        return pl.read_csv(path, infer_schema_length=0)
    except (OSError, pl.exceptions.PolarsError):
        LOGGER.warning("Failed to read CSV artifact: %s", path)
        return None


def _text(value: object) -> str:
    return str(value or "").strip()


def _int_value(value: object) -> int:
    text = _text(value)
    return int(text) if text.isdigit() else 0


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "on"}


def _crawl_ts(row: Mapping[str, object], summary: Mapping[str, object]) -> str:
    return _text(row.get("crawl_ts")) or _text(summary.get("crawl_ts"))


def _allowed_retailer(row: Mapping[str, object], retailers: set[str] | None) -> bool:
    retailer = _text(row.get("retailer")).lower()
    if not retailer or retailer.startswith("__"):
        return False
    if retailers is None:
        return True
    return retailer in retailers


def _valid_category(row: Mapping[str, object]) -> bool:
    category_key = _text(row.get("category_key"))
    return bool(category_key) and not category_key.startswith("__")


def _columns(frame: pl.DataFrame) -> set[str]:
    columns, _schema = get_schema_and_column_names(frame)
    return set(columns)


def _iter_listing_groups(
    path: Path,
    *,
    summary: Mapping[str, object],
    retailers: set[str] | None,
) -> Iterable[tuple[str, list[ListingObservation]]]:
    frame = _read_csv(path)
    if frame is None or frame.is_empty():
        return []
    required = {"retailer", "category_key", "source_surface", "sort_mode", "pdp_url"}
    if not required.issubset(_columns(frame)):
        LOGGER.warning("Skipping listing CSV with missing columns: %s", path)
        return []

    grouped: dict[str, list[ListingObservation]] = {}
    for row in frame.to_dicts():
        if not _allowed_retailer(row, retailers) or not _valid_category(row):
            continue
        crawl_ts = _crawl_ts(row, summary)
        pdp_url = _text(row.get("pdp_url"))
        if not crawl_ts or not pdp_url:
            continue
        grouped.setdefault(crawl_ts, []).append(
            ListingObservation(
                retailer=_text(row.get("retailer")).lower(),
                category_key=_text(row.get("category_key")),
                source_surface=_text(row.get("source_surface")),
                sort_mode=_text(row.get("sort_mode")),
                page=_int_value(row.get("page")),
                position=_int_value(row.get("position")),
                pdp_url=pdp_url,
                parent_product_id=_text(row.get("parent_product_id")) or None,
                product_name=_text(row.get("product_name")) or None,
                brand=_text(row.get("brand")) or None,
                has_new_badge=_bool_value(row.get("has_new_badge")),
                listing_url=_text(row.get("listing_url")) or None,
            )
        )
    return grouped.items()


def _iter_surface_groups(
    path: Path,
    *,
    summary: Mapping[str, object],
    retailers: set[str] | None,
) -> Iterable[tuple[str, list[FilterSurface]]]:
    frame = _read_csv(path)
    if frame is None or frame.is_empty():
        return []
    required = {
        "retailer",
        "category_key",
        "filter_family",
        "filter_value",
        "filter_url",
    }
    if not required.issubset(_columns(frame)):
        LOGGER.warning("Skipping filter surface CSV with missing columns: %s", path)
        return []

    grouped: dict[str, list[FilterSurface]] = {}
    for row in frame.to_dicts():
        if not _allowed_retailer(row, retailers) or not _valid_category(row):
            continue
        crawl_ts = _crawl_ts(row, summary)
        filter_url = _text(row.get("filter_url"))
        if not crawl_ts or not filter_url:
            continue
        grouped.setdefault(crawl_ts, []).append(
            FilterSurface(
                retailer=_text(row.get("retailer")).lower(),
                category_key=_text(row.get("category_key")),
                filter_family=_text(row.get("filter_family")),
                filter_value=_text(row.get("filter_value")),
                filter_url=filter_url,
                filter_label=_text(row.get("filter_label")) or None,
            )
        )
    return grouped.items()


def _iter_filter_observation_groups(
    path: Path,
    *,
    summary: Mapping[str, object],
    retailers: set[str] | None,
) -> Iterable[tuple[str, list[FilterObservation]]]:
    frame = _read_csv(path)
    if frame is None or frame.is_empty():
        return []
    required = {
        "retailer",
        "category_key",
        "filter_family",
        "filter_value",
        "source_surface",
        "pdp_url",
    }
    if not required.issubset(_columns(frame)):
        LOGGER.warning("Skipping filter observation CSV with missing columns: %s", path)
        return []

    grouped: dict[str, list[FilterObservation]] = {}
    for row in frame.to_dicts():
        if not _allowed_retailer(row, retailers) or not _valid_category(row):
            continue
        crawl_ts = _crawl_ts(row, summary)
        pdp_url = _text(row.get("pdp_url"))
        if not crawl_ts or not pdp_url:
            continue
        grouped.setdefault(crawl_ts, []).append(
            FilterObservation(
                retailer=_text(row.get("retailer")).lower(),
                category_key=_text(row.get("category_key")),
                filter_family=_text(row.get("filter_family")),
                filter_value=_text(row.get("filter_value")),
                source_surface=_text(row.get("source_surface")),
                pdp_url=pdp_url,
                parent_product_id=_text(row.get("parent_product_id")) or None,
                page=_int_value(row.get("page")),
                position=_int_value(row.get("position")),
                listing_url=_text(row.get("listing_url")) or None,
            )
        )
    return grouped.items()


def _iter_discovery_run_dirs(discovery_root: Path) -> Iterable[Path]:
    if not discovery_root.is_dir():
        return []
    return (
        path
        for path in sorted(discovery_root.glob("*/*"))
        if path.is_dir() and not path.name.startswith(".")
    )


def _iter_evidence_dirs(evidence_root: Path) -> Iterable[Path]:
    if not evidence_root.is_dir():
        return []
    return (
        path
        for path in sorted(evidence_root.iterdir())
        if path.is_dir() and not path.name.startswith(".")
    )


def _persist_groups(
    store: PDPStore,
    *,
    listing_groups: Iterable[tuple[str, list[ListingObservation]]],
    surface_groups: Iterable[tuple[str, list[FilterSurface]]],
    filter_groups: Iterable[tuple[str, list[FilterObservation]]],
) -> dict[str, int]:
    counts = {
        "listing_rows": 0,
        "filter_surface_rows": 0,
        "filter_observation_rows": 0,
    }
    for crawl_ts, observations in listing_groups:
        store.append_retailer_listing_observations(
            crawl_ts=crawl_ts,
            observations=observations,
        )
        counts["listing_rows"] += len(observations)
    for crawl_ts, surfaces in surface_groups:
        store.append_retailer_filter_surfaces(crawl_ts=crawl_ts, surfaces=surfaces)
        counts["filter_surface_rows"] += len(surfaces)
    for crawl_ts, observations in filter_groups:
        store.append_retailer_filter_observations(
            crawl_ts=crawl_ts,
            observations=observations,
        )
        counts["filter_observation_rows"] += len(observations)
    return counts


def _backfill_discovery_runs(
    store: PDPStore,
    *,
    discovery_root: Path,
    retailers: set[str] | None,
) -> dict[str, int]:
    counts = {
        "listing_rows": 0,
        "filter_surface_rows": 0,
        "filter_observation_rows": 0,
        "run_dirs": 0,
    }
    for run_dir in _iter_discovery_run_dirs(discovery_root):
        summary = _read_summary(run_dir / "summary.json")
        result = _persist_groups(
            store,
            listing_groups=_iter_listing_groups(
                run_dir / "retailer_listing_observations.csv",
                summary=summary,
                retailers=retailers,
            ),
            surface_groups=_iter_surface_groups(
                run_dir / "retailer_filter_surfaces.csv",
                summary=summary,
                retailers=retailers,
            ),
            filter_groups=_iter_filter_observation_groups(
                run_dir / "retailer_filter_observations.csv",
                summary=summary,
                retailers=retailers,
            ),
        )
        counts["run_dirs"] += 1
        counts["listing_rows"] += result["listing_rows"]
        counts["filter_surface_rows"] += result["filter_surface_rows"]
        counts["filter_observation_rows"] += result["filter_observation_rows"]
    return counts


def _backfill_latest_evidence(
    store: PDPStore,
    *,
    evidence_root: Path,
    retailers: set[str] | None,
) -> dict[str, int]:
    counts = {
        "filter_surface_rows": 0,
        "filter_observation_rows": 0,
        "evidence_dirs": 0,
    }
    for evidence_dir in _iter_evidence_dirs(evidence_root):
        summary = _read_summary(evidence_dir / "metadata.json")
        result = _persist_groups(
            store,
            listing_groups=[],
            surface_groups=_iter_surface_groups(
                evidence_dir / "retailer_filter_surfaces.csv",
                summary=summary,
                retailers=retailers,
            ),
            filter_groups=_iter_filter_observation_groups(
                evidence_dir / "retailer_filter_observations.csv",
                summary=summary,
                retailers=retailers,
            ),
        )
        counts["evidence_dirs"] += 1
        counts["filter_surface_rows"] += result["filter_surface_rows"]
        counts["filter_observation_rows"] += result["filter_observation_rows"]
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    retailers = (
        {
            str(retailer).strip().lower()
            for retailer in args.retailers
            if str(retailer).strip()
        }
        if args.retailers
        else None
    )
    store = PDPStore(args.pdp_store_path)
    discovery_counts = _backfill_discovery_runs(
        store,
        discovery_root=args.discovery_root,
        retailers=retailers,
    )
    evidence_counts = _backfill_latest_evidence(
        store,
        evidence_root=args.evidence_root,
        retailers=retailers,
    )
    summary = {
        "pdp_store_path": str(args.pdp_store_path),
        "discovery": discovery_counts,
        "latest_evidence": evidence_counts,
        "total_listing_rows_seen": discovery_counts["listing_rows"],
        "total_filter_surface_rows_seen": (
            discovery_counts["filter_surface_rows"]
            + evidence_counts["filter_surface_rows"]
        ),
        "total_filter_observation_rows_seen": (
            discovery_counts["filter_observation_rows"]
            + evidence_counts["filter_observation_rows"]
        ),
    }
    LOGGER.info("Retailer observation Postgres backfill complete: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
