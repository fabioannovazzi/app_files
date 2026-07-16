from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import urljoin, urlparse

import polars as pl
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.amazon_fetcher import AmazonFetcher
from modules.pdp.category_keys import canonical_category_key, profile_category_key
from modules.pdp.discovery import discover_pdp_urls
from modules.pdp.fetcher import HTMLFetcher
from modules.pdp.http_headers import get_headers_for_retailer
from modules.pdp.http_proxies import get_proxies_for_retailer
from modules.pdp.image_downloader import download_variant_images
from modules.pdp.pacing import HumanPacingController
from modules.pdp.postgres_compat import is_postgres_enabled
from modules.pdp.profile import PDPProfile
from modules.pdp.profile_loader import iter_profile_summaries, load_profile
from modules.pdp.purina_catalog import (
    fetch_purina_wet_cat_food_products,
    purina_parent_id_from_url,
    purina_product_url,
)
from modules.pdp.review_constants import (
    DEFAULT_PDP_STORE_PATH,
    enforce_default_pdp_store_path,
)
from modules.pdp.sephora_fetcher import SephoraFetcher
from modules.pdp.service import (
    PARENT_SCHEMA,
    VARIANT_SCHEMA,
    apply_locale,
    flatten_for_export,
    parents_to_frame,
    parse_urls_to_batch,
    summarize_batch,
    variants_to_frame,
)
from modules.pdp.store import PDPStore
from modules.pdp.storage import EvidenceStorage
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.utils import get_row_count


@dataclass(slots=True)
class ProfileRun:
    profile: PDPProfile
    urls: list[str]
    discovered_count: int = 0
    skipped_existing: int = 0


@dataclass(slots=True)
class ProfileRunSummary:
    profile_name: str
    retailer: str
    parent_before: int
    parent_after: int
    parent_delta: int
    variant_before: int
    variant_after: int
    variant_delta: int
    parsed_parents: int
    parsed_variants: int
    skipped_existing: int
    failures: int


CSV_LIST_SEPARATOR = " | "
PARENT_LIST_COLUMNS = [
    name for name, dtype in PARENT_SCHEMA.items() if isinstance(dtype, pl.List)
]
VARIANT_LIST_COLUMNS = [
    name for name, dtype in VARIANT_SCHEMA.items() if isinstance(dtype, pl.List)
]

_PDP_API_HELPERS: dict[str, Callable[..., Any]] | None = None


def _load_pdp_api_helpers() -> dict[str, Callable[..., Any]]:
    """Lazy-load heavy UI/API helpers used only for missing-image runs."""
    global _PDP_API_HELPERS
    if _PDP_API_HELPERS is None:
        from modules.pdp.api import (  # local import by design
            _gather_records,
            _resolve_image_path,
            list_review_categories,
        )

        _PDP_API_HELPERS = {
            "_gather_records": _gather_records,
            "_resolve_image_path": _resolve_image_path,
            "list_review_categories": list_review_categories,
        }
    return _PDP_API_HELPERS


