from __future__ import annotations

import argparse
import difflib
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.sync_api import sync_playwright

from modules.pdp.discovery import discover_pdp_urls
from modules.pdp.profile_loader import iter_profile_summaries, load_profile

LOGGER = logging.getLogger(__name__)
AMAZON_ASIN_IN_PATH = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})", re.IGNORECASE)
AMAZON_RESULT_CARD_SELECTOR = (
    "div.s-main-slot div[data-component-type='s-search-result'][data-asin]"
)
AMAZON_GLOBAL_TITLE_EXCLUDES: tuple[str, ...] = (
    "audio cd",
    "album",
    "single",
    "vinyl",
    "blu-ray",
    "dvd",
    "paperback",
    "hardcover",
    "kindle edition",
    "sheet music",
    "soundtrack",
    "format:",
)
AMAZON_MEDIA_TERMS: tuple[str, ...] = (
    "music",
    "album",
    "soundtrack",
    "single",
    "audio cd",
    "vinyl",
    "blu-ray",
    "dvd",
    "kindle edition",
    "paperback",
    "hardcover",
    "format:",
)
AMAZON_STRONG_COSMETIC_CONTEXT_TERMS: tuple[str, ...] = (
    "makeup",
    "cosmetic",
    "beauty",
    "face",
    "cheek",
    "lip",
    "eye",
    "powder",
    "cream",
    "liquid",
    "palette",
    "primer",
    "foundation",
    "concealer",
    "contour",
    "highlighter",
    "bronzer",
    "lipstick",
    "gloss",
    "mascara",
    "eyeliner",
    "eyeshadow",
    "brow",
    "setting spray",
    "setting powder",
    "rouge",
)
AMAZON_CATEGORY_TITLE_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "blush": {
        "include": ("blush", "cheek color", "cheek tint", "cheek stain", "rouge"),
        "exclude": (),
    },
    "bronzer": {
        "include": ("bronzer", "bronzing"),
        "exclude": (),
    },
    "color_corrector": {
        "include": (
            "color corrector",
            "color correcting",
            "corrector",
            "correcting palette",
        ),
        "exclude": ("hair color",),
    },
    "concealer": {
        "include": ("concealer",),
        "exclude": (),
    },
    "contour": {
        "include": ("contour", "contouring"),
        "exclude": (),
    },
    "eyebrow": {
        "include": ("eyebrow", "brow", "brow pomade", "brow pencil", "brow gel"),
        "exclude": (),
    },
    "eyeliner": {
        "include": ("eyeliner", "eye liner", "kajal", "kohl liner"),
        "exclude": (),
    },
    "eyeshadow": {
        "include": ("eyeshadow", "eye shadow", "shadow palette", "eye palette"),
        "exclude": (),
    },
    "face_primer": {
        "include": ("primer", "face primer", "makeup primer", "pore primer"),
        "exclude": ("eyelash primer", "lash primer", "mascara primer", "eye primer"),
    },
    "foundation": {
        "include": ("foundation", "skin tint", "bb cream", "cc cream"),
        "exclude": (),
    },
    "highlighter": {
        "include": ("highlighter", "illuminator", "luminizer", "strobe"),
        "exclude": (),
    },
    "lip_gloss": {
        "include": ("lip gloss", "gloss"),
        "exclude": (),
    },
    "lip_oil": {
        "include": ("lip oil",),
        "exclude": (),
    },
    "lipstick": {
        "include": ("lipstick", "lip stick", "lip color"),
        "exclude": (),
    },
    "mascara": {
        "include": ("mascara",),
        "exclude": (),
    },
    "setting_spray_powder": {
        "include": (
            "setting spray",
            "setting powder",
            "finishing powder",
            "fixing spray",
            "makeup setting",
        ),
        "exclude": (),
    },
}


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect PDP links from a category page via an attached Chrome (CDP).",
    )
    parser.add_argument(
        "--remote-url",
        default="http://localhost:9222",
        help="Chrome DevTools endpoint (start Chrome with --remote-debugging-port).",
    )
    parser.add_argument(
        "--retailer",
        help="Retailer name (e.g., ulta). When set, category URLs are read from profiles unless --category-url is provided.",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        help="Optional category keys (derived from profile names) to include when --retailer is set.",
    )
    parser.add_argument(
        "--category-url",
        help="Category/PLP URL to open. Required unless using --reuse-open-tab with --no-navigation.",
    )
    parser.add_argument(
        "--page-start",
        type=int,
        default=1,
        help="First page number to fetch (default: 1).",
    )
    parser.add_argument(
        "--page-end",
        type=int,
        default=1,
        help="Last page number to fetch (inclusive). If greater than start, iterates pages.",
    )
    parser.add_argument(
        "--auto-paginate",
        action="store_true",
        help="Automatically increment retailer-specific page query param until navigation fails or no links found.",
    )
    parser.add_argument(
        "--scroll-steps",
        type=int,
        default=150,
        help="How many scroll passes to run before stopping (default: 150).",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=10000,
        help="Wait after each scroll in milliseconds (default: 10000).",
    )
    parser.add_argument(
        "--max-idle-scrolls",
        type=int,
        default=10,
        help="Stop scrolling after this many consecutive scrolls with no new links (default: 10).",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Navigation timeout for Playwright operations (milliseconds).",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=0,
        help="Stop after collecting this many links (0 means no cap).",
    )
    parser.add_argument(
        "--min-new-per-page",
        type=int,
        default=3,
        help="Auto-paginate stops if fewer than this many canonical PDP links are detected on a page (default: 3).",
    )
    parser.add_argument(
        "--amazon-min-first-page-links",
        type=int,
        default=8,
        help=(
            "For Amazon, require at least this many canonical links on page 1 before accepting "
            "the page snapshot (default: 8)."
        ),
    )
    parser.add_argument(
        "--amazon-first-page-attempts",
        type=int,
        default=3,
        help=(
            "For Amazon, retry page-1 snapshot up to this many times and keep the best "
            "result before deciding to skip (default: 3)."
        ),
    )
    parser.add_argument(
        "--category-name",
        help="Category name to use when providing --category-url (required with --category-url).",
    )
    parser.add_argument(
        "--reuse-open-tab",
        action="store_true",
        help="Reuse the first existing page in the attached Chrome context.",
    )
    parser.add_argument(
        "--no-navigation",
        action="store_true",
        help="Do not navigate; operate on the existing tab as-is (requires --reuse-open-tab).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum PLP pages to crawl per category when using retailer profile discovery (default: 50).",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=2.0,
        help="Delay between PLP page fetches in retailer profile discovery (default: 2.0 seconds).",
    )
    parser.add_argument(
        "--category-pause-seconds",
        type=float,
        default=1200.0,
        help="Pause between categories in seconds (default: 1200 = 20 minutes).",
    )
    parser.add_argument(
        "--reset-category-links",
        action="store_true",
        help="Clear existing links for selected category keys before recollecting.",
    )
    return parser.parse_args(argv)


