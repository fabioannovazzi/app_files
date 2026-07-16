from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import polars as pl
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.fetcher import HTMLFetcher
from modules.pdp.http_headers import get_headers_for_retailer
from modules.pdp.kiko_filter_discovery import (
    crawl_kiko_filter_observations,
    extract_kiko_filter_surfaces,
)
from modules.pdp.models import FilterObservation, FilterSurface
from modules.pdp.profile import PDPProfile
from modules.pdp.profile_loader import iter_profile_summaries, load_profile
from modules.pdp.review_constants import add_pdp_store_path_argument
from modules.pdp.service import apply_locale
from modules.pdp.store import PDPStore
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.utils import get_row_count

LOGGER = logging.getLogger(__name__)

DEFAULT_OUTPUT_ROOT = Path("data/pdp/discovery_runs/kiko_filters")
DEFAULT_EVIDENCE_ROOT = Path("data/pdp/retailer_filter_evidence")
DEFAULT_CACHE_ROOT = Path("data/pdp/pdp_attribute_cache")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Kiko category filter evidence from embedded Algolia PLP state.",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="Optional Kiko category keys to capture, e.g. foundation lip_gloss.",
    )
    parser.add_argument("--locale", default="en-us")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    add_pdp_store_path_argument(parser)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _category_key(profile: PDPProfile) -> str:
    prefix = f"{profile.retailer.lower()}_"
    if profile.profile_name.lower().startswith(prefix):
        return profile.profile_name[len(prefix) :]
    return profile.profile_name


def _normalize_categories(values: Sequence[str] | None) -> set[str] | None:
    if not values:
        return None
    normalized = {
        str(value).strip().lower().replace("-", "_").replace(" ", "_")
        for value in values
        if str(value).strip()
    }
    return normalized or None


def _load_profiles(categories: set[str] | None, *, locale: str) -> list[PDPProfile]:
    profiles: list[PDPProfile] = []
    for summary in iter_profile_summaries():
        if summary.retailer.lower() != "kiko":
            continue
        profile = apply_locale(load_profile(summary.profile_name), locale)
        key = _category_key(profile)
        if categories is not None and key not in categories:
            continue
        profiles.append(profile)
    return profiles


def _filter_surfaces_to_frame(
    surfaces: Sequence[FilterSurface],
    *,
    crawl_ts: str,
) -> pl.DataFrame:
    rows = [
        {
            "crawl_ts": crawl_ts,
            "retailer": surface.retailer,
            "category_key": surface.category_key,
            "filter_family": surface.filter_family,
            "filter_value": surface.filter_value,
            "filter_url": surface.filter_url,
            "filter_label": surface.filter_label,
        }
        for surface in surfaces
    ]
    schema = {
        "crawl_ts": pl.Utf8,
        "retailer": pl.Utf8,
        "category_key": pl.Utf8,
        "filter_family": pl.Utf8,
        "filter_value": pl.Utf8,
        "filter_url": pl.Utf8,
        "filter_label": pl.Utf8,
    }
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def _filter_observations_to_frame(
    observations: Sequence[FilterObservation],
    *,
    crawl_ts: str,
) -> pl.DataFrame:
    rows = [
        {
            "crawl_ts": crawl_ts,
            "retailer": observation.retailer,
            "category_key": observation.category_key,
            "filter_family": observation.filter_family,
            "filter_value": observation.filter_value,
            "source_surface": observation.source_surface,
            "pdp_url": observation.pdp_url,
            "parent_product_id": observation.parent_product_id,
            "page": observation.page,
            "position": observation.position,
            "listing_url": observation.listing_url,
        }
        for observation in observations
    ]
    schema = {
        "crawl_ts": pl.Utf8,
        "retailer": pl.Utf8,
        "category_key": pl.Utf8,
        "filter_family": pl.Utf8,
        "filter_value": pl.Utf8,
        "source_surface": pl.Utf8,
        "pdp_url": pl.Utf8,
        "parent_product_id": pl.Utf8,
        "page": pl.Int64,
        "position": pl.Int64,
        "listing_url": pl.Utf8,
    }
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def _load_variant_parent_lookup(cache_root: Path) -> dict[str, tuple[str, ...]]:
    variants_path = cache_root / "kiko" / "variants.parquet"
    if not variants_path.is_file():
        return {}
    frame = pl.read_parquet(variants_path)
    columns = set(frame.columns)
    if "parent_product_id" not in columns:
        return {}

    lookup: dict[str, set[str]] = {}
    key_columns = [
        column
        for column in ("variant_id", "backend_id", "backend_parent_id")
        if column in columns
    ]
    if not key_columns:
        return {}
    for row in frame.select(["parent_product_id", *key_columns]).to_dicts():
        parent_id = str(row.get("parent_product_id") or "").strip()
        if not parent_id:
            continue
        for column in key_columns:
            key = str(row.get(column) or "").strip()
            if key:
                lookup.setdefault(key, set()).add(parent_id)
    return {key: tuple(sorted(values)) for key, values in lookup.items()}


