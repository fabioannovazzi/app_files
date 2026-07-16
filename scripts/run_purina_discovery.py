from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

import polars as pl
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.category_keys import canonical_category_keys
from modules.pdp.models import FilterObservation, FilterSurface, ListingObservation
from modules.pdp.postgres_compat import connect_pdp_database, is_postgres_enabled
from modules.pdp.purina_catalog import (
    PURINA_BRAND_NAME,
    PURINA_CATEGORY_KEY,
    PURINA_RETAILER,
    PURINA_WET_CAT_FOOD_URL,
    fetch_purina_wet_cat_food_products,
    purina_brand_from_product,
    purina_parent_id_from_url,
    purina_product_text,
    purina_product_url,
    purina_semantic_attribute_hints,
)
from modules.pdp.purina_filter_discovery import (
    build_purina_filter_records,
    fetch_purina_filter_memberships,
    purina_api_filters_from_search_payload,
)
from modules.pdp.review_constants import (
    add_pdp_store_path_argument,
    enforce_default_pdp_store_path,
)
from modules.pdp.store import PDPStore
from modules.utilities.secrets_loader import load_env_from_secrets_file

LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT_ROOT = Path("data/pdp/discovery_runs")
DEFAULT_LINKS_PATH = Path("data/pdp/links.json")
DEFAULT_FILTER_EVIDENCE_ROOT = Path("data/pdp/retailer_filter_evidence")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover Purina US wet cat food products from the official Purina "
            "product search API and persist listing/filter evidence."
        ),
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--categories",
        nargs="*",
        default=(PURINA_CATEGORY_KEY,),
        help="Category keys to discover (default: wet_cat_food).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Discovery artifact root (default: data/pdp/discovery_runs).",
    )
    parser.add_argument(
        "--links-path",
        type=Path,
        default=DEFAULT_LINKS_PATH,
        help="Links manifest to update (default: data/pdp/links.json).",
    )
    parser.add_argument(
        "--filter-evidence-root",
        type=Path,
        default=DEFAULT_FILTER_EVIDENCE_ROOT,
        help=(
            "Latest retailer filter evidence root "
            "(default: data/pdp/retailer_filter_evidence)."
        ),
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP timeout for Purina API requests (default: 30).",
    )
    parser.add_argument(
        "--crawl-ts",
        default=None,
        help="Optional crawl timestamp. Defaults to current UTC time.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    return parser.parse_args(list(argv))


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, str(level or "INFO").upper(), logging.INFO),
        format="%(levelname)s %(message)s",
    )


