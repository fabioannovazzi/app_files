from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.discovery import discover_listing_observations
from modules.pdp.fetcher import HTMLFetcher
from modules.pdp.http_headers import get_headers_for_retailer
from modules.pdp.http_proxies import get_proxies_for_retailer
from modules.pdp.profile import PDPProfile
from modules.pdp.profile_loader import iter_profile_summaries, load_profile
from modules.pdp.review_constants import (
    DEFAULT_PDP_STORE_PATH,
    add_pdp_store_path_argument,
)
from modules.pdp.sort_sequence_quality import (
    build_sort_sequence_quality_report,
    normalize_ranked_sort_modes,
)
from modules.pdp.store import PDPStore
from modules.pdp.ulta_filter_discovery import (
    crawl_ulta_filter_observations,
    default_filter_families_for_category,
    extract_ulta_filter_surfaces,
)
from modules.pdp.ulta_listing_discovery import (
    category_listing_identity,
    classify_listing_statuses,
    listing_identity,
    profile_to_category_key,
)
from modules.pdp.ulta_sitemap import (
    ULTA_SITEMAP_SOURCE_URLS,
    crawl_ulta_sitemap_observations,
    normalize_ulta_url,
)
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.utils import get_row_count

LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT_ROOT = Path("data/pdp/discovery_runs/ulta")
DEFAULT_LINKS_PATH = Path("data/pdp/links.json")
DEFAULT_SORT_MODES = ("best_sellers", "new_arrivals", "top_rated")
DEFAULT_SITEMAP_SOURCES = ("product",)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Ulta listing discovery, persist listing observations, and derive empirical recency."
    )
    add_pdp_store_path_argument(parser, default=DEFAULT_PDP_STORE_PATH)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Output root for run artifacts (default: data/pdp/discovery_runs/ulta).",
    )
    parser.add_argument(
        "--links-path",
        type=Path,
        default=DEFAULT_LINKS_PATH,
        help="Links manifest path to update (default: data/pdp/links.json).",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="Optional category keys to limit the Ulta run.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum number of paginated pages to crawl after the base listing.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=2.0,
        help="Delay between paginated requests.",
    )
    parser.add_argument(
        "--sort-modes",
        nargs="*",
        default=list(DEFAULT_SORT_MODES),
        help="Sort modes to crawl (default: best_sellers new_arrivals top_rated).",
    )
    parser.add_argument(
        "--recent-share",
        type=float,
        default=0.20,
        help=(
            "Share of each category to label as recent based on top rank in "
            "new_arrivals (default: 0.20)."
        ),
    )
    parser.add_argument(
        "--capture-filters",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Crawl selected Ulta attribute filter surfaces and persist product "
            "memberships (default: enabled; use --no-capture-filters to disable)."
        ),
    )
    parser.add_argument(
        "--filter-families",
        nargs="*",
        default=None,
        help=(
            "Optional override for filter families to capture. By default the "
            "runner chooses category-specific families automatically."
        ),
    )
    parser.add_argument(
        "--filter-max-pages",
        type=int,
        default=5,
        help="Maximum pages to crawl for each filter surface (default: 5).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    parser.add_argument(
        "--capture-sitemap",
        action="store_true",
        help="Also crawl selected Ulta sitemap sources as a completeness backstop.",
    )
    parser.add_argument(
        "--sitemap-sources",
        nargs="*",
        default=list(DEFAULT_SITEMAP_SOURCES),
        help=(
            "Sitemap sources to capture when --capture-sitemap is set "
            f"(default: {' '.join(DEFAULT_SITEMAP_SOURCES)}; available: "
            f"{' '.join(sorted(ULTA_SITEMAP_SOURCE_URLS))})."
        ),
    )
    parser.add_argument(
        "--sitemap-max-product-sitemaps",
        type=int,
        default=None,
        help="Optional limit on child product sitemap files, mainly for smoke runs.",
    )
    return parser.parse_args()


