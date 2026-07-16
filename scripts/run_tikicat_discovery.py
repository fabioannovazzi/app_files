from __future__ import annotations

import argparse
import datetime as dt
import html
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
from modules.pdp.review_constants import (
    add_pdp_store_path_argument,
    enforce_default_pdp_store_path,
)
from modules.pdp.store import PDPStore
from modules.pdp.tikicat_catalog import (
    TIKICAT_BRAND_NAME,
    TIKICAT_CATEGORY_KEY,
    TIKICAT_RETAILER,
    TIKICAT_WET_CAT_FOOD_URL,
    tikicat_feature_lines_from_product,
    tikicat_is_wet_cat_food_product,
    tikicat_parent_id_from_url,
    tikicat_product_text,
    tikicat_term_values_for_product,
)
from modules.pdp.tikicat_filter_discovery import (
    build_tikicat_filter_records,
    tikicat_site_filters_for_product,
)
from modules.utilities.secrets_loader import load_env_from_secrets_file

LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT_ROOT = Path("data/pdp/discovery_runs")
DEFAULT_LINKS_PATH = Path("data/pdp/links.json")
DEFAULT_FILTER_EVIDENCE_ROOT = Path("data/pdp/retailer_filter_evidence")
TIKICAT_PRODUCTS_API = "https://tikipets.com/wp-json/wp/v2/product"
TIKICAT_TERMS_API = "https://tikipets.com/wp-json/wp/v2/product_cat"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover Tiki Cat wet cat food products from the official Tiki Pets "
            "WordPress product API and persist listing/filter evidence."
        ),
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--categories",
        nargs="*",
        default=(TIKICAT_CATEGORY_KEY,),
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
        help="HTTP timeout for Tiki Pets API requests (default: 30).",
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


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": USER_AGENT,
        }
    )
    return session


def _fetch_json(
    session: requests.Session,
    url: str,
    *,
    params: Mapping[str, object],
    timeout: float,
) -> tuple[object, Mapping[str, str]]:
    response = session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json(), response.headers


