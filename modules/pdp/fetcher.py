from __future__ import annotations

import datetime as dt
from typing import Mapping

import requests

from .models import FetchResult
from .pacing import HumanPacingController


DEFAULT_HEADERS: Mapping[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class HTMLFetcher:
    """Wrapper around ``requests`` to capture response metadata."""

    def __init__(
        self,
        session: requests.Session | None = None,
        headers: Mapping[str, str] | None = None,
        proxies: Mapping[str, str] | None = None,
        pacing: HumanPacingController | None = None,
    ) -> None:
        self._session = session or requests.Session()
        if proxies:
            self._session.proxies.update(proxies)
        self._headers = dict(DEFAULT_HEADERS)
        if headers:
            self._headers.update(headers)
        self._pacing = pacing

    def fetch(self, url: str, *, timeout: float | tuple[float, float] = 20.0) -> FetchResult:
        if self._pacing is not None:
            self._pacing.wait_before_request()
        response = self._session.get(url, headers=self._headers, timeout=timeout)
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


__all__ = ["DEFAULT_HEADERS", "HTMLFetcher"]
