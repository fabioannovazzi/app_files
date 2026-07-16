# layers.py  (v2 – with throttling, on-disk cache & shared Playwright)

import functools
import hashlib
import html
import io
import json
import logging
import pathlib
import re
import time
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable, List, Optional

import ftfy
import requests
from bs4 import BeautifulSoup
from playwright._impl._errors import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from readability import Document

from modules.pdf_utils.pdf_utils import extract_pdf_rich
from modules.utilities.cache import get_cache_dir
from modules.utilities.ui_notifier import ui

LOGGER = logging.getLogger(__name__)

UA = "Mozilla/5.0 (compatible; LegalScraper/1.0)"
CACHE_DIR = get_cache_dir("page_cache")  # keeps HTML / JS for 24 h

_browser_cache = {"pw": None, "browser": None}

########################################################################
# polite, cached fetch -------------------------------------------------
########################################################################
_last_hit: dict[str, float] = defaultdict(float)


def _to_text(html: str) -> str:
    """Strip boiler-plate tags & collapse whitespace."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def _fetch(url: str, *, max_age_h=24, as_text=True) -> str | bytes:
    """
    • 200 ms politeness gap per domain
    • disk cache (hashed filename) – expires after `max_age_h`
    """
    host = urllib.parse.urlparse(url).hostname or ""
    since = time.time() - _last_hit[host]
    if since < 0.2:
        time.sleep(0.2 - since)

    h = hashlib.sha1(url.encode()).hexdigest()
    f = CACHE_DIR / h
    if f.exists() and time.time() - f.stat().st_mtime < max_age_h * 3600:
        data = f.read_bytes()
    else:
        r = requests.get(url, timeout=15, headers={"User-Agent": UA})
        data = r.content
        f.write_bytes(data)

    _last_hit[host] = time.time()
    return data.decode(errors="ignore") if as_text else data


def _postprocess(txt: str) -> str:
    """
    • de-HTML-entity, fix Unicode cruft (ftfy), collapse whitespace
    • returns a plain UTF-8 string ready for the pipeline
    """
    txt = html.unescape(txt)
    txt = ftfy.fix_text(txt, normalization="NFC")
    return re.sub(r"\s+", " ", txt).strip()


def _readability_extract(html: str) -> str:
    """Return plain text extracted from HTML using readability-lxml.

    Uses readability.Document(html).summary() for boilerplate removal and then
    strips tags with BeautifulSoup/_to_text. No legacy helpers are invoked.
    """
    try:
        frag_html = Document(html).summary() or ""
        return _to_text(frag_html)
    except Exception as e:
        logging.exception(e)
        ui.error("Something went wrong while extracting readability metrics.")
        return ""


########################################################################
# 1. Sanity CMS pattern ------------------------------------------------
########################################################################
def try_sanity(url: str, *, cite: str, **__) -> str | None:
    home = _fetch(url)
    m = re.search(
        r"https://([a-z0-9]{6})\.apicdn\.sanity\.io/.+?/data/query/([^/\"']+)", home
    )
    if not m:
        return None
    proj, dataset = m.groups()
    base = f"https://{proj}.apicdn.sanity.io/v2022-09-09/data/query/{dataset}"

    for field, val in (
        ("cite", cite),
        ("cite", cite.replace("-", ".")),
        ("slug.current", f"ic-{cite}"),
    ):
        q = f'*[_type=="statute" && {field}=="{val}"]{{bodyHtml,sections[]{{ bodyHtml }} }}'
        u = base + "?query=" + urllib.parse.quote(q, safe="")
        data = json.loads(_fetch(u))["result"]
        if data:
            blocks = [b.get("bodyHtml", "") for b in data] + [
                s.get("bodyHtml", "") for b in data for s in b.get("sections", [])
            ]
            soup = BeautifulSoup(html.unescape("".join(blocks)), "lxml")
            return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return None


########################################################################
# 2. generic HTML ------------------------------------------------------
########################################################################


def generic_html(url: str, *, min_len: int = 200, **__) -> str | None:
    if url.lower().endswith(".pdf"):
        return None
    html = _fetch(url)
    if "<html" not in html[:1000].lower():
        return None

    # 1️⃣  readabilipy fast-path
    txt = _readability_extract(html)
    if len(txt) < min_len:
        # 2️⃣  fallback to readability-lxml
        try:
            summary = Document(html).summary()
            txt = _to_text(summary)
        except Exception as e:
            logging.exception(e)
            ui.error("Something went wrong in the validation layer.")
            txt = ""

    if len(txt) < min_len:
        # 3️⃣ simple strip
        soup = BeautifulSoup(html, "lxml")
        for bad in soup(["script", "style", "nav", "footer", "header"]):
            bad.decompose()
        txt = _to_text(str(soup))

    txt = _postprocess(txt)
    return txt if len(txt) >= min_len else None


########################################################################
# 2️⃣  PDF → Markdown (rich)
########################################################################


def try_pdf(url: str, *, timeout: float = 10, max_pages: int = 40, **__) -> str | None:
    if not url.lower().endswith(".pdf"):
        return None

    try:
        resp = requests.get(
            url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True
        )
        resp.raise_for_status()
        if "application/pdf" not in resp.headers.get("Content-Type", ""):
            return None
    except requests.RequestException as e:
        logging.exception(e)
        ui.error("Something went wrong in the validation layer.")
        return None

    try:
        md = extract_pdf_rich(io.BytesIO(resp.content))
        if max_pages is not None:
            pages = md.split("\f")
            md = "\n\n".join(pages[:max_pages])
        return md if md.strip() else None
    except Exception as e:
        logging.exception(e)
        ui.error("Something went wrong in the validation layer.")
        LOGGER.debug("PDFExtractor crashed on %s: %s", url, e)
        return None


########################################################################
# 4. Bundled-JS / JSON  ------------------------------------------------
#    Works on URLs like “…/main.a1b2c3.js” or “…/next-data-build.json”
########################################################################
def try_bundles(url: str, *, min_len: int = 200, **__) -> str | None:
    # fast negative – only .js, .mjs or .json extensions
    if not re.search(r"\.(?:js|mjs|json)(?:\?|$)", url, re.I):
        return None

    raw = _fetch(url)  # cached + polite gap already handled
    if len(raw) < 500:  # skip very small assets
        return None

    # 1️⃣  Yank out anything that looks like a big JSON blob
    m = re.search(r"\{.*\}", raw, re.S)
    payload = m.group(0) if m else raw

    # 2️⃣  Undo common escape sequences (\\n, \\uXXXX, etc.)
    try:
        payload = bytes(payload, "utf-8").decode("unicode_escape")
    except Exception as e:
        logging.exception(e)
        ui.error("Something went wrong in the validation layer.")
        pass

    # 3️⃣  Strip JS comments and collapse whitespace
    payload = re.sub(r"//.*?$|/\\*.*?\\*/", " ", payload, flags=re.M | re.S)
    txt = _postprocess(payload)

    return txt if len(txt) >= min_len else None


def _scrape_frame(frame, *, depth: int = 0, max_depth: int = 4) -> str:
    """
    Recursively harvest visible innerText from:
    • the current frame
    • any shadow-DOM trees
    • all child frames (same-origin or cross-origin)
    Falls back to HTTP GET for cross-origin iframes.
    """
    if depth > max_depth:
        return ""

    # 1️⃣  Visible nodes in this frame
    txt = frame.evaluate(
        """
        () => [...document.querySelectorAll('*')]
              .filter(n => n.offsetParent !== null)
              .map(n => n.innerText.trim())
              .join(' ')
    """
    ).strip()

    # 2️⃣  Shadow-DOM
    shadow = frame.evaluate(
        """
        () => {
          function deep(root){
            let t='';
            for(const n of root.querySelectorAll('*')){
              if(n.shadowRoot) t += ' ' + deep(n.shadowRoot);
            }
            return t;
          }
          return deep(document);
        }
    """
    ).strip()
    if shadow:
        txt += " " + shadow

    # 3️⃣  Child frames
    for ch in frame.child_frames:
        try:
            txt += " " + _scrape_frame(ch, depth=depth + 1, max_depth=max_depth)
        except Exception as e:
            logging.exception(e)
            ui.error("Something went wrong in the validation layer.")
            # cross-origin → fall back to HTTP fetch + generic_html
            try:
                html_text = generic_html(ch.url) or ""
                if html_text:
                    txt += " " + html_text
            except Exception as e:
                logging.exception(e)
                ui.error("Something went wrong in the validation layer.")
                pass

    return txt.strip()


def playwright_fallback(url: str, **__) -> str | None:
    """
    Last-resort extractor: headless Chromium + auto-scroll + shadow-DOM scrape.

    • Skips obvious binary resources (.pdf, images, zips) – earlier layers handle those.
    • Catches Playwright navigation errors (net::ERR_ABORTED, timeouts, …) and
      returns None instead of raising, so the dispatcher can move on cleanly.
    • Closes the page/context in a finally-block to avoid leaking handles.
    """
    # 1️⃣  Skip non-HTML file types ------------------------------------------------
    if pathlib.Path(urllib.parse.urlparse(url).path).suffix.lower() in {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".zip",
    }:
        return None  # let PDF/image extractor (or none) handle it

    # 2️⃣  Get (or lazily create) the shared browser ------------------------------
    browser = _shared_browser()  # your existing helper
    context = browser.new_context()  # sandboxed per-request
    page = context.new_page()

    try:
        # 3️⃣  Navigate & wait for network to go (mostly) idle
        page.goto(url, wait_until="networkidle", timeout=30_000)

        # 4️⃣  Auto-scroll so lazy-loaders fire
        _scroll_to_bottom(page)

        # 5️⃣  Extract text from main frame (plus shadow DOM / iframes in helper)
        text = _scrape_frame(page.main_frame)

        return _postprocess(text) if text else None

    # 6️⃣  Graceful degradation on navigation errors -----------------------------
    except PlaywrightError as exc:
        LOGGER.debug("Playwright aborted on %s: %s", url, exc)
        ui.write("playwright navigation error:", exc)
        return None  # count as miss; dispatcher will move on

    finally:
        # Always clean up handles
        page.close()
        context.close()


def _shared_browser():
    if _browser_cache["browser"] is None:
        _browser_cache["pw"] = sync_playwright().start()
        _browser_cache["browser"] = _browser_cache["pw"].chromium.launch(headless=True)
    return _browser_cache["browser"]  # ← return, not yield


def _scroll_to_bottom(page, pause_ms: int = 250, max_scrolls: int = 20):
    last_height = 0
    for _ in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(pause_ms)
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def llm_fallback(*_, **__):  # dummy that always fails gracefully
    return None


# --------------------------------------------------------------------------- #
#  Tiny wrapper-classes so the new dispatcher can “see” each scraper.
#  You never have to edit these again – just change the priority number
#  if you want to move a scraper earlier/later in the chain.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
#  Tiny wrappers so the new dispatcher sees each scraper
# --------------------------------------------------------------------------- #
from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass(order=True, slots=True)
class _FnWrapper:
    """Make a plain function look like a class-based extractor."""

    priority: int
    fn: Callable[..., Optional[str]]
    name: str = ""

    def __post_init__(self):
        # self.name = self.fn.__name__      # old
        self.name = self.__class__.__name__  # new → logs "HTMLExtractor"

    def __call__(self, url: str, **kwargs):
        return self.fn(url, **kwargs)


# --- one class per scraper, each on its own block --------------------------
class SanityExtractor(_FnWrapper):
    def __init__(self):
        super().__init__(10, try_sanity)


class PDFExtractor(_FnWrapper):
    def __init__(self):
        super().__init__(20, try_pdf)


class HTMLExtractor(_FnWrapper):
    def __init__(self):
        super().__init__(30, generic_html)


class BundleExtractor(_FnWrapper):
    def __init__(self):
        super().__init__(40, try_bundles)


class BrowserExtractor(_FnWrapper):
    def __init__(self):
        super().__init__(50, playwright_fallback)


# --------------------------------------------------------------------------- #
ACTIVE_LAYERS: List[_FnWrapper] = [
    SanityExtractor(),
    PDFExtractor(),
    HTMLExtractor(),
    BundleExtractor(),
    BrowserExtractor(),
]

ACTIVE_LAYERS.sort(key=lambda layer: layer.priority)

__all__ = [
    "try_sanity",
    "try_pdf",
    "generic_html",
    "try_bundles",
    "playwright_fallback",
    "SanityExtractor",
    "HTMLExtractor",
    "PDFExtractor",
    "BundleExtractor",
    "BrowserExtractor",
    "ACTIVE_LAYERS",
]
