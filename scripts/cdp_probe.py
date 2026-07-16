from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.sync_api import sync_playwright

LOGGER = logging.getLogger(__name__)

__all__ = ["collect_pdp_links", "fetch_pdp_html", "main"]


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe PDP fetching via a visible Chrome (CDP) session.",
    )
    parser.add_argument(
        "--remote-url",
        default="http://localhost:9222",
        help="Chrome DevTools endpoint (start Chrome with --remote-debugging-port to expose it).",
    )
    parser.add_argument(
        "--category-url",
        required=True,
        help="Category/PLP URL to open in the visible browser.",
    )
    parser.add_argument(
        "--selector",
        default=(
            "a[data-at='product_link'], "
            "a[href*='/product/'], "
            "a[href*='/pimprod'], "
            "a[href*='/dp/'], "
            "a[href*='/gp/product/']"
        ),
        help="CSS selector used to collect PDP links from the category page.",
    )
    parser.add_argument(
        "--scroll-steps",
        type=int,
        default=8,
        help="How many scroll passes to run on the category page before collecting links.",
    )
    parser.add_argument(
        "--pdp-limit",
        type=int,
        default=3,
        help="Maximum number of PDPs to fetch for this probe.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/pdp/cdp_probe"),
        help="Where to write fetched PDP HTML snapshots.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Navigation timeout for Playwright operations (milliseconds).",
    )
    parser.add_argument(
        "--reuse-open-tab",
        action="store_true",
        help="Reuse the first existing page in the attached Chrome context (no new navigation).",
    )
    parser.add_argument(
        "--no-navigation",
        action="store_true",
        help="Do not navigate; operate on the existing tab as-is (requires --reuse-open-tab).",
    )
    return parser.parse_args(argv)


def _get_context(remote_url: str) -> tuple[object, Browser, BrowserContext, bool]:
    playwright = sync_playwright().start()
    browser = playwright.chromium.connect_over_cdp(remote_url)
    if browser.contexts:
        return playwright, browser, browser.contexts[0], False
    return playwright, browser, browser.new_context(), True


def _close_probe_session(
    playwright: object | None,
    browser: Browser | None,
    context: BrowserContext | None,
    created_context: bool,
) -> None:
    try:
        if created_context and context is not None:
            context.close()
    except Exception:
        pass
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


def _reconnect_probe_context(
    *,
    remote_url: str,
    playwright: object | None,
    browser: Browser | None,
    context: BrowserContext | None,
    created_context: bool,
) -> tuple[object, Browser, BrowserContext, bool]:
    _close_probe_session(playwright, browser, context, created_context)
    return _get_context(remote_url)


