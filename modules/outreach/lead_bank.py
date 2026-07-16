from __future__ import annotations

"""Source-first lead-bank discovery for outreach queues."""

import html
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Iterable, Protocol
from urllib.parse import urlparse

import requests

from modules.outreach.batch import OutreachLead, normalise_email
from modules.outreach.queue import append_leads_to_queue

__all__ = [
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "DiscoveredLeadBatch",
    "build_lead_bank_from_sources",
    "discover_leads_from_html",
    "discover_leads_from_source",
    "extract_email_addresses",
    "extract_pdf_text",
    "fetch_html_with_playwright",
    "fetch_static_html",
    "fetch_static_source_text",
    "load_source_urls",
]

LOGGER = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT_SECONDS = 20
_EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,63}", re.IGNORECASE)
_MAILTO_RE = re.compile(r"mailto:([^?\"'<>#\s]+)", re.IGNORECASE)
_USER_AGENT = (
    "Mozilla/5.0 (compatible; MparanzaOutreachLeadBank/1.0; " "+https://mparanza.com/)"
)


class _RequestsLike(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: int,
    ) -> requests.Response:
        """Return an HTTP response for a GET request."""


@dataclass(frozen=True)
class DiscoveredLeadBatch:
    """New queue rows found from one public source."""

    source_url: str
    leads: tuple[OutreachLead, ...]


def extract_email_addresses(text: str) -> tuple[str, ...]:
    """Extract normalized email addresses from visible text or mailto links."""

    decoded = html.unescape(text)
    candidates = [*_MAILTO_RE.findall(decoded), *_EMAIL_RE.findall(decoded)]
    emails: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = candidate.strip().strip(".,;:()[]{}<>")
        try:
            address = normalise_email(cleaned)
        except ValueError:
            continue
        if address in seen:
            continue
        emails.append(address)
        seen.add(address)
    return tuple(emails)


def fetch_static_html(
    url: str,
    *,
    timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    session: _RequestsLike | None = None,
) -> str:
    """Fetch a public source page without browser rendering."""

    return fetch_static_source_text(
        url,
        timeout_seconds=timeout_seconds,
        session=session,
    )


