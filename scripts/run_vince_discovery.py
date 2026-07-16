from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from urllib.request import Request, urlopen

import polars as pl
from bs4 import BeautifulSoup  # type: ignore[import]

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
from modules.pdp.vince_catalog import (
    VINCE_BRAND_NAME,
    VINCE_CATEGORY_KEY,
    VINCE_CATEGORY_URL,
    VINCE_RETAILER,
    vince_parent_id_from_url,
)
from modules.pdp.vince_filter_discovery import (
    extract_vince_filter_observations_from_html,
    extract_vince_filter_surfaces,
)
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
            "Discover Vince women's sneaker PDPs and persist listing/filter evidence."
        ),
    )
    add_pdp_store_path_argument(parser)
    parser.add_argument(
        "--categories",
        nargs="*",
        default=(VINCE_CATEGORY_KEY,),
        help="Category keys to discover (default: low_top_sneakers).",
    )
    parser.add_argument(
        "--category-url",
        default=VINCE_CATEGORY_URL,
        help=f"Vince sneaker category URL (default: {VINCE_CATEGORY_URL}).",
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
        "--skip-filter-pages",
        action="store_true",
        help="Skip fetching individual filter-result URLs for memberships.",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP timeout for category/filter requests (default: 30).",
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
        return response.read().decode("utf-8", errors="replace")


def _clean_text(value: object | None) -> str:
    return " ".join(str(value or "").split())


def _listing_observations_from_html(
    *,
    category_url: str,
    html: str,
    category_key: str,
) -> list[ListingObservation]:
    soup = BeautifulSoup(html, "lxml")
    observations: list[ListingObservation] = []
    seen_urls: set[str] = set()
    position = 0
    for tile in soup.select(".product"):
        anchor = tile.select_one(".pdp-link a[href*='/product/']")
        if anchor is None:
            anchor = tile.select_one("a[href*='/product/']")
        if anchor is None:
            continue
        href = _clean_text(anchor.get("href"))
        pdp_url = href if href.startswith("http") else f"https://www.vince.com{href}"
        if not pdp_url or pdp_url in seen_urls:
            continue
        parent_id = vince_parent_id_from_url(pdp_url)
        if not parent_id:
            continue
        seen_urls.add(pdp_url)
        position += 1
        product_name = _clean_text(tile.get("data-name")) or _clean_text(
            anchor.get_text(" ", strip=True)
        )
        badge_text = _clean_text(
            " ".join(
                node.get_text(" ", strip=True) for node in tile.select(".product-badge")
            )
        )
        observations.append(
            ListingObservation(
                retailer=VINCE_RETAILER,
                category_key=category_key,
                source_surface="category:sneakers-for-women",
                sort_mode="default",
                page=1,
                position=position,
                pdp_url=pdp_url,
                parent_product_id=parent_id,
                product_name=product_name,
                brand=VINCE_BRAND_NAME,
                has_new_badge="new" in badge_text.casefold().split(),
                listing_url=category_url,
            )
        )
    return observations


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


def _write_run_artifacts(
    *,
    output_dir: Path,
    listing_frame: pl.DataFrame,
    surface_frame: pl.DataFrame,
    observation_frame: pl.DataFrame,
    links: Sequence[str],
    summary: Mapping[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    listing_frame.write_csv(output_dir / "retailer_listing_observations.csv")
    surface_frame.write_csv(output_dir / "retailer_filter_surfaces.csv")
    observation_frame.write_csv(output_dir / "retailer_filter_observations.csv")
    (output_dir / "category_links.json").write_text(
        json.dumps({VINCE_CATEGORY_KEY: list(links)}, indent=2),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(dict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
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
    (evidence_dir / "summary.json").write_text(
        json.dumps(dict(summary), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _filter_page_observations(
    *,
    surfaces: Sequence[FilterSurface],
    timeout: float,
) -> list[FilterObservation]:
    observations: list[FilterObservation] = []
    for surface in surfaces:
        if surface.filter_family not in {"new_now", "color_family", "size"}:
            continue
        try:
            html = _fetch_text(surface.filter_url, timeout=timeout)
        except OSError as exc:
            LOGGER.warning(
                "Unable to fetch Vince filter page %s=%s: %s",
                surface.filter_family,
                surface.filter_value,
                exc,
            )
            continue
        observations.extend(
            extract_vince_filter_observations_from_html(
                filter_surface=surface,
                html=html,
                parent_id_from_url=vince_parent_id_from_url,
            )
        )
    return observations


def _dedupe_filter_observations(
    observations: Sequence[FilterObservation],
) -> list[FilterObservation]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[FilterObservation] = []
    for observation in observations:
        key = (
            observation.parent_product_id or "",
            observation.category_key,
            observation.filter_family,
            observation.filter_value,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(observation)
    return sorted(
        out,
        key=lambda item: (
            item.category_key,
            item.parent_product_id or "",
            item.filter_family,
            item.filter_value,
        ),
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

    categories = canonical_category_keys(VINCE_RETAILER, args.categories)
    if categories != {VINCE_CATEGORY_KEY}:
        raise SystemExit("Vince discovery currently supports low_top_sneakers only.")

    crawl_ts = args.crawl_ts or dt.datetime.now(dt.timezone.utc).isoformat()
    output_dir = (
        args.output_root / VINCE_RETAILER / crawl_ts.replace(":", "").replace("+", "Z")
    )
    category_url = str(args.category_url)
    LOGGER.info("Scanning Vince category: %s", category_url)
    html = _fetch_text(category_url, timeout=args.request_timeout_seconds)
    listing_observations = _listing_observations_from_html(
        category_url=category_url,
        html=html,
        category_key=VINCE_CATEGORY_KEY,
    )
    filter_surfaces = extract_vince_filter_surfaces(
        category_url=category_url,
        html=html,
        category_key=VINCE_CATEGORY_KEY,
    )
    filter_observations: list[FilterObservation] = []
    if not args.skip_filter_pages:
        filter_observations = _filter_page_observations(
            surfaces=filter_surfaces,
            timeout=args.request_timeout_seconds,
        )
        filter_observations = _dedupe_filter_observations(filter_observations)

    links = [observation.pdp_url for observation in listing_observations]
    listing_frame = _listing_frame(listing_observations, crawl_ts)
    surface_frame = _filter_surface_frame(filter_surfaces, crawl_ts)
    observation_frame = _filter_observation_frame(filter_observations, crawl_ts)
    summary = {
        "retailer": VINCE_RETAILER,
        "category_key": VINCE_CATEGORY_KEY,
        "crawl_ts": crawl_ts,
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
        retailer=VINCE_RETAILER,
        category_key=VINCE_CATEGORY_KEY,
        links=links,
    )
    _write_run_artifacts(
        output_dir=output_dir,
        listing_frame=listing_frame,
        surface_frame=surface_frame,
        observation_frame=observation_frame,
        links=links,
        summary=summary,
    )
    _write_latest_filter_evidence(
        evidence_root=args.filter_evidence_root,
        retailer=VINCE_RETAILER,
        filter_surfaces_frame=surface_frame,
        filter_observations_frame=observation_frame,
        summary=summary,
    )
    LOGGER.info(
        (
            "Vince discovery complete: links=%d filter_surfaces=%d "
            "filter_observations=%d output=%s"
        ),
        len(links),
        len(filter_surfaces),
        len(filter_observations),
        output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
