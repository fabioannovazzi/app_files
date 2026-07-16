from __future__ import annotations

"""Populate outreach queues from public accounting directories."""

import argparse
import csv
import logging
import math
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.outreach.batch import OutreachLead, normalise_email
from modules.outreach.lead_bank import discover_leads_from_html
from modules.outreach.queue import append_leads_to_queue

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; MparanzaOutreachDiscovery/1.0; " "+https://mparanza.com/)"
)
_TREUHAND_AJAX_URL = "https://www.treuhandsuisse-zh.ch/views/ajax"
_TREUHAND_DIRECTORY_URL = (
    "https://www.treuhandsuisse-zh.ch/mitgliedschaft/mitglied-finden"
)
_TREUHAND_VIEW_PARAMS = {
    "view_name": "companies",
    "view_display_id": "block_1",
    "view_args": "",
    "view_path": "/node/8147",
    "view_base_path": "admin/content/companies",
    "view_dom_id": "3c926cc21ddd336865cf947c1363153c79aef16cb32a6aca3ee9678a1270b910",
    "pager_element": "0",
}
_SWISS_ROMANDE_SECTIONS = {
    "Fribourg",
    "Genève",
    "Neuchâtel, Jura et Berne romand",
    "Valais/Wallis",
    "Vaudoise",
}
_SWISS_GERMAN_SECTIONS = {
    "Basel-Nordwestschweiz",
    "Bern",
    "Graubünden",
    "Ostschweiz",
    "Zentralschweiz",
    "Zürich",
}
_ACCA_LOCATIONS = (
    "London",
    "Manchester",
    "Birmingham",
    "Leeds",
    "Liverpool",
    "Bristol",
    "Sheffield",
    "Newcastle",
    "Nottingham",
    "Glasgow",
    "Edinburgh",
    "Cardiff",
    "Belfast",
)
_CONTACT_PATHS = (
    "",
    "/contact",
    "/contact/",
    "/contacts",
    "/contacts/",
    "/contactez-nous",
    "/contactez-nous/",
    "/kontakt",
    "/kontakt/",
    "/fr/contact",
    "/fr/contact/",
    "/fr/contacts",
    "/fr/contacts/",
    "/fr/contactez-nous",
    "/fr/contactez-nous/",
    "/fr/nous-contacter",
    "/fr/nous-contacter/",
    "/de/kontakt",
)
_CONTACT_LINK_KEYWORDS = (
    "contact",
    "contactez",
    "kontakt",
    "contatti",
    "nous-contacter",
)
_MAX_CONTACT_URLS_PER_SITE = 20
_ROLE_LOCAL_PARTS = {
    "admin",
    "contact",
    "hello",
    "info",
    "mail",
    "office",
    "secretariat",
    "sekretariat",
}


@dataclass(frozen=True)
class TreuhandCompany:
    """One firm row from the TREUHAND|SUISSE directory."""

    name: str
    city: str
    section: str
    canton: str
    website: str


@dataclass(frozen=True)
class DiscoverySummary:
    """Discovery result for one queue."""

    region: str
    sources_checked: int
    leads_found: int
    rows_appended: int
    queue_path: Path


