"""Simple HTML fetching with per-user cache."""

import logging
import time

import requests
from bs4 import BeautifulSoup

from modules.utilities.cache import get_cache_dir
from modules.utilities.json_record_store import JsonRecordStore
from modules.utilities.ui_notifier import ui

LOGGER = logging.getLogger(__name__)

_CACHE_DIR = get_cache_dir("vr_cache")
_CACHE_FILE = _CACHE_DIR / "pages.json"
_CACHE_STORE = JsonRecordStore(_CACHE_FILE)


def _init_cache() -> bool:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


_CACHE_ENABLED = _init_cache()


def _cache_get(url: str, max_age_s: int = 86_400) -> str | None:  # default 24 h
    if not _CACHE_ENABLED:
        return None
    row = _CACHE_STORE.get(url)
    if row is None:
        return None
    try:
        fetched = float(row.get("fetched") or 0)
    except (TypeError, ValueError):
        return None
    if time.time() - fetched < max_age_s:
        return str(row.get("text") or "")
    return None


def _cache_put(url: str, text: str) -> None:
    if not _CACHE_ENABLED:
        return
    _CACHE_STORE.upsert(url, {"url": url, "fetched": int(time.time()), "text": text})


def _clean_html(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "lxml")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    return soup.get_text(" ", strip=True)


def fetch_page_text(url: str, timeout: float = 6.0) -> tuple[str | None, int]:
    """
    Returns (text, status_code).  Text is None on network/HTML errors.
    Caches successful fetches.
    """
    cached = _cache_get(url)
    if cached:
        return cached, 200

    try:
        # quick HEAD first
        head = requests.head(url, timeout=timeout, allow_redirects=True)
        if head.status_code >= 400:
            return None, head.status_code

        # small streaming GET so we don't load megabytes into RAM
        resp = requests.get(url, timeout=timeout, stream=True)
        if resp.status_code >= 400:
            return None, resp.status_code

        raw = resp.text[:200_000]  # cap @200 kB
        clean = _clean_html(raw)
        _cache_put(url, clean)
        return clean, resp.status_code

    except requests.RequestException as e:
        LOGGER.warning("fetch_page_cached error: %s", e)
        ui.warning("fetch_page_cached error", error=str(e))
        return None, 599  # pseudo-status “network error”
