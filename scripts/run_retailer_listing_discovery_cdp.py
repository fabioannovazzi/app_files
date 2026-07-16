from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import logging
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qsl, quote, urlsplit
from urllib.request import urlopen

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.category_keys import canonical_category_key, canonical_category_keys
from modules.pdp.cdp_failure_diagnostics import write_cdp_failure_bundle
from modules.pdp.cdp_listing_engine import CapturedListingPage, CDPListingEngine
from modules.pdp.cdp_retailer_strategy import strategy_for_retailer
from modules.pdp.discovery_classification import (
    assign_new_rest_from_newest,
    assign_pareto_from_most_popular,
    build_parent_sort_snapshot,
)
from modules.pdp.kiko_filter_discovery import crawl_kiko_filter_observations
from modules.pdp.models import FilterObservation, FilterSurface, ListingObservation
from modules.pdp.profile import PDPProfile
from modules.pdp.profile_loader import iter_profile_summaries, load_profile
from modules.pdp.review_constants import add_pdp_store_path_argument
from modules.pdp.run_status_notifications import (
    resolve_notification_recipients,
    send_run_notification,
)
from modules.pdp.sort_sequence_quality import (
    EXCLUDED_RANKED_SORT_MODES,
    build_sort_sequence_quality_report,
    normalize_ranked_sort_modes,
)
from modules.pdp.store import PDPStore
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.utils import get_row_count, get_schema_and_column_names

LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT_ROOT = Path("data/pdp/discovery_runs/cdp")
DEFAULT_LINKS_PATH = Path("data/pdp/links.json")
DEFAULT_FILTER_EVIDENCE_ROOT = Path("data/pdp/retailer_filter_evidence")
DEFAULT_ATTRIBUTE_CACHE_ROOT = Path("data/pdp/pdp_attribute_cache")
CHECKPOINT_FILENAME = "resume_checkpoint.json"
CHEWY_SORT_GUARD_VERSION = "widget_click_pagination_v4"
CHEWY_DEFAULT_FILTER_FAMILIES = (
    "lifestage",
    "food texture",
    "flavor",
    "special diet",
    "health feature",
    "package count",
    "packaging type",
)
AMAZON_DEFAULT_FILTER_FAMILIES = (
    "flavor",
    "packaging type",
    "life stage",
    "special diet",
    "food texture",
    "package count",
    "health feature",
    "brand",
)
PRESERVED_LISTING_SORT_MODES_BY_RETAILER = {
    "lorealparis": frozenset({"default"}),
    "saksfifthavenue": frozenset({"sale_first", "sales_first"}),
}
PDP_LANDING_PATH_MARKERS_BY_RETAILER = {
    "saksfifthavenue": ("/product/",),
}
MANUAL_INTERVENTION_CLASSIFICATIONS = {
    "cloudflare_challenge",
    "access_denied_interstitial",
    "kasada_kpsdk_challenge",
}
FATAL_DISCOVERY_FAILURE_CLASSIFICATIONS_BY_RETAILER: dict[str, set[str]] = {
    "chewy": {
        "kasada_kpsdk_challenge",
        "empty_or_error_page",
        "no_products_detected",
    },
}
STALE_SORT_SEQUENCE_RETRY_RETAILERS = frozenset({"chewy", "saksfifthavenue"})
STALE_SORT_SEQUENCE_RETRY_ATTEMPTS = 2
STALE_SORT_SEQUENCE_MIN_PRODUCTS = 5
ManualNavigationLoader = Callable[[str, str, str, int], None]
ManualSortConfirmer = Callable[[str, str, str, int], None]
_CHEWY_PDP_ID_IN_PATH = re.compile(r"/dp/(\d+)(?:/)?$", re.IGNORECASE)