def _read_links_payload(path: Path) -> dict[str, dict[str, list[str]]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    result: dict[str, dict[str, list[str]]] = {}
    for retailer, categories in payload.items():
        if not isinstance(categories, Mapping):
            continue
        result[str(retailer).strip().lower()] = {
            str(category): [str(link) for link in links if isinstance(link, str)]
            for category, links in categories.items()
            if isinstance(links, list)
        }
    return result


def _write_links_payload(
    *,
    path: Path,
    retailer: str,
    category_key: str,
    links: Sequence[str],
) -> None:
    payload = _read_links_payload(path)
    retailer_key = retailer.strip().lower()
    retailer_payload = dict(payload.get(retailer_key, {}))
    retailer_payload[category_key] = list(links)
    payload[retailer_key] = retailer_payload
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _listing_frame(
    observations: Sequence[ListingObservation], crawl_ts: str
) -> pl.DataFrame:
    return pl.DataFrame(
        [{"crawl_ts": crawl_ts, **asdict(observation)} for observation in observations],
        infer_schema_length=None,
    )


def _filter_surface_frame(
    surfaces: Sequence[FilterSurface], crawl_ts: str
) -> pl.DataFrame:
    return pl.DataFrame(
        [{"crawl_ts": crawl_ts, **asdict(surface)} for surface in surfaces],
        infer_schema_length=None,
    )


def _filter_observation_frame(
    observations: Sequence[FilterObservation],
    crawl_ts: str,
) -> pl.DataFrame:
    return pl.DataFrame(
        [{"crawl_ts": crawl_ts, **asdict(observation)} for observation in observations],
        infer_schema_length=None,
    )


def _write_latest_filter_evidence(
    *,
    evidence_root: Path,
    retailer: str,
    filter_surfaces_frame: pl.DataFrame,
    filter_observations_frame: pl.DataFrame,
    summary: Mapping[str, object],
) -> None:
    evidence_dir = evidence_root / retailer
    evidence_dir.mkdir(parents=True, exist_ok=True)
    filter_surfaces_frame.write_parquet(evidence_dir / "filter_surfaces.parquet")
    filter_observations_frame.write_parquet(
        evidence_dir / "filter_observations.parquet"
    )
    filter_surfaces_frame.write_csv(evidence_dir / "retailer_filter_surfaces.csv")
    filter_observations_frame.write_csv(
        evidence_dir / "retailer_filter_observations.csv"
    )
    metadata = dict(summary)
    metadata["evidence_dir"] = str(evidence_dir)
    (evidence_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_run_artifacts(
    *,
    output_dir: Path,
    listing_frame: pl.DataFrame,
    surface_frame: pl.DataFrame,
    observation_frame: pl.DataFrame,
    included_rows: Sequence[Mapping[str, object]],
    excluded_rows: Sequence[Mapping[str, object]],
    api_filters: Sequence[Mapping[str, object]],
    enriched_products: Sequence[Mapping[str, object]],
    links: Sequence[str],
    summary: Mapping[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    listing_frame.write_csv(output_dir / "retailer_listing_observations.csv")
    surface_frame.write_csv(output_dir / "retailer_filter_surfaces.csv")
    observation_frame.write_csv(output_dir / "retailer_filter_observations.csv")
    pl.DataFrame(list(included_rows), infer_schema_length=None).write_csv(
        output_dir / "included_products.csv"
    )
    pl.DataFrame(list(excluded_rows), infer_schema_length=None).write_csv(
        output_dir / "excluded_products.csv"
    )
    (output_dir / "api_filters.json").write_text(
        json.dumps(list(api_filters), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "api_products.json").write_text(
        json.dumps(list(enriched_products), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "category_links.json").write_text(
        json.dumps({PURINA_CATEGORY_KEY: list(links)}, indent=2),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(dict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _require_postgres(pdp_store_path: Path) -> None:
    if not is_postgres_enabled():
        raise SystemExit(
            "PDP Postgres is not configured. Open the tunnel/load secrets first; "
            "this workflow does not use a local local PDP database fallback."
        )
    with connect_pdp_database(pdp_store_path) as conn:
        conn.execute("SELECT 1").fetchone()


def _listing_page_url(page: int) -> str:
    if page <= 1:
        return PURINA_WET_CAT_FOOD_URL
    return f"{PURINA_WET_CAT_FOOD_URL}?page={page}"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    _configure_logging(args.log_level)
    load_env_from_secrets_file()
    pdp_store_path = enforce_default_pdp_store_path(args.pdp_store_path)
    _require_postgres(pdp_store_path)

    categories = canonical_category_keys(PURINA_RETAILER, args.categories)
    if categories != {PURINA_CATEGORY_KEY}:
        raise SystemExit("Purina discovery currently supports wet_cat_food only.")

    crawl_ts = args.crawl_ts or dt.datetime.now(dt.timezone.utc).isoformat()
    output_dir = (
        args.output_root / PURINA_RETAILER / crawl_ts.replace(":", "").replace("+", "Z")
    )
    session = requests.Session()
    product_rows, first_payload = fetch_purina_wet_cat_food_products(
        session,
        timeout=args.request_timeout_seconds,
    )
    api_filters = purina_api_filters_from_search_payload(first_payload)
    filters_by_parent = fetch_purina_filter_memberships(
        session,
        api_filters,
        timeout=args.request_timeout_seconds,
    )

    included_rows: list[dict[str, object]] = []
    excluded_rows: list[dict[str, object]] = []
    listing_observations: list[ListingObservation] = []
    parent_rows_for_filters: list[dict[str, object]] = []
    enriched_products: list[dict[str, object]] = []
    links: list[str] = []
    seen_links: set[str] = set()

    for product in product_rows:
        parent_id = purina_parent_id_from_url(str(product.get("url") or ""))
        product_url = purina_product_url(parent_id or "", str(product.get("url") or ""))
        title = str(product.get("title") or "").strip()
        site_filters = filters_by_parent.get(parent_id or "", [])
        enriched_product = dict(product)
        enriched_product["site_filters"] = site_filters
        enriched_product["site_attributes"] = purina_semantic_attribute_hints(
            enriched_product,
            site_filters=site_filters,
        )
        brand = purina_brand_from_product(enriched_product)

        row = {
            "brand": brand,
            "parent_product_id": parent_id,
            "pdp_url": product_url,
            "product_assortment": (
                "Variety Pack"
                if str(product.get("type") or "").endswith("bundle")
                else "Single Recipe"
            ),
            "site_filter_count": len(site_filters),
            "title": title,
            "type": product.get("type"),
        }
        if not parent_id:
            excluded_rows.append({**row, "scope_reason": "missing parent id"})
            continue

        included_rows.append(
            {
                **row,
                "scope_reason": "official Purina US wet-cat-food API product",
                "text_length": len(purina_product_text(enriched_product)),
                "variation_count": len(product.get("product_variations") or []),
            }
        )
        enriched_products.append(enriched_product)
        if product_url not in seen_links:
            seen_links.add(product_url)
            links.append(product_url)
        page = int(product.get("_listing_page") or 1)
        position = int(product.get("_listing_position") or len(links))
        listing_observations.append(
            ListingObservation(
                retailer=PURINA_RETAILER,
                category_key=PURINA_CATEGORY_KEY,
                source_surface="purina_product_search_api",
                sort_mode="relevance",
                page=page,
                position=position,
                pdp_url=product_url,
                parent_product_id=parent_id,
                product_name=title,
                brand=brand or PURINA_BRAND_NAME,
                has_new_badge=False,
                listing_url=_listing_page_url(page),
            )
        )
        parent_rows_for_filters.append(
            {
                "parent_product_id": parent_id,
                "pdp_url": product_url,
                "category_key": PURINA_CATEGORY_KEY,
                "extras": {"site_filters": site_filters},
            }
        )

    filter_surfaces, filter_observations = build_purina_filter_records(
        parent_rows_for_filters,
        allowed_categories=(PURINA_CATEGORY_KEY,),
    )
    listing_df = _listing_frame(listing_observations, crawl_ts)
    surface_df = _filter_surface_frame(filter_surfaces, crawl_ts)
    observation_df = _filter_observation_frame(filter_observations, crawl_ts)

    summary = {
        "retailer": PURINA_RETAILER,
        "category_key": PURINA_CATEGORY_KEY,
        "crawl_ts": crawl_ts,
        "source_product_rows": len(product_rows),
        "included_products": len(included_rows),
        "excluded_products": len(excluded_rows),
        "api_filter_rows": len(api_filters),
        "listing_observation_rows": len(listing_observations),
        "filter_surface_rows": len(filter_surfaces),
        "filter_observation_rows": len(filter_observations),
        "links_path": str(args.links_path),
        "output_dir": str(output_dir),
    }

    store = PDPStore(pdp_store_path)
    store.append_retailer_listing_observations(
        crawl_ts=crawl_ts,
        observations=listing_observations,
    )
    store.append_retailer_filter_surfaces(crawl_ts=crawl_ts, surfaces=filter_surfaces)
    store.append_retailer_filter_observations(
        crawl_ts=crawl_ts,
        observations=filter_observations,
    )
    _write_links_payload(
        path=args.links_path,
        retailer=PURINA_RETAILER,
        category_key=PURINA_CATEGORY_KEY,
        links=links,
    )
    _write_run_artifacts(
        output_dir=output_dir,
        listing_frame=listing_df,
        surface_frame=surface_df,
        observation_frame=observation_df,
        included_rows=included_rows,
        excluded_rows=excluded_rows,
        api_filters=api_filters,
        enriched_products=enriched_products,
        links=links,
        summary=summary,
    )
    _write_latest_filter_evidence(
        evidence_root=args.filter_evidence_root,
        retailer=PURINA_RETAILER,
        filter_surfaces_frame=surface_df,
        filter_observations_frame=observation_df,
        summary=summary,
    )

    LOGGER.info(
        (
            "Purina discovery complete: included=%d excluded=%d "
            "listing_rows=%d api_filters=%d filter_surfaces=%d "
            "filter_observations=%d output=%s"
        ),
        len(included_rows),
        len(excluded_rows),
        len(listing_observations),
        len(api_filters),
        len(filter_surfaces),
        len(filter_observations),
        output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
