from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Mapping

import requests

from .fetcher import DEFAULT_HEADERS, HTMLFetcher
from .models import FetchResult
from .pacing import HumanPacingController

try:  # Playwright may not be installed in minimal envs
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    sync_playwright = None  # type: ignore[assignment]

_logger = logging.getLogger(__name__)


def _load_storage_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - defensive
        _logger.debug("Failed to load storage state from %s: %s", path, exc)
        return {}


def _requests_cookiejar_from_state(state: dict) -> requests.cookies.RequestsCookieJar:
    jar = requests.cookies.RequestsCookieJar()
    for cookie in state.get("cookies", []):
        name = cookie.get("name")
        value = cookie.get("value")
        domain = cookie.get("domain")
        if not (name and value and domain):
            continue
        jar.set(
            name,
            value,
            domain=domain,
            path=cookie.get("path", "/"),
        )
    return jar


class SephoraFetcher(HTMLFetcher):
    """Sephora-only fetcher that falls back to Playwright on 403.

    Strategy:
    1) Try ``requests`` with browser-like headers and any persisted cookies.
    2) If Sephora/Akamai returns 403 or an Access Denied body, retry via
       Playwright (headless Chromium) to acquire valid cookies.
    3) Persist cookies to ``storage_path`` so subsequent ``requests`` calls
       look like a browser session.
    """

    def __init__(
        self,
        *,
        storage_path: Path,
        headers: Mapping[str, str] | None = None,
        proxies: Mapping[str, str] | None = None,
        pacing: HumanPacingController | None = None,
    ) -> None:
        super().__init__(headers=headers, proxies=proxies, pacing=pacing)
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        state = _load_storage_state(self._storage_path)
        self._session.cookies.update(_requests_cookiejar_from_state(state))
        self._proxies = dict(proxies) if proxies else {}

        # Playwright context needs a UA; prefer supplied headers, else default
        self._user_agent = (headers or {}).get("User-Agent", DEFAULT_HEADERS["User-Agent"])

    def fetch(self, url: str, *, timeout: float | tuple[float, float] = 20.0) -> FetchResult:
        if self._pacing is not None:
            self._pacing.wait_before_request()

        response = self._session.get(url, headers=self._headers, timeout=timeout)
        if response.status_code == 403 or "Access Denied" in response.text:
            fallback = self._try_playwright(url, timeout)
            if fallback is not None:
                return fallback
        response.raise_for_status()
        fetched_at = dt.datetime.now(dt.timezone.utc)
        headers = {key: value for key, value in response.headers.items()}
        return FetchResult(
            url=url,
            status_code=response.status_code,
            headers=headers,
            html=response.text,
            fetched_at=fetched_at,
        )

    def _try_playwright(
        self, url: str, timeout: float | tuple[float, float]
    ) -> FetchResult | None:
        if sync_playwright is None:
            _logger.warning("Playwright not available; cannot bypass Sephora 403.")
            return None

        timeout_ms = int(timeout * 1000) if isinstance(timeout, (int, float)) else 20000
        homepage = "https://www.sephora.com/"

        try:
            with sync_playwright() as p:
                browser_kwargs = {"headless": True}
                proxy_server = self._proxies.get("https") or self._proxies.get("http")
                if proxy_server:
                    browser_kwargs["proxy"] = {"server": proxy_server}
                browser = p.chromium.launch(**browser_kwargs)
                context_kwargs = {
                    "user_agent": self._user_agent,
                    "extra_http_headers": dict(self._headers),
                }
                if self._storage_path.exists():
                    context_kwargs["storage_state"] = str(self._storage_path)
                context = browser.new_context(**context_kwargs)
                page = context.new_page()
                # Prime cookies via homepage first to appease Akamai, ignore failures
                try:
                    page.goto(homepage, wait_until="networkidle", timeout=timeout_ms)
                except Exception:  # noqa: BLE001 - best-effort priming
                    pass

                response = page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=timeout_ms,
                    referer=homepage,
                )
                html = page.content()
                fetched_at = dt.datetime.now(dt.timezone.utc)

                # Persist cookies for subsequent requests usage
                context.storage_state(path=str(self._storage_path))
                # Update requests session cookies immediately
                state = _load_storage_state(self._storage_path)
                self._session.cookies.update(_requests_cookiejar_from_state(state))

                headers = {}
                status = 0
                if response is not None:
                    headers = response.headers
                    status = response.status
                else:
                    _logger.warning("Playwright returned no response for %s", url)

                page.close()
                context.close()
                browser.close()

                # Treat Access Denied or HTTP errors as failures so callers can retry/abort
                if status and status >= 400:
                    _logger.warning("Playwright returned HTTP %s for %s", status, url)
                    return None
                if "Access Denied" in html:
                    _logger.warning("Playwright HTML still blocked for %s (Access Denied)", url)
                    return None

                return FetchResult(
                    url=url,
                    status_code=status or 200,
                    headers=headers,
                    html=html,
                    fetched_at=fetched_at,
                )
        except Exception as exc:  # noqa: BLE001 - defensive
            _logger.warning("Playwright fallback failed for %s: %s", url, exc)
            return None


__all__ = ["SephoraFetcher"]
