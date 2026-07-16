"""Utilities for normalising numbers, dates and inferring direction."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Optional

from .keywords import KEYWORDS

EU_NUMBER_RE = re.compile(r"(?<!\d)\d{1,3}(?:\.\d{3})*,\d{2}")
US_NUMBER_RE = re.compile(r"(?<!\d)\d{1,3}(?:,\d{3})*\.\d{2}")
INT_NUMBER_RE = re.compile(r"(?<!\d)\d+(?:[.,]\d{2})?")
DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-](?:\d{2}|\d{4})\b")
ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def parse_amount(token: str) -> Decimal:
    """Parse a currency amount token into Decimal."""
    token = token.replace("\u00a0", "").strip()
    for cur in KEYWORDS.currencies:
        token = token.replace(cur, "")
    token = token.replace(" ", "")
    if EU_NUMBER_RE.fullmatch(token):
        token = token.replace(".", "").replace(",", ".")
    elif US_NUMBER_RE.fullmatch(token):
        token = token.replace(",", "")
    token = token.replace(",", ".")
    return Decimal(token)


def parse_amount_any(text: str) -> Optional[Decimal]:
    """Find and parse the first amount in text."""
    cleaned = text.replace(" ", "")
    m = EU_NUMBER_RE.search(cleaned) or US_NUMBER_RE.search(cleaned)
    if not m:
        m = INT_NUMBER_RE.search(cleaned)
        if m:
            token = m.group()
            if "," not in token and "." not in token and len(token) > 7:
                return None
    if not m:
        return None
    try:
        return parse_amount(m.group())
    except Exception as e:
        logging.exception(e)
        return None


def parse_date_token(token: str) -> date:
    """Parse various date formats."""
    token = token.strip()
    if ISO_DATE_RE.fullmatch(token):
        dt = datetime.strptime(token, "%Y-%m-%d").date()
        return dt
    parts = re.split(r"[./-]", token)
    if len(parts[2]) == 2:
        year = int(parts[2])
        year += 2000 if year < 70 else 1900
        parts[2] = str(year)
    delimiter = "/"
    if "." in token:
        delimiter = "."
    elif "-" in token:
        delimiter = "-"
    fmt = f"%d{delimiter}%m{delimiter}%Y"
    normalised = delimiter.join(parts)
    return datetime.strptime(normalised, fmt).date()


def extract_dates(tokens: Iterable[str]) -> list[date]:
    dates: list[date] = []
    for tok in tokens:
        if DATE_RE.fullmatch(tok) or ISO_DATE_RE.fullmatch(tok):
            try:
                dates.append(parse_date_token(tok))
            except ValueError as e:
                logging.debug("Failed to parse date token %s: %s", tok, e)
                continue
    return dates


def infer_direction(description: str) -> Optional[str]:
    desc = description.lower()
    for kw in KEYWORDS.incoming:
        if kw.lower() in desc:
            return "credit"
    for kw in KEYWORDS.outgoing:
        if kw.lower() in desc:
            return "debit"
    return None
