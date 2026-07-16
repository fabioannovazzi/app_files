from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup  # type: ignore[import]
from playwright.sync_api import (
    Browser,
    BrowserContext,
)
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import (
    Locator,
    Page,
)
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import (
    sync_playwright,
)

from .cdp_failure_diagnostics import write_cdp_failure_bundle

LOGGER = logging.getLogger(__name__)

AMAZON_RESULT_CARD_SELECTOR = (
    "div.s-main-slot div[data-component-type='s-search-result'][data-asin]"
)

__all__ = [
    "CandidateLink",
    "CapturedListingPage",
    "CDPListingEngine",
    "ListingStatePreparationError",
    "find_next_page_url",
    "set_query_param",
]

_CHEWY_LISTING_STATE_QUERY_KEYS = {
    "sort",
    "page",
    "p",
    "pagenumber",
    "pagenum",
    "currentpage",
}
_CHEWY_SORT_SELECTORS = ("#plp-sort-select, select.kib-input-select__control",)
_CHEWY_SORT_LABEL_TO_VALUE = {
    "Newest": "byNewest",
    "Bestselling": "byPopularity",
}
_CHEWY_SORT_LABEL_TO_INDEX = {
    "Newest": 1,
    "Bestselling": 2,
}
_CHEWY_SORT_CONTROL_TIMEOUT_MS = 10_000


class ListingStatePreparationError(RuntimeError):
    """Raised when a required browser-side listing state cannot be verified."""


@dataclass(slots=True)
class CandidateLink:
    """Represent one candidate PDP link discovered on a listing page."""

    url: str
    title: str | None = None
    is_sponsored: bool = False
    is_before_sort_control: bool = False


@dataclass(slots=True)
class CapturedListingPage:
    """Capture the rendered state of one listing page."""

    requested_url: str
    final_url: str
    html: str
    candidates: tuple[CandidateLink, ...]
    page_title: str | None = None
    selector_found: bool = True