class FatalRetailerDiscoveryError(RuntimeError):
    """Abort the current discovery run because the browser session is unusable."""


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run browser-backed listing discovery over an attached Chrome CDP session "
            "and persist category/filter/sort artifacts."
        ),
    )
    parser.add_argument(
        "--retailer",
        required=True,
        help=(
            "Retailer to crawl (currently: saloncentric, amazon, "
            "cosmoprofbeauty, saksfifthavenue, chewy, kiko, lorealparis)."
        ),
    )
    parser.add_argument(
        "--remote-url",
        default="http://localhost:9222",
        help="Chrome DevTools endpoint (start Chrome with --remote-debugging-port).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Output root for run metadata and optional audit artifacts.",
    )
    parser.add_argument(
        "--write-csv-artifacts",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Write CSV audit sidecars for listing/filter observations "
            "(default: disabled; PDP store and links JSON are the primary outputs)."
        ),
    )
    parser.add_argument(
        "--links-path",
        type=Path,
        default=DEFAULT_LINKS_PATH,
        help="Links manifest path to update (default: data/pdp/links.json).",
    )
    add_pdp_store_path_argument(parser, dest="pdp_store_path")
    parser.add_argument(
        "--filter-evidence-root",
        type=Path,
        default=DEFAULT_FILTER_EVIDENCE_ROOT,
        help=(
            "Latest retailer filter evidence root. Kiko writes first-choice "
            "filter evidence here (default: data/pdp/retailer_filter_evidence)."
        ),
    )
    parser.add_argument(
        "--attribute-cache-root",
        type=Path,
        default=DEFAULT_ATTRIBUTE_CACHE_ROOT,
        help=(
            "PDP attribute cache root used to map Kiko Algolia variant hits to "
            "parent products (default: data/pdp/pdp_attribute_cache)."
        ),
    )
    parser.add_argument(
        "--resume-run-dir",
        type=Path,
        default=None,
        help=(
            "Resume a previously interrupted discovery run from its run directory "
            f"using {CHECKPOINT_FILENAME}."
        ),
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Resume the latest interrupted run for the retailer from "
            f"{CHECKPOINT_FILENAME} under the output root."
        ),
    )
    parser.add_argument(
        "--locale",
        default="en-us",
        help="Locale used to expand profile URL placeholders such as {locale}.",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="Optional category keys to limit the run.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        help="Maximum listing pages to crawl per base category/sort surface.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=2.0,
        help="Delay between PLP pages/surfaces.",
    )
    parser.add_argument(
        "--sort-modes",
        nargs="*",
        default=None,
        help="Sort modes to crawl. Defaults to the retailer strategy defaults.",
    )
    parser.add_argument(
        "--chewy-manual-sort-widget",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "For Chewy ranked category surfaces, load the page and wait for the "
            "operator to set the Sort By widget instead of clicking it automatically."
        ),
    )
    parser.add_argument(
        "--recent-share",
        type=float,
        default=0.20,
        help="Share to label as new based on the retailer recent/new-arrivals surface (default: 0.20).",
    )
    parser.add_argument(
        "--capture-filters",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Capture filter surfaces and crawl filter memberships (default: enabled).",
    )
    parser.add_argument(
        "--filter-families",
        nargs="*",
        default=None,
        help="Optional override for captured filter families.",
    )
    parser.add_argument(
        "--filter-max-pages",
        type=int,
        default=3,
        help="Maximum listing pages to crawl for each filter surface.",
    )
    parser.add_argument(
        "--filter-surface-limit",
        type=int,
        default=0,
        help=(
            "Optional cap on filter surfaces crawled per category after extraction "
            "(0 means no cap). Useful for retailer smoke tests."
        ),
    )
    parser.add_argument(
        "--materialize-filter-attributes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Materialize captured retailer_filter_observations into "
            "pdp_attribute_values after persistence (default: enabled)."
        ),
    )
    parser.add_argument(
        "--filter-request-timeout-seconds",
        type=float,
        default=15.0,
        help="HTTP timeout for non-CDP filter membership requests such as Kiko Algolia.",
    )
    parser.add_argument(
        "--reuse-open-tab",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Reuse the first existing page in the attached Chrome context "
            "(default: enabled)."
        ),
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45_000,
        help="Navigation timeout for Playwright operations (milliseconds).",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=4_000,
        help="Wait after navigation before collecting links (milliseconds).",
    )
    parser.add_argument(
        "--scroll-steps",
        type=int,
        default=40,
        help="How many scroll passes to run before stopping (default: 40).",
    )
    parser.add_argument(
        "--max-idle-scrolls",
        type=int,
        default=6,
        help="Stop scrolling after this many idle passes (default: 6).",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=0,
        help="Stop after collecting this many links per page (0 means no cap).",
    )
    parser.add_argument(
        "--manual-navigation",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Prompt before each listing/filter surface and capture the already-loaded "
            "Chrome tab instead of navigating through CDP. Use for retailers such as "
            "Chewy where human URL entry renders but CDP navigation is challenged."
        ),
    )
    parser.add_argument(
        "--manual-navigation-notify",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Send an ACTION REQUIRED run notification for each manual-navigation "
            "prompt, using the existing PDP notification email configuration."
        ),
    )
    parser.add_argument(
        "--manual-navigation-crawl-filter-memberships",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "In manual-navigation mode, also prompt and crawl every discovered "
            "filter value URL. By default manual mode captures filter surfaces "
            "but skips filter membership crawls to avoid dozens of paste prompts."
        ),
    )
    parser.add_argument(
        "--manual-navigation-auto-paste",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "In manual-navigation mode, automatically paste each requested URL "
            "into the visible Windows Chrome window using OS-level clipboard/"
            "keyboard automation, then wait for CDP to report that URL."
        ),
    )
    parser.add_argument(
        "--manual-navigation-auto-paste-wait-seconds",
        type=float,
        default=60.0,
        help="Seconds to wait for Chrome to reach an auto-pasted URL (default: 60).",
    )
    parser.add_argument(
        "--manual-navigation-auto-paste-attempts",
        type=int,
        default=3,
        help="How many times to retry Windows auto-paste navigation before failing.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    return parser.parse_args(argv)


def _apply_retailer_defaults(args: argparse.Namespace) -> argparse.Namespace:
    """Apply retailer-specific CLI presets while preserving explicit overrides."""

    retailer = str(args.retailer or "").strip().lower()
    if retailer == "chewy":
        if args.max_pages == 10:
            args.max_pages = 100
        if args.filter_max_pages == 3:
            args.filter_max_pages = 100
        if args.delay_seconds == 2.0:
            args.delay_seconds = 1.0
        if args.wait_ms == 4_000:
            args.wait_ms = 3_000
        if args.max_idle_scrolls == 6:
            args.max_idle_scrolls = 2
        if args.filter_families is None:
            args.filter_families = list(CHEWY_DEFAULT_FILTER_FAMILIES)
        if args.manual_navigation is None:
            args.manual_navigation = False
        if args.manual_navigation_auto_paste is None:
            args.manual_navigation_auto_paste = False
        if args.manual_navigation_crawl_filter_memberships is None:
            args.manual_navigation_crawl_filter_memberships = True
        if args.manual_navigation_auto_paste_wait_seconds == 60.0:
            args.manual_navigation_auto_paste_wait_seconds = 20.0
        if args.manual_navigation_auto_paste_attempts == 3:
            args.manual_navigation_auto_paste_attempts = 5
        if args.chewy_manual_sort_widget is None:
            args.chewy_manual_sort_widget = False
    elif retailer == "amazon":
        if args.filter_families is None:
            args.filter_families = list(AMAZON_DEFAULT_FILTER_FAMILIES)
        if args.manual_navigation is None:
            args.manual_navigation = False
        if args.manual_navigation_auto_paste is None:
            args.manual_navigation_auto_paste = False
        if args.manual_navigation_crawl_filter_memberships is None:
            args.manual_navigation_crawl_filter_memberships = False
        if args.chewy_manual_sort_widget is None:
            args.chewy_manual_sort_widget = False
    else:
        if args.manual_navigation is None:
            args.manual_navigation = False
        if args.manual_navigation_auto_paste is None:
            args.manual_navigation_auto_paste = False
        if args.manual_navigation_crawl_filter_memberships is None:
            args.manual_navigation_crawl_filter_memberships = False
        if args.chewy_manual_sort_widget is None:
            args.chewy_manual_sort_widget = False
    return args


def _normalize_categories(
    values: Sequence[str] | None,
    *,
    retailer: str,
) -> set[str] | None:
    return canonical_category_keys(retailer, values)


def _load_profiles(retailer: str, categories: set[str] | None) -> list[PDPProfile]:
    strategy = strategy_for_retailer(retailer)
    matched: list[PDPProfile] = []
    for summary in iter_profile_summaries():
        if summary.retailer.lower() != retailer.lower():
            continue
        profile = load_profile(summary.profile_name)
        category_key = strategy.profile_to_category_key(profile.profile_name).lower()
        if categories is not None and category_key not in categories:
            continue
        matched.append(profile)
    return matched


def _profile_category_urls(profile: PDPProfile, *, locale: str) -> tuple[str, ...]:
    return tuple(
        str(url).strip().replace("{locale}", locale)
        for url in profile.category_urls
        if str(url).strip()
    )


def _category_links_from_observations(
    observations: Sequence[ListingObservation | FilterObservation],
    *,
    category_keys: set[str],
) -> dict[str, list[str]]:
    """Return PDP URL manifest entries from category and filter observations."""

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
            return {
                retailer: {
                    str(category_key): [
                        str(link) for link in links if isinstance(link, str)
                    ]
                    for category_key, links in categories.items()
                    if isinstance(links, list)
                }
            }
    result: dict[str, dict[str, list[str]]] = {}
    for retailer, categories in payload.items():
        if not isinstance(categories, Mapping):
            continue
        result[str(retailer).lower()] = {
            str(category_key): [str(link) for link in links if isinstance(link, str)]
            for category_key, links in categories.items()
            if isinstance(links, list)
        }
    return result


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


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _checkpoint_path(run_dir: Path) -> Path:
    return run_dir / CHECKPOINT_FILENAME


def _latest_checkpoint_run_dir(*, output_root: Path, retailer: str) -> Path | None:
    retailer_root = output_root / retailer.strip().lower()
    if not retailer_root.is_dir():
        return None
    candidates = [
        path
        for path in retailer_root.iterdir()
        if path.is_dir() and _checkpoint_path(path).is_file()
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.name)[-1]


def _listing_surface_checkpoint_key(
    *,
    category_key: str,
    source_surface: str,
    sort_mode: str,
    surface_url: str,
) -> str:
    return json.dumps(
        ["listing", category_key, source_surface, sort_mode, surface_url],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _filter_surface_checkpoint_key(surface: FilterSurface) -> str:
    return json.dumps(
        [
            "filter",
            surface.category_key,
            surface.filter_family,
            surface.filter_value,
            surface.filter_url,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _bool_from_payload(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _listing_observation_from_payload(
    payload: Mapping[str, object],
) -> ListingObservation:
    retailer = str(payload.get("retailer", ""))
    return ListingObservation(
        retailer=retailer,
        category_key=canonical_category_key(retailer, payload.get("category_key", "")),
        source_surface=str(payload.get("source_surface", "")),
        sort_mode=str(payload.get("sort_mode", "")),
        page=int(payload.get("page", 0) or 0),
        position=int(payload.get("position", 0) or 0),
        pdp_url=str(payload.get("pdp_url", "")),
        parent_product_id=_optional_text(payload.get("parent_product_id")),
        product_name=_optional_text(payload.get("product_name")),
        brand=_optional_text(payload.get("brand")),
        has_new_badge=_bool_from_payload(payload.get("has_new_badge", False)),
        listing_url=_optional_text(payload.get("listing_url")),
    )


def _filter_surface_from_payload(payload: Mapping[str, object]) -> FilterSurface:
    retailer = str(payload.get("retailer", ""))
    return FilterSurface(
        retailer=retailer,
        category_key=canonical_category_key(retailer, payload.get("category_key", "")),
        filter_family=str(payload.get("filter_family", "")),
        filter_value=str(payload.get("filter_value", "")),
        filter_url=str(payload.get("filter_url", "")),
        filter_label=_optional_text(payload.get("filter_label")),
    )


def _filter_observation_from_payload(
    payload: Mapping[str, object],
) -> FilterObservation:
    retailer = str(payload.get("retailer", ""))
    return FilterObservation(
        retailer=retailer,
        category_key=canonical_category_key(retailer, payload.get("category_key", "")),
        filter_family=str(payload.get("filter_family", "")),
        filter_value=str(payload.get("filter_value", "")),
        source_surface=str(payload.get("source_surface", "")),
        pdp_url=str(payload.get("pdp_url", "")),
        parent_product_id=_optional_text(payload.get("parent_product_id")),
        page=int(payload.get("page", 0) or 0),
        position=int(payload.get("position", 0) or 0),
        listing_url=_optional_text(payload.get("listing_url")),
    )


def _write_discovery_checkpoint(
    *,
    output_dir: Path,
    crawl_ts: str,
    retailer: str,
    categories: Sequence[str],
    sort_modes: Sequence[str],
    observations: Sequence[ListingObservation],
    filter_surfaces: Sequence[FilterSurface],
    filter_observations: Sequence[FilterObservation],
    completed_surface_keys: set[str],
) -> Path:
    path = _checkpoint_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "crawl_ts": crawl_ts,
        "retailer": retailer,
        "categories": list(categories),
        "sort_modes": list(sort_modes),
        "listing_observations": [asdict(observation) for observation in observations],
        "filter_surfaces": [asdict(surface) for surface in filter_surfaces],
        "filter_observations": [
            asdict(observation) for observation in filter_observations
        ],
        "completed_surface_keys": sorted(completed_surface_keys),
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if retailer == "chewy":
        payload["chewy_sort_guard_version"] = CHEWY_SORT_GUARD_VERSION
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)
    return path


def _load_discovery_checkpoint(
    run_dir: Path,
) -> tuple[
    str,
    list[ListingObservation],
    list[FilterSurface],
    list[FilterObservation],
    set[str],
    dict[str, object],
]:
    path = _checkpoint_path(run_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Checkpoint is not a JSON object: {path}")

    listing_payloads = payload.get("listing_observations", [])
    surface_payloads = payload.get("filter_surfaces", [])
    filter_payloads = payload.get("filter_observations", [])
    completed_payloads = payload.get("completed_surface_keys", [])
    if not isinstance(listing_payloads, list):
        raise ValueError(f"Invalid listing observations in checkpoint: {path}")
    if not isinstance(surface_payloads, list):
        raise ValueError(f"Invalid filter surfaces in checkpoint: {path}")
    if not isinstance(filter_payloads, list):
        raise ValueError(f"Invalid filter observations in checkpoint: {path}")
    if not isinstance(completed_payloads, list):
        raise ValueError(f"Invalid completed keys in checkpoint: {path}")

    checkpoint_retailer = str(payload.get("retailer", ""))

    return (
        str(payload.get("crawl_ts", "")),
        [
            _listing_observation_from_payload(row)
            for row in listing_payloads
            if isinstance(row, Mapping)
        ],
        [
            _filter_surface_from_payload(row)
            for row in surface_payloads
            if isinstance(row, Mapping)
        ],
        [
            _filter_observation_from_payload(row)
            for row in filter_payloads
            if isinstance(row, Mapping)
        ],
        {
            _canonical_checkpoint_key(checkpoint_retailer, key)
            for key in completed_payloads
            if str(key)
        },
        dict(payload),
    )


def _canonical_checkpoint_key(retailer: str, key: object) -> str:
    try:
        payload = json.loads(str(key))
    except json.JSONDecodeError:
        return str(key)
    if (
        isinstance(payload, list)
        and len(payload) > 1
        and payload[0] in {"listing", "filter"}
    ):
        payload[1] = canonical_category_key(retailer, payload[1])
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return str(key)


def _observations_to_frame(
    observations: Sequence[ListingObservation],
    *,
    crawl_ts: str,
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
            }
        )
    return pl.DataFrame(rows)


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


def _filter_surfaces_to_frame(
    surfaces: Sequence[FilterSurface], *, crawl_ts: str
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


def _classification_to_frame(
    observations: Sequence[ListingObservation],
    *,
    crawl_ts: str,
    recent_share: float,
) -> pl.DataFrame:
    snapshot = build_parent_sort_snapshot(observations)
    if snapshot.is_empty():
        return pl.DataFrame(
            schema={
                "crawl_ts": pl.Utf8,
                "retailer": pl.Utf8,
                "category_key": pl.Utf8,
                "parent_product_id": pl.Utf8,
                "brand": pl.Utf8,
                "product_name": pl.Utf8,
                "pdp_url": pl.Utf8,
                "has_new_badge": pl.Boolean,
                "new_rest_class": pl.Utf8,
                "pareto_class": pl.Utf8,
            }
        )
    retailer = (
        str(observations[0].retailer or "").strip().lower() if observations else ""
    )
    strategy = strategy_for_retailer(retailer)
    new_rest = assign_new_rest_from_newest(
        snapshot,
        newest_sort_mode=strategy.recent_sort_mode,
        new_share=recent_share,
    )
    pareto = assign_pareto_from_most_popular(
        snapshot,
        popular_sort_mode=strategy.popularity_sort_mode,
    )
    key_cols = ["retailer", "category_key", "parent_product_id"]
    base = snapshot.select(
        [
            "retailer",
            "category_key",
            "parent_product_id",
            "brand",
            "product_name",
            "pdp_url",
            "has_new_badge",
        ]
    ).unique(subset=key_cols, keep="first")
    frame = (
        base.join(
            new_rest.select(key_cols + ["new_rest_class"]),
            on=key_cols,
            how="left",
        )
        .join(
            pareto.select(key_cols + ["pareto_class"]),
            on=key_cols,
            how="left",
        )
        .with_columns(pl.lit(crawl_ts).alias("crawl_ts"))
    )
    return frame.select(
        [
            "crawl_ts",
            "retailer",
            "category_key",
            "parent_product_id",
            "brand",
            "product_name",
            "pdp_url",
            "has_new_badge",
            "new_rest_class",
            "pareto_class",
        ]
    )


def _listing_observation_identity(observation: ListingObservation) -> str:
    return str(observation.parent_product_id or observation.pdp_url or "").strip()


def _is_ranked_sort_mode(sort_mode: str | None) -> bool:
    normalized = str(sort_mode or "").strip().lower()
    return bool(normalized) and normalized not in EXCLUDED_RANKED_SORT_MODES


def _normalize_listing_surface_sort_modes(
    retailer: str,
    sort_modes: Sequence[str],
) -> tuple[str, ...]:
    normalized: list[str] = list(normalize_ranked_sort_modes(sort_modes))
    seen = {str(sort_mode or "").strip().lower() for sort_mode in normalized}
    preserved = PRESERVED_LISTING_SORT_MODES_BY_RETAILER.get(
        str(retailer or "").strip().lower(),
        frozenset(),
    )
    for sort_mode in sort_modes:
        value = str(sort_mode or "").strip()
        key = value.lower()
        if not value or key in seen or key not in preserved:
            continue
        normalized.append(value)
        seen.add(key)
    return tuple(normalized)


def _limit_filter_surfaces(
    surfaces: Sequence[FilterSurface],
    *,
    limit: int,
) -> list[FilterSurface]:
    """Return filter surfaces capped for smoke runs while balancing families."""

    surface_list = list(surfaces)
    if limit <= 0:
        return surface_list
    grouped: dict[str, list[FilterSurface]] = {}
    family_order: list[str] = []
    for surface in surface_list:
        family = str(surface.filter_family or "").strip()
        if family not in grouped:
            grouped[family] = []
            family_order.append(family)
        grouped[family].append(surface)

    selected: list[FilterSurface] = []
    while len(selected) < limit:
        progressed = False
        for family in family_order:
            family_surfaces = grouped[family]
            if not family_surfaces:
                continue
            selected.append(family_surfaces.pop(0))
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def _ordered_observation_sequence(
    observations: Sequence[ListingObservation],
) -> list[str]:
    ordered = sorted(
        observations,
        key=lambda observation: (
            int(observation.page),
            int(observation.position),
            str(observation.pdp_url or ""),
        ),
    )
    return [
        identity
        for observation in ordered
        if (identity := _listing_observation_identity(observation))
    ]


def _category_sort_sequences_from_observations(
    observations: Sequence[ListingObservation],
    *,
    category_key: str,
    source_surface: str,
) -> dict[str, list[str]]:
    grouped: dict[str, list[ListingObservation]] = {}
    for observation in observations:
        sort_mode = str(observation.sort_mode or "").strip()
        if not _is_ranked_sort_mode(sort_mode):
            continue
        if observation.category_key != category_key:
            continue
        if observation.source_surface != source_surface:
            continue
        grouped.setdefault(sort_mode, []).append(observation)
    return {
        sort_mode: _ordered_observation_sequence(rows)
        for sort_mode, rows in grouped.items()
    }


def _matching_identical_prior_sort_sequence(
    sequence: Sequence[str],
    prior_sequences: Mapping[str, Sequence[str]],
    *,
    current_sort_mode: str,
    min_products: int = STALE_SORT_SEQUENCE_MIN_PRODUCTS,
) -> str | None:
    current_key = str(current_sort_mode or "").strip().lower()
    if len(sequence) < min_products:
        return None
    for prior_sort_mode, prior_sequence in sorted(prior_sequences.items()):
        if str(prior_sort_mode or "").strip().lower() == current_key:
            continue
        if len(prior_sequence) < min_products:
            continue
        if list(sequence) == list(prior_sequence):
            return prior_sort_mode
    return None


def _first_identical_sort_sequence_pair(
    sequences: Mapping[str, Sequence[str]],
    *,
    min_products: int = STALE_SORT_SEQUENCE_MIN_PRODUCTS,
) -> tuple[str, str] | None:
    prior_sequences: dict[str, Sequence[str]] = {}
    for sort_mode, sequence in sorted(sequences.items()):
        match = _matching_identical_prior_sort_sequence(
            sequence,
            prior_sequences,
            current_sort_mode=sort_mode,
            min_products=min_products,
        )
        if match is not None:
            return match, sort_mode
        prior_sequences[sort_mode] = sequence
    return None


def _crawl_surface(
    *,
    engine: CDPListingEngine,
    strategy,
    profile: PDPProfile,
    category_key: str,
    surface_url: str,
    source_surface: str,
    sort_mode: str,
    max_pages: int,
    delay_seconds: float,
    failure_artifact_root: Path,
    manual_navigation_loader: ManualNavigationLoader | None = None,
    manual_sort_confirmer: ManualSortConfirmer | None = None,
    force_navigation: bool = False,
    sort_control_mode: str = "set",
) -> tuple[list[ListingObservation], CapturedListingPage | None, bool]:
    observations: list[ListingObservation] = []
    first_capture: CapturedListingPage | None = None
    completed = False
    current_url = surface_url
    current_page = 1
    capture_loaded_tab = False
    seen_urls: set[str] = set()
    visited_page_urls: set[str] = set()
    while current_url and current_page <= max_pages:
        if manual_navigation_loader is not None and not capture_loaded_tab:
            try:
                manual_navigation_loader(
                    current_url,
                    category_key,
                    source_surface,
                    current_page,
                )
            except RuntimeError as exc:
                raise FatalRetailerDiscoveryError(
                    "Manual navigation failed before capture for "
                    f"{strategy.retailer} / {category_key} ({source_surface} "
                    f"page {current_page}). Fix or restart Chrome, then resume "
                    f"with --resume. Details: {exc}"
                ) from exc
        if manual_navigation_loader is not None and manual_sort_confirmer is not None:
            manual_sort_confirmer(
                category_key,
                source_surface,
                sort_mode,
                current_page,
            )
        capture = engine.capture_listing_page(
            url=current_url,
            selector=strategy.selector,
            retailer=strategy.retailer,
            category_key=category_key,
            sort_mode=sort_mode,
            load_more_texts=strategy.load_more_texts,
            navigate=manual_navigation_loader is None and not capture_loaded_tab,
            force_navigation=(
                force_navigation
                and manual_navigation_loader is None
                and not capture_loaded_tab
            ),
            sort_control_mode=sort_control_mode,
        )
        capture_loaded_tab = False
        if capture is None:
            LOGGER.warning("Failed to capture surface %s", current_url)
            break
        if first_capture is None:
            first_capture = capture
        if _chewy_filter_redirected_to_base_category(
            retailer=strategy.retailer,
            source_surface=source_surface,
            requested_url=current_url,
            final_url=capture.final_url,
        ):
            LOGGER.warning(
                "Skipping Chewy filter surface %s because requested filter URL %s "
                "landed on base listing URL %s.",
                source_surface,
                current_url,
                capture.final_url,
            )
            completed = True
            break
        if _is_unexpected_pdp_landing_url(
            retailer=strategy.retailer,
            url=capture.final_url,
        ):
            LOGGER.warning(
                "Stopping %s surface %s because listing URL %s landed on PDP %s.",
                strategy.retailer,
                source_surface,
                current_url,
                capture.final_url,
            )
            if observations:
                completed = True
            else:
                _write_capture_failure_bundle(
                    failure_artifact_root=failure_artifact_root,
                    capture=capture,
                    strategy=strategy,
                    category_key=category_key,
                    reason="pdp_landing",
                )
            break
        if capture.final_url in visited_page_urls:
            completed = True
            break
        visited_page_urls.add(capture.final_url)
        page_observations = strategy.build_observations(
            candidates=capture.candidates,
            category_key=category_key,
            source_surface=source_surface,
            sort_mode=sort_mode,
            page_number=current_page,
            listing_url=capture.final_url,
            profile=profile,
            seen_urls=seen_urls,
        )
        observations.extend(page_observations)
        if not page_observations:
            if observations:
                LOGGER.info(
                    "No new listing observations produced for %s / %s (%s) at %s after %d accumulated rows; treating surface as complete.",
                    strategy.retailer,
                    category_key,
                    sort_mode,
                    capture.final_url or capture.requested_url,
                    len(observations),
                )
                completed = True
                break
            bundle_dir = _write_capture_failure_bundle(
                failure_artifact_root=failure_artifact_root,
                capture=capture,
                strategy=strategy,
                category_key=category_key,
                reason="no_observations",
            )
            LOGGER.warning(
                "No listing observations produced for %s / %s (%s); wrote failure bundle to %s",
                strategy.retailer,
                category_key,
                sort_mode,
                bundle_dir,
            )
            diagnosis = _read_failure_diagnosis(bundle_dir)
            classification = _failure_classification(diagnosis)
            if _should_abort_after_failure_classification(
                retailer=strategy.retailer,
                classification=classification,
            ):
                raise FatalRetailerDiscoveryError(
                    "Aborting discovery run after unusable "
                    f"{strategy.retailer} listing page ({classification}) at "
                    f"{capture.final_url or capture.requested_url}"
                )
            break
        if current_page >= max_pages:
            completed = bool(observations)
            break
        next_url = strategy.next_page_url(
            current_url=(
                current_url if strategy.retailer == "chewy" else capture.final_url
            ),
            html=capture.html,
            current_page=current_page,
        )
        if strategy.retailer == "chewy" and hasattr(engine, "click_next_listing_page"):
            advanced_url = engine.click_next_listing_page(retailer=strategy.retailer)
            if advanced_url and advanced_url != capture.final_url:
                current_page += 1
                current_url = advanced_url
                capture_loaded_tab = True
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
                continue
        if not next_url or next_url == capture.final_url:
            completed = True
            break
        current_page += 1
        current_url = next_url
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    else:
        completed = bool(observations)
    return observations, first_capture, completed


def _chewy_filter_redirected_to_base_category(
    *,
    retailer: str,
    source_surface: str,
    requested_url: str,
    final_url: str | None,
) -> bool:
    if str(retailer or "").strip().lower() != "chewy":
        return False
    if not str(source_surface or "").startswith("filter:"):
        return False
    requested_path = urlsplit(str(requested_url or "")).path.rstrip("/")
    final_path = urlsplit(str(final_url or "")).path.rstrip("/")
    if not requested_path.startswith("/f/"):
        return False
    return final_path.startswith("/b/")


def _is_unexpected_pdp_landing_url(*, retailer: str, url: str) -> bool:
    markers = PDP_LANDING_PATH_MARKERS_BY_RETAILER.get(retailer.lower(), ())
    if not markers:
        return False
    path = urlsplit(str(url or "")).path.lower()
    return any(marker in path for marker in markers)


def _crawl_filter_observations(
    *,
    engine: CDPListingEngine,
    strategy,
    profile: PDPProfile,
    surface: FilterSurface,
    max_pages: int,
    delay_seconds: float,
    failure_artifact_root: Path,
    manual_navigation_loader: ManualNavigationLoader | None = None,
    sort_control_mode: str = "set",
) -> tuple[list[FilterObservation], bool]:
    listing_rows, _first_capture, completed = _crawl_surface(
        engine=engine,
        strategy=strategy,
        profile=profile,
        category_key=surface.category_key,
        surface_url=surface.filter_url,
        source_surface=f"filter:{surface.filter_family}={surface.filter_value}",
        sort_mode="default",
        max_pages=max_pages,
        delay_seconds=delay_seconds,
        failure_artifact_root=failure_artifact_root,
        manual_navigation_loader=manual_navigation_loader,
        sort_control_mode=sort_control_mode,
    )
    return (
        [
            FilterObservation(
                retailer=surface.retailer,
                category_key=surface.category_key,
                filter_family=surface.filter_family,
                filter_value=surface.filter_value,
                source_surface=row.source_surface,
                pdp_url=row.pdp_url,
                parent_product_id=row.parent_product_id,
                page=row.page,
                position=row.position,
                listing_url=row.listing_url,
            )
            for row in listing_rows
        ],
        completed,
    )


def _write_run_artifacts(
    *,
    output_dir: Path,
    observations_frame: pl.DataFrame,
    classification_frame: pl.DataFrame,
    filter_surfaces_frame: pl.DataFrame,
    filter_observations_frame: pl.DataFrame,
    category_links_payload: dict[str, list[str]],
    summary: dict[str, object],
    write_csv_artifacts: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if write_csv_artifacts:
        observations_frame.write_csv(output_dir / "retailer_listing_observations.csv")
        classification_frame.write_csv(
            output_dir / "retailer_listing_classification.csv"
        )
        filter_surfaces_frame.write_csv(output_dir / "retailer_filter_surfaces.csv")
        filter_observations_frame.write_csv(
            output_dir / "retailer_filter_observations.csv"
        )
    (output_dir / "category_links.json").write_text(
        json.dumps(category_links_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_kiko_variant_parent_lookup(
    attribute_cache_root: Path,
) -> dict[str, tuple[str, ...]]:
    variants_path = attribute_cache_root / "kiko" / "variants.parquet"
    if not variants_path.is_file():
        return {}
    try:
        frame = pl.read_parquet(variants_path)
    except (OSError, pl.exceptions.PolarsError):
        LOGGER.exception(
            "Failed to read Kiko variant cache for filter membership mapping: %s",
            variants_path,
        )
        return {}

    columns, _schema = get_schema_and_column_names(frame)
    if "parent_product_id" not in columns:
        return {}
    key_columns = [
        column
        for column in ("variant_id", "backend_id", "backend_parent_id")
        if column in columns
    ]
    if not key_columns:
        return {}

    lookup: dict[str, set[str]] = {}
    for row in frame.select(["parent_product_id", *key_columns]).to_dicts():
        parent_id = str(row.get("parent_product_id") or "").strip()
        if not parent_id:
            continue
        for column in key_columns:
            key = str(row.get(column) or "").strip()
            if key:
                lookup.setdefault(key, set()).add(parent_id)
    return {key: tuple(sorted(parent_ids)) for key, parent_ids in lookup.items()}


def _write_latest_filter_evidence(
    *,
    evidence_root: Path,
    retailer: str,
    filter_surfaces_frame: pl.DataFrame,
    filter_observations_frame: pl.DataFrame,
    summary: dict[str, object],
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


def _count_failure_bundles(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.glob("*/diagnosis.json"))


def _send_manual_intervention_alert(
    *,
    retailer: str,
    category_key: str,
    requested_url: str,
    final_url: str,
    classification: str,
    page_title: str | None,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    send_run_notification(
        run_name=f"cdp_discovery_manual_intervention_{retailer}",
        status="ACTION REQUIRED",
        recipients=resolve_notification_recipients(),
        started_at=now,
        finished_at=now,
        details={
            "retailer": retailer,
            "category_key": category_key,
            "classification": classification,
            "requested_url": requested_url,
            "final_url": final_url,
            "page_title": page_title or "",
            "action": "Clear the anti-bot check in the attached Chrome session and rerun discovery.",
        },
        logger=LOGGER,
    )


def _send_manual_navigation_prompt_alert(
    *,
    retailer: str,
    category_key: str,
    requested_url: str,
    source_surface: str,
    page_number: int,
    auto_paste: bool = False,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    action = (
        "The runner is auto-pasting this URL into the attached Chrome window. "
        "Keep that Chrome window open and visible."
        if auto_paste
        else (
            "Paste the requested URL into the attached Chrome window, wait for "
            "the product grid to render, then press Enter in the terminal."
        )
    )
    send_run_notification(
        run_name=f"cdp_discovery_manual_navigation_{retailer}",
        status="ACTION REQUIRED",
        recipients=resolve_notification_recipients(),
        started_at=now,
        finished_at=now,
        details={
            "retailer": retailer,
            "category_key": category_key,
            "source_surface": source_surface,
            "page_number": page_number,
            "requested_url": requested_url,
            "action": action,
        },
        logger=LOGGER,
    )


def _cdp_json_endpoint(remote_url: str) -> str:
    return f"{str(remote_url or '').rstrip('/')}/json/list"


def _manual_navigation_urls_match(current_url: str, requested_url: str) -> bool:
    current = urlsplit(str(current_url or "").strip())
    requested = urlsplit(str(requested_url or "").strip())
    current_path = current.path.rstrip("/") or "/"
    requested_path = requested.path.rstrip("/") or "/"
    same_host = current.netloc.lower() == requested.netloc.lower()
    same_scheme = current.scheme.lower() == requested.scheme.lower()
    same_path = current_path == requested_path
    chewy_same_pdp = False
    if same_host and current.netloc.lower().endswith("chewy.com"):
        current_match = _CHEWY_PDP_ID_IN_PATH.search(current_path)
        requested_match = _CHEWY_PDP_ID_IN_PATH.search(requested_path)
        chewy_same_pdp = (
            current_match is not None
            and requested_match is not None
            and current_match.group(1) == requested_match.group(1)
        )
    if not same_scheme or not same_host or (not same_path and not chewy_same_pdp):
        return False
    current_query = dict(parse_qsl(current.query, keep_blank_values=True))
    requested_query = dict(parse_qsl(requested.query, keep_blank_values=True))
    if current.netloc.lower().endswith("chewy.com") and current_path.startswith(
        ("/b/", "/f/")
    ):
        current_query_keys = {key.lower() for key in current_query}
        requested_query_keys = {key.lower() for key in requested_query}
        state_query_keys = {
            "sort",
            "page",
            "p",
            "pagenumber",
            "pagenum",
            "currentpage",
        }
        if current_query_keys.intersection(state_query_keys) - requested_query_keys:
            return False
    for key, value in requested_query.items():
        if current_query.get(key) != value:
            return False
    return True


def _read_cdp_tab_urls(remote_url: str) -> tuple[str, ...]:
    return tuple(tab["url"] for tab in _read_cdp_tabs(remote_url) if tab["url"])


def _read_cdp_tabs(remote_url: str) -> tuple[dict[str, str], ...]:
    try:
        with urlopen(_cdp_json_endpoint(remote_url), timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, list):
        return ()
    tabs: list[dict[str, str]] = []
    for item in payload:
        if isinstance(item, Mapping):
            url = str(item.get("url", "") or "").strip()
            if url:
                tabs.append(
                    {
                        "id": str(item.get("id", "") or "").strip(),
                        "title": str(item.get("title", "") or "").strip(),
                        "type": str(item.get("type", "") or "").strip(),
                        "url": url,
                    }
                )
    return tuple(tabs)


def _is_listing_like_manual_tab_url(url: str, requested_url: str) -> bool:
    current = urlsplit(str(url or "").strip())
    requested = urlsplit(str(requested_url or "").strip())
    if current.scheme.lower() not in {"http", "https"}:
        return False
    if current.netloc.lower() != requested.netloc.lower():
        return False
    path = current.path.rstrip("/") or "/"
    if current.netloc.lower().endswith("chewy.com"):
        return path.startswith(("/b/", "/f/"))
    return "/dp/" not in path.lower()


def _activate_cdp_tab(tab_id: str, *, remote_url: str) -> None:
    tab_id = str(tab_id or "").strip()
    if not tab_id:
        return
    try:
        with urlopen(
            f"{str(remote_url or '').rstrip('/')}/json/activate/{quote(tab_id, safe='')}",
            timeout=2.0,
        ) as response:
            response.read()
    except (OSError, URLError, TimeoutError):
        LOGGER.debug("Could not activate CDP tab %s before auto-paste.", tab_id)


def _activate_cdp_tab_for_manual_navigation(
    *,
    remote_url: str,
    requested_url: str,
) -> tuple[str | None, str | None]:
    tabs = _read_cdp_tabs(remote_url)
    if not tabs:
        return None, None
    requested = urlsplit(str(requested_url or "").strip())

    exact_matches = [
        tab for tab in tabs if _manual_navigation_urls_match(tab["url"], requested_url)
    ]
    listing_matches = [
        tab
        for tab in tabs
        if _is_listing_like_manual_tab_url(tab["url"], requested_url)
    ]
    same_host_pages = [
        tab
        for tab in tabs
        if urlsplit(tab["url"]).scheme.lower() in {"http", "https"}
        and urlsplit(tab["url"]).netloc.lower() == requested.netloc.lower()
    ]
    http_pages = [
        tab for tab in tabs if urlsplit(tab["url"]).scheme.lower() in {"http", "https"}
    ]
    selected = next(
        iter(exact_matches or listing_matches or same_host_pages or http_pages),
        tabs[0],
    )
    _activate_cdp_tab(selected["id"], remote_url=remote_url)
    LOGGER.info(
        "Activated CDP tab before auto-paste; current URL before paste is %s; requested URL is %s",
        selected["url"],
        requested_url,
    )
    return selected["title"] or None, selected["url"] or None


def _wait_for_cdp_tab_url(
    *,
    remote_url: str,
    requested_url: str,
    timeout_seconds: float,
    stale_url: str | None = None,
    unchanged_timeout_seconds: float = 8.0,
) -> bool:
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    unchanged_deadline = time.monotonic() + max(0.0, float(unchanged_timeout_seconds))
    last_urls: tuple[str, ...] = ()
    while time.monotonic() <= deadline:
        last_urls = _read_cdp_tab_urls(remote_url)
        if any(
            _manual_navigation_urls_match(current_url, requested_url)
            for current_url in last_urls
        ):
            return True
        if (
            stale_url
            and time.monotonic() >= unchanged_deadline
            and any(
                _manual_navigation_urls_match(current_url, stale_url)
                for current_url in last_urls
            )
        ):
            LOGGER.warning(
                "Auto-paste did not change the active tab URL within %.1f seconds; retrying. Current CDP tab URLs: %s",
                unchanged_timeout_seconds,
                ", ".join(last_urls) if last_urls else "(none)",
            )
            return False
        time.sleep(0.5)
    LOGGER.warning(
        "Timed out waiting for Chrome to load %s. Last CDP tab URLs: %s",
        requested_url,
        ", ".join(last_urls) if last_urls else "(none)",
    )
    return False


def _paste_url_into_windows_chrome(
    url: str,
    *,
    title_hint: str | None = None,
) -> None:
    if sys.platform != "win32":
        raise RuntimeError(
            "Automatic paste navigation is only supported from Windows Python."
        )
    encoded_url = base64.b64encode(str(url).encode("utf-16le")).decode("ascii")
    encoded_title_hint = base64.b64encode(
        str(title_hint or "").encode("utf-16le")
    ).decode("ascii")
    script = f"""
$ErrorActionPreference = 'Stop'
$url = [System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded_url}'))
$titleHint = [System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded_title_hint}'))
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class ChromeWindowTools {{
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
}}
"@
$chromeCandidates = @(Get-Process chrome | Where-Object {{ $_.MainWindowHandle -ne 0 }})
if ($chromeCandidates.Count -eq 0) {{
    throw 'No visible Chrome window was found.'
}}
$chrome = $null
if (-not [string]::IsNullOrWhiteSpace($titleHint)) {{
    $chrome = $chromeCandidates |
        Where-Object {{ $_.MainWindowTitle.IndexOf($titleHint, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 }} |
        Sort-Object StartTime -Descending |
        Select-Object -First 1
}}
if ($null -eq $chrome) {{
    $chrome = $chromeCandidates |
        Where-Object {{ $_.MainWindowTitle.IndexOf('Chewy', [System.StringComparison]::OrdinalIgnoreCase) -ge 0 }} |
        Sort-Object StartTime -Descending |
        Select-Object -First 1
}}
if ($null -eq $chrome) {{
    $chrome = $chromeCandidates | Sort-Object StartTime -Descending | Select-Object -First 1
}}
$shell = New-Object -ComObject WScript.Shell
[ChromeWindowTools]::ShowWindowAsync($chrome.MainWindowHandle, 9) | Out-Null
Start-Sleep -Milliseconds 250
[ChromeWindowTools]::SetForegroundWindow($chrome.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 300
$shell.AppActivate($chrome.Id) | Out-Null
Start-Sleep -Milliseconds 500
$usedUiAutomation = $false
try {{
    $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$chrome.MainWindowHandle)
    $editCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Edit
    )
    $edits = @($root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCondition))
    foreach ($edit in $edits) {{
        $valuePattern = $null
        $name = ""
        try {{
            $name = [string]$edit.Current.Name
        }} catch {{
            $name = ""
        }}
        if (
            $edit.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$valuePattern) -and
            (
                $name.IndexOf('address', [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or
                $name.IndexOf('omnibox', [System.StringComparison]::OrdinalIgnoreCase) -ge 0
            )
        ) {{
            $edit.SetFocus()
            Start-Sleep -Milliseconds 100
            $valuePattern.SetValue($url)
            $usedUiAutomation = $true
            break
        }}
    }}
    if (-not $usedUiAutomation) {{
        [System.Windows.Forms.SendKeys]::SendWait('{{ESC}}')
        Start-Sleep -Milliseconds 150
        [System.Windows.Forms.SendKeys]::SendWait('%d')
        Start-Sleep -Milliseconds 350
        $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
        if ($null -ne $focused) {{
            $valuePattern = $null
            if ($focused.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$valuePattern)) {{
                $valuePattern.SetValue($url)
                $usedUiAutomation = $true
            }}
        }}
    }}
}} catch {{
    $usedUiAutomation = $false
}}
if (-not $usedUiAutomation) {{
    [System.Windows.Forms.SendKeys]::SendWait('{{ESC}}')
    Start-Sleep -Milliseconds 150
    [System.Windows.Forms.Clipboard]::SetText($url)
    Start-Sleep -Milliseconds 150
    [System.Windows.Forms.SendKeys]::SendWait('%d')
    Start-Sleep -Milliseconds 200
    [System.Windows.Forms.SendKeys]::SendWait('^l')
    Start-Sleep -Milliseconds 200
    [System.Windows.Forms.SendKeys]::SendWait('^l')
    Start-Sleep -Milliseconds 200
    [System.Windows.Forms.SendKeys]::SendWait('^a')
    Start-Sleep -Milliseconds 100
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    Start-Sleep -Milliseconds 200
}}
[System.Windows.Forms.SendKeys]::SendWait('{{ENTER}}')
[System.Windows.Forms.SendKeys]::Flush()
Start-Sleep -Milliseconds 250
"""
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-STA",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        message = " ".join(
            part.strip()
            for part in (completed.stderr, completed.stdout)
            if str(part or "").strip()
        )
        raise RuntimeError(
            f"Failed to auto-paste URL into Chrome: {message or completed.returncode}"
        )


def _build_manual_navigation_loader(
    *,
    retailer: str,
    remote_url: str,
    send_notifications: bool,
    auto_paste: bool,
    auto_paste_wait_seconds: float,
    auto_paste_attempts: int,
) -> ManualNavigationLoader:
    alerted_urls: set[str] = set()

    def _load_url(
        requested_url: str,
        category_key: str,
        source_surface: str,
        page_number: int,
    ) -> None:
        LOGGER.warning(
            "Manual navigation required for %s / %s (%s page %d).",
            retailer,
            category_key,
            source_surface,
            page_number,
        )
        LOGGER.warning("Paste/load this URL in Chrome: %s", requested_url)
        if send_notifications and requested_url not in alerted_urls:
            _send_manual_navigation_prompt_alert(
                retailer=retailer,
                category_key=category_key,
                requested_url=requested_url,
                source_surface=source_surface,
                page_number=page_number,
                auto_paste=auto_paste,
            )
            alerted_urls.add(requested_url)
        if auto_paste:
            attempts = max(1, int(auto_paste_attempts))
            for attempt in range(1, attempts + 1):
                LOGGER.warning(
                    "Auto-pasting URL into visible Chrome window (attempt %d/%d).",
                    attempt,
                    attempts,
                )
                title_hint, stale_url = _activate_cdp_tab_for_manual_navigation(
                    remote_url=remote_url,
                    requested_url=requested_url,
                )
                _paste_url_into_windows_chrome(
                    requested_url,
                    title_hint=title_hint,
                )
                if _wait_for_cdp_tab_url(
                    remote_url=remote_url,
                    requested_url=requested_url,
                    timeout_seconds=auto_paste_wait_seconds,
                    stale_url=stale_url,
                ):
                    return
            raise RuntimeError(
                f"Chrome did not reach requested URL after {attempts} auto-paste attempt(s): {requested_url}"
            )
        input(
            "After the product grid is visible in the attached Chrome window, "
            "press Enter here to capture it..."
        )

    return _load_url


def _browser_sort_label(strategy, sort_mode: str) -> str | None:
    label_getter = getattr(strategy, "browser_sort_label", None)
    if not callable(label_getter):
        return None
    label = str(label_getter(sort_mode) or "").strip()
    return label or None


def _build_manual_sort_confirmer(strategy) -> ManualSortConfirmer:
    prompted: set[tuple[str, str]] = set()

    def _confirm(
        category_key: str,
        source_surface: str,
        sort_mode: str,
        page_number: int,
    ) -> None:
        if source_surface != "category" or page_number != 1:
            return
        sort_label = _browser_sort_label(strategy, sort_mode)
        if not sort_label:
            return
        prompt_key = (category_key, sort_mode)
        if prompt_key in prompted:
            return
        LOGGER.warning(
            "Set the Chewy Sort By widget to %s for %s / %s, then press Enter.",
            sort_label,
            category_key,
            sort_mode,
        )
        input(
            f"After the visible Chewy Sort By widget shows {sort_label}, "
            "press Enter here to capture and paginate..."
        )
        prompted.add(prompt_key)

    return _confirm


def _write_capture_failure_bundle(
    *,
    failure_artifact_root: Path,
    capture: CapturedListingPage,
    strategy,
    category_key: str,
    reason: str,
) -> Path:
    return write_cdp_failure_bundle(
        artifact_root=failure_artifact_root,
        requested_url=capture.requested_url,
        final_url=capture.final_url,
        page_title=capture.page_title,
        html=capture.html,
        selector=strategy.selector,
        reason=reason,
        retailer=strategy.retailer,
        category_key=category_key,
        candidate_count=len(capture.candidates),
        selector_found=capture.selector_found,
        screenshot_png=None,
    )


def _read_failure_diagnosis(bundle_dir: Path) -> dict[str, object]:
    try:
        return json.loads((bundle_dir / "diagnosis.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _failure_classification(diagnosis: Mapping[str, object]) -> str:
    return str(diagnosis.get("classification", "") or "").strip()


def _should_abort_after_failure_classification(
    *, retailer: str, classification: str
) -> bool:
    retailer_classifications = FATAL_DISCOVERY_FAILURE_CLASSIFICATIONS_BY_RETAILER.get(
        retailer.lower(), set()
    )
    return str(classification or "").strip() in retailer_classifications


def main(argv: Sequence[str] | None = None) -> int:
    args = _apply_retailer_defaults(_parse_args(argv or sys.argv[1:]))
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_env_from_secrets_file()

    retailer = str(args.retailer or "").strip().lower()
    strategy = strategy_for_retailer(retailer)
    if args.resume and args.resume_run_dir is None:
        resume_run_dir = _latest_checkpoint_run_dir(
            output_root=args.output_root,
            retailer=retailer,
        )
        if resume_run_dir is None:
            LOGGER.error(
                "No checkpointed %s discovery run found under %s.",
                retailer,
                args.output_root / retailer,
            )
            return 1
        args.resume_run_dir = resume_run_dir
        LOGGER.info("Resuming latest %s discovery run: %s", retailer, resume_run_dir)
    run_started = dt.datetime.now(dt.timezone.utc)
    crawl_ts = run_started.isoformat()
    run_slug = run_started.strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.resume_run_dir or args.output_root / retailer / run_slug
    failure_artifact_root = output_dir / "failure_bundles"
    categories = _normalize_categories(args.categories, retailer=retailer)
    profiles = _load_profiles(retailer, categories)
    if not profiles:
        LOGGER.warning("No %s profiles matched the requested category set.", retailer)
        return 0
    category_keys = {
        strategy.profile_to_category_key(profile.profile_name) for profile in profiles
    }

    requested_sort_modes = tuple(args.sort_modes or strategy.default_sort_modes)
    sort_modes = _normalize_listing_surface_sort_modes(retailer, requested_sort_modes)
    selected_sort_mode_keys = {
        str(sort_mode or "").strip().lower() for sort_mode in sort_modes
    }
    removed_sort_modes = [
        sort_mode
        for sort_mode in requested_sort_modes
        if str(sort_mode or "").strip().lower() not in selected_sort_mode_keys
    ]
    if removed_sort_modes:
        LOGGER.warning(
            "Ignoring non-ranked sort modes for %s discovery: %s",
            retailer,
            ", ".join(str(mode) for mode in removed_sort_modes),
        )
    if not sort_modes and not args.capture_filters:
        LOGGER.error("No ranked sort modes remain for %s discovery.", retailer)
        return 1
    if retailer == "chewy":
        LOGGER.info(
            "Chewy sort guard active (%s): category URLs must be clean, Sort By widget must verify as Newest/Bestselling before capture, and stale sort/page URLs are rejected.",
            CHEWY_SORT_GUARD_VERSION,
        )
    allowed_families = tuple(args.filter_families) if args.filter_families else None

    observations: list[ListingObservation] = []
    filter_surfaces: list[FilterSurface] = []
    filter_observations: list[FilterObservation] = []
    completed_surface_keys: set[str] = set()
    if args.resume_run_dir is not None:
        try:
            (
                checkpoint_crawl_ts,
                observations,
                filter_surfaces,
                filter_observations,
                completed_surface_keys,
                checkpoint_metadata,
            ) = _load_discovery_checkpoint(args.resume_run_dir)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            LOGGER.error(
                "Unable to resume discovery from %s: %s",
                args.resume_run_dir,
                exc,
            )
            return 1
        checkpoint_retailer = str(checkpoint_metadata.get("retailer", "")).lower()
        checkpoint_categories = {
            canonical_category_key(checkpoint_retailer, category)
            for category in checkpoint_metadata.get("categories", [])
        }
        checkpoint_sort_modes = tuple(
            str(sort_mode) for sort_mode in checkpoint_metadata.get("sort_modes", [])
        )
        if checkpoint_retailer != retailer:
            LOGGER.error(
                "Checkpoint retailer %s does not match requested retailer %s.",
                checkpoint_retailer,
                retailer,
            )
            return 1
        if checkpoint_categories != category_keys:
            LOGGER.error(
                "Checkpoint categories %s do not match requested categories %s.",
                sorted(checkpoint_categories),
                sorted(category_keys),
            )
            return 1
        if checkpoint_sort_modes != tuple(sort_modes):
            LOGGER.error(
                "Checkpoint sort modes %s do not match requested sort modes %s.",
                list(checkpoint_sort_modes),
                list(sort_modes),
            )
            return 1
        if (
            retailer == "chewy"
            and checkpoint_metadata.get("chewy_sort_guard_version")
            != CHEWY_SORT_GUARD_VERSION
        ):
            LOGGER.error(
                "Checkpoint %s was created before the verified Chewy sort guard (%s). "
                "Do not resume it because it may contain Relevance rows. Start a new run instead.",
                args.resume_run_dir,
                CHEWY_SORT_GUARD_VERSION,
            )
            return 1
        crawl_ts = checkpoint_crawl_ts or crawl_ts
        LOGGER.info(
            "Resuming %s discovery from %s with %d listing rows, %d filter surfaces, and %d filter rows.",
            retailer,
            args.resume_run_dir,
            len(observations),
            len(filter_surfaces),
            len(filter_observations),
        )

    manual_navigation_enabled = bool(
        args.manual_navigation or args.manual_navigation_auto_paste
    )
    manual_navigation_loader = (
        _build_manual_navigation_loader(
            retailer=retailer,
            remote_url=str(args.remote_url),
            send_notifications=bool(args.manual_navigation_notify),
            auto_paste=bool(args.manual_navigation_auto_paste),
            auto_paste_wait_seconds=float(
                args.manual_navigation_auto_paste_wait_seconds
            ),
            auto_paste_attempts=int(args.manual_navigation_auto_paste_attempts),
        )
        if manual_navigation_enabled
        else None
    )
    sort_control_mode = (
        "verify"
        if retailer == "chewy" and bool(args.chewy_manual_sort_widget)
        else "set"
    )
    manual_sort_confirmer = (
        _build_manual_sort_confirmer(strategy)
        if retailer == "chewy"
        and bool(args.chewy_manual_sort_widget)
        and manual_navigation_loader is not None
        else None
    )
    if retailer == "chewy" and bool(args.chewy_manual_sort_widget):
        LOGGER.info(
            "Chewy manual sort widget mode is active: the operator sets Newest/Bestselling; the scraper verifies the widget and paginates."
        )

    seen_filter_surfaces: set[tuple[str, str, str, str]] = set()
    for surface in filter_surfaces:
        seen_filter_surfaces.add(
            (
                surface.category_key,
                surface.filter_family,
                surface.filter_value,
                surface.filter_url,
            )
        )
    sent_manual_alerts: set[tuple[str, str, str]] = set()
    kiko_variant_parent_lookup = (
        _load_kiko_variant_parent_lookup(args.attribute_cache_root)
        if retailer == "kiko"
        else {}
    )
    if retailer == "kiko" and not kiko_variant_parent_lookup:
        LOGGER.warning(
            "No Kiko variant-parent lookup found at %s; filter observations may not map to parent products.",
            args.attribute_cache_root / "kiko" / "variants.parquet",
        )

    def _checkpoint_current_state() -> None:
        checkpoint_path = _write_discovery_checkpoint(
            output_dir=output_dir,
            crawl_ts=crawl_ts,
            retailer=retailer,
            categories=sorted(category_keys),
            sort_modes=sort_modes,
            observations=observations,
            filter_surfaces=filter_surfaces,
            filter_observations=filter_observations,
            completed_surface_keys=completed_surface_keys,
        )
        LOGGER.info("Wrote discovery checkpoint: %s", checkpoint_path)

    _checkpoint_current_state()

    engine = CDPListingEngine(
        remote_url=args.remote_url,
        reuse_open_tab=bool(args.reuse_open_tab),
        timeout_ms=int(args.timeout_ms),
        wait_ms=int(args.wait_ms),
        scroll_steps=int(args.scroll_steps),
        max_idle_scrolls=int(args.max_idle_scrolls),
        max_links=int(args.max_links),
        diagnostic_artifact_root=failure_artifact_root,
    )
    try:
        with engine:
            for profile in profiles:
                category_key = strategy.profile_to_category_key(profile.profile_name)
                LOGGER.info("Crawling %s category %s", retailer, category_key)
                for category_url in _profile_category_urls(
                    profile,
                    locale=str(args.locale),
                ):
                    filter_capture: CapturedListingPage | None = None
                    category_sort_sequences = (
                        _category_sort_sequences_from_observations(
                            observations,
                            category_key=category_key,
                            source_surface="category",
                        )
                    )
                    for sort_mode in sort_modes:
                        is_ranked_sort_mode = _is_ranked_sort_mode(sort_mode)
                        surface_url = strategy.apply_sort_mode(category_url, sort_mode)
                        surface_key = _listing_surface_checkpoint_key(
                            category_key=category_key,
                            source_surface="category",
                            sort_mode=sort_mode,
                            surface_url=surface_url,
                        )
                        if surface_key in completed_surface_keys:
                            LOGGER.info(
                                "Skipping completed %s listing surface %s / %s.",
                                retailer,
                                category_key,
                                sort_mode,
                            )
                            continue
                        retry_attempts = (
                            STALE_SORT_SEQUENCE_RETRY_ATTEMPTS
                            if retailer in STALE_SORT_SEQUENCE_RETRY_RETAILERS
                            else 1
                        )
                        page_observations: list[ListingObservation] = []
                        first_capture: CapturedListingPage | None = None
                        surface_completed = False
                        stale_matching_sort_mode: str | None = None
                        for stale_attempt in range(1, retry_attempts + 1):
                            (
                                page_observations,
                                first_capture,
                                surface_completed,
                            ) = _crawl_surface(
                                engine=engine,
                                strategy=strategy,
                                profile=profile,
                                category_key=category_key,
                                surface_url=surface_url,
                                source_surface="category",
                                sort_mode=sort_mode,
                                max_pages=args.max_pages,
                                delay_seconds=args.delay_seconds,
                                failure_artifact_root=failure_artifact_root,
                                manual_navigation_loader=manual_navigation_loader,
                                manual_sort_confirmer=manual_sort_confirmer,
                                force_navigation=stale_attempt > 1,
                                sort_control_mode=sort_control_mode,
                            )
                            stale_matching_sort_mode = None
                            if (
                                surface_completed
                                and is_ranked_sort_mode
                                and retry_attempts > 1
                                and category_sort_sequences
                            ):
                                stale_matching_sort_mode = (
                                    _matching_identical_prior_sort_sequence(
                                        _ordered_observation_sequence(
                                            page_observations
                                        ),
                                        category_sort_sequences,
                                        current_sort_mode=sort_mode,
                                    )
                                )
                            if stale_matching_sort_mode is None:
                                break
                            if stale_attempt < retry_attempts:
                                LOGGER.warning(
                                    "%s / %s / %s produced the same ranked product order as %s; forcing a reload before crawling filters.",
                                    retailer,
                                    category_key,
                                    sort_mode,
                                    stale_matching_sort_mode,
                                )
                                if args.delay_seconds > 0:
                                    time.sleep(args.delay_seconds)
                                continue
                            raise FatalRetailerDiscoveryError(
                                f"{retailer} / {category_key} / {sort_mode} "
                                "produced the same ranked product order as "
                                f"{stale_matching_sort_mode} after "
                                f"{retry_attempts} capture attempt(s). Stopping "
                                "before filters because the sort capture is stale "
                                "or invalid."
                            )
                        if not surface_completed and retailer == "chewy":
                            raise FatalRetailerDiscoveryError(
                                "Discovery interrupted before completing listing "
                                f"surface {retailer} / {category_key} / {sort_mode}. "
                                f"Resume with --resume, or --resume-run-dir {output_dir}."
                            )
                        observations.extend(page_observations)
                        if surface_completed:
                            completed_surface_keys.add(surface_key)
                            if is_ranked_sort_mode:
                                category_sort_sequences[sort_mode] = (
                                    _ordered_observation_sequence(page_observations)
                                )
                        if (
                            sort_mode in strategy.filter_sort_modes
                            and first_capture is not None
                            and filter_capture is None
                        ):
                            filter_capture = first_capture
                        if surface_completed:
                            _checkpoint_current_state()
                        else:
                            LOGGER.warning(
                                "Listing surface did not complete: %s / %s / %s.",
                                retailer,
                                category_key,
                                sort_mode,
                            )

                    if retailer in STALE_SORT_SEQUENCE_RETRY_RETAILERS:
                        identical_pair = _first_identical_sort_sequence_pair(
                            category_sort_sequences
                        )
                        if identical_pair is not None:
                            left_sort_mode, right_sort_mode = identical_pair
                            raise FatalRetailerDiscoveryError(
                                f"{retailer} / {category_key} has identical "
                                "ranked product order for "
                                f"{left_sort_mode} and {right_sort_mode}. "
                                "Stopping before filters because the sort "
                                "capture is stale or invalid."
                            )

                    if not args.capture_filters:
                        continue

                    category_surfaces = [
                        surface
                        for surface in filter_surfaces
                        if surface.category_key == category_key
                    ]
                    if category_surfaces:
                        LOGGER.info(
                            "Using %d checkpointed filter surfaces for %s / %s.",
                            len(category_surfaces),
                            retailer,
                            category_key,
                        )
                    else:
                        if filter_capture is None:
                            if manual_navigation_loader is not None:
                                manual_navigation_loader(
                                    category_url,
                                    category_key,
                                    "filter_base",
                                    1,
                                )
                            filter_capture = engine.capture_listing_page(
                                url=category_url,
                                selector=strategy.selector,
                                retailer=strategy.retailer,
                                category_key=category_key,
                                load_more_texts=strategy.load_more_texts,
                                navigate=manual_navigation_loader is None,
                            )
                        if filter_capture is None:
                            LOGGER.warning(
                                "Skipping filter extraction for %s / %s because the base PLP could not be captured.",
                                retailer,
                                category_key,
                            )
                            if retailer == "chewy":
                                raise FatalRetailerDiscoveryError(
                                    "Discovery interrupted before filter extraction "
                                    f"for {retailer} / {category_key}. Resume with "
                                    f"--resume, or --resume-run-dir {output_dir}."
                                )
                            continue
                        category_surfaces = strategy.extract_filter_surfaces(
                            category_url=filter_capture.final_url,
                            html=filter_capture.html,
                            category_key=category_key,
                            allowed_families=allowed_families,
                        )
                        category_surfaces = _limit_filter_surfaces(
                            category_surfaces,
                            limit=int(args.filter_surface_limit),
                        )
                        if not category_surfaces:
                            bundle_dir = _write_capture_failure_bundle(
                                failure_artifact_root=failure_artifact_root,
                                capture=filter_capture,
                                strategy=strategy,
                                category_key=category_key,
                                reason="no_filter_surfaces",
                            )
                            LOGGER.warning(
                                "No filter surfaces discovered for %s / %s; wrote failure bundle to %s",
                                retailer,
                                category_key,
                                bundle_dir,
                            )
                            diagnosis = _read_failure_diagnosis(bundle_dir)
                            classification = _failure_classification(diagnosis)
                            requested_url = str(
                                diagnosis.get("requested_url", "") or ""
                            ).strip()
                            final_url = str(
                                diagnosis.get("final_url", "") or ""
                            ).strip()
                            page_title = str(
                                diagnosis.get("page_title", "") or ""
                            ).strip()
                            alert_key = (category_key, requested_url, classification)
                            if (
                                classification in MANUAL_INTERVENTION_CLASSIFICATIONS
                                and alert_key not in sent_manual_alerts
                            ):
                                _send_manual_intervention_alert(
                                    retailer=retailer,
                                    category_key=category_key,
                                    requested_url=requested_url,
                                    final_url=final_url,
                                    classification=classification,
                                    page_title=page_title,
                                )
                                sent_manual_alerts.add(alert_key)
                            if _should_abort_after_failure_classification(
                                retailer=retailer,
                                classification=classification,
                            ):
                                raise FatalRetailerDiscoveryError(
                                    "Aborting discovery run after unusable "
                                    f"{retailer} filter base page ({classification}) at "
                                    f"{final_url or requested_url or category_url}"
                                )
                        added_surface = False
                        for surface in category_surfaces:
                            dedupe_key = (
                                surface.category_key,
                                surface.filter_family,
                                surface.filter_value,
                                surface.filter_url,
                            )
                            if dedupe_key in seen_filter_surfaces:
                                continue
                            seen_filter_surfaces.add(dedupe_key)
                            filter_surfaces.append(surface)
                            added_surface = True
                        if added_surface:
                            _checkpoint_current_state()
                    if retailer == "kiko":
                        filter_observations.extend(
                            crawl_kiko_filter_observations(
                                category_url=filter_capture.final_url,
                                html=filter_capture.html,
                                category_key=category_key,
                                variant_parent_lookup=kiko_variant_parent_lookup,
                                max_pages=int(args.filter_max_pages),
                                timeout=float(args.filter_request_timeout_seconds),
                                allowed_families=allowed_families,
                            )
                        )
                        continue
                    for surface in category_surfaces:
                        surface_key = _filter_surface_checkpoint_key(surface)
                        if surface_key in completed_surface_keys:
                            LOGGER.info(
                                "Skipping completed %s filter surface %s / %s=%s.",
                                retailer,
                                category_key,
                                surface.filter_family,
                                surface.filter_value,
                            )
                            continue
                        if (
                            manual_navigation_loader is not None
                            and not args.manual_navigation_crawl_filter_memberships
                        ):
                            continue
                        (
                            surface_observations,
                            surface_completed,
                        ) = _crawl_filter_observations(
                            engine=engine,
                            strategy=strategy,
                            profile=profile,
                            surface=surface,
                            max_pages=args.filter_max_pages,
                            delay_seconds=args.delay_seconds,
                            failure_artifact_root=failure_artifact_root,
                            manual_navigation_loader=manual_navigation_loader,
                            sort_control_mode=sort_control_mode,
                        )
                        if not surface_completed and retailer == "chewy":
                            raise FatalRetailerDiscoveryError(
                                "Discovery interrupted before completing filter "
                                f"surface {retailer} / {category_key} / "
                                f"{surface.filter_family}={surface.filter_value}. "
                                f"Resume with --resume, or --resume-run-dir {output_dir}."
                            )
                        filter_observations.extend(surface_observations)
                        if surface_completed:
                            completed_surface_keys.add(surface_key)
                            _checkpoint_current_state()
                        else:
                            LOGGER.warning(
                                "Filter surface did not complete: %s / %s / %s=%s.",
                                retailer,
                                category_key,
                                surface.filter_family,
                                surface.filter_value,
                            )
    except FatalRetailerDiscoveryError as exc:
        LOGGER.error("%s", exc)
        return 1

    category_keys = {
        strategy.profile_to_category_key(profile.profile_name) for profile in profiles
    }
    category_links_payload = _category_links_from_observations(
        [*observations, *filter_observations],
        category_keys=category_keys,
    )
    links_payload = _read_links_payload(args.links_path)
    merged_links_payload = _merge_links_payload(
        links_payload,
        retailer=retailer,
        category_links=category_links_payload,
    )
    observations_frame = _observations_to_frame(observations, crawl_ts=crawl_ts)
    classification_frame = _classification_to_frame(
        observations,
        crawl_ts=crawl_ts,
        recent_share=float(args.recent_share),
    )
    filter_surfaces_frame = _filter_surfaces_to_frame(
        filter_surfaces,
        crawl_ts=crawl_ts,
    )
    filter_observations_frame = _filter_observations_to_frame(
        filter_observations,
        crawl_ts=crawl_ts,
    )
    sort_sequence_quality = build_sort_sequence_quality_report(observations)

    summary = {
        "crawl_ts": crawl_ts,
        "retailer": retailer,
        "categories": sorted(category_keys),
        "sort_modes": list(sort_modes),
        "removed_sort_modes": removed_sort_modes,
        "listing_rows": get_row_count(observations_frame),
        "filter_surface_rows": get_row_count(filter_surfaces_frame),
        "filter_observation_rows": get_row_count(filter_observations_frame),
        "classification_rows": get_row_count(classification_frame),
        "failure_bundle_count": _count_failure_bundles(failure_artifact_root),
        "links_rows": sum(len(links) for links in category_links_payload.values()),
        "links_path": str(args.links_path),
        "links_categories_updated": sorted(category_links_payload),
        "output_dir": str(output_dir),
        "checkpoint_path": str(_checkpoint_path(output_dir)),
        "pdp_store_backend": "postgres",
        "materialized_filter_attribute_rows": None,
        "csv_artifacts_written": bool(args.write_csv_artifacts),
        "sort_sequence_quality": sort_sequence_quality,
    }
    if retailer == "kiko":
        summary["filter_evidence_dir"] = str(args.filter_evidence_root / retailer)
        summary["variant_parent_lookup_keys"] = len(kiko_variant_parent_lookup)
    _write_run_artifacts(
        output_dir=output_dir,
        observations_frame=observations_frame,
        classification_frame=classification_frame,
        filter_surfaces_frame=filter_surfaces_frame,
        filter_observations_frame=filter_observations_frame,
        category_links_payload=category_links_payload,
        summary=summary,
        write_csv_artifacts=bool(args.write_csv_artifacts),
    )
    if sort_sequence_quality["status"] == "failed":
        LOGGER.error(
            "%s discovery failed sort sequence quality gate: %s",
            retailer,
            sort_sequence_quality,
        )
        return 1
    if sort_sequence_quality["status"] == "warning":
        LOGGER.warning(
            "%s discovery found high newest/top-seller sort overlap. "
            "Persisting observations; downstream packages should use "
            "rank-order contrast rather than independent cohort contrast. "
            "Details: %s",
            retailer,
            sort_sequence_quality,
        )

    _write_json(args.links_path, merged_links_payload)
    store = PDPStore(args.pdp_store_path)
    store.append_retailer_listing_observations(
        crawl_ts=crawl_ts,
        observations=observations,
    )
    store.append_retailer_filter_surfaces(
        crawl_ts=crawl_ts,
        surfaces=filter_surfaces,
    )
    store.append_retailer_filter_observations(
        crawl_ts=crawl_ts,
        observations=filter_observations,
    )
    materialized_filter_attribute_rows = 0
    if args.materialize_filter_attributes and filter_observations:
        materialized_filter_attribute_rows = (
            store.materialize_retailer_filter_attributes(
                retailer=retailer,
                crawl_ts=crawl_ts,
            )
        )
    summary["materialized_filter_attribute_rows"] = materialized_filter_attribute_rows
    _write_json(output_dir / "summary.json", summary)
    if retailer == "kiko" and args.capture_filters:
        _write_latest_filter_evidence(
            evidence_root=args.filter_evidence_root,
            retailer=retailer,
            filter_surfaces_frame=filter_surfaces_frame,
            filter_observations_frame=filter_observations_frame,
            summary=summary,
        )
    LOGGER.info("%s discovery complete: %s", retailer, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