def _emit_store_metrics(metrics: dict[str, int]) -> None:
    if not metrics:
        return
    notes: list[str] = []
    discontinued = metrics.get("newly_discontinued", 0)
    reactivated = metrics.get("reactivated", 0)
    failures = metrics.get("logged_failures", 0)
    if discontinued:
        notes.append(f"Marked {discontinued} parent(s) as discontinued.")
    if reactivated:
        notes.append(f"Cleared discontinued flag for {reactivated} parent(s).")
    if failures and not (discontinued or reactivated):
        notes.append(f"Logged {failures} failure(s).")
    if not notes:
        return
    sys.stdout.write("\n".join(f"  - {note}" for note in notes) + "\n")
    sys.stdout.flush()


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse Ulta PDPs via retailer profiles.",
    )
    parser.add_argument(
        "--profile",
        help="Explicit profile name to parse (e.g. ulta_lipstick).",
    )
    parser.add_argument(
        "--urls",
        nargs="*",
        default=(),
        help="Explicit PDP URLs to parse (used with --profile).",
    )
    parser.add_argument(
        "--urls-file",
        type=Path,
        help="Path to a text file containing PDP URLs (one per line).",
    )
    parser.add_argument(
        "--retailer",
        help="Retailer identifier (e.g. ulta). When provided, categories are discovered automatically.",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        help="Category slugs to parse when using --retailer (e.g. lipstick foundation). Defaults to all retailer profiles.",
    )
    parser.add_argument(
        "--links-path",
        type=Path,
        default=Path("data/pdp/links.json"),
        help=(
            "Path to links.json used in retailer mode. When links exist for the "
            "requested retailer/category, they are used instead of rediscovering PDP URLs."
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum PLP pages to crawl per category when discovering PDP URLs (default: 50).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/pdp/cli"),
        help="Directory to store exports (defaults to data/pdp/cli).",
    )
    parser.add_argument(
        "--no-evidence",
        action="store_true",
        help="Disable persisting raw HTML/JSON evidence blobs.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite CSV exports and PDP store rows instead of appending timestamp suffixes.",
    )
    parser.add_argument(
        "--reviews-only",
        action="store_true",
        help="Refresh review metadata only (updates parent extras, skips exports/images).",
    )
    parser.add_argument(
        "--locale",
        default="en-us",
        help="Locale path segment used to replace `{locale}` placeholders (default: en-us).",
    )
    parser.add_argument(
        "--human-pace",
        action="store_true",
        help="Throttle requests to mimic a Finnish analyst (weekdays 08:00–20:00, 30–90s per PDP).",
    )
    parser.add_argument(
        "--only-missing-images",
        action="store_true",
        help="When set, reparse only products the review UI flags as 'Image unavailable'.",
    )
    return parser.parse_args(argv)


def _normalize_category(value: str) -> str:
    return canonical_category_key("", value)


def _category_variants(value: str) -> set[str]:
    """Return normalized value plus simple singular/plural variants."""
    normalized = _normalize_category(value)
    variants: set[str] = {normalized}
    if normalized.endswith("ies") and len(normalized) > 3:
        variants.add(normalized[:-3] + "y")
    if normalized.endswith("es") and len(normalized) > 2:
        variants.add(normalized[:-2])
    if normalized.endswith("s") and len(normalized) > 1:
        variants.add(normalized[:-1])
    return {variant for variant in variants if variant}


def _profile_matches_category(profile: PDPProfile, category: str) -> bool:
    target_category = canonical_category_key(profile.retailer, category)
    target_variants = _category_variants(target_category)
    if not target_variants:
        return False
    profile_keys: set[str] = set()
    if "_" in profile.profile_name:
        profile_keys |= _category_variants(
            profile_category_key(profile.retailer, profile.profile_name)
        )
    for hint in profile.category_hints:
        slug = hint.split("/")[-1]
        profile_keys |= _category_variants(
            canonical_category_key(profile.retailer, slug)
        )
    return bool(profile_keys & target_variants)


def _load_retailer_profiles(retailer: str) -> list[PDPProfile]:
    summaries = iter_profile_summaries()
    matched = [
        load_profile(summary.profile_name)
        for summary in summaries
        if summary.retailer.lower() == retailer.lower()
    ]
    return matched


def _profile_category_key(profile: PDPProfile) -> str:
    return profile_category_key(profile.retailer, profile.profile_name)


def _load_links_for_retailer(
    links_path: Path,
    *,
    retailer: str,
    categories: set[str] | None,
) -> dict[str, list[str]]:
    if not links_path.exists():
        return {}

    payload = json.loads(links_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}

    retailer_payload = payload.get(retailer.lower())
    if not isinstance(retailer_payload, dict):
        return {}

    out: dict[str, list[str]] = {}
    for category_key, links in retailer_payload.items():
        normalized_category = canonical_category_key(retailer, category_key)
        if categories and normalized_category not in categories:
            continue
        if not isinstance(links, list):
            continue
        deduped: list[str] = []
        seen: set[str] = set()
        for link in links:
            url = str(link).strip()
            if not url or url in seen:
                continue
            deduped.append(url)
            seen.add(url)
        out[normalized_category] = deduped
    return out


def _discover_for_profile(
    profile: PDPProfile,
    *,
    max_pages: int,
) -> list[str]:
    urls: set[str] = set()
    patterns: tuple[re.Pattern[str], ...] | None = None
    if profile.id_extractors.parent_from_url_regex:
        patterns = (profile.id_extractors.parent_from_url_regex,)
    headers = get_headers_for_retailer(profile.retailer)
    proxies = get_proxies_for_retailer(profile.retailer)
    retailer_lower = profile.retailer.lower()
    if retailer_lower == "purina":
        session = requests.Session()
        products, _payload = fetch_purina_wet_cat_food_products(session)
        urls = {
            purina_product_url(parent_id, str(product.get("url") or ""))
            for product in products
            if (parent_id := purina_parent_id_from_url(str(product.get("url") or "")))
        }
        return sorted(urls)
    if retailer_lower == "sephora":
        storage_path = Path("caches") / "sephora_storage_state.json"
        fetcher = SephoraFetcher(
            headers=headers if headers else None,
            proxies=proxies if proxies else None,
            storage_path=storage_path,
        )
    elif retailer_lower == "amazon":
        storage_path = Path("caches") / "amazon_storage_state.json"
        fetcher = AmazonFetcher(
            headers=headers if headers else None,
            proxies=proxies if proxies else None,
            storage_path=storage_path,
        )
    else:
        fetcher = HTMLFetcher(
            headers=headers if headers else None,
            proxies=proxies if proxies else None,
        )
    for category_url in profile.category_urls:
        discovered = discover_pdp_urls(
            [category_url],
            max_pages=max_pages,
            fetcher=fetcher,
            allowed_patterns=patterns,
            raise_on_error=False,
            retailer=profile.retailer,
        )
        for raw_url in discovered:
            canonical = raw_url
            if profile.base_url:
                path = urlparse(raw_url).path
                canonical = urljoin(
                    profile.base_url.rstrip("/") + "/", path.lstrip("/")
                )
            urls.add(canonical)
    return sorted(urls)


def _load_urls(urls: Iterable[str], urls_file: Path | None) -> list[str]:
    collected = [url.strip() for url in urls if url and url.strip()]
    if urls_file:
        if not urls_file.exists():
            raise FileNotFoundError(f"URL file not found: {urls_file}")
        file_urls = [
            line.strip()
            for line in urls_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        collected.extend(file_urls)
    deduped: list[str] = []
    seen: set[str] = set()
    for url in collected:
        if url not in seen:
            deduped.append(url)
            seen.add(url)
    return deduped


def _parent_id_from_url(profile: PDPProfile, url: str) -> str | None:
    pattern = profile.id_extractors.parent_from_url_regex
    if not pattern:
        return None
    match = pattern.search(url)
    if not match:
        return None
    return match.group(1) if match.groups() else match.group(0)


def _filter_existing_urls(
    profile: PDPProfile,
    urls: list[str],
    existing_ids: set[str],
) -> tuple[list[str], int]:
    filtered: list[str] = []
    skipped = 0
    for url in urls:
        parent_id = _parent_id_from_url(profile, url)
        if parent_id and parent_id in existing_ids:
            skipped += 1
            continue
        filtered.append(url)
    return filtered, skipped


def _sanitize_remote_url_ui(value: object | None) -> str | None:
    """Match the catalog UI's remote URL guard: only HTTP(S), trimmed, non-empty."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return None
    return text


def _record_parent_id(record: dict[str, object]) -> str | None:
    for key in ("product", "parent_product_id", "parent"):
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _record_variant_id(record: dict[str, object]) -> str | None:
    for key in ("variant", "variant_id"):
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _has_image_like_ui(
    record: dict[str, object],
    *,
    record_type: str,
    cache: dict[str, bool],
) -> bool:
    """Replicate the UI's resolveCardImage logic."""
    parent_id = _record_parent_id(record)
    variant_id = _record_variant_id(record) if record_type == "variant" else None
    hero_url = _sanitize_remote_url_ui(record.get("hero_image_url"))
    swatch_url = _sanitize_remote_url_ui(record.get("swatch_image_url"))
    remote_url = hero_url or swatch_url

    cache_key = f"{parent_id or ''}::{variant_id or ''}"
    if cache_key in cache:
        return cache[cache_key]

    if not parent_id:
        if remote_url:
            try:
                response = requests.get(remote_url, timeout=10)
            except requests.RequestException:
                response = None
            cache[cache_key] = bool(response and response.ok and response.content)
            return cache[cache_key]
        cache[cache_key] = False
        return False

    prefer_remote = bool(remote_url)
    helpers = _load_pdp_api_helpers()
    resolve_image_path = helpers["_resolve_image_path"]
    try:
        path = resolve_image_path(parent_id, variant_id, prefer_remote=prefer_remote)
    except Exception:
        path = None
    if path and Path(path).exists():
        cache[cache_key] = True
        return True

    if remote_url:
        try:
            response = requests.get(remote_url, timeout=10)
        except requests.RequestException:
            response = None
        if response is not None and response.ok and response.content:
            cache[cache_key] = True
            return True

    cache[cache_key] = False
    return False


def _load_missing_image_urls(
    pdp_store_path: Path,
    retailer: str,
    categories: Sequence[str] | None = None,
) -> list[tuple[str, list[str]]]:
    """Return (pdp_url, categories) for parents whose cards would show 'Image unavailable' in the UI."""
    enforce_default_pdp_store_path(pdp_store_path)
    requested_categories = (
        {
            canonical_category_key(retailer, category)
            for category in categories
            if category
        }
        if categories
        else None
    )
    helpers = _load_pdp_api_helpers()
    list_review_categories = helpers["list_review_categories"]
    gather_records = helpers["_gather_records"]
    try:
        category_items = list_review_categories(
            retailer=retailer, brands=None
        ).categories
    except Exception:
        return []
    category_keys = [
        item.key
        for item in category_items
        if item.key
        and (
            requested_categories is None
            or canonical_category_key(retailer, item.key) in requested_categories
        )
    ]
    if not category_keys:
        return []

    try:
        records_response = gather_records(
            retailer=retailer,
            category_keys=category_keys,
            brands=[],
            record_type="parent",
            filters=[],
            limit=None,
            download_all=True,
            pareto_filter=[],
            price_band_filter=[],
        )
        records = getattr(records_response, "records", None)
        if records is None:
            records = (
                records_response.get("records", [])
                if isinstance(records_response, dict)
                else []
            )
    except Exception:
        return []

    missing: list[tuple[str, list[str]]] = []
    cache: dict[str, bool] = {}
    seen_parents: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            continue
        parent_id = _record_parent_id(record)
        if not parent_id or parent_id in seen_parents:
            continue

        has_image = _has_image_like_ui(record, record_type="parent", cache=cache)
        seen_parents.add(parent_id)
        if has_image:
            continue

        pdp_url = str(record.get("pdp_url") or "").strip()
        if not pdp_url:
            continue
        categories_for_record: list[str] = []
        category_key = record.get("category_key")
        if category_key:
            categories_for_record.append(str(category_key))
        missing.append((pdp_url, categories_for_record))

    return missing


def _write_csv(frame: pl.DataFrame, path: Path) -> None:
    export_frame = flatten_for_export(frame, list_separator=CSV_LIST_SEPARATOR)
    path.parent.mkdir(parents=True, exist_ok=True)
    export_frame.write_csv(path, include_header=True)


def _remove_legacy_parquet_exports(profile_dir: Path) -> None:
    """Remove obsolete local parser Parquet snapshots from a profile export."""

    for filename in ("parents.parquet", "variants.parquet"):
        path = profile_dir / filename
        if path.exists():
            path.unlink()


def _save_variant_images(
    run: ProfileRun,
    variants_df: pl.DataFrame,
    output_dir: Path,
    overwrite: bool,
) -> None:
    """Persist hero/swatch images for the current run into the export directory."""
    profile_dir = output_dir / run.profile.profile_name
    record_count = get_row_count(variants_df)
    if record_count == 0:
        return

    image_records = variants_df.to_dicts()
    if not image_records:
        return

    image_dir = profile_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    sys.stdout.write(f"Downloading product images to {image_dir}...\n")
    sys.stdout.flush()

    skip_existing = not overwrite
    downloaded, errors = download_variant_images(
        image_records,
        image_dir,
        skip_existing=skip_existing,
    )

    sys.stdout.write(f"Saved {len(downloaded)} images (errors: {len(errors)}).\n")
    if errors:
        sys.stderr.write("Image download issues:\n")
        for err in errors:
            attempted = (
                ", ".join(err.attempted_urls) if err.attempted_urls else "no URLs"
            )
            sys.stderr.write(
                (
                    f"  - parent {err.parent_product_id or '(unknown)'} "
                    f"variant {err.variant_id or '(unknown)'}: {err.reason} "
                    f"[attempted: {attempted}]\n"
                )
            )
    sys.stdout.flush()
    if errors:
        sys.stderr.flush()


def _export_results(
    run: ProfileRun,
    parents_df: pl.DataFrame,
    variants_df: pl.DataFrame,
    summary: dict[str, object],
    output_dir: Path,
    overwrite: bool,
) -> None:
    profile_dir = output_dir / run.profile.profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    _remove_legacy_parquet_exports(profile_dir)

    summary_path = profile_dir / "summary.json"
    parents_csv = profile_dir / "parents.csv"
    variants_csv = profile_dir / "variants.csv"

    if not overwrite:
        if parents_csv.exists():
            existing_parents = pl.read_csv(parents_csv)
            existing_parents, parents_df = _align_key_types(
                existing_parents, parents_df, ["parent_product_id"]
            )
            existing_parents = _normalize_list_columns(
                existing_parents, PARENT_LIST_COLUMNS
            )
            parents_df = _normalize_list_columns(parents_df, PARENT_LIST_COLUMNS)
            parents_df = pl.concat([existing_parents, parents_df]).unique(
                "parent_product_id", keep="last"
            )

        if variants_csv.exists():
            existing_variants = pl.read_csv(
                variants_csv,
                dtypes={"price": VARIANT_SCHEMA["price"]},
            )
            existing_variants = _cast_decimal_columns(existing_variants, ["price"])
            variants_df = _cast_decimal_columns(variants_df, ["price"])
            existing_variants, variants_df = _align_key_types(
                existing_variants, variants_df, ["parent_product_id", "variant_id"]
            )
            existing_variants = _normalize_list_columns(
                existing_variants, VARIANT_LIST_COLUMNS
            )
            variants_df = _normalize_list_columns(variants_df, VARIANT_LIST_COLUMNS)
            variants_df = pl.concat([existing_variants, variants_df]).unique(
                ["parent_product_id", "variant_id"], keep="last"
            )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    if get_row_count(parents_df) > 0:
        _write_csv(parents_df, parents_csv)
    if get_row_count(variants_df) > 0:
        _write_csv(variants_df, variants_csv)

    sys.stdout.write(
        (
            f"[{run.profile.profile_name}] exports written:\n"
            f"  Parents CSV:   {parents_csv}\n"
            f"  Variants CSV:  {variants_csv}\n"
            f"  Summary JSON:  {summary_path}\n"
        )
    )


def _align_key_types(
    existing: pl.DataFrame, current: pl.DataFrame, key_columns: list[str]
) -> tuple[pl.DataFrame, pl.DataFrame]:
    casts_existing: list[pl.Expr] = []
    casts_current: list[pl.Expr] = []

    for column in key_columns:
        if column in existing.columns:
            casts_existing.append(pl.col(column).cast(pl.Utf8).alias(column))
        if column in current.columns:
            casts_current.append(pl.col(column).cast(pl.Utf8).alias(column))

    if casts_existing:
        existing = existing.with_columns(casts_existing)
    if casts_current:
        current = current.with_columns(casts_current)

    return existing, current


def _cast_decimal_columns(df: pl.DataFrame, columns: Sequence[str]) -> pl.DataFrame:
    casts = [
        pl.col(column).cast(dtype, strict=False).alias(column)
        for column in columns
        if (dtype := VARIANT_SCHEMA.get(column)) is not None and column in df.columns
    ]
    if not casts:
        return df
    return df.with_columns(casts)


def _normalize_list_columns(
    df: pl.DataFrame, list_columns: Sequence[str]
) -> pl.DataFrame:
    casts: list[pl.Expr] = []
    for name in list_columns:
        if name not in df.columns:
            continue
        dtype = df.schema.get(name)
        if isinstance(dtype, pl.List):
            casts.append(pl.col(name).cast(pl.List(pl.Utf8)).alias(name))
        else:
            casts.append(
                pl.when(pl.col(name).is_null() | (pl.col(name) == ""))
                .then(pl.lit([]))
                .otherwise(pl.col(name).cast(pl.Utf8).str.split(CSV_LIST_SEPARATOR))
                .alias(name)
            )
    if not casts:
        return df
    return df.with_columns(casts)


FAILED_URL_PREVIEW_LIMIT = 1


def _emit_failed_urls(failures: Sequence[str]) -> None:
    if not failures:
        return
    preview = list(failures[:FAILED_URL_PREVIEW_LIMIT])
    total = len(failures)
    header = "Failed URLs"
    if total > FAILED_URL_PREVIEW_LIMIT:
        header += f" (showing first {FAILED_URL_PREVIEW_LIMIT})"
    sys.stdout.write(header + ":\n")
    sys.stdout.write("\n".join(f"  - {url}" for url in preview) + "\n")
    if total > FAILED_URL_PREVIEW_LIMIT:
        sys.stdout.write(f"  ... {total - FAILED_URL_PREVIEW_LIMIT} more not shown\n")
    sys.stdout.flush()


def _runs_from_args(args: argparse.Namespace) -> list[ProfileRun]:
    if args.retailer:
        if args.urls or args.urls_file or args.profile:
            raise ValueError(
                "When using --retailer, do not supply --profile/--urls/--urls-file."
            )
        profiles = [
            apply_locale(profile, args.locale)
            for profile in _load_retailer_profiles(args.retailer)
        ]
        if not profiles:
            raise ValueError(f"No profiles found for retailer: {args.retailer}")
        if args.categories:
            requested = {
                canonical_category_key(args.retailer, category)
                for category in args.categories
            }
            profiles = [
                profile
                for profile in profiles
                if any(
                    _profile_matches_category(profile, category)
                    for category in requested
                )
            ]
            if not profiles:
                raise ValueError(
                    f"No profiles matched categories {', '.join(args.categories)} for retailer {args.retailer}."
                )
        else:
            requested = None
        links_by_category = _load_links_for_retailer(
            args.links_path,
            retailer=args.retailer,
            categories=requested,
        )
        missing_image_urls: list[tuple[str, list[str]]] = []
        if args.only_missing_images:
            try:
                missing_image_urls = _load_missing_image_urls(
                    enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH),
                    args.retailer,
                    categories=args.categories,
                )
            except Exception:
                missing_image_urls = []
        if args.only_missing_images:
            total_missing = len(missing_image_urls)
            sys.stdout.write(
                f"Found {total_missing} parent(s) missing images for retailer '{args.retailer}'.\n"
            )
            sys.stdout.flush()
        runs: list[ProfileRun] = []
        for profile in profiles:
            if args.only_missing_images:
                seen_urls: set[str] = set()
                urls = []
                for url, _ in missing_image_urls:
                    if not url or url in seen_urls:
                        continue
                    if _parent_id_from_url(profile, url):
                        urls.append(url)
                        seen_urls.add(url)
                if not urls:
                    continue
                runs.append(
                    ProfileRun(profile=profile, urls=urls, discovered_count=len(urls))
                )
            else:
                category_key = _normalize_category(_profile_category_key(profile))
                urls = links_by_category.get(category_key, [])
                if not urls:
                    urls = _discover_for_profile(profile, max_pages=args.max_pages)
                runs.append(
                    ProfileRun(profile=profile, urls=urls, discovered_count=len(urls))
                )
        return runs

    profile_name = args.profile or "ulta_lipstick"
    urls = _load_urls(args.urls, args.urls_file)
    if not urls:
        raise ValueError("No PDP URLs provided. Use --urls/--urls-file or --retailer.")
    profile = apply_locale(load_profile(profile_name), args.locale)
    return [ProfileRun(profile=profile, urls=urls, discovered_count=len(urls))]


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    load_env_from_secrets_file()
    pdp_store_path = enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH)
    postgres_enabled = is_postgres_enabled()
    if not postgres_enabled:
        sys.stderr.write(
            "PDP Postgres is not configured. Set PDP_DATABASE_URL or set "
            "PDP_STORE_BACKEND=postgres with DATABASE_URL, and make sure the SSH "
            "tunnel is active. run_pdp_parser.py requires the Postgres PDP store.\n"
        )
        return 1
    try:
        runs = _runs_from_args(args)
    except Exception as exc:  # noqa: BLE001 - surfaced to user
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    try:
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        if args.reviews_only:
            sys.stdout.write(
                "Reviews-only mode: skipping CSV exports and image downloads.\n"
            )
            sys.stdout.flush()

        storage = None if args.no_evidence or args.reviews_only else EvidenceStorage()
        store = PDPStore(pdp_store_path)
        existing_cache: dict[str, set[str]] = {}
        image_cache: dict[str, set[str]] = {}
        total_parents_before = store.count_parents()
        total_variants_before = store.count_variants()
        profile_summaries: list[ProfileRunSummary] = []

        pacing = HumanPacingController() if args.human_pace else None
        any_parsed = False
        for run in runs:
            sys.stdout.write(
                f"\n=== {run.profile.display_name} ({run.profile.profile_name}) ===\n"
            )
            sys.stdout.write(f"Discovered {run.discovered_count} URLs.\n")
            sys.stdout.flush()

            before_parent_count = store.count_parents(run.profile.retailer)
            before_variant_count = store.count_variants(run.profile.retailer)

            urls = run.urls
            cache_key = run.profile.retailer.lower()
            run.skipped_existing = 0
            if (
                not args.only_missing_images
                and not args.overwrite
                and not args.reviews_only
            ):
                existing_ids = existing_cache.setdefault(
                    cache_key,
                    store.existing_parent_ids(run.profile.retailer),
                )
                urls, skipped = _filter_existing_urls(run.profile, urls, existing_ids)
                run.skipped_existing = skipped
                if skipped:
                    sys.stdout.write(
                        f"Skipped {skipped} previously parsed PDPs (use --overwrite to reparse).\n"
                    )

            if not urls:
                sys.stdout.write("No new PDPs to parse for this profile.\n")
                sys.stdout.flush()
                profile_summaries.append(
                    ProfileRunSummary(
                        profile_name=run.profile.profile_name,
                        retailer=run.profile.retailer,
                        parent_before=before_parent_count,
                        parent_after=before_parent_count,
                        parent_delta=0,
                        variant_before=before_variant_count,
                        variant_after=before_variant_count,
                        variant_delta=0,
                        parsed_parents=0,
                        parsed_variants=0,
                        skipped_existing=run.skipped_existing,
                        failures=0,
                    )
                )
                continue

            sys.stdout.write(f"Parsing {len(urls)} PDPs...\n")
            sys.stdout.flush()
            batch = parse_urls_to_batch(
                run.profile.profile_name,
                urls,
                storage=storage,
                pacing=pacing,
            )
            parents = list(batch.parents())
            variants = list(batch.variants())
            summary = summarize_batch(batch)
            failures_count = len(batch.failures)

            if args.reviews_only:
                try:
                    metrics = store.update_parent_reviews(batch, summary=summary)
                    parent_count = len(parents)
                    sys.stdout.write(
                        f"Updated reviews for {parent_count} parents (failures: {failures_count}).\n"
                    )
                    _emit_store_metrics(metrics)
                except Exception as exc:  # noqa: BLE001 - diagnostic for CLI usage
                    sys.stderr.write(
                        f"Failed to update reviews in the PDP store: {exc}\n"
                    )
                after_parent_count = store.count_parents(run.profile.retailer)
                after_variant_count = store.count_variants(run.profile.retailer)
                profile_summaries.append(
                    ProfileRunSummary(
                        profile_name=run.profile.profile_name,
                        retailer=run.profile.retailer,
                        parent_before=before_parent_count,
                        parent_after=after_parent_count,
                        parent_delta=after_parent_count - before_parent_count,
                        variant_before=before_variant_count,
                        variant_after=after_variant_count,
                        variant_delta=after_variant_count - before_variant_count,
                        parsed_parents=len(parents),
                        parsed_variants=len(variants),
                        skipped_existing=run.skipped_existing,
                        failures=failures_count,
                    )
                )
                if failures_count:
                    _emit_failed_urls(batch.failures)
                if parents:
                    any_parsed = True
                sys.stdout.flush()
                continue

            parents_df = parents_to_frame(parents).with_columns(
                pl.col("parent_product_id").cast(pl.Utf8)
            )
            variants_df = variants_to_frame(variants).with_columns(
                pl.col("parent_product_id").cast(pl.Utf8),
                pl.col("variant_id").cast(pl.Utf8),
            )
            variants_df = _cast_decimal_columns(variants_df, ["price"])

            if not args.overwrite:
                existing_cache.setdefault(cache_key, set()).update(
                    parent.parent_product_id for parent in parents
                )

            try:
                metrics = store.write_batch(
                    batch, summary=summary, overwrite=args.overwrite
                )
                sys.stdout.write("PDP store updated.\n")
                _emit_store_metrics(metrics)
            except Exception as exc:  # noqa: BLE001 - diagnostic for CLI usage
                sys.stderr.write(f"Failed to persist to the PDP store: {exc}\n")
            after_parent_count = store.count_parents(run.profile.retailer)
            after_variant_count = store.count_variants(run.profile.retailer)
            profile_summaries.append(
                ProfileRunSummary(
                    profile_name=run.profile.profile_name,
                    retailer=run.profile.retailer,
                    parent_before=before_parent_count,
                    parent_after=after_parent_count,
                    parent_delta=after_parent_count - before_parent_count,
                    variant_before=before_variant_count,
                    variant_after=after_variant_count,
                    variant_delta=after_variant_count - before_variant_count,
                    parsed_parents=len(parents),
                    parsed_variants=len(variants),
                    skipped_existing=run.skipped_existing,
                    failures=failures_count,
                )
            )

            _export_results(
                run, parents_df, variants_df, summary, output_dir, args.overwrite
            )
            try:
                _save_variant_images(run, variants_df, output_dir, args.overwrite)
            except Exception as exc:  # noqa: BLE001 - surfaced to user
                sys.stderr.write(f"Failed to download product images: {exc}\n")

            parent_count = len(parents)
            variant_count = len(variants)
            sys.stdout.write(
                (
                    f"Parsed {parent_count} parents and {variant_count} variants "
                    f"(failures: {failures_count}).\n"
                )
            )
            sys.stdout.flush()
            if failures_count:
                _emit_failed_urls(batch.failures)
            any_parsed = any_parsed or bool(parents)

        total_parents_after = store.count_parents()
        total_variants_after = store.count_variants()

        sys.stdout.write("\n=== PDP Store Totals ===\n")
        sys.stdout.write(
            f"Parents: {total_parents_before} -> {total_parents_after} "
            f"(Δ {total_parents_after - total_parents_before:+d})\n"
        )
        sys.stdout.write(
            f"Variants: {total_variants_before} -> {total_variants_after} "
            f"(Δ {total_variants_after - total_variants_before:+d})\n"
        )
        if profile_summaries:
            sys.stdout.write("\nPer-profile breakdown:\n")
            for summary in profile_summaries:
                sys.stdout.write(
                    (
                        f"  - {summary.profile_name} ({summary.retailer}): "
                        f"parents {summary.parent_before} -> {summary.parent_after} "
                        f"(Δ {summary.parent_delta:+d}), "
                        f"variants {summary.variant_before} -> {summary.variant_after} "
                        f"(Δ {summary.variant_delta:+d}), "
                        f"parsed {summary.parsed_parents} parents / {summary.parsed_variants} variants, "
                        f"skipped {summary.skipped_existing}, failures {summary.failures}\n"
                    )
                )
        sys.stdout.flush()

        if not any_parsed:
            sys.stdout.write("No profiles were parsed.\n")
            sys.stdout.flush()
        return 0
    except Exception as exc:  # noqa: BLE001 - keep CLI failure explicit
        sys.stderr.write(f"Error: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
