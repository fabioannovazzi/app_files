from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
)
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import (
    sync_playwright,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.adapters import NullAdapter
from modules.pdp.adapters.amazon import AmazonAdapter
from modules.pdp.adapters.chewy import ChewyAdapter
from modules.pdp.adapters.cosmoprofbeauty import CosmoprofbeautyAdapter
from modules.pdp.adapters.guestinresidence import GuestInResidenceAdapter
from modules.pdp.adapters.kiko import KikoAdapter
from modules.pdp.adapters.lorealparis import LorealParisAdapter
from modules.pdp.adapters.purina import PurinaAdapter
from modules.pdp.adapters.saksfifthavenue import SaksfifthavenueAdapter
from modules.pdp.adapters.saloncentric import SaloncentricAdapter
from modules.pdp.adapters.sephora import SephoraAdapter
from modules.pdp.adapters.tikicat import TikiCatAdapter
from modules.pdp.adapters.ulta import UltaAdapter
from modules.pdp.adapters.vince import VinceAdapter
from modules.pdp.category_keys import (
    canonical_category_key,
    canonical_category_keys,
    profile_category_key,
)
from modules.pdp.engine import PDPParser
from modules.pdp.image_downloader import download_variant_images
from modules.pdp.models import BatchParseResult, ParseResult, Variant
from modules.pdp.postgres_compat import connect_pdp_database
from modules.pdp.profile_loader import iter_profile_summaries, load_profile
from modules.pdp.review_constants import enforce_default_pdp_store_path
from modules.pdp.storage import EvidenceStorage
from modules.pdp.store import PDPStore
from modules.utilities.secrets_loader import load_env_from_secrets_file
from scripts.run_retailer_listing_discovery_cdp import (
    _activate_cdp_tab_for_manual_navigation,
    _manual_navigation_urls_match,
    _paste_url_into_windows_chrome,
    _wait_for_cdp_tab_url,
)

LOGGER = logging.getLogger(__name__)
SEPHORA_IMG_SELECTORS = (
    "img[data-at='main_product_image']",
    "img[src*='productimages/sku']",
    "img[src*='Pim']",
)
AMAZON_ASIN_IN_PATH = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})", re.IGNORECASE)
HTTP_ERROR_CODE_IN_TEXT = re.compile(r"error code\s*(\d{3})", re.IGNORECASE)
CHEWY_FATAL_FAILURE_MESSAGE_RE = re.compile(r"unusable Chewy page \(([^)]+)\) at (.+)$")
CLOUDFLARE_CHALLENGE_MARKERS = (
    "just a moment",
    "performing security verification",
    "verify you are human",
    "verifying you are human",
    "enable javascript and cookies to continue",
)
KASADA_CHALLENGE_MARKERS = (
    "window.kpsdk",
    "ips.js?kp_uid",
    "x-kpsdk",
)
KNOWN_INTERSTITIAL_MARKERS = CLOUDFLARE_CHALLENGE_MARKERS + (
    "access to this page has been denied",
    "web server is down",
    "web server is returning an unknown error",
    "bad gateway",
)
ASYNCIO_SUBPROCESS_ENV = "PDP_FETCH_SYNC_SUBPROCESS"
MANUAL_INTERVENTION_REASONS = {
    "cloudflare_challenge",
    "access_denied_interstitial",
}
SAKS_GENERIC_TITLES = {
    "saksfifthavenue.com",
    "saks fifth avenue",
}
SAKS_MIN_VALID_HTML_CHARS = 5000
CHEWY_MIN_VALID_HTML_CHARS = 5000
CHEWY_CAPTURE_RETRY_REASONS = {
    "blank_html_shell",
    "kasada_challenge",
}
CHEWY_CAPTURE_MAX_ATTEMPTS = 4
CHEWY_CAPTURE_RETRY_WAIT_MS = 3000
CHEWY_HOME_URL = "https://www.chewy.com/"
CHEWY_AUTO_PASTE_WAIT_SECONDS = 20.0
CHEWY_AUTO_PASTE_ATTEMPTS = 5
CHEWY_GOTO_TIMEOUT_MS = 20000
CHEWY_REQUEST_PAUSE_SECONDS = 15.0
CHEWY_BATCH_PAUSE_EVERY = 30
CHEWY_BATCH_PAUSE_SECONDS = 180.0
FATAL_INVALID_PAGE_REASONS_BY_RETAILER: dict[str, set[str]] = {
    "chewy": {"blank_html_shell", "kasada_challenge"},
}
FATAL_PARSE_FAILURE_RETAILERS = {"chewy"}


class FatalPDPFetchError(RuntimeError):
    """Abort the current fetch run because the browser session is not usable."""


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch PDPs via attached Chrome (CDP) and parse with existing profiles."
    )
    parser.add_argument(
        "--remote-url",
        default="http://localhost:9222",
        help="Chrome DevTools endpoint (start Chrome with --remote-debugging-port).",
    )
    parser.add_argument("--url", help="Single PDP URL to fetch (testing mode).")
    parser.add_argument(
        "--retailer", required=True, help="Retailer name (e.g., sephora, ulta, amazon)."
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        help="Category slugs to include (profile name without retailer_ prefix). Defaults to all retailer profiles.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Navigation timeout for Playwright operations (milliseconds).",
    )
    parser.add_argument(
        "--max-per-run",
        type=int,
        default=0,
        help="Optional cap on number of PDPs to fetch this run (0 means no cap).",
    )
    parser.add_argument(
        "--links-path",
        type=Path,
        default=Path("data/pdp/links.json"),
        help="Path to links JSON (retailer -> category -> URLs) for batch mode.",
    )
    parser.add_argument(
        "--task-source",
        choices=("links-json", "latest-listing"),
        default="links-json",
        help=(
            "Where batch PDP URLs come from. Use links-json for the legacy "
            "data/pdp/links.json input, or latest-listing to scrape URLs from "
            "the latest retailer_listing_observations rows in the PDP store."
        ),
    )
    parser.add_argument(
        "--listing-sort-modes",
        nargs="*",
        help=(
            "When --task-source latest-listing is used, limit PDP URLs to these "
            "sort modes, for example: best_selling newest. Defaults to all sort "
            "modes present in the latest listing crawl."
        ),
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=8000,
        help="Wait after navigation before capturing HTML (milliseconds).",
    )
    parser.add_argument(
        "--request-pause-seconds",
        type=float,
        default=5.0,
        help="Pause between PDP requests in seconds (default: 5).",
    )
    parser.add_argument(
        "--category-pause-seconds",
        type=float,
        default=1200.0,
        help="Pause between categories in seconds (default: 1200 = 20 minutes).",
    )
    parser.add_argument(
        "--batch-pause-every",
        type=int,
        default=0,
        help=(
            "Pause automatically after this many successfully saved PDPs "
            "(0 disables batch cooldowns)."
        ),
    )
    parser.add_argument(
        "--batch-pause-seconds",
        type=float,
        default=0.0,
        help=(
            "How long to sleep during each automatic batch cooldown "
            "(used with --batch-pause-every)."
        ),
    )
    parser.add_argument(
        "--restart-delay-seconds",
        type=float,
        default=30.0,
        help="Wait before retrying after a task-level crash (default: 30 seconds).",
    )
    parser.add_argument(
        "--max-task-restarts",
        type=int,
        default=0,
        help="Maximum restart attempts per PDP task (0 means unlimited).",
    )
    parser.add_argument(
        "--cdp-connect-retry-seconds",
        type=float,
        default=20.0,
        help="Wait between retries when Chrome CDP is unavailable (default: 20 seconds).",
    )
    parser.add_argument(
        "--cdp-connect-max-attempts",
        type=int,
        default=5,
        help="Maximum attempts to reconnect to CDP (default: 5; 0 means unlimited).",
    )
    parser.add_argument(
        "--rescrape-existing",
        action="store_true",
        help=(
            "Force re-scrape of URLs already present in storage. "
            "By default, existing PDPs are skipped when the parent id can be "
            "derived from the URL."
        ),
    )
    parser.add_argument(
        "--purge-invalid-existing",
        action="store_true",
        help=(
            "Before filtering existing rows, delete known invalid/interstitial PDP "
            "rows for the requested retailer URLs so only that bad subset is retried."
        ),
    )
    parser.add_argument(
        "--challenge-poll-seconds",
        type=float,
        default=5.0,
        help="Poll interval while waiting for manual Cloudflare clearance (default: 5).",
    )
    parser.add_argument(
        "--challenge-max-wait-seconds",
        type=float,
        default=0.0,
        help=(
            "Maximum time to wait for manual Cloudflare clearance. "
            "Use 0 to wait indefinitely (default: 0)."
        ),
    )
    parser.add_argument(
        "--manual-navigation-auto-paste",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "For blocked retailers such as Chewy, load each PDP by pasting the URL "
            "into the visible Chrome address bar instead of using plain CDP navigation."
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
        help="How many times to retry auto-paste navigation before failing.",
    )
    return parser.parse_args(argv)


def _apply_retailer_defaults(args: argparse.Namespace) -> argparse.Namespace:
    retailer = str(args.retailer or "").strip().lower()
    if retailer == "chewy":
        if args.manual_navigation_auto_paste is None:
            args.manual_navigation_auto_paste = True
        if args.manual_navigation_auto_paste_wait_seconds == 60.0:
            args.manual_navigation_auto_paste_wait_seconds = (
                CHEWY_AUTO_PASTE_WAIT_SECONDS
            )
        if args.manual_navigation_auto_paste_attempts == 3:
            args.manual_navigation_auto_paste_attempts = CHEWY_AUTO_PASTE_ATTEMPTS
        if args.timeout_ms == 45000:
            args.timeout_ms = CHEWY_GOTO_TIMEOUT_MS
        if args.request_pause_seconds == 5.0:
            args.request_pause_seconds = CHEWY_REQUEST_PAUSE_SECONDS
        if args.batch_pause_every == 0:
            args.batch_pause_every = CHEWY_BATCH_PAUSE_EVERY
        if args.batch_pause_seconds == 0.0:
            args.batch_pause_seconds = CHEWY_BATCH_PAUSE_SECONDS
    elif args.manual_navigation_auto_paste is None:
        args.manual_navigation_auto_paste = False
    return args


