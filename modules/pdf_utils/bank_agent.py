"""
Agentic multi‑strategy PDF parser for bank statements.

This parser tries to extract tables via pdfplumber, then falls back to
line‑by‑line heuristics, and finally to OCR if no text is embedded.
It returns a list of Transaction objects (date, amount, description).
"""

import io
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import pdfplumber

from modules.pdf_utils.pdf_utils import extract_pdf_text_with_ocr


# local type for the returned transaction
@dataclass
class BankTransaction:
    date: datetime
    amount: float
    description: str


_DATE_RE = re.compile(r"\b([0-3]?\d/[01]?\d/20\d{2})\b")


def _parse_it_date(s: str) -> Optional[datetime]:
    m = _DATE_RE.search(s or "")
    return datetime.strptime(m.group(1), "%d/%m/%Y") if m else None


def _parse_it_amount(s: str) -> Optional[float]:
    s = (s or "").strip().replace("€", "").replace("\u00a0", "")
    # handle trailing minus: "1.234,56-"
    if s.endswith("-") and not s.startswith("-"):
        s = "-" + s[:-1]
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def extract_bank_pdf(pdf_bytes: bytes, lang: str = "ita") -> List[BankTransaction]:
    """
    Parse a bank statement PDF into a list of transactions.
    Strategy:
      1) pdfplumber tables
      2) text heuristics
      3) OCR fallback
    """
    transactions: List[BankTransaction] = []

    # 1) table extraction
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table or not table[0]:
                    continue
                header = [
                    c.lower().strip() if isinstance(c, str) else "" for c in table[0]
                ]

                # find relevant columns
                def col(name):
                    return header.index(name) if name in header else None

                c_date = col("data")
                c_desc = col("descrizione")
                c_imp = col("importo")
                c_deb = col("uscite")
                c_cred = col("entrate")
                # skip if no date column
                if c_date is None:
                    continue
                for row in table[1:]:
                    d = _parse_it_date(row[c_date])
                    if not d:
                        continue
                    desc = row[c_desc] if c_desc is not None else ""
                    amt: Optional[float] = None
                    if c_imp is not None:
                        amt = _parse_it_amount(row[c_imp])
                    else:
                        if c_deb is not None:
                            deb = _parse_it_amount(row[c_deb])
                            if deb:
                                amt = -abs(deb)
                        if c_cred is not None and amt is None:
                            cred = _parse_it_amount(row[c_cred])
                            if cred:
                                amt = abs(cred)
                    if amt is None:
                        continue
                    transactions.append(BankTransaction(d, amt, desc))
    # 2) text heuristics
    if not transactions:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text = page.get_text()
            for line in text.splitlines():
                d = _parse_it_date(line)
                if not d:
                    continue
                numbers = [
                    m.group(0) for m in re.finditer(r"-?[\d\.\s]*,\d{2}-?", line)
                ]
                if not numbers:
                    continue
                amt = _parse_it_amount(numbers[-1])
                if amt is None:
                    continue
                desc = _DATE_RE.sub("", line).replace(numbers[-1], "").strip(" -–:\t")
                transactions.append(BankTransaction(d, amt, desc))
    # 3) OCR fallback
    if not transactions:
        ocr_text = extract_pdf_text_with_ocr(
            pdf_bytes, lang=lang, retries=1
        ).text
        for line in ocr_text.splitlines():
            d = _parse_it_date(line)
            if not d:
                continue
            numbers = [
                m.group(0) for m in re.finditer(r"-?[\d\.\s]*,\d{2}-?", line)
            ]
            if not numbers:
                continue
            amt = _parse_it_amount(numbers[-1])
            if amt is None:
                continue
            desc = _DATE_RE.sub("", line).replace(numbers[-1], "").strip()
            transactions.append(BankTransaction(d, amt, desc))
    return transactions