def _normalize_categories(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    return {str(value).strip().lower() for value in values if str(value).strip()}


def _build_prior_seen_identities(
    store: PDPStore,
    *,
    crawl_ts: str,
) -> set[str]:
    prior_listing_identities = store.fetch_retailer_seen_listing_identities(
        retailer="ulta", before_crawl_ts=crawl_ts
    )
    existing_parent_ids = store.existing_parent_ids("ulta")
    existing_pdp_urls = store.existing_pdp_urls("ulta")
    normalized_existing_urls = {
        normalized
        for normalized in (normalize_ulta_url(url) for url in existing_pdp_urls)
        if normalized
    }
    return prior_listing_identities | existing_parent_ids | normalized_existing_urls


def _load_ulta_profiles(categories: set[str] | None) -> list[PDPProfile]:
    matched: list[PDPProfile] = []
    for summary in iter_profile_summaries():
        if summary.retailer.lower() != "ulta":
            continue
        profile = load_profile(summary.profile_name)
        category_key = profile_to_category_key(profile.profile_name).lower()
        if categories is not None and category_key not in categories:
            continue
        matched.append(profile)
    return matched


def _observations_to_frame(
    observations: list,
    *,
    crawl_ts: str,
    statuses: dict[tuple[str, str], str],
) -> pl.DataFrame:
    rows = [
        {
            "crawl_ts": crawl_ts,
            "retailer": observation.retailer,
            "category_key": observation.category_key,
            "source_surface": observation.source_surface,
            "sort_mode": observation.sort_mode,
            "page": observation.page,
            "position": observation.position,
            "pdp_url": observation.pdp_url,
            "parent_product_id": observation.parent_product_id,
            "product_name": observation.product_name,
            "brand": observation.brand,
            "has_new_badge": observation.has_new_badge,
            "listing_url": observation.listing_url,
            "listing_identity": listing_identity(observation),
            "listing_status": statuses.get(
                category_listing_identity(observation), "old"
            ),
        }
        for observation in observations
    ]
    if not rows:
        return pl.DataFrame(
            schema={
                "crawl_ts": pl.Utf8,
                "retailer": pl.Utf8,
                "category_key": pl.Utf8,
                "source_surface": pl.Utf8,
                "sort_mode": pl.Utf8,
                "page": pl.Int64,
                "position": pl.Int64,
                "pdp_url": pl.Utf8,
                "parent_product_id": pl.Utf8,
                "product_name": pl.Utf8,
                "brand": pl.Utf8,
                "has_new_badge": pl.Boolean,
                "listing_url": pl.Utf8,
                "listing_identity": pl.Utf8,
                "listing_status": pl.Utf8,
            }
        )
    return pl.DataFrame(rows)


def _write_run_artifacts(
    *,
    output_dir: Path,
    observations_frame: pl.DataFrame,
    category_links_payload: dict[str, list[str]],
    filter_observations_frame: pl.DataFrame | None,
    filter_surfaces_frame: pl.DataFrame | None,
    sitemap_observations_frame: pl.DataFrame | None,
    sitemap_missing_products_frame: pl.DataFrame | None,
    summary: dict[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    observations_frame.write_csv(output_dir / "retailer_listing_observations.csv")
    (output_dir / "category_links.json").write_text(
        json.dumps(category_links_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if filter_observations_frame is not None:
        filter_observations_frame.write_csv(
            output_dir / "retailer_filter_observations.csv"
        )
    if filter_surfaces_frame is not None:
        filter_surfaces_frame.write_csv(output_dir / "retailer_filter_surfaces.csv")
    if sitemap_observations_frame is not None:
        sitemap_observations_frame.write_csv(
            output_dir / "retailer_sitemap_observations.csv"
        )
    if sitemap_missing_products_frame is not None:
        sitemap_missing_products_frame.write_csv(
            output_dir / "retailer_sitemap_missing_products.csv"
        )

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _filter_observations_to_frame(
    observations: list,
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
    if not rows:
        return pl.DataFrame(
            schema={
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
        )
    return pl.DataFrame(rows)


def _filter_surfaces_to_frame(surfaces: list, *, crawl_ts: str) -> pl.DataFrame:
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
    if not rows:
        return pl.DataFrame(
            schema={
                "crawl_ts": pl.Utf8,
                "retailer": pl.Utf8,
                "category_key": pl.Utf8,
                "filter_family": pl.Utf8,
                "filter_value": pl.Utf8,
                "filter_url": pl.Utf8,
                "filter_label": pl.Utf8,
            }
        )
    return pl.DataFrame(rows)


def _sitemap_observations_to_frame(
    observations: list,
    *,
    crawl_ts: str,
) -> pl.DataFrame:
    rows = [
        {
            "crawl_ts": crawl_ts,
            "retailer": observation.retailer,
            "sitemap_source": observation.sitemap_source,
            "url": observation.url,
            "lastmod": observation.lastmod,
            "url_type": observation.url_type,
        }
        for observation in observations
    ]
    if not rows:
        return pl.DataFrame(
            schema={
                "crawl_ts": pl.Utf8,
                "retailer": pl.Utf8,
                "sitemap_source": pl.Utf8,
                "url": pl.Utf8,
                "lastmod": pl.Utf8,
                "url_type": pl.Utf8,
            }
        )
    return pl.DataFrame(rows)


def _build_sitemap_missing_products_frame(
    *,
    sitemap_observations_frame: pl.DataFrame,
    existing_pdp_urls: set[str],
) -> pl.DataFrame:
    if sitemap_observations_frame.is_empty():
        return pl.DataFrame(
            schema={
                "url": pl.Utf8,
                "lastmod": pl.Utf8,
                "sitemap_source": pl.Utf8,
            }
        )

    normalized_existing_urls = [
        normalized
        for normalized in (normalize_ulta_url(url) for url in existing_pdp_urls)
        if normalized
    ]
    product_frame = (
        sitemap_observations_frame.filter(pl.col("url_type") == "product")
        .sort(["url", "sitemap_source"])
        .unique(subset=["url"], keep="first")
    )
    if not normalized_existing_urls:
        return product_frame.select(["url", "lastmod", "sitemap_source"])
    return product_frame.filter(~pl.col("url").is_in(normalized_existing_urls)).select(
        ["url", "lastmod", "sitemap_source"]
    )


def _read_links_payload(path: Path) -> dict[str, dict[str, list[str]]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    if "retailer" in payload and "categories" in payload:
        retailer = str(payload.get("retailer", "")).strip().lower()
        categories = payload.get("categories")
        if retailer and isinstance(categories, Mapping):
            category_map: dict[str, list[str]] = {}
            for category_key, links in categories.items():
                if isinstance(links, list):
                    category_map[str(category_key)] = [
                        str(link) for link in links if isinstance(link, str)
                    ]
            return {retailer: category_map}
    result: dict[str, dict[str, list[str]]] = {}
    for retailer, categories in payload.items():
        if not isinstance(categories, Mapping):
            continue
        category_map: dict[str, list[str]] = {}
        for category_key, links in categories.items():
            if isinstance(links, list):
                category_map[str(category_key)] = [
                    str(link) for link in links if isinstance(link, str)
                ]
        result[str(retailer).lower()] = category_map
    return result


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _category_links_from_observations(
    observations: list,
    *,
    category_keys: set[str],
) -> dict[str, list[str]]:
    links_by_category: dict[str, list[str]] = {key: [] for key in sorted(category_keys)}
    seen_by_category: dict[str, set[str]] = {key: set() for key in category_keys}
    for observation in observations:
        category_key = str(observation.category_key or "").strip()
        if category_key not in seen_by_category:
            continue
        url = str(observation.pdp_url or "").strip()
        if not url or url in seen_by_category[category_key]:
            continue
        seen_by_category[category_key].add(url)
        links_by_category[category_key].append(url)
    return links_by_category


def _merge_links_payload(
    existing_payload: dict[str, dict[str, list[str]]],
    *,
    retailer: str,
    category_links: dict[str, list[str]],
) -> dict[str, dict[str, list[str]]]:
    merged: dict[str, dict[str, list[str]]] = {
        key: {category: list(links) for category, links in categories.items()}
        for key, categories in existing_payload.items()
    }
    retailer_key = retailer.strip().lower()
    retailer_payload = merged.get(retailer_key, {})
    for category_key, links in category_links.items():
        retailer_payload[category_key] = list(links)
    merged[retailer_key] = retailer_payload
    return merged


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_env_from_secrets_file()

    run_started = dt.datetime.now(dt.timezone.utc)
    crawl_ts = run_started.isoformat()
    run_slug = run_started.strftime("%Y%m%dT%H%M%SZ")

    categories = _normalize_categories(args.categories)
    profiles = _load_ulta_profiles(categories)
    if not profiles:
        LOGGER.warning("No Ulta profiles matched the requested category set.")
        return 0
    requested_sort_modes = tuple(args.sort_modes or ())
    args.sort_modes = list(normalize_ranked_sort_modes(requested_sort_modes))
    removed_sort_modes = [
        sort_mode
        for sort_mode in requested_sort_modes
        if sort_mode not in args.sort_modes
    ]
    if removed_sort_modes:
        LOGGER.warning(
            "Ignoring non-ranked Ulta sort modes: %s",
            ", ".join(str(mode) for mode in removed_sort_modes),
        )
    if not args.sort_modes:
        LOGGER.error(
            "No ranked Ulta sort modes remain after removing default/sale sorts."
        )
        return 1

    store = PDPStore(args.pdp_store_path)
    existing_parent_ids = store.existing_parent_ids("ulta")
    existing_pdp_urls = store.existing_pdp_urls("ulta")
    headers = get_headers_for_retailer("ulta")
    proxies = get_proxies_for_retailer("ulta")
    fetcher = HTMLFetcher(
        headers=headers if headers else None,
        proxies=proxies if proxies else None,
    )

    observations = []
    filter_surfaces = []
    filter_observations = []
    sitemap_observations = []
    for profile in profiles:
        category_key = profile_to_category_key(profile.profile_name)
        LOGGER.info("Crawling Ulta category %s", category_key)
        category_observations = discover_listing_observations(
            profile.category_urls,
            category_key=category_key,
            max_pages=args.max_pages,
            fetcher=fetcher,
            delay_seconds=args.delay_seconds,
            allowed_patterns=(
                (profile.id_extractors.parent_from_url_regex,)
                if profile.id_extractors.parent_from_url_regex
                else None
            ),
            raise_on_error=False,
            retailer=profile.retailer,
            sort_modes=tuple(args.sort_modes),
            source_surface="category",
            parent_id_pattern=profile.id_extractors.parent_from_url_regex,
            canonical_base_url=profile.base_url,
        )
        observations.extend(category_observations)

        if args.capture_filters:
            allowed_families = (
                tuple(args.filter_families)
                if args.filter_families
                else default_filter_families_for_category(category_key)
            )
            for category_url in profile.category_urls:
                base_result = fetcher.fetch(category_url)
                category_surfaces = extract_ulta_filter_surfaces(
                    category_url=base_result.url,
                    html=base_result.html,
                    category_key=category_key,
                    retailer=profile.retailer,
                    allowed_families=allowed_families,
                )
                filter_surfaces.extend(category_surfaces)
                category_filter_observations = crawl_ulta_filter_observations(
                    category_surfaces,
                    fetcher=fetcher,
                    max_pages=args.filter_max_pages,
                    delay_seconds=args.delay_seconds,
                    allowed_patterns=(
                        (profile.id_extractors.parent_from_url_regex,)
                        if profile.id_extractors.parent_from_url_regex
                        else None
                    ),
                    parent_id_pattern=profile.id_extractors.parent_from_url_regex,
                    canonical_base_url=profile.base_url,
                )
                filter_observations.extend(category_filter_observations)

    if args.capture_sitemap:
        LOGGER.info(
            "Crawling Ulta sitemap sources: %s",
            ", ".join(str(source) for source in args.sitemap_sources),
        )
        sitemap_observations = crawl_ulta_sitemap_observations(
            fetcher=fetcher,
            sources=tuple(args.sitemap_sources),
            max_product_sitemaps=args.sitemap_max_product_sitemaps,
        )

    statuses = classify_listing_statuses(
        observations,
        recent_share=args.recent_share,
    )
    category_keys = {
        profile_to_category_key(profile.profile_name) for profile in profiles
    }
    category_links_payload = _category_links_from_observations(
        observations,
        category_keys=category_keys,
    )
    links_payload = _read_links_payload(args.links_path)
    merged_links_payload = _merge_links_payload(
        links_payload,
        retailer="ulta",
        category_links=category_links_payload,
    )

    observations_frame = _observations_to_frame(
        observations,
        crawl_ts=crawl_ts,
        statuses=statuses,
    )
    filter_observations_frame = _filter_observations_to_frame(
        filter_observations,
        crawl_ts=crawl_ts,
    )
    filter_surfaces_frame = _filter_surfaces_to_frame(
        filter_surfaces,
        crawl_ts=crawl_ts,
    )
    sitemap_observations_frame = _sitemap_observations_to_frame(
        sitemap_observations,
        crawl_ts=crawl_ts,
    )
    sitemap_missing_products_frame = _build_sitemap_missing_products_frame(
        sitemap_observations_frame=sitemap_observations_frame,
        existing_pdp_urls=existing_pdp_urls,
    )
    sort_sequence_quality = build_sort_sequence_quality_report(observations)

    status_counts = (
        observations_frame.select("category_key", "listing_identity", "listing_status")
        .unique()
        .group_by("listing_status")
        .len()
        .sort("listing_status")
    )
    summary = {
        "crawl_ts": crawl_ts,
        "profile_count": len(profiles),
        "observed_rows": get_row_count(observations_frame),
        "unique_products": observations_frame.select(
            pl.col("listing_identity").n_unique()
        ).item(),
        "unique_category_products": observations_frame.select(
            pl.struct(["category_key", "listing_identity"]).n_unique()
        ).item(),
        "status_counts": status_counts.to_dicts(),
        "filter_surface_count": filter_surfaces_frame.select(pl.len()).item(),
        "filter_observation_rows": get_row_count(filter_observations_frame),
        "sitemap_observation_rows": get_row_count(sitemap_observations_frame),
        "sitemap_missing_product_count": get_row_count(sitemap_missing_products_frame),
        "links_path": str(args.links_path),
        "links_categories_updated": sorted(category_links_payload),
        "categories": sorted(
            {profile_to_category_key(profile.profile_name) for profile in profiles}
        ),
        "sort_modes": list(args.sort_modes),
        "removed_sort_modes": removed_sort_modes,
        "sort_sequence_quality": sort_sequence_quality,
        "recent_share": args.recent_share,
        "cohort_definition": (
            "recent = top share of category products by new_arrivals rank; "
            "rest = all other discovered products in the category"
        ),
    }

    output_dir = args.output_root / run_slug
    _write_run_artifacts(
        output_dir=output_dir,
        observations_frame=observations_frame,
        category_links_payload=category_links_payload,
        filter_observations_frame=(
            filter_observations_frame if args.capture_filters else None
        ),
        filter_surfaces_frame=filter_surfaces_frame if args.capture_filters else None,
        sitemap_observations_frame=(
            sitemap_observations_frame if args.capture_sitemap else None
        ),
        sitemap_missing_products_frame=(
            sitemap_missing_products_frame if args.capture_sitemap else None
        ),
        summary=summary,
    )
    if sort_sequence_quality["status"] == "failed":
        LOGGER.error(
            "Ulta discovery failed sort sequence quality gate: %s",
            sort_sequence_quality,
        )
        return 1
    if sort_sequence_quality["status"] == "warning":
        LOGGER.warning(
            "Ulta discovery found high newest/top-seller sort overlap. "
            "Persisting observations; downstream packages should use rank-order "
            "contrast rather than independent cohort contrast. Details: %s",
            sort_sequence_quality,
        )

    try:
        _write_json(args.links_path, merged_links_payload)
        store.append_retailer_listing_observations(
            crawl_ts=crawl_ts,
            observations=observations,
        )
        if filter_surfaces:
            store.append_retailer_filter_surfaces(
                crawl_ts=crawl_ts,
                surfaces=filter_surfaces,
            )
        if filter_observations:
            store.append_retailer_filter_observations(
                crawl_ts=crawl_ts,
                observations=filter_observations,
            )
        if sitemap_observations:
            store.append_retailer_sitemap_observations(
                crawl_ts=crawl_ts,
                observations=sitemap_observations,
            )
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        return 1

    LOGGER.info("Persisted %s listing observations.", get_row_count(observations_frame))
    LOGGER.info("Wrote discovery artifacts to %s", output_dir)
    LOGGER.info("Updated links manifest: %s", args.links_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
