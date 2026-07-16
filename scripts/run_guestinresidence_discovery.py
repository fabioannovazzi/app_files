from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.category_keys import canonical_category_keys
from modules.pdp.guestinresidence_catalog import (
    GUESTINRESIDENCE_BASE_URL,
    GUESTINRESIDENCE_CATEGORY_KEY,
    GUESTINRESIDENCE_COLLECTION_PATHS,
    GUESTINRESIDENCE_RETAILER,
    guestinresidence_cashmere_scope_decision,
    guestinresidence_parent_id_from_url,
    guestinresidence_product_url,
)
from modules.pdp.guestinresidence_filter_discovery import (
    build_guestinresidence_filter_records,
    extract_guestinresidence_filter_surfaces,
    guestinresidence_site_filters_for_product,
)
from modules.pdp.models import FilterObservation, FilterSurface, ListingObservation
from modules.pdp.postgres_compat import connect_pdp_database, is_postgres_enabled
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
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover Guest in Residence cashmere-led sweater/cardigan/top products "
            "from Shopify collection JSON and persist PDP listing/filter evidence."
        ),
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--categories",
        nargs="*",
        default=(GUESTINRESIDENCE_CATEGORY_KEY,),
        help="Category keys to discover (default: cashmere_sweaters).",
    )
    parser.add_argument(
        "--collection",
        nargs="*",
        default=tuple(GUESTINRESIDENCE_COLLECTION_PATHS),
        choices=tuple(GUESTINRESIDENCE_COLLECTION_PATHS),
        help="GIR source collections to scan.",
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
        "--max-pages",
        type=int,
        default=5,
        help="Maximum Shopify products.json pages per collection (default: 5).",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP timeout for collection JSON/HTML requests (default: 30).",
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


def _fetch_text(url: str, *, timeout: float) -> str:
    request = Request(url, headers={"Accept": "*/*", "User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _fetch_collection_products(
    collection_url: str,
    *,
    max_pages: int,
    timeout: float,
) -> list[tuple[int, int, Mapping[str, object]]]:
    rows: list[tuple[int, int, Mapping[str, object]]] = []
    seen_handles: set[str] = set()
    for page in range(1, max(1, max_pages) + 1):
        url = f"{collection_url.rstrip('/')}/products.json?limit=250&page={page}"
        payload = json.loads(_fetch_text(url, timeout=timeout))
        products = payload.get("products") if isinstance(payload, Mapping) else None
        if not isinstance(products, list):
            break
        page_new = 0
        for position, product in enumerate(products, start=1):
            if not isinstance(product, Mapping):
                continue
            handle = str(product.get("handle") or "").strip().lower()
            if not handle or handle in seen_handles:
                continue
            seen_handles.add(handle)
            page_new += 1
            rows.append((page, position, product))
        if not products or len(products) < 250 or page_new == 0:
            break
    return rows


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
    (output_dir / "category_links.json").write_text(
        json.dumps({GUESTINRESIDENCE_CATEGORY_KEY: list(links)}, indent=2),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(dict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _dedupe_surfaces(surfaces: Sequence[FilterSurface]) -> list[FilterSurface]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[FilterSurface] = []
    for surface in surfaces:
        key = (
            surface.category_key,
            surface.filter_family,
            surface.filter_value.casefold(),
            surface.filter_url,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(surface)
    return sorted(out, key=lambda item: (item.filter_family, item.filter_value))


def _require_postgres(pdp_store_path: Path) -> None:
    if not is_postgres_enabled():
        raise SystemExit(
            "PDP Postgres is not configured. Open the tunnel/load secrets first; "
            "this workflow does not use a local local PDP database fallback."
        )
    with connect_pdp_database(pdp_store_path) as conn:
        conn.execute("SELECT 1").fetchone()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    _configure_logging(args.log_level)
    load_env_from_secrets_file()
    pdp_store_path = enforce_default_pdp_store_path(args.pdp_store_path)
    _require_postgres(pdp_store_path)

    categories = canonical_category_keys(GUESTINRESIDENCE_RETAILER, args.categories)
    if categories != {GUESTINRESIDENCE_CATEGORY_KEY}:
        raise SystemExit(
            "Guest in Residence discovery currently supports cashmere_sweaters only."
        )

    crawl_ts = args.crawl_ts or dt.datetime.now(dt.timezone.utc).isoformat()
    output_dir = (
        args.output_root
        / GUESTINRESIDENCE_RETAILER
        / crawl_ts.replace(":", "").replace("+", "Z")
    )

    products_by_handle: dict[str, Mapping[str, object]] = {}
    source_meta_by_handle: dict[str, list[dict[str, object]]] = {}
    collection_surfaces: list[FilterSurface] = []
    for collection_name in args.collection:
        collection_path = GUESTINRESIDENCE_COLLECTION_PATHS[collection_name]
        collection_url = urljoin(GUESTINRESIDENCE_BASE_URL, collection_path)
        LOGGER.info("Scanning GIR collection %s: %s", collection_name, collection_url)
        html = _fetch_text(collection_url, timeout=args.request_timeout_seconds)
        collection_surfaces.extend(
            extract_guestinresidence_filter_surfaces(
                category_url=collection_url,
                html=html,
                category_key=GUESTINRESIDENCE_CATEGORY_KEY,
            )
        )
        for page, position, product in _fetch_collection_products(
            collection_url,
            max_pages=args.max_pages,
            timeout=args.request_timeout_seconds,
        ):
            handle = str(product.get("handle") or "").strip().lower()
            if not handle:
                continue
            products_by_handle.setdefault(handle, product)
            source_meta_by_handle.setdefault(handle, []).append(
                {
                    "collection": collection_name,
                    "collection_url": collection_url,
                    "page": page,
                    "position": position,
                }
            )

    listing_observations: list[ListingObservation] = []
    included_rows: list[dict[str, object]] = []
    excluded_rows: list[dict[str, object]] = []
    parent_rows_for_filters: list[dict[str, object]] = []
    links: list[str] = []
    seen_links: set[str] = set()

    for handle, product in sorted(products_by_handle.items()):
        include, reason = guestinresidence_cashmere_scope_decision(product)
        product_url = guestinresidence_product_url(handle)
        source_meta = source_meta_by_handle.get(handle, [])
        row = {
            "handle": handle,
            "title": str(product.get("title") or ""),
            "product_type": str(
                product.get("product_type") or product.get("type") or ""
            ),
            "pdp_url": product_url,
            "scope_reason": reason,
            "source_collections": "|".join(
                str(item["collection"]) for item in source_meta
            ),
        }
        if not include:
            excluded_rows.append(row)
            continue

        included_rows.append(row)
        if product_url not in seen_links:
            seen_links.add(product_url)
            links.append(product_url)
        for source in source_meta:
            listing_observations.append(
                ListingObservation(
                    retailer=GUESTINRESIDENCE_RETAILER,
                    category_key=GUESTINRESIDENCE_CATEGORY_KEY,
                    source_surface=f"collection:{source['collection']}",
                    sort_mode="default",
                    page=int(source["page"]),
                    position=int(source["position"]),
                    pdp_url=product_url,
                    parent_product_id=guestinresidence_parent_id_from_url(product_url),
                    product_name=str(product.get("title") or ""),
                    brand="Guest in Residence",
                    has_new_badge=False,
                    listing_url=str(source["collection_url"]),
                )
            )
        site_filters = guestinresidence_site_filters_for_product(product)
        parent_rows_for_filters.append(
            {
                "parent_product_id": handle,
                "pdp_url": product_url,
                "category_key": GUESTINRESIDENCE_CATEGORY_KEY,
                "extras": {"site_filters": site_filters},
            }
        )

    product_surfaces, filter_observations = build_guestinresidence_filter_records(
        parent_rows_for_filters,
        allowed_categories=(GUESTINRESIDENCE_CATEGORY_KEY,),
    )
    filter_surfaces = _dedupe_surfaces([*collection_surfaces, *product_surfaces])
    listing_frame = _listing_frame(listing_observations, crawl_ts)
    surface_frame = _filter_surface_frame(filter_surfaces, crawl_ts)
    observation_frame = _filter_observation_frame(filter_observations, crawl_ts)

    summary = {
        "retailer": GUESTINRESIDENCE_RETAILER,
        "category_key": GUESTINRESIDENCE_CATEGORY_KEY,
        "crawl_ts": crawl_ts,
        "source_product_rows": len(products_by_handle),
        "included_products": len(included_rows),
        "excluded_products": len(excluded_rows),
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
        retailer=GUESTINRESIDENCE_RETAILER,
        category_key=GUESTINRESIDENCE_CATEGORY_KEY,
        links=links,
    )
    _write_run_artifacts(
        output_dir=output_dir,
        listing_frame=listing_frame,
        surface_frame=surface_frame,
        observation_frame=observation_frame,
        included_rows=included_rows,
        excluded_rows=excluded_rows,
        links=links,
        summary=summary,
    )
    _write_latest_filter_evidence(
        evidence_root=args.filter_evidence_root,
        retailer=GUESTINRESIDENCE_RETAILER,
        filter_surfaces_frame=surface_frame,
        filter_observations_frame=observation_frame,
        summary=summary,
    )

    LOGGER.info(
        (
            "Guest in Residence discovery complete: included=%d excluded=%d "
            "listing_rows=%d filter_surfaces=%d filter_observations=%d output=%s"
        ),
        len(included_rows),
        len(excluded_rows),
        len(listing_observations),
        len(filter_surfaces),
        len(filter_observations),
        output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
