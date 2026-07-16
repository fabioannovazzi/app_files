"""Extraction strategies for different statement layouts."""

from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import List

import pdfplumber

from .lexicon import Lexicon
from .model import BankTransaction
from .normalize import (
    combine_debit_credit,
    detect_number_format,
    parse_amount,
    parse_date,
)


class StrategyError(RuntimeError):
    pass


def _find_header_row(table: List[List[str]], lex: Lexicon) -> int | None:
    for idx, row in enumerate(table):
        text = " ".join(c.lower() for c in row if c)
        for pat in lex.header_patterns:
            if re.search(pat, text):
                return idx
    return None


def strategy_layout(
    page: pdfplumber.page.Page, lex: Lexicon, lang: str
) -> List[BankTransaction]:
    """Extract transactions when a structured table is present."""
    table = page.extract_table()
    if not table:
        return []
    header_idx = _find_header_row(table, lex)
    if header_idx is None:
        return []
    header = [c.lower() if c else "" for c in table[header_idx]]
    data_rows = table[header_idx + 1 :]
    transactions: List[BankTransaction] = []
    for row in data_rows:
        raw = {header[i]: row[i] for i in range(len(header))}
        posted = parse_date(row[0], lang)
        if posted is None:
            continue
        amount = None
        if "debit" in header and "credit" in header:
            debit = row[header.index("debit")] if "debit" in header else None
            credit = row[header.index("credit")] if "credit" in header else None
            amount = combine_debit_credit(debit, credit, lang)
        elif "amount" in header:
            amount = parse_amount(row[header.index("amount")], lang)
        if amount is None:
            continue
        desc = row[header.index("description")] if "description" in header else ""
        currency = row[header.index("currency")] if "currency" in header else None
        transactions.append(
            BankTransaction(
                posted_date=posted,
                value_date=None,
                description=desc,
                amount=amount,
                currency=currency,
                raw=raw,
            )
        )
    return transactions


def strategy_stream(
    page: pdfplumber.page.Page, lex: Lexicon, lang: str
) -> List[BankTransaction]:
    """Parse lines of text without relying on explicit table structure."""
    text = page.extract_text() or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    transactions: List[BankTransaction] = []
    amount_re = re.compile(r"[+-]?\d[\d\.,]*")
    date_re = re.compile(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}")
    dec_sep, thou_sep = detect_number_format(lines)
    for idx, line in enumerate(lines, start=1):
        if any(s in line.lower() for s in lex.sentinels):
            break
        dmatch = date_re.search(line)
        amatch = amount_re.search(line[::-1])
        if not dmatch or not amatch:
            continue
        date_str = dmatch.group()
        amount_str = amatch.group()[::-1]
        desc = line[dmatch.end() : len(line) - len(amount_str)].strip()
        posted = parse_date(date_str, lang)
        if posted is None:
            continue
        try:
            amount = parse_amount(amount_str, lang, dec_sep, thou_sep)
        except Exception as e:
            logging.exception(e)
            continue
        transactions.append(
            BankTransaction(
                posted_date=posted,
                value_date=None,
                description=desc,
                amount=amount,
                currency=None,
                source_page=page.page_number,
                line_no=idx,
                raw={"line": line},
                confidence=0.8,
            )
        )
    return transactions


def strategy_ocr(
    page: pdfplumber.page.Page, lex: Lexicon, lang: str
) -> List[BankTransaction]:
    """OCR-based fallback via PaddleOCR; returns empty list when unavailable."""
    try:
        from PIL import Image
        from modules.slides.ocr import extract_text_from_image_bytes
    except Exception as e:  # pragma: no cover - optional dependency
        logging.exception(e)
        return []
    img = page.to_image(resolution=300).original
    pil_image = img if isinstance(img, Image.Image) else Image.fromarray(img)
    image_buf = BytesIO()
    pil_image.save(image_buf, format="PNG")
    text = extract_text_from_image_bytes(
        image_buf.getvalue(),
        lang=lang,
        preprocess_profile="document_scan",
        allow_preprocess_fallback=True,
    )
    fake_page = type(
        "P", (), {"extract_text": lambda self: text, "page_number": page.page_number}
    )()
    return strategy_stream(fake_page, lex, lang)