def _fetch_terms(
    session: requests.Session,
    *,
    timeout: float,
) -> dict[int, Mapping[str, object]]:
    payload, _headers = _fetch_json(
        session,
        TIKICAT_TERMS_API,
        params={"per_page": 100},
        timeout=timeout,
    )
    if not isinstance(payload, list):
        raise RuntimeError("Tiki Pets product_cat API did not return a list.")
    terms: dict[int, Mapping[str, object]] = {}
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        try:
            term_id = int(item.get("id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        terms[term_id] = item
    return terms


def _fetch_products(
    session: requests.Session,
    *,
    timeout: float,
) -> list[tuple[int, int, Mapping[str, object]]]:
    rows: list[tuple[int, int, Mapping[str, object]]] = []
    page = 1
    while True:
        payload, headers = _fetch_json(
            session,
            TIKICAT_PRODUCTS_API,
            params={"per_page": 100, "page": page, "_embed": 1},
            timeout=timeout,
        )
        if not isinstance(payload, list):
            raise RuntimeError("Tiki Pets product API did not return a list.")
        for position, item in enumerate(payload, start=1):
            if isinstance(item, Mapping):
                rows.append((page, position, item))
        total_pages = int(headers.get("X-WP-TotalPages") or "1")
        if page >= total_pages or not payload:
            break
        page += 1
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
        json.dumps({TIKICAT_CATEGORY_KEY: list(links)}, indent=2),
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


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    _configure_logging(args.log_level)
    load_env_from_secrets_file()
    pdp_store_path = enforce_default_pdp_store_path(args.pdp_store_path)
    _require_postgres(pdp_store_path)

    categories = canonical_category_keys(TIKICAT_RETAILER, args.categories)
    if categories != {TIKICAT_CATEGORY_KEY}:
        raise SystemExit("Tiki Cat discovery currently supports wet_cat_food only.")

    crawl_ts = args.crawl_ts or dt.datetime.now(dt.timezone.utc).isoformat()
    output_dir = (
        args.output_root
        / TIKICAT_RETAILER
        / crawl_ts.replace(":", "").replace("+", "Z")
    )
    session = _session()
    term_lookup = _fetch_terms(session, timeout=args.request_timeout_seconds)
    product_rows = _fetch_products(session, timeout=args.request_timeout_seconds)

    included_rows: list[dict[str, object]] = []
    excluded_rows: list[dict[str, object]] = []
    listing_observations: list[ListingObservation] = []
    parent_rows_for_filters: list[dict[str, object]] = []
    links: list[str] = []
    seen_links: set[str] = set()

    for page, position, product in product_rows:
        product_url = str(product.get("link") or "").strip()
        parent_id = tikicat_parent_id_from_url(product_url)
        title_payload = product.get("title")
        title = (
            html.unescape(str(title_payload.get("rendered") or "")).strip()
            if isinstance(title_payload, Mapping)
            else html.unescape(str(title_payload or "")).strip()
        )
        term_values = tikicat_term_values_for_product(
            product,
            term_lookup=term_lookup,
        )
        row = {
            "parent_product_id": parent_id,
            "title": title,
            "pdp_url": product_url,
            "texture": term_values.get("texture"),
            "product_lines": "|".join(
                str(item) for item in term_values.get("product_lines") or ()
            ),
            "lifestage": term_values.get("lifestage"),
            "product_assortment": term_values.get("product_assortment"),
        }
        if not parent_id or not tikicat_is_wet_cat_food_product(
            product,
            term_lookup=term_lookup,
        ):
            excluded_rows.append({**row, "scope_reason": "not wet cat food"})
            continue

        site_filters = tikicat_site_filters_for_product(
            product,
            term_lookup=term_lookup,
        )
        included_rows.append(
            {
                **row,
                "scope_reason": "official Tiki Cat wet-food product",
                "feature_count": len(tikicat_feature_lines_from_product(product)),
                "text_length": len(tikicat_product_text(product)),
            }
        )
        if product_url not in seen_links:
            seen_links.add(product_url)
            links.append(product_url)
        listing_observations.append(
            ListingObservation(
                retailer=TIKICAT_RETAILER,
                category_key=TIKICAT_CATEGORY_KEY,
                source_surface="wp_product_api",
                sort_mode="default",
                page=page,
                position=position,
                pdp_url=product_url,
                parent_product_id=parent_id,
                product_name=title,
                brand=TIKICAT_BRAND_NAME,
                has_new_badge=False,
                listing_url=TIKICAT_WET_CAT_FOOD_URL,
            )
        )
        parent_rows_for_filters.append(
            {
                "parent_product_id": parent_id,
                "pdp_url": product_url,
                "category_key": TIKICAT_CATEGORY_KEY,
                "extras": {"site_filters": site_filters},
            }
        )

    filter_surfaces, filter_observations = build_tikicat_filter_records(
        parent_rows_for_filters,
        allowed_categories=(TIKICAT_CATEGORY_KEY,),
    )
    listing_df = _listing_frame(listing_observations, crawl_ts)
    surface_df = _filter_surface_frame(filter_surfaces, crawl_ts)
    observation_df = _filter_observation_frame(filter_observations, crawl_ts)

    summary = {
        "retailer": TIKICAT_RETAILER,
        "category_key": TIKICAT_CATEGORY_KEY,
        "crawl_ts": crawl_ts,
        "source_product_rows": len(product_rows),
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
        retailer=TIKICAT_RETAILER,
        category_key=TIKICAT_CATEGORY_KEY,
        links=links,
    )
    _write_run_artifacts(
        output_dir=output_dir,
        listing_frame=listing_df,
        surface_frame=surface_df,
        observation_frame=observation_df,
        included_rows=included_rows,
        excluded_rows=excluded_rows,
        links=links,
        summary=summary,
    )
    _write_latest_filter_evidence(
        evidence_root=args.filter_evidence_root,
        retailer=TIKICAT_RETAILER,
        filter_surfaces_frame=surface_df,
        filter_observations_frame=observation_df,
        summary=summary,
    )

    LOGGER.info(
        (
            "Tiki Cat discovery complete: included=%d excluded=%d "
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