def _running_asyncio_loop_present() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _maybe_respawn_outside_asyncio_loop(argv: Sequence[str]) -> int | None:
    if os.environ.get(ASYNCIO_SUBPROCESS_ENV) == "1":
        return None
    if not _running_asyncio_loop_present():
        return None

    env = os.environ.copy()
    env[ASYNCIO_SUBPROCESS_ENV] = "1"
    command = [sys.executable, str(Path(__file__).resolve()), *list(argv)]
    LOGGER.warning(
        "Active asyncio loop detected; respawning cdp_fetch_pdp.py in a plain subprocess."
    )
    result = subprocess.run(command, env=env, check=False)
    return int(result.returncode)


def _cdp_version_url(remote_url: str) -> str:
    split = urlsplit(remote_url)
    path = split.path.rstrip("/")
    if path.endswith("/json/version"):
        version_path = path
    elif path:
        version_path = f"{path}/json/version"
    else:
        version_path = "/json/version"
    return urlunsplit((split.scheme, split.netloc, version_path, "", ""))


def _probe_cdp_endpoint(
    remote_url: str, *, timeout_seconds: float = 2.0
) -> tuple[bool, str]:
    version_url = _cdp_version_url(remote_url)
    try:
        with urlopen(version_url, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", 200) or 200)
            if status >= 400:
                return False, f"CDP endpoint returned HTTP {status} at {version_url}"
            return True, version_url
    except URLError as exc:
        return False, f"Chrome/CDP is not reachable at {version_url}: {exc.reason}"
    except Exception as exc:  # noqa: BLE001 - surface probe details directly
        return False, f"Chrome/CDP probe failed at {version_url}: {exc}"


def _normalize_category_token(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _merge_category_path(
    existing_path: Sequence[str] | None,
    category_key: str | None,
) -> tuple[str, ...]:
    merged = tuple(
        str(item).strip() for item in (existing_path or ()) if str(item).strip()
    )
    normalized_key = _normalize_category_token(category_key)
    if not normalized_key:
        return merged
    existing_tokens = {_normalize_category_token(item) for item in merged}
    if normalized_key in existing_tokens:
        return merged
    return (*merged, str(category_key).strip())


def _apply_category_context(
    result: ParseResult | None, category_key: str | None
) -> ParseResult | None:
    if not result or not result.parent:
        return result
    if category_key:
        result.parent.category_path = _merge_category_path(
            getattr(result.parent, "category_path", ()),
            category_key,
        )
        result.parent.extras = dict(getattr(result.parent, "extras", {}) or {})
        result.parent.extras["category_key"] = category_key
    if not getattr(result.parent, "brand_raw", None):
        result.parent.brand_raw = getattr(result.parent, "brand_normalized", "") or ""
    if not getattr(result.parent, "title_raw", None):
        result.parent.title_raw = getattr(result.parent, "title_normalized", "") or ""
    if result.variants:
        for variant in result.variants:
            if category_key and hasattr(variant, "extras"):
                extras = getattr(variant, "extras") or {}
                extras = dict(extras)
                extras["category_key"] = category_key
                variant.extras = extras
            if not getattr(variant, "variant_id", None):
                pid = (
                    getattr(result.parent, "parent_product_id", "")
                    if result.parent
                    else ""
                )
                variant.variant_id = pid or "variant"
    return result


def _get_context(
    remote_url: str, *, playwright: object | None = None
) -> tuple[object, Browser, BrowserContext]:
    current_playwright = (
        playwright if playwright is not None else sync_playwright().start()
    )
    browser = current_playwright.chromium.connect_over_cdp(remote_url)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return current_playwright, browser, context


def _sleep_with_log(seconds: float, *, reason: str) -> None:
    if seconds <= 0:
        return
    LOGGER.info("Sleeping %.1f seconds (%s)...", seconds, reason)
    time.sleep(seconds)


def _should_take_batch_pause(
    *,
    processed: int,
    batch_pause_every: int,
    task_index: int,
    task_total: int,
    max_per_run: int | None,
) -> bool:
    if batch_pause_every <= 0 or processed <= 0:
        return False
    if processed % batch_pause_every != 0:
        return False
    if max_per_run is not None and processed >= max_per_run:
        return False
    return task_index < task_total


def _send_run_notification(
    *,
    success: bool,
    retailer: str,
    processed: int,
    downloaded_images: int,
    detail: str | None = None,
) -> None:
    status = "SUCCESS" if success else "FAILED"
    subject = f"[cdp_fetch_pdp] {status} retailer={retailer}"
    lines = [
        f"Status: {status}",
        f"Retailer: {retailer}",
        f"Processed PDPs: {processed}",
        f"Downloaded images: {downloaded_images}",
        f"Timestamp UTC: {dt.datetime.now(dt.timezone.utc).isoformat()}",
    ]
    if detail:
        lines.append(f"Detail: {detail}")
    body = "\n".join(lines)

    try:
        from modules.notifications.resend_client import (
            is_resend_configured,
            send_plain_text_email,
        )
        from modules.pdp.run_status_notifications import (
            resolve_notification_recipients,
        )
    except Exception as exc:  # noqa: BLE001 - optional notification dependency
        LOGGER.warning("Notification setup unavailable: %s", exc)
        return

    if not is_resend_configured():
        LOGGER.warning(
            "Notification skipped: RESEND_API_KEY/RESEND_FROM_EMAIL not configured."
        )
        return

    recipients = resolve_notification_recipients()
    if not recipients:
        LOGGER.info("Notification skipped: PDP_RUN_NOTIFY_EMAILS is not configured.")
        return
    sent = send_plain_text_email(list(recipients), subject, body)
    if sent:
        LOGGER.info("Notification email sent to %s", ",".join(recipients))
    else:
        LOGGER.warning("Notification email delivery failed to %s", ",".join(recipients))


def _send_operator_alert(*, subject: str, body: str) -> None:
    try:
        from modules.notifications.resend_client import (
            is_resend_configured,
            send_plain_text_email,
        )
        from modules.pdp.run_status_notifications import (
            resolve_notification_recipients,
        )
    except Exception as exc:  # noqa: BLE001 - optional notification dependency
        LOGGER.warning("Operator alert unavailable: %s", exc)
        return

    if not is_resend_configured():
        LOGGER.warning(
            "Operator alert skipped: RESEND_API_KEY/RESEND_FROM_EMAIL not configured."
        )
        return

    recipients = resolve_notification_recipients()
    if not recipients:
        LOGGER.info("Operator alert skipped: PDP_RUN_NOTIFY_EMAILS is not configured.")
        return
    sent = send_plain_text_email(list(recipients), subject, body)
    if sent:
        LOGGER.info("Operator alert email sent to %s", ",".join(recipients))
    else:
        LOGGER.warning("Operator alert delivery failed to %s", ",".join(recipients))


def _close_browser(browser: Browser | None) -> None:
    try:
        if browser is not None:
            browser.close()
    except Exception:
        pass


def _get_context_with_retry(
    remote_url: str,
    *,
    retry_seconds: float,
    max_attempts: int,
    playwright: object | None = None,
) -> tuple[object, Browser, BrowserContext]:
    attempts = 0
    while True:
        attempts += 1
        try:
            ready, detail = _probe_cdp_endpoint(remote_url)
            if not ready:
                raise ConnectionError(detail)
            return _get_context(remote_url, playwright=playwright)
        except Exception as exc:  # noqa: BLE001 - CDP endpoint can be transiently down
            message = str(exc).lower()
            if (
                "chrome/cdp is not reachable" in message
                or "cdp endpoint returned http" in message
            ):
                if max_attempts > 0 and attempts >= max_attempts:
                    raise RuntimeError(str(exc)) from exc
                LOGGER.warning(
                    "CDP endpoint unavailable at %s (attempt %d): %s",
                    remote_url,
                    attempts,
                    exc,
                )
                _sleep_with_log(
                    retry_seconds,
                    reason="waiting for Chrome/CDP to recover",
                )
                continue
            if "sync api inside the asyncio loop" in message:
                raise RuntimeError(
                    "Playwright Sync API cannot run inside an active asyncio loop. "
                    "Run this script from a regular shell process (python ...), "
                    "not inside a notebook/async runtime."
                ) from exc
            if max_attempts > 0 and attempts >= max_attempts:
                raise
            LOGGER.warning(
                "Unable to connect to CDP %s (attempt %d): %s",
                remote_url,
                attempts,
                exc,
            )
            _sleep_with_log(
                retry_seconds,
                reason="waiting for Chrome/CDP to recover",
            )


def _close_cdp_session(playwright: object | None, browser: Browser | None) -> None:
    try:
        if browser is not None:
            browser.close()
    except Exception:
        pass


def _image_records_for_result(result: ParseResult) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for variant in result.variants:
        if isinstance(variant, dict):
            records.append(dict(variant))
            continue
        records.append(
            {
                "retailer": getattr(variant, "retailer", None),
                "parent_product_id": getattr(variant, "parent_product_id", None),
                "variant_id": getattr(variant, "variant_id", None),
                "shade_name_raw": getattr(variant, "shade_name_raw", None),
                "shade_name_normalized": getattr(
                    variant, "shade_name_normalized", None
                ),
                "size_text_raw": getattr(variant, "size_text_raw", None),
                "price_raw": getattr(variant, "price_raw", None),
                "price": getattr(variant, "price", None),
                "currency": getattr(variant, "currency", None),
                "barcode": getattr(variant, "barcode", None),
                "swatch_image_url": getattr(variant, "swatch_image_url", None),
                "hero_image_url": getattr(variant, "hero_image_url", None),
                "availability": getattr(variant, "availability", None),
                "source_index": getattr(variant, "source_index", None),
                "qa_flags": getattr(variant, "qa_flags", ()),
                "extras": getattr(variant, "extras", {}),
            }
        )

    parent = result.parent
    if parent is not None:
        parent_hero = str(parent.extras.get("hero_image_url") or "").strip()
        if parent_hero:
            records.append(
                {
                    "retailer": parent.retailer,
                    "parent_product_id": parent.parent_product_id,
                    "variant_id": None,
                    "shade_name_raw": None,
                    "shade_name_normalized": None,
                    "size_text_raw": None,
                    "price_raw": None,
                    "price": None,
                    "currency": None,
                    "barcode": None,
                    "swatch_image_url": None,
                    "hero_image_url": parent_hero,
                    "availability": None,
                    "source_index": None,
                    "qa_flags": (),
                    "extras": {"image_role": "parent_hero"},
                }
            )
    return records


def _is_known_invalid_text(text: str | None) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    if lowered in SAKS_GENERIC_TITLES:
        return True
    if any(marker in lowered for marker in KNOWN_INTERSTITIAL_MARKERS):
        return True
    if "404 - page not found" in lowered or "page not found" in lowered:
        return True
    status_match = HTTP_ERROR_CODE_IN_TEXT.search(lowered)
    if not status_match:
        return False
    return int(status_match.group(1)) in {404, 502, 520, 521}


def _known_invalid_page_details(
    result: ParseResult,
    *,
    retailer: str,
    page_title: str = "",
) -> tuple[int | None, str] | None:
    parent_title = ""
    if result.parent is not None:
        parent_title = str(getattr(result.parent, "title_raw", "") or "")
    html = str(getattr(result.fetch_result, "html", "") or "")
    return _known_invalid_page_details_from_content(
        retailer=retailer,
        parent_title=parent_title,
        page_title=page_title,
        html=html,
    )


def _known_invalid_page_details_from_content(
    *,
    retailer: str,
    parent_title: str,
    page_title: str = "",
    html: str,
) -> tuple[int | None, str] | None:
    retailer_lower = retailer.lower()
    if retailer_lower not in {
        "chewy",
        "saloncentric",
        "cosmoprofbeauty",
        "saksfifthavenue",
    }:
        return None

    combined = "\n".join(part for part in (parent_title, html) if part).lower()
    if not combined:
        return None

    if retailer_lower == "chewy":
        html_length = len(str(html or "").strip())
        if html_length < 5000 and any(
            marker in combined for marker in KASADA_CHALLENGE_MARKERS
        ):
            return 429, "kasada_challenge"
        if html_length < CHEWY_MIN_VALID_HTML_CHARS and not _has_chewy_pdp_markers(
            html
        ):
            return 204, "blank_html_shell"

    if any(marker in combined for marker in CLOUDFLARE_CHALLENGE_MARKERS):
        return 403, "cloudflare_challenge"
    if "access to this page has been denied" in combined:
        return 403, "access_denied_interstitial"

    status_match = HTTP_ERROR_CODE_IN_TEXT.search(combined)
    if status_match:
        status_code = int(status_match.group(1))
        if status_code in {404, 502, 520, 521}:
            return status_code, f"error_interstitial_{status_code}"

    if "page not found" in combined:
        return 404, "error_interstitial_404"
    if "web server is down" in combined:
        return 521, "error_interstitial_521"
    if "web server is returning an unknown error" in combined:
        return 520, "error_interstitial_520"
    if "bad gateway" in combined:
        return 502, "error_interstitial_502"
    if retailer_lower == "saksfifthavenue":
        title_norm = str(page_title or parent_title or "").strip().lower()
        html_length = len(str(html or "").strip())
        if (
            title_norm in SAKS_GENERIC_TITLES
            and html_length < SAKS_MIN_VALID_HTML_CHARS
        ):
            return 503, "generic_shell_interstitial"
    return None


def _is_manual_intervention_content(
    *,
    retailer: str,
    title: str,
    html: str,
) -> bool:
    details = _known_invalid_page_details_from_content(
        retailer=retailer,
        parent_title=title,
        html=html,
    )
    if details is None:
        return False
    _status_code, reason = details
    return reason in MANUAL_INTERVENTION_REASONS


def _should_abort_after_invalid_page(*, retailer: str, reason: str) -> bool:
    retailer_reasons = FATAL_INVALID_PAGE_REASONS_BY_RETAILER.get(
        retailer.lower(), set()
    )
    return str(reason or "").strip() in retailer_reasons


def _should_abort_after_parse_failure(*, retailer: str) -> bool:
    return retailer.lower() in FATAL_PARSE_FAILURE_RETAILERS


def _is_cloudflare_challenge_content(
    *,
    retailer: str,
    title: str,
    html: str,
) -> bool:
    details = _known_invalid_page_details_from_content(
        retailer=retailer,
        parent_title=title,
        html=html,
    )
    return details == (403, "cloudflare_challenge")


def _wait_for_manual_intervention_clear(
    *,
    page: Page,
    retailer: str,
    url: str,
    poll_seconds: float,
    max_wait_seconds: float,
) -> bool:
    start = time.monotonic()
    next_log_at = start
    while True:
        try:
            current_title = str(page.title() or "")
        except Exception:
            current_title = ""
        try:
            current_html = str(page.content() or "")
        except Exception:
            current_html = ""

        if not _is_manual_intervention_content(
            retailer=retailer,
            title=current_title,
            html=current_html,
        ):
            LOGGER.info("Manual anti-bot block cleared for %s; resuming.", url)
            return True

        now = time.monotonic()
        if max_wait_seconds > 0 and (now - start) >= max_wait_seconds:
            LOGGER.error(
                "Manual anti-bot block still active for %s after %.1f seconds.",
                url,
                now - start,
            )
            return False

        if now >= next_log_at:
            LOGGER.warning(
                "Anti-bot block active for %s; waiting for manual intervention...",
                url,
            )
            next_log_at = now + max(30.0, poll_seconds)
        time.sleep(max(1.0, poll_seconds))


def _send_manual_intervention_alert(
    *,
    retailer: str,
    category_key: str,
    url: str,
    page_title: str,
    reason: str,
) -> None:
    subject = f"[cdp_fetch_pdp] ACTION REQUIRED anti-bot retailer={retailer}"
    body = "\n".join(
        [
            "Manual anti-bot intervention is required during PDP fetch.",
            f"Retailer: {retailer}",
            f"Category: {category_key}",
            f"URL: {url}",
            f"Reason: {reason}",
            f"Page title: {page_title}",
            "Action: clear the challenge in the attached Chrome session.",
            "Behavior: the fetcher is paused and will resume automatically after the page clears.",
        ]
    )
    _send_operator_alert(subject=subject, body=body)


def _failure_detail(url: str, *, status_code: int | None, reason: str) -> str:
    reason_text = str(reason or "").strip()
    if status_code is None:
        return f"{url} ({reason_text})" if reason_text else url
    if reason_text:
        return f"{url} (http_status={status_code}; {reason_text})"
    return f"{url} (http_status={status_code})"


def _skippable_fatal_pdp_failure_detail(
    exc: BaseException,
    *,
    retailer: str,
    fallback_url: str,
) -> str | None:
    if retailer.lower() != "chewy":
        return None
    message = str(exc or "").strip()
    match = CHEWY_FATAL_FAILURE_MESSAGE_RE.search(message)
    if not match:
        return None
    reason = str(match.group(1) or "").strip().lower()
    if reason not in CHEWY_CAPTURE_RETRY_REASONS:
        return None
    invalid_url = str(match.group(2) or "").strip() or str(fallback_url or "").strip()
    status_code_by_reason = {
        "blank_html_shell": 204,
        "kasada_challenge": 429,
    }
    return _failure_detail(
        invalid_url or fallback_url,
        status_code=status_code_by_reason.get(reason),
        reason=reason,
    )


def _has_chewy_pdp_markers(html: str) -> bool:
    lowered = str(html or "").lower()
    return any(
        marker in lowered
        for marker in (
            "productgroup",
            "__next_data__",
            "__apollo_chewy_api_state__",
            'property="og:type" content="product"',
            "application/ld+json",
        )
    )


def _is_known_invalid_existing_row(
    *,
    retailer: str,
    title_raw: object,
) -> bool:
    title_text = str(title_raw or "").strip()
    if retailer.lower() == "chewy" and not title_text:
        return True
    return _is_known_invalid_text(title_text)


def _purge_known_invalid_existing(
    tasks: Sequence[tuple[str, str | None]],
    store: PDPStore,
    *,
    retailer: str,
) -> tuple[int, list[str]]:
    urls = sorted({str(url) for _, url in tasks if str(url or "").strip()})
    if not urls:
        return 0, []

    placeholders = ",".join("?" for _ in urls)
    query = f"""
        SELECT parent_product_id, pdp_url, title_raw
        FROM parent_products
        WHERE retailer = ?
          AND pdp_url IN ({placeholders})
    """
    with connect_pdp_database(store.path) as conn:
        rows = conn.execute(query, (retailer, *urls)).fetchall()

    removed_urls: list[str] = []
    for parent_product_id, pdp_url, title_raw in rows:
        if not _is_known_invalid_existing_row(
            retailer=retailer,
            title_raw=title_raw,
        ):
            continue
        removed = store.delete_parent_with_variants(
            retailer, str(parent_product_id or "")
        )
        if removed:
            removed_urls.append(str(pdp_url or ""))
    return len(removed_urls), removed_urls


def _is_closed_target_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "target page, context or browser has been closed" in message
        or "context has been closed" in message
        or "browser has been closed" in message
    )


def _retailer_hostnames(retailer: str) -> tuple[str, ...]:
    retailer_lower = retailer.lower()
    if retailer_lower == "chewy":
        return ("www.chewy.com", "chewy.com")
    return ()


def _page_matches_retailer(page: Page, retailer: str) -> bool:
    hostnames = _retailer_hostnames(retailer)
    if not hostnames:
        return False
    try:
        current_url = str(page.url or "").strip()
    except Exception:
        return False
    parsed = urlsplit(current_url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    host = parsed.netloc.lower()
    return any(host == name or host.endswith(f".{name}") for name in hostnames)


def _find_retailer_seed_page(context: BrowserContext, retailer: str) -> Page | None:
    for candidate in reversed(context.pages):
        try:
            if candidate.is_closed():
                continue
        except Exception:
            continue
        if _page_matches_retailer(candidate, retailer):
            return candidate
    return None


def _find_retailer_seed_page_not_matching(
    context: BrowserContext,
    retailer: str,
    requested_url: str,
) -> Page | None:
    for candidate in reversed(context.pages):
        try:
            if candidate.is_closed():
                continue
        except Exception:
            continue
        if not _page_matches_retailer(candidate, retailer):
            continue
        current_url = str(candidate.url or "").strip()
        if current_url and not _manual_navigation_urls_match(
            current_url, requested_url
        ):
            return candidate
    return None


def _open_work_page(
    context: BrowserContext,
    *,
    retailer: str | None = None,
    require_seeded_retailer_page: bool = False,
) -> Page:
    if retailer:
        seeded_page = _find_retailer_seed_page(context, retailer)
        if seeded_page is not None:
            return seeded_page
        if require_seeded_retailer_page:
            raise FatalPDPFetchError(
                "No live Chewy tab found in the attached Chrome session. "
                "Open chewy.com in that same Chrome window/profile first, "
                "then rerun the fetcher."
            )
    fallback_candidates: list[Page] = []
    for candidate in context.pages:
        try:
            if candidate.is_closed():
                continue
        except Exception:
            continue
        fallback_candidates.append(candidate)
    for candidate in fallback_candidates:
        try:
            if _is_usable_fallback_page_url(str(candidate.url or "").strip()):
                return candidate
        except Exception:
            continue
    if fallback_candidates:
        return fallback_candidates[0]
    return context.new_page()


def _get_work_page_with_reconnect(
    *,
    remote_url: str,
    playwright: object | None,
    browser: Browser | None,
    context: BrowserContext | None,
    retailer: str | None = None,
    require_seeded_retailer_page: bool = False,
    reconnect_attempts: int = 2,
    connect_retry_seconds: float = 20.0,
    connect_max_attempts: int = 0,
) -> tuple[object, Browser, BrowserContext, Page]:
    current_playwright = playwright
    current_browser = browser
    current_context = context
    last_exc: Exception | None = None

    for attempt in range(reconnect_attempts + 1):
        if current_context is not None:
            try:
                page = _open_work_page(
                    current_context,
                    retailer=retailer,
                    require_seeded_retailer_page=require_seeded_retailer_page,
                )
                return current_playwright, current_browser, current_context, page
            except (
                Exception
            ) as exc:  # noqa: BLE001 - CDP context can be externally closed
                last_exc = exc
                if not _is_closed_target_error(exc):
                    raise
                LOGGER.warning(
                    "Attached Chrome context closed while opening a work tab (attempt %d/%d).",
                    attempt + 1,
                    reconnect_attempts + 1,
                )

        if attempt >= reconnect_attempts:
            break

        LOGGER.info(
            "Reconnecting to Chrome CDP endpoint %s (attempt %d/%d).",
            remote_url,
            attempt + 1,
            reconnect_attempts,
        )
        _close_browser(current_browser)
        (
            current_playwright,
            current_browser,
            current_context,
        ) = _get_context_with_retry(
            remote_url,
            retry_seconds=connect_retry_seconds,
            max_attempts=connect_max_attempts,
            playwright=current_playwright,
        )

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Unable to acquire a working page from CDP session.")


def _goto(
    page: Page,
    url: str,
    timeout_ms: int,
    *,
    retailer: str | None = None,
) -> bool:
    retailer_lower = str(retailer or "").strip().lower()
    if retailer_lower == "chewy":
        wait_until = "domcontentloaded"
        effective_timeout_ms = min(timeout_ms, CHEWY_GOTO_TIMEOUT_MS)
    else:
        wait_until = "networkidle"
        effective_timeout_ms = timeout_ms
    LOGGER.info("Navigating to %s", url)
    try:
        page.goto(url, wait_until=wait_until, timeout=effective_timeout_ms)
        LOGGER.info("Navigation OK: %s", page.url)
        return True
    except PlaywrightTimeoutError:
        current = page.url
        if current and current.split("?")[0].rstrip("/") == url.split("?")[0].rstrip(
            "/"
        ):
            LOGGER.info("Navigation timed out but page is at %s; continuing.", current)
            return True
        if retailer_lower == "chewy":
            LOGGER.info(
                "DOM-content timed out for %s after %d ms",
                url,
                effective_timeout_ms,
            )
            return False
        LOGGER.info(
            "Network-idle timed out for %s; retrying with domcontentloaded.", url
        )
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            LOGGER.info("Navigation OK after retry: %s", page.url)
            return True
        except PlaywrightTimeoutError:
            current = page.url
            if current and current.split("?")[0].rstrip("/") == url.split("?")[
                0
            ].rstrip("/"):
                LOGGER.info(
                    "DOM-content timed out but page is at %s; continuing.", current
                )
                return True
            LOGGER.info("Navigation timed out for %s", url)
            return False
    except Exception as exc:  # noqa: BLE001
        if _is_closed_target_error(exc):
            raise
        LOGGER.info("Navigation error for %s: %s", url, exc)
        return False


def _find_context_page_for_requested_url(
    context: BrowserContext,
    requested_url: str,
) -> Page | None:
    for candidate in reversed(context.pages):
        try:
            if candidate.is_closed():
                continue
            if _manual_navigation_urls_match(str(candidate.url or ""), requested_url):
                return candidate
        except Exception:
            continue
    return None


def _page_title_hint(page: Page) -> str | None:
    try:
        return str(page.title() or "").strip() or None
    except Exception:
        return None


def _read_cdp_tabs(remote_url: str) -> tuple[dict[str, str], ...]:
    endpoint = f"{str(remote_url or '').rstrip('/')}/json/list"
    try:
        with urlopen(endpoint, timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, list):
        return ()
    tabs: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        tab_id = str(item.get("id", "") or "").strip()
        if not tab_id:
            continue
        tabs.append(
            {
                "id": tab_id,
                "title": str(item.get("title", "") or "").strip(),
                "type": str(item.get("type", "") or "").strip(),
                "url": str(item.get("url", "") or "").strip(),
            }
        )
    return tuple(tabs)


def _activate_cdp_tab(tab_id: str, *, remote_url: str) -> None:
    tab_id = str(tab_id or "").strip()
    if not tab_id:
        return
    try:
        with urlopen(
            f"{str(remote_url or '').rstrip('/')}/json/activate/{tab_id}",
            timeout=2.0,
        ) as response:
            response.read()
    except (OSError, URLError, TimeoutError):
        LOGGER.debug("Could not activate CDP tab %s before auto-paste.", tab_id)


def _activate_current_cdp_tab_for_page(
    *,
    remote_url: str,
    page: Page,
) -> tuple[str | None, str | None, str | None]:
    current_url = str(page.url or "").strip() or "about:blank"
    tabs = _read_cdp_tabs(remote_url)
    if not tabs:
        return None, None, current_url
    exact_matches = [
        tab
        for tab in tabs
        if (current_url == "about:blank" and tab["url"] == "about:blank")
        or _manual_navigation_urls_match(tab["url"], current_url)
    ]
    if not exact_matches:
        return None, None, current_url
    selected = exact_matches[-1]
    _activate_cdp_tab(selected["id"], remote_url=remote_url)
    LOGGER.info("Activated current CDP tab before auto-paste: %s", selected["url"])
    title_hint = selected["title"] or _page_title_hint(page)
    return selected["id"], title_hint, selected["url"] or current_url


def _wait_for_cdp_tab_id_url(
    *,
    remote_url: str,
    tab_id: str,
    requested_url: str,
    timeout_seconds: float,
    stale_url: str | None = None,
    unchanged_timeout_seconds: float = 8.0,
) -> bool:
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    unchanged_deadline = time.monotonic() + max(0.0, float(unchanged_timeout_seconds))
    last_url = ""
    while time.monotonic() <= deadline:
        tabs = _read_cdp_tabs(remote_url)
        selected = next((tab for tab in tabs if tab["id"] == tab_id), None)
        if selected is None:
            LOGGER.warning(
                "Selected Chrome tab %s disappeared while waiting for %s.",
                tab_id,
                requested_url,
            )
            return False
        last_url = selected["url"]
        if _manual_navigation_urls_match(last_url, requested_url):
            return True
        if (
            stale_url
            and time.monotonic() >= unchanged_deadline
            and _manual_navigation_urls_match(last_url, stale_url)
        ):
            LOGGER.warning(
                "Auto-paste did not change the selected tab URL within %.1f seconds; retrying. Current selected tab URL: %s",
                unchanged_timeout_seconds,
                last_url or "(blank)",
            )
            return False
        time.sleep(0.5)
    LOGGER.warning(
        "Timed out waiting for the selected Chrome tab to load %s. Last selected tab URL: %s",
        requested_url,
        last_url or "(blank)",
    )
    return False


def _wait_for_page_url(
    page: Page,
    requested_url: str,
    *,
    timeout_ms: int,
) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_ms / 1000.0)
    last_url = str(page.url or "").strip()
    while time.monotonic() <= deadline:
        try:
            last_url = str(page.url or "").strip()
        except Exception:
            last_url = ""
        if last_url and _manual_navigation_urls_match(last_url, requested_url):
            return True
        page.wait_for_timeout(250)
    LOGGER.warning(
        "Selected Chrome tab reached %s, but the same Playwright page is still at %s.",
        requested_url,
        last_url or "(blank)",
    )
    return False


def _is_usable_fallback_page_url(url: str) -> bool:
    current_url = str(url or "").strip()
    if not current_url:
        return False
    if current_url == "about:blank":
        return True
    parsed = urlsplit(current_url)
    return parsed.scheme.lower() in {"http", "https"}


def _goto_via_auto_paste(
    page: Page,
    *,
    remote_url: str,
    url: str,
    timeout_ms: int,
    wait_seconds: float,
    attempts: int,
) -> tuple[bool, Page]:
    if sys.platform != "win32":
        raise RuntimeError(
            "Chewy address-bar navigation requires Windows Python because the "
            "auto-paste path uses UIAutomation/SendKeys against the visible Chrome window."
        )

    active_page = page
    total_attempts = max(1, int(attempts))
    for attempt in range(1, total_attempts + 1):
        try:
            active_page.bring_to_front()
        except Exception:
            LOGGER.debug("Could not bring the current CDP page to the foreground.")
        current_url = str(active_page.url or "").strip() or "about:blank"
        if _manual_navigation_urls_match(current_url, url):
            LOGGER.info(
                "Current Playwright page is already at the requested PDP: %s",
                current_url,
            )
            return True, active_page
        tab_id, title_hint, stale_url = _activate_current_cdp_tab_for_page(
            remote_url=remote_url,
            page=active_page,
        )
        if tab_id is None:
            raise FatalPDPFetchError(
                "Could not identify the current Chrome tab for the attached Playwright page. "
                "Keep one normal Chrome tab open in the attached session, then rerun the fetcher."
            )
        LOGGER.info(
            "Loading %s via Chrome address bar (attempt %d/%d).",
            url,
            attempt,
            total_attempts,
        )
        _paste_url_into_windows_chrome(url, title_hint=title_hint)
        reached_requested_url = _wait_for_cdp_tab_id_url(
            remote_url=remote_url,
            tab_id=tab_id,
            requested_url=url,
            timeout_seconds=wait_seconds,
            stale_url=stale_url,
        )
        if not reached_requested_url:
            continue
        if not _wait_for_page_url(active_page, url, timeout_ms=min(timeout_ms, 5000)):
            continue
        try:
            active_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            LOGGER.info(
                "DOM-content wait timed out after address-bar navigation to %s; continuing.",
                url,
            )
        current_url = str(active_page.url or "").strip()
        if current_url and _manual_navigation_urls_match(current_url, url):
            LOGGER.info("Address-bar navigation OK: %s", current_url)
            return True, active_page
    return False, active_page


def _navigate_to_pdp(
    page: Page,
    *,
    retailer: str,
    remote_url: str,
    url: str,
    timeout_ms: int,
    manual_navigation_auto_paste: bool,
    auto_paste_wait_seconds: float,
    auto_paste_attempts: int,
) -> tuple[bool, Page]:
    if retailer.lower() == "chewy" and manual_navigation_auto_paste:
        return _goto_via_auto_paste(
            page,
            remote_url=remote_url,
            url=url,
            timeout_ms=timeout_ms,
            wait_seconds=auto_paste_wait_seconds,
            attempts=auto_paste_attempts,
        )
    return _goto(page, url, timeout_ms, retailer=retailer), page


def _dismiss_sephora_banner(page: Page) -> None:
    """Best-effort close for the Sephora geo/overlay banner (mirrors link collector)."""
    LOGGER.info("Checking for Sephora banner to close...")
    selectors = (
        "button[aria-label='Close modal'][data-at='modal_close']",
        "button[data-at='modal_close']",
        "button[aria-label*='close' i]",
        "[data-at='closeButton']",
        "[data-comp='ModalClose'] button",
        "div[role='dialog'] button[aria-label*='close' i]",
        "div[id^='modal'][role='dialog'] button[data-at='modal_close']",
        "div[id^='modal'][role='dialog'] button[aria-label*='close' i]",
        "div[role='dialog'][aria-modal='true'] button[aria-label='Close modal']",
        "div[role='dialog'][aria-modal='true'] button.css-1kna575",
    )
    for _ in range(6):
        for selector in selectors:
            try:
                element = page.query_selector(selector)
                if element:
                    element.click(timeout=2000, force=True)
                    page.wait_for_timeout(500)
                    LOGGER.info("Closed banner via selector: %s", selector)
                    return
            except Exception:
                continue
        try:
            btn = page.query_selector("button:has-text('Continue to Sephora')")
            if btn:
                btn.click(timeout=2000, force=True)
                page.wait_for_timeout(500)
                LOGGER.info("Clicked 'Continue to Sephora' button to dismiss banner.")
                return
        except Exception:
            pass
        page.wait_for_timeout(400)
    LOGGER.info("No Sephora banner closed after retries.")


def _category_key(profile_name: str, retailer: str) -> str:
    return profile_category_key(retailer, profile_name)


def _extract_parent_id_from_url(
    pattern: re.Pattern[str] | None, url: str
) -> str | None:
    if pattern is None:
        return None
    match = pattern.search(url)
    if not match:
        return None
    if match.lastindex:
        for group_index in range(1, match.lastindex + 1):
            candidate = str(match.group(group_index) or "").strip()
            if candidate:
                return candidate
    candidate = str(match.group(0) or "").strip()
    return candidate or None


def _load_links(
    path: Path, retailer: str, categories: set[str] | None
) -> list[tuple[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Links file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Links JSON must be an object.")
    retailer_payload = payload.get(retailer, {})
    if not isinstance(retailer_payload, Mapping):
        raise ValueError(f"No entries for retailer {retailer} in {path}")
    urls: list[tuple[str, str]] = []
    for category, links in retailer_payload.items():
        canonical_category = canonical_category_key(retailer, category)
        if categories and canonical_category not in categories:
            continue
        if not isinstance(links, Iterable):
            continue
        for link in links:
            urls.append((canonical_category, str(link)))
    return urls


def _sort_mode_priority(sort_mode: str) -> tuple[int, str]:
    preferred = {
        "best_selling": 0,
        "newest": 1,
    }
    normalized = sort_mode.lower()
    return (preferred.get(normalized, len(preferred)), normalized)


def _load_latest_listing_links(
    pdp_store_path: Path,
    retailer: str,
    categories: set[str] | None,
    sort_modes: Sequence[str] | None,
) -> list[tuple[str, str]]:
    """Load PDP tasks from the latest listing crawl instead of links.json."""

    requested_sorts = {sort.lower() for sort in (sort_modes or []) if sort}
    tasks: list[tuple[str, str]] = []
    seen: set[str] = set()

    with connect_pdp_database(pdp_store_path) as conn:
        rows = conn.execute(
            """
            SELECT category_key, MAX(crawl_ts) AS crawl_ts
            FROM retailer_listing_observations
            WHERE retailer = ?
            GROUP BY category_key
            """,
            (retailer,),
        ).fetchall()

        latest_by_category = {
            str(category_key).lower(): (
                canonical_category_key(retailer, category_key),
                str(crawl_ts),
            )
            for category_key, crawl_ts in rows
            if category_key and crawl_ts
        }
        if categories is not None:
            latest_by_category = {
                category: value
                for category, value in latest_by_category.items()
                if value[0] in categories
            }

        for category in sorted(latest_by_category):
            canonical_category, crawl_ts = latest_by_category[category]
            available_sort_rows = conn.execute(
                """
                SELECT DISTINCT sort_mode
                FROM retailer_listing_observations
                WHERE retailer = ?
                  AND category_key = ?
                  AND crawl_ts = ?
                  AND pdp_url IS NOT NULL
                  AND pdp_url != ''
                """,
                (retailer, category, crawl_ts),
            ).fetchall()
            available_sorts = sorted(
                {str(row[0]).lower() for row in available_sort_rows},
                key=_sort_mode_priority,
            )
            selected_sorts = [
                sort
                for sort in available_sorts
                if not requested_sorts or sort in requested_sorts
            ]
            for sort_mode in selected_sorts:
                listing_rows = conn.execute(
                    """
                    SELECT parent_product_id, pdp_url
                    FROM retailer_listing_observations
                    WHERE retailer = ?
                      AND category_key = ?
                      AND crawl_ts = ?
                      AND LOWER(sort_mode) = ?
                      AND pdp_url IS NOT NULL
                      AND pdp_url != ''
                    ORDER BY page, position, pdp_url
                    """,
                    (retailer, category, crawl_ts, sort_mode),
                ).fetchall()
                for parent_product_id, pdp_url in listing_rows:
                    url = str(pdp_url)
                    key = str(parent_product_id or url)
                    if key in seen:
                        continue
                    seen.add(key)
                    tasks.append((canonical_category, url))

    if requested_sorts and not tasks:
        requested = ", ".join(sorted(requested_sorts))
        raise ValueError(
            "No latest listing PDP URLs found for "
            f"retailer={retailer}, categories={sorted(categories or [])}, "
            f"sort_modes={requested}."
        )
    return tasks


def _filter_tasks_against_existing(
    tasks: Sequence[tuple[str, str | None]],
    store: PDPStore,
    *,
    retailer: str,
) -> tuple[list[tuple[str, str]], int, int]:
    """Drop tasks already present in the PDP store and dedupe repeated parent ids."""

    normalized = [(category, str(url)) for category, url in tasks if url]
    if retailer != "amazon":
        existing_parent_ids = store.existing_parent_ids(retailer)
        if not existing_parent_ids:
            return normalized, 0, 0

        profile_regex_cache: dict[str, re.Pattern[str] | None] = {}
        filtered: list[tuple[str, str]] = []
        skipped_existing = 0
        skipped_duplicate = 0
        queued_parent_ids: set[str] = set()
        for category, url in normalized:
            parent_id = None
            profile_name = _profile_for_category(retailer, category or "")
            if profile_name is not None:
                if profile_name not in profile_regex_cache:
                    profile_regex_cache[profile_name] = load_profile(
                        profile_name
                    ).id_extractors.parent_from_url_regex
                pattern = profile_regex_cache[profile_name]
                parent_id = _extract_parent_id_from_url(pattern, url)
            if parent_id:
                if parent_id in existing_parent_ids:
                    skipped_existing += 1
                    continue
                if parent_id in queued_parent_ids:
                    skipped_duplicate += 1
                    continue
                queued_parent_ids.add(parent_id)
            filtered.append((category, str(url)))
        return filtered, skipped_existing, skipped_duplicate

    asins = [
        asin for _, url in tasks if url for asin in [_amazon_asin_from_url(url)] if asin
    ]
    if not asins:
        normalized = [(category, str(url)) for category, url in tasks if url]
        return normalized, 0, 0

    existing_parent_ids = store.existing_parent_ids(retailer)
    existing_variant_map = store.parent_ids_for_variant_ids(retailer, asins)
    existing_asins = set(existing_variant_map).union(existing_parent_ids)

    filtered: list[tuple[str, str]] = []
    skipped_existing = 0
    skipped_duplicate = 0
    queued_asins: set[str] = set()
    for category, url in tasks:
        if not url:
            continue
        asin = _amazon_asin_from_url(url)
        if asin:
            if asin in existing_asins:
                skipped_existing += 1
                continue
            if asin in queued_asins:
                skipped_duplicate += 1
                continue
            queued_asins.add(asin)
        filtered.append((category, str(url)))
    return filtered, skipped_existing, skipped_duplicate


def _adapter_for_retailer(retailer: str):
    r = retailer.lower()
    if r == "sephora":
        return SephoraAdapter()
    if r == "ulta":
        return UltaAdapter()
    if r == "amazon":
        return AmazonAdapter()
    if r == "chewy":
        return ChewyAdapter()
    if r == "saloncentric":
        return SaloncentricAdapter()
    if r == "cosmoprofbeauty":
        return CosmoprofbeautyAdapter()
    if r == "saksfifthavenue":
        return SaksfifthavenueAdapter()
    if r == "kiko":
        return KikoAdapter()
    if r == "lorealparis":
        return LorealParisAdapter()
    if r == "guestinresidence":
        return GuestInResidenceAdapter()
    if r == "vince":
        return VinceAdapter()
    if r == "tikicat":
        return TikiCatAdapter()
    if r == "purina":
        return PurinaAdapter()
    return NullAdapter()


def _should_overwrite_existing_rows(*, rescrape_existing: bool) -> bool:
    """Return whether parsed PDP rows should replace existing PDP store rows."""

    return bool(rescrape_existing)


def _profile_for_category(retailer: str, category: str) -> str | None:
    retailer_lower = retailer.lower()
    canonical_category = canonical_category_key(retailer_lower, category)
    for summary in iter_profile_summaries():
        if summary.retailer.lower() != retailer_lower:
            continue
        if _category_key(summary.profile_name, retailer_lower) == canonical_category:
            return summary.profile_name
    return None


def _normalize_url_for_retailer(url: str, retailer: str) -> str:
    """Patch common Sephora URL issues (missing ? before skuId)."""
    r = retailer.lower()
    original = url
    if r == "sephora" and "skuId=" in url and "?skuId=" not in url:
        if "?" not in url:
            url = url.replace("skuId=", "?skuId=", 1)
        else:
            url = url.replace("&skuId=", "?skuId=", 1)
        url = re.sub(r"(P[0-9]+)\?skuId=", r"\1?skuId=", url, count=1)
    if url != original:
        LOGGER.info("Normalized URL for %s: %s -> %s", retailer, original, url)
    return url


def _amazon_asin_from_url(url: str) -> str | None:
    match = AMAZON_ASIN_IN_PATH.search(url)
    if not match:
        return None
    return match.group(1).upper()


def _canonicalize_amazon_parent_from_existing_variants(
    store: PDPStore,
    result: ParseResult,
) -> str | None:
    _ = store
    if result.parent is None:
        return None
    # Amazon twister metadata can include broad ASIN sets that cross product
    # families, so only trust the adapter-parsed parent ASIN for this retailer.
    return str(result.parent.parent_product_id or "").strip() or None


def _canonicalize_parent_from_existing_variants(
    store: PDPStore,
    result: ParseResult,
    *,
    retailer: str,
) -> str | None:
    if result.parent is None or not result.variants:
        return None
    current_parent_id = str(result.parent.parent_product_id or "").strip()
    if not current_parent_id:
        return None

    variant_ids = [
        str(getattr(variant, "variant_id", "")).strip()
        for variant in result.variants
        if str(getattr(variant, "variant_id", "")).strip()
    ]
    if not variant_ids:
        return current_parent_id

    existing_variant_parent_map = store.parent_ids_for_variant_ids(
        retailer, variant_ids
    )
    if not existing_variant_parent_map:
        return current_parent_id

    parent_counts = Counter(
        parent_id
        for parent_id in existing_variant_parent_map.values()
        if str(parent_id).strip()
    )
    if not parent_counts:
        return current_parent_id

    canonical_parent_id = sorted(
        parent_counts.items(), key=lambda item: (-item[1], item[0])
    )[0][0]
    if canonical_parent_id == current_parent_id:
        return canonical_parent_id

    result.parent.extras = dict(getattr(result.parent, "extras", {}) or {})
    result.parent.extras["source_parent_id_inferred"] = current_parent_id
    result.parent.parent_product_id = canonical_parent_id
    for variant in result.variants:
        variant.parent_product_id = canonical_parent_id
    return canonical_parent_id


def _parse_single(
    parser: PDPParser,
    page: Page,
    url: str,
    timeout_ms: int,
    wait_ms: int,
    retailer: str,
    category_key: str | None,
    remote_url: str,
    manual_navigation_auto_paste: bool,
    auto_paste_wait_seconds: float,
    auto_paste_attempts: int,
) -> tuple[ParseResult | None, Page]:
    normalized_url = _normalize_url_for_retailer(url, retailer)
    navigated, page = _navigate_to_pdp(
        page,
        retailer=retailer,
        remote_url=remote_url,
        url=normalized_url,
        timeout_ms=timeout_ms,
        manual_navigation_auto_paste=manual_navigation_auto_paste,
        auto_paste_wait_seconds=auto_paste_wait_seconds,
        auto_paste_attempts=auto_paste_attempts,
    )
    if not navigated:
        LOGGER.info("Skip %s due to navigation failure", url)
        return None, page
    if retailer.lower() == "sephora":
        _dismiss_sephora_banner(page)
    # Short initial settle to allow DOM to stabilize before long wait.
    short_wait = max(500, wait_ms // 2)
    LOGGER.info("Waiting %d ms (short settle) before final wait...", short_wait)
    page.wait_for_timeout(short_wait)
    if retailer.lower() == "sephora":
        _dismiss_sephora_banner(page)
    remaining_wait = max(0, wait_ms - short_wait)
    if remaining_wait:
        LOGGER.info("Waiting %d ms for page to settle...", remaining_wait)
        page.wait_for_timeout(remaining_wait)
    html = ""
    page_title = ""
    invalid_capture: tuple[int | None, str] | None = None
    capture_attempts = CHEWY_CAPTURE_MAX_ATTEMPTS if retailer.lower() == "chewy" else 1
    for capture_attempt in range(1, capture_attempts + 1):
        html = page.content()
        page_title = page.title()
        invalid_capture = _known_invalid_page_details_from_content(
            retailer=retailer,
            parent_title="",
            page_title=page_title,
            html=html,
        )
        if (
            retailer.lower() == "chewy"
            and invalid_capture is not None
            and invalid_capture[1] in CHEWY_CAPTURE_RETRY_REASONS
            and capture_attempt < capture_attempts
        ):
            _status_code, reason = invalid_capture
            LOGGER.warning(
                "Chewy captured invalid PDP shell for %s (%s, %d chars); retrying %d/%d.",
                normalized_url,
                reason,
                len(html or ""),
                capture_attempt + 1,
                capture_attempts,
            )
            page.wait_for_timeout(CHEWY_CAPTURE_RETRY_WAIT_MS)
            navigated, page = _navigate_to_pdp(
                page,
                retailer=retailer,
                remote_url=remote_url,
                url=normalized_url,
                timeout_ms=timeout_ms,
                manual_navigation_auto_paste=manual_navigation_auto_paste,
                auto_paste_wait_seconds=auto_paste_wait_seconds,
                auto_paste_attempts=auto_paste_attempts,
            )
            if not navigated:
                LOGGER.info("Retry navigation failed for %s", normalized_url)
                return None, page
            page.wait_for_timeout(max(1000, min(wait_ms, CHEWY_CAPTURE_RETRY_WAIT_MS)))
            continue
        break

    if invalid_capture is not None and _should_abort_after_invalid_page(
        retailer=retailer,
        reason=invalid_capture[1],
    ):
        raise FatalPDPFetchError(
            "Aborting fetch run after unusable Chewy page "
            f"({invalid_capture[1]}) at {normalized_url}"
        )

    LOGGER.info("Page title: %s", page_title)
    try:
        first_h1 = page.query_selector("h1")
        if first_h1:
            LOGGER.info("First H1 text: %s", first_h1.inner_text().strip()[:200])
    except Exception:
        pass
    captured_url = str(getattr(page, "url", "") or "").strip() or normalized_url
    LOGGER.info("Captured HTML (%d chars) for %s", len(html or ""), captured_url)
    result = parser.parse_url(captured_url, html=html, timeout=timeout_ms / 1000.0)
    return _apply_category_context(result, category_key), page


def main(argv: Sequence[str] | None = None) -> int:
    arg_list = list(argv or sys.argv[1:])
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    respawn_code = _maybe_respawn_outside_asyncio_loop(arg_list)
    if respawn_code is not None:
        return respawn_code
    args = _apply_retailer_defaults(_parse_args(arg_list))
    load_env_from_secrets_file()

    retailer = args.retailer.lower()
    category_filter = canonical_category_keys(retailer, args.categories)
    max_per_run = (
        args.max_per_run if args.max_per_run and args.max_per_run > 0 else None
    )

    pdp_store_path = enforce_default_pdp_store_path()

    tasks: list[tuple[str, str | None]] = []
    if args.url:
        category_guess = None
        if category_filter:
            category_guess = next(iter(category_filter))
        tasks.append((category_guess, args.url))
    else:
        if args.task_source == "latest-listing":
            tasks.extend(
                _load_latest_listing_links(
                    pdp_store_path,
                    retailer,
                    category_filter,
                    args.listing_sort_modes,
                )
            )
            LOGGER.info(
                "Loaded %d PDP URL(s) from latest listing observations.",
                len(tasks),
            )
        else:
            links = _load_links(args.links_path, retailer, category_filter)
            tasks.extend(links)
            LOGGER.info("Loaded %d PDP URL(s) from %s.", len(tasks), args.links_path)

    if not tasks:
        LOGGER.error("No PDP URLs to process.")
        return 1

    profile_cache: dict[str, PDPParser] = {}
    adapter_cache: dict[str, object] = {}

    processed = 0
    downloaded_images = 0
    playwright = browser = context = None
    require_seeded_chewy_tab = False

    try:
        (
            playwright,
            browser,
            context,
        ) = _get_context_with_retry(
            args.remote_url,
            retry_seconds=args.cdp_connect_retry_seconds,
            max_attempts=args.cdp_connect_max_attempts,
        )
        (
            playwright,
            browser,
            context,
            page,
        ) = _get_work_page_with_reconnect(
            remote_url=args.remote_url,
            playwright=playwright,
            browser=browser,
            context=context,
            retailer=retailer,
            require_seeded_retailer_page=require_seeded_chewy_tab,
            connect_retry_seconds=args.cdp_connect_retry_seconds,
            connect_max_attempts=args.cdp_connect_max_attempts,
        )
        storage = EvidenceStorage()
        store = PDPStore(pdp_store_path)
        if args.purge_invalid_existing:
            purged_count, purged_urls = _purge_known_invalid_existing(
                tasks,
                store,
                retailer=retailer,
            )
            if purged_count:
                sample = ", ".join(purged_urls[:3])
                LOGGER.info(
                    "Purged %d known invalid existing %s PDP row(s) before retrying. Sample: %s",
                    purged_count,
                    retailer,
                    sample,
                )
            else:
                LOGGER.info(
                    "No known invalid existing %s PDP rows matched the requested URLs.",
                    retailer,
                )
        if not args.rescrape_existing:
            tasks, skipped_existing, skipped_duplicate = _filter_tasks_against_existing(
                tasks,
                store,
                retailer=retailer,
            )
            if skipped_existing:
                LOGGER.info(
                    "Skipping %d %s URL(s) already present in the PDP store. "
                    "Use --rescrape-existing to force re-scrape.",
                    skipped_existing,
                    retailer,
                )
            if skipped_duplicate:
                LOGGER.info(
                    "Skipping %d duplicate %s URL(s) by repeated parent id in input.",
                    skipped_duplicate,
                    retailer,
                )
        if not tasks:
            LOGGER.info("No PDP URLs left to process after existing-record filtering.")
            return 0

        previous_category: str | None = None
        task_total = len(tasks)
        alerted_challenge_urls: set[str] = set()
        for task_index, (category, url) in enumerate(tasks, start=1):
            if max_per_run is not None and processed >= max_per_run:
                LOGGER.info("Reached max-per-run (%d); stopping.", max_per_run)
                break

            category_key = category or "uncategorized"
            if previous_category is not None and category_key != previous_category:
                _sleep_with_log(
                    args.category_pause_seconds,
                    reason=f"between categories {previous_category} -> {category_key}",
                )
            previous_category = category_key

            task_restart_attempts = 0
            while True:
                try:
                    profile_name = _profile_for_category(retailer, category_key)
                    if profile_name is None:
                        LOGGER.error(
                            "No profile found for retailer=%s category=%s; skipping %s",
                            retailer,
                            category_key,
                            url,
                        )
                        break

                    parser = profile_cache.get(profile_name)
                    if parser is None:
                        profile = load_profile(profile_name)
                        adapter = adapter_cache.get(profile.retailer)
                        if adapter is None:
                            adapter = _adapter_for_retailer(profile.retailer)
                            adapter_cache[profile.retailer] = adapter
                        parser = PDPParser(
                            profile=profile,
                            adapter=adapter,
                            fetcher=None,
                            storage=storage,
                        )
                        profile_cache[profile_name] = parser

                    try:
                        page_closed = page.is_closed()
                    except Exception:
                        page_closed = True
                    if page_closed:
                        LOGGER.warning(
                            "Active CDP tab is closed before processing %s; reconnecting.",
                            url,
                        )
                        (
                            playwright,
                            browser,
                            context,
                            page,
                        ) = _get_work_page_with_reconnect(
                            remote_url=args.remote_url,
                            playwright=playwright,
                            browser=browser,
                            context=context,
                            retailer=retailer,
                            require_seeded_retailer_page=require_seeded_chewy_tab,
                            connect_retry_seconds=args.cdp_connect_retry_seconds,
                            connect_max_attempts=args.cdp_connect_max_attempts,
                        )

                    task_parent_id = str(
                        _extract_parent_id_from_url(
                            parser.profile.id_extractors.parent_from_url_regex,
                            url,
                        )
                        or ""
                    ).strip()
                    LOGGER.info(
                        "Fetching PDP %d/%d [%s] %s",
                        task_index,
                        task_total,
                        category_key,
                        url,
                    )
                    result: ParseResult | None = None
                    parse_failed = False
                    skip_current_task = False
                    for attempt in range(2):
                        try:
                            result, page = _parse_single(
                                parser,
                                page,
                                url,
                                args.timeout_ms,
                                args.wait_ms,
                                retailer,
                                category_key,
                                str(args.remote_url),
                                bool(args.manual_navigation_auto_paste),
                                float(args.manual_navigation_auto_paste_wait_seconds),
                                int(args.manual_navigation_auto_paste_attempts),
                            )
                            break
                        except FatalPDPFetchError as exc:
                            failure_detail = _skippable_fatal_pdp_failure_detail(
                                exc,
                                retailer=retailer,
                                fallback_url=url,
                            )
                            if failure_detail is not None:
                                LOGGER.warning(
                                    "Skipping unusable %s PDP after retries: %s",
                                    retailer,
                                    failure_detail,
                                )
                                failure_batch = BatchParseResult(
                                    retailer=parser.profile.retailer,
                                    profile_name=parser.profile.profile_name,
                                    parsed=tuple(),
                                    failures=(failure_detail,),
                                    generated_at=dt.datetime.now(dt.timezone.utc),
                                )
                                store.write_batch(failure_batch, overwrite=False)
                                _close_browser(browser)
                                (
                                    playwright,
                                    browser,
                                    context,
                                ) = _get_context_with_retry(
                                    args.remote_url,
                                    retry_seconds=args.cdp_connect_retry_seconds,
                                    max_attempts=args.cdp_connect_max_attempts,
                                    playwright=playwright,
                                )
                                (
                                    playwright,
                                    browser,
                                    context,
                                    page,
                                ) = _get_work_page_with_reconnect(
                                    remote_url=args.remote_url,
                                    playwright=playwright,
                                    browser=browser,
                                    context=context,
                                    retailer=retailer,
                                    require_seeded_retailer_page=require_seeded_chewy_tab,
                                    connect_retry_seconds=args.cdp_connect_retry_seconds,
                                    connect_max_attempts=args.cdp_connect_max_attempts,
                                )
                                skip_current_task = True
                                break
                            raise
                        except (
                            Exception
                        ) as exc:  # noqa: BLE001 - recover from closed CDP contexts
                            if attempt == 0 and _is_closed_target_error(exc):
                                LOGGER.warning(
                                    "CDP context closed while processing %s; reconnecting and retrying once.",
                                    url,
                                )
                                (
                                    playwright,
                                    browser,
                                    context,
                                    page,
                                ) = _get_work_page_with_reconnect(
                                    remote_url=args.remote_url,
                                    playwright=playwright,
                                    browser=browser,
                                    context=context,
                                    retailer=retailer,
                                    require_seeded_retailer_page=require_seeded_chewy_tab,
                                    connect_retry_seconds=args.cdp_connect_retry_seconds,
                                    connect_max_attempts=args.cdp_connect_max_attempts,
                                )
                                continue
                            LOGGER.warning("Failed to parse %s: %s", url, exc)
                            parse_failed = True
                            break
                    if skip_current_task:
                        break
                    if parse_failed or result is None:
                        if _should_abort_after_parse_failure(retailer=retailer):
                            raise FatalPDPFetchError(
                                "Aborting fetch run after Chewy PDP capture failed "
                                f"for {url}"
                            )
                        break

                    current_page_title = ""
                    try:
                        current_page_title = str(page.title() or "")
                    except Exception:
                        current_page_title = ""
                    invalid_page = _known_invalid_page_details(
                        result,
                        retailer=retailer,
                        page_title=current_page_title,
                    )
                    if invalid_page is not None:
                        status_code, reason = invalid_page
                        invalid_url = str(
                            getattr(result.fetch_result, "url", "") or url
                        )
                        if reason in MANUAL_INTERVENTION_REASONS:
                            page_title = str(
                                getattr(result.parent, "title_raw", "") or ""
                            )
                            if not page_title:
                                page_title = current_page_title
                            alert_key = f"{reason}:{invalid_url}"
                            if alert_key not in alerted_challenge_urls:
                                _send_manual_intervention_alert(
                                    retailer=retailer,
                                    category_key=category_key,
                                    url=invalid_url,
                                    page_title=page_title,
                                    reason=reason,
                                )
                                alerted_challenge_urls.add(alert_key)
                            cleared = _wait_for_manual_intervention_clear(
                                page=page,
                                retailer=retailer,
                                url=invalid_url,
                                poll_seconds=args.challenge_poll_seconds,
                                max_wait_seconds=args.challenge_max_wait_seconds,
                            )
                            if cleared:
                                LOGGER.info(
                                    "Retrying %s after manual anti-bot clearance.",
                                    invalid_url,
                                )
                                continue
                        LOGGER.warning(
                            "Rejecting invalid PDP page for [%s] %s: %s",
                            category_key,
                            invalid_url,
                            reason,
                        )
                        failure_batch = BatchParseResult(
                            retailer=parser.profile.retailer,
                            profile_name=parser.profile.profile_name,
                            parsed=tuple(),
                            failures=(
                                _failure_detail(
                                    invalid_url,
                                    status_code=status_code,
                                    reason=reason,
                                ),
                            ),
                            generated_at=dt.datetime.now(dt.timezone.utc),
                        )
                        store.write_batch(failure_batch, overwrite=False)
                        if _should_abort_after_invalid_page(
                            retailer=retailer,
                            reason=reason,
                        ):
                            raise FatalPDPFetchError(
                                "Aborting fetch run after unusable Chewy page "
                                f"({reason}) at {invalid_url}"
                            )
                        break

                    if retailer == "amazon" and result.parent is not None:
                        original_parent_id = str(
                            result.parent.parent_product_id or ""
                        ).strip()
                        canonical_parent_id = (
                            _canonicalize_amazon_parent_from_existing_variants(
                                store, result
                            )
                        )
                        canonical_parent_id = str(canonical_parent_id or "").strip()
                        if (
                            canonical_parent_id
                            and original_parent_id
                            and canonical_parent_id != original_parent_id
                        ):
                            LOGGER.info(
                                "Amazon variants matched existing family; canonical parent %s (was %s).",
                                canonical_parent_id,
                                original_parent_id,
                            )

                        url_asin = _amazon_asin_from_url(url)
                        if (
                            url_asin
                            and canonical_parent_id
                            and url_asin != canonical_parent_id
                        ):
                            removed = store.delete_parent_with_variants(
                                retailer, url_asin
                            )
                            LOGGER.info(
                                "Amazon canonical parent ASIN %s differs from URL ASIN %s; "
                                "removed stale parent row(s): %d",
                                canonical_parent_id,
                                url_asin,
                                removed,
                            )
                    # Sephora image fallback: if variants lack image URLs, try to grab one from the DOM.
                    fallback_src = None
                    if retailer == "sephora":
                        try:
                            for selector in SEPHORA_IMG_SELECTORS:
                                img = page.query_selector(selector)
                                if img:
                                    src = img.get_attribute("src")
                                    if src and "data:image" not in src:
                                        fallback_src = src
                                        LOGGER.info(
                                            "Using fallback image from selector %s: %s",
                                            selector,
                                            src,
                                        )
                                        break
                        except Exception:
                            pass
                        if fallback_src and result.variants:
                            for variant in result.variants:
                                if not getattr(variant, "hero_image_url", None):
                                    variant.hero_image_url = fallback_src
                        if fallback_src and not result.variants and result.parent:
                            # Synthesize a variant for image download/storage.
                            parent_id = (
                                getattr(result.parent, "parent_product_id", None) or ""
                            )
                            result.variants = (
                                Variant(
                                    retailer=retailer,
                                    parent_product_id=parent_id,
                                    variant_id=parent_id or "variant",
                                    shade_name_raw=None,
                                    shade_name_normalized=None,
                                    size_text_raw=None,
                                    price_raw=None,
                                    price=None,
                                    currency=None,
                                    barcode=None,
                                    swatch_image_url=None,
                                    hero_image_url=fallback_src,
                                    availability=None,
                                    source_index=None,
                                    qa_flags=(),
                                    extras={},
                                ),
                            )

                    batch = BatchParseResult(
                        retailer=parser.profile.retailer,
                        profile_name=parser.profile.profile_name,
                        parsed=(result,),
                        failures=(),
                        generated_at=dt.datetime.now(dt.timezone.utc),
                    )
                    store.write_batch(
                        batch,
                        overwrite=_should_overwrite_existing_rows(
                            rescrape_existing=args.rescrape_existing
                        ),
                    )
                    # Download images for this single result.
                    image_records = _image_records_for_result(result)
                    if image_records:
                        with_urls = sum(
                            1
                            for rec in image_records
                            if rec.get("hero_image_url") or rec.get("swatch_image_url")
                        )
                        LOGGER.info(
                            "Image records with URLs: %d / %d",
                            with_urls,
                            len(image_records),
                        )
                        image_dir = (
                            Path("data/pdp/cli")
                            / parser.profile.profile_name
                            / "images"
                        )
                        image_dir.mkdir(parents=True, exist_ok=True)
                        dl, errs = download_variant_images(
                            image_records, image_dir, skip_existing=True
                        )
                        downloaded_images += len(dl)
                        if errs:
                            for err in errs[:3]:
                                attempted = (
                                    ", ".join(err.attempted_urls)
                                    if err.attempted_urls
                                    else "no URLs"
                                )
                                LOGGER.info(
                                    "Image download error p=%s v=%s: %s (attempted: %s)",
                                    err.parent_product_id,
                                    err.variant_id,
                                    err.reason,
                                    attempted,
                                )
                    processed += 1
                    LOGGER.info("Saved PDP (%d total this run): %s", processed, url)
                    if _should_take_batch_pause(
                        processed=processed,
                        batch_pause_every=int(args.batch_pause_every),
                        task_index=task_index,
                        task_total=task_total,
                        max_per_run=max_per_run,
                    ):
                        _sleep_with_log(
                            float(args.batch_pause_seconds),
                            reason=("Chewy batch cooldown after " f"{processed} PDPs"),
                        )
                    break
                except FatalPDPFetchError:
                    raise
                except (
                    Exception
                ) as exc:  # noqa: BLE001 - keep runner alive on task crashes
                    task_restart_attempts += 1
                    if _is_closed_target_error(exc):
                        LOGGER.warning(
                            "CDP target closed while processing %s (restart %d).",
                            url,
                            task_restart_attempts,
                        )
                    else:
                        LOGGER.exception(
                            "Unexpected task crash for [%s] %s (restart %d).",
                            category_key,
                            url,
                            task_restart_attempts,
                        )

                    if (
                        args.max_task_restarts > 0
                        and task_restart_attempts > args.max_task_restarts
                    ):
                        LOGGER.error(
                            "Giving up on %s after %d restart attempts.",
                            url,
                            task_restart_attempts - 1,
                        )
                        break

                    _sleep_with_log(
                        args.restart_delay_seconds,
                        reason=f"before restarting task {task_restart_attempts}",
                    )
                    _close_browser(browser)
                    (
                        playwright,
                        browser,
                        context,
                    ) = _get_context_with_retry(
                        args.remote_url,
                        retry_seconds=args.cdp_connect_retry_seconds,
                        max_attempts=args.cdp_connect_max_attempts,
                        playwright=playwright,
                    )
                    (
                        playwright,
                        browser,
                        context,
                        page,
                    ) = _get_work_page_with_reconnect(
                        remote_url=args.remote_url,
                        playwright=playwright,
                        browser=browser,
                        context=context,
                        retailer=retailer,
                        require_seeded_retailer_page=require_seeded_chewy_tab,
                        connect_retry_seconds=args.cdp_connect_retry_seconds,
                        connect_max_attempts=args.cdp_connect_max_attempts,
                    )

            if task_index < task_total and (
                max_per_run is None or processed < max_per_run
            ):
                _sleep_with_log(
                    args.request_pause_seconds,
                    reason=f"before next PDP ({task_index + 1}/{task_total})",
                )

        LOGGER.info(
            "Done. Processed %d PDP(s). Downloaded images: %d",
            processed,
            downloaded_images,
        )
        _send_run_notification(
            success=True,
            retailer=retailer,
            processed=processed,
            downloaded_images=downloaded_images,
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - top-level guard for CLI reliability
        LOGGER.exception("Fatal error while running PDP fetch.")
        detail = str(exc)
        _send_run_notification(
            success=False,
            retailer=retailer,
            processed=processed,
            downloaded_images=downloaded_images,
            detail=detail,
        )
        return 1
    finally:
        _close_cdp_session(playwright, browser)


if __name__ == "__main__":
    sys.exit(main())
