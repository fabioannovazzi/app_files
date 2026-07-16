from __future__ import annotations

"""Populate the Italy organization outreach queue from CNDCEC order details."""

import argparse
import csv
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.outreach.batch import OutreachLead
from modules.outreach.lead_bank import extract_email_addresses
from modules.outreach.queue import append_leads_to_queue

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)

_CNDCEC_ORDERS_URL = (
    "https://commercialisti.it/il-consiglio-nazionale/ordini-territoriali/"
)
_DETAIL_URL = "https://ricerca.commercialisti.it/enteDettaglio"
_USER_AGENT = (
    "Mozilla/5.0 (compatible; MparanzaOutreachDiscovery/1.0; " "+https://mparanza.com/)"
)
_ROLE_LOCAL_PARTS = (
    "segreteria",
    "info",
    "ordine",
    "odcec",
    "amministrazione",
    "presidenza",
)


@dataclass(frozen=True)
class TerritorialOrder:
    """One CNDCEC territorial-order option."""

    name: str
    identifier: str


def main() -> int:
    """Build the ODCEC organization queue from ranked pending orders."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ranking",
        default=Path("data/outreach/italian_odcec_organization_ranking_2026-05-29.csv"),
        type=Path,
    )
    parser.add_argument(
        "--queue",
        default=Path("data/outreach/queues/italy-organization.csv"),
        type=Path,
    )
    parser.add_argument(
        "--ledger",
        default=Path("data/outreach/outreach_ledger.jsonl"),
        type=Path,
    )
    parser.add_argument(
        "--sources-dir",
        default=Path("data/outreach/sources/italy/odcec-organizations"),
        type=Path,
    )
    parser.add_argument("--timeout-seconds", default=10, type=int)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    session = requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT})

    orders = fetch_territorial_orders(
        session,
        args.sources_dir,
        timeout_seconds=args.timeout_seconds,
    )
    ranked_rows = load_pending_ranked_orders(args.ranking)
    leads = discover_organization_leads(
        ranked_rows,
        orders,
        session,
        args.sources_dir,
        timeout_seconds=args.timeout_seconds,
    )
    appended = append_leads_to_queue(args.queue, leads, ledger_path=args.ledger)
    LOGGER.info(
        "ranked_pending=%s leads_found=%s appended=%s queue=%s",
        len(ranked_rows),
        len(leads),
        appended,
        args.queue,
    )
    return 0


def fetch_territorial_orders(
    session: requests.Session,
    sources_dir: Path,
    *,
    timeout_seconds: int,
) -> dict[str, TerritorialOrder]:
    """Fetch and parse CNDCEC territorial-order identifiers."""

    sources_dir.mkdir(parents=True, exist_ok=True)
    response = session.get(_CNDCEC_ORDERS_URL, timeout=timeout_seconds)
    response.raise_for_status()
    html = response.text
    (sources_dir / "cndcec-ordini-territoriali.html").write_text(
        html,
        encoding="utf-8",
    )
    soup = BeautifulSoup(html, "html.parser")
    select = soup.select_one("select#ordineTerritorialeSelect")
    if select is None:
        raise ValueError("CNDCEC territorial-order select not found")

    orders: dict[str, TerritorialOrder] = {}
    for option in select.select("option[value]"):
        identifier = option.get("value", "").strip()
        name = option.get_text(" ", strip=True)
        if not identifier or not name or name == "Seleziona una voce":
            continue
        orders[_normalise_name(name)] = TerritorialOrder(
            name=name, identifier=identifier
        )
    return orders


def load_pending_ranked_orders(path: Path) -> list[str]:
    """Load ranked ODCEC names that still need organization outreach."""

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        (row.get("odcec") or "").strip()
        for row in rows
        if (row.get("status") or "").strip() == "pending"
        and (row.get("odcec") or "").strip()
    ]


def discover_organization_leads(
    order_names: list[str],
    orders: dict[str, TerritorialOrder],
    session: requests.Session,
    sources_dir: Path,
    *,
    timeout_seconds: int,
) -> tuple[OutreachLead, ...]:
    """Fetch detail pages and extract one public non-PEC email per order."""

    leads: list[OutreachLead] = []
    missing: list[str] = []
    without_email: list[str] = []
    for order_name in order_names:
        order = orders.get(_normalise_name(order_name))
        if order is None:
            missing.append(order_name)
            continue
        source_url = f"{_DETAIL_URL}?id={order.identifier}"
        response = session.get(source_url, timeout=timeout_seconds)
        response.raise_for_status()
        html = response.text
        (sources_dir / f"{_slug(order.name)}.html").write_text(
            html,
            encoding="utf-8",
        )
        email = _select_organization_email(extract_email_addresses(html))
        if not email:
            without_email.append(order_name)
            continue
        leads.append(
            OutreachLead(
                name=f"ODCEC {order.name}",
                email=email,
                city=order.name,
                country="Italy",
                source_url=source_url,
                source_note="cndcec-ordine-territoriale",
            )
        )
    if missing:
        LOGGER.warning("missing_order_ids=%s", ", ".join(missing))
    if without_email:
        LOGGER.warning("orders_without_non_pec_email=%s", ", ".join(without_email))
    return tuple(leads)


def _select_organization_email(emails: tuple[str, ...]) -> str:
    usable = [email for email in emails if _usable_organization_email(email)]
    if not usable:
        return ""
    for role in _ROLE_LOCAL_PARTS:
        for email in usable:
            local_part = email.split("@", 1)[0].casefold()
            if local_part == role or local_part.startswith(f"{role}."):
                return email
    return usable[0]


def _usable_organization_email(email: str) -> bool:
    local_part, domain = email.casefold().rsplit("@", 1)
    domain_parts = set(domain.split("."))
    if any("pec" in part or "legalmail" in part for part in domain_parts):
        return False
    if local_part.startswith("pec"):
        return False
    if local_part in {"privacy", "dpo", "webmaster", "noreply", "no-reply"}:
        return False
    return True


def _normalise_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalise_name(value)).strip("-") or "ordine"


if __name__ == "__main__":
    raise SystemExit(main())