class CDPListingEngine:
    """Collect listing pages through an attached Chrome CDP session."""

    def __init__(
        self,
        *,
        remote_url: str,
        reuse_open_tab: bool = False,
        timeout_ms: int = 45_000,
        wait_ms: int = 4_000,
        scroll_steps: int = 40,
        max_idle_scrolls: int = 6,
        max_links: int = 0,
        diagnostic_artifact_root: Path | None = None,
    ) -> None:
        self._remote_url = remote_url
        self._reuse_open_tab = reuse_open_tab
        self._timeout_ms = timeout_ms
        self._wait_ms = wait_ms
        self._scroll_steps = scroll_steps
        self._max_idle_scrolls = max_idle_scrolls
        self._max_links = max_links
        self._diagnostic_artifact_root = diagnostic_artifact_root
        self._playwright: object | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> CDPListingEngine:
        self.connect()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def connect(self) -> None:
        if self._context is not None:
            return
        self._playwright, self._browser, self._context = _get_context(self._remote_url)

    def close(self) -> None:
        _close_cdp_session(self._playwright, self._browser)
        self._playwright = None
        self._browser = None
        self._context = None

    def capture_listing_page(
        self,
        *,
        url: str,
        selector: str,
        retailer: str,
        category_key: str | None = None,
        sort_mode: str | None = None,
        load_more_texts: tuple[str, ...] = (),
        navigate: bool = True,
        force_navigation: bool = False,
        sort_control_mode: str = "set",
    ) -> CapturedListingPage | None:
        page = self._get_or_create_page()
        if _same_document_url(page.url, url) and not force_navigation:
            LOGGER.info("Using already loaded tab without navigation: %s", page.url)
        elif navigate:
            if not _navigate_to_listing_page(
                page,
                url,
                timeout_ms=self._timeout_ms,
                retailer=retailer,
            ):
                self._persist_failure_bundle(
                    page=page,
                    requested_url=url,
                    selector=selector,
                    retailer=retailer,
                    category_key=category_key,
                    reason="navigation_failed",
                    candidate_count=0,
                    selector_found=False,
                )
                return None
        else:
            matching_page = _find_open_page_matching_url(self._context, url)
            if matching_page is None:
                self._playwright, self._browser, self._context = _reconnect_context(
                    self._remote_url,
                    self._playwright,
                    self._browser,
                )
                matching_page = _find_open_page_matching_url(self._context, url)
            if matching_page is not None:
                page = matching_page
            if not _manual_navigation_url_matches(page.url, url):
                LOGGER.warning(
                    "Manual navigation URL mismatch: current tab is %s but requested URL is %s",
                    page.url,
                    url,
                )
                self._persist_failure_bundle(
                    page=page,
                    requested_url=url,
                    selector=selector,
                    retailer=retailer,
                    category_key=category_key,
                    reason="manual_url_mismatch",
                    candidate_count=0,
                    selector_found=False,
                )
                return None
            LOGGER.info("Manual navigation mode: capturing loaded tab %s", page.url)
        url_state_error = _chewy_listing_url_state_error(
            current_url=page.url,
            requested_url=url,
            retailer=retailer,
            sort_mode=sort_mode,
        )
        if url_state_error:
            bundle_dir = self._persist_failure_bundle(
                page=page,
                requested_url=url,
                selector=selector,
                retailer=retailer,
                category_key=category_key,
                reason="listing_url_state_mismatch",
                candidate_count=0,
                selector_found=False,
            )
            if bundle_dir is not None:
                LOGGER.error(
                    "%s; wrote failure bundle to %s", url_state_error, bundle_dir
                )
            else:
                LOGGER.error("%s", url_state_error)
            return None
        if _recover_from_terminal_page(page, timeout_ms=min(self._timeout_ms, 5_000)):
            html = page.content()
            final_url = page.url or url
            page_title = _safe_page_title(page)
            bundle_dir = self._persist_failure_bundle(
                page=page,
                requested_url=url,
                selector=selector,
                retailer=retailer,
                category_key=category_key,
                reason="terminal_page",
                candidate_count=0,
                selector_found=False,
            )
            if bundle_dir is not None:
                LOGGER.warning(
                    "Terminal page detected for %s / %s; wrote failure bundle to %s",
                    retailer,
                    category_key or "unknown-category",
                    bundle_dir,
                )
            return CapturedListingPage(
                requested_url=url,
                final_url=final_url,
                html=html,
                candidates=(),
                page_title=page_title,
                selector_found=False,
            )
        selector_found = True
        if selector:
            try:
                page.wait_for_selector(selector, timeout=self._timeout_ms)
            except Exception:
                selector_found = False
                LOGGER.info(
                    "Selector %s not found within timeout for %s; continuing.",
                    selector,
                    url,
                )
        if self._wait_ms > 0:
            page.wait_for_timeout(self._wait_ms)
        try:
            _prepare_retailer_listing_state(
                page,
                retailer=retailer,
                sort_mode=sort_mode,
                wait_ms=self._wait_ms,
                sort_control_mode=sort_control_mode,
            )
        except ListingStatePreparationError as exc:
            bundle_dir = self._persist_failure_bundle(
                page=page,
                requested_url=url,
                selector=selector,
                retailer=retailer,
                category_key=category_key,
                reason="listing_state_preparation_failed",
                candidate_count=0,
                selector_found=selector_found,
            )
            if bundle_dir is not None:
                LOGGER.error(
                    "%s; wrote failure bundle to %s",
                    exc,
                    bundle_dir,
                )
            else:
                LOGGER.error("%s", exc)
            return None
        candidates = _scroll_collect_candidates(
            page,
            selector=selector,
            retailer=retailer,
            category_key=category_key,
            scroll_steps=self._scroll_steps,
            wait_ms=self._wait_ms,
            max_links=self._max_links,
            max_idle_scrolls=self._max_idle_scrolls,
            load_more_texts=load_more_texts,
        )
        html = page.content()
        final_url = page.url or url
        page_title = _safe_page_title(page)
        if not candidates:
            bundle_dir = self._persist_failure_bundle(
                page=page,
                requested_url=url,
                selector=selector,
                retailer=retailer,
                category_key=category_key,
                reason="no_candidates",
                candidate_count=0,
                selector_found=selector_found,
            )
            if bundle_dir is not None:
                LOGGER.warning(
                    "No candidate links found for %s / %s; wrote failure bundle to %s",
                    retailer,
                    category_key or "unknown-category",
                    bundle_dir,
                )
        return CapturedListingPage(
            requested_url=url,
            final_url=final_url,
            html=html,
            candidates=tuple(candidates),
            page_title=page_title,
            selector_found=selector_found,
        )

    def _get_or_create_page(self) -> Page:
        (
            self._playwright,
            self._browser,
            self._context,
            page,
            _created_new_page,
        ) = _get_or_create_page_with_reconnect(
            remote_url=self._remote_url,
            playwright=self._playwright,
            browser=self._browser,
            context=self._context,
            reuse_open_tab=self._reuse_open_tab,
        )
        return page

    def click_next_listing_page(self, *, retailer: str) -> str | None:
        """Advance a listing page using the visible retailer pagination control."""

        page = self._get_or_create_page()
        return _click_next_listing_page(
            page,
            retailer=retailer,
            timeout_ms=self._timeout_ms,
        )

    def _persist_failure_bundle(
        self,
        *,
        page: Page,
        requested_url: str,
        selector: str,
        retailer: str,
        category_key: str | None,
        reason: str,
        candidate_count: int,
        selector_found: bool,
    ) -> Path | None:
        if self._diagnostic_artifact_root is None:
            return None
        try:
            screenshot_png = page.screenshot(type="png", full_page=True)
        except Exception:
            screenshot_png = None
        try:
            html = page.content()
        except Exception:
            html = ""
        final_url = str(page.url or requested_url)
        page_title = _safe_page_title(page)
        return write_cdp_failure_bundle(
            artifact_root=self._diagnostic_artifact_root,
            requested_url=requested_url,
            final_url=final_url,
            page_title=page_title,
            html=html,
            selector=selector,
            reason=reason,
            retailer=retailer,
            category_key=category_key,
            candidate_count=candidate_count,
            selector_found=selector_found,
            screenshot_png=screenshot_png,
        )


def find_next_page_url(
    *,
    current_url: str,
    html: str,
    current_page: int,
    fallback_page_param: str | None = None,
) -> str | None:
    """Return the next PLP URL when the rendered page exposes one."""

    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith("javascript:"):
            continue
        rel = " ".join(anchor.get("rel", []))
        text = " ".join(anchor.get_text(" ", strip=True).split()).lower()
        aria = str(anchor.get("aria-label") or "").strip().lower()
        title = str(anchor.get("title") or "").strip().lower()
        if (
            rel == "next"
            or "next" in aria
            or "next" in title
            or text
            in {
                "next",
                "next page",
                "›",
                "»",
            }
        ):
            return urljoin(current_url, href)
    if fallback_page_param:
        return set_query_param(current_url, fallback_page_param, current_page + 1)
    return None