def _get_context(remote_url: str) -> tuple[object, Browser, BrowserContext]:
    playwright = sync_playwright().start()
    browser = playwright.chromium.connect_over_cdp(remote_url)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return playwright, browser, context


def _close_cdp_session(playwright: object | None, browser: Browser | None) -> None:
    try:
        if browser is not None:
            browser.close()
    except Exception:
        pass
    try:
        if playwright is not None:
            playwright.stop()
    except Exception:
        pass


def _is_closed_target_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "target page, context or browser has been closed" in message
        or "context has been closed" in message
        or "browser has been closed" in message
    )


def _get_or_create_page_with_reconnect(
    *,
    remote_url: str,
    playwright: object | None,
    browser: Browser | None,
    context: BrowserContext | None,
    reuse_open_tab: bool,
    reconnect_attempts: int = 2,
) -> tuple[object, Browser, BrowserContext, Page, bool]:
    current_playwright = playwright
    current_browser = browser
    current_context = context
    last_exc: Exception | None = None

    for attempt in range(reconnect_attempts + 1):
        if current_context is not None:
            try:
                page, created_new_page = _get_or_create_page(
                    current_context, reuse_open_tab
                )
                return (
                    current_playwright,
                    current_browser,
                    current_context,
                    page,
                    created_new_page,
                )
            except (
                Exception
            ) as exc:  # noqa: BLE001 - CDP sessions can be closed externally
                last_exc = exc
                if not _is_closed_target_error(exc):
                    raise
                LOGGER.warning(
                    "Attached Chrome context closed while opening a tab (attempt %d/%d).",
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
        _close_cdp_session(current_playwright, current_browser)
        current_playwright, current_browser, current_context = _get_context(remote_url)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Unable to acquire browser page from CDP session.")


def _first_open_page(context: BrowserContext) -> Page | None:
    fallback: Page | None = None
    for candidate in reversed(context.pages):
        try:
            if candidate.is_closed():
                continue
            if fallback is None:
                fallback = candidate
            current_url = str(candidate.url or "").strip().lower()
            if current_url.startswith(
                ("chrome://", "devtools://", "chrome-extension://")
            ):
                continue
            return candidate
        except Exception:
            continue
    return fallback


def _get_or_create_page(
    context: BrowserContext, reuse_open_tab: bool, retries: int = 3
) -> tuple[Page, bool]:
    if reuse_open_tab:
        existing = _first_open_page(context)
        if existing is not None:
            return existing, False

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return context.new_page(), True
        except Exception as exc:  # noqa: BLE001 - CDP tabs can transiently fail
            last_exc = exc
            LOGGER.info(
                "Unable to open a new browser tab (attempt %d/%d): %s",
                attempt,
                retries,
                exc,
            )
            existing = _first_open_page(context)
            if existing is not None:
                LOGGER.info("Falling back to existing tab: %s", existing.url)
                return existing, False
            if attempt < retries:
                time.sleep(0.5 * attempt)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Failed to obtain a browser page from the attached context.")


def _goto(page: Page, url: str, timeout_ms: int) -> bool:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        LOGGER.info("Navigation timed out for %s", url)
        return False
    except Exception as exc:  # noqa: BLE001
        LOGGER.info("Navigation error for %s: %s", url, exc)
        return False


def _is_amazon_interstitial(page: Page) -> bool:
    current_url = (page.url or "").lower()
    if "validatecaptcha" in current_url or "/errors/" in current_url:
        return True
    try:
        title = (page.title() or "").lower()
    except Exception:
        title = ""
    if "robot check" in title:
        return True
    try:
        body = (page.content() or "").lower()
    except Exception:
        return False
    return (
        "robot check" in body
        or "enter the characters you see below" in body
        or "type the characters you see in this image" in body
    )


def _normalize_category_key(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.strip().lower().replace("-", "_").replace(" ", "_")


def _amazon_title_matches_category(title: str, category_key: str | None) -> bool:
    normalized_category = _normalize_category_key(category_key)
    if not normalized_category:
        return True
    # This category is intentionally sourced from two explicit Amazon search seeds
    # (setting spray + setting powder). Strict title gating under-filters in some
    # sessions and drops valid ASINs, so trust the seeded query scope instead.
    if normalized_category == "setting_spray_powder":
        return True
    rules = AMAZON_CATEGORY_TITLE_RULES.get(normalized_category)
    if not rules:
        return True
    normalized_title = " ".join(title.lower().split())
    if not normalized_title:
        # Title extraction can occasionally fail on dynamic result cards.
        # Keep the ASIN candidate rather than dropping the entire page.
        return True
    has_media_term = any(term in normalized_title for term in AMAZON_MEDIA_TERMS)
    has_strong_cosmetic_context = any(
        term in normalized_title for term in AMAZON_STRONG_COSMETIC_CONTEXT_TERMS
    )
    if has_media_term and not has_strong_cosmetic_context:
        return False
    if any(term in normalized_title for term in AMAZON_GLOBAL_TITLE_EXCLUDES):
        return False
    excludes = rules.get("exclude", ())
    if excludes and any(term in normalized_title for term in excludes):
        return False
    includes = rules.get("include", ())
    if not includes:
        return True
    return any(term in normalized_title for term in includes)


def _scroll_collect(
    page: Page,
    selector: str,
    retailer: str,
    category_key: str | None,
    scroll_steps: int,
    wait_ms: int,
    max_links: int,
    max_idle_scrolls: int,
) -> list[str]:
    def _safe_wait_for_dom() -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            return

    def grab() -> list[dict[str, str]]:
        # Amazon pages can re-render mid-read when attached over CDP. Retry and
        # keep extraction restricted to search result cards.
        for attempt in range(3):
            try:
                if retailer.lower() == "amazon":
                    return page.eval_on_selector_all(
                        AMAZON_RESULT_CARD_SELECTOR,
                        (
                            "cards => {"
                            "const out = [];"
                            "const seen = new Set();"
                            "const asinRe = /\\/(?:dp|gp\\/product)\\/([A-Z0-9]{10})/i;"
                            "const titleSelectors = ["
                            '"h2 a span",'
                            '"h2 span",'
                            "\"span[data-cy='title-recipe']\","
                            '"span.a-size-base-plus.a-color-base",'
                            '"span.a-size-medium.a-color-base"'
                            "];"
                            "for (const card of cards) {"
                            "const titleEl = titleSelectors.map(sel => card.querySelector(sel)).find(Boolean);"
                            "let title = (titleEl && titleEl.textContent ? titleEl.textContent : '').trim();"
                            "if (!title) {"
                            "const h2 = card.querySelector('h2');"
                            "if (h2) title = ((h2.getAttribute('aria-label') || h2.textContent || '')).trim();"
                            "}"
                            "if (!title) {"
                            "const titleAnchor = card.querySelector(\"a[href*='/dp/'], a[href*='/gp/product/']\");"
                            "if (titleAnchor) title = ((titleAnchor.getAttribute('aria-label') || titleAnchor.textContent || '')).trim();"
                            "}"
                            "if (!title) {"
                            "const img = card.querySelector('img[alt]');"
                            "if (img) title = (img.getAttribute('alt') || '').trim();"
                            "}"
                            "const pushUrl = (url) => {"
                            "if (!url || seen.has(url)) return;"
                            "seen.add(url);"
                            "out.push({ url, title });"
                            "};"
                            "const asin = (card.getAttribute('data-asin') || '').trim().toUpperCase();"
                            "if (/^[A-Z0-9]{10}$/.test(asin)) pushUrl(`https://www.amazon.com/dp/${asin}`);"
                            "const anchors = card.querySelectorAll(\"a[href*='/dp/'], a[href*='/gp/product/']\");"
                            "for (const anchor of anchors) {"
                            "const href = anchor.href || '';"
                            "const m = href.match(asinRe);"
                            "if (m) pushUrl(`https://www.amazon.com/dp/${m[1].toUpperCase()}`);"
                            "}"
                            "}"
                            "return out;"
                            "}"
                        ),
                    )
                hrefs = page.eval_on_selector_all(
                    selector, "els => [...new Set(els.map(e => e.href))]"
                )
                return [{"url": href} for href in hrefs if isinstance(href, str)]
            except PlaywrightError as exc:
                LOGGER.info(
                    "Selector eval failed (attempt %d/3): %s",
                    attempt + 1,
                    exc,
                )
                _safe_wait_for_dom()
                page.wait_for_timeout(350)
            except Exception as exc:  # noqa: BLE001 - defensive for flaky pages
                LOGGER.info("Unexpected selector eval error: %s", exc)
                _safe_wait_for_dom()
                page.wait_for_timeout(350)

        if retailer.lower() == "amazon":
            LOGGER.info("Amazon result-card extraction failed after retries.")
            return []

        try:
            hrefs = page.eval_on_selector_all(
                "a[href]", "els => [...new Set(els.map(e => e.href))]"
            )
            return [{"url": href} for href in hrefs if isinstance(href, str)]
        except Exception as exc:  # noqa: BLE001 - final fallback
            LOGGER.info("Anchor fallback extraction failed: %s", exc)
            return []

    links: list[str] = []
    seen: set[str] = set()

    def ingest(items: list[dict[str, str]]) -> int:
        added = 0
        for item in items:
            href = str(item.get("url", "")).strip()
            if not href:
                continue
            if href not in seen:
                seen.add(href)
                links.append(href)
                added += 1
        return added

    if retailer.lower() == "amazon":
        LOGGER.info(
            "Collecting canonical product links from Amazon search-result cards (initial pass)..."
        )
    else:
        LOGGER.info("Collecting candidate links (initial pass)...")
    ingest(grab())
    if retailer.lower() == "amazon":
        LOGGER.info(
            "Initial Amazon search-result product links collected: %d",
            len(links),
        )
    else:
        LOGGER.info("Initial candidate links collected: %d", len(links))
    if max_links and len(links) >= max_links:
        return links[:max_links]

    if scroll_steps:
        LOGGER.info(
            "Scrolling up to %d steps (wait %d ms each; stop after %d idle steps)...",
            scroll_steps,
            wait_ms,
            max_idle_scrolls,
        )

    idle_steps = 0
    for idx in range(max(scroll_steps, 0)):
        before_count = len(links)
        # Scroll down to trigger lazy loading, then a small upward jiggle so we don't get stuck at the bottom.
        page.mouse.wheel(0, 3200)
        page.wait_for_timeout(wait_ms // 2 if wait_ms > 1 else 0)
        page.mouse.wheel(0, -1800)
        page.wait_for_timeout(wait_ms - wait_ms // 2 if wait_ms > 1 else 0)
        ingest(grab())
        new_this_step = len(links) - before_count
        if new_this_step == 0:
            idle_steps += 1
        else:
            idle_steps = 0
        if retailer.lower() == "amazon":
            LOGGER.info(
                "After scroll %d, total Amazon search-result product links: %d (new this step: %d, idle: %d/%d)",
                idx + 1,
                len(links),
                new_this_step,
                idle_steps,
                max_idle_scrolls,
            )
        else:
            LOGGER.info(
                "After scroll %d, total candidate links: %d (new this step: %d, idle: %d/%d)",
                idx + 1,
                len(links),
                new_this_step,
                idle_steps,
                max_idle_scrolls,
            )
        if max_links and len(links) >= max_links:
            return links[:max_links]
        if max_idle_scrolls > 0 and idle_steps >= max_idle_scrolls:
            LOGGER.info("Stopping scroll early after %d idle steps.", idle_steps)
            break
    return links


def _pagination_param_for(retailer: str | None, base_url: str) -> str:
    r = (retailer or "").lower()
    if r == "amazon":
        return "page"
    if r == "sephora":
        return "currentPage"
    if "currentPage=" in base_url:
        return "currentPage"
    if re.search(r"(?:\?|&)page=", base_url):
        return "page"
    return "currentPage"


def _set_query_param(url: str, key: str, value: int) -> str:
    parts = urlsplit(url)
    query_items = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key
    ]
    query_items.append((key, str(value)))
    query = urlencode(query_items, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _page_urls(base_url: str, start: int, end: int, page_param: str) -> list[str]:
    urls: list[str] = []
    for p in range(start, end + 1):
        if p == 1:
            urls.append(base_url)
            continue
        urls.append(_set_query_param(base_url, page_param, p))
    return urls


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_links_from_json(path: Path) -> dict[str, dict[str, list[str]]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    # support single retailer payload or top-level retailer map
    if "retailer" in payload and "categories" in payload:
        retailer = str(payload.get("retailer", "")).lower()
        cats = payload.get("categories")
        if isinstance(cats, Mapping):
            return {retailer: {k: v for k, v in cats.items() if isinstance(v, list)}}
    result: dict[str, dict[str, list[str]]] = {}
    for retailer, cats in payload.items():
        if not isinstance(cats, Mapping):
            continue
        cat_map: dict[str, list[str]] = {}
        for key, links in cats.items():
            if isinstance(links, list):
                cat_map[str(key)] = [
                    str(link) for link in links if isinstance(link, str)
                ]
        result[str(retailer).lower()] = cat_map
    return result


def _allowed_patterns(retailer: str) -> Iterable[re.Pattern[str]] | None:
    r = retailer.lower()
    if r == "ulta":
        return (re.compile(r"/p/"),)
    if r == "sephora":
        return (re.compile(r"/product/"),)
    if r == "amazon":
        return (re.compile(r"/dp/"), re.compile(r"/gp/product/"))
    return None


def _default_selector_for(retailer: str | None) -> str:
    r = (retailer or "").lower()
    if r == "sephora":
        return "a[data-at='product_link'], a[href*='/product/']"
    if r == "ulta":
        return "a[href*='/product/'], a[href*='/p/']"
    if r == "amazon":
        return "a[href*='/dp/'], a[href*='/gp/product/']"
    return "a[data-at='product_link'], a[href*='/product/'], a[href*='/p/'], a[href*='/dp/'], a[href*='/gp/product/']"


def _normalize_link_for_retailer(link: str, retailer: str) -> str:
    if retailer.lower() != "amazon":
        return link
    match = AMAZON_ASIN_IN_PATH.search(link)
    if not match:
        return link
    asin = match.group(1).upper()
    return f"https://www.amazon.com/dp/{asin}"


def _postprocess_links(links: list[str], retailer: str) -> list[str]:
    patterns = _allowed_patterns(retailer)
    normalized: list[str] = []
    seen: set[str] = set()
    for href in links:
        if patterns and not any(pattern.search(href) for pattern in patterns):
            continue
        canonical = _normalize_link_for_retailer(href, retailer)
        if canonical not in seen:
            seen.add(canonical)
            normalized.append(canonical)
    return normalized


def _category_key(profile_name: str, retailer: str) -> str:
    prefix = f"{retailer.lower()}_"
    if profile_name.lower().startswith(prefix):
        return profile_name[len(prefix) :]
    return profile_name


def _category_matches_filter(category_key: str, category_filter: set[str]) -> bool:
    """Return True when category_key matches filter, allowing simple pluralization."""
    if not category_filter:
        return True
    key = category_key.lower()
    if key in category_filter:
        return True
    if (
        key.endswith("s")
        and not key.endswith("ss")
        and len(key) > 3
        and key[:-1] in category_filter
    ):
        return True
    if not key.endswith("s") and f"{key}s" in category_filter:
        return True
    return False


def _suggest_categories(requested: str, available: Sequence[str]) -> list[str]:
    matches = difflib.get_close_matches(requested, available, n=3, cutoff=0.72)
    return [match for match in matches if match != requested]


def _dismiss_sephora_banner(page: Page) -> None:
    """Best-effort close for the Sephora geo/overlay banner."""
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
    for attempt in range(6):
        for selector in selectors:
            try:
                element = page.query_selector(selector)
                if element:
                    element.click(timeout=2000, force=True)
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue
        try:
            btn = page.query_selector("button:has-text('Continue to Sephora')")
            if btn:
                btn.click(timeout=2000, force=True)
                page.wait_for_timeout(500)
                return
        except Exception:
            pass
        page.wait_for_timeout(400)


def _iterate_pages(base_url: str, page_param: str):
    """Yield URLs with incremented page query parameter until navigation fails/no links."""
    page_num = 1
    while True:
        if page_num == 1:
            yield base_url
        else:
            yield _set_query_param(base_url, page_param, page_num)
        page_num += 1


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    output_path = Path("data/pdp/links.json")
    existing_payload = _read_links_from_json(output_path)
    seen: set[str] = set()

    if args.no_navigation and not args.reuse_open_tab:
        LOGGER.error("--no-navigation requires --reuse-open-tab.")
        return 1
    if not args.no_navigation and not args.category_url and not args.retailer:
        LOGGER.error("--retailer or --category-url is required.")
        return 1
    if args.category_url and not args.retailer:
        LOGGER.error(
            "--retailer is required when using --category-url so output can be keyed correctly."
        )
        return 1
    if args.category_url and not args.category_name:
        LOGGER.error("--category-name is required when using --category-url.")
        return 1
    if args.page_end < args.page_start and not args.auto_paginate:
        LOGGER.error("--page-end must be >= --page-start.")
        return 1

    retailer_key = (args.retailer or "").lower()
    retailer_payload: dict[str, list[str]] = (
        {k: list(v) for k, v in existing_payload.get(retailer_key, {}).items()}
        if retailer_key
        else {}
    )
    if retailer_key:
        seen.update(link for links in retailer_payload.values() for link in links)

    playwright = None
    browser = None
    context = None
    baseline_links = len(seen)
    try:
        playwright, browser, context = _get_context(args.remote_url)
        total_links = len(seen)
        samples: list[str] = []

        # Build target categories/URLs.
        targets: list[tuple[str, tuple[str, ...]]] = []
        available_categories: list[str] = []
        if args.category_url:
            targets.append((args.category_name, (args.category_url,)))
        elif args.retailer:
            category_filter = {c.lower() for c in (args.categories or [])}
            for summary in iter_profile_summaries():
                if summary.retailer.lower() != retailer_key:
                    continue
                category_key = _category_key(summary.profile_name, retailer_key)
                available_categories.append(category_key.lower())
                if not _category_matches_filter(category_key, category_filter):
                    continue
                profile = load_profile(summary.profile_name)
                category_urls = tuple(profile.category_urls)
                if not category_urls:
                    continue
                targets.append((category_key, category_urls))

        if not targets:
            if retailer_key and args.categories:
                available_sorted = sorted(set(available_categories))
                if available_sorted:
                    LOGGER.error(
                        "Available categories for %s: %s",
                        retailer_key,
                        ", ".join(available_sorted),
                    )
                for requested in args.categories:
                    suggestions = _suggest_categories(
                        requested.lower(), available_sorted
                    )
                    if suggestions:
                        LOGGER.error("Did you mean --categories %s ?", suggestions[0])
            LOGGER.error(
                "No categories resolved. Provide --category-url or ensure retailer profiles exist."
            )
            return 1

        if args.reset_category_links and retailer_key:
            reset_categories = [name for name, _ in targets]
            removed_links = 0
            for category_name in reset_categories:
                removed_links += len(retailer_payload.get(category_name, []))
                retailer_payload[category_name] = []
            existing_payload[retailer_key] = retailer_payload
            seen = {link for links in retailer_payload.values() for link in links}
            baseline_links = len(seen)
            _write_json(output_path, existing_payload)
            LOGGER.info(
                "Reset existing links for %s categorie(s): %s (removed %d links).",
                retailer_key,
                ", ".join(reset_categories),
                removed_links,
            )

        for category_idx, (category_name, category_urls) in enumerate(targets, start=1):
            if category_idx > 1 and args.category_pause_seconds > 0:
                LOGGER.info(
                    "Pausing %.1f second(s) before next category (%s / %s).",
                    args.category_pause_seconds,
                    retailer_key,
                    category_name,
                )
                time.sleep(args.category_pause_seconds)
            category_seen: set[str] = set()
            existing_links = retailer_payload.get(category_name, [])
            if isinstance(existing_links, list):
                category_seen = {str(link) for link in existing_links}
                seen.update(category_seen)
                LOGGER.info(
                    "Seeding %d existing link(s) for %s / %s from %s",
                    len(category_seen),
                    retailer_key,
                    category_name,
                    output_path,
                )

            selector = _default_selector_for(retailer_key)

            if args.no_navigation:
                try:
                    (
                        playwright,
                        browser,
                        context,
                        page,
                        _,
                    ) = _get_or_create_page_with_reconnect(
                        remote_url=args.remote_url,
                        playwright=playwright,
                        browser=browser,
                        context=context,
                        reuse_open_tab=args.reuse_open_tab,
                    )
                except (
                    Exception
                ) as exc:  # noqa: BLE001 - CDP tab acquisition can fail transiently
                    LOGGER.error(
                        "Unable to open a browser tab in the attached Chrome context: %s",
                        exc,
                    )
                    return 1
                LOGGER.info("Using existing tab without navigation: %s", page.url)
                if retailer_key == "sephora":
                    _dismiss_sephora_banner(page)
                raw_links = _scroll_collect(
                    page,
                    selector=selector,
                    retailer=retailer_key,
                    category_key=category_name,
                    scroll_steps=args.scroll_steps,
                    wait_ms=args.wait_ms,
                    max_links=args.max_links,
                    max_idle_scrolls=args.max_idle_scrolls,
                )
                links = _postprocess_links(raw_links, retailer_key)
                LOGGER.info(
                    "Post-processed links: raw candidates=%d, canonical PDP links=%d",
                    len(raw_links),
                    len(links),
                )
                new_links = [href for href in links if href not in category_seen]
                category_seen.update(new_links)
                seen.update(new_links)
                retailer_payload[category_name] = sorted(category_seen)
                existing_payload[retailer_key] = retailer_payload
                _write_json(output_path, existing_payload)
                LOGGER.info(
                    "Checkpoint saved after no-navigation run: %d link(s) for %s / %s",
                    len(category_seen),
                    retailer_key,
                    category_name,
                )
                total_links = len(seen)
                if len(samples) < 5:
                    samples.extend(new_links[: 5 - len(samples)])
            else:
                for seed_idx, category_url in enumerate(category_urls, start=1):
                    if len(category_urls) > 1:
                        LOGGER.info(
                            "Using category seed URL %d/%d for %s / %s: %s",
                            seed_idx,
                            len(category_urls),
                            retailer_key,
                            category_name,
                            category_url,
                        )
                    page_param = _pagination_param_for(retailer_key, category_url)

                    if args.auto_paginate:
                        pages_iterable = _iterate_pages(category_url, page_param)
                        LOGGER.info(
                            "Auto-paginate mode: incrementing %s until failure/no links (max %d pages).",
                            page_param,
                            args.max_pages,
                        )
                        total_hint = "?"
                    else:
                        pages = _page_urls(
                            category_url, args.page_start, args.page_end, page_param
                        )
                        pages_iterable = pages
                        total_hint = str(len(pages))

                    page: Page | None = None
                    created_new_page = False
                    try:
                        (
                            playwright,
                            browser,
                            context,
                            page,
                            created_new_page,
                        ) = _get_or_create_page_with_reconnect(
                            remote_url=args.remote_url,
                            playwright=playwright,
                            browser=browser,
                            context=context,
                            reuse_open_tab=args.reuse_open_tab,
                        )
                        if not created_new_page:
                            LOGGER.info(
                                "Reusing existing tab for pagination: %s", page.url
                            )
                    except (
                        Exception
                    ) as exc:  # noqa: BLE001 - CDP sessions can occasionally fail tab creation
                        LOGGER.error(
                            "Unable to open a browser tab in the attached Chrome context: %s",
                            exc,
                        )
                        LOGGER.error(
                            "No usable tab is available. Restart Chrome with remote debugging and retry."
                        )
                        return 1

                    try:
                        for idx, url in enumerate(pages_iterable, start=1):
                            if args.auto_paginate and idx > args.max_pages:
                                LOGGER.info(
                                    "Reached --max-pages=%d; stopping auto-paginate.",
                                    args.max_pages,
                                )
                                break
                            LOGGER.info(
                                "(%d/%s) Navigating to page: %s", idx, total_hint, url
                            )
                            ok = _goto(page, url, args.timeout_ms)
                            if not ok:
                                if args.auto_paginate:
                                    LOGGER.info(
                                        "Navigation failed; stopping auto-paginate."
                                    )
                                    break
                                continue
                            if retailer_key == "amazon" and _is_amazon_interstitial(
                                page
                            ):
                                LOGGER.warning(
                                    "Amazon bot wall/interstitial detected for %s. "
                                    "Open the attached Chrome window, resolve it if needed, then rerun.",
                                    url,
                                )
                                if args.auto_paginate:
                                    break
                                continue
                            try:
                                page.wait_for_selector(
                                    selector, timeout=args.timeout_ms
                                )
                            except Exception:
                                LOGGER.info(
                                    "Selector %s not found within timeout; continuing anyway.",
                                    selector,
                                )
                            if retailer_key == "sephora":
                                _dismiss_sephora_banner(page)

                            if (
                                retailer_key == "amazon"
                                and idx == 1
                                and args.amazon_min_first_page_links > 0
                            ):
                                best_preview_count = -1
                                best_preview_attempt = 0
                                max_preview_attempts = max(
                                    1, args.amazon_first_page_attempts
                                )
                                for preview_attempt in range(
                                    1, max_preview_attempts + 1
                                ):
                                    try:
                                        preview_raw_links = _scroll_collect(
                                            page,
                                            selector=selector,
                                            retailer=retailer_key,
                                            category_key=category_name,
                                            scroll_steps=0,
                                            wait_ms=args.wait_ms,
                                            max_links=args.max_links,
                                            max_idle_scrolls=0,
                                        )
                                    except PlaywrightError as exc:
                                        LOGGER.info(
                                            "Amazon page-1 preview collection failed on %s: %s",
                                            url,
                                            exc,
                                        )
                                        preview_raw_links = []
                                    preview_links = _postprocess_links(
                                        preview_raw_links, retailer_key
                                    )
                                    preview_count = len(preview_links)
                                    if preview_count > best_preview_count:
                                        best_preview_count = preview_count
                                        best_preview_attempt = preview_attempt
                                    if (
                                        preview_count
                                        >= args.amazon_min_first_page_links
                                    ):
                                        break
                                    if preview_attempt < max_preview_attempts:
                                        LOGGER.warning(
                                            "Low Amazon page-1 candidates for %s / %s on attempt %d/%d: %d (< %d). Retrying...",
                                            retailer_key,
                                            category_name,
                                            preview_attempt,
                                            max_preview_attempts,
                                            preview_count,
                                            args.amazon_min_first_page_links,
                                        )
                                        if not _goto(page, url, args.timeout_ms):
                                            break
                                        if _is_amazon_interstitial(page):
                                            break
                                if (
                                    best_preview_count
                                    < args.amazon_min_first_page_links
                                ):
                                    LOGGER.warning(
                                        "Skipping low-yield Amazon page-1 snapshot for %s / %s: best=%d required=%d url=%s",
                                        retailer_key,
                                        category_name,
                                        best_preview_count,
                                        args.amazon_min_first_page_links,
                                        url,
                                    )
                                    if args.auto_paginate:
                                        LOGGER.info(
                                            "Stopping auto-paginate because page 1 did not pass Amazon quality gate."
                                        )
                                        break
                                    continue
                                if best_preview_attempt > 1:
                                    LOGGER.info(
                                        "Accepted Amazon page-1 after retry attempt %d with %d canonical links.",
                                        best_preview_attempt,
                                        best_preview_count,
                                    )

                            try:
                                raw_links = _scroll_collect(
                                    page,
                                    selector=selector,
                                    retailer=retailer_key,
                                    category_key=category_name,
                                    scroll_steps=args.scroll_steps,
                                    wait_ms=args.wait_ms,
                                    max_links=args.max_links,
                                    max_idle_scrolls=args.max_idle_scrolls,
                                )
                            except PlaywrightError as exc:
                                LOGGER.info(
                                    "Link collection failed on %s: %s", url, exc
                                )
                                if args.auto_paginate:
                                    LOGGER.info(
                                        "Stopping auto-paginate after page interaction failure."
                                    )
                                    break
                                continue
                            links = _postprocess_links(raw_links, retailer_key)
                            LOGGER.info(
                                "Post-processed links: raw candidates=%d, canonical PDP links=%d",
                                len(raw_links),
                                len(links),
                            )
                            new_links = [
                                href for href in links if href not in category_seen
                            ]
                            category_seen.update(new_links)
                            seen.update(new_links)
                            LOGGER.info(
                                "Links collected on this page: %d (new: %d)",
                                len(links),
                                len(new_links),
                            )
                            total_links = len(seen)
                            retailer_payload[category_name] = sorted(category_seen)
                            existing_payload[retailer_key] = retailer_payload
                            _write_json(output_path, existing_payload)
                            LOGGER.info(
                                "Checkpoint saved after page %d: %d link(s) for %s / %s",
                                idx,
                                len(category_seen),
                                retailer_key,
                                category_name,
                            )
                            if len(samples) < 5:
                                samples.extend(new_links[: 5 - len(samples)])
                            LOGGER.info("Running total links: %d", total_links)
                            if (
                                args.auto_paginate
                                and len(links) < args.min_new_per_page
                            ):
                                LOGGER.info(
                                    "Only %d canonical links detected on %s (< %d); stopping auto-paginate.",
                                    len(links),
                                    url,
                                    args.min_new_per_page,
                                )
                                break
                    finally:
                        if created_new_page and page is not None:
                            try:
                                page.close()
                            except Exception:
                                pass

            retailer_payload[category_name] = sorted(category_seen)
            existing_payload[retailer_key] = retailer_payload
            _write_json(output_path, existing_payload)
            LOGGER.info(
                "Saved %d link(s) for %s / %s to %s",
                len(category_seen),
                retailer_key,
                category_name,
                output_path,
            )

        LOGGER.info("Total links collected across pages: %d", total_links)
        if total_links >= baseline_links:
            LOGGER.info("New links added this run: %d", total_links - baseline_links)
        if samples:
            LOGGER.info("Sample links: %s", samples)
        return 0
    finally:
        _close_cdp_session(playwright, browser)


if __name__ == "__main__":
    sys.exit(main())