def fetch_static_source_text(
    url: str,
    *,
    timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    session: _RequestsLike | None = None,
) -> str:
    """Fetch a public HTML or text-PDF source without browser rendering."""

    client = session or requests.Session()
    response = client.get(
        url,
        headers={"User-Agent": _USER_AGENT},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if _looks_like_pdf(url, content_type, response.content):
        return extract_pdf_text(response.content)
    return response.text


def extract_pdf_text(content: bytes) -> str:
    """Extract text from a public text-based PDF register."""

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(page_texts)


def fetch_html_with_playwright(
    url: str,
    *,
    timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> str:
    """Fetch a public source page after browser rendering."""

    from playwright.sync_api import sync_playwright

    timeout_ms = timeout_seconds * 1000
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=_USER_AGENT)
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            return str(page.content())
        finally:
            browser.close()


def discover_leads_from_source(
    source_url: str,
    *,
    country: str,
    city: str = "",
    source_note: str = "public-directory",
    use_playwright: bool = False,
    timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> DiscoveredLeadBatch:
    """Fetch one public source URL and extract queue-ready leads from it."""

    html_text = (
        fetch_html_with_playwright(source_url, timeout_seconds=timeout_seconds)
        if use_playwright
        else fetch_static_source_text(source_url, timeout_seconds=timeout_seconds)
    )
    leads = discover_leads_from_html(
        html_text,
        source_url=source_url,
        country=country,
        city=city,
        source_note=source_note,
    )
    return DiscoveredLeadBatch(source_url=source_url, leads=tuple(leads))


def discover_leads_from_html(
    html_text: str,
    *,
    source_url: str,
    country: str,
    city: str = "",
    source_note: str = "public-directory",
) -> list[OutreachLead]:
    """Extract queue-ready leads from an already-fetched public source page."""

    parser = _LeadHTMLParser()
    parser.feed(html_text)
    raw_lines = [_clean_text(line) for line in html_text.splitlines()]
    lines = [line for line in [*parser.lines, *raw_lines] if line]
    page_text = "\n".join(lines)
    title = parser.title or _host_label(source_url)
    emails = [
        email_address
        for email_address in extract_email_addresses(f"{html_text}\n{page_text}")
        if _usable_outreach_email(email_address)
    ]
    return [
        OutreachLead(
            name=_name_for_email(email_address, lines, title),
            email=email_address,
            city=city,
            country=country,
            source_url=source_url,
            source_note=source_note,
        )
        for email_address in emails
    ]


def build_lead_bank_from_sources(
    source_urls: Iterable[str],
    *,
    queue_path: Path,
    ledger_path: Path,
    country: str,
    city: str = "",
    source_note: str = "public-directory",
    use_playwright: bool = False,
    timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    salt: str = "",
) -> int:
    """Scrape public sources and append only new, not-yet-contacted leads."""

    appended_count = 0
    for source_url in source_urls:
        stripped_url = source_url.strip()
        if not stripped_url:
            continue
        batch = discover_leads_from_source(
            stripped_url,
            country=country,
            city=city,
            source_note=source_note,
            use_playwright=use_playwright,
            timeout_seconds=timeout_seconds,
        )
        appended = append_leads_to_queue(
            queue_path,
            batch.leads,
            ledger_path=ledger_path,
            salt=salt,
        )
        appended_count += appended
        LOGGER.info(
            "source=%s discovered=%s appended=%s queue=%s",
            batch.source_url,
            len(batch.leads),
            appended,
            queue_path,
        )
    return appended_count


def load_source_urls(path: Path) -> tuple[str, ...]:
    """Load newline-delimited public source URLs, ignoring comments."""

    urls: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.split("#", 1)[0].strip()
            if line:
                urls.append(line)
    return tuple(urls)


class _LeadHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.title = ""
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in {"br", "p", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._append_line("")
        for name, value in attrs:
            if name == "href" and value and value.casefold().startswith("mailto:"):
                for email_address in extract_email_addresses(value):
                    self._append_line(email_address)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "li", "tr", "h1", "h2", "h3", "h4", "div"}:
            self._append_line("")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = _clean_text(data)
        if not cleaned:
            return
        if self._in_title:
            self.title = _clean_text(f"{self.title} {cleaned}")
        self._append_line(cleaned)

    def _append_line(self, value: str) -> None:
        cleaned = _clean_text(value)
        if cleaned:
            self.lines.append(cleaned)


def _name_for_email(email_address: str, lines: list[str], fallback_title: str) -> str:
    for index, line in enumerate(lines):
        if email_address not in line.casefold():
            continue
        name = _previous_label(lines, index)
        if name:
            return name
    return fallback_title


def _previous_label(lines: list[str], index: int) -> str:
    for previous_line in reversed(lines[max(0, index - 6) : index]):
        candidate = _clean_text(previous_line)
        name_match = re.match(r"^\d+\s+([A-ZÀ-ÖØ-Þ][^@\d]{2,100})$", candidate)
        if name_match:
            return name_match.group(1).strip()
        trailing_number_match = re.match(r"^([A-ZÀ-ÖØ-Þ][^@\d]{2,100})\d+$", candidate)
        if trailing_number_match:
            return trailing_number_match.group(1).strip()
    for previous_line in reversed(lines[max(0, index - 5) : index]):
        candidate = _clean_text(previous_line)
        if not candidate or "@" in candidate:
            continue
        if re.match(r"^\d+\/[A-Z]\s+\d{5}", candidate):
            continue
        if re.match(r"^\d{2}\/\d{2}\/\d{4}", candidate):
            continue
        label = candidate.rstrip(":")
        if label.casefold() in {"email", "e-mail", "mail", "contact", "contacts"}:
            continue
        if len(label) <= 120:
            return label
    return ""


def _host_label(source_url: str) -> str:
    host = urlparse(source_url).netloc or source_url
    return host.removeprefix("www.")


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value).split())


def _looks_like_pdf(url: str, content_type: str, content: bytes) -> bool:
    return (
        "application/pdf" in content_type.casefold()
        or urlparse(url).path.casefold().endswith(".pdf")
        or content.startswith(b"%PDF")
    )


def _usable_outreach_email(email_address: str) -> bool:
    local_part, domain = email_address.rsplit("@", 1)
    domain_parts = set(domain.casefold().split("."))
    suffix = domain.rsplit(".", 1)[-1].casefold()
    blocked_domains = {
        "beispiel.ch",
        "company.com",
        "divi.express",
        "domain.com",
        "email.ch",
        "example.com",
        "legit.com",
        "mailservice.com",
        "treuhandsuisse.ch",
        "treuhandsuisse-zh.ch",
    }
    allowed_suffixes = {
        "ch",
        "com",
        "de",
        "eu",
        "fr",
        "it",
        "li",
        "net",
        "org",
        "swiss",
        "uk",
    }
    if "%" in email_address or "*" in email_address:
        return False
    if suffix not in allowed_suffixes:
        return False
    if suffix in {"gif", "jpg", "jpeg", "png", "svg", "webp"} or len(suffix) > 10:
        return False
    if domain.casefold() in blocked_domains:
        return False
    if "sentry" in domain.casefold() or "wixpress.com" in domain.casefold():
        return False
    if len(local_part) > 40 and re.fullmatch(r"[a-f0-9]+", local_part.casefold()):
        return False
    if any("pec" in part or "legalmail" in part for part in domain_parts):
        return False
    if local_part.casefold().startswith("pec"):
        return False
    if domain.startswith("odcec") or ".odcec" in domain:
        return False
    return True