def main() -> int:
    """Run public-source discovery for requested regions."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regions",
        nargs="+",
        choices=("swiss-romande", "swiss-german", "uk"),
        default=("swiss-romande", "swiss-german", "uk"),
    )
    parser.add_argument("--data-dir", default=Path("data/outreach"), type=Path)
    parser.add_argument(
        "--ledger",
        default=Path("data/outreach/outreach_ledger.jsonl"),
        type=Path,
    )
    parser.add_argument("--timeout-seconds", default=10, type=int)
    parser.add_argument("--delay-seconds", default=0.2, type=float)
    parser.add_argument("--max-workers", default=16, type=int)
    parser.add_argument("--use-cached-treuhand", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    session = requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT})
    summaries: list[DiscoverySummary] = []
    regions = set(args.regions)
    if {"swiss-romande", "swiss-german"}.intersection(regions):
        sources_dir = args.data_dir / "sources"
        treuhand_companies = (
            load_cached_treuhand_companies(sources_dir)
            if args.use_cached_treuhand
            else fetch_treuhand_companies(
                session,
                sources_dir,
                timeout_seconds=args.timeout_seconds,
                delay_seconds=args.delay_seconds,
            )
        )
        if "swiss-romande" in regions:
            summaries.append(
                discover_swiss_region(
                    "swiss-romande",
                    treuhand_companies,
                    args.data_dir,
                    args.ledger,
                    session,
                    timeout_seconds=args.timeout_seconds,
                    delay_seconds=args.delay_seconds,
                    max_workers=args.max_workers,
                )
            )
        if "swiss-german" in regions:
            summaries.append(
                discover_swiss_region(
                    "swiss-german",
                    treuhand_companies,
                    args.data_dir,
                    args.ledger,
                    session,
                    timeout_seconds=args.timeout_seconds,
                    delay_seconds=args.delay_seconds,
                    max_workers=args.max_workers,
                )
            )
    if "uk" in regions:
        summaries.append(
            discover_uk(
                args.data_dir,
                args.ledger,
                session,
                timeout_seconds=args.timeout_seconds,
                delay_seconds=args.delay_seconds,
            )
        )
    for summary in summaries:
        LOGGER.info(
            "region=%s sources=%s leads_found=%s appended=%s queue=%s",
            summary.region,
            summary.sources_checked,
            summary.leads_found,
            summary.rows_appended,
            summary.queue_path,
        )
    return 0


def fetch_treuhand_companies(
    session: requests.Session,
    sources_dir: Path,
    *,
    timeout_seconds: int,
    delay_seconds: float,
) -> tuple[TreuhandCompany, ...]:
    """Fetch all company pages from the public TREUHAND|SUISSE directory."""

    target_dir = sources_dir / "switzerland"
    target_dir.mkdir(parents=True, exist_ok=True)
    first_html = _fetch_treuhand_page(
        session,
        0,
        target_dir,
        timeout_seconds=timeout_seconds,
    )
    total_rows = _treuhand_total_rows(first_html)
    page_count = max(1, math.ceil(total_rows / 25))
    companies = _parse_treuhand_companies(first_html)
    for page in range(1, page_count):
        sleep(delay_seconds)
        html = _fetch_treuhand_page(
            session,
            page,
            target_dir,
            timeout_seconds=timeout_seconds,
        )
        companies.extend(_parse_treuhand_companies(html))
    deduped = _dedupe_companies(companies)
    LOGGER.info(
        "Fetched %s TREUHAND|SUISSE company rows from %s pages",
        len(deduped),
        page_count,
    )
    return tuple(deduped)


def load_cached_treuhand_companies(sources_dir: Path) -> tuple[TreuhandCompany, ...]:
    """Load previously archived TREUHAND|SUISSE directory pages."""

    target_dir = sources_dir / "switzerland"
    paths = sorted(target_dir.glob("treuhandsuisse-companies-page-*.html"))
    companies: list[TreuhandCompany] = []
    for path in paths:
        companies.extend(_parse_treuhand_companies(path.read_text(encoding="utf-8")))
    deduped = _dedupe_companies(companies)
    LOGGER.info(
        "Loaded %s cached TREUHAND|SUISSE company rows from %s pages",
        len(deduped),
        len(paths),
    )
    return tuple(deduped)


def discover_swiss_region(
    region: str,
    companies: tuple[TreuhandCompany, ...],
    data_dir: Path,
    ledger_path: Path,
    session: requests.Session,
    *,
    timeout_seconds: int,
    delay_seconds: float,
    max_workers: int,
) -> DiscoverySummary:
    """Discover public emails for one Swiss regional queue."""

    sections = (
        _SWISS_ROMANDE_SECTIONS if region == "swiss-romande" else _SWISS_GERMAN_SECTIONS
    )
    queue_path = data_dir / "queues" / f"{region}.csv"
    target_companies = [
        company
        for company in companies
        if company.section in sections and company.website
    ]
    leads_found = 0
    rows_appended = 0
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        futures = [
            executor.submit(
                discover_company_website,
                company,
                region,
                timeout_seconds=timeout_seconds,
                delay_seconds=delay_seconds,
            )
            for company in target_companies
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            discovered = future.result()
            leads_found += len(discovered)
            if discovered:
                rows_appended += append_leads_to_queue(
                    queue_path,
                    discovered,
                    ledger_path=ledger_path,
                )
            if index % 100 == 0:
                LOGGER.info(
                    "region=%s checked %s/%s listed firm websites",
                    region,
                    index,
                    len(target_companies),
                )
    return DiscoverySummary(
        region=region,
        sources_checked=len(target_companies),
        leads_found=leads_found,
        rows_appended=rows_appended,
        queue_path=queue_path,
    )


def discover_company_website(
    company: TreuhandCompany,
    region: str,
    *,
    timeout_seconds: int,
    delay_seconds: float,
) -> list[OutreachLead]:
    """Fetch a listed firm website and keep one public contact email."""

    urls = list(_contact_urls(company.website))
    seen_urls = set(urls)
    found: list[OutreachLead] = []
    while urls and len(seen_urls) <= _MAX_CONTACT_URLS_PER_SITE:
        url = urls.pop(0)
        try:
            response = requests.get(
                url,
                headers={"User-Agent": _USER_AGENT},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue
        leads = discover_leads_from_html(
            response.text,
            source_url=response.url,
            country="Switzerland",
            city=company.city,
            source_note=f"treuhandsuisse-directory:{region}",
        )
        selected = _select_company_contact(leads, company)
        if selected is not None:
            found.append(
                OutreachLead(
                    name=company.name,
                    email=selected.email,
                    city=company.city,
                    country="Switzerland",
                    source_url=selected.source_url,
                    source_note=f"treuhandsuisse-directory:{region}",
                )
            )
            break
        for contact_url in _contact_links(response.text, response.url):
            if (
                contact_url not in seen_urls
                and len(seen_urls) < _MAX_CONTACT_URLS_PER_SITE
            ):
                urls.append(contact_url)
                seen_urls.add(contact_url)
        sleep(delay_seconds)
    return found


def discover_uk(
    data_dir: Path,
    ledger_path: Path,
    session: requests.Session,
    *,
    timeout_seconds: int,
    delay_seconds: float,
) -> DiscoverySummary:
    """Discover public emails from the ACCA firm directory."""

    queue_path = data_dir / "queues" / "uk.csv"
    sources_dir = data_dir / "sources" / "uk"
    sources_dir.mkdir(parents=True, exist_ok=True)
    leads: list[OutreachLead] = []
    sources_checked = 0
    for location in _ACCA_LOCATIONS:
        for page in range(1, 4):
            html = _fetch_acca_page(
                session,
                location,
                page,
                sources_dir,
                timeout_seconds=timeout_seconds,
            )
            sources_checked += 1
            page_leads = _parse_acca_leads(html, location)
            if not page_leads:
                break
            leads.extend(page_leads)
            sleep(delay_seconds)
    appended = append_leads_to_queue(queue_path, leads, ledger_path=ledger_path)
    return DiscoverySummary(
        region="uk",
        sources_checked=sources_checked,
        leads_found=len(leads),
        rows_appended=appended,
        queue_path=queue_path,
    )


def _fetch_treuhand_page(
    session: requests.Session,
    page: int,
    target_dir: Path,
    *,
    timeout_seconds: int,
) -> str:
    response = session.post(
        _TREUHAND_AJAX_URL,
        params={"_wrapper_format": "drupal_ajax", "page": page},
        data=_TREUHAND_VIEW_PARAMS,
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    commands = response.json()
    html = "".join(
        str(command.get("data", ""))
        for command in commands
        if command.get("command") == "insert"
    )
    (target_dir / f"treuhandsuisse-companies-page-{page + 1:03d}.html").write_text(
        html,
        encoding="utf-8",
    )
    return html


def _treuhand_total_rows(html: str) -> int:
    match = re.search(r"Zeige\s+\d+\s+-\s+\d+\s+von\s+(\d+)", html)
    if match is None:
        return 25
    return int(match.group(1))


def _parse_treuhand_companies(html: str) -> list[TreuhandCompany]:
    soup = BeautifulSoup(html, "html.parser")
    companies: list[TreuhandCompany] = []
    for row in soup.select("tbody tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        if len(cells) < 5:
            continue
        companies.append(
            TreuhandCompany(
                name=cells[0],
                city=cells[1],
                section=cells[2],
                canton=cells[3],
                website=_clean_website(cells[4]),
            )
        )
    return companies


def _dedupe_companies(companies: list[TreuhandCompany]) -> list[TreuhandCompany]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[TreuhandCompany] = []
    for company in companies:
        key = (company.name.casefold(), company.city.casefold(), company.website)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(company)
    return deduped


def _fetch_acca_page(
    session: requests.Session,
    location: str,
    page: int,
    target_dir: Path,
    *,
    timeout_seconds: int,
) -> str:
    response = session.get(
        "https://www.accaglobal.com/gb/en/member/find-an-accountant/find-firm/results.html",
        params={
            "location": location,
            "country": "GB",
            "firmname": "",
            "pagenumber": str(page),
            "resultsperpage": "50",
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    html = response.text
    slug = _slug(location)
    (target_dir / f"acca-results-{slug}-page-{page}.html").write_text(
        html,
        encoding="utf-8",
    )
    return html


def _parse_acca_leads(html: str, location: str) -> list[OutreachLead]:
    soup = BeautifulSoup(html, "html.parser")
    leads: list[OutreachLead] = []
    for row in soup.select("table.firm-search-results tbody tr[id^='rowId-']"):
        name_node = row.select_one("h5 a")
        email_node = row.select_one("a[href^='mailto:']")
        if name_node is None or email_node is None:
            continue
        email = _clean_email(email_node.get_text(strip=True))
        if not email or not _usable_email(email):
            continue
        details_href = name_node.get("href", "")
        source_url = urljoin("https://www.accaglobal.com", str(details_href)).replace(
            "isocountry=CH",
            "isocountry=GB",
        )
        leads.append(
            OutreachLead(
                name=name_node.get_text(" ", strip=True),
                email=email,
                city=location,
                country="United Kingdom",
                source_url=source_url,
                source_note="acca-firm-directory",
            )
        )
    return leads


def _select_company_contact(
    leads: list[OutreachLead], company: TreuhandCompany
) -> OutreachLead | None:
    usable = [
        lead
        for lead in leads
        if _usable_email(lead.email)
        and _email_matches_company(lead.email, lead.source_url, company.name)
    ]
    if not usable:
        return None
    role_leads = [
        lead
        for lead in usable
        if lead.email.split("@", 1)[0].casefold() in _ROLE_LOCAL_PARTS
    ]
    if role_leads:
        return role_leads[0]
    info_like = [
        lead
        for lead in usable
        if any(
            token in lead.email.split("@", 1)[0].casefold()
            for token in ("info", "contact")
        )
    ]
    if info_like:
        return info_like[0]
    return usable[0]


def _contact_urls(website: str) -> tuple[str, ...]:
    parsed = urlparse(website)
    if not parsed.scheme:
        website = f"https://{website}"
        parsed = urlparse(website)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls = [urljoin(base, path) for path in _CONTACT_PATHS]
    return tuple(dict.fromkeys(urls))


def _contact_links(html: str, source_url: str) -> tuple[str, ...]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for node in soup.select("a[href]"):
        href = str(node.get("href") or "").strip()
        label = node.get_text(" ", strip=True)
        combined = f"{href} {label}".casefold()
        if not any(keyword in combined for keyword in _CONTACT_LINK_KEYWORDS):
            continue
        parsed = urlparse(href)
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            continue
        links.append(urljoin(source_url, href))
    return tuple(dict.fromkeys(links))


def _clean_website(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    return cleaned if urlparse(cleaned).scheme else f"https://{cleaned}"


def _usable_email(email: str) -> bool:
    local_part, domain = email.casefold().rsplit("@", 1)
    domain_parts = domain.split(".")
    suffix = domain.rsplit(".", 1)[-1]
    blocked_domains = {
        "beispiel.ch",
        "beispiel.de",
        "company.com",
        "clearmediaconcept.ch",
        "comvation.com",
        "divi.express",
        "domaine.com",
        "email.ch",
        "example.com",
        "legit.com",
        "mailservice.com",
        "manix.ch",
        "privacybee.ch",
        "webromand.ch",
        "yourdomain.com",
    }
    allowed_suffixes = {
        "ch",
        "com",
        "de",
        "eu",
        "fr",
        "li",
        "net",
        "org",
        "swiss",
        "uk",
    }
    if "%" in email or "*" in email:
        return False
    if suffix not in allowed_suffixes:
        return False
    if suffix in {"gif", "jpg", "jpeg", "png", "svg", "webp"} or len(suffix) > 10:
        return False
    if domain in blocked_domains:
        return False
    if "sentry" in domain or "wixpress.com" in domain:
        return False
    if len(local_part) > 40 and re.fullmatch(r"[a-f0-9]+", local_part):
        return False
    if any("pec" in part or "legalmail" in part for part in domain_parts):
        return False
    if domain in {"accaglobal.com", "treuhandsuisse.ch", "treuhandsuisse-zh.ch"}:
        return False
    if local_part in {"webmaster", "privacy", "dpo", "noreply", "no-reply"}:
        return False
    return True


def _email_matches_company(email: str, source_url: str, company_name: str) -> bool:
    _local_part, domain = email.casefold().rsplit("@", 1)
    host = urlparse(source_url).netloc.casefold().removeprefix("www.")
    if host == domain or host.endswith(f".{domain}") or domain.endswith(f".{host}"):
        return True
    if domain in _personal_email_domains():
        return True
    reference_tokens = _meaningful_tokens(f"{company_name} {host}")
    domain_tokens = _meaningful_tokens(domain)
    return bool(reference_tokens.intersection(domain_tokens))


def _personal_email_domains() -> set[str]:
    return {
        "bluewin.ch",
        "gmail.com",
        "gmx.ch",
        "gmx.com",
        "gmx.de",
        "hotmail.ch",
        "hotmail.com",
        "hotmail.de",
        "icloud.com",
        "me.com",
        "outlook.com",
        "proton.me",
        "protonmail.com",
        "sunrise.ch",
        "yahoo.ch",
        "yahoo.com",
    }


def _meaningful_tokens(value: str) -> set[str]:
    stopwords = {
        "accounting",
        "advisory",
        "audit",
        "cabinet",
        "conseil",
        "conseils",
        "consulting",
        "fiduciaire",
        "gmbh",
        "group",
        "gruppe",
        "partner",
        "partners",
        "revision",
        "sarl",
        "steuerberatung",
        "swiss",
        "treuhand",
    }
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.casefold())
        if len(token) >= 4 and token not in stopwords
    }


def _clean_email(value: str) -> str:
    cleaned = value.strip().strip(".,;:()[]{}<>")
    try:
        return normalise_email(cleaned)
    except ValueError:
        return ""


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return cleaned or "source"


if __name__ == "__main__":
    raise SystemExit(main())