def _goto_best_effort(page: Page, url: str, timeout_ms: int) -> bool:
    """Navigate with a tolerant wait strategy. Returns True on success."""
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        LOGGER.info(
            "Network-idle wait timed out for %s; retrying with DOM content.", url
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic for flaky geo pages
        LOGGER.info("Navigation error for %s: %s", url, exc)
        return False
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        return True
    except Exception as exc:  # noqa: BLE001 - diagnostic for flaky geo pages
        LOGGER.info("Secondary navigation error for %s: %s", url, exc)
        return False


def _handle_sephora_interstitial(page: Page, target_url: str, timeout_ms: int) -> None:
    """Click through Sephora's geo banner if present, then reload target."""
    if "sephora.com" not in target_url.lower():
        return
    clicked = False
    try:
        for text in (
            "Continue to Sephora.com.",
            "Continue to Sephora.com",
            "Continue to Sephora.com ",
        ):
            try:
                page.get_by_text(text, exact=False).click(timeout=1200)
                clicked = True
                break
            except PlaywrightTimeoutError:
                continue
        if clicked:
            page.wait_for_timeout(800)
            _goto_best_effort(page, target_url, timeout_ms)
    except PlaywrightTimeoutError:
        return
    except Exception:
        return


def _dismiss_sephora_banner(page: Page, target_url: str, timeout_ms: int) -> None:
    """Best-effort close of Sephora overlay without changing page."""
    if "sephora.com" not in target_url.lower():
        return
    try:
        # Prefer a close/X button to avoid homepage redirect.
        for selector in (
            "button[aria-label*='Close' i]",
            "button[aria-label='Close']",
            "[data-at='closeButton']",
        ):
            try:
                page.wait_for_timeout(200)
                element = page.query_selector(selector)
                if element:
                    element.click(timeout=1200)
                    return
            except Exception:
                continue
        # Fallback: click Continue and reload target.
        _handle_sephora_interstitial(page, target_url, timeout_ms)
    except Exception:
        return


def _prepare_page_for_url(page: Page, target_url: str, timeout_ms: int) -> bool:
    """Open the target URL and handle the Sephora interstitial in-place."""
    success = _goto_best_effort(page, target_url, timeout_ms)
    if success and "sephora.com" in target_url.lower():
        _dismiss_sephora_banner(page, target_url, timeout_ms)
    return success


def _scroll_and_maybe_click(page: Page, scroll_steps: int, timeout_ms: int) -> None:
    for _ in range(max(scroll_steps, 0)):
        page.mouse.wheel(0, 3200)
        page.wait_for_timeout(800)
        try:
            page.get_by_text("Load more", exact=False).click(timeout=1500)
        except PlaywrightTimeoutError:
            continue


def _collect_links_with_scrolling(
    page: Page,
    selector: str,
    *,
    scroll_steps: int,
    timeout_ms: int,
    target_limit: int | None = None,
) -> list[str]:
    """Collect links, stopping early once the target limit is reached."""

    def _grab() -> list[str]:
        return page.eval_on_selector_all(
            selector, "els => [...new Set(els.map(e => e.href))]"
        )

    LOGGER.info("Collecting links (initial pass)...")
    seen: list[str] = []
    seen_set: set[str] = set()

    for href in _grab():
        if href not in seen_set:
            seen.append(href)
            seen_set.add(href)
    LOGGER.info("Initial links collected: %d", len(seen))
    if not seen:
        LOGGER.info("Initial selector yielded no links (selector=%s)", selector)
    if target_limit and len(seen) >= target_limit:
        return seen

    if scroll_steps and (target_limit is None or len(seen) < target_limit):
        LOGGER.info("Scrolling for more links (up to %s steps)...", scroll_steps)

    for idx in range(max(scroll_steps, 0)):
        _scroll_and_maybe_click(page, 1, timeout_ms)
        page.wait_for_timeout(1200)
        for href in _grab():
            if href not in seen_set:
                seen.append(href)
                seen_set.add(href)
        LOGGER.info("After scroll %d, total links: %d", idx + 1, len(seen))
        if target_limit and len(seen) >= target_limit:
            break
    return seen


def collect_pdp_links(
    context: BrowserContext,
    category_url: str,
    selector: str,
    *,
    scroll_steps: int,
    timeout_ms: int,
    target_limit: int | None = None,
) -> list[str]:
    """Open a category URL in the visible browser and return discovered PDP links."""
    page = context.new_page()
    try:
        _prepare_page_for_url(page, category_url, timeout_ms)
        try:
            page.wait_for_selector(selector, timeout=timeout_ms)
        except Exception:
            LOGGER.info(
                "Selector %s not found within timeout; continuing anyway.", selector
            )
        return _collect_links_with_scrolling(
            page,
            selector,
            scroll_steps=scroll_steps,
            timeout_ms=timeout_ms,
            target_limit=target_limit,
        )
    finally:
        page.close()


def fetch_pdp_html(
    context: BrowserContext, url: str, *, timeout_ms: int
) -> tuple[int, dict[str, str], str]:
    """Navigate to a PDP in the visible browser and return (status, headers, html)."""
    page = context.new_page()
    try:
        if "sephora.com" in url.lower():
            _prepare_page_for_url(page, url, timeout_ms)
        response = page.goto(
            url, wait_until="networkidle", timeout=timeout_ms, referer=url
        )
        _handle_sephora_interstitial(page, url, timeout_ms)
        if "sephora.com" in url.lower() and url not in (page.url or ""):
            LOGGER.info("Bounce detected when fetching %s; retrying.", url)
            _prepare_page_for_url(page, url, timeout_ms)
            response = page.goto(
                url, wait_until="networkidle", timeout=timeout_ms, referer=url
            )
            _handle_sephora_interstitial(page, url, timeout_ms)
        status = response.status if response is not None else 0
        headers = response.headers if response is not None else {}
        html = page.content()
        return status, headers, html
    finally:
        page.close()


def fetch_pdp_html_inplace(
    page: Page, url: str, *, timeout_ms: int
) -> tuple[int, dict[str, str], str]:
    """Reuse the same tab to fetch a PDP, keeping session state intact."""
    referer = page.url or url
    response = None
    try:
        response = page.goto(
            url, wait_until="networkidle", timeout=timeout_ms, referer=referer
        )
    except PlaywrightTimeoutError:
        LOGGER.info(
            "Network-idle wait timed out for %s; retrying with DOM content.", url
        )
        response = page.goto(
            url, wait_until="domcontentloaded", timeout=timeout_ms, referer=referer
        )

    _handle_sephora_interstitial(page, url, timeout_ms)
    if "sephora.com" in url.lower() and url not in (page.url or ""):
        LOGGER.info("Bounce detected (in-place) for %s; retrying.", url)
        try:
            response = page.goto(
                url, wait_until="networkidle", timeout=timeout_ms, referer=referer
            )
        except PlaywrightTimeoutError:
            response = page.goto(
                url, wait_until="domcontentloaded", timeout=timeout_ms, referer=referer
            )
        _handle_sephora_interstitial(page, url, timeout_ms)

    status = response.status if response is not None else 0
    headers = response.headers if response is not None else {}
    html = page.content()
    return status, headers, html


def _write_html(output_dir: Path, index: int, url: str, html: str) -> Path:
    def _extract_identifier(target_url: str) -> str | None:
        parsed = urlparse(target_url)
        qs = parse_qs(parsed.query)
        sku_id = next((value for value in qs.get("skuId", []) if value), None)
        if sku_id:
            return sku_id
        match_sku = re.search(r"skuId=?([0-9]+)", target_url, flags=re.IGNORECASE)
        if match_sku:
            return match_sku.group(1)
        match = re.search(r"(P\d{4,})", target_url, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        last_segment = parsed.path.rstrip("/").split("/")[-1]
        return last_segment or None

    def _safe_stem(stem: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", stem)
        return cleaned or "pdp"

    identifier = _extract_identifier(url)
    stem = _safe_stem(identifier) if identifier else f"{index:03d}"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{stem}.html"
    if path.exists():
        path = output_dir / f"{stem}_{index:03d}.html"
    path.write_text(f"<!-- {url} -->\n{html}", encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )
    LOGGER.info(
        "Starting probe (reuse_tab=%s, scroll_steps=%s, pdp_limit=%s)",
        args.reuse_open_tab,
        args.scroll_steps,
        args.pdp_limit,
    )

    playwright = None
    browser = None
    context = None
    created_context = False

    try:
        playwright, browser, context, created_context = _get_context(args.remote_url)
    except Exception as exc:  # noqa: BLE001 - surfaced for CLI usage
        LOGGER.error("Failed to connect to Chrome at %s: %s", args.remote_url, exc)
        return 1

    try:
        base_page = context.pages[0] if args.reuse_open_tab and context.pages else None
        if base_page is not None and base_page.is_closed():
            LOGGER.info("Reused tab is closed; opening a new tab instead.")
            base_page = None

        def _refresh_reused_page() -> Page | None:
            candidate = (
                context.pages[0] if args.reuse_open_tab and context.pages else None
            )
            if candidate is not None and candidate.is_closed():
                return None
            return candidate

        links: list[str]
        if args.no_navigation and not base_page:
            LOGGER.error(
                "--no-navigation requires an existing tab (use --reuse-open-tab with the tab on the category)."
            )
            return 1

        if base_page is not None and not args.no_navigation:
            try:
                LOGGER.info("Reusing existing tab: %s", base_page.url)
                LOGGER.info("Navigating reused tab to category: %s", args.category_url)
                ok = _prepare_page_for_url(
                    base_page, args.category_url, args.timeout_ms
                )
                if not ok:
                    LOGGER.info(
                        "Reused tab navigation did not succeed; opening a new tab."
                    )
                    base_page = None
            except Exception as exc:  # noqa: BLE001 - defensive; fall back to fresh tab
                LOGGER.info(
                    "Reused tab navigation failed (%s); opening a new tab.", exc
                )
                base_page = None

        if base_page is None:
            LOGGER.info("Collecting PDP links from %s", args.category_url)
            try:
                links = collect_pdp_links(
                    context,
                    args.category_url,
                    args.selector,
                    scroll_steps=args.scroll_steps,
                    timeout_ms=args.timeout_ms,
                    target_limit=args.pdp_limit,
                )
            except Exception as exc:
                if not _is_closed_target_error(exc):
                    raise
                LOGGER.warning(
                    "CDP context closed while collecting links; reconnecting and retrying once."
                )
                (
                    playwright,
                    browser,
                    context,
                    created_context,
                ) = _reconnect_probe_context(
                    remote_url=args.remote_url,
                    playwright=playwright,
                    browser=browser,
                    context=context,
                    created_context=created_context,
                )
                base_page = _refresh_reused_page()
                if args.no_navigation and base_page is None:
                    LOGGER.error(
                        "No existing tab available after reconnect in no-navigation mode."
                    )
                    return 1
                if base_page is None:
                    links = collect_pdp_links(
                        context,
                        args.category_url,
                        args.selector,
                        scroll_steps=args.scroll_steps,
                        timeout_ms=args.timeout_ms,
                        target_limit=args.pdp_limit,
                    )
                else:
                    links = _collect_links_with_scrolling(
                        base_page,
                        args.selector,
                        scroll_steps=args.scroll_steps,
                        timeout_ms=args.timeout_ms,
                        target_limit=args.pdp_limit,
                    )
        else:
            if args.no_navigation:
                LOGGER.info(
                    "Reusing existing tab without navigation (no-navigation mode)."
                )
            links = _collect_links_with_scrolling(
                base_page,
                args.selector,
                scroll_steps=args.scroll_steps,
                timeout_ms=args.timeout_ms,
                target_limit=args.pdp_limit,
            )

        LOGGER.info("Found %d candidate PDP links", len(links))
        if not links:
            LOGGER.info(
                "No links found; ensure the tab is on a category page with products visible."
            )
            return 0

        limited_links: list[str] = list(links[: args.pdp_limit])
        for idx, link in enumerate(limited_links, start=1):
            LOGGER.info("Link %d: %s", idx, link)

        for idx, url in enumerate(limited_links, start=1):
            LOGGER.info("Fetching PDP %d/%d: %s", idx, len(limited_links), url)
            fetch_error: Exception | None = None
            status = 0
            headers: dict[str, str] = {}
            html = ""
            for attempt in range(2):
                try:
                    if base_page is not None:
                        status, headers, html = fetch_pdp_html_inplace(
                            base_page,
                            url,
                            timeout_ms=args.timeout_ms,
                        )
                        try:
                            base_page.go_back(timeout=args.timeout_ms)
                            base_page.wait_for_timeout(500)
                        except PlaywrightTimeoutError:
                            LOGGER.info(
                                "go_back timed out after fetching %s; staying on current page.",
                                url,
                            )
                    else:
                        status, headers, html = fetch_pdp_html(
                            context,
                            url,
                            timeout_ms=args.timeout_ms,
                        )
                    fetch_error = None
                    break
                except Exception as exc:  # noqa: BLE001 - surfaced for CLI usage
                    if attempt == 0 and _is_closed_target_error(exc):
                        LOGGER.warning(
                            "CDP context closed while fetching %s; reconnecting and retrying once.",
                            url,
                        )
                        (
                            playwright,
                            browser,
                            context,
                            created_context,
                        ) = _reconnect_probe_context(
                            remote_url=args.remote_url,
                            playwright=playwright,
                            browser=browser,
                            context=context,
                            created_context=created_context,
                        )
                        base_page = _refresh_reused_page()
                        if args.no_navigation and base_page is None:
                            fetch_error = RuntimeError(
                                "No existing tab available after reconnect in no-navigation mode."
                            )
                            break
                        continue
                    fetch_error = exc
                    break
            if fetch_error is not None:
                LOGGER.warning("Failed to fetch %s: %s", url, fetch_error)
                continue
            path = _write_html(args.output_dir, idx, url, html)
            LOGGER.info("Saved HTML (status %s) to %s", status or "?", path)

        return 0
    finally:
        _close_probe_session(playwright, browser, context, created_context)


if __name__ == "__main__":
    sys.exit(main())