def set_query_param(url: str, key: str, value: int | str) -> str:
    """Return URL with one query parameter replaced."""

    parts = urlsplit(url)
    query_items = [
        (name, item)
        for name, item in parse_qsl(parts.query, keep_blank_values=True)
        if name != key
    ]
    query_items.append((key, str(value)))
    query = urlencode(query_items, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _same_document_url(current_url: str | None, target_url: str) -> bool:
    current = str(current_url or "").strip()
    target = str(target_url or "").strip()
    if not current or not target:
        return False
    current_parts = urlsplit(current)
    target_parts = urlsplit(target)
    current_path = current_parts.path.rstrip("/") or "/"
    target_path = target_parts.path.rstrip("/") or "/"
    return (
        current_parts.scheme.lower() == target_parts.scheme.lower()
        and current_parts.netloc.lower() == target_parts.netloc.lower()
        and current_path == target_path
        and current_parts.query == target_parts.query
    )


def _manual_navigation_url_matches(
    current_url: str | None,
    target_url: str,
) -> bool:
    current = str(current_url or "").strip()
    target = str(target_url or "").strip()
    if not current or not target:
        return False
    current_parts = urlsplit(current)
    target_parts = urlsplit(target)
    current_path = current_parts.path.rstrip("/") or "/"
    target_path = target_parts.path.rstrip("/") or "/"
    if (
        current_parts.scheme.lower() != target_parts.scheme.lower()
        or current_parts.netloc.lower() != target_parts.netloc.lower()
        or current_path != target_path
    ):
        return False
    current_query = dict(parse_qsl(current_parts.query, keep_blank_values=True))
    target_query = dict(parse_qsl(target_parts.query, keep_blank_values=True))
    if current_parts.netloc.lower().endswith("chewy.com") and current_path.startswith(
        ("/b/", "/f/")
    ):
        current_query_keys = {item.lower() for item in current_query}
        target_query_keys = {item.lower() for item in target_query}
        if (
            current_query_keys.intersection(_CHEWY_LISTING_STATE_QUERY_KEYS)
            - target_query_keys
        ):
            return False
    return all(current_query.get(key) == value for key, value in target_query.items())


def _chewy_listing_url_state_error(
    *,
    current_url: str | None,
    requested_url: str,
    retailer: str,
    sort_mode: str | None,
) -> str | None:
    if str(retailer or "").strip().lower() != "chewy":
        return None
    if not _chewy_sort_label(sort_mode):
        return None
    current = str(current_url or "").strip()
    requested = str(requested_url or "").strip()
    if not current or not requested:
        return "Chewy ranked capture cannot verify an empty current/requested URL."
    current_parts = urlsplit(current)
    requested_parts = urlsplit(requested)
    current_path = current_parts.path.rstrip("/") or "/"
    requested_path = requested_parts.path.rstrip("/") or "/"
    if (
        current_parts.scheme.lower() != requested_parts.scheme.lower()
        or current_parts.netloc.lower() != requested_parts.netloc.lower()
        or current_path != requested_path
    ):
        return (
            "Chewy ranked capture is on the wrong URL before widget sorting: "
            f"current={current}; requested={requested}"
        )
    current_query = dict(parse_qsl(current_parts.query, keep_blank_values=True))
    requested_query = dict(parse_qsl(requested_parts.query, keep_blank_values=True))
    current_state_keys = {
        key.lower()
        for key in current_query
        if key.lower() in _CHEWY_LISTING_STATE_QUERY_KEYS
    }
    requested_state_keys = {key.lower() for key in requested_query}
    extra_state_keys = current_state_keys - requested_state_keys
    if extra_state_keys:
        return (
            "Chewy ranked capture is on a stale stateful URL before widget sorting: "
            f"current={current}; requested={requested}; "
            f"unexpected_query_keys={sorted(extra_state_keys)}"
        )
    for key, value in requested_query.items():
        if current_query.get(key) != value:
            return (
                "Chewy ranked capture query mismatch before widget sorting: "
                f"current={current}; requested={requested}; key={key}"
            )
    return None


def _get_context(remote_url: str) -> tuple[object, Browser, BrowserContext]:
    playwright = sync_playwright().start()
    browser = playwright.chromium.connect_over_cdp(remote_url)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return playwright, browser, context


def _reconnect_context(
    remote_url: str,
    playwright: object | None,
    browser: Browser | None,
) -> tuple[object, Browser, BrowserContext]:
    _close_cdp_session(playwright, browser)
    return _get_context(remote_url)


def _close_cdp_session(playwright: object | None, browser: Browser | None) -> None:
    # This engine attaches to a user-managed Chrome via CDP. Closing the
    # Browser object can close that visible browser, so only stop Playwright and
    # let Chrome keep running for manual challenge handling between runs.
    _ = browser
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


def _find_open_page_matching_url(
    context: BrowserContext | None,
    url: str,
) -> Page | None:
    if context is None:
        return None
    for candidate in reversed(context.pages):
        try:
            if candidate.is_closed():
                continue
            if _manual_navigation_url_matches(candidate.url, url):
                return candidate
        except Exception:
            continue
    return None


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


def _navigate_to_listing_page(
    page: Page,
    url: str,
    *,
    timeout_ms: int,
    retailer: str,
) -> bool:
    retailer_lower = str(retailer or "").strip().lower()
    if retailer_lower == "chewy" and _navigate_via_address_bar(
        page, url, timeout_ms=timeout_ms
    ):
        return True
    return _goto(page, url, timeout_ms)


def _navigate_via_address_bar(page: Page, url: str, *, timeout_ms: int) -> bool:
    """Navigate through browser UI shortcuts for retailers sensitive to page.goto."""

    try:
        page.bring_to_front()
    except Exception:
        pass

    try:
        page.keyboard.press("Control+L")
        page.keyboard.type(url)
        page.keyboard.press("Enter")
    except Exception as exc:  # noqa: BLE001 - CDP UI navigation can fail externally
        LOGGER.info("Address-bar navigation error for %s: %s", url, exc)
        return False

    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        LOGGER.info("Address-bar navigation timed out for %s", url)
    except Exception as exc:  # noqa: BLE001 - page can detach while loading
        LOGGER.info("Address-bar navigation load-state error for %s: %s", url, exc)
        return False

    try:
        page.wait_for_timeout(1_000)
    except Exception:
        pass
    return _same_document_url(page.url, url)


def _safe_page_title(page: Page) -> str | None:
    try:
        title = " ".join(str(page.title() or "").split())
    except Exception:
        return None
    return title or None


def _safe_page_body_text(page: Page) -> str:
    try:
        body = str(page.text_content("body") or "")
    except Exception:
        return ""
    return " ".join(body.split())


def _looks_like_challenge_page(title: str | None, body: str) -> bool:
    haystack = f"{str(title or '').lower()} {str(body or '').lower()}"
    markers = (
        "cloudflare",
        "verify you are human",
        "performing security verification",
        "security verification",
        "access to this page has been denied",
        "press and hold the box below to confirm you are human",
        "why am i seeing this?",
    )
    return any(marker in haystack for marker in markers)


def _looks_like_terminal_error_page(title: str | None, body: str) -> bool:
    haystack = f"{str(title or '').lower()} {str(body or '').lower()}"
    if _looks_like_challenge_page(title, body):
        return False
    error_markers = (
        "this page needs a makeover",
        "for technical reasons",
        "request could not be handled properly",
        "apologize for any inconvenience",
        "apologies for any inconvenience",
        "something went wrong",
        "temporarily unavailable",
        "please try again later",
        "we hit a snag",
        "let’s get you back on track",
        "let's get you back on track",
        "check your spelling and try it again",
        "products may not be available in your area",
    )
    cta_markers = (
        "continue shopping",
        "return home",
        "go home",
        "back to home",
        "back to shopping",
        "trending now",
        "deals and hot offers",
        "featured brands",
    )
    return any(marker in haystack for marker in error_markers) and any(
        marker in haystack for marker in cta_markers
    )


def _click_recovery_cta_if_available(page: Page) -> bool:
    texts = (
        "continue shopping",
        "return home",
        "go home",
        "back to home",
        "back to shopping",
    )
    for raw_text in texts:
        text = str(raw_text or "").strip()
        if not text:
            continue
        candidates = (
            page.get_by_role("button", name=re.compile(re.escape(text), re.IGNORECASE)),
            page.get_by_role("link", name=re.compile(re.escape(text), re.IGNORECASE)),
            page.locator(
                "button, a, [role='button']",
                has_text=re.compile(re.escape(text), re.IGNORECASE),
            ),
        )
        for locator in candidates:
            target = _first_visible_enabled_locator(locator)
            if target is None:
                continue
            try:
                target.scroll_into_view_if_needed(timeout=2_000)
            except Exception:
                pass
            try:
                target.click(timeout=2_500)
                return True
            except Exception:
                pass
            try:
                target.evaluate(
                    """(el) => {
                        el.scrollIntoView({block: 'center', inline: 'center'});
                        el.click();
                    }"""
                )
                return True
            except Exception:
                continue
    return False


def _recover_from_terminal_page(page: Page, *, timeout_ms: int) -> bool:
    title = _safe_page_title(page)
    body = _safe_page_body_text(page)
    if not _looks_like_terminal_error_page(title, body):
        return False
    clicked = _click_recovery_cta_if_available(page)
    if clicked:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass
        page.wait_for_timeout(500)
    LOGGER.info("Detected retailer terminal page and short-circuited this branch.")
    return True


def _prepare_retailer_listing_state(
    page: Page,
    *,
    retailer: str,
    sort_mode: str | None,
    wait_ms: int,
    sort_control_mode: str = "set",
) -> None:
    if str(retailer or "").strip().lower() != "chewy":
        return
    sort_label = _chewy_sort_label(sort_mode)
    if not sort_label:
        return
    mode = str(sort_control_mode or "set").strip().lower()
    if mode == "ignore":
        return
    if mode == "verify":
        if not _verify_chewy_sort_option(page, sort_label):
            current_label = _current_chewy_sort_label(page)
            raise ListingStatePreparationError(
                "Chewy Sort By widget is not set to "
                f"{sort_label}; current widget value is {current_label or 'unknown'}"
            )
        page.wait_for_timeout(max(1_000, min(int(wait_ms or 0), 3_000)))
        return
    if not _select_chewy_sort_option(page, sort_label):
        current_label = _current_chewy_sort_label(page)
        raise ListingStatePreparationError(
            "Unable to verify Chewy Sort By widget "
            f"as {sort_label}; current widget value is {current_label or 'unknown'}"
        )
    page.wait_for_timeout(max(1_000, min(int(wait_ms or 0), 3_000)))


def _chewy_sort_label(sort_mode: str | None) -> str | None:
    mode = str(sort_mode or "").strip().lower()
    return {
        "newest": "Newest",
        "best_selling": "Bestselling",
        "best_sellers": "Bestselling",
        "bestselling": "Bestselling",
        "most_popular": "Bestselling",
    }.get(mode)


def _verify_chewy_sort_option(page: Page, sort_label: str) -> bool:
    if not _wait_for_chewy_sort_control(
        page, timeout_ms=_CHEWY_SORT_CONTROL_TIMEOUT_MS
    ):
        LOGGER.warning("Chewy Sort By widget did not appear for manual verification.")
        return False
    current_label = _current_chewy_sort_label(page)
    if current_label == sort_label:
        LOGGER.info("Verified Chewy Sort By widget is %s", sort_label)
        return True
    LOGGER.warning(
        "Chewy Sort By widget verification failed: expected %s but current value is %s",
        sort_label,
        current_label or "unknown",
    )
    return False


def _select_chewy_sort_option(
    page: Page,
    sort_label: str,
    *,
    control_timeout_ms: int = _CHEWY_SORT_CONTROL_TIMEOUT_MS,
) -> bool:
    if not _wait_for_chewy_sort_control(page, timeout_ms=control_timeout_ms):
        LOGGER.warning(
            "Chewy Sort By widget did not appear within %d ms.",
            control_timeout_ms,
        )
        return False
    current_label = _current_chewy_sort_label(page)
    if current_label == sort_label:
        LOGGER.info("Chewy Sort By widget already set to %s", sort_label)
        return True
    if _select_chewy_sort_with_native_select(page, sort_label):
        LOGGER.info("Set Chewy Sort By widget to %s", sort_label)
        return True
    if _select_chewy_sort_with_keyboard(page, sort_label):
        LOGGER.info(
            "Set Chewy Sort By widget to %s using keyboard fallback", sort_label
        )
        return True
    if _select_chewy_sort_with_dom_event(page, sort_label):
        LOGGER.info(
            "Set Chewy Sort By widget to %s using DOM event fallback", sort_label
        )
        return True
    if _select_chewy_sort_with_radio_sheet(page, sort_label):
        LOGGER.info(
            "Set Chewy Sort By widget to %s using Sort sheet fallback", sort_label
        )
        return True
    LOGGER.warning(
        "Unable to set Chewy Sort By widget to %s; current widget value is %s",
        sort_label,
        _current_chewy_sort_label(page) or "unknown",
    )
    return False


def _wait_for_chewy_sort_control(page: Page, *, timeout_ms: int) -> bool:
    if _current_chewy_sort_label(page) is not None:
        return True
    if _chewy_sort_button_available(page):
        return True
    selector = _CHEWY_SORT_SELECTORS[0]
    try:
        page.wait_for_selector(selector, state="attached", timeout=max(0, timeout_ms))
        return True
    except (
        PlaywrightError,
        PlaywrightTimeoutError,
        RuntimeError,
        AttributeError,
        TypeError,
    ) as exc:
        LOGGER.info("Chewy Sort By widget not ready yet: %s", exc)
        return (
            _current_chewy_sort_label(page) is not None
            or _chewy_sort_button_available(page)
        )


def _chewy_sort_button_available(page: Page) -> bool:
    try:
        return (
            _first_visible_enabled_locator(
                page.get_by_role("button", name=re.compile(r"^Sort$", re.IGNORECASE))
            )
            is not None
        )
    except (
        PlaywrightError,
        PlaywrightTimeoutError,
        RuntimeError,
        AttributeError,
        TypeError,
    ):
        return False


def _current_chewy_sort_label(page: Page) -> str | None:
    try:
        result = page.evaluate(
            """
            () => {
              const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const selects = Array.from(document.querySelectorAll('select'))
                .filter((select) => {
                  const labels = Array.from(select.options || []).map((option) => clean(option.textContent));
                  return labels.includes('Newest') && labels.includes('Bestselling');
                });
              const select = selects[0];
              if (select) {
                const selected = select.selectedOptions && select.selectedOptions[0];
                const option = selected || Array.from(select.options || []).find((item) => item.value === select.value);
                const label = clean(option && option.textContent);
                if (label) return label;
              }
              const labelForInput = (input) => {
                const values = [];
                if (input.getAttribute('aria-label')) values.push(input.getAttribute('aria-label'));
                if (input.id) {
                  const explicit = document.querySelector(`label[for="${CSS.escape(input.id)}"]`);
                  if (explicit) values.push(explicit.textContent);
                }
                const label = input.closest('label');
                if (label) values.push(label.textContent);
                const parent = input.parentElement;
                if (parent) values.push(parent.textContent);
                const next = input.nextElementSibling;
                if (next) values.push(next.textContent);
                return values.map(clean).find((value) => ['Relevance', 'Newest', 'Bestselling'].includes(value)) || '';
              };
              const checkedInput = Array.from(document.querySelectorAll('input[type="radio"]:checked'))
                .find((input) => ['Relevance', 'Newest', 'Bestselling'].includes(labelForInput(input)));
              if (checkedInput) return labelForInput(checkedInput);
              const checkedRole = Array.from(document.querySelectorAll('[role="radio"][aria-checked="true"]'))
                .find((item) => ['Relevance', 'Newest', 'Bestselling'].includes(clean(item.textContent || item.getAttribute('aria-label'))));
              if (checkedRole) return clean(checkedRole.textContent || checkedRole.getAttribute('aria-label'));
              return null;
            }
            """
        )
    except (
        Exception
    ) as exc:  # noqa: BLE001 - page scripts can be transiently unavailable
        LOGGER.info("Unable to read Chewy sort option: %s", exc)
        return None
    label = str(result or "").strip()
    return label or None


def _select_chewy_sort_with_native_select(page: Page, sort_label: str) -> bool:
    target_value = _CHEWY_SORT_LABEL_TO_VALUE.get(sort_label)
    if not target_value:
        return False
    for selector in _CHEWY_SORT_SELECTORS:
        try:
            locator = page.locator(selector)
            if locator.count() <= 0:
                continue
            sort_select = locator.nth(0)
            sort_select.scroll_into_view_if_needed(timeout=2_000)
            sort_select.select_option(value=target_value, timeout=5_000)
            page.wait_for_timeout(500)
            if _wait_for_chewy_sort_label(page, sort_label, timeout_ms=3_000):
                return True
        except (
            PlaywrightError,
            PlaywrightTimeoutError,
            RuntimeError,
            AttributeError,
            TypeError,
        ) as exc:
            LOGGER.info(
                "Unable to select Chewy sort option %s with selector %s: %s",
                sort_label,
                selector,
                exc,
            )
    return False


def _select_chewy_sort_with_keyboard(page: Page, sort_label: str) -> bool:
    option_index = _CHEWY_SORT_LABEL_TO_INDEX.get(sort_label)
    if option_index is None:
        return False
    for selector in _CHEWY_SORT_SELECTORS:
        try:
            locator = page.locator(selector)
            if locator.count() <= 0:
                continue
            sort_select = locator.nth(0)
            sort_select.scroll_into_view_if_needed(timeout=2_000)
            sort_select.focus(timeout=2_000)
            page.keyboard.press("Home")
            for _index in range(option_index):
                page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")
            page.wait_for_timeout(500)
            if _wait_for_chewy_sort_label(page, sort_label, timeout_ms=3_000):
                return True
        except (
            PlaywrightError,
            PlaywrightTimeoutError,
            RuntimeError,
            AttributeError,
            TypeError,
        ) as exc:
            LOGGER.info(
                "Unable to select Chewy sort option %s with keyboard fallback on %s: %s",
                sort_label,
                selector,
                exc,
            )
    return False


def _select_chewy_sort_with_dom_event(page: Page, sort_label: str) -> bool:
    target_value = _CHEWY_SORT_LABEL_TO_VALUE.get(sort_label)
    if not target_value:
        return False
    try:
        changed = page.evaluate(
            """
            (targetValue) => {
              const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const select = Array.from(document.querySelectorAll('select'))
                .find((item) => {
                  const labels = Array.from(item.options || [])
                    .map((option) => clean(option.textContent));
                  return labels.includes('Newest') && labels.includes('Bestselling');
                });
              if (!select) return false;
              select.value = targetValue;
              select.dispatchEvent(new Event('input', {bubbles: true}));
              select.dispatchEvent(new Event('change', {bubbles: true}));
              return select.value === targetValue;
            }
            """,
            target_value,
        )
        if not changed:
            return False
        page.wait_for_timeout(500)
        return _wait_for_chewy_sort_label(page, sort_label, timeout_ms=3_000)
    except (
        PlaywrightError,
        PlaywrightTimeoutError,
        RuntimeError,
        AttributeError,
        TypeError,
    ) as exc:
        LOGGER.info(
            "Unable to select Chewy sort option %s with DOM event fallback: %s",
            sort_label,
            exc,
        )
        return False


def _select_chewy_sort_with_radio_sheet(page: Page, sort_label: str) -> bool:
    try:
        sort_button = _first_visible_enabled_locator(
            page.get_by_role("button", name=re.compile(r"^Sort$", re.IGNORECASE))
        )
        if sort_button is None:
            sort_button = _first_visible_enabled_locator(
                page.locator(
                    "button, [role='button']",
                    has_text=re.compile(r"^\\s*Sort\\s*$", re.IGNORECASE),
                )
            )
        if sort_button is None:
            return False
        sort_button.click(timeout=5_000)
        page.wait_for_timeout(500)
        radio = _first_visible_enabled_locator(
            page.get_by_role("radio", name=sort_label)
        )
        target_value = _CHEWY_SORT_LABEL_TO_VALUE.get(sort_label)
        if radio is None and target_value:
            radio = _first_visible_enabled_locator(
                page.locator(f"input[type='radio'][value='{target_value}']")
            )
        if radio is None:
            return False
        radio.click(timeout=5_000)
        page.wait_for_timeout(500)
        close_button = _first_visible_enabled_locator(
            page.get_by_role("button", name=re.compile(r"^Close$", re.IGNORECASE))
        )
        if close_button is not None:
            try:
                close_button.click(timeout=2_500)
            except Exception:
                pass
        return _wait_for_chewy_sort_label(page, sort_label, timeout_ms=3_000)
    except (
        PlaywrightError,
        PlaywrightTimeoutError,
        RuntimeError,
        AttributeError,
        TypeError,
    ) as exc:
        LOGGER.info(
            "Unable to select Chewy sort option %s with Sort sheet fallback: %s",
            sort_label,
            exc,
        )
        return False


def _wait_for_chewy_sort_label(
    page: Page,
    sort_label: str,
    *,
    timeout_ms: int,
) -> bool:
    if _current_chewy_sort_label(page) == sort_label:
        return True
    page.wait_for_timeout(min(max(0, int(timeout_ms)), 500))
    return _current_chewy_sort_label(page) == sort_label


def _scroll_collect_candidates(
    page: Page,
    *,
    selector: str,
    retailer: str,
    category_key: str | None,
    scroll_steps: int,
    wait_ms: int,
    max_links: int,
    max_idle_scrolls: int,
    load_more_texts: tuple[str, ...],
) -> list[CandidateLink]:
    def _safe_wait_for_dom() -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except Exception:
            return

    def grab() -> list[CandidateLink]:
        for attempt in range(3):
            try:
                if retailer.lower() == "amazon":
                    raw_items = page.eval_on_selector_all(
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
                elif retailer.lower() == "chewy":
                    raw_items = page.eval_on_selector_all(
                        "a[href*='/dp/']",
                        (
                            "els => {"
                            "const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();"
                            "const normalizeUrl = (href) => {"
                            "try {"
                            "const url = new URL(href || '', window.location.href);"
                            "if (url.hostname !== 'www.chewy.com') return '';"
                            "if (!/\\/dp\\/\\d+/i.test(url.pathname)) return '';"
                            "url.search = '';"
                            "url.hash = '';"
                            "return url.toString();"
                            "} catch { return ''; }"
                            "};"
                            "const titleScore = (value) => {"
                            "const text = clean(value);"
                            "if (!text || /^slide\\s+\\d+\\s+of\\s+\\d+$/i.test(text)) return -1000;"
                            "return text.includes('...') ? text.length - 500 : text.length;"
                            "};"
                            "return els.filter(el => {"
                            "const href = el.href || el.getAttribute('href') || '';"
                            "if (!normalizeUrl(href) || /\\/api\\/event\\//i.test(href)) return false;"
                            "if (!el.querySelector('h2')) return false;"
                            "const title = clean(el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '');"
                            "if (!title || /^slide\\s+\\d+\\s+of\\s+\\d+$/i.test(title)) return false;"
                            "return true;"
                            "}).map(el => {"
                            "let sponsored = false;"
                            "let node = el;"
                            "for (let depth = 0; node && depth < 8; depth += 1) {"
                            "const nodeRect = node.getBoundingClientRect ? node.getBoundingClientRect() : null;"
                            "const text = clean(node.innerText || node.textContent || '');"
                            "const bounded = nodeRect && nodeRect.width > 0 && nodeRect.height > 0 && "
                            "nodeRect.height < 650 && nodeRect.width < window.innerWidth * 0.98;"
                            "if (bounded && /\\bSponsored\\b/i.test(text)) {"
                            "sponsored = true;"
                            "break;"
                            "}"
                            "node = node.parentElement;"
                            "}"
                            "let title = clean(el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '');"
                            "const card = el.closest(\"article, li, [data-testid*='product'], [class*='product'], [class*='card']\");"
                            "const img = card ? card.querySelector('img[alt]') : el.querySelector('img[alt]');"
                            "const alt = img ? clean((img.getAttribute('alt') || '').replace(/\\s+slide\\s+\\d+\\s+of\\s+\\d+$/i, '')) : '';"
                            "if (titleScore(alt) > titleScore(title)) {"
                            "title = alt;"
                            "}"
                            "return {"
                            "url: normalizeUrl(el.href || el.getAttribute('href') || ''),"
                            "title,"
                            "isSponsored: sponsored,"
                            "isBeforeSortControl: false"
                            "};"
                            "}).filter(item => item.url);"
                            "}"
                        ),
                    )
                else:
                    raw_items = page.eval_on_selector_all(
                        selector,
                        (
                            "els => els.map(el => ({"
                            "url: el.href || el.getAttribute('href') || '',"
                            "title: ((el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '')).trim()"
                            "})).filter(item => item.url)"
                        ),
                    )
                return [
                    CandidateLink(
                        url=str(item.get("url") or "").strip(),
                        title=(" ".join(str(item.get("title") or "").split()) or None),
                        is_sponsored=bool(item.get("isSponsored")),
                        is_before_sort_control=bool(item.get("isBeforeSortControl")),
                    )
                    for item in raw_items
                    if str(item.get("url") or "").strip()
                ]
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
        return []

    links: list[CandidateLink] = []
    seen: set[str] = set()

    def ingest(items: list[CandidateLink]) -> int:
        added = 0
        for item in items:
            href = str(item.url or "").strip()
            if not href or href in seen:
                continue
            seen.add(href)
            links.append(
                CandidateLink(
                    url=href,
                    title=item.title,
                    is_sponsored=item.is_sponsored,
                    is_before_sort_control=item.is_before_sort_control,
                )
            )
            added += 1
        return added

    LOGGER.info(
        "Collecting candidate links for %s / %s...",
        retailer,
        category_key or "unknown-category",
    )
    ingest(grab())
    if max_links and len(links) >= max_links:
        return links[:max_links]

    idle_steps = 0
    for idx in range(max(scroll_steps, 0)):
        before_count = len(links)
        if load_more_texts:
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                page.mouse.wheel(0, 3200)
            page.wait_for_timeout(min(wait_ms, 1_500) if wait_ms > 0 else 0)
        else:
            page.mouse.wheel(0, 3200)
            page.wait_for_timeout(wait_ms // 2 if wait_ms > 1 else 0)
            page.mouse.wheel(0, -1800)
            page.wait_for_timeout(wait_ms - wait_ms // 2 if wait_ms > 1 else 0)
        ingest(grab())
        new_this_step = len(links) - before_count
        clicked_load_more = False
        if load_more_texts and _click_load_more_if_available(
            page, load_more_texts=load_more_texts
        ):
            clicked_load_more = True
            before_click_count = len(links)
            click_new = _wait_for_candidate_growth(
                page,
                grab=grab,
                ingest=ingest,
                links=links,
                before_count=before_click_count,
                wait_ms=wait_ms,
            )
            new_this_step += click_new
            LOGGER.info(
                "After load-more click, %s candidate links=%d (new from click=%d)",
                retailer,
                len(links),
                click_new,
            )
        if new_this_step == 0:
            idle_steps += 1
        else:
            idle_steps = 0
        LOGGER.info(
            "After scroll %d, %s candidate links=%d (new=%d idle=%d/%d)",
            idx + 1,
            retailer,
            len(links),
            new_this_step,
            idle_steps,
            max_idle_scrolls,
        )
        if max_links and len(links) >= max_links:
            return links[:max_links]
        if load_more_texts and not clicked_load_more:
            if not _load_more_available(page, load_more_texts=load_more_texts):
                break
        if max_idle_scrolls > 0 and idle_steps >= max_idle_scrolls:
            break
    return links


def _click_next_listing_page(
    page: Page,
    *,
    retailer: str,
    timeout_ms: int,
) -> str | None:
    retailer_lower = str(retailer or "").strip().lower()
    locators: tuple[Locator, ...]
    if retailer_lower == "chewy":
        locators = (
            page.get_by_role(
                "link", name=re.compile(r"^\\s*Next Page\\s*$", re.IGNORECASE)
            ),
            page.get_by_role("link", name=re.compile(r"^\\s*Next\\s*$", re.IGNORECASE)),
            page.locator("a[aria-label*='Next' i][href*='page=']"),
        )
    else:
        locators = (
            page.get_by_role("link", name=re.compile(r"next", re.IGNORECASE)),
            page.locator("a[rel='next'], a[aria-label*='Next' i]"),
        )
    for locator in locators:
        target = _first_visible_enabled_locator(locator)
        if target is None:
            continue
        before_url = str(page.url or "")
        try:
            target.scroll_into_view_if_needed(timeout=2_000)
        except Exception:
            pass
        try:
            with page.expect_navigation(
                wait_until="domcontentloaded",
                timeout=max(1_000, timeout_ms),
            ):
                target.click(timeout=5_000)
        except PlaywrightTimeoutError:
            LOGGER.info("Next-page click did not produce a load-state event.")
        except Exception as exc:  # noqa: BLE001 - click may still have changed SPA state
            LOGGER.info("Next-page click failed: %s", exc)
            try:
                target.evaluate(
                    """(el) => {
                        el.scrollIntoView({block: 'center', inline: 'center'});
                        el.click();
                    }"""
                )
            except Exception:
                continue
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(750)
        except Exception:
            pass
        after_url = str(page.url or "")
        if after_url and after_url != before_url:
            LOGGER.info("Advanced listing page from %s to %s", before_url, after_url)
            return after_url
    return None


def _wait_for_candidate_growth(
    page: Page,
    *,
    grab,
    ingest,
    links: list[CandidateLink],
    before_count: int,
    wait_ms: int,
) -> int:
    deadline = time.monotonic() + (max(wait_ms, 0) / 1000.0)
    while True:
        remaining_ms = int(max(0.0, (deadline - time.monotonic()) * 1000))
        if remaining_ms <= 0:
            break
        page.wait_for_timeout(min(1_000, remaining_ms))
        ingest(grab())
        current_count = len(links)
        if current_count > before_count:
            return current_count - before_count
    return 0


def _load_more_available(
    page: Page,
    *,
    load_more_texts: tuple[str, ...],
) -> bool:
    for raw_text in load_more_texts:
        text = str(raw_text or "").strip()
        if not text:
            continue
        candidates = (
            page.get_by_role("button", name=re.compile(re.escape(text), re.IGNORECASE)),
            page.locator(
                "button, a, [role='button']",
                has_text=re.compile(re.escape(text), re.IGNORECASE),
            ),
        )
        for locator in candidates:
            if _first_visible_enabled_locator(locator) is not None:
                return True
    return False


def _click_load_more_if_available(
    page: Page,
    *,
    load_more_texts: tuple[str, ...],
) -> bool:
    for raw_text in load_more_texts:
        text = str(raw_text or "").strip()
        if not text:
            continue
        candidates = (
            page.get_by_role("button", name=re.compile(re.escape(text), re.IGNORECASE)),
            page.locator(
                "button, a, [role='button']",
                has_text=re.compile(re.escape(text), re.IGNORECASE),
            ),
        )
        for locator in candidates:
            target = _first_visible_enabled_locator(locator)
            if target is None:
                continue
            try:
                target.scroll_into_view_if_needed(timeout=2_000)
            except Exception:
                pass
            try:
                target.click(timeout=2_500)
                return True
            except Exception:
                pass
            try:
                target.evaluate(
                    """(el) => {
                        el.scrollIntoView({block: 'center', inline: 'center'});
                        el.click();
                    }"""
                )
                return True
            except Exception:
                continue
    return False


def _first_visible_enabled_locator(locator: Locator) -> Locator | None:
    try:
        count = locator.count()
    except Exception:
        return None
    for index in range(count):
        try:
            candidate = locator.nth(index)
            if not candidate.is_visible():
                continue
            if not candidate.is_enabled():
                continue
            return candidate
        except Exception:
            continue
    return None