def _write_outputs(
    *,
    output_dir: Path,
    evidence_dir: Path,
    surfaces_frame: pl.DataFrame,
    observations_frame: pl.DataFrame,
    summary: Mapping[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    surfaces_frame.write_csv(output_dir / "retailer_filter_surfaces.csv")
    observations_frame.write_csv(output_dir / "retailer_filter_observations.csv")
    surfaces_frame.write_parquet(output_dir / "filter_surfaces.parquet")
    observations_frame.write_parquet(output_dir / "filter_observations.parquet")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    surfaces_frame.write_parquet(evidence_dir / "filter_surfaces.parquet")
    observations_frame.write_parquet(evidence_dir / "filter_observations.parquet")
    surfaces_frame.write_csv(evidence_dir / "retailer_filter_surfaces.csv")
    observations_frame.write_csv(evidence_dir / "retailer_filter_observations.csv")
    (evidence_dir / "metadata.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_env_from_secrets_file()

    categories = _normalize_categories(args.categories)
    profiles = _load_profiles(categories, locale=str(args.locale))
    if not profiles:
        LOGGER.warning(
            "No Kiko profiles matched categories=%s", sorted(categories or [])
        )
        return 0

    variant_parent_lookup = _load_variant_parent_lookup(args.cache_root)
    if not variant_parent_lookup:
        LOGGER.warning(
            "No Kiko variant-parent lookup found at %s; filter observations will not map to parents.",
            args.cache_root / "kiko" / "variants.parquet",
        )

    started = dt.datetime.now(dt.timezone.utc)
    crawl_ts = started.isoformat()
    run_slug = started.strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_root / run_slug
    evidence_dir = args.evidence_root / "kiko"

    session = requests.Session()
    fetcher = HTMLFetcher(session=session, headers=get_headers_for_retailer("kiko"))
    surfaces: list[FilterSurface] = []
    observations: list[FilterObservation] = []
    failures: list[dict[str, str]] = []

    for profile in profiles:
        category_key = _category_key(profile)
        for category_url in profile.category_urls:
            try:
                result = fetcher.fetch(category_url, timeout=float(args.timeout))
            except Exception as exc:
                LOGGER.warning(
                    "Failed to fetch Kiko category %s: %s", category_url, exc
                )
                failures.append(
                    {
                        "category_key": category_key,
                        "category_url": category_url,
                        "error": str(exc),
                    }
                )
                continue

            category_surfaces = extract_kiko_filter_surfaces(
                category_url=result.url,
                html=result.html,
                category_key=category_key,
            )
            surfaces.extend(category_surfaces)
            observations.extend(
                crawl_kiko_filter_observations(
                    category_url=result.url,
                    html=result.html,
                    category_key=category_key,
                    variant_parent_lookup=variant_parent_lookup,
                    session=session,
                    max_pages=int(args.max_pages),
                    timeout=float(args.timeout),
                )
            )
            LOGGER.info(
                "Captured Kiko filters for %s: surfaces=%s observations=%s",
                category_key,
                len(category_surfaces),
                len(observations),
            )

    surfaces_frame = _filter_surfaces_to_frame(surfaces, crawl_ts=crawl_ts)
    observations_frame = _filter_observations_to_frame(observations, crawl_ts=crawl_ts)
    store = PDPStore(args.pdp_store_path)
    store.append_retailer_filter_surfaces(crawl_ts=crawl_ts, surfaces=surfaces)
    store.append_retailer_filter_observations(
        crawl_ts=crawl_ts,
        observations=observations,
    )
    summary = {
        "crawl_ts": crawl_ts,
        "retailer": "kiko",
        "categories": sorted({_category_key(profile) for profile in profiles}),
        "filter_surface_rows": get_row_count(surfaces_frame),
        "filter_observation_rows": get_row_count(observations_frame),
        "variant_parent_lookup_keys": len(variant_parent_lookup),
        "failures": failures,
        "output_dir": str(output_dir),
        "evidence_dir": str(evidence_dir),
        "pdp_store_path": str(args.pdp_store_path),
    }
    _write_outputs(
        output_dir=output_dir,
        evidence_dir=evidence_dir,
        surfaces_frame=surfaces_frame,
        observations_frame=observations_frame,
        summary=summary,
    )
    LOGGER.info("Kiko filter discovery complete: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
