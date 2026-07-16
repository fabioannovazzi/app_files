from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect the current page in an attached Chrome CDP session.",
    )
    parser.add_argument(
        "--remote-url",
        default="http://localhost:9222",
        help="Chrome DevTools endpoint.",
    )
    parser.add_argument(
        "--url-contains",
        default="",
        help="Prefer an open tab whose URL contains this text.",
    )
    parser.add_argument(
        "--selector",
        default="a[href*='/dp/']",
        help="Primary selector to count and sample.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=2_000,
        help="Milliseconds to wait before inspecting the tab.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/pdp/cdp_debug"),
        help="Directory for screenshot, HTML, and diagnosis JSON.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level.",
    )
    return parser.parse_args(argv)


def _select_page(pages: Sequence[Page], url_contains: str) -> Page:
    needle = str(url_contains or "").strip().lower()
    if needle:
        for page in pages:
            if needle in str(page.url or "").lower():
                return page
    if not pages:
        raise RuntimeError("No open tabs are exposed by the CDP session.")
    return pages[0]


def _sample_links(page: Page, selector: str) -> list[dict[str, str]]:
    raw_items = page.eval_on_selector_all(
        selector,
        (
            "els => els.slice(0, 20).map(el => ({"
            "href: el.href || el.getAttribute('href') || '',"
            "text: (el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim()"
            "}))"
        ),
    )
    links: list[dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        links.append(
            {
                "href": str(item.get("href") or ""),
                "text": " ".join(str(item.get("text") or "").split()),
            }
        )
    return links


def _build_diagnosis(page: Page, selector: str) -> dict[str, Any]:
    body_text = " ".join(str(page.text_content("body") or "").split())
    return {
        "url": page.url,
        "title": page.title(),
        "selector": selector,
        "selector_count": page.locator(selector).count(),
        "all_link_count": page.locator("a[href]").count(),
        "body_text_length": len(body_text),
        "body_text_sample": body_text[:2_000],
        "sample_links": _sample_links(page, selector),
    }


def _write_outputs(page: Page, diagnosis: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "diagnosis.json").write_text(
        json.dumps(diagnosis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "page.html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=output_dir / "screenshot.png", full_page=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(message)s",
    )

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(args.remote_url)
        contexts = browser.contexts
        pages = [page for context in contexts for page in context.pages]
        page = _select_page(pages, args.url_contains)
        if args.wait_ms > 0:
            page.wait_for_timeout(args.wait_ms)
        diagnosis = _build_diagnosis(page, str(args.selector))
        _write_outputs(page, diagnosis, args.output_dir)
    finally:
        # Do not close the connected browser; this is the user's visible Chrome.
        playwright.stop()

    LOGGER.info("URL: %s", diagnosis["url"])
    LOGGER.info("TITLE: %s", diagnosis["title"])
    LOGGER.info("SELECTOR_COUNT: %s", diagnosis["selector_count"])
    LOGGER.info("ANY_LINKS: %s", diagnosis["all_link_count"])
    LOGGER.info("BODY_TEXT_LENGTH: %s", diagnosis["body_text_length"])
    LOGGER.info("BODY_TEXT_SAMPLE: %s", diagnosis["body_text_sample"][:500])
    LOGGER.info("WROTE: %s", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
